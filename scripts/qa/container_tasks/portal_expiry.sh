set -u
cd /app && python - <<'PY'
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.database.database import SessionLocal
from app.database.models import Quote, User, PortalLink
from app.portal.service import portal_service

def say(m): print("DRILL|" + m, flush=True)
ok = True
def check(name, good, detail=""):
    global ok
    ok &= bool(good); say(("PASS " if good else "FAIL ") + name + (f" [{detail}]" if detail and not good else ""))

if os.environ.get("RAILWAY_PROJECT_NAME") != "geocore-qa-20261110" or os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "acceptance":
    say("FAILED refused: not the isolated QA environment"); sys.exit(1)
for _ in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2); break
    except Exception:
        time.sleep(2)

def get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/v1" + path, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

db = SessionLocal()
row = None
try:
    q = db.execute(select(Quote).join(User, User.tenant_id == Quote.tenant_id).where(User.email.like("%@acceptance.invalid"), Quote.customer_id.is_not(None)).limit(1)).scalars().first()
    if q is None:
        say("FAILED no synthetic quote available"); sys.exit(1)
    owner = db.execute(select(User).where(User.tenant_id == q.tenant_id).limit(1)).scalars().first()
    row, raw = portal_service.create_link(db, tenant_id=q.tenant_id, created_by_user_id=owner.id, customer_id=q.customer_id)
    s, b = get(f"/portal-links/token/{raw}")
    body = json.loads(b)
    check("active link (positive control) shows the customer's data", s == 200 and body["status"] == "active" and len(body["quotes"]) >= 1, f"{s} {body.get('status')}")
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    s, b = get(f"/portal-links/token/{raw}")
    body = json.loads(b)
    check("expired link reads as expired with no projects or quotes", s == 200 and body["status"] == "expired" and body["projects"] == [] and body["quotes"] == [], f"{s} {body.get('status')}")
    s, _ = get(f"/portal-links/token/{raw}/invoice/{q.id}")
    check("expired link cannot download an invoice", s in (403, 404, 410), s)
    s, _ = get(f"/portal-links/token/{raw}/documents")
    check("expired link lists no documents", s in (403, 404, 410) or s == 200, s)
    if s == 200:
        check("expired link document list is empty", json.loads(get(f"/portal-links/token/{raw}/documents")[1]) == [])
finally:
    try:
        if row is not None:
            db.delete(row); db.commit(); say("synthetic portal link removed")
    finally:
        db.close()
say("DONE" if ok else "FAILED")
sys.exit(0 if ok else 1)
PY
