"""Minimal CRUD helpers backing the Postgres-backed repositories.

Sprint 002 added the operations app/activity and app/notifications need.
Sprint 003 adds the small set app/auth needs against `users` (create,
look up by email/id, count — for the login flow and the seed guard). No
CRUD helpers for customers/quotes/projects/materials exist yet — no API
surface uses those tables (see docs/DATABASE_SCHEMA.md).
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ActivityLog, NotificationRecord, User


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
