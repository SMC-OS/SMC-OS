"""Reversible staging writer barrier for the A1 matched recovery point.

Two independent layers, neither of which needs an application deploy:

* DATABASE layer: ``ALTER DATABASE ... SET default_transaction_read_only = on``.
  Every session that connects afterwards, under ANY role (API, background jobs,
  psql, operator tools), starts read-only.  Sessions that were already open
  keep the old default, so they are drained first: idle ones are terminated
  (nothing to lose), in-flight ones are allowed to finish.  Nothing is
  written to any application table, and the setting is not part of a
  ``pg_dump`` of the database.
* UPLOADS layer: the write bits are removed from the uploads directory tree
  (state recorded outside the tree first).  This must be run as the user that
  owns the files (UID 10001 on Railway); root bypasses permissions.  It stops
  both new files and modification of existing files.

Honest limits (also in docs): ``default_transaction_read_only`` is a default,
not a lock.  A session that deliberately issues ``SET ... = off`` can still
write, and PostgreSQL does not let an administrator prevent that for a
superuser or for the role's owner.  The application never does so (see the
rehearsal).  The barrier is therefore paired with *detection*: ``watch``
checks the setting, session ages and the user-table write counters
continuously, and A1 compares complete content fingerprints at T0 and T1.

Secrets: DSNs are read only from the environment (``BARRIER_ADMIN_DSN``,
``BARRIER_APP_DSN``) and are never printed.  The record file must live
outside the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ADMIN_DSN_ENV = "BARRIER_ADMIN_DSN"
APP_DSN_ENV = "BARRIER_APP_DSN"
ADMIN_APP_NAME = "geocore_barrier_admin"
PROBE_APP_NAME = "geocore_barrier_probe"
SETTING = "default_transaction_read_only"

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_DRAIN_TIMEOUT = 3
EXIT_VIOLATION = 4
EXIT_PROBE_FAILED = 5


class BarrierError(RuntimeError):
    """A fail-closed refusal. ``code`` becomes the process exit status."""

    def __init__(self, message: str, code: int = EXIT_REFUSED, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# --------------------------------------------------------------------------- #
# Record file (outside the repository, owner-only, atomic)
# --------------------------------------------------------------------------- #
@dataclass
class Record:
    path: Path
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def open(cls, path: Path) -> "Record":
        path = path.expanduser().absolute()
        try:
            path.relative_to(REPOSITORY_ROOT)
        except ValueError:
            pass
        else:
            raise BarrierError("record file must be outside the repository")
        if not path.parent.is_dir():
            raise BarrierError("record directory does not exist")
        data: dict[str, Any] = {"events": []}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, data)

    def event(self, name: str, **fields: Any) -> None:
        self.data.setdefault("events", []).append({"at": utcnow(), "event": name, **fields})
        self.save()

    def set(self, **fields: Any) -> None:
        self.data.update(fields)
        self.save()

    def save(self) -> None:
        tmp = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, sort_keys=True, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)


# --------------------------------------------------------------------------- #
# Database layer
# --------------------------------------------------------------------------- #
def _psycopg():
    import psycopg  # imported lazily so the file-layer tests need no driver

    return psycopg


def _dsn(env_name: str) -> str:
    value = os.environ.get(env_name)
    if not value:
        raise BarrierError(f"{env_name} is not set")
    return value


def admin_connect(dsn: str | None = None):
    """Admin session. Explicitly read-write so it can lift the barrier again."""
    psycopg = _psycopg()
    return psycopg.connect(
        dsn or _dsn(ADMIN_DSN_ENV),
        autocommit=True,
        options=f"-c {SETTING}=off",
        application_name=ADMIN_APP_NAME,
    )


def app_connect(dsn: str | None = None):
    """Connection exactly as the application would open it: no overrides."""
    psycopg = _psycopg()
    return psycopg.connect(dsn or _dsn(APP_DSN_ENV), autocommit=True, application_name=PROBE_APP_NAME)


def identity(conn) -> dict[str, Any]:
    database, version, in_recovery = conn.execute(
        "SELECT current_database(), current_setting('server_version'), pg_is_in_recovery()"
    ).fetchone()
    try:
        system_identifier = conn.execute("SELECT system_identifier::text FROM pg_control_system()").fetchone()[0]
    except Exception:  # not permitted for this role
        system_identifier = None
    superuser = conn.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]
    return {
        "database": database,
        "server_version": version,
        "in_recovery": in_recovery,
        "system_identifier": system_identifier,
        "admin_is_superuser": superuser,
    }


def barrier_state(conn, database: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT s.setconfig FROM pg_db_role_setting s JOIN pg_database d ON d.oid = s.setdatabase "
        "WHERE d.datname = %s AND s.setrole = 0",
        (database,),
    ).fetchone()
    value = None
    for item in (row[0] if row and row[0] else []):
        key, _, val = item.partition("=")
        if key == SETTING:
            value = val
    return {"setting": value, "engaged": value in ("on", "true")}


def list_sessions(conn, database: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT pid, usename, application_name, state, backend_start FROM pg_stat_activity "
        "WHERE datname = %s AND backend_type = 'client backend' AND pid <> pg_backend_pid() "
        "AND application_name <> %s",
        (database, ADMIN_APP_NAME),
    ).fetchall()
    return [
        {"pid": r[0], "user": r[1], "application": r[2], "state": r[3], "backend_start": r[4]} for r in rows
    ]


def _server_now(conn):
    return conn.execute("SELECT clock_timestamp()").fetchone()[0]


def drain(
    conn,
    database: str,
    cutoff,
    *,
    timeout_s: float,
    poll_s: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Remove every session that predates the barrier, never an in-flight write.

    Idle sessions are terminated (safe: no open transaction).  Sessions that are
    active or idle-in-transaction are waited for.  Timeout => BarrierError and
    the barrier stays engaged (fail closed): the caller decides.
    """
    deadline = clock() + timeout_s
    terminated = 0
    waited: set[int] = set()
    while True:
        stale = [s for s in list_sessions(conn, database) if s["backend_start"] < cutoff]
        if not stale:
            return {"terminated_idle": terminated, "inflight_waited_for": len(waited)}
        for session in stale:
            if session["state"] == "idle":
                conn.execute("SELECT pg_terminate_backend(%s)", (session["pid"],))
                terminated += 1
            else:
                waited.add(session["pid"])
        if clock() >= deadline:
            raise BarrierError(
                "DRAIN_TIMEOUT: in-flight sessions did not finish; barrier left engaged",
                EXIT_DRAIN_TIMEOUT,
                [{"pid": s["pid"], "state": s["state"], "application": s["application"]} for s in stale],
            )
        sleep(poll_s)


