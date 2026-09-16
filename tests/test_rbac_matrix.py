"""Sprint 027 (docs/SPRINTS/sprint-027.md §6/§8) — RBAC integration sweep.

Every prior sprint's own test file proves its own module's auth/role gate
correctly (verified in Phase 1/2 discovery). What has never existed is one
test that walks *every* route in `app/api/v1/__init__.py`'s `api_router`
(plus `app/activity/router.py` and `app/notifications/router.py`, mounted
separately in `app/main.py`) and asserts its actual auth requirement
matches what this table says it should be. This is exactly the class of
gap Sprint 026 found once, by hand, on the legacy `GET /dashboard` route
(no `require_role`, unlike every sibling route) — this test exists so a
similar gap on a *different* route fails CI instead of waiting for the
next manual audit.

Known, accepted limitation (stated here, not silently glossed over): this
table is hand-authored, not derived from route introspection. A future
route added to `app/api/v1/__init__.py` without a corresponding row here
passes silently. Sprint 027's contract (docs/SPRINTS/sprint-027.md §6.3)
locks this trade-off deliberately: a fully automatic sweep can't
distinguish "should require Owner" from "should require any role" from
route shape alone, without hand-authored intent per route.

Assertion strategy: this test proves the *auth gate*, not full business
correctness (each module's own suite already owns that). A request that
gets past the gate may still legitimately fail downstream with 404
(nonexistent id) or 422 (a deliberately minimal `{}` body) — both are
valid "not 401/403" signals that the gate let the request through, so the
assertions below check membership in {401, 403} rather than requiring a
specific success status.
"""

import uuid

import pytest

from app.auth.service import auth_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Subscription, Tenant, User
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service
from sqlalchemy import delete

RUN_ID = uuid.uuid4().hex[:10]
TENANT_NAME = f"Pytest RBAC Matrix Tenant {RUN_ID}"
OWNER_EMAIL = f"pytest-rbac-matrix-owner-{RUN_ID}@example.invalid"
STAFF_EMAIL = f"pytest-rbac-matrix-staff-{RUN_ID}@example.invalid"
NO_ROLE_EMAIL = f"pytest-rbac-matrix-norole-{RUN_ID}@example.invalid"
PASSWORD = "pytest-rbac-matrix-password-1"

# Auth-requirement categories, matching docs/SPRINTS/sprint-027.md's §2
# journey/coverage matrix exactly.
PUBLIC = "public"  # no auth dependency at all
OPTIONAL_PUBLIC = "optional_public"  # get_current_user_optional — never 401s
AUTHENTICATED = "authenticated"  # get_current_user only — any valid role
OWNER_STAFF = "owner_staff"  # require_role(OWNER, STAFF)
OWNER_ONLY = "owner_only"  # require_role(OWNER)
TOKEN_SCOPED_PUBLIC = "token_scoped_public"  # portal/invitation token routes — no JWT at all

# (method, path template, expected category). Path templates use a
# syntactically-valid but nonexistent UUID/token placeholder — proving the
# gate does not require the resource to actually exist.
_ID = str(uuid.uuid4())
_TOKEN = "nonexistent-token-rbac-matrix"

