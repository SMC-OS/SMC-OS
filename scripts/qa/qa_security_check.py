"""Deployed security checks against the ISOLATED QA API and web (synthetic data; read-mostly).

Headers, CORS (allowed and disallowed origin), error sanitisation, webhook signature enforcement, brute-force throttle
(on a random NON-EXISTENT e-mail so no real account is ever locked), secret exposure in public documents, unauthenticated
sweep of representative protected routes. Env: QA_API, QA_WEB (https QA hosts only; loopback allowed for a dry run).
Writes qa-security-results.json. Prints no secrets.
"""
import json, os, re, sys, urllib.error, urllib.request, uuid

API, WEB = os.environ["QA_API"].rstrip("/"), os.environ.get("QA_WEB", "").rstrip("/")
LOCAL = API.startswith("http://127.0.0.1:")
if not LOCAL and (API != "https://geocore-api-qa-acceptance.up.railway.app" or WEB != "https://geocore-web-qa-acceptance.up.railway.app"):
    sys.exit("REFUSED: not the isolated QA hosts")
results = []


def req(method, url, headers=None, body=None):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    h = dict(headers or {})
    if data is not None and "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=h), timeout=30) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:200]})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


# ---- API security headers (also on error responses)
for label, path in (("200", "/health"), ("404", "/api/v1/does-not-exist"), ("401", "/api/v1/customers")):
    s, b, h = req("GET", API + path)
    check(f"API {label} response carries nosniff, frame denial, referrer policy, CSP",
          h.get("x-content-type-options") == "nosniff" and h.get("x-frame-options") == "DENY" and "strict-origin" in h.get("referrer-policy", "")
          and "frame-ancestors 'none'" in h.get("content-security-policy", ""), f"{s} {sorted(k for k in h if k.startswith('x-'))}")
if not LOCAL:
    s, b, h = req("GET", API + "/health")
    check("API sends HSTS over HTTPS", "max-age=" in h.get("strict-transport-security", ""))
    s, b, h = req("GET", WEB + "/login")
    check("web sends nosniff, frame denial, referrer policy", h.get("x-content-type-options") == "nosniff" and h.get("x-frame-options") == "DENY" and "referrer-policy" in h, s)
    check("web sends a Content-Security-Policy with frame-ancestors 'none' and no unsafe-eval", "frame-ancestors 'none'" in h.get("content-security-policy", "") and "unsafe-eval" not in h.get("content-security-policy", ""))
    check("web sends HSTS", "max-age=" in h.get("strict-transport-security", ""))
    check("web does not advertise its framework (x-powered-by absent)", "x-powered-by" not in h, h.get("x-powered-by"))

