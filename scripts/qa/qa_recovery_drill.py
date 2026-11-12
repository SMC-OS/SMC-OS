"""Matched database + uploads recovery drill for the ISOLATED QA environment (synthetic data only).

Runs INSIDE the QA API container (private network, non-root), through scripts/qa/container_tasks/drill.sh.
Reuses scripts/recovery: content_fingerprint, matched_bundle, restore_upload_bundle.
  1. PG client of the SAME MAJOR VERSION as the server (downloaded as .deb from apt.postgresql.org, SHA256-verified
     against the signed-index entry's checksum, unpacked without root).
  2. T0 fingerprints (database + uploads) -> pg_dump --format=custom -> matched uploads bundle -> T1 fingerprints.
  3. Restore into a DISPOSABLE database created here (never the active one), uploads into an empty scratch directory.
  4. Compare per-table row counts + content hashes, sequences, alembic revision, every upload file byte-for-byte (SHA-256),
     per-tenant row counts. 5. Drop the disposable database and remove all scratch files. 6. Print timings.
The active database is only READ (pg_dump snapshot and read-only fingerprints). No credential is ever printed.
Every output line starts with "DRILL|".
"""
import gzip, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECOVERY = Path(os.environ.get("RECOVERY_DIR", HERE.parent / "recovery"))
sys.path.insert(0, str(RECOVERY))
import content_fingerprint as cf  # noqa: E402
import matched_bundle  # noqa: E402
import restore_upload_bundle as rub  # noqa: E402

OUT = Path(os.environ.get("DRILL_WORK", "/tmp/qa-drill"))
ok = True


def say(msg):
    print(f"DRILL|{msg}", flush=True)


def check(name, good, detail=""):
    global ok
    ok &= bool(good)
    say(f"{'PASS' if good else 'FAIL'} {name}" + (f" [{detail}]" if detail and not good else ""))


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def dsn_plain():
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql", 1)


def with_dbname(dsn, name):
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    return make_conninfo(**{**conninfo_to_dict(dsn), "dbname": name})


def server_major():
    import psycopg
    with psycopg.connect(dsn_plain()) as c:
        return int(c.execute("show server_version_num").fetchone()[0]) // 10000


def fetch_pg_client(major):
    """Same-major client binaries without root: .deb files from the PGDG index, checksum-verified, unpacked locally."""
    override = os.environ.get("PG_BIN_DIR")
    if override:
        return Path(override), {}
    base = "https://apt.postgresql.org/pub/repos/apt"
    release = "trixie-pgdg"
    try:
        text = open("/etc/os-release").read()
        m = re.search(r"VERSION_CODENAME=(\w+)", text)
        release = f"{m.group(1)}-pgdg" if m else release
    except OSError:
        pass
    arch = "amd64" if os.uname().machine in ("x86_64", "amd64") else "arm64"
    index = gzip.decompress(urllib.request.urlopen(f"{base}/dists/{release}/main/binary-{arch}/Packages.gz", timeout=60).read()).decode()
    stanzas = {}
    for block in index.split("\n\n"):
        f = dict(re.findall(r"^([A-Za-z0-9-]+): (.*)$", block, re.M))
        if f.get("Package") in (f"postgresql-client-{major}", "libpq5"):
            stanzas.setdefault(f["Package"], []).append(f)
    root = OUT / "pgclient"
    root.mkdir(parents=True, exist_ok=True)
    for pkg, items in stanzas.items():
        items = [i for i in items if i["Version"].startswith(f"{major}.")] if pkg == "libpq5" else items
        item = sorted(items, key=lambda i: [int(x) if x.isdigit() else 0 for x in re.split(r"[.+~-]", i["Version"])])[-1]
        data = urllib.request.urlopen(f"{base}/{item['Filename']}", timeout=180).read()
        if hashlib.sha256(data).hexdigest() != item["SHA256"]:
            raise RuntimeError(f"{pkg} checksum mismatch")
        deb = root / f"{pkg}.deb"
        deb.write_bytes(data)
        subprocess.run(["dpkg-deb", "-x", str(deb), str(root / "x")], check=True)
        say(f"client package {pkg} {item['Version']} checksum verified")
    bindir = root / "x" / "usr" / "lib" / "postgresql" / str(major) / "bin"
    libdirs = [str(p) for p in (root / "x").rglob("libpq.so*")]
    libdir = str(Path(libdirs[0]).parent) if libdirs else ""
    return bindir, {"LD_LIBRARY_PATH": libdir}


def run(cmd, env_extra=None, **kw):
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(cmd, env=env, capture_output=True, text=True, **kw)


def tenant_counts(dsn):
    import psycopg
    out = {}
    with psycopg.connect(dsn) as c:
        cols = c.execute("select table_name from information_schema.columns where table_schema='public' and column_name='tenant_id' order by 1").fetchall()
        for (t,) in cols:
            for tid, n in c.execute(f'select tenant_id::text, count(*) from "{t}" group by 1 order by 1').fetchall():
                out[f"{t}:{tid}"] = n
    return out


