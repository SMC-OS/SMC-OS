# Sprint 015 — Team Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Owner view their team and deactivate a Staff member's access — closing the permission-matrix gap `docs/USER_ROLES.md` names explicitly ("removing a teammate?").

**Architecture:** A new `app/users/` backend module (models/service/router), following the one-module-per-business-concern convention every prior module uses. Soft-deactivation via `users.is_active` (not row deletion — `Invitation.invited_by_user_id`/`PortalLink.created_by_user_id` are `NOT NULL` FKs to `users.id`). `get_current_user` gains an `is_active` check so deactivation takes effect on the deactivated user's very next request. Frontend adds a "Team" card to the existing (non-placeholder) `/settings` page, reusing the `Badge`/list/action-button pattern Sprint 014 established.

**Tech Stack:** FastAPI/SQLAlchemy 2.0 backend (Python 3.12, `.venv`), Next.js 16/React 19 frontend (TypeScript, Tailwind v4, pnpm/Turborepo), pytest, Alembic.

**Spec:** `docs/superpowers/specs/2026-08-15-sprint-015-team-management-design.md`

## Global Constraints

- One additive migration only: `users.is_active BOOLEAN NOT NULL DEFAULT true`. No other schema change.
- No reactivation endpoint or UI this sprint (spec §15 — deactivate-only, matches invitations/portal-links precedent).
- A deactivated teammate's portal links keep working — do NOT add any cascade/revoke logic touching `PortalLink` rows (spec §4/§11/§15).
- No "last owner" check distinct from self-deactivation — signup always creates exactly one Owner, invitations only ever create Staff, so no such state can occur (spec §15). Do not build speculative multi-owner handling.
- `docs/ROADMAP.md` must NOT be modified.
- New ADR-031 required in `docs/DECISIONS.md` (spec §16 — unlike Sprint 014, this introduces a genuinely new capability, not just an already-decided convention).
- Sprint 014 (commit `f4b508a`) must not be reopened or modified.
- Do not push to any remote at any point in this plan — commits are local only unless the user separately asks for a push.
- Frontend render-gate lesson from Sprint 014's final review: a list must never be gated on `!error &&` alongside its own non-null/non-empty check — a failed action (e.g. a failed deactivate) must not blank an otherwise-valid list. Follow `apps/web/app/settings/page.tsx`'s existing invitations-list pattern (`{invitations && invitations.length > 0 && (...)}`, no error-gate) for the new Team list too.

---

## Task 1: Database migration — `users.is_active`

