"""Deployed Owner/Staff role checks, remaining tenant isolation and workflow completion on ISOLATED QA.

Synthetic data only. Needs QA_API, STAGING_OWNER_* (workspace A owner) and STAGING_OTHER_OWNER_* (workspace B owner).
Writes qa-roles-results.json and qa-owner-decisions.json. Never prints tokens or passwords.
"""
import json, os, sys, urllib.error, urllib.request, uuid

API = os.environ["QA_API"].rstrip("/")
LOCAL = API.startswith("http://127.0.0.1:")
if API != "https://geocore-api-qa-acceptance.up.railway.app" and not LOCAL:
    sys.exit("REFUSED: not the isolated QA API host")
V1 = API + "/api/v1"
results, decisions = [], []


def call(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Accept": "application/json"}
    if data is not None:
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(V1 + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
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


def login(email, pw):
    s, b = call("POST", "/auth/login", body={"email": email, "password": pw})
    j = js(b) or {}
    assert s == 200 and j.get("access_token"), f"login failed ({s})"
    return j["access_token"]


A = login(os.environ["STAGING_OWNER_EMAIL"], os.environ["STAGING_OWNER_PASSWORD"])
B = login(os.environ["STAGING_OTHER_OWNER_EMAIL"], os.environ["STAGING_OTHER_OWNER_PASSWORD"])
run = uuid.uuid4().hex[:8]

# ---- Staff user in workspace A through the real invitation flow
staff_email = f"staff-{run}@acceptance.invalid"
staff_pw = uuid.uuid4().hex + "Aa1!"
s, b = call("POST", "/invitations", A, {"email": staff_email})
inv = js(b) or {}
check("Owner invites a Staff user", s == 201 and inv.get("token"), f"{s} {b[:120] if s != 201 else ''}")
S = None
if inv.get("token"):
    s, b = call("POST", f"/invitations/token/{inv['token']}/accept", None, {"name": "QA Staff", "password": staff_pw})
    check("Staff accepts the invitation", s == 200, s)
    if s == 200:
        S = login(staff_email, staff_pw)
if not S:
    json.dump(results, open("qa-roles-results.json", "w"), indent=1)
    sys.exit("staff fixture unavailable")
s, b = call("GET", "/users", A)
staff_id = next((u["id"] for u in (js(b) or []) if u.get("email") == staff_email), None)
check("Owner sees the Staff user with role staff", staff_id is not None and any(str(u.get("role")).lower() == "staff" for u in (js(b) or []) if u["id"] == staff_id), s)

# ---- every owner-only operation in the reviewed role matrix must refuse Staff on the deployed build
matrix = json.load(open(os.environ.get("ROLE_MATRIX", "tests/data/role_matrix.json")))
ZERO = "00000000-0000-4000-8000-000000000000"
skipped = []
for key, exp in sorted(matrix.items()):
    if exp["staff"] != "forbidden":
        continue
    method, path = key.split(" ", 1)
    path = path.replace("/api/v1", "", 1)
    for p in ("{automation_id}", "{invitation_id}", "{export_id}", "{case_id}", "{project_id}", "{user_id}", "{surface_id}", "{tenant_id}"):
        path = path.replace(p, ZERO)
    s, b = call(method, path, S, {} if method in ("POST", "PUT", "PATCH") else None)
    internal = "/internal/" in path
    check(f"Staff refused: {key}", s in (401, 403) if internal else s == 403, s)

# ---- Staff-allowed financial approvals: record the OBSERVED deployed behaviour for an explicit owner decision
s, b = call("POST", "/customers", A, {"name": "QA Role Customer"})
cust = (js(b) or {}).get("id")
s, b = call("POST", "/projects", A, {"name": "QA Role Project", "customer_id": cust, "project_type": "general_building"})
proj = (js(b) or {}).get("id")
check("Owner creates customer and project for role checks", bool(cust and proj), s)
q = {"customer_id": cust, "title": "QA role quote", "vat_rate": 0.2, "lines": [{"line_kind": "labour", "description": "Work", "quantity": 1, "unit": "item", "unit_price": 1000.0}]}
s, b = call("POST", "/quotes", S, q)
sq = (js(b) or {}).get("id")
check("Staff can create a quote", s == 201 and sq, s)
s, b = call("POST", f"/quotes/{sq}/approve", S) if sq else (0, b"")
decisions.append({"operation": "POST /quotes/{id}/approve", "staff_result": s, "needs_owner_decision": s in (200, 201),
                  "note": "Staff can approve a quote the same Staff user created (a £1,000 quote here); no approval limit or second approver exists."})
check("Staff quote approval behaves as recorded in the role matrix (allowed)", s in (200, 201), s)
s, b = call("POST", f"/projects/{proj}/variations", S, {"title": "QA staff variation", "items": [{"description": "Extra", "quantity": 1, "unit": "item", "unit_price": 250.0}]})
vid = (js(b) or {}).get("id")
check("Staff can create a variation", s == 201 and vid, s)
if vid:
    s, b = call("POST", f"/variations/{vid}/send", S)
    s, b = call("POST", f"/variations/{vid}/approve", S)
    decisions.append({"operation": "POST /variations/{id}/approve", "staff_result": s, "needs_owner_decision": s in (200, 201),
                      "note": "Staff can approve a customer-facing variation; Owner must confirm this is intended."})
    check("Staff variation approval behaves as recorded (allowed)", s in (200, 201, 409), s)
s, b = call("POST", f"/projects/{proj}/costs", S, {"category": "material", "state": "actual", "description": "QA staff cost", "total_cost": 100.0})
decisions.append({"operation": "POST /projects/{id}/costs", "staff_result": s, "needs_owner_decision": s in (200, 201),
                  "note": "Staff can write the project cost ledger (committed/actual cost entries)."})
check("Staff cost-ledger write behaves as recorded (allowed)", s in (200, 201), s)

# ---- customer editing, assignment, task completion
s, b = call("PATCH", f"/customers/{cust}", A, {"name": "QA Role Customer Edited", "phone": "07700900123", "city": "London"})
check("Owner edits customer", s == 200 and (js(b) or {}).get("name") == "QA Role Customer Edited", s)
s, b = call("GET", f"/customers/{cust}", S)
check("Staff sees the edited customer", s == 200 and (js(b) or {}).get("city") == "London", s)
s, b = call("PATCH", f"/projects/{proj}/assign", A, {"assigned_user_id": staff_id})
check("Owner assigns the project to Staff", s == 200 and (js(b) or {}).get("assigned_user_id") == staff_id, s)
s, b = call("PATCH", f"/projects/{proj}", S, {"description": "Edited by staff"})
check("Staff edits the assigned project", s == 200 and (js(b) or {}).get("description") == "Edited by staff", s)
s, b = call("POST", "/tasks", A, {"title": "QA task", "assigned_user_id": staff_id, "source_type": "project", "source_id": proj})
tid = (js(b) or {}).get("id")
check("Owner creates a task assigned to Staff", s == 201 and tid, s)
s, b = call("PATCH", f"/tasks/{tid}/status", S, {"status": "done"}) if tid else (0, b"")
check("Staff completes the task", s == 200 and (js(b) or {}).get("status") == "done", s)
s, b = call("GET", "/tasks?status=done", A)
check("Owner sees the completed task", s == 200 and tid in json.dumps(js(b)), s)

# ---- remaining tenant isolation: workspace A rows that workspace B must never reach
s, b = call("POST", f"/projects/{proj}/costs", A, {"category": "labour", "state": "budgeted", "description": "QA A cost", "total_cost": 500.0})
cost = (js(b) or {}).get("id")
s, b = call("POST", f"/messages?customer_id={cust}", A, {"body": "QA private message"})
msg = (js(b) or {}).get("id")
s, b = call("POST", f"/projects/{proj}/requirements", A, {"description": "QA requirement", "custom_material_name": "QA stone", "required_quantity": 2, "unit": "slab"})
req = (js(b) or {}).get("id")
check("A fixtures: cost, message, requirement, variation exist", bool(cost and msg and req and vid), f"{bool(cost)} {bool(msg)} {bool(req)} {bool(vid)}")


def deny(name, s):
    check(name, s in (403, 404), s)


deny("B cannot read A's project financial summary", call("GET", f"/projects/{proj}/financials/summary", B)[0])
deny("B cannot list A's project costs", call("GET", f"/projects/{proj}/costs", B)[0])
deny("B cannot add a cost to A's project", call("POST", f"/projects/{proj}/costs", B, {"category": "other", "state": "actual", "description": "x", "total_cost": 1.0})[0])
deny("B cannot edit A's cost entry", call("PATCH", f"/projects/{proj}/costs/{cost}", B, {"category": "other", "state": "actual", "description": "x", "total_cost": 1.0})[0])
deny("B cannot delete A's cost entry", call("DELETE", f"/projects/{proj}/costs/{cost}", B)[0])
deny("B cannot list A's customer messages", call("GET", f"/messages?customer_id={cust}", B)[0])
deny("B cannot post a message to A's customer", call("POST", f"/messages?customer_id={cust}", B, {"body": "x"})[0])
deny("B cannot list A's project variations", call("GET", f"/projects/{proj}/variations", B)[0])
deny("B cannot read A's variation", call("GET", f"/variations/{vid}", B)[0])
deny("B cannot approve A's variation", call("POST", f"/variations/{vid}/approve", B)[0])
deny("B cannot read A's variation PDF", call("GET", f"/variations/{vid}/pdf", B)[0])
deny("B cannot list A's material requirements", call("GET", f"/projects/{proj}/requirements", B)[0])
deny("B cannot edit A's requirement", call("PATCH", f"/requirements/{req}", B, {"description": "x"})[0])
deny("B cannot cancel A's requirement", call("POST", f"/requirements/{req}/cancel", B)[0])
deny("B cannot read A's workflow", call("GET", f"/projects/{proj}/workflow", B)[0])
deny("B cannot transition A's workflow", call("POST", f"/projects/{proj}/workflow/transition", B, {"target_stage_key": "x"})[0])
deny("B cannot change A's task", call("PATCH", f"/tasks/{tid}/status", B, {"status": "cancelled"})[0])
s, b = call("GET", "/tasks", B)
check("B's task list excludes A's task", s == 200 and tid not in json.dumps(js(b)), s)
s, b = call("GET", "/purchase-orders", B)
check("B's purchase-order list excludes A's data", s == 200 and proj not in json.dumps(js(b)), s)
s, b = call("GET", "/users", B)
check("B's user list excludes A's staff user", s == 200 and staff_email not in json.dumps(js(b)), s)
s, b = call("GET", "/invitations", B)
check("B cannot see A's invitations", s == 200 and staff_email not in json.dumps(js(b)), s)
for who, tok in (("anonymous", None),):
    for p in (f"/projects/{proj}/costs", f"/messages?customer_id={cust}", f"/projects/{proj}/variations", f"/projects/{proj}/requirements", f"/projects/{proj}/workflow"):
        check(f"{who} refused: {p.split('?')[0].split('/')[-1]}", call("GET", p, tok)[0] in (401, 403))

# ---- full workflow driven stage by stage through the real transition API
wf_trace = []
for step in range(40):
    s, b = call("GET", f"/projects/{proj}/workflow", A)
    wf = js(b) or {}
    if s != 200:
        check("workflow readable", False, s); break
    wf_trace.append(wf.get("stage_key"))
    if wf.get("is_terminal"):
        break
    opts = [o for o in wf.get("allowed_transitions", []) if o["stage_key"] not in ("on_hold", "cancelled")]
    free = [o for o in opts if not o.get("blocked_requirements")]
    if not free:
        blockers = sorted({bl.get("code") for o in opts for bl in o.get("blocked_requirements", [])})
        check(f"workflow can advance from {wf.get('stage_key')}", False, f"blocked by {blockers}")
        break
    s, b = call("POST", f"/projects/{proj}/workflow/transition", A, {"target_stage_key": free[0]["stage_key"]})
    if s != 200:
        check(f"transition to {free[0]['stage_key']}", False, f"{s} {b[:160]}"); break
else:
    check("workflow terminates", False, "no terminal stage in 40 steps")
check("workflow reaches a terminal stage", bool(wf_trace) and (js(call('GET', f'/projects/{proj}/workflow', A)[1]) or {}).get("is_terminal") is True, " > ".join(str(x) for x in wf_trace))
s, b = call("GET", f"/projects/{proj}/workflow/history", A)
check("workflow history recorded every move", s == 200 and len(js(b) or []) >= max(len(wf_trace) - 1, 1), len(js(b) or []))

json.dump(results, open("qa-roles-results.json", "w"), indent=1)
json.dump({"stages_visited": wf_trace, "decisions": decisions}, open("qa-owner-decisions.json", "w"), indent=1)
failed = [r for r in results if not r["ok"]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
print("owner decisions recorded:", json.dumps(decisions)[:600])
sys.exit(1 if failed else 0)