# ---- CORS
if not LOCAL:
    s, b, h = req("OPTIONS", API + "/api/v1/auth/login", {"Origin": WEB, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    check("CORS preflight allows the QA web origin with credentials", h.get("access-control-allow-origin") == WEB and h.get("access-control-allow-credentials") == "true", f"{s} {h.get('access-control-allow-origin')}")
s, b, h = req("OPTIONS", API + "/api/v1/auth/login", {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
check("CORS preflight does not allow an arbitrary origin", h.get("access-control-allow-origin") in (None, ""), h.get("access-control-allow-origin"))
s, b, h = req("POST", API + "/api/v1/auth/login", {"Origin": "https://evil.example"}, {"email": "nobody@acceptance.invalid", "password": "x"})
check("a disallowed origin gets no CORS grant on a real call", h.get("access-control-allow-origin") in (None, ""))
# Valid credentials, hostile origin: the browser-session mode must be refused before any cookie is set.
cred = {"email": os.environ.get("STAGING_OWNER_EMAIL", ""), "password": os.environ.get("STAGING_OWNER_PASSWORD", "")}
if cred["email"]:
    s, b, h = req("POST", API + "/api/v1/auth/login", {"Origin": "https://evil.example", "X-Geocore-Session": "cookie"}, cred)
    check("cookie-session login from a disallowed origin is refused (403), no cookie set", s == 403 and "set-cookie" not in h, s)
    s, b, h = req("POST", API + "/api/v1/auth/login", {"X-Geocore-Session": "cookie"}, cred)
    check("cookie-session login with no Origin header is refused (403)", s == 403 and "set-cookie" not in h, s)

# ---- error sanitisation
for label, method, path, body, hdrs in (("malformed JSON", "POST", "/api/v1/auth/login", b"{not json", {"Content-Type": "application/json"}),
                                        ("wrong types", "POST", "/api/v1/auth/login", {"email": 5, "password": []}, None),
                                        ("bad UUID path", "GET", "/api/v1/customers/not-a-uuid", None, {"Authorization": "Bearer x"})):
    s, b, h = req(method, API + path, hdrs, body)
    text = b.decode("utf-8", "replace")
    check(f"error sanitised: {label}", s in (400, 401, 422) and not re.search(r"Traceback|File \"|sqlalchemy|psycopg|/app/|postgresql://", text), f"{s}")
s, b, h = req("GET", API + "/api/v1/customers", {"Authorization": "Bearer not.a.jwt"})
check("garbage bearer token is a clean 401", s == 401 and b"Traceback" not in b, s)

# ---- webhook security
s, b, h = req("POST", API + "/api/v1/billing/webhook", {"Stripe-Signature": "t=1,v1=deadbeef"}, {"id": "evt_fake", "type": "invoice.paid"})
check("Stripe webhook without a valid signature is never accepted (400/503, not 200)", s in (400, 503), s)
s, b, h = req("POST", API + "/api/v1/billing/webhook", None, {"id": "evt_fake"})
check("Stripe webhook with no signature header is never accepted", s in (400, 503), s)

# ---- secret exposure in public documents
leak = re.compile(rb"(sk_(live|test)_[A-Za-z0-9]{8,}|whsec_[A-Za-z0-9]{8,}|re_[A-Za-z0-9]{20,}|postgres(ql)?(\+\w+)?://[^\s\"']+:[^\s\"']+@|JWT_SECRET)", re.I)
for path in ("/health", "/ready", "/openapi.json"):
    s, b, h = req("GET", API + path)
    check(f"no credential-shaped strings in {path}", not leak.search(b), s)
if not LOCAL:
    s, b, h = req("GET", WEB + "/login")
    check("no credential-shaped strings in the web login HTML", not leak.search(b), s)
    check("web login HTML does not reference a private Railway hostname", b".railway.internal" not in b)
    for m in re.finditer(rb".{0,60}(localhost|127\\.0\\.0\\.1).{0,60}", b):
        print("INFO loopback reference in login HTML:", m.group(0).decode("utf-8", "replace")[:140].replace("\n", " "))
    check("web login HTML has no loopback URL (e.g. social-preview og:image base)", not re.search(rb"https?://(localhost|127\\.0\\.0\\.1)", b))
    check("web login HTML does not point the browser at a loopback API (NEXT_PUBLIC_API_URL)", not re.search(rb"NEXT_PUBLIC_API_URL[^,}]{0,40}(localhost|127\\.0\\.0\\.1)", b))

# ---- unauthenticated sweep of representative protected routes
for p in ("/customers", "/projects", "/quotes", "/tasks", "/users", "/invitations", "/purchase-orders", "/billing/subscription", "/tenants/me/profile", "/documents?customer_id=" + str(uuid.uuid4()), "/privacy/exports"):
    s, b, h = req("GET", API + "/api/v1" + p)
    check(f"anonymous refused: {p.split('?')[0]}", s in (401, 403, 405), s)

# ---- brute-force throttle on a random non-existent e-mail
ghost = f"ghost-{uuid.uuid4().hex[:10]}@acceptance.invalid"
codes = [req("POST", API + "/api/v1/auth/login", None, {"email": ghost, "password": "Wrong-Password-1!"})[0] for _ in range(14)]
check("repeated failed logins are throttled (429 appears, no 200)", 429 in codes and 200 not in codes, codes)

json.dump(results, open("qa-security-results.json", "w"), indent=1)
failed = [r for r in results if not r["ok"]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