EXPECTED_ROUTE_AUTH: list[tuple[str, str, str]] = [
    # app/api/v1/core.py
    ("POST", "/api/v1/process", PUBLIC),
    ("POST", "/api/v1/quote", OPTIONAL_PUBLIC),
    ("POST", "/api/v1/estimate", OPTIONAL_PUBLIC),
    ("GET", "/api/v1/dashboard", OWNER_STAFF),
    # app/auth/router.py
    ("POST", "/api/v1/auth/signup", PUBLIC),
    ("POST", "/api/v1/auth/login", PUBLIC),
    ("GET", "/api/v1/auth/me", AUTHENTICATED),
    # app/activity/router.py (mounted separately in app/main.py, /api/v1 prefix)
    ("GET", "/api/v1/activity", AUTHENTICATED),
    ("POST", "/api/v1/activity", AUTHENTICATED),
    # app/notifications/router.py (mounted separately)
    ("GET", "/api/v1/notifications", AUTHENTICATED),
    ("GET", "/api/v1/notifications/unread-count", AUTHENTICATED),
    ("POST", "/api/v1/notifications", AUTHENTICATED),
    ("PATCH", f"/api/v1/notifications/{_ID}/read", AUTHENTICATED),
    # app/billing/router.py
    ("GET", "/api/v1/billing/plans", PUBLIC),
    ("GET", "/api/v1/billing/subscription", OWNER_STAFF),
    ("POST", "/api/v1/billing/checkout", OWNER_ONLY),
    ("POST", "/api/v1/billing/portal", OWNER_ONLY),
    ("POST", "/api/v1/billing/cancel", OWNER_ONLY),
    ("POST", "/api/v1/billing/resume", OWNER_ONLY),
    ("POST", "/api/v1/billing/webhook", PUBLIC),
    # app/customers/router.py
    ("GET", "/api/v1/customers", AUTHENTICATED),
    ("GET", f"/api/v1/customers/{_ID}", AUTHENTICATED),
    ("POST", "/api/v1/customers", AUTHENTICATED),
    # app/tenants/router.py
    ("GET", "/api/v1/tenants", AUTHENTICATED),
    ("GET", f"/api/v1/tenants/{_ID}", AUTHENTICATED),
    ("POST", "/api/v1/tenants", AUTHENTICATED),
    # Sprint 034 — company identity. Read is any authenticated member (the
    # letterhead is not a secret from staff); write is Owner-only because
    # these are the business's statutory details on customer-facing invoices.
    ("GET", "/api/v1/tenants/me/profile", AUTHENTICATED),
    ("PATCH", "/api/v1/tenants/me/profile", OWNER_ONLY),
    # app/projects/router.py
    ("GET", "/api/v1/projects", AUTHENTICATED),
    ("GET", f"/api/v1/projects/{_ID}", AUTHENTICATED),
    ("POST", "/api/v1/projects", AUTHENTICATED),
    ("PATCH", f"/api/v1/projects/{_ID}/status", OWNER_STAFF),
    ("PATCH", f"/api/v1/projects/{_ID}/assign", OWNER_ONLY),
    ("POST", f"/api/v1/projects/{_ID}/convert-to-customer", AUTHENTICATED),
    # app/quotes/router.py
    ("GET", "/api/v1/quotes", AUTHENTICATED),
    ("GET", f"/api/v1/quotes/{_ID}", AUTHENTICATED),
    ("POST", f"/api/v1/quotes/{_ID}/approve", OWNER_STAFF),
    ("POST", f"/api/v1/quotes/{_ID}/handoff", OWNER_STAFF),
    ("GET", f"/api/v1/quotes/{_ID}/invoice", AUTHENTICATED),
    ("POST", "/api/v1/quotes/ai-draft", AUTHENTICATED),
    # app/appointments/router.py
    ("POST", f"/api/v1/projects/{_ID}/appointments", OWNER_STAFF),
    ("GET", f"/api/v1/projects/{_ID}/appointments", OWNER_STAFF),
    ("PATCH", f"/api/v1/appointments/{_ID}/status", OWNER_STAFF),
    # app/documents/router.py
    ("POST", "/api/v1/documents", AUTHENTICATED),
    ("GET", "/api/v1/documents", AUTHENTICATED),
    ("GET", f"/api/v1/documents/{_ID}/download", AUTHENTICATED),
    # app/messages/router.py
    ("POST", "/api/v1/messages", AUTHENTICATED),
    ("GET", "/api/v1/messages", AUTHENTICATED),
    # app/portal/router.py — staff-management routes
    ("POST", "/api/v1/portal-links", AUTHENTICATED),
    ("GET", "/api/v1/portal-links", AUTHENTICATED),
    ("DELETE", f"/api/v1/portal-links/{_ID}", AUTHENTICATED),
    # app/portal/router.py — public token routes
    ("GET", f"/api/v1/portal-links/token/{_TOKEN}", TOKEN_SCOPED_PUBLIC),
    ("GET", f"/api/v1/portal-links/token/{_TOKEN}/invoice/{_ID}", TOKEN_SCOPED_PUBLIC),
    ("GET", f"/api/v1/portal-links/token/{_TOKEN}/documents", TOKEN_SCOPED_PUBLIC),
    (
        "GET",
        f"/api/v1/portal-links/token/{_TOKEN}/documents/{_ID}/download",
        TOKEN_SCOPED_PUBLIC,
    ),
    ("GET", f"/api/v1/portal-links/token/{_TOKEN}/messages", TOKEN_SCOPED_PUBLIC),
    ("POST", f"/api/v1/portal-links/token/{_TOKEN}/messages", TOKEN_SCOPED_PUBLIC),
    # app/invitations/router.py — staff-management routes
    ("POST", "/api/v1/invitations", OWNER_ONLY),
    ("GET", "/api/v1/invitations", OWNER_ONLY),
    ("DELETE", f"/api/v1/invitations/{_ID}", OWNER_ONLY),
    # app/invitations/router.py — public token routes
    ("GET", f"/api/v1/invitations/token/{_TOKEN}", TOKEN_SCOPED_PUBLIC),
    ("POST", f"/api/v1/invitations/token/{_TOKEN}/accept", TOKEN_SCOPED_PUBLIC),
    # app/users/router.py
    ("GET", "/api/v1/users", OWNER_ONLY),
    ("POST", f"/api/v1/users/{_ID}/deactivate", OWNER_ONLY),
    # app/dashboard/router.py
    ("GET", "/api/v1/dashboard/command-centre", OWNER_STAFF),
    # --- Sprint 036 ---
    # app/customers/router.py — editing a customer's address is routine
    # work, the same posture as creating one.
    ("PATCH", f"/api/v1/customers/{_ID}", AUTHENTICATED),
    ("GET", f"/api/v1/customers/{_ID}/context", AUTHENTICATED),
    # app/projects/router.py — details PATCH matches create's posture;
    # status keeps its own separately-gated endpoint.
    ("PATCH", f"/api/v1/projects/{_ID}", AUTHENTICATED),
    # app/quotes/router.py — creating, editing and sending a priced,
    # customer-facing document is Owner/Staff, matching approve/handoff.
    ("POST", "/api/v1/quotes", OWNER_STAFF),
    ("PATCH", f"/api/v1/quotes/{_ID}", OWNER_STAFF),
    ("POST", f"/api/v1/quotes/{_ID}/send", OWNER_STAFF),
    ("POST", f"/api/v1/quotes/{_ID}/send-email", OWNER_STAFF),
    ("GET", "/api/v1/quotes/meta/trades", AUTHENTICATED),
    ("GET", "/api/v1/quotes/meta/units", AUTHENTICATED),
    # app/automations/router.py — reading what the system will do to your
    # work is not a privilege; authoring a workspace-wide rule that
    # creates work for other people is Owner-only, the same class as team
    # management and billing.
    ("GET", "/api/v1/automations", AUTHENTICATED),
    ("GET", f"/api/v1/automations/{_ID}", AUTHENTICATED),
    ("GET", "/api/v1/automations/meta", AUTHENTICATED),
    ("GET", "/api/v1/automations/templates", AUTHENTICATED),
    ("GET", "/api/v1/automations/runs", AUTHENTICATED),
    ("POST", "/api/v1/automations", OWNER_ONLY),
    ("POST", "/api/v1/automations/templates", OWNER_ONLY),
    ("PATCH", f"/api/v1/automations/{_ID}", OWNER_ONLY),
    ("DELETE", f"/api/v1/automations/{_ID}", OWNER_ONLY),
    # app/tasks/router.py — day-to-day work, same posture as customers.
    ("GET", "/api/v1/tasks", AUTHENTICATED),
    ("POST", "/api/v1/tasks", AUTHENTICATED),
    ("PATCH", f"/api/v1/tasks/{_ID}/status", AUTHENTICATED),
    # app/communications/router.py (Sprint 038) — history is read-only,
    # day-to-day work, same posture as tasks/calendar.
    ("GET", "/api/v1/communications", AUTHENTICATED),
    # Public — Resend/Svix authenticates via signature, not a bearer
    # token, same shape as the Stripe webhook above.
    ("POST", "/api/v1/communications/webhook", PUBLIC),
    # app/calendar/router.py — read-only, any member.
    ("GET", "/api/v1/calendar", AUTHENTICATED),
    # app/ai/router.py — no write capability to gate; the service has no
    # tools and cannot modify a record.
    ("GET", "/api/v1/ai/capabilities", AUTHENTICATED),
    ("POST", "/api/v1/ai/chat", AUTHENTICATED),
    # app/tenants/router.py — the workspace's own setup and branding.
    # Reading is any member; writing is Owner-only, same reasoning as
    # company identity above (a logo appears on every customer-facing
    # document this business issues).
    ("GET", "/api/v1/tenants/me/onboarding", AUTHENTICATED),
    ("PATCH", "/api/v1/tenants/me/onboarding", OWNER_ONLY),
    ("GET", "/api/v1/tenants/me/logo", AUTHENTICATED),
    ("POST", "/api/v1/tenants/me/logo", OWNER_ONLY),
    ("DELETE", "/api/v1/tenants/me/logo", OWNER_ONLY),
]


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(Customer).where(Customer.tenant_id == tenant.id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.execute(
            delete(User).where(User.email.in_([OWNER_EMAIL, STAFF_EMAIL, NO_ROLE_EMAIL]))
        )
        db.execute(delete(Tenant).where(Tenant.name == TENANT_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def rbac_users(request):
    """One tenant with an Owner, a Staff, and a role=None user — the three
    identities every category above needs. Module-scoped: this fixture's
    only job is producing valid bearer tokens, not per-test isolation of
    business data (every request in this file targets a nonexistent
    resource id, so nothing here is mutated by the sweep itself)."""
    _cleanup()
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=TENANT_NAME))
        auth_service.create_user(
            db, tenant_id=tenant.id, name="Owner", email=OWNER_EMAIL, password=PASSWORD, role="Owner"
        )
        auth_service.create_user(
            db, tenant_id=tenant.id, name="Staff", email=STAFF_EMAIL, password=PASSWORD, role="Staff"
        )
        auth_service.create_user(
            db, tenant_id=tenant.id, name="No Role", email=NO_ROLE_EMAIL, password=PASSWORD
        )
    finally:
        db.close()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:

        def _login(email: str) -> dict[str, str]:
            r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert r.status_code == 200, f"fixture login failed for {email}: {r.text}"
            return {"Authorization": f"Bearer {r.json()['access_token']}"}

        headers = {
            "owner": _login(OWNER_EMAIL),
            "staff": _login(STAFF_EMAIL),
            "no_role": _login(NO_ROLE_EMAIL),
        }

    def _teardown():
        _cleanup()

    request.addfinalizer(_teardown)
    return headers


def _call(client, method: str, path: str, headers: dict[str, str] | None = None):
    kwargs = {"headers": headers} if headers else {}
    if method in ("POST", "PATCH"):
        kwargs["json"] = {}
    return client.request(method, path, **kwargs)


@pytest.mark.parametrize("method,path,category", EXPECTED_ROUTE_AUTH)
def test_no_token_matches_expected_category(client, method, path, category):
    response = _call(client, method, path)
    if category in (OWNER_STAFF, OWNER_ONLY, AUTHENTICATED):
        assert response.status_code == 401, (
            f"{method} {path} (expected {category}) allowed a request with no "
            f"token through: got {response.status_code}, expected 401"
        )
    else:
        assert response.status_code != 401, (
            f"{method} {path} (expected {category}) rejected a request with no "
            f"token — it should not require auth at all: got 401"
        )


@pytest.mark.parametrize(
    "method,path,category",
    [row for row in EXPECTED_ROUTE_AUTH if row[2] in (OWNER_STAFF, OWNER_ONLY)],
)
def test_no_role_caller_is_forbidden(client, rbac_users, method, path, category):
    response = _call(client, method, path, rbac_users["no_role"])
    assert response.status_code == 403, (
        f"{method} {path} (expected {category}) let a role=None caller through: "
        f"got {response.status_code}, expected 403"
    )


@pytest.mark.parametrize(
    "method,path,category", [row for row in EXPECTED_ROUTE_AUTH if row[2] == OWNER_ONLY]
)
def test_staff_caller_is_forbidden_on_owner_only_routes(client, rbac_users, method, path, category):
    response = _call(client, method, path, rbac_users["staff"])
    assert response.status_code == 403, (
        f"{method} {path} is Owner-only but let a Staff caller through: "
        f"got {response.status_code}, expected 403"
    )


@pytest.mark.parametrize(
    "method,path,category",
    [row for row in EXPECTED_ROUTE_AUTH if row[2] in (OWNER_STAFF, OWNER_ONLY, AUTHENTICATED)],
)
def test_correctly_privileged_caller_passes_the_gate(client, rbac_users, method, path, category):
    role_key = "staff" if category == AUTHENTICATED else "owner"
    response = _call(client, method, path, rbac_users[role_key])
    assert response.status_code not in (401, 403), (
        f"{method} {path} (expected {category}) rejected a correctly-privileged "
        f"caller at the auth gate: got {response.status_code}"
    )
