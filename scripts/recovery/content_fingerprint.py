"""Content-level fingerprints for the T0/T1 recovery-point comparison.

Row counts cannot detect an UPDATE or a swapped file, so these hash content:

* ``db_fingerprint``: one REPEATABLE READ / READ ONLY snapshot.  For every user
  table, the row count and a SHA-256 over every row's text form in sorted
  order, plus every sequence position (a ``nextval`` is a write too) and the
  Alembic revision.  The write-ahead-log position is recorded but is NOT part
  of the digest: it may advance for operational reasons (checkpoints,
  autovacuum) without any content change.
* ``uploads_manifest``: relative path, size and SHA-256 of every regular file,
  sorted.  Symlinks and special files are refused rather than skipped.

Neither function writes anything.  Identifiers and values stay in memory or in
the private operator record; only digests are meant to be quoted elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHUNK = 1024 * 1024
SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def db_fingerprint(dsn: str) -> dict[str, Any]:
    import psycopg
    from psycopg import sql

    with psycopg.connect(dsn, application_name="geocore_fingerprint") as conn:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        taken = conn.execute("SELECT clock_timestamp()").fetchone()[0]
        lsn = conn.execute("SELECT pg_current_wal_lsn()::text").fetchone()[0]
        version = conn.execute("SELECT current_setting('server_version')").fetchone()[0]
        tables = conn.execute(
            "SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind IN ('r','p') AND n.nspname <> ALL(%s) AND n.nspname NOT LIKE 'pg_temp%%' "
            "AND n.nspname NOT LIKE 'pg_toast_temp%%' ORDER BY 1, 2",
            (list(SYSTEM_SCHEMAS),),
        ).fetchall()
        per_table: dict[str, list[Any]] = {}
        for schema, name in tables:
            count, digest = conn.execute(
                sql.SQL(
                    "SELECT count(*), encode(sha256(convert_to(coalesce(string_agg(t::text, E'\\n' "
                    "ORDER BY t::text), ''), 'UTF8')), 'hex') FROM {}.{} t"
                ).format(sql.Identifier(schema), sql.Identifier(name))
            ).fetchone()
            per_table[f"{schema}.{name}"] = [count, digest]
        sequences = {
            f"{s}.{n}": v
            for s, n, v in conn.execute(
                "SELECT schemaname, sequencename, last_value FROM pg_sequences ORDER BY 1, 2"
            ).fetchall()
        }
        alembic = None
        if "public.alembic_version" in per_table:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            alembic = row[0] if row else None
        conn.rollback()
    body = {"tables": per_table, "sequences": sequences, "alembic_version": alembic}
    return {
        "digest": hashlib.sha256(_canonical(body)).hexdigest(),
        "table_count": len(per_table),
        "row_total": sum(v[0] for v in per_table.values()),
        "alembic_version": alembic,
        "server_version": version,
        "taken_utc": taken.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "wal_lsn_informational": lsn,
        "tables": per_table,
        "sequences": sequences,
    }


def uploads_manifest(directory: Path) -> dict[str, Any]:
    root = directory.absolute()
    st = root.lstat()
    if not stat.S_ISDIR(st.st_mode):
        raise ValueError("uploads path is not a directory")
    entries: list[dict[str, Any]] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        for name in sorted(dirs):
            child = Path(current) / name
            if stat.S_ISLNK(child.lstat().st_mode):
                raise ValueError("uploads tree contains a symlink")
        for name in sorted(files):
            path = Path(current) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("uploads tree contains a non-regular file")
            entries.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "size_bytes": info.st_size,
                    "sha256": sha256_file(path),
                }
            )
    entries.sort(key=lambda e: e["relative_path"])
    return {
        "digest": hashlib.sha256(_canonical(entries)).hexdigest(),
        "file_count": len(entries),
        "total_bytes": sum(e["size_bytes"] for e in entries),
        "taken_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "entries": entries,
    }


def diff_fingerprints(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Human-readable differences between two database fingerprints (names only)."""
    problems: list[str] = []
    for key in sorted(set(a["tables"]) | set(b["tables"])):
        if a["tables"].get(key) != b["tables"].get(key):
            problems.append(f"table {key} differs")
    for key in sorted(set(a["sequences"]) | set(b["sequences"])):
        if a["sequences"].get(key) != b["sequences"].get(key):
            problems.append(f"sequence {key} differs")
    if a["alembic_version"] != b["alembic_version"]:
        problems.append("alembic revision differs")
    return problems


def diff_manifests(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Differences between two uploads manifests (relative paths only)."""
    left = {e["relative_path"]: e for e in a["entries"]}
    right = {e["relative_path"]: e for e in b["entries"]}
    problems = [f"{p}: missing at second capture" for p in sorted(left.keys() - right.keys())]
    problems += [f"{p}: new at second capture" for p in sorted(right.keys() - left.keys())]
    problems += [f"{p}: content differs" for p in sorted(left.keys() & right.keys()) if left[p] != right[p]]
    return problems