def main():
    start_all = time.time()
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    dsn = dsn_plain()
    uploads = Path(os.environ.get("UPLOAD_DIR", "/var/lib/simo-os/uploads"))
    major = server_major()
    say(f"server major version {major}")
    bindir, env_extra = fetch_pg_client(major)
    pg_dump, pg_restore = str(bindir / "pg_dump"), str(bindir / "pg_restore")
    ver = run([pg_dump, "--version"], env_extra).stdout.strip()
    check("pg_dump client major version equals server major", ver.split()[-1].split(".")[0] == str(major), ver)

    # ---- T0 + capture
    t0 = cf.db_fingerprint(dsn)
    up0 = cf.uploads_manifest(uploads)
    say(f"T0 database digest {t0['digest'][:16]} tables={t0['table_count']} rows={t0['row_total']} alembic={t0['alembic_version']}")
    say(f"T0 uploads digest {up0['digest'][:16]} files={up0['file_count']} bytes={up0['total_bytes']}")
    dump = OUT / "qa.dump"
    c0 = time.time()
    snapshot_at = utc()
    from psycopg.conninfo import conninfo_to_dict
    p = conninfo_to_dict(dsn)
    penv = {**env_extra, "PGHOST": p["host"], "PGPORT": str(p.get("port", 5432)), "PGUSER": p["user"], "PGPASSWORD": p.get("password", ""), "PGDATABASE": p["dbname"]}
    r = run([pg_dump, "--format=custom", "--no-owner", f"--file={dump}"], penv)
    dump_s = time.time() - c0
    check("pg_dump (custom format, same-major client) succeeded", r.returncode == 0 and dump.exists(), r.stderr.strip()[:160])
    say(f"dump size_bytes={dump.stat().st_size if dump.exists() else 0} seconds={dump_s:.1f}")

    recovery_point = f"qa-drill.t0.{t0['digest'][:16]}"
    archive, manifest = OUT / "uploads.tar", OUT / "uploads.manifest.json"
    b0 = time.time()
    matched_bundle.create_bundle(uploads, archive, manifest, recovery_point, utc())
    say(f"matched uploads bundle created seconds={time.time() - b0:.1f} recovery_point={recovery_point}")
    t1 = cf.db_fingerprint(dsn)
    up1 = cf.uploads_manifest(uploads)
    quiet = not cf.diff_fingerprints(t0, t1) and not cf.diff_manifests(up0, up1)
    say(f"data unchanged between T0 and T1: {quiet}")

    # ---- restore into a disposable database (never the active one) and an empty scratch uploads directory
    import psycopg
    drill_db = f"qa_recovery_drill_{int(time.time())}"
    admin = with_dbname(dsn, "postgres")
    restore_s = None
    try:
        r0 = time.time()
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'CREATE DATABASE "{drill_db}"')
        rr = run([pg_restore, "--no-owner", "--exit-on-error", f"--dbname={drill_db}", str(dump)], {**penv, "PGDATABASE": drill_db})
        check("pg_restore into the disposable database succeeded", rr.returncode == 0, rr.stderr.strip()[:200])
        scratch = OUT / "uploads-restore"
        scratch.mkdir()
        count, archive_digest, rp = rub.restore_bundle(archive, manifest, scratch)
        restore_s = time.time() - r0
        say(f"uploads restored files={count} recovery_point={rp} total_restore_seconds={restore_s:.1f}")
        rdsn = with_dbname(dsn, drill_db)
        rest = cf.db_fingerprint(rdsn)
        problems = cf.diff_fingerprints(t1, rest)
        check("restored database equals the capture: all tables (rows + content hash), sequences, alembic revision", not problems, "; ".join(problems[:3]))
        check("restored alembic revision is the expected head", rest["alembic_version"] == "a5f6b7c8d9e0", rest["alembic_version"])
        check("restored row total equals the source", rest["row_total"] == t1["row_total"], f"{rest['row_total']} vs {t1['row_total']}")
        upr = cf.uploads_manifest(scratch)
        uprob = cf.diff_manifests(up1, upr)
        check("every restored upload is byte-identical (SHA-256, size, path)", not uprob and upr["file_count"] == up1["file_count"], "; ".join(uprob[:3]))
        tc_src, tc_rest = tenant_counts(dsn), tenant_counts(rdsn)
        check("per-tenant row counts identical in the restored database (no cross-tenant leakage)", tc_src == tc_rest and len(tc_src) > 0, f"{len(tc_src)} vs {len(tc_rest)} keys")
        tenants_src = set(k.split(":")[1] for k in tc_src)
        say(f"tenants with data={len(tenants_src)}")
    finally:
        try:
            with psycopg.connect(admin, autocommit=True) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{drill_db}" WITH (FORCE)')
            say("disposable database dropped")
        except Exception as e:  # noqa: BLE001
            check("disposable database dropped", False, str(e)[:120])
        shutil.rmtree(OUT, ignore_errors=True)
        say("scratch files removed")
    say(f"TIMINGS recovery_point={snapshot_at} backup_seconds={dump_s:.1f} restore_seconds={restore_s if restore_s is None else round(restore_s, 1)} total_seconds={time.time() - start_all:.1f}")
    say("NOTE logical dump gives RPO = time since the dump (no PITR/WAL on this QA database); RTO excludes provisioning a new Postgres service")
    say("DONE" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        say(f"FAILED unexpected {type(exc).__name__}: {str(exc)[:160]}")
        sys.exit(1)
