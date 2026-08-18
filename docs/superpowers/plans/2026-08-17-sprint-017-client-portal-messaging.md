# Sprint 017 — Client Portal Messaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff and a customer exchange text messages tied to that customer — staff from the customer detail page, the customer through their existing portal link, no account, no login — closing the last piece of the client-portal gap deferred since Sprint 013.

**Architecture:** A new `app/messages/` module (`models.py`, `service.py`, `router.py`) owns staff-side post/list, following the one-module-per-concern convention. The two customer-facing public routes live in `app/portal/router.py`, not `app/messages/router.py` — the established convention Sprint 016 already set for documents: `PortalService` gains `list_customer_messages`/`post_customer_message`, mirroring `get_customer_quote`'s/`list_customer_documents`'s exact validation shape (active-token check, tenant_id/customer_id resolved from the token row only). `post_customer_message` additionally logs an `ActivityEvent` and creates a `Notification` — the first time this codebase triggers a `Notification` as a side effect of another module's business logic rather than from the notifications HTTP layer itself. Both new UI surfaces (customer page, portal page) poll every 5 seconds via the existing `usePolling` hook.

**Tech Stack:** FastAPI/SQLAlchemy 2.0 backend (Python 3.12, `.venv`), Next.js 16/React 19 frontend (TypeScript, Tailwind v4, pnpm/Turborepo), pytest, Alembic. No new third-party dependency.

**Spec:** `docs/superpowers/specs/2026-08-17-sprint-017-client-portal-messaging-design.md`

## Global Constraints

- Message content policy (spec §5), binding, not a placeholder:
  - Maximum body length: 5,000 characters, enforced server-side via Pydantic validation on `MessageCreate.body` — `422` on violation.
  - Empty or whitespace-only bodies are rejected with `422`. The body is stripped only to *check* emptiness — the stored/returned value is the original, unstripped string.
  - Plain text only. No markdown parsing, no rich text, no HTML interpretation, anywhere. The frontend renders `message.body` as a plain React text node — NEVER `dangerouslySetInnerHTML`. This is the sole XSS mitigation for this feature and must not be weakened.
  - No file attachments — do not add one.
  - No per-message read/unread column — do not add one.
  - No editing or deleting a sent message — post-and-read only.
  - No resolution of a staff sender's display name in any response model — `MessageOut` exposes `sender_type`/`sender_user_id` (raw id) only.
  - No rate limiting on the public `POST /token/{token}/messages` route this sprint — do not add any.
  - No WebSockets/SSE — polling only, via the existing `usePolling` hook, 5-second interval.
- Messages are customer-level, not project-level. `Message.customer_id` is the only relationship column beyond `tenant_id`/`sender_user_id` — do not add a `project_id` column.
- No `require_role` usage anywhere in `app/messages/` — any authenticated tenant user may post/list, matching customer/project/portal-link/document creation precedent.
- Public routes (`app/portal/router.py`) resolve `tenant_id`/`customer_id` from the portal token row itself — NEVER from a caller-supplied parameter. Neither public message route accepts a `customer_id` argument at all.
- A staff-authored message (`POST /api/v1/messages`) must NOT create an `ActivityEvent` or a `Notification` — only a customer-authored message (via the public route) does.
- `docs/ROADMAP.md` must NOT be modified.
- New ADR-033 required in `docs/DECISIONS.md` (spec §18 — first bidirectional, publicly-writable data flow in this codebase).
- Sprint 016 (commit `37ddc25`) must not be reopened or modified.
- Do not push to any remote at any point in this plan — commits are local only unless the user separately asks.

---

## Task 1: Database migration and `Message` model

**Files:**
- Modify: `app/database/models.py` (new `Message` class)
- Create: `alembic/versions/<generated>_add_messages_table.py`

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces: `Message` ORM model — consumed by Task 2's crud/service/router and Task 3's portal-side additions.

- [ ] **Step 1: Add the `Message` model**

In `app/database/models.py`, insert a new class immediately after the `Document` class (after line 256, before the `ActivityLog` class):

```python
class Message(Base):
    """A text message between staff and a customer, tied to the customer
    (not project) level — same reasoning as PortalLink (ADR-030) and
    Document (ADR-032): one thread covers all of a customer's concurrent
    jobs. sender_user_id is NULL for a customer-authored message (no
    users row for a customer, per ADR-030) and set to the acting staff
    user's id for a staff-authored one. No relationship() (repo
    convention) — every FK here is a plain column, resolved via explicit
    crud lookups. See app/messages/service.py and
    app/portal/service.py's post_customer_message() (Sprint 017,
    ADR-033).
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String, nullable=False)
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`String`, `DateTime`, `ForeignKey`, `UUID`, `Mapped`, `mapped_column`, `func`, `uuid`, `datetime` are all already imported at the top of this file — no new imports needed.

- [ ] **Step 2: Generate the migration**

Run: `.venv/Scripts/python.exe -m alembic revision --autogenerate -m "add messages table"`

Expected: a new file under `alembic/versions/`. Open it and confirm it contains exactly one `op.create_table("messages", ...)` in `upgrade()` with all 7 columns (`id`, `tenant_id`, `customer_id`, `sender_type`, `sender_user_id`, `body`, `created_at`), the 3 FK constraints (to `tenants`, `customers`, `users` — `sender_user_id`'s FK must be nullable), and exactly one `op.drop_table("messages")` in `downgrade()` — nothing else. If autogenerate detected any other change, stop and report it as a concern — that would mean pre-existing drift, not this task's job to fix.

- [ ] **Step 3: Round-trip verification**

Run, in order:
```
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic downgrade -1
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

