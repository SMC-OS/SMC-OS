-- READ-ONLY PITR / WAL-archiver diagnostics for staging PostgreSQL (B1 evidence).
-- Run through the private tunnel, one read-only transaction, aggregate output only:
--   railway connect simo-postgres-staging --tunnel-only ...   (see docs/STAGING_RUNBOOK.md)
--   psql "$DSN" -v ON_ERROR_STOP=1 -f scripts/recovery/pitr_diagnostics.sql
-- Nothing here writes, changes settings, switches WAL or touches pgBackRest.
-- Keep the output outside Git. `archive_command` can contain provider details: do not paste it into tickets.

BEGIN READ ONLY;

\echo '== 1. Archiving configuration'
SELECT name, setting FROM pg_settings
WHERE name IN ('archive_mode', 'archive_timeout', 'wal_level', 'max_wal_size', 'wal_keep_size', 'archive_library')
ORDER BY name;

\echo '== 2. Archiver state (failures are cumulative since the last stats reset)'
SELECT archived_count, last_archived_wal, last_archived_time,
       failed_count, last_failed_wal, last_failed_time, stats_reset
FROM pg_stat_archiver;

\echo '== 3. Did archiving continue past the failure? (same timeline: WAL names sort chronologically)'
SELECT (last_archived_wal > last_failed_wal)            AS archived_past_last_failure,
       (last_archived_time > last_failed_time)           AS archived_after_last_failure,
       now() - last_archived_time                        AS archive_lag,
       now() - last_failed_time                          AS since_last_failure
FROM pg_stat_archiver;

\echo '== 4. Position and timeline'
SELECT now() AS server_now, pg_postmaster_start_time() AS postmaster_started,
       pg_current_wal_lsn() AS current_lsn, pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file,
       (SELECT timeline_id FROM pg_control_checkpoint()) AS timeline;

\echo '== 5. Backlog of segments waiting to be archived (needs pg_monitor/superuser; a growing count = stuck archiver)'
SELECT count(*) FILTER (WHERE name LIKE '%.ready') AS ready_not_yet_archived,
       count(*) FILTER (WHERE name LIKE '%.done')  AS done
FROM pg_ls_archive_statusdir();

ROLLBACK;

-- Decision rule (record the outcome in the A1 record; do not rely on `archive_mode=on` alone):
--   PASS    : archived_after_last_failure = true, archive_lag is within ~2 x archive_timeout (or the idle-database
--             equivalent), ready_not_yet_archived = 0 or 1, AND on the Postgres service
--             `pgbackrest info --output=json` shows a base backup whose WAL range is continuous to the latest
--             archived segment, AND `pgbackrest check` succeeds.
--   BLOCKED : any gap, a growing .ready backlog, no completed base backup, or `pgbackrest check` failing.
--   The two historic failures (last 2026-11-04 10:40 UTC) are explained only when the pgBackRest log shows the
--   failing archive-push at that time and a later successful push of the SAME segment (a retry), or a provider
--   incident notice for the same time. Without one of those they stay UNEXPLAINED.
