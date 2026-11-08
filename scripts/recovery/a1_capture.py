"""A1 matched recovery-point capture WITHOUT a Railway manual backup.

Used because Railway refuses manual backups beyond 10 per volume and the
uploads volume is also beyond the 50%-of-volume manual-backup limit.  Nothing
here deletes, restores, resizes or reconfigures anything; it only reads.

Preconditions (all checked, all fail closed): an owner-recorded UTC window of
at most 30 minutes that is open now; the writer barrier engaged and drained
(`writer_barrier.py`), uploads frozen; a private, empty, owner-only output
directory outside the repository with enough free disk; a `pg_dump` at least
as new as the server; no active or idle-in-transaction sessions.

Sequence: T0 (content fingerprints) -> custom-format `pg_dump` -> read-only
uploads copy and deterministic archive with per-file SHA-256 manifest -> T1
(same fingerprints, compared byte-for-byte to T0) -> correlation record ->
four independent SHA-256 values (hashlib AND the system `sha256sum`) ->
dump/archive readability checks.

STOP (exit 10, partial artifacts MOVED to quarantine-*, never deleted): barrier
interrupted or lifted, any T0/T1 difference, window expired, a signal, dump or
archive unreadable or incomplete, manifest mismatch, or disk exhausted.

"Capture verified" means the artifacts are complete and consistent.  It does
NOT prove restore usability or RPO/RTO; those need the separate scratch
restore (B4/B5).  Secrets: DSNs come from the environment and reach pg_dump
only through its own process environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import content_fingerprint as cf  # noqa: E402
import matched_bundle  # noqa: E402
import writer_barrier as wb  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXIT_OK, EXIT_REFUSED, EXIT_STOP = 0, 2, 10
MAX_WINDOW = timedelta(minutes=30)
MIN_REMAINING = timedelta(minutes=2)
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}[A-Za-z0-9]")
ARTIFACTS = ("dump.pgdump", "uploads.tar", "uploads.manifest.json", "correlation.json")
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Stop(RuntimeError):
    """A STOP condition: capture is NOT verified; partial artifacts are quarantined."""

    def __init__(self, phase: str, reason: str):
        super().__init__(f"{phase}: {reason}")
        self.phase, self.reason = phase, reason


def parse_utc(value: str) -> datetime:
    try:
        return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise wb.BarrierError(f"{value!r} is not an exact UTC time like 2026-11-09T10:00:00Z") from exc


def utc(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime(UTC_FORMAT)


def check_window(start: datetime, end: datetime, now: datetime, *, phase: str, fresh: bool = False) -> None:
    if end - start > MAX_WINDOW or end <= start:
        raise wb.BarrierError("window must be positive and at most 30 minutes")
    if now < start:
        raise Stop(phase, "the approved window has not opened yet")
    if now >= end:
        raise Stop(phase, "the approved window has expired")
    if fresh and end - now < MIN_REMAINING:
        raise Stop(phase, "less than 2 minutes of the window remain; do not start")


def major(text: str) -> int:
    match = re.search(r"(\d+)(?:\.\d+)?", text)
    if not match:
        raise Stop("preflight", f"cannot read a version from {text!r}")
    return int(match.group(1))


def check_output_dir(out_dir: Path, uploads_hint: Path | None) -> Path:
    out = out_dir.expanduser().absolute()
    if not out.is_dir():
        raise wb.BarrierError("output directory does not exist")
    try:
        out.resolve().relative_to(REPOSITORY_ROOT)
        raise wb.BarrierError("output directory must be outside the repository")
    except ValueError:
        pass
    if uploads_hint is not None:
        try:
            out.resolve().relative_to(uploads_hint.resolve())
            raise wb.BarrierError("output directory must not be inside the uploads directory")
        except ValueError:
            pass
    if stat.S_IMODE(out.stat().st_mode) & 0o077:
        raise wb.BarrierError("output directory must be private (mode 0700)")
    if any(out.iterdir()):
        raise wb.BarrierError("output directory must be empty")
    return out


def dsn_environment(dsn: str) -> dict[str, str]:
    from psycopg.conninfo import conninfo_to_dict

    d = conninfo_to_dict(dsn)
    env = {"PATH": os.environ.get("PATH", ""), "PGUSER": d.get("user", ""), "PGPASSWORD": d.get("password", ""),
           "PGHOST": d.get("host", ""), "PGPORT": str(d.get("port", 5432)), "PGDATABASE": d.get("dbname", ""),
           "PGAPPNAME": "geocore_a1_dump"}
    return env


def sha256sum_tool(path: Path) -> str:
    out = subprocess.run(["sha256sum", "-b", str(path)], capture_output=True, text=True, check=True)
    return out.stdout.split()[0]


def table_data_entries(listing: str) -> set[str]:
    return {f"{m.group(1)}.{m.group(2)}" for m in re.finditer(r"\bTABLE DATA (\S+) (\S+)", listing)}


class Monitor:
    """Samples the barrier in a background thread; any violation latches."""

    def __init__(self, dsn: str, database: str, cutoff, expected_locks: int, interval: float = 1.0):
        self.dsn, self.database, self.cutoff, self.interval = dsn, database, cutoff, interval
        self.expected_locks = expected_locks
        self.problems: list[str] = []
        self.samples = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.baseline: dict[str, Any] | None = None

    def start(self) -> None:
        with wb.admin_connect(self.dsn) as conn:
            time.sleep(1.5)  # let cumulative statistics settle
            self.baseline = wb.sample(conn, self.database, self.cutoff)
        problems = wb.violations(self.baseline, self.baseline, self.expected_locks)
        if problems:
            raise Stop("preflight", "; ".join(problems))
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            with wb.admin_connect(self.dsn) as conn:
                while not self._stop.wait(self.interval):
                    current = wb.sample(conn, self.database, self.cutoff)
                    self.samples += 1
                    self.problems += wb.violations(self.baseline, current, self.expected_locks)
        except Exception as exc:  # losing the monitor is itself a violation
            self.problems.append(f"barrier monitor failed: {type(exc).__name__}")

    def check(self, phase: str) -> None:
        if self.problems:
            raise Stop(phase, "barrier violated: " + "; ".join(sorted(set(self.problems))))
        if self._thread is not None and not self._stop.is_set() and not self._thread.is_alive():
            raise Stop(phase, "barrier monitor stopped")

    def sample_now(self) -> None:
        """A synchronous sample so 'uninterrupted barrier' never rests on timing alone."""
        time.sleep(1.2)  # allow cumulative statistics to flush before comparing counters
        with wb.admin_connect(self.dsn) as conn:
            current = wb.sample(conn, self.database, self.cutoff)
        self.samples += 1
        self.problems += wb.violations(self.baseline, current, self.expected_locks)

    def finish(self) -> int:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return self.samples


class Remote:
    """Runs a command where the uploads live: `railway ssh -- ...`, or nothing when local."""

    def __init__(self, prefix: list[str], python: str):
        self.prefix, self.python = prefix, python

    def run(self, argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(self.prefix + argv, input=stdin, capture_output=True)

    def script(self, command: str, directory: str) -> dict[str, Any]:
        source = Path(cf.__file__).read_bytes()
        done = self.run([self.python, "-", command, "--dir", directory], stdin=source)
        if done.returncode != 0:
            raise Stop("uploads", f"remote {command} failed (exit {done.returncode})")
        return json.loads(done.stdout)

    def fetch_tar(self, directory: str, destination: Path) -> None:
        with destination.open("wb") as handle:
            proc = subprocess.Popen(self.prefix + ["tar", "-C", directory, "-cf", "-", "."], stdout=handle, stderr=subprocess.PIPE)
            _, err = proc.communicate()
        if proc.returncode != 0:
            raise Stop("uploads", f"remote tar failed (exit {proc.returncode})")


def extract_tree(tar_path: Path, tree: Path) -> int:
    """Safe extraction of regular files only; anything else is a STOP."""
    tree.mkdir(mode=0o700)
    count = 0
    with tarfile.open(tar_path, "r:") as archive:
        for member in archive:
            name = member.name[2:] if member.name.startswith("./") else member.name
            if name in ("", "."):
                continue
            parts = Path(name).parts
            if member.name.startswith("/") or ".." in parts:
                raise Stop("uploads", "archive member path escapes the destination")
            target = tree.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif member.isreg():
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.extractfile(member) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst, cf.CHUNK)
                os.chmod(target, 0o600)
                count += 1
            else:
                raise Stop("uploads", "archive contains a link or special file")
    return count


def verify_archive(archive: Path, manifest: dict[str, Any], expected: dict[str, Any]) -> None:
    """3-way check: archive members == bundle manifest == live T0 manifest (path, size, SHA-256)."""
    want = {e["relative_path"]: (e["size_bytes"], e["sha256"]) for e in expected["entries"]}
    listed = {e["relative_path"]: (e["size_bytes"], e["sha256"]) for e in manifest["entries"]}
    if listed != want:
        raise Stop("verify", "bundle manifest does not match the live uploads manifest")
    seen: dict[str, tuple[int, str]] = {}
    with tarfile.open(archive, "r:") as tar:
        for member in tar:
            if not member.isreg():
                raise Stop("verify", "archive holds a non-regular member")
            digest, size = hashlib.sha256(), 0
            src = tar.extractfile(member)
            for chunk in iter(lambda: src.read(cf.CHUNK), b""):
                digest.update(chunk)
                size += len(chunk)
            seen[member.name] = (size, digest.hexdigest())
    if seen != want:
        raise Stop("verify", "archive contents do not match the manifest (missing, extra or altered file)")


def capture(args: argparse.Namespace, *, now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
            hooks: dict[str, Callable[[], None]] | None = None) -> dict[str, Any]:
    hooks = hooks or {}
    start, end = parse_utc(args.window_start), parse_utc(args.window_end)
    if end - start > MAX_WINDOW or end <= start:
        raise wb.BarrierError("window must be positive and at most 30 minutes")
    if not RUN_ID.fullmatch(args.run_id):
        raise wb.BarrierError("run id is invalid")
    if args.confirm_environment not in ("staging", "local"):
        raise wb.BarrierError("--confirm-environment must be 'staging' or 'local'")
    if not args.operator.strip():
        raise wb.BarrierError("an operator must be named")
    if args.confirm_environment == "staging":
        from approval import ApprovalError, validate_approval

        try:
            validate_approval(getattr(args, "approval_file", None), now=now_fn(), operator=args.operator,
                              window_start=args.window_start, window_end=args.window_end)
        except ApprovalError as exc:
            raise wb.BarrierError("STAGING IS UNAPPROVED: " + str(exc)) from None
    out = check_output_dir(args.out_dir, Path(args.uploads_dir) if not args.remote_prefix else None)
    hash_record = args.hash_record.expanduser().absolute()
    for forbidden in (REPOSITORY_ROOT, out):
        try:
            hash_record.relative_to(forbidden)
            raise wb.BarrierError("hash record must be outside the repository and the output directory")
        except ValueError:
            pass
    if hash_record.exists():
        raise wb.BarrierError("hash record already exists")
    phase = "preflight"
    admin_dsn = os.environ.get(wb.ADMIN_DSN_ENV)
    if not admin_dsn:
        raise wb.BarrierError(f"{wb.ADMIN_DSN_ENV} is not set")
    remote = Remote(shlex.split(args.remote_prefix) if args.remote_prefix else [], args.remote_python)
    started = time.monotonic()
    signal_name: list[str] = []

    def on_signal(signum, _frame):
        signal_name.append(signal.Signals(signum).name)
        raise Stop("interrupted", f"received {signal.Signals(signum).name}")

    old = {s: signal.signal(s, on_signal) for s in (signal.SIGINT, signal.SIGTERM)}
    monitor: Monitor | None = None
    work = out / "work"
    try:
        check_window(start, end, now_fn(), phase=phase, fresh=True)
        with wb.admin_connect(admin_dsn) as conn:
            ident = wb.identity(conn)
            database = ident["database"]
            if ident["system_identifier"] != args.expect_system_identifier or ident["in_recovery"]:
                raise Stop(phase, "cluster identity does not match the approved target")
            record = wb.Record.open(args.barrier_record)
            if record.data.get("status") != "engaged" or record.data.get("database") != database:
                raise Stop(phase, "the writer barrier is not recorded as engaged and drained for this database")
            state = wb.barrier_state(conn, database)
            if not state["engaged"]:
                raise Stop(phase, "the database barrier setting is not engaged")
            if record.data.get("busy_engage") or not record.data.get("quiet_verified"):
                raise Stop(phase, "the barrier was engaged without a verified quiet period")
            if not record.data.get("locked_tables"):
                raise Stop(phase, "the write-fence locks are not recorded")
            cutoff = datetime.fromisoformat(record.data["cutoff"])
            busy = [s for s in wb.list_sessions(conn, database) if s["state"] != "idle"]
            if busy:
                raise Stop(phase, f"{len(busy)} unexpected active or in-transaction session(s)")
            if any(s["backend_start"] < cutoff for s in wb.list_sessions(conn, database)):
                raise Stop(phase, "a session older than the barrier is still connected")
            db_bytes = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        writable = remote.script("writable-count", args.uploads_dir)["writable_entries"]
        if writable:
            raise Stop(phase, f"uploads are not frozen: {writable} entries still writable")
        m0 = remote.script("uploads-manifest", args.uploads_dir)
        free = shutil.disk_usage(out).free
        need = args.min_free_multiple * (db_bytes + m0["total_bytes"])
        if free < need:
            raise Stop(phase, f"insufficient free disk: {free} bytes free, {int(need)} required")
        try:
            dump_version = subprocess.run([args.pg_dump, "--version"], capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            raise Stop(phase, "pg_dump is not usable")
        if major(dump_version.split(")", 1)[-1]) < major(ident["server_version"]):
            raise Stop(phase, "pg_dump is older than the server; use a client of the same major version")

        monitor = Monitor(admin_dsn, database, cutoff, int(record.data["locked_tables"]))
        monitor.start()
        monitor.check(phase)

        phase = "T0"
        check_window(start, end, now_fn(), phase=phase)
        fp0 = cf.db_fingerprint(admin_dsn)
        m0b = remote.script("uploads-manifest", args.uploads_dir)
        if cf.diff_manifests(m0, m0b):
            raise Stop(phase, "uploads changed between preflight and T0")
        monitor.check(phase)
        hooks.get("after_t0", lambda: None)()

        phase = "dump"
        check_window(start, end, now_fn(), phase=phase)
        dump = out / ARTIFACTS[0]
        done = subprocess.run([args.pg_dump, "--format=custom", "--no-owner", f"--file={dump}"],
                              env=dsn_environment(admin_dsn), capture_output=True, text=True)
        if done.returncode != 0 or not dump.exists() or dump.stat().st_size == 0:
            raise Stop(phase, f"pg_dump failed or produced nothing (exit {done.returncode})")
        listing = subprocess.run([args.pg_restore, "--list", str(dump)], capture_output=True, text=True)
        if listing.returncode != 0:
            raise Stop(phase, "the dump cannot be listed by pg_restore")
        missing = sorted(set(fp0["tables"]) - table_data_entries(listing.stdout))
        if missing:
            raise Stop(phase, f"the dump has no data entry for {len(missing)} table(s)")
        monitor.check(phase)
        hooks.get("after_dump", lambda: None)()

        phase = "uploads"
        check_window(start, end, now_fn(), phase=phase)
        work.mkdir(mode=0o700)
        tar_stream = work / "stream.tar"
        remote.fetch_tar(args.uploads_dir, tar_stream)
        tree = work / "tree"
        extract_tree(tar_stream, tree)
        copied = cf.uploads_manifest(tree)
        if cf.diff_manifests(m0, copied):
            raise Stop(phase, "the copied uploads do not match the live manifest (transfer or source change)")
        recovery_point = f"{args.run_id}.t0.{fp0['digest'][:16]}"
        archive, manifest_path = out / ARTIFACTS[1], out / ARTIFACTS[2]
        try:
            matched_bundle.create_bundle(tree, archive, manifest_path, recovery_point, utc(now_fn()))
        except matched_bundle.RecoveryError as exc:
            raise Stop(phase, f"archive creation refused: {exc}")
        hooks.get("after_archive", lambda: None)()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_archive(archive, manifest, m0)
        monitor.check(phase)

        phase = "T1"
        check_window(start, end, now_fn(), phase=phase)
        fp1 = cf.db_fingerprint(admin_dsn)
        m1 = remote.script("uploads-manifest", args.uploads_dir)
        diffs = cf.diff_fingerprints(fp0, fp1) + cf.diff_manifests(m0, m1)
        if diffs or fp0["digest"] != fp1["digest"] or m0["digest"] != m1["digest"]:
            raise Stop(phase, f"T0 and T1 differ ({len(diffs)} difference(s)); the recovery point is not valid")
        monitor.check(phase)
        still_frozen = remote.script("writable-count", args.uploads_dir)["writable_entries"]
        if still_frozen:
            raise Stop(phase, "uploads were unfrozen during the capture")
        monitor.sample_now()
        monitor.check(phase)
        samples = monitor.finish()

        phase = "correlation"
        check_window(start, end, now_fn(), phase=phase)

        def artifact(path: Path) -> dict[str, Any]:
            return {"file": path.name, "bytes": path.stat().st_size, "sha256_hashlib": cf.sha256_file(path)}

        correlation = {
            "schema": "geocore-a1-correlation/1", "run_id": args.run_id, "operator": args.operator,
            "environment": args.confirm_environment, "created_utc": utc(now_fn()),
            "window": {"start": args.window_start, "end": args.window_end},
            "target": {"system_identifier": ident["system_identifier"], "database": database, "server_version": ident["server_version"]},
            "alembic_version": fp0["alembic_version"], "recovery_point": recovery_point,
            "t0": {"taken_utc": fp0["taken_utc"], "db_digest": fp0["digest"], "tables": fp0["table_count"], "rows": fp0["row_total"],
                   "uploads_digest": m0["digest"], "wal_lsn_informational": fp0["wal_lsn_informational"]},
            "t1": {"taken_utc": fp1["taken_utc"], "db_digest": fp1["digest"], "uploads_digest": m1["digest"],
                   "wal_lsn_informational": fp1["wal_lsn_informational"]},
            "t0_equals_t1": True,
            "uploads": {"files": m0["file_count"], "bytes": m0["total_bytes"]},
            "barrier": {"cutoff": record.data["cutoff"], "samples_taken": samples, "violations": []},
            "artifacts": {"dump": artifact(dump), "uploads_archive": artifact(archive), "uploads_manifest": artifact(manifest_path)},
            "provider_backups": args.provider_backups or "none: native manual backups refused by plan limit",
            "scope": "capture and integrity only; restore usability and RPO/RTO are NOT proven by this record",
        }
        corr_path = out / ARTIFACTS[3]
        corr_path.write_text(json.dumps(correlation, indent=2, sort_keys=True), encoding="utf-8")

        phase = "hashes"
        paths = [out / name for name in ARTIFACTS]
        for p in paths:
            os.chmod(p, 0o400)
        independent = {}
        for p in paths:
            lib, tool = cf.sha256_file(p), sha256sum_tool(p)
            if lib != tool:
                raise Stop(phase, f"two SHA-256 implementations disagree for {p.name}")
            independent[p.name] = lib
        if len(set(independent.values())) != 4:
            raise Stop(phase, "the four hashes are not distinct")
        listing2 = subprocess.run([args.pg_restore, "--list", str(dump)], capture_output=True, text=True)
        verify_archive(archive, json.loads(manifest_path.read_text()), m0)
        if listing2.returncode != 0 or any(cf.sha256_file(p) != independent[p.name] for p in paths):
            raise Stop(phase, "an artifact changed or became unreadable during verification")
        fd = os.open(hash_record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(f"# out-of-band SHA-256 evidence for run {args.run_id}; keep apart from the bundle\n")
            for name, value in independent.items():
                handle.write(f"{value}  {name}\n")
        shutil.rmtree(work)  # our own working copy of customer files, not a backup
        if now_fn() >= end:
            raise Stop(phase, "the window expired before the capture finished")
        result = {"capture_verified": True, "run_id": args.run_id, "hashes": independent, "t0_equals_t1": True,
                  "seconds": round(time.monotonic() - started, 1), "scope": correlation["scope"]}
        (out / "RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True))
        return result
    except BaseException as exc:
        stop = exc if isinstance(exc, Stop) else Stop(phase, f"{type(exc).__name__}: {exc}")
        if monitor is not None:
            monitor.finish()
        quarantine = out / f"quarantine-{utc(now_fn()).replace(':', '')}"
        quarantine.mkdir(mode=0o700, exist_ok=True)
        for name in (*ARTIFACTS, "work", "RESULT.json"):
            p = out / name
            if p.exists():
                try:
                    os.chmod(p, 0o600)
                except OSError:
                    pass
                p.rename(quarantine / name)
        (quarantine / "STOP.json").write_text(json.dumps({"stop": True, "phase": stop.phase, "reason": stop.reason,
                                                          "at": utc(now_fn()), "capture_verified": False}, indent=2))
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise stop from None
    finally:
        for s, h in old.items():
            signal.signal(s, h)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run-id", required=True)
    p.add_argument("--operator", required=True)
    p.add_argument("--confirm-environment", required=True)
    p.add_argument("--window-start", required=True, help="exact UTC, e.g. 2026-11-09T10:00:00Z")
    p.add_argument("--window-end", required=True)
    p.add_argument("--expect-system-identifier", required=True)
    p.add_argument("--barrier-record", type=Path, required=True)
    p.add_argument("--uploads-dir", required=True, help="path where the uploads live (inside the container when --remote-prefix is used)")
    p.add_argument("--remote-prefix", default="", help='e.g. "railway ssh --service simo-api-staging --environment staging --"')
    p.add_argument("--remote-python", default="python3")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--hash-record", type=Path, required=True)
    p.add_argument("--approval-file", type=Path, help="owner approval file; mandatory for --confirm-environment staging")
    p.add_argument("--provider-backups", default="")
    p.add_argument("--pg-dump", default="pg_dump")
    p.add_argument("--pg-restore", default="pg_restore")
    p.add_argument("--min-free-multiple", type=float, default=3.0)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        result = capture(build_parser().parse_args(argv))
    except wb.BarrierError as exc:
        print(json.dumps({"refused": str(exc)}), file=sys.stderr)
        return EXIT_REFUSED
    except Stop as stop:
        print(json.dumps({"STOP": stop.reason, "phase": stop.phase, "capture_verified": False}), file=sys.stderr)
        return EXIT_STOP
    print(json.dumps(result, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