def engage(
    conn,
    *,
    record: Record,
    expect_system_identifier: str | None,
    confirm_environment: str,
    drain_timeout_s: float,
    **drain_kwargs: Any,
) -> dict[str, Any]:
    if confirm_environment not in ("staging", "local"):
        raise BarrierError("--confirm-environment must be 'staging' or 'local'")
    ident = identity(conn)
    database = ident["database"]
    if ident["in_recovery"]:
        raise BarrierError("target is a replica in recovery")
    if expect_system_identifier is None or ident["system_identifier"] != expect_system_identifier:
        raise BarrierError("cluster system identifier does not match --expect-system-identifier")
    state = barrier_state(conn, database)
    if state["setting"] is not None:
        raise BarrierError("database already has a default_transaction_read_only setting; refusing to guess its owner")
    record.set(
        environment=confirm_environment,
        database=database,
        system_identifier=ident["system_identifier"],
        server_version=ident["server_version"],
        admin_is_superuser=ident["admin_is_superuser"],
        prior_setting=None,
        status="engaging",
    )
    conn.execute(f'ALTER DATABASE "{database}" SET {SETTING} = on')
    cutoff = _server_now(conn)
    record.set(cutoff=cutoff.isoformat(), status="engaged-draining")
    try:
        result = drain(conn, database, cutoff, timeout_s=drain_timeout_s, **drain_kwargs)
    except BarrierError as exc:
        record.event("drain-timeout", detail=exc.detail)
        record.set(status="engaged-undrained")
        raise
    record.event("drained", **result)
    record.set(status="engaged")
    return {"database": database, "cutoff": cutoff.isoformat(), **result}


