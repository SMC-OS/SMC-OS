"""Bounded, measured capacity test against the ISOLATED QA API (synthetic data only).

First-commercial-cohort model: ~10 workspaces x ~3 concurrent staff = 30 concurrent users at the top step, doing a
realistic mix (85% reads: dashboard/list/detail, 15% writes: customer + quote creation). Steps: 5, 15, 30 virtual
users, each 40 s, think time 0.3-0.8 s. Hard caps: 4,000 requests, 6 minutes. Two workspaces are used (A and B).
Pass criteria (stated before measuring): at 15 VUs p95 <= 1.5 s and 0 errors; at 30 VUs p95 <= 3 s and error rate <= 1%.
Writes the full result to qa-capacity-results.json. No credentials printed.
"""
import json, os, random, statistics, sys, threading, time, urllib.error, urllib.request

API = os.environ["QA_API"].rstrip("/")
LOCAL = API.startswith("http://127.0.0.1:")
if API != "https://geocore-api-qa-acceptance.up.railway.app" and not LOCAL:
    sys.exit("REFUSED: not the isolated QA API host")
V1 = API + "/api/v1"
MAX_REQUESTS, DEADLINE = 4000, time.time() + 360
lock = threading.Lock()
count = {"n": 0}


def req(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if data:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(V1 + path, data=data, method=method, headers=h)
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            resp.read(); code = resp.status
    except urllib.error.HTTPError as e:
        e.read(); code = e.code
    except Exception:
        code = 0
    return code, time.perf_counter() - t


def login(e, p):
    r = urllib.request.Request(V1 + "/auth/login", data=json.dumps({"email": e, "password": p}).encode(), method="POST", headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))["access_token"]


tokens = [login(os.environ["STAGING_OWNER_EMAIL"], os.environ["STAGING_OWNER_PASSWORD"]),
          login(os.environ["STAGING_OTHER_OWNER_EMAIL"], os.environ["STAGING_OTHER_OWNER_PASSWORD"])]
cust = {}
for i, t in enumerate(tokens):
    c, _ = 0, 0
    r = urllib.request.Request(V1 + "/customers", data=json.dumps({"name": f"Capacity customer {i}"}).encode(), method="POST",
                               headers={"Authorization": f"Bearer {t}", "Content-Type": "application/json"})
    cust[i] = json.load(urllib.request.urlopen(r, timeout=30))["id"]

READS = ["/customers", "/projects", "/quotes", "/tasks", "/notifications", "/dashboard/command-centre"]


def worker(step_end, idx, samples):
    rnd = random.Random(idx)
    tok_i = idx % 2
    tok = tokens[tok_i]
    while time.time() < step_end and time.time() < DEADLINE:
        with lock:
            if count["n"] >= MAX_REQUESTS:
                return
            count["n"] += 1
        if rnd.random() < 0.85:
            path = rnd.choice(READS)
            code, dt = req("GET", path, tok)
            kind = "read"
        elif rnd.random() < 0.5:
            code, dt = req("POST", "/customers", tok, {"name": f"Cap {rnd.randrange(10**6)}"})
            kind = "write"
        else:
            code, dt = req("POST", "/quotes", tok, {"customer_id": cust[tok_i], "title": "Capacity quote", "vat_rate": 0.2,
                                                    "lines": [{"line_kind": "labour", "description": "x", "quantity": 1, "unit": "item", "unit_price": 100.0}]})
            kind = "write"
        samples.append((kind, path if kind == "read" else "write", code, dt))
        time.sleep(rnd.uniform(0.3, 0.8))


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p / 100))] if v else None


report, ok_all = [], True
for vus, limits in ((5, None), (15, (1.5, 0.0)), (30, (3.0, 0.01))):
    samples, threads = [], []
    end = time.time() + 40
    for i in range(vus):
        th = threading.Thread(target=worker, args=(end, i, samples)); th.start(); threads.append(th)
    for th in threads:
        th.join()
    lat = [s[3] for s in samples]
    errs = [s for s in samples if not (200 <= s[2] < 300)]
    by_path = {}
    for k, p, c, d in samples:
        by_path.setdefault(p, []).append(d)
    row = {"virtual_users": vus, "requests": len(samples), "errors": len(errs), "error_rate": round(len(errs) / max(1, len(samples)), 4),
           "p50_s": round(pct(lat, 50), 3) if lat else None, "p95_s": round(pct(lat, 95), 3) if lat else None, "p99_s": round(pct(lat, 99), 3) if lat else None,
           "throughput_rps": round(len(samples) / 40, 1), "slowest_p95_by_endpoint": {p: round(pct(v, 95), 3) for p, v in sorted(by_path.items(), key=lambda kv: -pct(kv[1], 95))[:3]},
           "error_codes": sorted({s[2] for s in errs})}
    if limits:
        row["pass"] = bool(lat) and row["p95_s"] <= limits[0] and row["error_rate"] <= limits[1]
        ok_all &= row["pass"]
    report.append(row)
    print(json.dumps(row))
    time.sleep(5)
json.dump({"criteria": "15 VU: p95<=1.5s, 0 errors; 30 VU: p95<=3s, errors<=1%", "steps": report, "total_requests": count["n"]}, open("qa-capacity-results.json", "w"), indent=1)
print("CAPACITY", "PASS" if ok_all else "FAIL")
sys.exit(0 if ok_all else 1)
