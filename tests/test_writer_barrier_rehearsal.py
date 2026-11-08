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
    wrong_id = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "staging",
                           "--expect-system-identifier", "0000000000000000000")
    record("negative: wrong cluster system identifier is refused", wrong_id.returncode == wb.EXIT_REFUSED, exit=wrong_id.returncode)
    prod = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "production",
                       "--expect-system-identifier", env["system_id"])
    record("negative: --confirm-environment production is refused", prod.returncode == wb.EXIT_REFUSED, exit=prod.returncode)
    inside = barrier_cli(env, "db-engage", "--record", str(REPO / "barrier-record.json"), "--confirm-environment", "staging",
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
    done = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "staging",
                       "--expect-system-identifier", env["system_id"], "--drain-timeout", "30")
    engaged_at = time.monotonic()
    assert done.returncode == 0, done.stderr
    summary = json.loads(done.stdout)
    time.sleep(2.0)
    stop.set()
    [w.join() for w in workers]
    t_in.join()
    S["record"] = rec
    record("concurrency: engage waited for the in-flight transaction (never killed it)",
           summary["inflight_waited_for"] >= 1 and engaged_at - t0 >= 1.5, drain=summary, seconds=round(engaged_at - t0, 2))
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
           writer.returncode != 0 and "read-only transaction" in writer.stderr, exit=writer.returncode)
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
def test_08_edge_cases_on_second_database(env):
    import psycopg
    dsn_admin, dsn_app = env["dsn"]("simo_admin", "rehearsal_b"), env["dsn"]("simo_super", "rehearsal_b")
    rec = env["private"] / "b-barrier.json"
    # (a) a pending in-flight write is never killed: drain times out, barrier stays engaged, the write still commits
    pending = psycopg.connect(dsn_app, application_name="pending-writer")
    pending.execute("INSERT INTO barrier_probe(note) VALUES ('uncommitted at engage')")  # open transaction
    slow = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "staging",
                       "--expect-system-identifier", env["system_id"], "--drain-timeout", "2", database="rehearsal_b")
    record("negative: an undrainable in-flight transaction => DRAIN_TIMEOUT (exit 3)", slow.returncode == wb.EXIT_DRAIN_TIMEOUT, exit=slow.returncode)
    pending.commit()
    with admin(env, "rehearsal_b") as c:
        record("negative: the in-flight transaction was not terminated and committed intact",
               c.execute("SELECT count(*) FROM barrier_probe").fetchone()[0] == 1)
        record("negative: after the timeout the barrier is still engaged (fail closed)", wb.barrier_state(c, "rehearsal_b")["engaged"])
    pending.close()
    retry = barrier_cli(env, "db-engage", "--record", str(rec), "--confirm-environment", "staging",
                        "--expect-system-identifier", env["system_id"], database="rehearsal_b")
    record("negative: engaging an already-engaged database is refused", retry.returncode == wb.EXIT_REFUSED, exit=retry.returncode)
    # (b) known limit: a session that explicitly overrides the default can still write; the monitor and fingerprint must catch it
    with admin(env, "rehearsal_b") as c:
        cutoff = wb._server_now(c)
        baseline = wb.sample(c, "rehearsal_b", cutoff)
        fp_before = cf.db_fingerprint(dsn_admin)
        with psycopg.connect(dsn_app, autocommit=True, options="-c default_transaction_read_only=off") as rogue:
            rogue.execute("INSERT INTO barrier_probe(note) VALUES ('rogue override')")
        time.sleep(1.5)
        current = wb.sample(c, "rehearsal_b", cutoff)
    found = wb.violations(baseline, current)
    fp_after = cf.db_fingerprint(dsn_admin)
    record("KNOWN LIMIT: an explicit SET ... = off override can still write", True,
           note="default_transaction_read_only is a default, not a lock; the app never overrides it")
    record("detection: the monitor flags the override write", any("inserted" in f for f in found), problems=found)
    record("detection: the content fingerprint flags the override write", fp_before["digest"] != fp_after["digest"],
           differences=cf.diff_fingerprints(fp_before, fp_after))
    # (c) release refuses a record from another cluster/database, and emergency release works with no record
    wrong = env["private"] / "wrong.json"
    wrong.write_text(json.dumps({"events": [], "database": "someone_else"}))
    refused = barrier_cli(env, "db-release", "--record", str(wrong), database="rehearsal_b")
    record("negative: release refuses a record that belongs to another database", refused.returncode == wb.EXIT_REFUSED, exit=refused.returncode)
    emergency = barrier_cli(env, "db-release", "--record", str(env["private"] / "none.json"), "--emergency", database="rehearsal_b")
    with admin(env, "rehearsal_b") as c:
        record("emergency: release works without the original record", emergency.returncode == 0 and wb.barrier_state(c, "rehearsal_b")["setting"] is None)
    # (d) a pre-existing setting of unknown origin is never overwritten
    with admin(env, "rehearsal_b") as c:
        c.execute('ALTER DATABASE "rehearsal_b" SET default_transaction_read_only = on')
    pre = barrier_cli(env, "db-engage", "--record", str(env["private"] / "pre.json"), "--confirm-environment", "staging",
                      "--expect-system-identifier", env["system_id"], database="rehearsal_b")
    record("negative: a pre-existing read-only setting of unknown origin is not adopted", pre.returncode == wb.EXIT_REFUSED, exit=pre.returncode)
    with admin(env, "rehearsal_b") as c:
        c.execute('ALTER DATABASE "rehearsal_b" RESET default_transaction_read_only')


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