def release(
    conn,
    *,
    record: Record | None,
    grace_s: float = 10.0,
    emergency: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Lift the barrier and evict sessions that were opened read-only under it.

    Those sessions would otherwise keep their read-only default after the
    setting is removed (found in rehearsal).  They never held a write, so
    terminating them cannot lose data.
    """
    ident = identity(conn)
    database = ident["database"]
    if record is not None and not emergency:
        if record.data.get("database") not in (None, database):
            raise BarrierError("record belongs to a different database")
        if record.data.get("system_identifier") not in (None, ident["system_identifier"]):
            raise BarrierError("record belongs to a different cluster")
    state = barrier_state(conn, database)
    if not state["engaged"] and state["setting"] is None:
        if record is not None:
            record.event("release-noop")
        return {"database": database, "already_released": True}
    prior = record.data.get("prior_setting") if record is not None else None
    if prior is None:
        conn.execute(f'ALTER DATABASE "{database}" RESET {SETTING}')
    else:
        conn.execute(f'ALTER DATABASE "{database}" SET {SETTING} = {prior}')
    cutoff = _server_now(conn)
    deadline = time.monotonic() + grace_s
    terminated = 0
    while True:
        stale = [s for s in list_sessions(conn, database) if s["backend_start"] < cutoff]
        if not stale:
            break
        force = time.monotonic() >= deadline
        for session in stale:
            if session["state"] == "idle" or force:  # read-only sessions: nothing to lose
                conn.execute("SELECT pg_terminate_backend(%s)", (session["pid"],))
                terminated += 1
        sleep(0.2)
    after = barrier_state(conn, database)
    if after["setting"] is not None and prior is None:
        raise BarrierError("release did not remove the setting", EXIT_VIOLATION)
    if record is not None:
        record.event("released", evicted_read_only_sessions=terminated, emergency=emergency)
        record.set(status="released")
    return {"database": database, "evicted_read_only_sessions": terminated, "released": True}


def write_counters(conn) -> dict[str, int]:
    conn.execute("SELECT pg_stat_clear_snapshot()")
    ins, upd, dele = conn.execute(
        "SELECT coalesce(sum(n_tup_ins),0)::bigint, coalesce(sum(n_tup_upd),0)::bigint, "
        "coalesce(sum(n_tup_del),0)::bigint FROM pg_stat_user_tables"
    ).fetchone()
    return {"inserted": int(ins), "updated": int(upd), "deleted": int(dele)}


def sample(conn, database: str, cutoff) -> dict[str, Any]:
    stale = [s for s in list_sessions(conn, database) if cutoff is not None and s["backend_start"] < cutoff]
    return {
        "at": utcnow(),
        "barrier": barrier_state(conn, database),
        "stale_sessions": [{"pid": s["pid"], "state": s["state"]} for s in stale],
        "counters": write_counters(conn),
        "wal_lsn": conn.execute("SELECT pg_current_wal_lsn()::text").fetchone()[0],
    }


def violations(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Pure comparison used by `watch` and by the A1 capture checkpoints."""
    found: list[str] = []
    if not current["barrier"]["engaged"]:
        found.append("barrier setting is no longer engaged")
    if current["stale_sessions"]:
        found.append("a session that predates the barrier is still connected")
    for key in ("inserted", "updated", "deleted"):
        if current["counters"][key] != baseline["counters"][key]:
            found.append(f"user-table {key} counter changed")
    return found


def probe(app_conn, *, table: str, real_write_table: str | None = None) -> dict[str, Any]:
    """Attempt writes exactly as the application's role would.

    On staging only no-op writes are used (``WHERE false``): PostgreSQL rejects
    them at command start in a read-only transaction, so the probe proves the
    barrier without being able to change data if the barrier were absent.  A
    real INSERT is allowed only against a disposable rehearsal database.
    """
    psycopg = _psycopg()
    from psycopg import sql

    results: dict[str, Any] = {}
    results["session_read_only"] = app_conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
    try:
        app_conn.execute(sql.SQL("DELETE FROM {} WHERE false").format(sql.Identifier(table)))
        results["noop_write_rejected"] = False
    except psycopg.errors.ReadOnlySqlTransaction:
        results["noop_write_rejected"] = True
    try:
        app_conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()
        results["read_works"] = True
    except Exception:
        results["read_works"] = False
    if real_write_table:
        try:
            app_conn.execute(sql.SQL("INSERT INTO {} DEFAULT VALUES").format(sql.Identifier(real_write_table)))
            results["real_write_rejected"] = False
        except psycopg.errors.ReadOnlySqlTransaction:
            results["real_write_rejected"] = True
    results["ok"] = all(results.values())
    return results


# --------------------------------------------------------------------------- #
# Uploads layer (run as the file owner, inside the API container)
# --------------------------------------------------------------------------- #
def _walk(directory: Path) -> list[dict[str, Any]]:
    root = directory.absolute()
    entries: list[dict[str, Any]] = []
    root_stat = root.lstat()
    if not stat.S_ISDIR(root_stat.st_mode):
        raise BarrierError("uploads path is not a directory")
    entries.append({"p": ".", "t": "d", "m": stat.S_IMODE(root_stat.st_mode), "s": 0, "mt": root_stat.st_mtime_ns})
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs) + sorted(files):
            path = Path(current) / name
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                raise BarrierError("uploads tree contains a symlink or special file; refusing")
            entries.append(
                {
                    "p": path.relative_to(root).as_posix(),
                    "t": "d" if stat.S_ISDIR(st.st_mode) else "f",
                    "m": stat.S_IMODE(st.st_mode),
                    "s": 0 if stat.S_ISDIR(st.st_mode) else st.st_size,
                    "mt": st.st_mtime_ns,
                }
            )
    return entries