Expected: all four succeed; the final check reports "No new upgrade operations detected."

- [ ] **Step 4: Commit**

```bash
git add app/database/models.py alembic/versions/
git commit -m "feat: Sprint 017 - add messages table

Additive-only migration. Customer-level attachment (not project-level),
matching PortalLink/Document precedent. sender_user_id is nullable —
NULL for a customer-authored message, since a customer has no users row
(ADR-030)."
```

---

## Task 2: Backend — `app/messages/` module (staff post, list)

**Files:**
- Modify: `app/database/crud.py`
- Create: `app/messages/__init__.py` (empty, matches `app/documents/__init__.py` convention)
- Create: `app/messages/models.py`
- Create: `app/messages/service.py`
- Create: `app/messages/router.py`
- Modify: `app/api/v1/__init__.py`
- Create: `tests/test_messages.py`

**Interfaces:**
- Consumes: `Message` model (Task 1).
- Produces: `POST /api/v1/messages`, `GET /api/v1/messages` — consumed by Task 4 (frontend `api.postMessage`/`api.getMessages`). `crud.create_message(db, *, id, tenant_id, customer_id, sender_type, sender_user_id, body) -> Message` and `crud.list_messages(db, tenant_id, customer_id) -> list[Message]` — consumed by Task 3's `PortalService` additions. `MessageCreate`, `MessageOut`, `SenderType` (`app/messages/models.py`) — consumed by Task 3's portal router.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_messages.py`:

```python
"""Sprint 017 — app/messages/ + portal-token messaging (docs/DECISIONS.md
ADR-033).

Covers the full lifecycle through the HTTP layer: staff post/list
(success, cross-tenant customer_id rejected, empty/over-length body
rejected, missing customer_id rejected). Portal-token-side access
(list/post/isolation/notification+activity side effects/revoked-link) is
covered separately in this same file once Task 3 adds those routes.
"""

import pytest
from sqlalchemy import delete

from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Message, NotificationRecord

TEST_CUSTOMER_NAME = "Pytest Messages Customer"


def _cleanup():
    db = SessionLocal()
    try:
        customer_ids = [
            row.id for row in db.query(Customer).filter(Customer.name == TEST_CUSTOMER_NAME).all()
        ]
        if customer_ids:
            db.execute(delete(Message).where(Message.customer_id.in_(customer_ids)))
        db.execute(delete(ActivityLog).where(ActivityLog.description == TEST_CUSTOMER_NAME))
        db.execute(
            delete(NotificationRecord).where(
                NotificationRecord.message.like(f"{TEST_CUSTOMER_NAME}%")
            )
        )
        db.execute(delete(Customer).where(Customer.name == TEST_CUSTOMER_NAME))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def created_customer(client, auth_headers):
    _cleanup()
    r = client.post("/api/v1/customers", json={"name": TEST_CUSTOMER_NAME}, headers=auth_headers)
    yield r.json()
    _cleanup()


def test_staff_post_message_success(client, auth_headers, created_customer):
    r = client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "Hi, just checking in on the kitchen job."},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["sender_type"] == "staff"
    assert body["sender_user_id"] is not None
    assert body["body"] == "Hi, just checking in on the kitchen job."
    assert body["customer_id"] == created_customer["id"]


def test_staff_post_message_cross_tenant_customer_returns_404(
    client, auth_headers, other_tenant_auth_headers, created_customer
):
    r = client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "Hello"},
        headers=other_tenant_auth_headers,
    )
    assert r.status_code == 404


def test_staff_post_empty_body_returns_422(client, auth_headers, created_customer):
    r = client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "   "},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_staff_post_over_length_body_returns_422(client, auth_headers, created_customer):
    r = client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "a" * 5001},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_staff_list_messages_requires_customer_id(client, auth_headers):
    r = client.get("/api/v1/messages", headers=auth_headers)
    assert r.status_code == 422


