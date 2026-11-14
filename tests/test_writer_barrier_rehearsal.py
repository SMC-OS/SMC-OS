"""Disposable-LOCAL rehearsal of the A1 writer barrier (never touches Railway).

Builds a throwaway PostgreSQL cluster, runs the real application as UID 10001
(as on Railway) in production mode against it, then proves with ACTUAL writes
that the barrier blocks API mutations, direct database writes under the
application role, background-job writes and upload writes, while reads keep
working, in-flight transactions finish, and removal restores normal service
without losing or corrupting anything.

Positive controls come first so that every later denial is attributable to the
barrier and not to a broken fixture.  Results are collected in EVIDENCE and
written as JSON when REHEARSAL_EVIDENCE names a path.

Skipped unless: Linux, running as root (to drop to UID 10001 and to own the
cluster), PostgreSQL server binaries installed, and REHEARSAL_PYTHON (an
interpreter UID 10001 can execute, with the app requirements) set.
"""

from __future__ import annotations

import concurrent.futures
import glob
import hashlib
import io
import json
import os
import pwd
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[1]
RECOVERY = REPO / "scripts" / "recovery"
sys.path.insert(0, str(RECOVERY))

import content_fingerprint as cf  # noqa: E402
import writer_barrier as wb  # noqa: E402

PG_BINS = sorted(glob.glob("/usr/lib/postgresql/*/bin"))
PYTHON = os.environ.get("REHEARSAL_PYTHON", "")
APP = ["setpriv", "--reuid=10001", "--regid=10001", "--clear-groups"]
PORT_PG, PORT_API = 55433, 18080

pytestmark = pytest.mark.skipif(
    not (
        sys.platform.startswith("linux")
        and hasattr(os, "geteuid")
        and os.geteuid() == 0
        and PG_BINS
        and shutil.which("setpriv")
        and PYTHON
    ),
    reason="local rehearsal needs root, PostgreSQL server binaries, setpriv and REHEARSAL_PYTHON",
)

EVIDENCE: list[dict] = []