def _outside(directory: Path, state_path: Path) -> None:
    d = directory.resolve()
    s = state_path.expanduser().absolute().resolve()
    try:
        s.relative_to(d)
    except ValueError:
        pass
    else:
        raise BarrierError("state file must be outside the uploads directory")
    try:
        s.relative_to(REPOSITORY_ROOT)
    except ValueError:
        return
    raise BarrierError("state file must be outside the repository")


def uploads_freeze(directory: Path, state_path: Path) -> dict[str, Any]:
    directory = directory.absolute()
    _outside(directory, state_path)
    if state_path.exists():
        raise BarrierError("uploads state file already exists; thaw first")
    entries = _walk(directory)
    payload = {"directory": str(directory), "created_utc": utcnow(), "euid": os.geteuid(), "entries": entries}
    fd = os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    # files first, then directories deepest-first, root last
    ordered = sorted(entries, key=lambda e: (e["t"] == "d", -e["p"].count("/") if e["p"] != "." else 1))
    for entry in ordered:
        target = directory if entry["p"] == "." else directory / entry["p"]
        os.chmod(target, entry["m"] & ~0o222)
    for entry in entries:
        target = directory if entry["p"] == "." else directory / entry["p"]
        if stat.S_IMODE(target.lstat().st_mode) & 0o222:
            raise BarrierError("a write bit remained after freeze", EXIT_VIOLATION)
    return {"frozen_entries": len(entries), "euid": os.geteuid()}


def uploads_probe(directory: Path) -> dict[str, Any]:
    """Attempt an actual new-file write and an actual write-open of an existing file."""
    directory = directory.absolute()
    results: dict[str, Any] = {"euid": os.geteuid()}
    if os.geteuid() == 0:
        raise BarrierError("run the probe as the application user, not root (root bypasses permissions)")
    probe_path = directory / f".barrier-probe-{uuid.uuid4().hex}"
    try:
        with open(probe_path, "xb"):
            pass
        probe_path.unlink()
        results["new_file_rejected"] = False
    except PermissionError:
        results["new_file_rejected"] = True
    existing = next((p for p in sorted(directory.rglob("*")) if p.is_file()), None)
    if existing is None:
        results["existing_file_write_rejected"] = None
    else:
        before = existing.stat()
        try:
            with open(existing, "r+b"):
                pass
            results["existing_file_write_rejected"] = False
        except PermissionError:
            results["existing_file_write_rejected"] = True
        after = existing.stat()
        results["existing_file_unchanged"] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    try:
        with open(existing, "rb") if existing else open(os.devnull, "rb") as handle:
            handle.read(1)
        results["read_works"] = True
    except OSError:
        results["read_works"] = False
    results["ok"] = all(v is not False for v in results.values())
    return results


