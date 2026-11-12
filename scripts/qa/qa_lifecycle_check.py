"""Authenticated lifecycle and cross-tenant check against the ISOLATED QA API (synthetic data only).

Environment: QA_API, STAGING_OWNER_EMAIL/PASSWORD (workspace A), STAGING_OTHER_OWNER_EMAIL/PASSWORD (workspace B).
Refuses any API host other than the isolated QA host. Never prints credentials, tokens or document bytes.
Exit 0 only when every check passed. Results are written to qa-lifecycle-results.json.
"""
import io, json, os, sys, urllib.error, urllib.request, uuid

API = os.environ["QA_API"].rstrip("/")
LOCAL_DRY_RUN = API.startswith("http://127.0.0.1:")  # loopback only, for developing this script
if API != "https://geocore-api-qa-acceptance.up.railway.app" and not LOCAL_DRY_RUN:
    sys.exit("REFUSED: not the isolated QA API host")
V1 = API + "/api/v1"
results: list[dict] = []


def call(method, path, token=None, body=None, raw=None, ctype=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Accept": "application/json", **(headers or {})}
    if ctype or body is not None:
        h["Content-Type"] = ctype or "application/json"
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(V1 + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def js(b):
    try:
        return json.loads(b)
    except Exception:
        return None


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:200]})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    return ok


def login(email, pw):
    s, b, _ = call("POST", "/auth/login", body={"email": email, "password": pw})
    j = js(b) or {}
    assert s == 200 and j.get("access_token"), f"login failed ({s})"
    return j["access_token"]


def multipart(field, filename, content, ctype="text/plain"):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


A = login(os.environ["STAGING_OWNER_EMAIL"], os.environ["STAGING_OWNER_PASSWORD"])
B = login(os.environ["STAGING_OTHER_OWNER_EMAIL"], os.environ["STAGING_OTHER_OWNER_PASSWORD"])

# --- workspace A: customer -> project -> quote -> approve -> PDF -> document
s, b, _ = call("POST", "/customers", A, {"name": "QA Lifecycle Customer", "email": "lifecycle@acceptance.invalid", "customer_type": "individual", "postcode": "SW1A 1AA"})
cust = js(b) or {}
check("A creates customer", s == 201 and cust.get("id"), s)
cid = cust.get("id")

s, b, _ = call("POST", "/projects", A, {"name": "QA Lifecycle Kitchen", "customer_id": cid, "project_type": None, "estimated_value": 12000})
proj = js(b) or {}
check("A creates project linked to customer", s == 201 and proj.get("id"), s)
pid = proj.get("id")

quote_body = {"customer_id": cid, "title": "QA lifecycle quote", "vat_rate": 0.2, "discount_amount": 50.0,
              "lines": [{"line_kind": "labour", "description": "Installation", "quantity": 2, "unit": "item", "unit_price": 150.0},
                        {"line_kind": "labour", "description": "Templating", "quantity": 1, "unit": "item", "unit_price": 500.0}]}
s, b, _ = call("POST", "/quotes", A, quote_body)
q = js(b) or {}
check("A creates quote", s == 201 and q.get("id"), f"{s} {b[:120] if s != 201 else ''}")
qid = q.get("id")
if q:
    net, vat, total = q.get("price_before_vat"), q.get("vat"), q.get("total")
    check("quote money: net £750.00 after £50 discount", net is not None and abs(float(net) - 750.0) < 0.005, f"net={net}")
    check("quote money: VAT 20% of net", vat is not None and abs(float(vat) - 150.0) < 0.005, f"vat={vat}")
    check("quote money: total = net + VAT", total is not None and abs(float(total) - 900.0) < 0.005, f"total={total}")
    s2, b2, _ = call("GET", f"/quotes/{qid}", A)
    check("A re-reads quote with identical total (repeat read stable)", s2 == 200 and (js(b2) or {}).get("total") == total, s2)

s, b, _ = call("POST", f"/quotes/{qid}/approve", A) if qid else (0, b"", {})
check("A approves quote", s in (200, 201), s)
s, b, h = call("GET", f"/quotes/{qid}/invoice", A) if qid else (0, b"", {})
check("quote/invoice PDF is a real PDF", s == 200 and b[:5] == b"%PDF-" and len(b) > 1500 and "pdf" in h.get("Content-Type", h.get("content-type", "")).lower(), f"{s} len={len(b)}")

payload = b"QA acceptance document " + uuid.uuid4().hex.encode()
mp, ct = multipart("file", "qa-note.txt", payload)
s, b, _ = call("POST", f"/documents?customer_id={cid}", A, raw=mp, ctype=ct)
doc = js(b) or {}
check("A uploads a document", s == 201 and doc.get("id"), f"{s}")
did = doc.get("id")
s, b, _ = call("GET", f"/documents/{did}/download", A) if did else (0, b"", {})
check("A downloads identical document bytes", s == 200 and b == payload, s)
mp2, ct2 = multipart("file", "evil.exe", b"MZ", "application/octet-stream")
s, b, _ = call("POST", f"/documents?customer_id={cid}", A, raw=mp2, ctype=ct2)
check("disallowed file type (.exe) refused", s == 422, s)

# --- workspace B must see none of A's records
def deny(name, s):
    check(name, s in (403, 404), s)

deny("B cannot read A's customer", call("GET", f"/customers/{cid}", B)[0])
deny("B cannot read A's project", call("GET", f"/projects/{pid}", B)[0])
deny("B cannot read A's quote", call("GET", f"/quotes/{qid}", B)[0])
deny("B cannot download A's quote PDF", call("GET", f"/quotes/{qid}/invoice", B)[0])
deny("B cannot approve A's quote", call("POST", f"/quotes/{qid}/approve", B)[0])
deny("B cannot download A's document", call("GET", f"/documents/{did}/download", B)[0])
mp3, ct3 = multipart("file", "x.txt", b"x")
deny("B cannot upload onto A's customer", call("POST", f"/documents?customer_id={cid}", B, raw=mp3, ctype=ct3)[0])
s, _, _ = call("POST", "/projects", B, {"name": "steal", "customer_id": cid})
check("B cannot create a project on A's customer", s in (403, 404, 422), s)
s, b, _ = call("GET", "/customers", B)
check("B's customer list does not contain A's customer", s == 200 and cid not in json.dumps(js(b)), s)
s, b, _ = call("GET", "/projects", B)
check("B's project list does not contain A's project", s == 200 and pid not in json.dumps(js(b)), s)
s, b, _ = call("GET", "/quotes", B)
check("B's quote list does not contain A's quote", s == 200 and qid not in json.dumps(js(b)), s)

# --- anonymous
for p in (f"/customers/{cid}", f"/projects/{pid}", f"/quotes/{qid}", f"/quotes/{qid}/invoice", f"/documents/{did}/download"):
    check(f"anonymous refused: {p.split('/')[1]}", call("GET", p)[0] in (401, 403))

json.dump(results, open("qa-lifecycle-results.json", "w"), indent=1)
failed = [r for r in results if not r["ok"]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
