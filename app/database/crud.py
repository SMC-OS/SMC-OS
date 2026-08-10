"""Minimal CRUD helpers backing the Postgres-backed repositories.

Sprint 002 only needs the operations app/activity and app/notifications
already perform against their in-memory repositories — no CRUD helpers for
customers/quotes/projects/materials/users are added here, since no API
surface uses those tables yet (see docs/SPRINTS/sprint-002.md).
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ActivityLog, NotificationRecord


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