def record(name: str, passed: bool, **detail) -> None:
    EVIDENCE.append({"check": name, "passed": bool(passed), **detail})
    assert passed, f"{name}: {detail}"


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def env():
    base = Path(tempfile.mkdtemp(prefix="geocore-rehearsal-", dir="/var/tmp"))
    base.chmod(0o755)
    postgres = pwd.getpwnam("postgres")
    os.chown(base, postgres.pw_uid, postgres.pw_gid)
    pw = {k: secrets.token_urlsafe(18) for k in ("admin", "super", "limited")}
    pwfile = base / "pwfile"
    pwfile.write_text(pw["admin"])
    os.chown(pwfile, postgres.pw_uid, postgres.pw_gid)
    bindir = PG_BINS[-1]
    pg = ["runuser", "-u", "postgres", "--"]
    subprocess.run(
        pg + [f"{bindir}/initdb", "-D", str(base / "data"), "-U", "simo_admin", "-A", "scram-sha-256", f"--pwfile={pwfile}"],
        check=True, capture_output=True,
    )
    subprocess.run(
        pg + [f"{bindir}/pg_ctl", "-D", str(base / "data"), "-w", "-l", str(base / "pg.log"), "-o",
              f"-p {PORT_PG} -c listen_addresses=127.0.0.1 -c unix_socket_directories={base} -c fsync=off", "start"],
        check=True, capture_output=True,
    )
    uploads = base / "uploads"
    uploads.mkdir(mode=0o750)
    os.chown(uploads, 10001, 10001)
    (base / "private").mkdir(mode=0o700)  # barrier records: outside repo, root-only

    def dsn(user, database):
        return f"postgresql://{user}:{pw[{'simo_admin': 'admin', 'simo_super': 'super', 'simo_limited': 'limited'}[user]]}@127.0.0.1:{PORT_PG}/{database}"

    import psycopg

    with psycopg.connect(dsn("simo_admin", "postgres"), autocommit=True) as c:
        c.execute(f"CREATE ROLE simo_super SUPERUSER LOGIN PASSWORD '{pw['super']}'")
        c.execute(f"CREATE ROLE simo_limited NOSUPERUSER LOGIN PASSWORD '{pw['limited']}'")
        for database in ("rehearsal", "rehearsal_b"):
            c.execute(f"CREATE DATABASE {database}")
    alembic_env = {**os.environ, "DATABASE_URL": dsn("simo_admin", "rehearsal").replace("postgresql://", "postgresql+psycopg://"),
                   "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([PYTHON, "-m", "alembic", "upgrade", "head"], cwd=REPO, env=alembic_env, check=True, capture_output=True)
    with psycopg.connect(dsn("simo_admin", "rehearsal"), autocommit=True) as c:
        c.execute("CREATE TABLE barrier_probe (id serial PRIMARY KEY, note text)")
        c.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO simo_limited")
        c.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO simo_limited")
    with psycopg.connect(dsn("simo_admin", "rehearsal_b"), autocommit=True) as c:
        c.execute("CREATE TABLE barrier_probe (id serial PRIMARY KEY, note text)")
        c.execute("CREATE TABLE alembic_version (version_num text)")
    with psycopg.connect(dsn("simo_admin", "rehearsal"), autocommit=True) as c:
        system_id = c.execute("SELECT system_identifier::text FROM pg_control_system()").fetchone()[0]

    app_env = {
        "PATH": os.environ["PATH"], "HOME": "/nonexistent", "PYTHONDONTWRITEBYTECODE": "1",
        "APP_ENV": "production", "SEED_DATA_ENABLED": "false",
        "DATABASE_URL": dsn("simo_super", "rehearsal").replace("postgresql://", "postgresql+psycopg://"),
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "SEED_ADMIN_EMAIL": "rehearsal-admin@acceptance.invalid",
        "SEED_ADMIN_PASSWORD": secrets.token_urlsafe(18),
        "CORS_ALLOWED_ORIGINS": "https://web.rehearsal.invalid",
        "UPLOAD_DIR": str(uploads),
    }
    state = {"base": base, "dsn": dsn, "uploads": uploads, "system_id": system_id, "app_env": app_env,
             "private": base / "private", "owner_password": "Rehearsal-" + secrets.token_urlsafe(12) + "1!"}
    yield state
    subprocess.run(pg + [f"{bindir}/pg_ctl", "-D", str(base / "data"), "-m", "immediate", "stop"], capture_output=True)
    shutil.rmtree(base, ignore_errors=True)
    out = os.environ.get("REHEARSAL_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=2), encoding="utf-8")


def start_api(env, port=PORT_API, wait=True):
    log = open(env["base"] / f"api-{port}.log", "wb")  # a file, never an undrained pipe (a full pipe blocks the server)
    proc = subprocess.Popen(
        APP + [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO, env=env["app_env"], stdout=log, stderr=subprocess.STDOUT,
    )
    proc.log_path = env["base"] / f"api-{port}.log"
    if wait:
        for _ in range(100):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                    return proc
            except httpx.HTTPError:
                time.sleep(0.2)
            if proc.poll() is not None:
                raise RuntimeError("API exited during start-up")
        raise RuntimeError("API did not become healthy")
    return proc


@pytest.fixture(scope="module")
def api(env):
    proc = start_api(env)
    yield f"http://127.0.0.1:{PORT_API}"
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def admin(env, database="rehearsal"):
    return wb.admin_connect(env["dsn"]("simo_admin", database))


def barrier_cli(env, *args, database="rehearsal", as_app=False, extra_env=None):
    cmd = ([*APP] if as_app else []) + [PYTHON, str(RECOVERY / "writer_barrier.py"), *args]
    e = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1",
         wb.ADMIN_DSN_ENV: env["dsn"]("simo_admin", database), wb.APP_DSN_ENV: env["dsn"]("simo_super", database),
         **(extra_env or {})}
    return subprocess.run(cmd, env=e, capture_output=True, text=True)


def pdf(n: int) -> bytes:
    return b"%PDF-1.4\nrehearsal-" + str(n).encode() * 50


S: dict = {}  # scenario state shared by ordered tests


# --------------------------------------------------------------- 0 controls
def test_00_positive_controls(env, api):
    owner = {"SYNTHETIC_OWNER_PASSWORD": env["owner_password"], "PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1",
             "APP_ENV": "development", "DATABASE_URL": env["app_env"]["DATABASE_URL"],
             "UPLOAD_DIR": str(env["uploads"]), "SEED_DATA_ENABLED": "false"}
    done = subprocess.run(
        APP + [PYTHON, "scripts/qa/provision_synthetic_owner.py", "--email", "rehearsal-a@acceptance.invalid",
               "--company", "Rehearsal A", "--confirm-environment", "local"],
        cwd=REPO, env=owner, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    r = httpx.post(f"{api}/api/v1/auth/login", json={"email": "rehearsal-a@acceptance.invalid", "password": env["owner_password"]})
    assert r.status_code == 200, r.text
    S["token"] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = httpx.post(f"{api}/api/v1/customers", json={"name": "Rehearsal Customer"}, headers=S["token"])
    record("control: API mutation succeeds before the barrier", r.status_code == 201, status=r.status_code)
    S["customer_id"] = r.json()["id"]
    ids = []
    for n in range(3):
        r = httpx.post(f"{api}/api/v1/documents?customer_id={S['customer_id']}",
                       files={"file": (f"doc{n}.pdf", io.BytesIO(pdf(n)), "application/pdf")}, headers=S["token"])
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    S["doc_ids"] = ids
    files = sorted(p for p in env["uploads"].iterdir())
    record("control: upload succeeds and writes files before the barrier", len(files) == 3 and files[0].stat().st_uid == 10001, files=len(files))
    for role in ("simo_super", "simo_limited"):
        with wb.app_connect(env["dsn"](role, "rehearsal")) as c:
            c.execute("INSERT INTO barrier_probe(note) VALUES ('control')")
        record(f"control: direct DB write succeeds as {role} before the barrier", True)
    job = subprocess.run(APP + [PYTHON, "-m", "app.jobs.automations"], cwd=REPO, env=env["app_env"], capture_output=True, text=True)
    record("control: automation job entrypoint runs before the barrier", job.returncode == 0, exit=job.returncode)
    S["doc_hash"] = hashlib.sha256(pdf(0)).hexdigest()


# ------------------------------------------------------- 1 negative engage
def test_01_engage_refusals_change_nothing(env, api):
    rec = env["private"] / "refusals.json"
    wrong_id = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "local",
                           "--expect-system-identifier", "0000000000000000000")
    record("negative: wrong cluster system identifier is refused", wrong_id.returncode == wb.EXIT_REFUSED, exit=wrong_id.returncode)
    prod = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "production",
                       "--expect-system-identifier", env["system_id"])
    record("negative: --confirm-environment production is refused", prod.returncode == wb.EXIT_REFUSED, exit=prod.returncode)
    inside = barrier_cli(env, "db-engage", "--record", str(REPO / "barrier-record.json"), "--confirm-environment", "local",
                         "--expect-system-identifier", env["system_id"])
    record("negative: record file inside the repository is refused", inside.returncode == wb.EXIT_REFUSED, exit=inside.returncode)
    with admin(env) as c:
        state = wb.barrier_state(c, "rehearsal")
    record("negative: refused engage left the database untouched", state["setting"] is None, state=state)
    S["fp_pre"] = cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal"))
    S["m_pre"] = cf.uploads_manifest(env["uploads"])


# ----------------------------------------------- 2 concurrency + in-flight
def test_02_engage_under_concurrent_load(env, api):
    results, stop = [], threading.Event()
    lock = threading.Lock()
    inflight_done = {}

    def inflight():  # a transaction that is mid-flight when the barrier engages
        import psycopg
        with psycopg.connect(env["dsn"]("simo_super", "rehearsal"), application_name="inflight") as c:
            c.execute("INSERT INTO barrier_probe(note) VALUES ('inflight')")
            c.execute("SELECT pg_sleep(4)")
        inflight_done["committed_at"] = time.monotonic()

    def hammer(worker):
        n = 0
        while not stop.is_set():
            n += 1
            name = f"load-{worker}-{n}"
            started = time.monotonic()
            try:
                r = httpx.post(f"{api}/api/v1/customers", json={"name": name}, headers=S["token"], timeout=15)
                code = r.status_code
            except httpx.HTTPError:
                code = None
            with lock:
                results.append((name, code, started, time.monotonic() - started))

    t_in = threading.Thread(target=inflight)
    t_in.start()
    workers = [threading.Thread(target=hammer, args=(w,)) for w in range(6)]
    [w.start() for w in workers]
    time.sleep(1.5)
    rec = env["private"] / "main-barrier.json"
    t0 = time.monotonic()
    done = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "local", "--allow-busy",
                       "--expect-system-identifier", env["system_id"], "--drain-timeout", "30")
    engaged_at = time.monotonic()
    assert done.returncode == 0, done.stderr
    summary = json.loads(done.stdout)
    time.sleep(2.0)
    stop.set()
    [w.join() for w in workers]
    t_in.join()
    S["record"] = rec
    record("concurrency: engage waited for the in-flight transaction (never killed it) and then took the write fence",
           summary["inflight_waited_for"] >= 1 and engaged_at - t0 >= 1.5 and summary["locked_tables"] >= 10, drain=summary, seconds=round(engaged_at - t0, 2))
    with admin(env) as c:
        present = {r[0] for r in c.execute("SELECT name FROM customers WHERE name LIKE 'load-%'").fetchall()}
        inflight_row = c.execute("SELECT count(*) FROM barrier_probe WHERE note='inflight'").fetchone()[0]
    record("concurrency: the in-flight transaction committed intact", inflight_row == 1 and "committed_at" in inflight_done)
    ok = {n for n, code, *_ in results if code == 201}
    failed = {n for n, code, *_ in results if code is not None and code != 201}
    unknown = {n for n, code, *_ in results if code is None}
    record("concurrency: every acknowledged write is present (no loss)", ok <= present, acknowledged=len(ok), present=len(present))
    started_at = {n: st for n, _c, st, _d in results}
    leaked = failed & present
    leaked_after = {n for n in leaked if started_at[n] > engaged_at}
    with admin(env) as c:
        activity = {r[0] for r in c.execute("SELECT description FROM activity_log WHERE description LIKE 'load-%'").fetchall()}
    straddlers = sorted(leaked - leaked_after)
    record("concurrency: no request STARTED after the barrier left a row", not leaked_after, leaked_after=len(leaked_after))
    EVIDENCE.append({
        "check": "FINDING: a request straddling the cutoff can be half-applied (row saved, follow-up write refused, client sees an error)",
        "passed": True, "straddling_requests_with_error_but_saved_row": len(straddlers),
        "of_which_missing_their_activity_log_row": len([n for n in straddlers if n not in activity]),
        "note": "database stays internally consistent; engage when staging is idle and take T0 only after the drain",
    })
    after = [code for _, code, started, _d in results if started > engaged_at + 0.5]
    record("concurrency: no write started after the barrier succeeded", bool(after) and all(c != 201 for c in after),
           attempts_after_barrier=len(after), statuses=sorted({c for c in after}, key=str),
           slowest=sorted((round(d, 1), c) for _, c, st, d in results if st > t0)[-4:], engage_seconds=round(engaged_at - t0, 1))
    record("concurrency: the load was real (writes succeeded before the barrier)", len(ok) > 5, acknowledged_before=len(ok), unknown=len(unknown))
    S["fp_barrier"] = cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal"))
    S["m_barrier"] = cf.uploads_manifest(env["uploads"])


