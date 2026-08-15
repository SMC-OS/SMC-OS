"""Core SQLAlchemy models for SIMO OS.

Sprint 002 — see docs/DATABASE_SCHEMA.md §2 for the source pydantic models
and informal shapes these are drawn from, and docs/DECISIONS.md ADR-013 for
why every table below carries a `tenant_id` column that isn't enforced yet.

Sprint 008 added the `Tenant` table itself and converted every `tenant_id`
column from a bare nullable UUID into a real `ForeignKey("tenants.id")` —
still nullable, still unenforced by any query. See ADR-025. Enforcement
(every query filtering by the caller's tenant) is Sprint 012, not this one.

These are the first real database models in the project. Columns are a
starting point, not a finalised schema — revisit foreign keys, indexes, and
constraints as each dependent module (CRM, Projects, Materials, Auth) is
actually built in its own sprint. No API routes read or write these tables
yet except activity_log/notifications (see app/activity, app/notifications).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class Tenant(Base):
    """A company/workspace using SIMO OS. Sprint 008 — schema only, no
    enforcement: the 7 tables below gain a real FK to this table but every
    existing row (and every query in every existing module) is untouched.
    See docs/DECISIONS.md ADR-025 for the full reasoning and what's
    deliberately deferred to Sprint 009 (tenant-aware auth) and Sprint 012
    (isolation enforcement).
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    # Stays nullable: POST /api/v1/quote and /estimate remain deliberately
    # public (ADR-023) — an anonymous quote is created with tenant_id=NULL
    # and is visible to no tenant's authenticated browsing routes.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )

    material: Mapped[str] = mapped_column(String, nullable=False)
    thickness: Mapped[str] = mapped_column(String, nullable=False)
    kitchen_length: Mapped[float] = mapped_column(Float, nullable=False)
    island: Mapped[bool] = mapped_column(Boolean, default=False)
    waterfall: Mapped[int] = mapped_column(Integer, default=0)
    splashback: Mapped[bool] = mapped_column(Boolean, default=False)
    upstands: Mapped[bool] = mapped_column(Boolean, default=False)
    postcode: Mapped[str | None] = mapped_column(String, nullable=True)

    price_per_slab: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_before_vat: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="enquiry")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    thickness: Mapped[str | None] = mapped_column(String, nullable=True)
    slab_size: Mapped[str | None] = mapped_column(String, nullable=True)
    finish: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 009 — the first tenant_id column to actually become NOT NULL
    # (migration c28dd4348080); every user belongs to exactly one tenant.
    # The other 6 tables' tenant_id columns stay nullable until Sprint 012.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Sprint 010 — constrained to app.auth.models.UserRole's values at the
    # Pydantic/API boundary, same convention as Project.status/ProjectStatus.
    # Still a plain String column, no DB-level enum or CHECK constraint.
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Sprint 015 (docs/DECISIONS.md ADR-031) — soft-deactivation. An Owner
    # can revoke a teammate's access without deleting the row (Invitation.
    # invited_by_user_id / PortalLink.created_by_user_id are NOT NULL FKs to
    # this table, so deletion would break historical rows). See
    # app/users/service.py and app/auth/dependencies.py's get_current_user.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Invitation(Base):
    """A pending offer to join a tenant as a Staff user. Sprint 011 — the
    first table that lets a tenant have more than one user. No
    relationship() (repo convention) — tenant_id/invited_by_user_id are
    plain FK columns, resolved via explicit crud lookups.

    status is one of "pending" | "accepted" | "revoked" — plain String,
    same convention as User.role/Project.status. "expired" is derived at
    read time from expires_at, not stored. See docs/DECISIONS.md ADR-028.
    """

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortalLink(Base):
    """A reusable, revocable link letting one customer view their own
    projects/quotes with no account (Sprint 013, ADR-030). Same opaque
    hashed-token convention as Invitation (token_hash, unique, never the
    recoverable secret) but NOT single-use: status is "active" | "revoked"
    only — there is no "accepted" state, since an active link is meant to
    be opened repeatedly until the Owner/Staff revokes it or it expires.
    "expired" is derived at read time from expires_at, same as
    Invitation's, never stored. No relationship() (repo convention) —
    tenant_id/customer_id/created_by_user_id are plain FK columns,
    resolved via explicit crud lookups.
    """

    __tablename__ = "portal_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    """Table-ification of app/activity/models.py's ActivityEvent.

    Column names/types intentionally mirror the pydantic model so
    PostgresActivityRepository can map between them with no translation
    logic beyond str(uuid) <-> uuid.UUID.
    """

    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    # Stays nullable: seed rows and events logged from an anonymous /quote or
    # /estimate call have no tenant and are visible to no tenant's activity
    # feed — see ADR-029.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationRecord(Base):
    """Table-ification of app/notifications/models.py's Notification.

    Named NotificationRecord, not Notification, to avoid colliding with the
    pydantic model app.notifications.models.Notification that the API
    already returns — PostgresNotificationRepository converts between them.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    # Stays nullable: seed rows have no tenant and are visible to no tenant's
    # notification feed — see ADR-029.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="info")
    read: Mapped[bool] = mapped_column(Boolean, default=False)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
