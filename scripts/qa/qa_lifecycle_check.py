"""Authenticated lifecycle and cross-tenant check against the ISOLATED QA API (synthetic data only).

Environment: QA_API, STAGING_OWNER_EMAIL/PASSWORD (workspace A), STAGING_OTHER_OWNER_EMAIL/PASSWORD (workspace B).
Refuses any API host other than the isolated QA host. Never prints credentials, tokens or document bytes.
Exit 0 only when every check passed. Results are written to qa-lifecycle-results.json.
"""
import io, json, os, sys, urllib.error, urllib.request, uuid
import re, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


# --- Invoice numbering, draft amendments and portal isolation (synthetic QA fixtures only).
# No actual customer or email addresses; never include a portal bearer token in logs/artifacts.
def header(h, key):
    return next((v for k, v in h.items() if k.lower() == key.lower()), "")


def pdf_reference(h):
    m = re.search(r'filename="([^"]+)\.pdf"', header(h, "Content-Disposition"))
    return m.group(1) if m else None


def create_quote(owner, customer, title):
    data = dict(quote_body, customer_id=customer, title=title)
    s, b, _ = call("POST", "/quotes", owner, data)
    obj = js(b) or {}
    check(f"{title}: quote created", s == 201 and obj.get("id"), s)
    if not obj.get("id"):
        raise RuntimeError("synthetic quote fixture unavailable")
    return obj["id"]


def read_pdf(owner, quote_id):
    status, data, headers = call("GET", f"/quotes/{quote_id}/invoice", owner)
    return status, data, pdf_reference(headers)


def pdf_text(data):
    # Runner installs poppler-utils; parse actual deployed PDF, not a local generator.
    return subprocess.run(["pdftotext", "-layout", "-", "-"], input=data,
                          capture_output=True, check=True, timeout=30).stdout.decode("utf-8", errors="replace")


# The fresh owner fixtures have not downloaded invoices before the lifecycle's initial quote.
s, pdf_a, ref_a = read_pdf(A, qid)
check("A first invoice is Invoice-000001", s == 200 and ref_a == "Invoice-000001", s)
s2, pdf_again, ref_again = read_pdf(A, qid)
check("A invoice reference stable on re-download", s2 == 200 and ref_again == ref_a, s2)
if s == 200 and s2 == 200:
    try:
        text_a = pdf_text(pdf_a)
        check("deployed invoice PDF text includes correct reference and total",
              "Invoice-000001" in text_a and "900.00" in text_a)
        check("deployed invoice PDF text stable on re-download", text_a == pdf_text(pdf_again))
        # Synthetic PDF only; reviewers must inspect layout before claiming visual acceptance.
        Path("qa-pdf-evidence").mkdir(exist_ok=True)
        Path("qa-pdf-evidence/invoice-a.pdf").write_bytes(pdf_a)
    except (OSError, subprocess.SubprocessError):
        check("deployed PDF extraction", False, "pdftotext unavailable or PDF unreadable")

# Workspace B receives an independent first invoice sequence.
s, b, _ = call("POST", "/customers", B, {"name": "QA Workspace B Customer"})
bcid = (js(b) or {}).get("id")
check("B creates own customer", s == 201 and bcid, s)
if not bcid:
    raise RuntimeError("workspace B customer fixture unavailable")
bqid = create_quote(B, bcid, "QA B first invoice")
s, pdf_b, ref_b = read_pdf(B, bqid)
check("B first invoice independently starts Invoice-000001", s == 200 and ref_b == "Invoice-000001", s)

# A fresh quote in A: draft amendment, repeated save and concurrent first downloads.
aqid = create_quote(A, cid, "QA A draft amendment")
amendment = {"title": "QA amended draft", "discount_amount": 75.0}
for attempt in (1, 2):
    s, b, _ = call("PATCH", f"/quotes/{aqid}", A, amendment)
    amended = js(b) or {}
    check(f"draft save {attempt} retains changed title and total", s == 200 and
          amended.get("title") == amendment["title"] and
          abs(float(amended.get("total") or 0) - 870.0) < 0.005, s)
s, b, _ = call("GET", f"/quotes/{aqid}", A)
check("amended draft reopens with stable total", s == 200 and
      abs(float((js(b) or {}).get("total") or 0) - 870.0) < 0.005, s)
with ThreadPoolExecutor(max_workers=3) as pool:
    downloads = list(pool.map(lambda _: read_pdf(A, aqid), range(3)))
check("concurrent first invoice downloads allocate exactly one next reference",
      all(status == 200 and ref == "Invoice-000002" for status, _, ref in downloads))
s, b, _ = call("POST", f"/quotes/{aqid}/approve", A)
check("amended quote approved", s in (200, 201), s)
s, b, _ = call("PATCH", f"/quotes/{aqid}", A, {"title": "Should not replace approved quote"})
check("approved quote cannot be silently amended", s == 409, s)
s, b, _ = call("PATCH", "/tenants/me/profile", A, {"invoice_prefix": "QAInvoice", "invoice_next_number": 41})
check("A sets own invoice prefix and sequence", s == 200 and (js(b) or {}).get("invoice_prefix") == "QAInvoice", s)
aqid2 = create_quote(A, cid, "QA custom invoice reference")
s, _, ref_custom = read_pdf(A, aqid2)
check("A new invoice uses configured reference QAInvoice-000041", s == 200 and ref_custom == "QAInvoice-000041", s)
s, _, ref_original = read_pdf(A, qid)
check("prefix change does not alter an already issued invoice", s == 200 and ref_original == ref_a, s)
s, b, _ = call("GET", "/tenants/me/profile", B)
check("B invoice settings unchanged by A", s == 200 and (js(b) or {}).get("invoice_prefix") == "Invoice"
      and (js(b) or {}).get("invoice_next_number") == 2, s)