# --------------------------------------------------- 3 database-layer denials
def test_03_db_denials_and_reads(env, api):
    for role in ("simo_super", "simo_limited"):
        with wb.app_connect(env["dsn"](role, "rehearsal")) as c:
            result = wb.probe(c, table="alembic_version", real_write_table="barrier_probe")
        record(f"barrier: direct DB write rejected for {role} (no-op and real INSERT), reads work", result["ok"], result=result)
    r = httpx.post(f"{api}/api/v1/customers", json={"name": "after-barrier"}, headers=S["token"])
    record("barrier: API mutation rejected", r.status_code >= 400, status=r.status_code)
    for path in ("/api/v1/customers", f"/api/v1/documents?customer_id={S['customer_id']}", "/api/v1/auth/me"):
        g = httpx.get(f"{api}{path}", headers=S["token"])
        record(f"reads: GET {path.split('?')[0]} still 200", g.status_code == 200, status=g.status_code)
    for path in ("/health", "/ready"):
        record(f"reads: {path} still 200", httpx.get(f"{api}{path}").status_code == 200)
    login = httpx.post(f"{api}/api/v1/auth/login", json={"email": "rehearsal-a@acceptance.invalid", "password": env["owner_password"]})
    EVIDENCE.append({"check": "informational: fresh login during the barrier", "passed": True, "status": login.status_code,
                     "note": "log in BEFORE the window; tokens already issued keep working for reads"})
    now = cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal"))
    record("barrier: denied attempts left the database byte-identical", now["digest"] == S["fp_barrier"]["digest"],
           differences=cf.diff_fingerprints(S["fp_barrier"], now))


