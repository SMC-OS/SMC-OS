set -u
say() { echo "DRILL|$*"; }
say "whoami=$(id -un) uid=$(id -u)"
say "tmp_free_mb=$(df -m /tmp | awk 'NR==2{print $4}')"
say "upload_dir=${UPLOAD_DIR:-unset} files=$(find "${UPLOAD_DIR:-/nonexistent}" -type f 2>/dev/null | wc -l)"
python - <<'PY'
import os, psycopg
dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
with psycopg.connect(dsn) as c:
    cur = c.cursor()
    cur.execute("show server_version"); print("DRILL|server_version=%s" % cur.fetchone()[0])
    cur.execute("select rolsuper, rolcreatedb from pg_roles where rolname = current_user"); print("DRILL|role_super_createdb=%s" % (cur.fetchone(),))
    cur.execute("select pg_database_size(current_database())/1024/1024"); print("DRILL|db_size_mb=%s" % cur.fetchone()[0])
    cur.execute("select count(*) from tenants"); print("DRILL|tenants=%s" % cur.fetchone()[0])
PY
python -m pip install --user --quiet --no-cache-dir pgserver >/tmp/pip.log 2>&1; say "pip_pgserver_rc=$?"
f=$(find "$HOME/.local" -name pg_dump -type f 2>/dev/null | head -1); say "pg_dump=${f:-none}"
[ -n "$f" ] && say "$("$f" --version)"
say "DONE"
