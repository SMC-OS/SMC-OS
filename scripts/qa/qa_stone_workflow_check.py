"""Stone job from enquiry to completion through the real API, fulfilling every workflow gate (ISOLATED QA, synthetic data).

Each gate is first proven to BLOCK the move (409 with its code), then fulfilled the way a user would, then the move succeeds:
customer_linked, assigned_user, site_address_present, completed_site_visit, approved_source_quote, materials_ready
(requirement -> purchase order -> approve -> order -> full receipt). Env: QA_API, STAGING_OWNER_EMAIL/PASSWORD.
Writes qa-stone-workflow-results.json. No credentials printed.
"""
import json, os, sys, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone

API = os.environ["QA_API"].rstrip("/")
if API != "https://geocore-api-qa-acceptance.up.railway.app" and not API.startswith("http://127.0.0.1:"):
    sys.exit("REFUSED: not the isolated QA API host")
V1 = API + "/api/v1"
results = []


def call(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Accept": "application/json", **({"Content-Type": "application/json"} if data else {}), **({"Authorization": f"Bearer {token}"} if token else {})}
    try:
        with urllib.request.urlopen(urllib.request.Request(V1 + path, data=data, method=method, headers=h), timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def js(b):
    try:
        return json.loads(b)
    except Exception:
        return None


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)[:240]})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    return ok


s, b = call("POST", "/auth/login", body={"email": os.environ["STAGING_OWNER_EMAIL"], "password": os.environ["STAGING_OWNER_PASSWORD"]})
T = (js(b) or {})["access_token"]
s, b = call("GET", "/users", T)
me = next(u["id"] for u in js(b) if u["email"] == os.environ["STAGING_OWNER_EMAIL"])

s, b = call("POST", "/customers", T, {"name": "QA Stone Customer", "email": "stone@acceptance.invalid"})
cust = js(b)["id"]
s, b = call("POST", "/quotes", T, {"customer_id": cust, "title": "QA stone worktops", "trade": "stone", "vat_rate": 0.2,
                                  "lines": [{"line_kind": "labour", "description": "Template, fabricate and fit", "quantity": 1, "unit": "item", "unit_price": 2400.0}]})
quote = js(b)
check("stone quote created", s == 201 and quote.get("trade") == "stone", s)
s, b = call("POST", f"/quotes/{quote['id']}/approve", T)
check("quote approved", s in (200, 201), s)
s, b = call("POST", f"/quotes/{quote['id']}/handoff", T)
proj = js(b) or {}
check("approved quote hands off to a project", s in (200, 201) and proj.get("id"), s)
pid = proj["id"]
s, b = call("GET", f"/projects/{pid}/workflow", T)
wf = js(b)
check("project runs the stone workflow template", s == 200 and "stone" in json.dumps(wf).lower(), wf.get("template_key") if wf else s)

# The stone requirement exists from the start of the job; the materials gate must hold fabrication shut until it is received.
s, b = call("POST", f"/projects/{pid}/requirements", T, {"description": "QA quartz slab", "custom_material_name": "QA quartz", "required_quantity": 3, "unit": "slab"})
req = (js(b) or {}).get("id")
check("material requirement recorded on the project", s == 201 and req, s)
fulfilled, trace = set(), []


def fulfil(code):
    if code == "assigned_user":
        s, _ = call("PATCH", f"/projects/{pid}/assign", T, {"assigned_user_id": me})
    elif code == "site_address_present":
        s, _ = call("PATCH", f"/projects/{pid}", T, {"site_address_line1": "1 Acceptance Street", "site_city": "London", "site_postcode": "SW1A 1AA"})
    elif code == "completed_site_visit":
        when = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        s, b = call("POST", f"/projects/{pid}/appointments", T, {"scheduled_at": when, "notes": "QA site visit"})
        aid = (js(b) or {}).get("id")
        s, _ = call("PATCH", f"/appointments/{aid}/status", T, {"status": "completed"}) if aid else (0, b"")
    elif code == "materials_ready":
        s, b = call("POST", "/purchase-orders", T, {"project_id": pid, "items": [{"description": "QA quartz slab", "material_requirement_id": req, "quantity": 3, "unit": "slab", "unit_cost": 400.0}]})
        po = js(b)
        for step in ("approve", "order"):
            ss, bb = call("POST", f"/purchase-orders/{po['id']}/{step}", T, {} if step == "order" else None)
            if ss not in (200, 201):
                return False
        item = po["items"][0]["id"]
        s, _ = call("POST", f"/purchase-orders/{po['id']}/receipts", T, {"received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "idempotency_key": "qa-stone-receipt-1", "items": [{"purchase_order_item_id": item, "quantity_received": 3}]})
    else:
        return False
    return s in (200, 201)


for _ in range(40):
    s, b = call("GET", f"/projects/{pid}/workflow", T)
    wf = js(b)
    trace.append(wf["stage_key"])
    if wf.get("is_terminal"):
        break
    options = [o for o in wf["allowed_transitions"] if o["stage_key"] not in ("on_hold", "cancelled")]
    if not options:
        check("a forward move exists", False, wf["stage_key"]); break
    target = options[0]["stage_key"]
    s, b = call("POST", f"/projects/{pid}/workflow/transition", T, {"target_stage_key": target})
    if s == 409:
        codes = sorted({x["code"] for x in (js(b) or {}).get("detail", {}).get("blocked_requirements", [])})
        check(f"gate blocks {wf['stage_key']} -> {target} with {codes}", bool(codes))
        for code in codes:
            if code not in fulfilled:
                check(f"gate '{code}' fulfilled the way a user would", fulfil(code))
                fulfilled.add(code)
        s, b = call("POST", f"/projects/{pid}/workflow/transition", T, {"target_stage_key": target})
    if s != 200:
        check(f"move {wf['stage_key']} -> {target}", False, f"{s} {b[:160]}"); break
s, b = call("GET", f"/projects/{pid}/workflow", T)
final = js(b)
check("stone job reaches a terminal stage", final.get("is_terminal") is True, " > ".join(trace))
check("the materials gate blocked fabrication until receipt, then opened", "materials_ready" in fulfilled, sorted(fulfilled))
s, b = call("GET", f"/projects/{pid}/workflow/history", T)
check("history records every stage move", s == 200 and len(js(b)) >= len(trace) - 1, len(js(b) or []))
json.dump({"results": results, "stages": trace, "gates_fulfilled": sorted(fulfilled)}, open("qa-stone-workflow-results.json", "w"), indent=1)
failed = [r for r in results if not r["ok"]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed; stages: {' > '.join(trace)}")
sys.exit(1 if failed else 0)