# ---------------------------------------------- 4 uploads layer (gap, then fix)
def test_04_uploads_gap_then_freeze(env, api):
    upload = lambda: httpx.post(f"{api}/api/v1/documents?customer_id={S['customer_id']}",
                                files={"file": ("late.pdf", io.BytesIO(pdf(9)), "application/pdf")}, headers=S["token"])
    r = upload()
    orphans = sorted(set(env["uploads"].iterdir()) - {env["uploads"] / e["relative_path"] for e in S["m_pre"]["entries"]})
    record("FINDING: with the DB barrier alone, a rejected upload still leaves an orphan FILE (uploads layer is mandatory)",
           r.status_code >= 400 and len(orphans) == 1, status=r.status_code, orphan_files=len(orphans))
    for o in orphans:
        o.unlink()  # rehearsal cleanup, as the owning user
    state = env["private"] / "uploads-state.json"
    root = subprocess.run([PYTHON, str(RECOVERY / "writer_barrier.py"), "uploads-probe", "--dir", str(env["uploads"])],
                          capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    record("negative: uploads probe refuses to run as root (root would bypass permissions)", root.returncode == wb.EXIT_REFUSED)
    pre_probe = barrier_cli(env, "uploads-probe", "--dir", str(env["uploads"]), as_app=True)
    record("control: before freezing, the uploads probe correctly FAILS (writes still possible)",
           pre_probe.returncode == wb.EXIT_PROBE_FAILED, exit=pre_probe.returncode)
    S["uploads_state"] = state
    os.chown(env["private"], 10001, 10001)  # state is written by the app user, like `railway ssh` would
    freeze = barrier_cli(env, "uploads-freeze", "--dir", str(env["uploads"]), "--state", str(state), as_app=True)
    assert freeze.returncode == 0, freeze.stderr
    probe = barrier_cli(env, "uploads-probe", "--dir", str(env["uploads"]), as_app=True)
    record("barrier: actual new-file write and existing-file write-open rejected, reads work",
           probe.returncode == 0, result=json.loads(probe.stdout))
    r = upload()
    now = cf.uploads_manifest(env["uploads"])
    record("barrier: API upload rejected and NO file left behind", r.status_code >= 400 and not cf.diff_manifests(S["m_pre"], now),
           status=r.status_code, differences=cf.diff_manifests(S["m_pre"], now))
    d = httpx.get(f"{api}/api/v1/documents/{S['doc_ids'][0]}/download", headers=S["token"])
    record("reads: existing document still downloads with identical bytes while frozen",
           d.status_code == 200 and hashlib.sha256(d.content).hexdigest() == S["doc_hash"], status=d.status_code)


# --------------------------------------------------------- 5 background jobs
def test_05_background_jobs_cannot_write(env, api):
    script = ("from sqlalchemy import text\nfrom app.database.database import SessionLocal\n"
              "db = SessionLocal()\ndb.execute(text(\"INSERT INTO barrier_probe(note) VALUES ('job')\"))\ndb.commit()\n")
    writer = subprocess.run(APP + [PYTHON, "-c", script], cwd=REPO, env=env["app_env"], capture_output=True, text=True)
    record("barrier: a job-style writer using the app's own SessionLocal is rejected",
           writer.returncode != 0 and ("read-only transaction" in writer.stderr or "lock timeout" in writer.stderr),
           exit=writer.returncode)
    for module in ("app.jobs.automations", "app.jobs.follow_up", "app.jobs.trial_reminders"):
        job = subprocess.run(APP + [PYTHON, "-m", module], cwd=REPO, env=env["app_env"], capture_output=True, text=True)
        EVIDENCE.append({"check": f"informational: {module} during the barrier", "passed": True, "exit": job.returncode,
                         "note": "exit code only; the content fingerprint below proves nothing changed"})
    now = cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal"))
    record("barrier: jobs changed nothing (content fingerprint identical)", now["digest"] == S["fp_barrier"]["digest"],
           differences=cf.diff_fingerprints(S["fp_barrier"], now))


# --------------------------------------------------- 6 watch + restart hazard
def test_06_watch_clean_and_restart_hazard(env, api):
    watch = barrier_cli(env, "db-watch", "--record", str(S["record"]), "--duration", "4", "--interval", "1")
    record("monitor: continuous watch over an idle barrier reports clean", watch.returncode == 0, out=watch.stdout.strip()[:120])
    second = start_api(env, port=18081, wait=False)
    try:
        second.wait(timeout=30)
    except subprocess.TimeoutExpired:
        second.kill()
    out = second.log_path.read_text(errors="replace")
    record("HAZARD: an API restart during the freeze crash-loops on the production upload probe",
           second.returncode != 0 and "UPLOAD_DIR must be writable" in out, exit=second.returncode)


# ----------------------------------------------------------- 7 reversal
def test_07_release_restores_service_without_loss(env, api):
    thaw = barrier_cli(env, "uploads-thaw", "--dir", str(env["uploads"]), "--state", str(S["uploads_state"]), as_app=True)
    result = json.loads(thaw.stdout)
    record("reversal: uploads thaw restores recorded modes with NO content/metadata drift", thaw.returncode == 0 and result["no_drift"], result=result)
    release = barrier_cli(env, "db-release", "--record", str(S["record"]))
    assert release.returncode == 0, release.stderr
    released = json.loads(release.stdout)
    with admin(env) as c:
        state = wb.barrier_state(c, "rehearsal")
    record("reversal: database setting removed", state["setting"] is None, release=released)
    now = cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal"))
    record("reversal: database is byte-identical to its state at barrier time (nothing lost or altered)",
           now["digest"] == S["fp_barrier"]["digest"], differences=cf.diff_fingerprints(S["fp_barrier"], now))
    record("reversal: uploads are byte-identical to their pre-barrier state", not cf.diff_manifests(S["m_pre"], cf.uploads_manifest(env["uploads"])))
    # the API process was NOT restarted: evicted read-only pool connections must be replaced transparently
    r = httpx.post(f"{api}/api/v1/customers", json={"name": "after-release"}, headers=S["token"])
    record("reversal: API mutation works again with no restart", r.status_code == 201, status=r.status_code)
    r = httpx.post(f"{api}/api/v1/documents?customer_id={S['customer_id']}",
                   files={"file": ("again.pdf", io.BytesIO(pdf(7)), "application/pdf")}, headers=S["token"])
    record("reversal: uploads work again", r.status_code == 201, status=r.status_code)
    for role in ("simo_super", "simo_limited"):
        with wb.app_connect(env["dsn"](role, "rehearsal")) as c:
            c.execute("INSERT INTO barrier_probe(note) VALUES ('post-release')")
    again = barrier_cli(env, "db-release", "--record", str(S["record"]))
    record("reversal: a second release is a safe no-op", again.returncode == 0 and json.loads(again.stdout).get("already_released"))


# ------------------------------------------------ 8 edge cases on database B
def test_08_fence_override_attempts_and_recovery_on_second_database(env):
    import psycopg
    dsn_admin, dsn_app = env["dsn"]("simo_admin", "rehearsal_b"), env["dsn"]("simo_super", "rehearsal_b")  # superuser: worst case
    rec, rec2 = env["private"] / "b-barrier.json", env["private"] / "b-barrier-2.json"
    common = ["--expect-system-identifier", env["system_id"]]
    # (a) an in-flight write is never killed; an undrained barrier is releasable
    pending = psycopg.connect(dsn_app, application_name="pending-writer")
    pending.execute("INSERT INTO barrier_probe(note) VALUES ('uncommitted at engage')")  # open transaction
    refused = barrier_cli(env, "db-engage", "--record", str(env["private"] / "b-default.json"), "--confirm-environment", "local",
                          *common, "--quiet-seconds", "2", database="rehearsal_b")
    with admin(env, "rehearsal_b") as c:
        untouched = wb.barrier_state(c, "rehearsal_b")
    record("refusal: default engage refuses while a transaction is open (exit 6) and changes nothing",
           refused.returncode == wb.EXIT_NOT_QUIET and untouched == {"setting": None, "engaged": False, "lock_timeout": None},
           exit=refused.returncode, stderr=refused.stderr[:160])
    slow = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "local", "--allow-busy", *common,
                       "--drain-timeout", "2", database="rehearsal_b")
    record("negative: an undrainable in-flight transaction => DRAIN_TIMEOUT (exit 3)", slow.returncode == wb.EXIT_DRAIN_TIMEOUT, exit=slow.returncode)
    pending.commit()
    with admin(env, "rehearsal_b") as c:
        record("negative: the in-flight transaction was not terminated and committed intact",
               c.execute("SELECT count(*) FROM barrier_probe").fetchone()[0] == 1)
        record("negative: after the timeout the barrier is still engaged (fail closed)", wb.barrier_state(c, "rehearsal_b")["engaged"])
    pending.close()
    retry = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "local", "--allow-busy", *common, database="rehearsal_b")
    record("negative: engaging an already-engaged database is refused", retry.returncode == wb.EXIT_REFUSED, exit=retry.returncode)
    rel = barrier_cli(env, "db-release", "--record", str(rec), database="rehearsal_b")
    with admin(env, "rehearsal_b") as c:
        state = wb.barrier_state(c, "rehearsal_b")
    record("recovery: an undrained barrier is releasable", rel.returncode == 0 and state["setting"] is None and state["lock_timeout"] is None)

    # (b) clean engage, then every way a SUPERUSER session could try to write
    eng = barrier_cli(env, "db-engage", "--record", str(rec2), "--confirm-environment", "local", *common,
                      "--quiet-seconds", "12", database="rehearsal_b")
    assert eng.returncode == 0, eng.stderr
    locked = json.loads(eng.stdout)["locked_tables"]
    fp_before = cf.db_fingerprint(dsn_admin)

    def override(statement, extra=""):
        c = psycopg.connect(dsn_app, autocommit=True, options=f"-c default_transaction_read_only=off -c lock_timeout=1500 {extra}")
        try:
            c.execute(statement)
            return "WRITTEN"
        except psycopg.Error as exc:
            return type(exc).__name__
        finally:
            c.close()

    attempts = {sqltext: override(sqltext) for sqltext in (
        "INSERT INTO barrier_probe(note) VALUES ('rogue')", "UPDATE barrier_probe SET note = 'x'", "DELETE FROM barrier_probe",
        "TRUNCATE barrier_probe", "ALTER TABLE barrier_probe ADD COLUMN z int", "DROP TABLE barrier_probe")}
    attempts["INSERT with lock_timeout=0 (would wait forever)"] = override("INSERT INTO barrier_probe(note) VALUES ('rogue')",
                                                                            "-c lock_timeout=0 -c statement_timeout=1500")
    record("FENCED: a superuser that overrides read-only cannot INSERT, UPDATE, DELETE, TRUNCATE, ALTER or DROP",
           all(v in ("LockNotAvailable", "QueryCanceled") for v in attempts.values()), attempts=attempts, locked_tables=locked)
    record("FENCED: content fingerprint identical after the override attempts", cf.db_fingerprint(dsn_admin)["digest"] == fp_before["digest"])
    probe_cli = barrier_cli(env, "db-probe", "--table", "barrier_probe", "--override-probe", database="rehearsal_b")
    record("monitoring: the non-mutating override probe proves the fence (exit 0)", probe_cli.returncode == 0, out=json.loads(probe_cli.stdout))
    with admin(env, "rehearsal_b") as c:
        cutoff = datetime.fromisoformat(json.loads(rec2.read_text())["cutoff"])
        baseline = wb.sample(c, "rehearsal_b", cutoff)
        record("monitoring: fenced state is clean (locks held, no counters moved)", wb.violations(baseline, baseline, locked) == [], sample={k: baseline[k] for k in ("holder_locks", "table_count")})
        # residual: a NEW object is not covered by locks taken on existing tables
        sneaky = override("CREATE TABLE sneaky(id int)")
        current = wb.sample(c, "rehearsal_b", cutoff)
        found = wb.violations(baseline, current, locked)
        fp_after = cf.db_fingerprint(dsn_admin)
    record("RESIDUAL: an override session can still create a NEW table", sneaky == "WRITTEN")
    record("detection: monitor and fingerprint both flag the new table",
           any("new table" in f for f in found) and fp_after["digest"] != fp_before["digest"], problems=found,
           differences=cf.diff_fingerprints(fp_before, fp_after))
    # holder lost -> detected
    with admin(env, "rehearsal_b") as c:
        c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = %s", (wb.HOLDER_APP,))
        time.sleep(1.0)
        lost = wb.violations(baseline, wb.sample(c, "rehearsal_b", cutoff), locked)
    record("detection: losing the lock holder is reported within one sample", any("holder" in f for f in lost), problems=lost)
    # (c) release refuses another database's record; emergency release works with the record DESTROYED
    wrong = env["private"] / "wrong.json"
    wrong.write_text(json.dumps({"events": [], "database": "someone_else"}))
    wrong_rel = barrier_cli(env, "db-release", "--record", str(wrong), database="rehearsal_b")
    record("negative: release refuses a record that belongs to another database", wrong_rel.returncode == wb.EXIT_REFUSED, exit=wrong_rel.returncode)
    rec2.unlink()
    emergency = barrier_cli(env, "db-release", "--record", str(env["private"] / "none.json"), "--emergency", database="rehearsal_b")
    with admin(env, "rehearsal_b") as c:
        state = wb.barrier_state(c, "rehearsal_b")
        holders = c.execute("SELECT count(*) FROM pg_stat_activity WHERE application_name = %s", (wb.HOLDER_APP,)).fetchone()[0]
        c.execute("DROP TABLE sneaky")
    with psycopg.connect(dsn_app, autocommit=True) as w:
        w.execute("INSERT INTO barrier_probe(note) VALUES ('writable again')")
    record("emergency: release works with the record destroyed, restores writes and leaves no holder",
           emergency.returncode == 0 and state["setting"] is None and state["lock_timeout"] is None and holders == 0)
    # (d) a pre-existing setting of unknown origin is never adopted
    with admin(env, "rehearsal_b") as c:
        c.execute('ALTER DATABASE "rehearsal_b" SET lock_timeout = \'5s\'')
    pre = barrier_cli(env, "db-engage", "--record", str(env["private"] / "pre.json"), "--confirm-environment", "local", *common,
                      "--quiet-seconds", "0", database="rehearsal_b")
    record("negative: a pre-existing lock_timeout of unknown origin is not adopted", pre.returncode == wb.EXIT_REFUSED, exit=pre.returncode)
    with admin(env, "rehearsal_b") as c:
        c.execute('ALTER DATABASE "rehearsal_b" RESET lock_timeout')
    busy_staging = barrier_cli(env, "db-engage", "--record", str(env["private"] / "b3.json"), "--confirm-environment", "staging", "--allow-busy",
                               *common, database="rehearsal_b")
    record("negative: --allow-busy is refused for staging", busy_staging.returncode == wb.EXIT_REFUSED, exit=busy_staging.returncode)