# Portal tokens scope to a specific customer (not just tenant). Create another customer within A.
s, b, _ = call("POST", "/customers", A, {"name": "QA Unrelated Customer"})
other_cid = (js(b) or {}).get("id")
check("A creates unrelated same-tenant customer", s == 201 and other_cid, s)
if not other_cid:
    raise RuntimeError("unrelated customer fixture unavailable")
other_qid = create_quote(A, other_cid, "QA unrelated portal quote")
other_payload = b"unrelated synthetic document"
mp, ct = multipart("file", "qa-unrelated.txt", other_payload)
s, b, _ = call("POST", f"/documents?customer_id={other_cid}", A, raw=mp, ctype=ct)
other_did = (js(b) or {}).get("id")
check("A uploads unrelated customer document", s == 201 and other_did, s)

s, b, _ = call("POST", "/portal-links", A, {"customer_id": cid})
link = js(b) or {}
check("A creates scoped active portal link", s == 201 and link.get("status") == "active" and link.get("token"), s)
if not link.get("token") or not link.get("id"):
    raise RuntimeError("portal fixture unavailable")
portal = "/portal-links/token/" + link["token"]
# No tokens in result names or details.
s, b, _ = call("GET", portal)
view = js(b) or {}
check("portal shows intended customer and excludes unrelated quote",
      s == 200 and view.get("status") == "active" and view.get("customer_name") == cust.get("name")
      and qid in {x["id"] for x in view.get("quotes", [])}
      and other_qid not in {x["id"] for x in view.get("quotes", [])}
      and bqid not in {x["id"] for x in view.get("quotes", [])}, s)
s, b, h = call("GET", portal + f"/invoice/{qid}")
check("portal downloads correct invoice with stable reference",
      s == 200 and b.startswith(b"%PDF-") and pdf_reference(h) == ref_a, s)
deny("portal denies invoice for unrelated same-tenant customer", call("GET", portal + f"/invoice/{other_qid}")[0])
deny("portal denies another tenant invoice", call("GET", portal + f"/invoice/{bqid}")[0])
s, b, _ = call("GET", portal + "/documents")
doclist = js(b)
check("portal document list scoped to intended customer", s == 200 and isinstance(doclist, list) and
      did in {d["id"] for d in doclist} and other_did not in {d["id"] for d in doclist}, s)
s, b, _ = call("GET", portal + f"/documents/{did}/download")
check("portal downloads byte-identical intended document", s == 200 and b == payload, s)
if other_did:
    deny("portal denies unrelated same-tenant document", call("GET", portal + f"/documents/{other_did}/download")[0])
deny("B cannot create portal for A customer", call("POST", "/portal-links", B, {"customer_id": cid})[0])
deny("B cannot revoke A portal", call("DELETE", f"/portal-links/{link['id']}", B)[0])
# Spoofed MIME: use genuine synthetic PDF bytes, but declare HTML on upload.
mp, ct = multipart("file", "qa-spoof.pdf", pdf_a, "text/html")
s, b, _ = call("POST", f"/documents?customer_id={cid}", A, raw=mp, ctype=ct)
spoof = js(b) or {}
check("spoofed upload type is server-controlled", s == 201 and spoof.get("content_type") == "application/pdf", s)
if spoof.get("id"):
    s, b, h = call("GET", f"/documents/{spoof['id']}/download", A)
    check("spoofed document served as PDF attachment, nosniff",
          s == 200 and b == pdf_a and header(h, "Content-Type").startswith("application/pdf")
          and "attachment" in header(h, "Content-Disposition") and header(h, "X-Content-Type-Options") == "nosniff", s)
    s, b, h = call("GET", portal + f"/documents/{spoof['id']}/download")
    check("portal also serves spoofed document with safe PDF type",
          s == 200 and b == pdf_a and header(h, "Content-Type").startswith("application/pdf")
          and "attachment" in header(h, "Content-Disposition"), s)
s, b, _ = call("DELETE", f"/portal-links/{link['id']}", A)
check("A revokes portal link", s == 200 and (js(b) or {}).get("status") == "revoked", s)
s, b, _ = call("GET", portal)
revoked = js(b) or {}
check("revoked portal contains no project or quote data", s == 200 and revoked.get("status") == "revoked"
      and revoked.get("projects") == [] and revoked.get("quotes") == [], s)
deny("revoked portal cannot download invoice", call("GET", portal + f"/invoice/{qid}")[0])
deny("revoked portal cannot download document", call("GET", portal + f"/documents/{did}/download")[0])
deny("unknown portal token refused", call("GET", "/portal-links/token/not-a-real-token")[0])
# Expiry requires a separately guarded time/fixture test; revocation is not expiry evidence.

json.dump(results, open("qa-lifecycle-results.json", "w"), indent=1)
failed = [r for r in results if not r["ok"]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
