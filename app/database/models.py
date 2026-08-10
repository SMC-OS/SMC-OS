"""Core SQLAlchemy models for SIMO OS.

Sprint 002 — see docs/DATABASE_SCHEMA.md §2 for the source pydantic models
and informal shapes these are drawn from, and docs/DECISIONS.md ADR-013 for
why every table below carries a `tenant_id` column that isn't enforced yet
(no tenants table exists, so it's a plain nullable UUID column, not a FK).

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


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

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
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    """Table-ification of app/activity/models.py's ActivityEvent.

    Column names/types intentionally mirror the pydantic model so
    PostgresActivityRepository can map between them with no translation
    logic beyond str(uuid) <-> uuid.UUID.
    """

    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

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
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    title: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="info")
    read: Mapped[bool] = mapped_column(Boolean, default=False)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