def test_staff_list_messages_is_tenant_scoped_and_ascending(client, auth_headers, created_customer):
    client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "First"},
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "Second"},
        headers=auth_headers,
    )
    r = client.get(f"/api/v1/messages?customer_id={created_customer['id']}", headers=auth_headers)
    assert r.status_code == 200
    bodies = [m["body"] for m in r.json()]
    assert bodies == ["First", "Second"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_messages.py -v`

Expected: every test fails (404/import error) — `/api/v1/messages` doesn't exist yet.

- [ ] **Step 3: Create `app/messages/__init__.py`**

Empty file, matching `app/documents/__init__.py`'s precedent.

- [ ] **Step 4: Add crud helpers**

In `app/database/crud.py`, add `Message` to the existing `from app.database.models import (...)` block (Step 4 alphabetically, between `Material` and `NotificationRecord`):

```python
from app.database.models import (
    ActivityLog,
    Customer,
    Document,
    Invitation,
    Material,
    Message,
    NotificationRecord,
    PortalLink,
    Project,
    Quote,
    Tenant,
    User,
)
```

Then add these two functions immediately after `list_documents` (after line 576, before `list_projects_by_customer`):

```python
def create_message(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    sender_type: str,
    sender_user_id: uuid.UUID | None,
    body: str,
) -> Message:
    row = Message(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        sender_type=sender_type,
        sender_user_id=sender_user_id,
        body=body,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_messages(db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.tenant_id == tenant_id, Message.customer_id == customer_id)
        .order_by(Message.created_at.asc())
    )
    return list(db.scalars(stmt))
```

- [ ] **Step 5: Create `app/messages/models.py`**

```python
"""Sprint 017 (docs/DECISIONS.md ADR-033) — client-portal messaging.

Content policy (binding, see the design spec's §5 for the full
rationale — do not weaken any of this without a new decision):
  - MAX_BODY_LENGTH: 5,000 characters.
  - Empty or whitespace-only bodies are rejected. The check strips the
    value; the stored/returned value is the ORIGINAL, unstripped string.
  - No markdown/HTML — plain text only, enforced on render (frontend),
    not here.
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

MAX_BODY_LENGTH = 5000


class SenderType(str, Enum):
    STAFF = "staff"
    CUSTOMER = "customer"


class MessageCreate(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def body_must_be_valid(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message body cannot be empty.")
        if len(value) > MAX_BODY_LENGTH:
            raise ValueError(f"Message body cannot exceed {MAX_BODY_LENGTH} characters.")
        return value


class MessageOut(BaseModel):
    """sender_type distinguishes who wrote it; sender_user_id is the raw
    id only — never resolved to a display name, matching every other
    *Out model in this codebase (DocumentOut exposes only
    uploaded_by_user_id, not a name)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    sender_type: SenderType
    sender_user_id: uuid.UUID | None
    body: str
    created_at: datetime
```

- [ ] **Step 6: Create `app/messages/service.py`**

```python
"""MessageService — Sprint 017 (docs/DECISIONS.md ADR-033).

Client-portal messaging: bidirectional text messages tied to a customer
(not project — same reasoning as PortalLink/Document). Content policy
(5,000-char cap, non-blank body) is enforced by app/messages/models.py's
MessageCreate validator, which runs before this service is ever called —
this module trusts an already-validated body.
"""

import uuid

from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import Message


class CustomerNotFoundError(Exception):
    """customer_id doesn't resolve under the caller's own tenant — the
    same relationship-linkage-bypass check ADR-029 added elsewhere,
    reused from PortalService.create_link()/DocumentService.upload_document()."""


class MessageService:
    def create_staff_message(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        sender_user_id: uuid.UUID,
        body: str,
    ) -> Message:
        if crud.get_customer_by_id(db, customer_id, tenant_id) is None:
            raise CustomerNotFoundError(customer_id)
        return crud.create_message(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            sender_type="staff",
            sender_user_id=sender_user_id,
            body=body,
        )

    def list_messages(self, db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> list[Message]:
        return crud.list_messages(db, tenant_id, customer_id)


message_service = MessageService()
```

- [ ] **Step 7: Create `app/messages/router.py`**

```python
"""Sprint 017 (docs/DECISIONS.md ADR-033). No require_role — any
authenticated tenant user may post/list, matching the
customer/project/portal-link/document creation precedent (routine work,
not a tenant-control decision).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User
from app.messages.models import MessageCreate, MessageOut
from app.messages.service import CustomerNotFoundError, message_service

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(
    customer_id: uuid.UUID,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return message_service.create_staff_message(
            db,
            tenant_id=current_user.tenant_id,
            customer_id=customer_id,
            sender_user_id=current_user.id,
            body=data.body,
        )
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")


@router.get("", response_model=list[MessageOut])
def list_messages(
    customer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return message_service.list_messages(db, current_user.tenant_id, customer_id)
```

- [ ] **Step 8: Mount the router**

In `app/api/v1/__init__.py`, imports are alphabetical by module name. Add the import after `from app.invitations.router import router as invitations_router` and before `from app.portal.router import router as portal_router`:

```python
from app.messages.router import router as messages_router
```

Add the corresponding `include_router` call in the same relative position, after `api_router.include_router(invitations_router)` and before `api_router.include_router(portal_router)`:

```python
api_router.include_router(messages_router)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_messages.py -v`

Expected: all 6 tests pass.

- [ ] **Step 10: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `163 passed` (157 existing + 6 new).

- [ ] **Step 11: Commit**

```bash
git add app/database/crud.py app/messages/ app/api/v1/__init__.py tests/test_messages.py
git commit -m "feat: Sprint 017 - add messages module (staff post, list)

New app/messages/ module: POST/GET /api/v1/messages. Enforces the
content policy (5,000-char cap, non-blank body) via a Pydantic
validator on MessageCreate. No require_role, matching
customer/project/portal-link/document creation precedent."
```

---

## Task 3: Backend — portal-token messaging (list + post) and staff notification

**Files:**
- Modify: `app/activity/models.py`
- Modify: `app/portal/service.py`
- Modify: `app/portal/router.py`
- Modify: `tests/test_messages.py`

**Interfaces:**
- Consumes: `crud.list_messages`/`crud.create_message` (Task 2), `MessageCreate`/`MessageOut` (Task 2), `PortalService.get_link_by_token`/`derive_status` (pre-existing, Sprint 013), `activity_service.log` (pre-existing), `notification_service.create` (pre-existing).
- Produces: `GET /api/v1/portal-links/token/{token}/messages`, `POST /api/v1/portal-links/token/{token}/messages` — consumed by Task 4 (frontend `api.getPortalMessages`/`api.postPortalMessage`).

- [ ] **Step 1: Add the new `ActivityType` value**

In `app/activity/models.py`, add a new line to the `ActivityType` enum, after `TEAM_MEMBER_DEACTIVATED`:

```python
    CUSTOMER_MESSAGE_RECEIVED = "customer_message_received"
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_messages.py`:

```python
def test_portal_lists_only_that_customers_messages(client, auth_headers, created_customer):
    client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "Staff hello"},
        headers=auth_headers,
    )
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.get(f"/api/v1/portal-links/token/{link['token']}/messages")
    assert r.status_code == 200
    assert any(m["body"] == "Staff hello" for m in r.json())


def test_portal_posts_message_and_triggers_notification_and_activity(
    client, auth_headers, created_customer
):
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.post(
        f"/api/v1/portal-links/token/{link['token']}/messages",
        json={"body": "When will the template visit happen?"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["sender_type"] == "customer"
    assert body["sender_user_id"] is None
    assert body["body"] == "When will the template visit happen?"

    activity = client.get(
        "/api/v1/activity?type=customer_message_received", headers=auth_headers
    ).json()
    assert any(a["description"] == TEST_CUSTOMER_NAME for a in activity)

    notifications = client.get("/api/v1/notifications", headers=auth_headers).json()
    assert any(TEST_CUSTOMER_NAME in n["message"] for n in notifications)


def test_portal_post_empty_body_returns_422_and_no_side_effects(
    client, auth_headers, created_customer
):
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.post(f"/api/v1/portal-links/token/{link['token']}/messages", json={"body": ""})
    assert r.status_code == 422

    messages = client.get(
        f"/api/v1/messages?customer_id={created_customer['id']}", headers=auth_headers
    ).json()
    assert messages == []


def test_portal_post_over_length_body_returns_422_and_no_side_effects(
    client, auth_headers, created_customer
):
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()

    r = client.post(
        f"/api/v1/portal-links/token/{link['token']}/messages", json={"body": "a" * 5001}
    )
    assert r.status_code == 422

    messages = client.get(
        f"/api/v1/messages?customer_id={created_customer['id']}", headers=auth_headers
    ).json()
    assert messages == []


def test_staff_message_does_not_trigger_notification_or_activity(
    client, auth_headers, created_customer
):
    client.post(
        f"/api/v1/messages?customer_id={created_customer['id']}",
        json={"body": "Staff-authored, should not notify anyone"},
        headers=auth_headers,
    )
    activity = client.get(
        "/api/v1/activity?type=customer_message_received", headers=auth_headers
    ).json()
    assert not any(a["description"] == TEST_CUSTOMER_NAME for a in activity)


def test_portal_revoked_link_cannot_access_messages(client, auth_headers, created_customer):
    link = client.post(
        "/api/v1/portal-links", json={"customer_id": created_customer["id"]}, headers=auth_headers
    ).json()
    client.delete(f"/api/v1/portal-links/{link['id']}", headers=auth_headers)

    r_list = client.get(f"/api/v1/portal-links/token/{link['token']}/messages")
    assert r_list.status_code == 404

    r_post = client.post(
        f"/api/v1/portal-links/token/{link['token']}/messages", json={"body": "Hello?"}
    )
    assert r_post.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_messages.py -k portal -v`

Expected: the new portal-side tests fail (404 — routes don't exist yet). `test_staff_message_does_not_trigger_notification_or_activity` currently passes vacuously (no `customer_message_received` activity type exists yet to match) — that's expected and will remain a valid regression guard once Step 4 adds the routes.

- [ ] **Step 4: Add methods to `PortalService`**

In `app/portal/service.py`:

Add `Message` to the existing import line (line 32):
```python
from app.database.models import Customer, Document, Message, PortalLink, Project, Quote, Tenant
```

Add two new imports after the existing `app.activity` imports (after line 29):
```python
from app.notifications.models import NotificationCreate, NotificationType
from app.notifications.service import notification_service
```

Add two new methods after `get_customer_document` (after line 178, before the `portal_service = PortalService()` line):

```python
    def list_customer_messages(self, db: Session, token: str) -> list[Message]:
        """Same active-token requirement as list_customer_documents — a
        revoked/expired link lists no messages."""
        row = self.get_link_by_token(db, token)
        if row is None or self.derive_status(row) != "active":
            raise PortalLinkNotFoundError(token)
        return crud.list_messages(db, row.tenant_id, row.customer_id)

    def post_customer_message(self, db: Session, token: str, body: str) -> Message:
        """Creates a customer-authored message (sender_user_id always
        None — a customer has no users row, ADR-030), tagged with the
        token's own tenant_id/customer_id, never caller input — there is
        no customer_id parameter on this method at all, unlike
        get_customer_document's document_id. Also logs an ActivityEvent
        and creates a Notification (Sprint 017, ADR-033) so staff learn
        about it outside the thread itself — the first time this
        codebase creates a Notification as a side effect of another
        module's business logic rather than from the notifications HTTP
        layer itself."""
        row = self.get_link_by_token(db, token)
        if row is None or self.derive_status(row) != "active":
            raise PortalLinkNotFoundError(token)

        message = crud.create_message(
            db,
            id=uuid.uuid4(),
            tenant_id=row.tenant_id,
            customer_id=row.customer_id,
            sender_type="customer",
            sender_user_id=None,
            body=body,
        )

        customer = crud.get_customer_by_id(db, row.customer_id, row.tenant_id)
        customer_name = customer.name if customer is not None else "A customer"

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.CUSTOMER_MESSAGE_RECEIVED,
                title="New message from a customer",
                description=customer_name,
            ),
            tenant_id=row.tenant_id,
        )
        notification_service.create(
            NotificationCreate(
                title="New message",
                message=f"{customer_name} sent a new message.",
                type=NotificationType.INFO,
            ),
            tenant_id=row.tenant_id,
        )

        return message
```

- [ ] **Step 5: Add the two routes**

In `app/portal/router.py`, add an import after `from app.documents.service import document_service` (line 25):

```python
from app.messages.models import MessageCreate, MessageOut
```

Add the two new routes after `download_portal_document` (after line 151, at the end of the file):

```python
@router.get("/token/{token}/messages", response_model=list[MessageOut])
def list_portal_messages(token: str, db: Session = Depends(get_db)):
    try:
        return portal_service.list_customer_messages(db, token)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")


@router.post(
    "/token/{token}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED
)
def post_portal_message(token: str, data: MessageCreate, db: Session = Depends(get_db)):
    try:
        return portal_service.post_customer_message(db, token, data.body)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_messages.py -v`

Expected: all 12 tests in this file pass (6 from Task 2 + 6 new).

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: `169 passed` (163 from Task 2 + 6 new).

- [ ] **Step 8: Commit**

```bash
git add app/activity/models.py app/portal/service.py app/portal/router.py tests/test_messages.py
git commit -m "feat: Sprint 017 - add portal-token messaging and staff notification

Two new public routes on app/portal/router.py, mirroring the existing
document routes' exact shape (active-token requirement, tenant_id/
customer_id resolved from the token row only). A customer-authored
message logs an ActivityEvent and creates a Notification; a
staff-authored one does not. A revoked or expired link cannot list or
post messages."
```

---

## Task 4: Frontend — Messages card on customer page, Messages section on portal page

**Files:**
- Create: `apps/web/types/message.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/customers/[id]/page.tsx`
- Modify: `apps/web/app/portal/[token]/page.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/messages`, `GET /api/v1/messages`, `GET /api/v1/portal-links/token/{token}/messages`, `POST /api/v1/portal-links/token/{token}/messages` (Tasks 2/3).
- Produces: nothing consumed by a later task — leaf UI change.

- [ ] **Step 1: Create `apps/web/types/message.ts`**

```typescript
// Sprint 017 — mirrors app/messages/models.py's MessageOut.

export type SenderType = "staff" | "customer";

export interface MessageOut {
  id: string;
  tenant_id: string;
  customer_id: string;
  sender_type: SenderType;
  sender_user_id: string | null;
  body: string;
  created_at: string;
}
```

- [ ] **Step 2: Add API client methods**

In `apps/web/lib/api.ts`, add the import alongside the other `@/types/*` imports (after the `@/types/invitation` import block, before `@/types/notification`):

```typescript
import type { MessageOut } from "@/types/message";
```

Add four methods inside the exported `api` object. `getMessages`/`postMessage` go near the documents methods (after `downloadDocument`, at the end of the object); `getPortalMessages`/`postPortalMessage` go near the portal methods (after `downloadPortalDocument`):

Insert after `downloadPortalDocument`'s closing `},` (after line 260, before `getProjects`):

```typescript
  // Sprint 017 — public, no token required, matches
  // getPortalByToken/getPortalDocuments.
  getPortalMessages: (token: string) =>
    request<MessageOut[]>(`/portal-links/token/${token}/messages`),

  postPortalMessage: (token: string, body: string) =>
    request<MessageOut>(`/portal-links/token/${token}/messages`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
```

Insert after `downloadDocument`'s closing `},` (at the very end of the object, before the final `};`):

```typescript
  // Sprint 017 — customer-level message thread. customer_id is a required
  // query parameter on GET (unlike getDocuments' optional filter) — a
  // thread with no customer scope is meaningless.
  getMessages: (customerId: string) =>
    request<MessageOut[]>(`/messages?customer_id=${customerId}`),

  postMessage: (customerId: string, body: string) =>
    request<MessageOut>(`/messages?customer_id=${customerId}`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
```

- [ ] **Step 3: Add the Messages card to the customer detail page**

In `apps/web/app/customers/[id]/page.tsx`:

Add `cn` to the existing `@/lib/utils` import (line 14):
```typescript
import { cn, formatRelativeTime } from "@/lib/utils";
```

Add two new imports:
```typescript
import { usePolling } from "@/hooks/usePolling";
import type { MessageOut } from "@/types/message";
```

Add `userId` to the existing `useAuth()` destructure (line 36):
```typescript
  const { isAuthenticated, isReady, userId } = useAuth();
```

Add message-thread state and the polling hook, after the existing `documents`/`downloadingDocId` state block (after line 69):

```typescript
  // Sprint 017 — client-portal messaging. Polls every 5s while this page
  // is mounted, matching the design spec's real-time-feeling convention.
  const [messageDraft, setMessageDraft] = useState("");
  const [sendingMessage, setSendingMessage] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);

  const { data: messages, refetch: refetchMessages } = usePolling<MessageOut[]>(
    () => (customer ? api.getMessages(customer.id) : Promise.resolve([])),
    { intervalMs: 5000, enabled: !!customer }
  );
```

Add a send handler, after `formatFileSize` (after line 177):

```typescript
  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!customer || !messageDraft.trim()) return;
    setSendingMessage(true);
    setMessageError(null);
    try {
      await api.postMessage(customer.id, messageDraft);
      setMessageDraft("");
      await refetchMessages();
    } catch (err) {
      setMessageError(err instanceof ApiError ? err.message : "Could not send that message.");
    } finally {
      setSendingMessage(false);
    }
  }
```

Add a new `<Card>` after the existing "Documents" card (after line 376, the closing `</Card>` for Documents, still inside the outer `<div className="mx-auto max-w-xl">`):

```tsx
      {customer && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Messages</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="flex max-h-80 flex-col gap-3 overflow-y-auto p-5">
              {messages && messages.length === 0 && (
                <p className="text-center text-sm text-muted">No messages yet.</p>
              )}
              {messages &&
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      "max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
                      msg.sender_type === "staff" && msg.sender_user_id === userId
                        ? "self-end bg-accent text-white"
                        : "self-start border border-border bg-background text-foreground"
                    )}
                  >
                    <p>{msg.body}</p>
                    <p className="mt-1 text-[10px] opacity-70">
                      {msg.sender_type === "customer" ? customer.name : "Staff"} ·{" "}
                      {formatRelativeTime(msg.created_at)}
                    </p>
                  </div>
                ))}
            </div>
            <form
              onSubmit={handleSendMessage}
              className="flex items-center gap-2 border-t border-border p-4"
            >
              <Input
                value={messageDraft}
                onChange={(e) => setMessageDraft(e.target.value)}
                placeholder="Write a message…"
                maxLength={5000}
                className="flex-1"
              />
              <Button type="submit" disabled={sendingMessage || !messageDraft.trim()}>
                {sendingMessage ? "Sending…" : "Send"}
              </Button>
            </form>
            {messageError && <p className="px-5 pb-4 text-sm text-danger">{messageError}</p>}
          </CardContent>
        </Card>
      )}
```

Note the message body is rendered via `{msg.body}` (JSX text interpolation) — never `dangerouslySetInnerHTML`. This is the binding XSS mitigation from the spec and must not change.

- [ ] **Step 4: Add the Messages section to the portal page**

In `apps/web/app/portal/[token]/page.tsx`:

Add two new imports:
```typescript
import { usePolling } from "@/hooks/usePolling";
import type { MessageOut } from "@/types/message";
```

Add message-thread state and the polling hook, after the existing `documentsError`/`downloadingDocId` state block (after line 41):

```typescript
  // Sprint 017 — client-portal messaging. Polls every 5s while this page
  // is mounted.
  const [messageDraft, setMessageDraft] = useState("");
  const [sendingMessage, setSendingMessage] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);

  const { data: messages, refetch: refetchMessages } = usePolling<MessageOut[]>(
    () => api.getPortalMessages(params.token),
    { intervalMs: 5000, enabled: !!portal && portal.status === "active" }
  );
```

Add a send handler, after `handleDownloadDocument` (after line 65):

```typescript
  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!messageDraft.trim()) return;
    setSendingMessage(true);
    setMessageError(null);
    try {
      await api.postPortalMessage(params.token, messageDraft);
      setMessageDraft("");
      await refetchMessages();
    } catch {
      setMessageError("Could not send that message. Try again.");
    } finally {
      setSendingMessage(false);
    }
  }
```

Add a new `<Card>` inside the `{!loadError && portal && portal.status === "active" && (<div className="flex flex-col gap-6">` block, after the existing "Documents" card and before the "This link expires..." paragraph (after line 239, before line 241):

```tsx
          <Card>
            <CardHeader>
              <CardTitle>Messages</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="flex max-h-80 flex-col gap-3 overflow-y-auto p-5">
                {messages && messages.length === 0 && (
                  <p className="text-center text-sm text-muted">No messages yet.</p>
                )}
                {messages &&
                  messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={
                        msg.sender_type === "customer"
                          ? "self-end max-w-[80%] whitespace-pre-wrap rounded-lg bg-accent px-3 py-2 text-sm text-white"
                          : "self-start max-w-[80%] whitespace-pre-wrap rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                      }
                    >
                      <p>{msg.body}</p>
                      <p className="mt-1 text-[10px] opacity-70">
                        {msg.sender_type === "customer" ? "You" : "Staff"} ·{" "}
                        {formatDate(msg.created_at)}
                      </p>
                    </div>
                  ))}
              </div>
              <form
                onSubmit={handleSendMessage}
                className="flex items-center gap-2 border-t border-border p-4"
              >
                <input
                  value={messageDraft}
                  onChange={(e) => setMessageDraft(e.target.value)}
                  placeholder="Write a message…"
                  maxLength={5000}
                  className="h-10 flex-1 rounded-lg border border-border bg-background px-3 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent"
                />
                <Button type="submit" disabled={sendingMessage || !messageDraft.trim()}>
                  {sendingMessage ? "Sending…" : "Send"}
                </Button>
              </form>
              {messageError && <p className="px-5 pb-4 text-sm text-danger">{messageError}</p>}
            </CardContent>
          </Card>
```

Note this page has no `Input` component imported (unlike the customer page) — the plain `<input>` above matches `Input`'s own class list exactly (copied from `components/ui/Field.tsx`) rather than adding a new import for one element; this stays consistent with the message body being rendered via `{msg.body}`, never `dangerouslySetInnerHTML`.

- [ ] **Step 5: Manual trace verification**

Read both resulting files once, tracing: (a) a customer/portal link with zero messages — no crash, sensible empty state; (b) sending a message — the draft clears and the new message appears without a page refresh (via `refetchMessages()`); (c) the polling hook only activates once its `enabled` condition is true (`!!customer` / `portal?.status === "active"`), so no request fires against an unresolved token or customer.

- [ ] **Step 6: Commit**

```bash
git add apps/web/types/message.ts apps/web/lib/api.ts "apps/web/app/customers/[id]/page.tsx" "apps/web/app/portal/[token]/page.tsx"
git commit -m "feat: Sprint 017 - add message thread UI to customer page and portal page

Customer page gets a Messages card (thread + send form). Portal page
gets a matching Messages section. Both poll every 5s via the existing
usePolling hook. Message bodies render as plain text only — no
dangerouslySetInnerHTML, no markdown parsing."
```

---

## Task 5: Full verification pass

**Files:** none modified — verification only.

**Interfaces:**
- Consumes: Tasks 1–4 must all be committed first.
- Produces: a pass/fail verdict gating Task 6/7/8.

- [ ] **Step 1: Full backend suite** — `.venv/Scripts/python.exe -m pytest tests/ -q` — expect `169 passed`.
- [ ] **Step 2: Migration round-trip** — `alembic check`, `downgrade -1`, `upgrade head`, `alembic check` again — expect clean throughout.
- [ ] **Step 3: Frontend lint** — `pnpm lint` — expect 0 errors/warnings.
- [ ] **Step 4: Frontend build** — `pnpm build` — expect clean compile, TypeScript passing inside build (no standalone `check-types` script for `apps/web`), same route count as Sprint 016's baseline (15 routes — this task adds no new route, only content on two existing routes).
- [ ] **Step 5: `git diff --check`** — against the commit before Task 1 — expect exit 0.
- [ ] **Step 6: Record results** — no git action, keep exact figures for Task 7's docs and Task 8's audit.

---

## Task 6: Manual smoke test

**Files:** none modified.

- [ ] **Step 1: Start the app** (uvicorn + `pnpm dev`, against the local Postgres instance).
- [ ] **Step 2: Staff sends a message** — on an existing customer's detail page, send a message via the new Messages card. Confirm it appears in the thread, right-aligned, without a page refresh.
- [ ] **Step 3: Portal receives it** — open that customer's existing (or a newly generated) portal link. Confirm the Messages section shows the staff message, left-aligned, within one 5-second poll interval (wait ~5s if it doesn't appear immediately on load).
- [ ] **Step 4: Customer replies** — send a message from the portal page. Confirm it appears there right-aligned, and confirm it appears on the staff customer page (left-aligned) within one poll interval.
- [ ] **Step 5: Notification/Activity check** — after Step 4, confirm exactly one new bell-icon Notification appeared ("New message") and exactly one new Recent Activity entry appeared ("New message from a customer") — both attributable to the customer reply, not the earlier staff message.
- [ ] **Step 6: Rejection checks** — attempt to send an empty/whitespace-only message from both the staff and portal UIs; confirm the Send button is disabled (client-side) and, via `/docs`, confirm a raw empty-body POST returns `422` server-side on both routes.
- [ ] **Step 7: Revoked-link check** — revoke the portal link used in Steps 3–5; confirm the Messages section's requests now fail (404) for that token — reload the portal page and confirm the page shows its existing "This link has been revoked" state rather than crashing.
- [ ] **Step 8: XSS render check** — send a message containing literal text like `<b>test</b>` from either side; confirm it renders as the literal visible characters `<b>test</b>` on both pages, not as bold text — the concrete verification that the frontend never interprets message bodies as HTML.
- [ ] **Step 9: Clean up and record** — stop the dev servers; keep pass/fail results for Task 7/8.

---

## Task 7: Docs — ADR-033, sprint record, changelog, doc touch-ups; commit

**Files:**
- Modify: `docs/DECISIONS.md` (new ADR-033)
- Create: `docs/SPRINTS/sprint-017.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/USER_ROLES.md`
- Modify: `docs/SYSTEM_ARCHITECTURE.md`
- Modify: `docs/API_SPEC.md`

**Interfaces:**
- Consumes: real results from Task 5/6 — this task's audit table must use those figures, not invented ones.
- Produces: nothing consumed by a later task.

- [ ] **Step 1: Write ADR-033** in `docs/DECISIONS.md`, after ADR-032, following its format. Cover: the messaging data model and why `sender_user_id` is nullable, the customer-level (not project-level) attachment decision, the notification/activity trigger on inbound customer messages (and that this is the first time `notification_service.create()` is called as a side effect of another module rather than from its own router), the plain-text-only rendering constraint and why (XSS), the 5,000-character cap, and the accepted no-rate-limiting gap.
- [ ] **Step 2: Write `docs/SPRINTS/sprint-017.md`** following `sprint-016.md`'s structure exactly, using only the real Task 5/6 results.
- [ ] **Step 3: Add the `docs/CHANGELOG.md` entry** at the top, above Sprint #016's entry, matching its format/density.
- [ ] **Step 4: Update `docs/USER_ROLES.md`** — note that the client-portal's original three-part gap (tracking + documents + messaging, Sprint 013's "deliberately deferred" note) is now fully closed.
- [ ] **Step 5: Update `docs/SYSTEM_ARCHITECTURE.md`** — add `app/messages/` to the module table/folder listing; note the two new routes on `app/portal/router.py`'s existing entry; note the new `ActivityType.CUSTOMER_MESSAGE_RECEIVED` value if the doc enumerates activity types anywhere.
- [ ] **Step 6: Update `docs/API_SPEC.md`** — add a "Message routes" section and table rows for all 4 new routes, matching the existing table's columns exactly (same approach Sprint 016 used for documents).
- [ ] **Step 7: Confirm `docs/ROADMAP.md` is untouched** (`git diff docs/ROADMAP.md` — no output) and `docs/SPRINTS/sprint-016.md`/its changelog entry are unmodified.
- [ ] **Step 8: Commit**

```bash
git add docs/DECISIONS.md docs/SPRINTS/sprint-017.md docs/CHANGELOG.md docs/USER_ROLES.md docs/SYSTEM_ARCHITECTURE.md docs/API_SPEC.md
git commit -m "docs: Sprint 017 - record client portal messaging (ADR-033)

Closes the last piece of the client-portal gap deferred since Sprint
013 (tracking + documents + messaging — all three now shipped).
Roadmap untouched."
```

---

## Task 8: Final scope-creep review before commit

**Files:** none modified — review only. This is the explicit final gate the user requested before any of this sprint's work is considered committable as a whole.

- [ ] **Step 1: Full diff stat** — `git diff --stat <commit before Task 1>..HEAD` — confirm every file matches this plan's declared file list (Tasks 1–7's "Files" sections combined) and nothing else appears.
- [ ] **Step 2: Confirm no attachment/file-upload code was added to messaging** — grep the diff for `UploadFile`/`multipart`/`File(` inside `app/messages/` and the new portal routes; expect no hits — messages are text-only this sprint.
- [ ] **Step 3: Confirm no rate-limiting or WebSocket/SSE code was added** — grep the diff for `slowapi`, `limiter`, `websocket`, `WebSocket`, `EventSource`, `socket.io`; any hit must be investigated — these were explicitly ruled out for this sprint.
- [ ] **Step 4: Confirm `docs/ROADMAP.md` and Sprint 016's files are untouched** — `git diff docs/ROADMAP.md docs/SPRINTS/sprint-016.md` — expect no output.
- [ ] **Step 5: Confirm the content policy is actually enforced as specified** — re-read `app/messages/models.py`'s `MAX_BODY_LENGTH` value and the `body_must_be_valid` validator against spec §5 verbatim; confirm no value was silently changed during implementation.
- [ ] **Step 6: Final security/tenant-isolation review** — a dedicated read-through, distinct from Step 5's value check: (a) confirm `POST /api/v1/messages` and `GET /api/v1/messages` both validate/filter by `current_user.tenant_id`; (b) confirm neither new portal route (`GET`/`POST /token/{token}/messages`) accepts a `customer_id` parameter from the caller anywhere — `tenant_id`/`customer_id` must come only from `PortalService.get_link_by_token()`'s resolved row; (c) confirm a staff-authored message never triggers `activity_service.log()` or `notification_service.create()` — only `PortalService.post_customer_message()` calls either; (d) confirm every rendering of `message.body` in both frontend pages uses plain JSX text interpolation (`{msg.body}`), never `dangerouslySetInnerHTML`; (e) re-run the 12 `tests/test_messages.py` cases mentally against this checklist.
- [ ] **Step 7: `git status --short`** — run and record the exact output for the final report; confirm nothing outside this sprint's declared file list is modified or untracked.
- [ ] **Step 8: Report** — a short pass/fail summary of Steps 1–7, presented to the user alongside the rest of the sprint's final report. No commit happens as part of this task — it is a review gate, not a code change.

---

## Explicit non-goals (carried from spec)

- File attachments on messages.
- Per-message read/unread state.
- WebSockets/SSE or any other real-time push.
- Rate limiting on the public post route.
- Editing or deleting a sent message.
- Resolving a staff sender's display name.
- Any change to portal token design, auth, or tenant-isolation semantics.
- Markdown or rich-text rendering.
- The `EmailAlreadyRegisteredError`/`is_active` interaction, a teammate reactivation endpoint, document content-sniffing validation, and the supplier/purchasing workflow — none of these are part of this sprint.
- No push to any remote — every commit in this plan is local.
- No work on Sprint 018 or `docs/ROADMAP.md`.
