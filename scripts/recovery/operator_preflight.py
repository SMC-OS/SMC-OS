"""Read-only operator preflight for the A1 staging window (run this BEFORE the window).

It changes nothing on staging: no barrier, no write, no restart.  It only reads
(`SELECT`s over the private tunnel, `id`/`stat`/`tar` inside the API container) and writes one
report file into a private directory outside the repository.  The window itself stays
UNAPPROVED until `validate_approval` accepts the owner's approval file.

Checks, each PASS / FAIL / WARN / INFO / UNVERIFIED (overall BLOCKED if any FAIL, and PITR is
never reported verified without pgBackRest evidence):

  workstation  WSL2, Python and psycopg, tool versions, `pg_dump` major >= server major (PG18),
               private output directory (ext4 not /mnt/c, no cloud-sync folder, 0700/0400 honoured,
               encryption attested), free disk
  container    UID is not root, uploads directory owned by that UID, nothing writable yet,
               file count/bytes, mount type, timed read-only transfer and extrapolation
  database     identity (the system identifier to put in the approval), version, roles, settings
               that could defeat the barrier, existing barrier settings, quiet probe, tunnel latency
  recovery     archiver state and decision rule, pgBackRest JSON continuity if supplied
  approval     owner approval file validity (never inferred)

Secrets: DSNs come from BARRIER_ADMIN_DSN / BARRIER_APP_DSN and are never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approval  # noqa: E402
import writer_barrier as wb  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXIT_OK, EXIT_BLOCKED, EXIT_REFUSED = 0, 8, 2
GIB = 1024**3
BAD_FILESYSTEMS = {"9p", "drvfs", "cifs", "smbfs", "vboxsf", "fuseblk", "ntfs", "ntfs3", "exfat", "vfat", "msdos"}
SYNC_FOLDERS = re.compile(r"onedrive|dropbox|google ?drive|icloud|box sync|sharepoint", re.I)


class Report:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, area: str, name: str, status: str, detail: Any = None) -> str:
        self.items.append({"area": area, "check": name, "status": status, "detail": detail})
        return status

    @property
    def blocked(self) -> bool:
        return any(i["status"] == "FAIL" for i in self.items)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i["status"] == status)


# ----------------------------------------------------------------------- pure helpers
def parse_major(text: str) -> int | None:
    m = re.search(r"(\d+)(?:\.\d+)*", text)
    return int(m.group(1)) if m else None


def tool_major(binary: str) -> tuple[int | None, str]:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None, "not found"
    text = (out.stdout or out.stderr).strip()
    return parse_major(text.split(")", 1)[-1]), text.splitlines()[0][:80] if text else ""


def wsl_kind(version_text: str) -> str:
    low = version_text.lower()
    if "microsoft" not in low and "wsl" not in low:
        return "not-wsl"
    return "wsl2" if "wsl2" in low or "microsoft-standard" in low else "wsl1"


def filesystem_for(path: Path, mounts_text: str) -> str | None:
    best, fstype = -1, None
    target = str(path.resolve())
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount = parts[1].replace("\\040", " ")
        if (target == mount or target.startswith(mount.rstrip("/") + "/")) and len(mount) > best:
            best, fstype = len(mount), parts[2]
    return fstype


def check_storage_path(path: Path, mounts_text: str) -> list[tuple[str, str]]:
    problems = []
    fstype = filesystem_for(path, mounts_text)
    if fstype is None:
        problems.append(("UNVERIFIED", "filesystem type could not be determined"))
    elif fstype in BAD_FILESYSTEMS or fstype.startswith("fuse"):
        problems.append(("FAIL", f"filesystem '{fstype}' does not honour POSIX permission bits (use ext4 inside WSL2, not /mnt/c)"))
    if re.match(r"^/mnt/[a-z]/", str(path.resolve())):
        problems.append(("FAIL", "path is on a Windows drive (/mnt/<drive>)"))
    if SYNC_FOLDERS.search(str(path.resolve())):
        problems.append(("FAIL", "path is inside a cloud-synced folder; recovery data must not be replicated"))
    return problems


def estimate_transfer(bytes_read: int, seconds: float, total_bytes: int, budget_s: float) -> dict[str, Any]:
    if seconds <= 0 or bytes_read <= 0:
        return {"status": "FAIL", "reason": "no data was transferred"}
    rate = bytes_read / seconds
    estimate = total_bytes / rate
    status = "FAIL" if estimate > budget_s else "WARN" if estimate > budget_s / 2 else "PASS"
    return {"status": status, "bytes_per_second": int(rate), "estimated_seconds_for_all": round(estimate, 1),
            "budget_seconds": budget_s}


def evaluate_archiver(row: dict[str, Any], *, now: datetime, max_lag_s: float, failures_explained: str | None) -> dict[str, Any]:
    reasons, status = [], "PASS"
    last = row.get("last_archived_time")
    if row.get("last_archived_wal") is None or last is None:
        return {"status": "FAIL", "reasons": ["nothing has ever been archived"]}
    lag = (now - last).total_seconds()
    if lag > max_lag_s:
        status = "FAIL"
        reasons.append(f"archive lag {int(lag)} s exceeds {int(max_lag_s)} s")
    failed = row.get("failed_count") or 0
    if failed:
        past = (row.get("last_failed_wal") or "") < row["last_archived_wal"] and (row.get("last_failed_time") or last) < last
        if not past:
            status = "FAIL"
            reasons.append("the last archive attempt failed and nothing has been archived since")
        elif not failures_explained:
            status = "WARN" if status == "PASS" else status
            reasons.append(f"{failed} historic failure(s) are archived past but UNEXPLAINED (no log evidence supplied)")
    return {"status": status, "reasons": reasons, "archive_lag_seconds": int(lag), "failed_count": failed}


def evaluate_pgbackrest(info: Any, *, archiver_last_wal: str | None = None) -> dict[str, Any]:
    """Interpret `pgbackrest info --output=json` (documented shape; verify against the real output)."""
    stanzas = info if isinstance(info, list) else [info]
    if not stanzas:
        return {"status": "FAIL", "reasons": ["no stanza reported"]}
    reasons, status = [], "PASS"
    for st in stanzas:
        if (st.get("status") or {}).get("code") != 0:
            return {"status": "FAIL", "reasons": [f"stanza status: {(st.get('status') or {}).get('message', 'unknown')}"]}
        backups = [b for b in st.get("backup", []) if not b.get("error")]
        if not backups:
            return {"status": "FAIL", "reasons": ["no completed base backup"]}
        latest = max(backups, key=lambda b: (b.get("timestamp") or {}).get("stop", 0))
        archives = st.get("archive") or []
        if not archives:
            return {"status": "FAIL", "reasons": ["no archive range reported"]}
        lo, hi = min(a["min"] for a in archives), max(a["max"] for a in archives)
        a0, a1 = (latest.get("archive") or {}).get("start"), (latest.get("archive") or {}).get("stop")
        if not (a0 and a1 and lo <= a0 and a1 <= hi):
            status = "FAIL"
            reasons.append("the latest base backup's WAL range is not covered by the archive (gap)")
        if archiver_last_wal and archiver_last_wal > hi:
            status = "WARN" if status == "PASS" else status
            reasons.append("PostgreSQL has archived newer WAL than pgBackRest reports (stale view or lag)")
        reasons.append(f"latest base backup {latest.get('label')} type {latest.get('type')}")
    return {"status": status, "reasons": reasons}


# --------------------------------------------------------------------------- checks
def check_workstation(rep: Report, args: argparse.Namespace, server_major: int | None) -> None:
    version_text = Path("/proc/version").read_text() if Path("/proc/version").exists() else ""
    kind = wsl_kind(version_text)
    need = args.require_wsl2
    rep.add("workstation", "WSL2", "PASS" if kind == "wsl2" else ("FAIL" if need else "INFO"),
            f"{kind}" + ("" if kind == "wsl2" else " (acceptable for a local rehearsal; the Windows operator must use WSL2)"))
    rep.add("workstation", "python >= 3.10", "PASS" if sys.version_info >= (3, 10) else "FAIL", sys.version.split()[0])
    try:
        import psycopg  # noqa: F401

        rep.add("workstation", "psycopg importable", "PASS", psycopg.__version__)
    except ImportError:
        rep.add("workstation", "psycopg importable", "FAIL", "pip install 'psycopg[binary]'")
    for tool in ("sha256sum", "tar"):
        rep.add("workstation", f"{tool} present", "PASS" if shutil.which(tool) else "FAIL")
    rw = shutil.which("railway")
    rep.add("workstation", "railway CLI present", "PASS" if rw else ("FAIL" if args.require_railway else "WARN"),
            "found" if rw else "not found: needed for the tunnel and `railway ssh`")
    dump_major, dump_text = tool_major(args.pg_dump)
    restore_major, restore_text = tool_major(args.pg_restore)
    psql_major, psql_text = tool_major(args.psql)
    rep.add("workstation", "pg_dump version", "PASS" if dump_major else "FAIL", dump_text)
    rep.add("workstation", "pg_restore version", "PASS" if restore_major else "FAIL", restore_text)
    rep.add("workstation", "psql version", "PASS" if psql_major else "WARN", psql_text)
    want = server_major or args.server_major
    if want is None:
        rep.add("workstation", "pg_dump >= server major", "UNVERIFIED", "server major unknown: pass --server-major or connect")
    elif dump_major is None:
        rep.add("workstation", "pg_dump >= server major", "FAIL", "pg_dump unusable")
    else:
        ok = dump_major >= want and (restore_major or 0) >= want
        rep.add("workstation", "pg_dump and pg_restore >= server major", "PASS" if ok else "FAIL",
                f"server {want}, pg_dump {dump_major}, pg_restore {restore_major}"
                + ("" if ok else ": pg_dump refuses to dump a newer server; install the matching client in WSL2"))


def check_storage(rep: Report, args: argparse.Namespace, db_bytes: int | None, uploads_bytes: int | None) -> None:
    out = args.out_dir.expanduser().absolute()
    if not out.is_dir():
        rep.add("storage", "output directory exists", "FAIL", "create it first")
        return
    try:
        out.resolve().relative_to(REPOSITORY_ROOT)
        rep.add("storage", "outside the repository", "FAIL", "inside the repository")
    except ValueError:
        rep.add("storage", "outside the repository", "PASS")
    mounts = Path("/proc/mounts").read_text() if Path("/proc/mounts").exists() else ""
    for status, why in check_storage_path(out, mounts) or [("PASS", f"filesystem {filesystem_for(out, mounts)}")]:
        rep.add("storage", "suitable filesystem and location", status, why)
    probe = out / f".preflight-{os.getpid()}"
    try:
        probe.mkdir(mode=0o700)
        f = probe / "f"
        f.write_bytes(b"x")
        os.chmod(f, 0o400)
        honoured = (probe.stat().st_mode & 0o777) == 0o700 and (f.stat().st_mode & 0o777) == 0o400
        rep.add("storage", "0700 directories and 0400 files are honoured", "PASS" if honoured else "FAIL")
    except OSError as exc:
        rep.add("storage", "0700 directories and 0400 files are honoured", "FAIL", type(exc).__name__)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    rep.add("storage", "encrypted volume attested by the operator", "PASS" if args.attest_encrypted_volume else "FAIL",
            "attestation only: encryption cannot be detected from here" if args.attest_encrypted_volume else "pass --attest-encrypted-volume once true")
    free = shutil.disk_usage(out).free
    if db_bytes is None or uploads_bytes is None:
        rep.add("storage", "free disk", "UNVERIFIED", {"free_bytes": free, "note": "sizes unknown: connect to the database and container"})
    else:
        need = max(int(args.min_free_multiple * (db_bytes + uploads_bytes)), 3 * GIB)
        rep.add("storage", "free disk >= max(3 x data, 3 GiB)", "PASS" if free >= need else "FAIL",
                {"free_bytes": free, "required_bytes": need, "database_bytes": db_bytes, "uploads_bytes": uploads_bytes})


def check_container(rep: Report, args: argparse.Namespace) -> int | None:
    from a1_capture import Remote

    remote = Remote(args.remote_prefix.split() if args.remote_prefix else [], args.remote_python)
    uid = remote.run(["id", "-u"])
    if uid.returncode != 0:
        rep.add("container", "reachable", "FAIL", "the remote command failed")
        return None
    uid_n = int(uid.stdout.decode().strip())
    rep.add("container", "runs as a non-root user", "FAIL" if uid_n == 0 else "PASS",
            f"uid {uid_n}" + (" (root bypasses permission-based freezing)" if uid_n == 0 else "") + ("" if uid_n == 10001 else " (runbook expects 10001)"))
    ver = remote.run([args.remote_python, "--version"])
    rep.add("container", "python available", "PASS" if ver.returncode == 0 else "FAIL", (ver.stdout or ver.stderr).decode().strip())
    st = remote.run(["stat", "-c", "%u %a", args.uploads_dir])
    if st.returncode != 0:
        rep.add("container", "uploads directory", "FAIL", "not found")
        return None
    owner, mode = st.stdout.decode().split()
    rep.add("container", "uploads directory owned by the running user", "PASS" if int(owner) == uid_n else "FAIL", f"owner {owner}, mode {mode}")
    tmp = remote.run(["sh", "-c", "test -w /tmp && echo yes"])
    rep.add("container", "/tmp writable for the freeze state file", "PASS" if tmp.stdout.decode().strip() == "yes" else "FAIL",
            "the state file must also be copied off the container before the freeze is relied on")
    mounts = remote.run(["cat", "/proc/mounts"]).stdout.decode()
    rep.add("container", "uploads mount", "INFO", filesystem_for(Path(args.uploads_dir), mounts))
    free = remote.script("writable-count", args.uploads_dir)
    rep.add("container", "uploads writable entries (0 only once frozen)", "INFO", free)
    man = remote.script("uploads-manifest", args.uploads_dir)
    rep.add("container", "uploads inventory (read-only)", "INFO", {"files": man["file_count"], "bytes": man["total_bytes"], "digest": man["digest"][:16]})
    rep.add("container", "uploads fit the tool limit (10,000 entries)", "PASS" if man["file_count"] < 10000 else "FAIL", man["file_count"])
    if args.timing_seconds > 0:
        proc = subprocess.Popen(remote.prefix + ["tar", "-C", args.uploads_dir, "-cf", "-", "."], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        digest, read, started = hashlib.sha256(), 0, time.monotonic()
        while time.monotonic() - started < args.timing_seconds:
            chunk = proc.stdout.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
            read += len(chunk)
        elapsed = time.monotonic() - started
        finished = proc.poll() is not None or not proc.stdout.read(1)
        proc.kill()
        proc.wait()
        est = estimate_transfer(read, elapsed, man["total_bytes"] if not finished else read, args.transfer_budget_seconds)
        est["sampled_bytes"], est["sampled_seconds"], est["whole_tree_read"] = read, round(elapsed, 2), finished
        rep.add("container", "read-only transfer timing", est.pop("status"), est)
    else:
        rep.add("container", "read-only transfer timing", "UNVERIFIED", "skipped (--timing-seconds 0)")
    return man["total_bytes"]


def check_database(rep: Report, args: argparse.Namespace) -> tuple[int | None, int | None]:
    dsn = os.environ.get(wb.ADMIN_DSN_ENV)
    if not dsn:
        rep.add("database", "connection", "UNVERIFIED", f"{wb.ADMIN_DSN_ENV} not set (open the tunnel and export it)")
        return None, None
    try:
        t0 = time.monotonic()
        conn = wb.admin_connect(dsn)
        latencies = []
        for _ in range(10):
            s = time.monotonic()
            conn.execute("SELECT 1")
            latencies.append((time.monotonic() - s) * 1000)
    except Exception as exc:
        rep.add("database", "connection", "FAIL", type(exc).__name__)
        return None, None
    with conn:
        ident = wb.identity(conn)
        major = parse_major(ident["server_version"])
        rep.add("database", "identity (record this system identifier in the approval)", "INFO",
                {"system_identifier": ident["system_identifier"], "database": ident["database"], "server_version": ident["server_version"]})
        rep.add("database", "not a replica", "PASS" if not ident["in_recovery"] else "FAIL")
        rep.add("database", "admin role is superuser", "INFO", ident["admin_is_superuser"])
        rep.add("database", "tunnel latency", "INFO", {"median_ms": round(sorted(latencies)[5], 1), "max_ms": round(max(latencies), 1)})
        settings = dict(conn.execute(
            "SELECT name, setting FROM pg_settings WHERE name IN ('archive_mode','archive_timeout','wal_level','idle_in_transaction_session_timeout',"
            "'idle_session_timeout','statement_timeout','lock_timeout','max_connections')").fetchall())
        rep.add("database", "settings relevant to the barrier", "INFO", settings)
        if settings.get("idle_in_transaction_session_timeout", "0") != "0":
            rep.add("database", "server idle-in-transaction timeout", "INFO",
                    "non-zero: the barrier's lock holder sets its own session value to 0, and the monitor reports it if killed")
        state = wb.barrier_state(conn, ident["database"])
        rep.add("database", "no barrier or lock_timeout already set on the database",
                "PASS" if state["setting"] is None and state["lock_timeout"] is None else "FAIL", state)
        db_bytes = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        tables = len(wb.user_tables(conn))
        alembic = None
        try:
            alembic = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        except Exception:
            pass
        rep.add("database", "size, tables, schema revision", "INFO", {"database_bytes": db_bytes, "tables": tables, "alembic_version": alembic})
        sessions = wb.list_sessions(conn, ident["database"])
        rep.add("database", "sessions right now", "INFO", {s: sum(1 for x in sessions if x["state"] == s) for s in {x["state"] for x in sessions}})
        wb.write_counters(conn)
        before = wb.write_counters(conn)
        time.sleep(args.quiet_probe_seconds)
        after = wb.write_counters(conn)
        busy = [x for x in wb.list_sessions(conn, ident["database"]) if x["state"] != "idle"]
        quiet = before == after and not busy
        rep.add("database", f"quiet right now ({int(args.quiet_probe_seconds)} s probe: no writes, no open transactions)",
                "PASS" if quiet else "WARN", {"counters_before": before, "counters_after": after, "open_transactions": len(busy),
                                               "note": "the real engage demands a longer quiet period and refuses otherwise"})
        row = conn.execute("SELECT last_archived_wal, last_archived_time, failed_count, last_failed_wal, last_failed_time FROM pg_stat_archiver").fetchone()
        keys = ("last_archived_wal", "last_archived_time", "failed_count", "last_failed_wal", "last_failed_time")
        arch = evaluate_archiver(dict(zip(keys, row)), now=datetime.now(timezone.utc), max_lag_s=args.archive_lag_max_seconds,
                                 failures_explained=args.failures_explained_by)
        rep.add("recovery", "WAL archiver state", arch.pop("status"), arch)
        last_wal = row[0]
    if args.pgbackrest_json:
        try:
            br = evaluate_pgbackrest(json.loads(Path(args.pgbackrest_json).read_text()), archiver_last_wal=last_wal)
            rep.add("recovery", "pgBackRest base backup + archive continuity", br.pop("status"), br)
        except (OSError, ValueError, KeyError) as exc:
            rep.add("recovery", "pgBackRest base backup + archive continuity", "FAIL", f"unreadable evidence: {type(exc).__name__}")
    else:
        rep.add("recovery", "pgBackRest base backup + archive continuity", "UNVERIFIED",
                "run `pgbackrest info --output=json` and `pgbackrest check` on the Postgres service and pass --pgbackrest-json")
    if os.environ.get(wb.APP_DSN_ENV):
        try:
            with wb.app_connect() as app:
                su = app.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]
                rep.add("database", "application role is superuser", "INFO", su)
        except Exception as exc:
            rep.add("database", "application role connection", "FAIL", type(exc).__name__)
    return db_bytes, major


def check_approval(rep: Report, args: argparse.Namespace) -> None:
    try:
        data = approval.validate_approval(args.approval_file, now=datetime.now(timezone.utc), require_window_open=False)
        rep.add("approval", "owner approval file", "PASS", {"window_start": data["window_start"], "window_end": data["window_end"], "operator": data["operator"]})
    except approval.ApprovalError as exc:
        rep.add("approval", "owner approval file", "FAIL", {"state": "UNAPPROVED", "missing": exc.problems})


def run(args: argparse.Namespace) -> Report:
    rep = Report()
    db_bytes, major = check_database(rep, args)
    uploads_bytes = check_container(rep, args) if args.remote_prefix is not None else None
    if args.remote_prefix is None:
        rep.add("container", "reachable", "UNVERIFIED", "no --remote-prefix given (e.g. 'railway ssh --service … --environment staging --')")
    check_workstation(rep, args, major)
    check_storage(rep, args, db_bytes, uploads_bytes)
    check_approval(rep, args)
    return rep


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True, help="private JSON report, outside the repository")
    p.add_argument("--uploads-dir", default="/var/lib/simo-os/uploads")
    p.add_argument("--remote-prefix", default=None, help='e.g. "railway ssh --service simo-api-staging --environment staging --"; "" runs locally')
    p.add_argument("--remote-python", default="python3")
    p.add_argument("--pg-dump", default="pg_dump")
    p.add_argument("--pg-restore", default="pg_restore")
    p.add_argument("--psql", default="psql")
    p.add_argument("--server-major", type=int)
    p.add_argument("--require-wsl2", action="store_true")
    p.add_argument("--require-railway", action="store_true")
    p.add_argument("--attest-encrypted-volume", action="store_true")
    p.add_argument("--min-free-multiple", type=float, default=3.0)
    p.add_argument("--timing-seconds", type=float, default=60.0, help="read-only transfer sample length (0 skips)")
    p.add_argument("--transfer-budget-seconds", type=float, default=480.0)
    p.add_argument("--quiet-probe-seconds", type=float, default=15.0)
    p.add_argument("--archive-lag-max-seconds", type=float, default=7200.0)
    p.add_argument("--failures-explained-by", help="operator's reference to the pgBackRest log / provider notice explaining the failures")
    p.add_argument("--pgbackrest-json", type=Path)
    p.add_argument("--approval-file", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = args.report.expanduser().absolute()
    try:
        report_path.relative_to(REPOSITORY_ROOT)
        print(json.dumps({"refused": "the report must be written outside the repository"}), file=sys.stderr)
        return EXIT_REFUSED
    except ValueError:
        pass
    if report_path.exists() or not report_path.parent.is_dir():
        print(json.dumps({"refused": "report path exists or its directory is missing"}), file=sys.stderr)
        return EXIT_REFUSED
    rep = run(args)
    verdict = "BLOCKED" if rep.blocked else ("READY (with unverified items)" if rep.count("UNVERIFIED") else "READY")
    doc = {"generated_utc": wb.utcnow(), "verdict": verdict, "window": "UNAPPROVED unless the approval check above is PASS",
           "counts": {s: rep.count(s) for s in ("PASS", "FAIL", "WARN", "INFO", "UNVERIFIED")}, "checks": rep.items}
    fd = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(doc, handle, indent=2, default=str)
    for i in rep.items:
        print(f"{i['status']:<10} {i['area']:<11} {i['check']}")
    print(f"\nVERDICT: {verdict}  {doc['counts']}")
    return EXIT_BLOCKED if rep.blocked else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