# ----------------------------------------- 9 uploads emergency thaw (owner user)
def test_09_uploads_emergency_thaw(env):
    target = Path(tempfile.mkdtemp(prefix="up-", dir=env["base"]))
    os.chown(target, 10001, 10001)
    script = (
        "import sys, json, pathlib\nsys.path.insert(0, %r)\nimport writer_barrier as wb\n"
        "d = pathlib.Path(%r)\n(d / 'a.bin').write_bytes(b'x')\n(d / 'sub').mkdir()\n(d / 'sub' / 'b.bin').write_bytes(b'y')\n"
        "wb.uploads_freeze(d, pathlib.Path(%r))\n"
        "try:\n    (d / 'c.bin').write_bytes(b'z'); frozen_write = True\nexcept PermissionError:\n    frozen_write = False\n"
        "wb.uploads_thaw(d, None, emergency=True)\n(d / 'c.bin').write_bytes(b'z')\n"
        "print(json.dumps({'write_while_frozen': frozen_write, 'write_after_emergency_thaw': True}))\n"
        % (str(RECOVERY), str(target), str(env["private"] / f"st-{secrets.token_hex(4)}.json"))
    )
    out = subprocess.run(APP + [PYTHON, "-c", script], capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout)
    record("emergency: freeze blocks writes; emergency thaw restores them without a state file",
           result == {"write_while_frozen": False, "write_after_emergency_thaw": True}, result=result)


def test_10_violations_pure_function():
    base = {"barrier": {"engaged": True}, "stale_sessions": [], "counters": {"inserted": 5, "updated": 1, "deleted": 0}}
    assert wb.violations(base, base) == []
    bad = {"barrier": {"engaged": False}, "stale_sessions": [{"pid": 1}], "counters": {"inserted": 6, "updated": 1, "deleted": 0}}
    record("monitor: violation detector flags lifted barrier, stale RW session and write counters", len(wb.violations(base, bad)) == 3)


# =========================================================================== #
# A1 capture rehearsal (local only): success path, restore proof, every STOP.
# =========================================================================== #
import a1_capture as a1  # noqa: E402

A1: dict = {"n": 0}
APP_PREFIX = " ".join(APP)


def a1_args(env, **override):
    A1["n"] += 1
    n = A1["n"]
    out = env["base"] / f"a1-out-{n}"
    out.mkdir(mode=0o700)
    now = datetime.now(a1.timezone.utc).replace(microsecond=0)
    values = {
        "run_id": f"rehearsal-{n}", "operator": "rehearsal-operator", "confirm_environment": "local",
        "window_start": a1.utc(now - a1.timedelta(minutes=1)), "window_end": a1.utc(now + a1.timedelta(minutes=20)),
        "expect_system_identifier": env["system_id"], "barrier_record": A1["record"], "uploads_dir": str(env["uploads"]),
        "remote_prefix": APP_PREFIX, "remote_python": PYTHON, "out_dir": out, "hash_record": env["private"] / f"hash-{n}.txt",
        "provider_backups": "", "pg_dump": f"{PG_BINS[-1]}/pg_dump", "pg_restore": f"{PG_BINS[-1]}/pg_restore", "min_free_multiple": 3.0,
    }
    values.update(override)
    A1["last_out"] = out
    return a1.argparse.Namespace(**values)


def expect_stop(env, monkeypatch, label, needle, hooks=None, **override):
    monkeypatch.setenv(wb.ADMIN_DSN_ENV, env["dsn"]("simo_admin", "rehearsal"))
    args = a1_args(env, **override)
    with pytest.raises(a1.Stop) as caught:
        a1.capture(args, hooks=hooks)
    reason = f"{caught.value.phase}: {caught.value.reason}"
    q = sorted(args.out_dir.glob("quarantine-*"))
    stop_file = json.loads((q[0] / "STOP.json").read_text()) if q else {}
    record(f"STOP: {label}", needle in reason and stop_file.get("capture_verified") is False and not (args.out_dir / "RESULT.json").exists(),
           reason=reason, quarantined=bool(q))
    return args, q


def expect_refused(env, monkeypatch, label, **override):
    monkeypatch.setenv(wb.ADMIN_DSN_ENV, env["dsn"]("simo_admin", "rehearsal"))
    args = a1_args(env, **override)
    with pytest.raises(wb.BarrierError) as caught:
        a1.capture(args)
    record(f"REFUSED: {label}", True, reason=str(caught.value))


def test_11_a1_engage_barrier_for_capture(env, api):
    A1["record"] = env["private"] / "a1-barrier.json"
    done = barrier_cli(env, "db-engage", "--record", str(A1["record"]), "--confirm-environment", "local",
                       "--expect-system-identifier", env["system_id"], "--drain-timeout", "30", "--quiet-seconds", "12")
    assert done.returncode == 0, done.stderr
    A1["fp_start"] = cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal"))
    A1["m_start"] = cf.uploads_manifest(env["uploads"])


def test_12_stop_when_uploads_are_not_frozen(env, monkeypatch):
    expect_stop(env, monkeypatch, "uploads still writable (database barrier alone is not enough)", "not frozen")


def test_13_freeze_uploads_for_capture(env):
    A1["state"] = env["private"] / "a1-uploads-state.json"
    done = barrier_cli(env, "uploads-freeze", "--dir", str(env["uploads"]), "--state", str(A1["state"]), as_app=True)
    assert done.returncode == 0, done.stderr


def test_14_refusals_and_preflight_stops(env, monkeypatch, tmp_path):
    now = datetime.now(a1.timezone.utc).replace(microsecond=0)
    expect_refused(env, monkeypatch, "window longer than 30 minutes",
                   window_start=a1.utc(now), window_end=a1.utc(now + a1.timedelta(minutes=31)))
    expect_stop(env, monkeypatch, "window already expired", "expired",
                window_start=a1.utc(now - a1.timedelta(minutes=40)), window_end=a1.utc(now - a1.timedelta(minutes=10)))
    expect_stop(env, monkeypatch, "window not yet open", "not opened",
                window_start=a1.utc(now + a1.timedelta(minutes=10)), window_end=a1.utc(now + a1.timedelta(minutes=30)))
    expect_stop(env, monkeypatch, "fewer than 2 minutes remain", "less than 2 minutes",
                window_start=a1.utc(now - a1.timedelta(minutes=29)), window_end=a1.utc(now + a1.timedelta(seconds=60)))
    expect_stop(env, monkeypatch, "wrong cluster", "identity", expect_system_identifier="1")
    stale = env["private"] / "released.json"
    stale.write_text(json.dumps({"status": "released", "database": "rehearsal", "events": []}))
    expect_stop(env, monkeypatch, "barrier not recorded as engaged", "not recorded as engaged", barrier_record=stale)
    expect_stop(env, monkeypatch, "insufficient free disk", "insufficient free disk", min_free_multiple=1e9)
    old_dump = tmp_path / "pg_dump"
    old_dump.write_text("#!/bin/sh\necho 'pg_dump (PostgreSQL) 13.0'\n")
    old_dump.chmod(0o755)
    expect_stop(env, monkeypatch, "pg_dump older than the server", "older than the server", pg_dump=str(old_dump))
    expect_stop(env, monkeypatch, "pg_dump missing", "not usable", pg_dump="/nonexistent/pg_dump")
    import psycopg
    open_tx = psycopg.connect(env["dsn"]("simo_super", "rehearsal"), application_name="stray-tx")
    open_tx.execute("SELECT 1")  # idle in transaction
    try:
        expect_stop(env, monkeypatch, "stray idle-in-transaction session", "unexpected active")
    finally:
        open_tx.close()
    for label, bad in (("world-readable output directory", 0o755), ("non-empty output directory", None)):
        monkeypatch.setenv(wb.ADMIN_DSN_ENV, env["dsn"]("simo_admin", "rehearsal"))
        args = a1_args(env)
        if bad:
            args.out_dir.chmod(bad)
        else:
            (args.out_dir / "leftover").write_text("x")
        with pytest.raises(wb.BarrierError):
            a1.capture(args)
        record(f"REFUSED: {label}", True)
    inside = REPO / "a1-out-should-not-exist"
    monkeypatch.setenv(wb.ADMIN_DSN_ENV, env["dsn"]("simo_admin", "rehearsal"))
    args = a1_args(env, out_dir=inside)
    inside.mkdir(mode=0o700, exist_ok=True)
    try:
        with pytest.raises(wb.BarrierError):
            a1.capture(args)
    finally:
        inside.rmdir()
    record("REFUSED: output directory inside the repository", True)


