"""Minimal CRUD helpers backing the Postgres-backed repositories.

Sprint 002 added the operations app/activity and app/notifications need.
Sprint 003 added the small set app/auth needs against `users`. Sprint 004
added `customers` (app/customers/). Sprint 005 added `materials`
(app/materials/) — internal only, no API surface of its own. Sprint 006
adds `projects` (app/projects/), including a status-update helper — the
first CRUD write beyond create/list/get. No CRUD helpers for `quotes`
exist yet (see docs/DATABASE_SCHEMA.md).
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import ActivityLog, Customer, Material, NotificationRecord, Project, User


def create_activity_log(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    type: str,
    title: str,
    description: str | None,
    timestamp: datetime,
) -> ActivityLog:
    row = ActivityLog(
        id=id,
        tenant_id=tenant_id,
        type=type,
        title=title,
        description=description,
        timestamp=timestamp,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_activity_log(db: Session, limit: int = 20) -> list[ActivityLog]:
    stmt = select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(limit)
    return list(db.scalars(stmt))


def count_activity_log(db: Session) -> int:
    return db.query(ActivityLog).count()


def create_notification(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    title: str,
    message: str,
    type: str,
    timestamp: datetime,
    read: bool = False,
) -> NotificationRecord:
    row = NotificationRecord(
        id=id,
        tenant_id=tenant_id,
        title=title,
        message=message,
        type=type,
        timestamp=timestamp,
        read=read,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_notifications(db: Session, limit: int = 50) -> list[NotificationRecord]:
    stmt = select(NotificationRecord).order_by(NotificationRecord.timestamp.desc()).limit(limit)
    return list(db.scalars(stmt))


def count_notifications(db: Session) -> int:
    return db.query(NotificationRecord).count()


def mark_notification_read(db: Session, notification_id: uuid.UUID) -> NotificationRecord | None:
    row = db.get(NotificationRecord, notification_id)
    if row is None:
        return None
    row.read = True
    db.commit()
    db.refresh(row)
    return row


def create_user(
    db: Session,
    *,
    id: uuid.UUID,
    name: str,
    email: str,
    password_hash: str,
    role: str | None = None,
) -> User:
    row = User(id=id, name=name, email=email, password_hash=password_hash, role=role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return db.scalars(stmt).first()


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def count_users(db: Session) -> int:
    return db.query(User).count()


def create_customer(
    db: Session,
    *,
    id: uuid.UUID,
    name: str,
    email: str | None = None,
    phone: str | None = None,
) -> Customer:
    row = Customer(id=id, name=name, email=email, phone=phone)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_customer_by_id(db: Session, customer_id: uuid.UUID) -> Customer | None:
    return db.get(Customer, customer_id)


def list_customers(db: Session, limit: int = 20) -> list[Customer]:
    stmt = select(Customer).order_by(Customer.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def create_material(
    db: Session,
    *,
    id: uuid.UUID,
    name: str,
    category: str | None,
    thickness: str | None,
    slab_size: str | None,
    finish: str | None,
    price: float | None,
) -> Material:
    row = Material(
        id=id,
        name=name,
        category=category,
        thickness=thickness,
        slab_size=slab_size,
        finish=finish,
        price=price,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_materials(db: Session) -> list[Material]:
    stmt = select(Material).order_by(Material.category, Material.name, Material.thickness)
    return list(db.scalars(stmt))


def get_material_by_name_and_thickness(db: Session, name: str, thickness: str) -> Material | None:
    stmt = select(Material).where(
        func.lower(Material.name) == name.lower(),
        func.lower(Material.thickness) == thickness.lower(),
    )
    return db.scalars(stmt).first()


def count_materials(db: Session) -> int:
    return db.query(Material).count()


def create_project(
    db: Session,
    *,
    id: uuid.UUID,
    name: str,
    customer_id: uuid.UUID | None,
    notes: str | None,
    status: str,
) -> Project:
    row = Project(id=id, name=name, customer_id=customer_id, notes=notes, status=status)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_project_by_id(db: Session, project_id: uuid.UUID) -> Project | None:
    return db.get(Project, project_id)


def list_projects(db: Session, limit: int = 20) -> list[Project]:
    stmt = select(Project).order_by(Project.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def update_project_status(db: Session, project_id: uuid.UUID, status: str) -> Project | None:
    row = db.get(Project, project_id)
    if row is None:
        return None
    row.status = status
    db.commit()
    db.refresh(row)
    return row