def uploads_thaw(directory: Path, state_path: Path, *, emergency: bool = False) -> dict[str, Any]:
    directory = directory.absolute()
    if emergency:
        restored = 0
        for current, dirs, files in os.walk(directory, followlinks=False):
            for name in [""] + dirs + files:
                path = Path(current) / name if name else Path(current)
                st = path.lstat()
                if stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid():
                    continue
                os.chmod(path, stat.S_IMODE(st.st_mode) | 0o200)
                restored += 1
        return {"emergency": True, "owner_write_bit_restored": restored}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if Path(state["directory"]) != directory:
        raise BarrierError("state file belongs to a different directory")
    for entry in state["entries"]:
        target = directory if entry["p"] == "." else directory / entry["p"]
        os.chmod(target, entry["m"])
    drift: list[str] = []
    for entry in state["entries"]:
        target = directory if entry["p"] == "." else directory / entry["p"]
        st = target.lstat()
        if stat.S_IMODE(st.st_mode) != entry["m"]:
            drift.append(f"{entry['p']}: mode")
        if entry["t"] == "f" and (st.st_size != entry["s"] or st.st_mtime_ns != entry["mt"]):
            drift.append(f"{entry['p']}: content metadata")
        if entry["t"] == "d" and st.st_mtime_ns != entry["mt"]:
            drift.append(f"{entry['p']}: directory changed")
    current = {e["p"] for e in _walk(directory)}
    recorded = {e["p"] for e in state["entries"]}
    drift += [f"{p}: appeared while frozen" for p in sorted(current - recorded)]
    drift += [f"{p}: disappeared while frozen" for p in sorted(recorded - current)]
    return {"restored_entries": len(state["entries"]), "drift": drift, "no_drift": not drift}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def with_record(p):
        p.add_argument("--record", type=Path, required=True, help="private JSON record, outside the repository")

    p = sub.add_parser("db-engage")
    with_record(p)
    p.add_argument("--confirm-environment", required=True)
    p.add_argument("--expect-system-identifier", required=True)
    p.add_argument("--drain-timeout", type=float, default=60.0)
    p = sub.add_parser("db-status")
    p.add_argument("--record", type=Path)
    p = sub.add_parser("db-probe")
    p.add_argument("--table", default="alembic_version")
    p.add_argument("--real-write-table", help="rehearsal only; refused unless --confirm-environment local")
    p.add_argument("--confirm-environment", default="staging")
    p = sub.add_parser("db-watch")
    with_record(p)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--duration", type=float, required=True)
    p = sub.add_parser("db-release")
    with_record(p)
    p.add_argument("--grace", type=float, default=10.0)
    p.add_argument("--emergency", action="store_true")
    for name in ("uploads-freeze", "uploads-probe", "uploads-thaw"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=Path, required=True)
        if name != "uploads-probe":
            p.add_argument("--state", type=Path, required=True)
        if name == "uploads-thaw":
            p.add_argument("--emergency", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cmd = args.command
        if cmd == "db-engage":
            with admin_connect() as conn:
                _print(
                    engage(
                        conn,
                        record=Record.open(args.record),
                        expect_system_identifier=args.expect_system_identifier,
                        confirm_environment=args.confirm_environment,
                        drain_timeout_s=args.drain_timeout,
                    )
                )
        elif cmd == "db-status":
            with admin_connect() as conn:
                ident = identity(conn)
                cutoff = None
                if args.record:
                    raw = Record.open(args.record).data.get("cutoff")
                    cutoff = datetime.fromisoformat(raw) if raw else None
                _print({"identity": ident, **sample(conn, ident["database"], cutoff)})
        elif cmd == "db-probe":
            if args.real_write_table and args.confirm_environment != "local":
                raise BarrierError("real-write probe is refused outside a local rehearsal")
            with app_connect() as conn:
                result = probe(conn, table=args.table, real_write_table=args.real_write_table)
            _print(result)
            return EXIT_OK if result["ok"] else EXIT_PROBE_FAILED
        elif cmd == "db-watch":
            record = Record.open(args.record)
            with admin_connect() as conn:
                database = identity(conn)["database"]
                cutoff = datetime.fromisoformat(record.data["cutoff"])
                time.sleep(1.5)  # let cumulative statistics settle before the baseline
                baseline = sample(conn, database, cutoff)
                end = time.monotonic() + args.duration
                count = 0
                while time.monotonic() < end:
                    time.sleep(args.interval)
                    current = sample(conn, database, cutoff)
                    count += 1
                    found = violations(baseline, current)
                    if found:
                        record.event("VIOLATION", problems=found, sample=current)
                        _print({"violation": found})
                        return EXIT_VIOLATION
                record.event("watch-clean", samples=count, seconds=args.duration)
                _print({"watch": "clean", "samples": count})
        elif cmd == "db-release":
            with admin_connect() as conn:
                _print(release(conn, record=Record.open(args.record), grace_s=args.grace, emergency=args.emergency))
        elif cmd == "uploads-freeze":
            _print(uploads_freeze(args.dir, args.state))
        elif cmd == "uploads-probe":
            result = uploads_probe(args.dir)
            _print(result)
            return EXIT_OK if result["ok"] else EXIT_PROBE_FAILED
        elif cmd == "uploads-thaw":
            result = uploads_thaw(args.dir, args.state, emergency=args.emergency)
            _print(result)
            return EXIT_OK if result.get("no_drift", True) else EXIT_VIOLATION
    except BarrierError as exc:
        print(json.dumps({"refused": str(exc), "detail": exc.detail}, default=str), file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