def test_15_a1_capture_success_and_restore_proof(env, monkeypatch):
    monkeypatch.setenv(wb.ADMIN_DSN_ENV, env["dsn"]("simo_admin", "rehearsal"))
    args = a1_args(env)
    result = a1.capture(args)
    out = args.out_dir
    names = sorted(p.name for p in out.iterdir())
    record("A1: capture verified, T0 equals T1, four distinct independently computed hashes",
           result["capture_verified"] and result["t0_equals_t1"] and len(set(result["hashes"].values())) == 4,
           seconds=result["seconds"], files=names)
    lines = [l.split() for l in args.hash_record.read_text().splitlines() if not l.startswith("#")]
    sums = {name: subprocess.run(["sha256sum", str(out / name)], capture_output=True, text=True).stdout.split()[0] for _, name in lines}
    record("A1: out-of-band hash record matches a fresh sha256sum of every artifact", all(h == sums[n] for h, n in lines) and len(lines) == 4)
    record("A1: artifacts are owner-read-only and the working copy of customer files was removed",
           all((out / n).stat().st_mode & 0o777 == 0o400 for n in a1.ARTIFACTS) and not (out / "work").exists())
    corr = json.loads((out / "correlation.json").read_text())
    record("A1: correlation record binds both digests, window, barrier cutoff and scope limits",
           corr["t0"]["db_digest"] == corr["t1"]["db_digest"] and "NOT proven" in corr["scope"] and corr["barrier"]["samples_taken"] >= 1,
           alembic=corr["alembic_version"], uploads=corr["uploads"], rows=corr["t0"]["rows"])
    # restore proof into a throwaway database (LOCAL ONLY; this is not the staging B5 gate)
    with admin(env, "postgres") as c:
        c.execute("CREATE DATABASE rehearsal_c")
    restore = subprocess.run([args_pg_restore(args), "--no-owner", "--exit-on-error", f"--dbname={env['dsn']('simo_admin', 'rehearsal_c')}",
                              str(out / "dump.pgdump")], capture_output=True, text=True)
    restored = cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal_c"))
    record("A1: dump restores into a scratch database with an identical content fingerprint (local rehearsal only)",
           restore.returncode == 0 and restored["digest"] == corr["t0"]["db_digest"],
           differences=cf.diff_fingerprints(cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal")), restored)[:3], stderr=restore.stderr[:200])
    tree = env["base"] / "restored-uploads"
    tree.mkdir()
    with a1.tarfile.open(out / "uploads.tar") as tar:
        tar.extractall(tree, filter="data")
    record("A1: uploads archive extracts to a tree identical to the live manifest",
           not cf.diff_manifests(A1["m_start"], cf.uploads_manifest(tree)))
    record("A1: capture changed neither database nor uploads",
           cf.db_fingerprint(env["dsn"]("simo_admin", "rehearsal"))["digest"] == A1["fp_start"]["digest"]
           and not cf.diff_manifests(A1["m_start"], cf.uploads_manifest(env["uploads"])))


def args_pg_restore(args):
    return args.pg_restore


def test_16_stops_during_capture(env, monkeypatch):
    # (1) a file appears in the frozen uploads (written as root, bypassing the permission barrier)
    intruder = env["uploads"] / "intruder.pdf"

    def add_file():
        intruder.write_bytes(b"%PDF-1.4 intruder")

    try:
        args, q = expect_stop(env, monkeypatch, "an upload appears mid-capture", "do not match the live manifest", hooks={"after_dump": add_file})
        record("STOP: the partial dump was quarantined, not deleted", (q[0] / "dump.pgdump").exists())
    finally:
        intruder.unlink(missing_ok=True)

    # (2) the archive is corrupted before verification
    def corrupt():
        archive = A1["last_out"] / "uploads.tar"
        data = bytearray(archive.read_bytes())
        data[2048] ^= 0xFF
        archive.write_bytes(bytes(data))

    expect_stop(env, monkeypatch, "archive corrupted after creation", "do not match the manifest", hooks={"after_archive": corrupt})

    # (3) the process is interrupted
    expect_stop(env, monkeypatch, "SIGTERM mid-capture", "interrupted",
                hooks={"after_dump": lambda: os.kill(os.getpid(), a1.signal.SIGTERM)})

    # (4) the write fence disappears mid-capture (holder killed): the monitor must stop the run
    def kill_holder():
        with admin(env) as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = %s", (wb.HOLDER_APP,))
        time.sleep(1.8)

    expect_stop(env, monkeypatch, "the write-fence holder is killed mid-capture", "fence lock holder is missing",
                hooks={"after_archive": kill_holder})


def test_17_release_after_capture(env):
    thaw = barrier_cli(env, "uploads-thaw", "--dir", str(env["uploads"]), "--state", str(A1["state"]), as_app=True)
    result = json.loads(thaw.stdout)
    # test 16 deliberately created and removed an "intruder" file as root: thaw must notice exactly that trace and nothing else
    record("reversal after A1: thaw detects the simulated intruder's directory change and no content drift",
           result["drift"] == [".: directory changed"], result=result)
    release = barrier_cli(env, "db-release", "--record", str(A1["record"]))
    with admin(env) as c:
        record("reversal after A1: database barrier removed", release.returncode == 0 and wb.barrier_state(c, "rehearsal")["setting"] is None)
    with wb.app_connect(env["dsn"]("simo_super", "rehearsal")) as c:
        c.execute("INSERT INTO barrier_probe(note) VALUES ('after A1')")
    record("reversal after A1: normal writes work again", True)


def test_18_pure_helpers():
    now = datetime(2026, 11, 9, 10, 0, tzinfo=a1.timezone.utc)
    record("helper: pg_restore listing parser finds TABLE DATA entries",
           a1.table_data_entries("1; 0 1 TABLE DATA public customers u\n2; 0 2 TABLE public x u") == {"public.customers"})
    record("helper: version parser", a1.major("18.6") == 18 and a1.major("16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)") == 16)
    with pytest.raises(wb.BarrierError):
        a1.parse_utc("2026-11-09 10:00")
    with pytest.raises(a1.Stop):
        a1.check_window(now, now + a1.timedelta(minutes=30), now + a1.timedelta(minutes=30), phase="x")
    bad = Path(tempfile.mkdtemp()) / "t.tar"
    with a1.tarfile.open(bad, "w") as t:
        info = a1.tarfile.TarInfo("../escape")
        info.size = 0
        t.addfile(info, io.BytesIO(b""))
    with pytest.raises(a1.Stop):
        a1.extract_tree(bad, bad.parent / "tree")
    record("helper: tar extraction refuses a path-traversal member", True)


def test_19_container_side_commands_work_when_piped_on_stdin(env):
    """How the operator runs them on Railway: `railway ssh -- python3 - <cmd> < script` (nothing is deployed)."""
    target = Path(tempfile.mkdtemp(prefix="piped-", dir=env["base"]))
    os.chown(target, 10001, 10001)
    (target / "f.bin").write_bytes(b"x")
    os.chown(target / "f.bin", 10001, 10001)
    state = env["private"] / f"piped-{secrets.token_hex(4)}.json"
    barrier_src = (RECOVERY / "writer_barrier.py").read_bytes()
    finger_src = (RECOVERY / "content_fingerprint.py").read_bytes()

    def piped(src, *args):
        return subprocess.run(APP + [PYTHON, "-", *args], input=src, capture_output=True, env={"PATH": os.environ["PATH"]})

    freeze = piped(barrier_src, "uploads-freeze", "--dir", str(target), "--state", str(state))
    probe = piped(barrier_src, "uploads-probe", "--dir", str(target))
    count = json.loads(piped(finger_src, "writable-count", "--dir", str(target)).stdout)
    manifest = json.loads(piped(finger_src, "uploads-manifest", "--dir", str(target)).stdout)
    thaw = piped(barrier_src, "uploads-thaw", "--dir", str(target), "--state", str(state))
    record("operator path: freeze, probe, read-only manifest and thaw all work when piped to `python3 -` as the app user",
           freeze.returncode == 0 and probe.returncode == 0 and count["writable_entries"] == 0
           and manifest["file_count"] == 1 and thaw.returncode == 0,
           exits=[freeze.returncode, probe.returncode, thaw.returncode], stderr=(freeze.stderr + probe.stderr + thaw.stderr).decode()[:200])



# =========================================================================== #
# Barrier v2: refusal under load, dirty engage detection and recovery.
# =========================================================================== #
def test_20_default_engage_refuses_under_load_and_changes_nothing(env, api):
    stop, results = threading.Event(), []

    def hammer(worker):
        n = 0
        while not stop.is_set():
            n += 1
            r = httpx.post(f"{api}/api/v1/customers", json={"name": f"busy-{worker}-{n}"}, headers=S["token"], timeout=15)
            results.append((time.monotonic(), r.status_code))

    workers = [threading.Thread(target=hammer, args=(w,)) for w in range(4)]
    [w.start() for w in workers]
    time.sleep(2)
    refused = barrier_cli(env, "db-engage", "--record", str(env["private"] / "busy.json"), "--confirm-environment", "local",
                          "--expect-system-identifier", env["system_id"], "--quiet-seconds", "5")
    refused_at = time.monotonic()
    time.sleep(1.5)
    stop.set()
    [w.join() for w in workers]
    with admin(env) as c:
        state = wb.barrier_state(c, "rehearsal")
        holders = c.execute("SELECT count(*) FROM pg_stat_activity WHERE application_name = %s", (wb.HOLDER_APP,)).fetchone()[0]
    after = [code for t, code in results if t > refused_at]
    record("refusal: engage under live write load exits 6 (NOT_QUIET), touches nothing, and users are not disturbed",
           refused.returncode == wb.EXIT_NOT_QUIET and "NOT_QUIET" in refused.stderr
           and state == {"setting": None, "engaged": False, "lock_timeout": None} and holders == 0
           and after and all(c == 201 for c in after),
           exit=refused.returncode, writes_after_refusal=len(after), statuses=sorted(set(after)))


def test_21_dirty_engage_is_detected_refused_by_capture_and_recoverable(env, monkeypatch):
    import psycopg
    monkeypatch.setenv(wb.ADMIN_DSN_ENV, env["dsn"]("simo_admin", "rehearsal"))
    time.sleep(12)  # let the previous test's statistics settle: this test needs a genuinely quiet database
    rec = wb.Record.open(env["private"] / "dirty.json")

    def late_write():  # a request that begins just after the quiet check passed
        with psycopg.connect(env["dsn"]("simo_super", "rehearsal"), autocommit=True) as c:
            c.execute("INSERT INTO barrier_probe(note) VALUES ('late write')")

    with wb.admin_connect() as conn:
        with pytest.raises(wb.BarrierError) as caught:
            wb.engage(conn, record=rec, expect_system_identifier=env["system_id"], confirm_environment="local",
                      drain_timeout_s=20, quiet_seconds=3, after_quiet=late_write)
    status = json.loads(rec.path.read_text())["status"]
    record("dirty engage: a write landing between the quiet check and the cutoff is detected (exit 7, status engaged-dirty)",
           caught.value.code == wb.EXIT_DIRTY and status == "engaged-dirty", status=status)
    args = a1_args(env, barrier_record=rec.path)
    with pytest.raises(a1.Stop) as stopped:
        a1.capture(args)
    record("dirty engage: A1 capture refuses a barrier that is not cleanly engaged", "not recorded as engaged" in stopped.value.reason)
    with wb.admin_connect() as conn:
        wb.release(conn, record=wb.Record.open(rec.path))
        state = wb.barrier_state(conn, "rehearsal")
        holders = conn.execute("SELECT count(*) FROM pg_stat_activity WHERE application_name = %s", (wb.HOLDER_APP,)).fetchone()[0]
    record("recovery: a dirty barrier releases cleanly (settings gone, no holder)",
           state == {"setting": None, "engaged": False, "lock_timeout": None} and holders == 0)
    retry = barrier_cli(env, "db-engage", "--record", str(env["private"] / "retry.json"), "--confirm-environment", "local",
                        "--expect-system-identifier", env["system_id"], "--quiet-seconds", "3")
    assert retry.returncode == 0, retry.stderr
    status = json.loads((env["private"] / "retry.json").read_text())
    release = barrier_cli(env, "db-release", "--record", str(env["private"] / "retry.json"))
    record("recovery: after a clean quiet period the retry engages with a verified quiet period and releases again",
           status["status"] == "engaged" and status["quiet_verified"] is True and release.returncode == 0)


def test_22_capture_refuses_busy_engaged_barrier(env, monkeypatch):
    rec = env["private"] / "busy-engaged.json"
    rec.write_text(json.dumps({"status": "engaged", "database": "rehearsal", "busy_engage": True, "quiet_verified": False,
                               "locked_tables": 10, "cutoff": "2026-01-01T00:00:00+00:00", "events": []}))
    with admin(env) as c:
        c.execute('ALTER DATABASE "rehearsal" SET default_transaction_read_only = on')
    try:
        expect_stop(env, monkeypatch, "barrier engaged without a verified quiet period", "without a verified quiet period", barrier_record=rec)
    finally:
        with admin(env) as c:
            c.execute('ALTER DATABASE "rehearsal" RESET default_transaction_read_only')



# =========================================================================== #
# Owner-approval gate: staging mutation is technically impossible without it.
# =========================================================================== #
def approval_file(tmp, **override):
    now = datetime.now(a1.timezone.utc).replace(microsecond=0)
    data = {
        "schema": "geocore-a1-approval/1", "approved_by": "Owner", "approved_at_utc": a1.utc(now - a1.timedelta(days=2)),
        "window_start": a1.utc(now - a1.timedelta(minutes=1)), "window_end": a1.utc(now + a1.timedelta(minutes=25)),
        "operator": "rehearsal-operator", "users_notified_at_utc": a1.utc(now - a1.timedelta(days=1, hours=2)),
        "notification_channel": "email", "private_storage_description": "encrypted ext4 volume",
        "private_storage_approved": True, "private_storage_encryption_attested": True,
        "barrier_operational_procedure_approved": True, "scope_staging_only": True,
        "historical_backups_untouched": True, "production_untouched": True,
    }
    data.update(override)
    path = tmp / f"approval-{secrets.token_hex(3)}.json"
    path.write_text(json.dumps(data))
    return path


def test_23_staging_is_refused_without_a_complete_owner_approval(env, tmp_path):
    common = ["--confirm-environment", "staging", "--expect-system-identifier", env["system_id"], "--quiet-seconds", "0",
              "--operator", "rehearsal-operator"]
    rec = lambda: str(env["private"] / f"gate-{secrets.token_hex(3)}.json")
    now = datetime.now(a1.timezone.utc).replace(microsecond=0)
    cases = {
        "no approval file": [],
        "template (all null)": ["--approval-file", str(REPO / "artifacts/qa/stone-hard-2026-11-05/a1-owner-approval.TEMPLATE.json")],
        "users notified only 2 hours before": ["--approval-file", str(approval_file(
            tmp_path, users_notified_at_utc=a1.utc(now - a1.timedelta(hours=2)), window_start=a1.utc(now + a1.timedelta(hours=1)),
            window_end=a1.utc(now + a1.timedelta(hours=1, minutes=30))))],
        "window not open yet": ["--approval-file", str(approval_file(
            tmp_path, window_start=a1.utc(now + a1.timedelta(days=2)), window_end=a1.utc(now + a1.timedelta(days=2, minutes=30)),
            users_notified_at_utc=a1.utc(now - a1.timedelta(hours=1))))],
        "window longer than 30 minutes": ["--approval-file", str(approval_file(tmp_path, window_end=a1.utc(now + a1.timedelta(minutes=45))))],
        "private storage not approved": ["--approval-file", str(approval_file(tmp_path, private_storage_approved=False))],
        "barrier procedure not approved": ["--approval-file", str(approval_file(tmp_path, barrier_operational_procedure_approved=False))],
        "different operator": ["--approval-file", str(approval_file(tmp_path, operator="someone-else"))],
    }
    outcomes = {}
    for label, extra in cases.items():
        done = barrier_cli(env, "db-engage", "--record", rec(), *common, *extra)
        outcomes[label] = done.returncode
    with admin(env) as c:
        untouched = wb.barrier_state(c, "rehearsal") == {"setting": None, "engaged": False, "lock_timeout": None}
    record("approval gate: every incomplete or wrong approval is refused (exit 2) and nothing is changed",
           set(outcomes.values()) == {wb.EXIT_REFUSED} and untouched, outcomes=outcomes)
    # capture is gated the same way
    args = a1_args(env, confirm_environment="staging", approval_file=None)
    with pytest.raises(wb.BarrierError) as caught:
        a1.capture(args)
    record("approval gate: A1 capture on staging is refused without approval", "UNAPPROVED" in str(caught.value))


def test_24_valid_approval_allows_the_gate_to_pass(env, tmp_path):
    good = approval_file(tmp_path)
    rec = env["private"] / "gate-ok.json"
    done = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "staging",
                       "--expect-system-identifier", env["system_id"], "--quiet-seconds", "3", "--operator", "rehearsal-operator",
                       "--approval-file", str(good))
    engaged = done.returncode == 0
    release = barrier_cli(env, "db-release", "--record", str(rec))
    record("approval gate: a complete, in-window, correctly-noticed approval lets the (local rehearsal) engage proceed, and it releases",
           engaged and release.returncode == 0, exit=done.returncode, stderr=done.stderr[:200])



# =========================================================================== #
# Operator preflight, run for real against the local cluster and "container".
# =========================================================================== #
def run_preflight(env, name, *extra):
    out = env["base"] / f"pf-out-{name}"
    out.mkdir(mode=0o700)
    report = env["private"] / f"pf-report-{name}.json"
    cmd = [PYTHON, str(RECOVERY / "operator_preflight.py"), "--out-dir", str(out), "--report", str(report),
           "--uploads-dir", str(env["uploads"]), "--remote-prefix", APP_PREFIX, "--remote-python", PYTHON,
           "--pg-dump", f"{PG_BINS[-1]}/pg_dump", "--pg-restore", f"{PG_BINS[-1]}/pg_restore", "--psql", f"{PG_BINS[-1]}/psql",
           "--attest-encrypted-volume", "--timing-seconds", "4", "--quiet-probe-seconds", "2", *extra]
    e = {"PATH": os.environ["PATH"], wb.ADMIN_DSN_ENV: env["dsn"]("simo_admin", "rehearsal"), wb.APP_DSN_ENV: env["dsn"]("simo_super", "rehearsal")}
    done = subprocess.run(cmd, env=e, capture_output=True, text=True)
    doc = json.loads(report.read_text()) if report.exists() else {}
    return done, doc


def statuses(doc, status):
    return sorted(c["check"] for c in doc.get("checks", []) if c["status"] == status)


def test_25_operator_preflight_blocks_until_approval_and_recovery_evidence_exist(env):
    done, doc = run_preflight(env, "base")
    fails = statuses(doc, "FAIL")
    record("preflight: runs read-only end to end and reports BLOCKED (exit 8) because approval and WAL archiving are absent",
           done.returncode == 8 and doc["verdict"] == "BLOCKED" and fails == ["WAL archiver state", "owner approval file"],
           fails=fails, unverified=statuses(doc, "UNVERIFIED"), warn=statuses(doc, "WARN"))
    by = {c["check"]: c for c in doc["checks"]}
    record("preflight: container checks ran as the non-root app user and measured the transfer",
           by["runs as a non-root user"]["status"] == "PASS" and by["read-only transfer timing"]["status"] in ("PASS", "WARN")
           and by["uploads directory owned by the running user"]["status"] == "PASS",
           transfer=by["read-only transfer timing"]["detail"], container_user=by["runs as a non-root user"]["detail"])
    record("preflight: database identity is reported for the approval and PITR stays UNVERIFIED without pgBackRest evidence",
           by["identity (record this system identifier in the approval)"]["detail"]["system_identifier"] == env["system_id"]
           and by["pgBackRest base backup + archive continuity"]["status"] == "UNVERIFIED")
    record("preflight: it changed nothing (no barrier setting, no holder, uploads still writable)",
           by["no barrier or lock_timeout already set on the database"]["status"] == "PASS")
    with admin(env) as c:
        record("preflight: database untouched afterwards", wb.barrier_state(c, "rehearsal") == {"setting": None, "engaged": False, "lock_timeout": None})


def test_26_preflight_rejects_a_postgresql_18_server_with_a_16_client(env):
    """The real check_workstation with the real PG16 binaries and a claimed PG18 server (no real PG18 client exists here)."""
    out = env["base"] / "pf-out-pg18"
    out.mkdir(mode=0o700)

    def run(major, name):
        report = env["private"] / f"pf-report-{name}.json"
        done = subprocess.run([PYTHON, str(RECOVERY / "operator_preflight.py"), "--out-dir", str(out), "--report", str(report), "--remote-prefix", "",
                               "--timing-seconds", "0", "--attest-encrypted-volume", "--server-major", str(major),
                               "--pg-dump", f"{PG_BINS[-1]}/pg_dump", "--pg-restore", f"{PG_BINS[-1]}/pg_restore"],
                              capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
        return done, {c["check"]: c for c in json.loads(report.read_text())["checks"]}

    done, by = run(18, "pg18")
    check = by["pg_dump and pg_restore >= server major"]
    record("PG18 rule on the real code path: a PG16 pg_dump/pg_restore against a PG18 server is FAIL (exit 8)",
           check["status"] == "FAIL" and done.returncode == 8 and "install the matching client" in check["detail"], detail=check["detail"],
           note="rule exercised with a real PG16 client; no real PG18 client or server was available here")
    _, by16 = run(16, "pg16")
    record("same code path with a matching major version passes", by16["pg_dump and pg_restore >= server major"]["status"] == "PASS")


def test_27_preflight_accepts_a_valid_approval_and_refuses_unsafe_storage(env, tmp_path):
    good = approval_file(tmp_path)
    done, doc = run_preflight(env, "approved", "--approval-file", str(good))
    by = {c["check"]: c for c in doc["checks"]}
    record("preflight: a valid approval file turns the approval check to PASS", by["owner approval file"]["status"] == "PASS")
    syncd = env["base"] / "OneDrive" / "recovery"
    syncd.mkdir(parents=True, mode=0o700)
    report = env["private"] / "pf-report-sync.json"
    done = subprocess.run([PYTHON, str(RECOVERY / "operator_preflight.py"), "--out-dir", str(syncd), "--report", str(report), "--remote-prefix", "",
                           "--timing-seconds", "0", "--attest-encrypted-volume", "--pg-dump", f"{PG_BINS[-1]}/pg_dump",
                           "--pg-restore", f"{PG_BINS[-1]}/pg_restore"], capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    doc = json.loads(report.read_text()) if report.exists() else {}
    record("preflight: an output directory inside a cloud-synced folder is FAIL",
           any(c["status"] == "FAIL" and "cloud-synced" in str(c["detail"]) for c in doc.get("checks", [])), exit=done.returncode)
    unattested = env["base"] / "pf-out-unattested"
    unattested.mkdir(mode=0o700)
    report2 = env["private"] / "pf-report-unattested.json"
    subprocess.run([PYTHON, str(RECOVERY / "operator_preflight.py"), "--out-dir", str(unattested), "--report", str(report2), "--remote-prefix", "",
                    "--timing-seconds", "0"], capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    doc2 = json.loads(report2.read_text())
    record("preflight: storage encryption is never assumed (FAIL until attested)",
           any(c["check"].startswith("encrypted volume") and c["status"] == "FAIL" for c in doc2["checks"]))