**Files:**
- Modify: `app/database/models.py` (`User` class)
- Create: `alembic/versions/<generated>_add_users_is_active.py`

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces: `User.is_active: bool` — consumed by Task 2 (`crud.update_user_active`, `TeamMemberOut.is_active`) and Task 3 (`get_current_user`'s check).

- [ ] **Step 1: Add the column to the model**

In `app/database/models.py`, inside `class User(Base):` (currently ending at `created_at`), add:

```python
    # Sprint 015 (docs/DECISIONS.md ADR-031) — soft-deactivation. An Owner
    # can revoke a teammate's access without deleting the row (Invitation.
    # invited_by_user_id / PortalLink.created_by_user_id are NOT NULL FKs to
    # this table, so deletion would break historical rows). See
    # app/users/service.py and app/auth/dependencies.py's get_current_user.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
```

`Boolean` is already imported at the top of this file (`from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func`) — no new import needed.

- [ ] **Step 2: Generate the migration**

Run: `.venv/Scripts/python.exe -m alembic revision --autogenerate -m "add users is_active"`

Expected: a new file under `alembic/versions/`. Open it and confirm it contains exactly one `op.add_column("users", sa.Column("is_active", sa.Boolean(), server_default=sa.text('true'), nullable=False))` (or equivalent) in `upgrade()`, and a matching `op.drop_column("users", "is_active")` in `downgrade()` — nothing else. If autogenerate detected any other change, stop and report it — that means model/migration drift already existed before this task, which is not this task's job to fix.

- [ ] **Step 3: Round-trip verification**

Run, in order:
```
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic downgrade -1
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

Expected: all four commands succeed with no errors; the final `alembic check` reports "No new upgrade operations detected."

- [ ] **Step 4: Commit**

```bash
git add app/database/models.py alembic/versions/
git commit -m "feat: Sprint 015 - add users.is_active column

Additive-only migration. Soft-deactivation, not row deletion —
Invitation.invited_by_user_id and PortalLink.created_by_user_id are both
NOT NULL FKs to users.id."
```

---

## Task 2: Backend — `app/users/` module (list team, deactivate)

**Files:**
- Modify: `app/database/crud.py`
- Create: `app/users/models.py`
- Create: `app/users/service.py`
- Create: `app/users/router.py`
- Modify: `app/api/v1/__init__.py`
- Modify: `app/activity/models.py`
- Create: `tests/test_users.py`

**Interfaces:**
- Consumes: `User.is_active` (Task 1).
- Produces: `GET /api/v1/users`, `POST /api/v1/users/{id}/deactivate` — consumed by Task 3's test (deactivated-token-401) and Task 4 (frontend `api.getUsers()`/`api.deactivateUser()`). `user_management_service.deactivate_user(db, *, tenant_id, user_id, acting_user_id) -> User` and its exceptions `UserNotFoundError`, `CannotDeactivateSelfError` — Task 3 does not call these directly but must not change their signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_users.py`:

```python
"""Sprint 015 — app/users/ (docs/DECISIONS.md ADR-031).

Covers the full lifecycle through the HTTP layer: listing a tenant's team,
deactivating a Staff member, require_role(OWNER) rejecting a Staff caller,
self-deactivation blocked, cross-tenant isolation, and that a deactivated
teammate's portal links keep resolving (no cascade). The deactivated user's
own existing token actually being rejected is covered separately in this
same file once Task 3 wires that check into get_current_user.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.customers.models import CustomerCreate
from app.customers.service import customer_service
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, PortalLink, Tenant, User
from app.portal.service import portal_service
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

TENANT_NAME = "Pytest Users Tenant"
OWNER_EMAIL = "pytest-users-owner@example.invalid"
STAFF_EMAIL = "pytest-users-staff@example.invalid"
PASSWORD = "correct-horse-battery-staple"


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            # FK-safe order: PortalLink references both Customer and
            # User(created_by_user_id) — delete it before either. Customer
            # and ActivityLog both reference Tenant only. User rows last
            # (PortalLink.created_by_user_id/Invitation.invited_by_user_id
            # reference them), Tenant last of all.
            db.execute(delete(PortalLink).where(PortalLink.tenant_id == tenant.id))
            db.execute(delete(Customer).where(Customer.tenant_id == tenant.id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
        db.execute(delete(User).where(User.email.in_([OWNER_EMAIL, STAFF_EMAIL])))
        db.execute(delete(Tenant).where(Tenant.name == TENANT_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def owner_and_staff():
    """A tenant with a real Owner and a real (non-invited) Staff user —
    same shape as tests/test_invitations.py's fixture of the same name."""
    _cleanup()
    db = SessionLocal()
    try:
        tenant = tenant_service.create(db, TenantCreate(name=TENANT_NAME))
        owner = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Owner", email=OWNER_EMAIL, password=PASSWORD, role="Owner"
        )
        staff = auth_service.create_user(
            db, tenant_id=tenant.id, name="Pytest Staff", email=STAFF_EMAIL, password=PASSWORD, role="Staff"
        )
        yield tenant, owner, staff
    finally:
        db.close()
        _cleanup()


@pytest.fixture()
def owner_headers(client, owner_and_staff):
    r = client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def staff_headers(client, owner_and_staff):
    r = client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_users_returns_owner_and_staff(client, owner_headers, owner_and_staff):
    r = client.get("/api/v1/users", headers=owner_headers)
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert emails == {OWNER_EMAIL, STAFF_EMAIL}
    assert all(u["is_active"] is True for u in r.json())


def test_list_users_requires_owner_role(client, staff_headers):
    r = client.get("/api/v1/users", headers=staff_headers)
    assert r.status_code == 403


def test_deactivate_user_flips_is_active_and_logs_activity(client, owner_headers, owner_and_staff):
    _, _, staff = owner_and_staff
    r = client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    activity = client.get(
        "/api/v1/activity?limit=50&type=team_member_deactivated", headers=owner_headers
    )
    events = activity.json()
    assert any(e["description"] == "Pytest Staff" for e in events)
    assert all(e["title"] == "Team member deactivated" for e in events)


def test_deactivate_activity_not_visible_to_other_tenant(
    client, owner_headers, other_tenant_auth_headers, owner_and_staff
):
    _, _, staff = owner_and_staff
    client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)

    activity = client.get(
        "/api/v1/activity?limit=50&type=team_member_deactivated", headers=other_tenant_auth_headers
    )
    events = activity.json()
    assert not any(e["description"] == "Pytest Staff" for e in events)


def test_deactivate_self_returns_409(client, owner_headers, owner_and_staff):
    _, owner, _ = owner_and_staff
    r = client.post(f"/api/v1/users/{owner.id}/deactivate", headers=owner_headers)
    assert r.status_code == 409


def test_deactivate_unknown_user_returns_404(client, owner_headers):
    r = client.post(f"/api/v1/users/{uuid.uuid4()}/deactivate", headers=owner_headers)
    assert r.status_code == 404


def test_deactivate_cross_tenant_user_returns_404(
    client, owner_headers, other_tenant_auth_headers, owner_and_staff
):
    _, _, staff = owner_and_staff
    r = client.post(f"/api/v1/users/{staff.id}/deactivate", headers=other_tenant_auth_headers)
    assert r.status_code == 404


def test_deactivated_users_portal_links_still_resolve(client, owner_headers, owner_and_staff, db):
    """Deliberate: deactivation does NOT cascade-revoke portal links the
    teammate created (spec §4/§11/§15) — tenant-owned data, not tied to
    who happened to generate the link."""
    tenant, _, staff = owner_and_staff
    customer = customer_service.create(db, CustomerCreate(name="Pytest Users Portal Customer"), tenant.id)
    _, raw_token = portal_service.create_link(
        db, tenant_id=tenant.id, created_by_user_id=staff.id, customer_id=customer.id
    )

    client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)

    r = client.get(f"/api/v1/portal-links/token/{raw_token}")
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_users.py -v`

Expected: every test fails — `/api/v1/users` doesn't exist yet (404 or import error), `app.users` module doesn't exist. This confirms the tests exercise real not-yet-built behavior.

- [ ] **Step 3: Add the `ActivityType` value**

In `app/activity/models.py`, inside `class ActivityType(str, Enum):`, add (after the existing members, e.g. after `PORTAL_LINK_CREATED`):

```python
    TEAM_MEMBER_DEACTIVATED = "team_member_deactivated"
```

- [ ] **Step 4: Add crud helpers**

In `app/database/crud.py`, near the existing `get_user_by_id`/`get_user_by_email`/`count_users` functions, add:

```python
def list_users_by_tenant(db: Session, tenant_id: uuid.UUID) -> list[User]:
    stmt = select(User).where(User.tenant_id == tenant_id).order_by(User.created_at)
    return list(db.scalars(stmt))


def update_user_active(db: Session, user_id: uuid.UUID, is_active: bool) -> User | None:
    row = db.get(User, user_id)
    if row is None:
        return None
    row.is_active = is_active
    db.commit()
    db.refresh(row)
    return row
```

(Mirrors `update_invitation_status`'s exact shape.) No new imports needed — `select`, `Session`, `uuid`, `User` are already imported in this file.

- [ ] **Step 5: Create `app/users/models.py`**

```python
"""Sprint 015 (docs/DECISIONS.md ADR-031) — team management: list a
tenant's users, deactivate a Staff member's access. See app/users/service.py
for the self-deactivation guard and app/auth/dependencies.py's
get_current_user for how is_active is enforced on every later request.

Named TeamMemberOut, not UserOut, to avoid colliding with
app.auth.models.UserOut (the /auth/me response shape) — different response,
different route family.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str | None = None
    is_active: bool
    created_at: datetime
```

- [ ] **Step 6: Create `app/users/service.py`**

```python
"""UserManagementService — Sprint 015 (docs/DECISIONS.md ADR-031).

Second real attachment point for require_role(UserRole.OWNER) after
app/invitations/ (Sprint 011/ADR-028). Deactivation is soft: users.is_active
flips to false rather than deleting the row, since Invitation.
invited_by_user_id and PortalLink.created_by_user_id are both NOT NULL FKs
to users.id — a hard delete would break those historical rows. Matches
Invitation.status/PortalLink.status's established "status field, not row
deletion" pattern.

No "last owner" guard beyond self-deactivation: signup() always creates
exactly one Owner per tenant and invitations only ever create Staff (see
app/auth/service.py, app/invitations/service.py) — there is no code path to
a second Owner today, so "deactivate the tenant's only other Owner" cannot
occur. Not building speculative handling for a state the system cannot
reach.
"""

import uuid

from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import User


class UserNotFoundError(Exception):
    """Unknown id, or an id that belongs to a different tenant. Deliberately
    the same error for both cases — a cross-tenant lookup must never confirm
    another tenant's user exists (ADR-028 precedent)."""


class CannotDeactivateSelfError(Exception):
    """An Owner cannot deactivate their own account through this route."""


class UserManagementService:
    def list_users(self, db: Session, tenant_id: uuid.UUID) -> list[User]:
        return crud.list_users_by_tenant(db, tenant_id)

    def deactivate_user(
        self, db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, acting_user_id: uuid.UUID
    ) -> User:
        if user_id == acting_user_id:
            raise CannotDeactivateSelfError(user_id)
        row = crud.get_user_by_id(db, user_id)
        if row is None or row.tenant_id != tenant_id:
            raise UserNotFoundError(user_id)
        return crud.update_user_active(db, user_id, is_active=False)


user_management_service = UserManagementService()
```

- [ ] **Step 7: Create `app/users/router.py`**

```python
"""Sprint 015 (docs/DECISIONS.md ADR-031). Both routes require
require_role(UserRole.OWNER), applied per-route (same style
app/invitations/router.py uses) rather than a router-level dependency —
this module has no public route, but matching the one existing exemplar
keeps the auth-gating style consistent across the codebase rather than
introducing a second pattern for it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.dependencies import require_role
from app.auth.models import UserRole
from app.database.database import get_db
from app.database.models import User
from app.users.models import TeamMemberOut
from app.users.service import CannotDeactivateSelfError, UserNotFoundError, user_management_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[TeamMemberOut])
def list_users(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    return user_management_service.list_users(db, current_user.tenant_id)


@router.post("/{user_id}/deactivate", response_model=TeamMemberOut)
def deactivate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        row = user_management_service.deactivate_user(
            db, tenant_id=current_user.tenant_id, user_id=user_id, acting_user_id=current_user.id
        )
    except CannotDeactivateSelfError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot deactivate your own account.",
        )
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.TEAM_MEMBER_DEACTIVATED,
            title="Team member deactivated",
            description=row.name,
        ),
        tenant_id=current_user.tenant_id,
    )
    return row
```

- [ ] **Step 8: Mount the router**

In `app/api/v1/__init__.py`, add the import alongside the existing ones (alphabetical order, after `app.tenants.router`):

```python
from app.users.router import router as users_router
```

And add the include after `api_router.include_router(tenants_router)`:

```python
api_router.include_router(users_router)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_users.py -v`

Expected: all 8 tests pass.

- [ ] **Step 10: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `144 passed` (136 existing + 8 new), no failures, no new warnings beyond the pre-existing deprecation warnings.

- [ ] **Step 11: Commit**

```bash
git add app/database/crud.py app/users/ app/api/v1/__init__.py app/activity/models.py tests/test_users.py
git commit -m "feat: Sprint 015 - add team management (list team, deactivate a teammate)

New app/users/ module: GET /api/v1/users, POST /api/v1/users/{id}/deactivate,
both Owner-gated. Soft-deactivation (users.is_active), self-deactivation
blocked, cross-tenant isolation, activity logging on deactivate. Deactivating
a teammate does not cascade-revoke portal links they created — confirmed by
a dedicated test."
```

---

## Task 3: Backend — enforce `is_active` in `get_current_user`

**Files:**
- Modify: `app/auth/dependencies.py`
- Modify: `tests/test_users.py`

**Interfaces:**
- Consumes: `User.is_active` (Task 1), `POST /api/v1/users/{id}/deactivate` (Task 2).
- Produces: nothing consumed by a later task — this is the last backend behavior task.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_users.py`:

```python
def test_deactivated_users_existing_token_is_rejected(
    client, owner_headers, owner_and_staff, staff_headers
):
    """staff_headers logs in (issuing a real, unexpired token) via its own
    fixture before this test body runs — deactivation then happens with
    that token already issued, exercising "an existing session stops
    working," not just "can't log in again.\""""
    _, _, staff = owner_and_staff
    client.post(f"/api/v1/users/{staff.id}/deactivate", headers=owner_headers)

    r = client.get("/api/v1/auth/me", headers=staff_headers)
    assert r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_users.py::test_deactivated_users_existing_token_is_rejected -v`

Expected: FAIL — `assert 200 == 401` (the deactivated user's token still works, since `get_current_user` doesn't check `is_active` yet).

- [ ] **Step 3: Add the check**

In `app/auth/dependencies.py`, in `get_current_user`, change:

```python
    user = crud.get_user_by_id(db, user_uuid)
    if user is None:
        raise credentials_error
    return user
```

to:

```python
    user = crud.get_user_by_id(db, user_uuid)
    if user is None or not user.is_active:
        raise credentials_error
    return user
```

Also add a paragraph to this file's module docstring (after the existing Sprint 012 paragraph), matching the file's established per-sprint changelog-in-docstring convention:

```python
Sprint 015 (docs/DECISIONS.md ADR-031) — get_current_user now also rejects
a token whose user has been deactivated (is_active = False), with the same
generic "Could not validate credentials" 401 — no detail leak distinguishing
"deactivated" from "invalid/expired." This costs no extra query: the row is
already fetched below. The first sprint where another user's action (an
Owner deactivating them) can end a Staff user's already-issued, unexpired
session mid-flight — previously only natural token expiry did.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_users.py::test_deactivated_users_existing_token_is_rejected -v`

Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `145 passed` (144 from Task 2 + 1 new), no failures. Pay particular attention to any test elsewhere in the suite that relies on `get_current_user` succeeding for a freshly-created user — a user created via `auth_service.create_user`/signup must default to `is_active=True` (guaranteed by the migration's `server_default="true"` from Task 1) or every other authenticated test in the suite would start failing.

- [ ] **Step 6: Commit**

```bash
git add app/auth/dependencies.py tests/test_users.py
git commit -m "feat: Sprint 015 - reject deactivated users' tokens in get_current_user

Costs no extra query — the user row is already fetched per-request. Same
generic 401 as an invalid token, no detail leak."
```

---

## Task 4: Frontend — Team card on `/settings`

**Files:**
- Modify: `apps/web/components/auth/AuthProvider.tsx`
- Create: `apps/web/types/user.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/settings/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/users`, `POST /api/v1/users/{id}/deactivate` (Task 2/3).
- Produces: `useAuth().userId: string | null` — a new field on `AuthContextValue`, used by `settings/page.tsx` to hide the Deactivate button on the caller's own row. No other page currently uses this field; adding it must not change any existing consumer of `useAuth()`.

- [ ] **Step 1: Add `userId` to `AuthProvider`**

In `apps/web/components/auth/AuthProvider.tsx`:

Add to the `AuthContextValue` interface (after the existing `role` field):

```typescript
  // Sprint 015 — the signed-in user's own id, used to hide a "manage this
  // person" action on their own row (e.g. the Team list's Deactivate
  // button) — the server enforces the real rule (CannotDeactivateSelfError)
  // regardless of what the UI shows.
  userId: string | null;
```

Add state (after the existing `role` state):

```typescript
  const [userId, setUserId] = useState<string | null>(null);
```

In the mount effect's `.then((me) => { ... })`, add `setUserId(me.id);` alongside the existing `setTenantName`/`setRole` calls.

In `login`, `signup`, and `acceptInvite` — each already has `setTenantName(response.user.tenant_name); setRole(response.user.role);` — add `setUserId(response.user.id);` right after, in all three functions.

In `logout`, add `setUserId(null);` alongside the existing `setTenantName(null); setRole(null);`.

Add `userId` to the context value object passed to `<AuthContext.Provider value={{ ... }}>`.

- [ ] **Step 2: Create `apps/web/types/user.ts`**

```typescript
// Sprint 015 — mirrors app/users/models.py's TeamMemberOut.

export interface TeamMemberOut {
  id: string;
  name: string;
  email: string;
  role: string | null;
  is_active: boolean;
  created_at: string;
}
```

- [ ] **Step 3: Add API client methods**

In `apps/web/lib/api.ts`, add the import at the top alongside the existing type imports:

```typescript
import type { TeamMemberOut } from "@/types/user";
```

Add near the invitation methods (after `revokeInvitation`):

```typescript
  // Sprint 015 — Owner-only (require_role(OWNER) server-side; a Staff
  // caller gets a 403 handled by the caller, same as invitations).
  getUsers: () => request<TeamMemberOut[]>("/users"),

  deactivateUser: (id: string) =>
    request<TeamMemberOut>(`/users/${id}/deactivate`, { method: "POST" }),
```

- [ ] **Step 4: Add the Team card to `/settings`**

In `apps/web/app/settings/page.tsx`:

Add to the imports:

```typescript
import type { TeamMemberOut } from "@/types/user";
```

Destructure `userId` alongside the existing `useAuth()` call: `const { isAuthenticated, isReady, role, userId } = useAuth();`

Add state (alongside the existing `invitations`/`listError` state):

```typescript
  const [teamMembers, setTeamMembers] = useState<TeamMemberOut[] | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [deactivatingId, setDeactivatingId] = useState<string | null>(null);
```

Add a load function (alongside `loadInvitations`):

```typescript
  function loadTeam() {
    api
      .getUsers()
      .then(setTeamMembers)
      .catch((err) =>
        setTeamError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }
```

In the existing `useEffect`, change the `if (isOwner) loadInvitations();` line to also call `loadTeam()`:

```typescript
    if (isOwner) {
      loadInvitations();
      loadTeam();
    }
```

Add a handler (alongside `handleRevoke`):

```typescript
  async function handleDeactivate(id: string) {
    setDeactivatingId(id);
    setTeamError(null);
    try {
      await api.deactivateUser(id);
      loadTeam();
    } catch (err) {
      setTeamError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setDeactivatingId(null);
    }
  }
```

Add a new `<Card>` inside the `{isOwner && (<div className="flex flex-col gap-6">` block — place it as the **first** card, before "Invite a teammate":

```tsx
          <Card>
            <CardHeader>
              <CardTitle>Team</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {teamError && <p className="p-5 text-sm text-danger">{teamError}</p>}
              {teamMembers === null && !teamError && (
                <p className="p-5 text-center text-sm text-muted">Loading…</p>
              )}
              {teamMembers && teamMembers.length > 0 && (
                <ul className="divide-y divide-border">
                  {teamMembers.map((member) => (
                    <li key={member.id} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {member.name}
                        </p>
                        <p className="truncate text-xs text-muted">{member.email}</p>
                      </div>
                      <Badge tone="neutral">{member.role}</Badge>
                      <Badge tone={member.is_active ? "success" : "neutral"}>
                        {member.is_active ? "active" : "inactive"}
                      </Badge>
                      {member.is_active && member.id !== userId && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={deactivatingId === member.id}
                          onClick={() => handleDeactivate(member.id)}
                        >
                          {deactivatingId === member.id ? "Deactivating…" : "Deactivate"}
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
```

Note the list-render condition is `{teamMembers && teamMembers.length > 0 && (...)}` — deliberately **not** gated on `!teamError`, per this plan's Global Constraints (a failed deactivate must not blank the list).

- [ ] **Step 5: Manual trace verification**

Read the resulting file once, tracing three states: (a) initial load succeeds with a non-empty team → list renders, no error banner; (b) `loadTeam()` fails → error banner shows, list stays `null` so nothing else renders; (c) a `handleDeactivate` call fails after a prior successful load → `teamError` is set but `teamMembers` still holds its last-successful value, so the error banner AND the list render together (matches the Global Constraints note). Confirm all three hold from reading the code — there is no dedicated frontend test file for this page (pre-existing gap, not this task's to fix).

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/auth/AuthProvider.tsx apps/web/types/user.ts apps/web/lib/api.ts apps/web/app/settings/page.tsx
git commit -m "feat: Sprint 015 - add Team card to /settings (list team, deactivate)

Reuses the Badge/list/action-button pattern Sprint 014 established for
portal links. AuthProvider gains userId so the Deactivate button can hide
on the caller's own row (server-enforced regardless via
CannotDeactivateSelfError)."
```

---

## Task 5: Full verification pass

**Files:** none modified — verification only.

**Interfaces:**
- Consumes: Tasks 1–4 must all be committed first.
- Produces: a pass/fail verdict gating Task 6/7.

- [ ] **Step 1: Full backend suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `145 passed`.

- [ ] **Step 2: Migration round-trip, re-confirmed on the final state**

Run:
```
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe -m alembic downgrade -1
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

Expected: clean throughout, "No new upgrade operations detected" both times.

- [ ] **Step 3: Frontend lint**

Run (from repo root): `pnpm lint`

Expected: 0 errors, 0 warnings.

- [ ] **Step 4: Frontend build (includes TypeScript check)**

Run (from repo root): `pnpm build`

Expected: compiles clean. `apps/web` has no standalone `check-types` script (confirmed during Sprint 014 planning) — Next.js's own TypeScript check inside `next build` is the real type-check for this repo. Route count should match Sprint 014's baseline (15 routes) — this task adds no new route, only new content on the existing `/settings` route.

- [ ] **Step 5: `git diff --check`**

Run: `git diff --check <task-1-base-sha>..HEAD` (the commit before Task 1's migration commit)

Expected: exit 0, no whitespace/conflict-marker issues.

- [ ] **Step 6: Record results**

No git action — keep the exact pass/fail figures from Steps 1–5 for Task 7's docs.

---

## Task 6: Manual smoke test

**Files:** none modified — manual verification only, run against the live local app.

**Interfaces:**
- Consumes: a running backend (`uvicorn`) and frontend (`pnpm dev`) against the local PostgreSQL instance.
- Produces: a pass/fail verdict gating Task 7.

- [ ] **Step 1: Start the app**

Backend: `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` from repo root. Frontend: `pnpm dev` (root or `apps/web`). Confirm both reachable.

- [ ] **Step 2: Create a second tenant user and confirm the team list**

Log in as the seeded owner. Via the API (`/docs`) or an invitation, get a second, Staff-role user into the seeded owner's tenant (e.g. `POST /api/v1/invitations` then accept it, or use an existing Staff account if one already exists from prior manual testing). Log in as that Staff user to obtain a token; keep it. As the Owner, open `/settings` — confirm the new "Team" card lists both the Owner and the Staff user, each with correct role/active badges, and that the Owner's own row has no Deactivate button.

- [ ] **Step 3: Deactivate and confirm session invalidation**

As the Owner, click "Deactivate" on the Staff user's row. Confirm: the row updates to "inactive," the button disappears. Using the Staff user's token captured in Step 2, call `GET /api/v1/auth/me` directly (e.g. via `/docs` or curl) — confirm it now returns 401.

- [ ] **Step 4: Confirm the activity event and no portal-link cascade**

Check the Recent Activity feed (or `GET /api/v1/activity?type=team_member_deactivated`) — confirm one event, title "Team member deactivated," description = the deactivated user's name. If the deactivated Staff user had created any portal link for a customer prior to deactivation, confirm that link's public token URL still resolves (200, not 404/expired).

- [ ] **Step 5: Confirm self-deactivation is blocked**

As the Owner, attempt `POST /api/v1/users/{owner_id}/deactivate` directly (their own id) via `/docs` — confirm 409, and confirm the Owner's own session still works afterward (their token wasn't affected).

- [ ] **Step 6: Clean up and record**

Stop the backend/frontend dev servers. No git action — keep pass/fail results for Task 7's docs.

---

## Task 7: Docs — ADR-031, sprint record, changelog, doc touch-ups; commit

**Files:**
- Modify: `docs/DECISIONS.md` (new ADR-031)
- Create: `docs/SPRINTS/sprint-015.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/USER_ROLES.md`
- Modify: `docs/SYSTEM_ARCHITECTURE.md`
- Modify: `docs/API_SPEC.md` (if this file tracks a route table — check its existing structure before editing)

**Interfaces:**
- Consumes: the real pass/fail results and exact figures from Task 5 (lint/build/alembic/pytest) and Task 6 (manual smoke test) — this task's audit table must use those real results, not invented ones.
- Produces: nothing consumed by a later task — final task in the plan.

- [ ] **Step 1: Write ADR-031 in `docs/DECISIONS.md`**

Add after the existing `## ADR-030` section, following that section's exact format (`**Status:** IMPLEMENTED (Sprint 015)` line, then prose). Cover: soft-deactivation over hard-delete and why (the two `NOT NULL` FKs), the self-deactivation-only guard and why there's no separate last-owner case (no code path to a second Owner today), the decision that a deactivated teammate's portal links keep working (tenant-owned data, not creator-owned), and that `get_current_user` now has a second real rejection path beyond invalid-token.

- [ ] **Step 2: Write `docs/SPRINTS/sprint-015.md`**

Follow `docs/SPRINTS/sprint-014.md`'s section structure exactly: header, `**Status:**`, `## Objective` (state the permission-matrix gap this closes, quoting `USER_ROLES.md`, and that the roadmap's literal Sprint 015 line is stale and untouched — supplier/purchasing remains entirely unaddressed), `## Scope delivered` (Backend/Frontend/Docs subsections listing the real changes from Tasks 1–4), `## Test-suite coverage` (name all 9 new tests and what each asserts), `## Audit results` (a table using Task 5's and Task 6's real recorded results: pytest count, alembic check/round-trip, lint, build, manual smoke test), `## Follow-up items raised, not part of Sprint 015 scope` (carry forward: reactivation not built; documents/messaging still unstarted; roadmap's stale table still unreconciled; roadmap's Supplier/Purchasing line still fully unaddressed; the pre-existing `EmailAlreadyRegisteredError`-doesn't-filter-by-`is_active` edge case flagged in the spec, not fixed).

- [ ] **Step 3: Add the `docs/CHANGELOG.md` entry**

Insert at the top of the file (above the Sprint #014 entry), following that entry's format: date, `Sprint #015` title, `Full detail in` pointer, Backend/Frontend/Tests subsections, `**Verified:**` closing line with the real Task 5/6 results.

- [ ] **Step 4: Update `docs/USER_ROLES.md`**

Update the passage this sprint's Objective quotes (the "permission matrix still isn't [decided]" paragraph) to note that "removing a teammate" is now resolved — an Owner can deactivate a Staff user via `app/users/`. Keep the rest of that paragraph's framing (other undecided cases like tenant settings/billing remain open) — this sprint answers one named example, not the whole open question.

- [ ] **Step 5: Update `docs/SYSTEM_ARCHITECTURE.md`**

Add `app/users/` to the module table/folder-tree listing (same format as the `app/portal/` entry added in Sprint 014), and note `/settings`'s new Team section in the frontend route table.

- [ ] **Step 6: Update `docs/API_SPEC.md` if applicable**

Check whether this file maintains a per-route table (grep for `/invitations` or `/portal-links` to find the pattern). If so, add rows for `GET /api/v1/users` and `POST /api/v1/users/{id}/deactivate` matching the existing table's columns exactly. If this file doesn't exist or doesn't track routes this granularly, skip this step and say so in the commit — don't invent a new documentation structure.

- [ ] **Step 7: Confirm `docs/ROADMAP.md` is untouched**

Run: `git diff docs/ROADMAP.md`

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add docs/DECISIONS.md docs/SPRINTS/sprint-015.md docs/CHANGELOG.md docs/USER_ROLES.md docs/SYSTEM_ARCHITECTURE.md docs/API_SPEC.md
git commit -m "docs: Sprint 015 - record team management (ADR-031, sprint record, changelog)

Closes the "removing a teammate?" example USER_ROLES.md's permission-matrix
paragraph named. Roadmap's stale Supplier/Purchasing Sprint 015 line
remains entirely unaddressed; docs/ROADMAP.md intentionally not touched."
```

(Adjust the `git add` file list to match whatever Step 6 actually decided about `API_SPEC.md`.)

---

## Explicit non-goals (carried from spec)

- No reactivation endpoint or UI (spec §15).
- No cascade-revoke of a deactivated teammate's portal links (spec §4/§11/§15).
- No "last owner" check beyond self-deactivation — no code path to a second Owner exists today (spec §15).
- No fix for the pre-existing `EmailAlreadyRegisteredError`/`is_active` interaction — flagged, not fixed (spec §15).
- No push to any remote — every commit in this plan is local. Pushing requires a separate, explicit user request.
- No work on Sprint 016 or the roadmap's stale lines (Contracts+Payments, Supplier/Purchasing, AI features, billing).
- No changes to `docs/ROADMAP.md`.
- No changes to Sprint 014's own commits or docs.
