"""Minimal CRUD helpers backing the Postgres-backed repositories.

Sprint 002 added the operations app/activity and app/notifications need.
Sprint 003 added the small set app/auth needs against `users`. Sprint 004
added `customers` (app/customers/). Sprint 005 added `materials`
(app/materials/) — internal only, no API surface of its own. Sprint 006
added `projects` (app/projects/), including a status-update helper. Sprint
007 adds `quotes` (app/quotes/) — the last of the 7 tables to get real
CRUD, plus two aggregate helpers (count_quotes_today, sum_quotes_revenue)
backing the now-real /api/v1/dashboard. Sprint 008 adds `tenants`
(app/tenants/) — schema/CRUD only, no query above filters by tenant yet.
Sprint 011 adds `invitations` (app/invitations/) — the first table that
lets a tenant have more than one user.

Sprint 012 (ADR-029) — every customers/projects/quotes/activity_log/
notifications function below now takes a required `tenant_id` (except the
`create_*` helpers for quotes/activity_log/notifications, which keep it
optional — an anonymous /quote|/estimate call or a seed row has no
tenant) and filters/checks ownership by it. `materials` stays unfiltered
by design (shared reference catalogue, not tenant-owned data — see
docs/DECISIONS.md ADR-029). `tenants`/`invitations` CRUD is unchanged
(already correctly scoped or scoped at the router, respectively).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import (
    ActivityLog,
    Appointment,
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


def create_activity_log(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    type: str,
    title: str,
    description: str | None,
    timestamp: datetime,
    commit: bool = True,
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
    # Sprint 021 — commit=False lets a caller (currently only
    # ProjectService.convert_to_customer) fold this write into its own
    # transaction instead of committing here. Every existing caller keeps
    # the default, unchanged commit-here behavior.
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row


def list_activity_log(db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[ActivityLog]:
    stmt = (
        select(ActivityLog)
        .where(ActivityLog.tenant_id == tenant_id)
        .order_by(ActivityLog.timestamp.desc())
        .limit(limit)
    )
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
    recipient_user_id: uuid.UUID | None = None,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    commit: bool = True,
) -> NotificationRecord:
    row = NotificationRecord(
        id=id,
        tenant_id=tenant_id,
        title=title,
        message=message,
        type=type,
        timestamp=timestamp,
        read=read,
        recipient_user_id=recipient_user_id,
        source_type=source_type,
        source_id=source_id,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def get_notification_by_dedupe_key(db: Session, dedupe_key: str) -> NotificationRecord | None:
    stmt = select(NotificationRecord).where(NotificationRecord.dedupe_key == dedupe_key)
    return db.scalars(stmt).first()


def list_notifications(
    db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50
) -> list[NotificationRecord]:
    # Sprint 024 — tenant-wide broadcasts (recipient_user_id IS NULL, the
    # only kind that existed before this sprint) stay visible to every
    # tenant member, unchanged; a set recipient_user_id scopes a row to
    # exactly that user (docs/SPRINTS/sprint-024.md §6).
    stmt = (
        select(NotificationRecord)
        .where(
            NotificationRecord.tenant_id == tenant_id,
            (NotificationRecord.recipient_user_id.is_(None))
            | (NotificationRecord.recipient_user_id == user_id),
        )
        .order_by(NotificationRecord.timestamp.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def count_notifications(db: Session) -> int:
    return db.query(NotificationRecord).count()


def mark_notification_read(
    db: Session, notification_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> NotificationRecord | None:
    stmt = select(NotificationRecord).where(
        NotificationRecord.id == notification_id,
        NotificationRecord.tenant_id == tenant_id,
        (NotificationRecord.recipient_user_id.is_(None))
        | (NotificationRecord.recipient_user_id == user_id),
    )
    row = db.scalars(stmt).first()
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
    tenant_id: uuid.UUID,
    name: str,
    email: str,
    password_hash: str,
    role: str | None = None,
) -> User:
    row = User(
        id=id, tenant_id=tenant_id, name=name, email=email, password_hash=password_hash, role=role
    )
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


def create_customer(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    commit: bool = True,
) -> Customer:
    row = Customer(id=id, tenant_id=tenant_id, name=name, email=email, phone=phone)
    db.add(row)
    # Sprint 021 — commit=False lets a caller (currently only
    # ProjectService.convert_to_customer) fold this write into its own
    # transaction instead of committing here. Every existing caller keeps
    # the default, unchanged commit-here behavior. flush() still runs so
    # row.created_at (server_default) and row.id are populated for the
    # caller before its own commit.
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row


def get_customer_by_id(db: Session, customer_id: uuid.UUID, tenant_id: uuid.UUID) -> Customer | None:
    stmt = select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
    return db.scalars(stmt).first()


def list_customers(db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[Customer]:
    stmt = (
        select(Customer)
        .where(Customer.tenant_id == tenant_id)
        .order_by(Customer.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def count_customers(db: Session, tenant_id: uuid.UUID) -> int:
    return db.query(Customer).filter(Customer.tenant_id == tenant_id).count()


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
    tenant_id: uuid.UUID,
    name: str,
    customer_id: uuid.UUID | None,
    notes: str | None,
    status: str,
    quote_id: uuid.UUID | None = None,
) -> Project:
    row = Project(
        id=id,
        tenant_id=tenant_id,
        name=name,
        customer_id=customer_id,
        notes=notes,
        status=status,
        quote_id=quote_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_project_by_id(db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID) -> Project | None:
    stmt = select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    return db.scalars(stmt).first()


def get_project_by_quote_id(db: Session, quote_id: uuid.UUID, tenant_id: uuid.UUID) -> Project | None:
    stmt = select(Project).where(Project.quote_id == quote_id, Project.tenant_id == tenant_id)
    return db.scalars(stmt).first()


def list_projects(db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.tenant_id == tenant_id)
        .order_by(Project.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def list_projects_by_status(db: Session, status: str) -> list[Project]:
    """Sprint 024 (docs/SPRINTS/sprint-024.md) — deliberately not
    tenant-scoped: the follow-up automation is an internal job that scans
    every tenant, tagging each created notification with that Project's
    own tenant_id (never the caller's, since there is no caller)."""
    stmt = select(Project).where(Project.status == status)
    return list(db.scalars(stmt))


def count_projects(db: Session, tenant_id: uuid.UUID) -> int:
    return db.query(Project).filter(Project.tenant_id == tenant_id).count()


def update_project_status(
    db: Session,
    project_id: uuid.UUID,
    tenant_id: uuid.UUID,
    status: str,
    *,
    commit: bool = True,
) -> Project | None:
    stmt = select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    row = db.scalars(stmt).first()
    if row is None:
        return None
    row.status = status
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def update_project_assignment(
    db: Session,
    project_id: uuid.UUID,
    tenant_id: uuid.UUID,
    assigned_user_id: uuid.UUID | None,
    *,
    commit: bool = True,
) -> Project | None:
    stmt = select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    row = db.scalars(stmt).first()
    if row is None:
        return None
    row.assigned_user_id = assigned_user_id
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def update_project_customer(
    db: Session,
    project_id: uuid.UUID,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    commit: bool = True,
) -> Project | None:
    stmt = select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    row = db.scalars(stmt).first()
    if row is None:
        return None
    row.customer_id = customer_id
    # Sprint 021 — commit=False lets a caller (currently only
    # ProjectService.convert_to_customer) fold this write into its own
    # transaction instead of committing here. Every existing caller keeps
    # the default, unchanged commit-here behavior.
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row


def create_quote(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    material: str,
    thickness: str,
    kitchen_length: float,
    island: bool,
    waterfall: int,
    splashback: bool,
    upstands: bool,
    postcode: str | None,
    price_per_slab: float,
    price_before_vat: float,
    vat: float,
    total: float,
) -> Quote:
    row = Quote(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        material=material,
        thickness=thickness,
        kitchen_length=kitchen_length,
        island=island,
        waterfall=waterfall,
        splashback=splashback,
        upstands=upstands,
        postcode=postcode,
        price_per_slab=price_per_slab,
        price_before_vat=price_before_vat,
        vat=vat,
        total=total,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_quote_by_id(db: Session, quote_id: uuid.UUID, tenant_id: uuid.UUID) -> Quote | None:
    stmt = select(Quote).where(Quote.id == quote_id, Quote.tenant_id == tenant_id)
    return db.scalars(stmt).first()


def list_quotes(db: Session, tenant_id: uuid.UUID, limit: int = 20) -> list[Quote]:
    stmt = (
        select(Quote)
        .where(Quote.tenant_id == tenant_id)
        .order_by(Quote.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def count_quotes_today(db: Session, tenant_id: uuid.UUID) -> int:
    return (
        db.query(Quote)
        .filter(Quote.tenant_id == tenant_id, func.date(Quote.created_at) == date.today())
        .count()
    )


def sum_quotes_revenue(db: Session, tenant_id: uuid.UUID) -> float:
    total = db.query(func.sum(Quote.total)).filter(Quote.tenant_id == tenant_id).scalar()
    return float(total) if total is not None else 0.0


# Sprint 025 (docs/SPRINTS/sprint-025.md) — Business Command Centre
# aggregates. Each is a single grouped/aggregate SQL query, never a
# per-row Python loop, so none of these introduce an N+1 pattern
# regardless of how many Projects/Quotes/Appointments a tenant has.


def count_projects_by_status(db: Session, tenant_id: uuid.UUID) -> dict[str, int]:
    rows = (
        db.query(Project.status, func.count())
        .filter(Project.tenant_id == tenant_id)
        .group_by(Project.status)
        .all()
    )
    return {status: count for status, count in rows}


def count_quotes_by_status(db: Session, tenant_id: uuid.UUID) -> dict[str, int]:
    rows = (
        db.query(Quote.status, func.count())
        .filter(Quote.tenant_id == tenant_id)
        .group_by(Quote.status)
        .all()
    )
    return {status: count for status, count in rows}


def count_handed_off_projects(db: Session, tenant_id: uuid.UUID) -> int:
    # Project.quote_id is a nullable, unique FK (Sprint 020) — set exactly
    # when a quote has been handed off into this Project (docs/SPRINTS/
    # sprint-025.md §1). A single indexed count, no join to quotes needed.
    return (
        db.query(Project)
        .filter(Project.tenant_id == tenant_id, Project.quote_id.isnot(None))
        .count()
    )


def sum_approved_quotes_value(db: Session, tenant_id: uuid.UUID) -> float:
    total = (
        db.query(func.sum(Quote.total))
        .filter(Quote.tenant_id == tenant_id, Quote.status == "approved")
        .scalar()
    )
    return float(total) if total is not None else 0.0


def count_appointments_by_status(db: Session, tenant_id: uuid.UUID) -> dict[str, int]:
    rows = (
        db.query(Appointment.status, func.count())
        .filter(Appointment.tenant_id == tenant_id)
        .group_by(Appointment.status)
        .all()
    )
    return {status: count for status, count in rows}


def count_unread_follow_up_notifications(db: Session, tenant_id: uuid.UUID) -> int:
    # Tenant-wide, not scoped to a single recipient (docs/SPRINTS/
    # sprint-025.md §1/§3) — an operational "how much is outstanding
    # across the team" count, not a personal inbox count.
    return (
        db.query(NotificationRecord)
        .filter(
            NotificationRecord.tenant_id == tenant_id,
            NotificationRecord.source_type == "project",
            NotificationRecord.read.is_(False),
        )
        .count()
    )


def create_tenant(
    db: Session,
    *,
    id: uuid.UUID,
    name: str,
    slug: str,
    status: str = "active",
) -> Tenant:
    row = Tenant(id=id, name=name, slug=slug, status=status)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_tenant_by_id(db: Session, tenant_id: uuid.UUID) -> Tenant | None:
    return db.get(Tenant, tenant_id)


def get_tenant_by_slug(db: Session, slug: str) -> Tenant | None:
    stmt = select(Tenant).where(Tenant.slug == slug)
    return db.scalars(stmt).first()


def list_tenants(db: Session, limit: int = 20) -> list[Tenant]:
    stmt = select(Tenant).order_by(Tenant.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def create_invitation(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    invited_by_user_id: uuid.UUID,
    email: str,
    role: str,
    token_hash: str,
    expires_at: datetime,
    status: str = "pending",
) -> Invitation:
    row = Invitation(
        id=id,
        tenant_id=tenant_id,
        invited_by_user_id=invited_by_user_id,
        email=email,
        role=role,
        token_hash=token_hash,
        expires_at=expires_at,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_invitation_by_id(db: Session, invitation_id: uuid.UUID) -> Invitation | None:
    return db.get(Invitation, invitation_id)


def get_invitation_by_token_hash(db: Session, token_hash: str) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token_hash == token_hash)
    return db.scalars(stmt).first()


def list_invitations(
    db: Session, tenant_id: uuid.UUID, status: str | None = None, limit: int = 50
) -> list[Invitation]:
    stmt = select(Invitation).where(Invitation.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(Invitation.status == status)
    stmt = stmt.order_by(Invitation.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_pending_invitation(db: Session, tenant_id: uuid.UUID, email: str) -> Invitation | None:
    stmt = select(Invitation).where(
        Invitation.tenant_id == tenant_id,
        Invitation.email == email,
        Invitation.status == "pending",
    )
    return db.scalars(stmt).first()


def update_invitation_status(db: Session, invitation_id: uuid.UUID, status: str) -> Invitation | None:
    row = db.get(Invitation, invitation_id)
    if row is None:
        return None
    row.status = status
    db.commit()
    db.refresh(row)
    return row


def create_portal_link(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
    status: str = "active",
) -> PortalLink:
    row = PortalLink(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        created_by_user_id=created_by_user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_portal_link_by_id(db: Session, portal_link_id: uuid.UUID) -> PortalLink | None:
    return db.get(PortalLink, portal_link_id)


def get_portal_link_by_token_hash(db: Session, token_hash: str) -> PortalLink | None:
    stmt = select(PortalLink).where(PortalLink.token_hash == token_hash)
    return db.scalars(stmt).first()


def list_portal_links(
    db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None = None
) -> list[PortalLink]:
    stmt = select(PortalLink).where(PortalLink.tenant_id == tenant_id)
    if customer_id is not None:
        stmt = stmt.where(PortalLink.customer_id == customer_id)
    stmt = stmt.order_by(PortalLink.created_at.desc())
    return list(db.scalars(stmt))


def update_portal_link_status(db: Session, portal_link_id: uuid.UUID, status: str) -> PortalLink | None:
    row = db.get(PortalLink, portal_link_id)
    if row is None:
        return None
    row.status = status
    db.commit()
    db.refresh(row)
    return row


def create_document(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
    original_filename: str,
    storage_filename: str,
    content_type: str,
    size_bytes: int,
) -> Document:
    row = Document(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        uploaded_by_user_id=uploaded_by_user_id,
        original_filename=original_filename,
        storage_filename=storage_filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_document_by_id(db: Session, document_id: uuid.UUID) -> Document | None:
    return db.get(Document, document_id)


def list_documents(
    db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None = None
) -> list[Document]:
    stmt = select(Document).where(Document.tenant_id == tenant_id)
    if customer_id is not None:
        stmt = stmt.where(Document.customer_id == customer_id)
    stmt = stmt.order_by(Document.created_at.desc())
    return list(db.scalars(stmt))


def create_message(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    sender_type: str,
    body: str,
    sender_user_id: uuid.UUID | None = None,
) -> Message:
    row = Message(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        sender_user_id=sender_user_id,
        sender_type=sender_type,
        body=body,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_messages_by_customer(
    db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> list[Message]:
    # Ascending, unlike list_documents/list_portal_links' newest-first
    # convention — a message thread reads top-to-bottom chronologically.
    stmt = (
        select(Message)
        .where(Message.tenant_id == tenant_id, Message.customer_id == customer_id)
        .order_by(Message.created_at.asc())
    )
    return list(db.scalars(stmt))


def list_projects_by_customer(
    db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.tenant_id == tenant_id, Project.customer_id == customer_id)
        .order_by(Project.created_at.desc())
    )
    return list(db.scalars(stmt))


def list_quotes_by_customer(db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> list[Quote]:
    stmt = (
        select(Quote)
        .where(Quote.tenant_id == tenant_id, Quote.customer_id == customer_id)
        .order_by(Quote.created_at.desc())
    )
    return list(db.scalars(stmt))


def create_appointment(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    scheduled_at: datetime,
    notes: str | None = None,
    commit: bool = True,
) -> Appointment:
    row = Appointment(
        id=id,
        tenant_id=tenant_id,
        project_id=project_id,
        created_by_user_id=created_by_user_id,
        scheduled_at=scheduled_at,
        notes=notes,
    )
    db.add(row)
    # Sprint 022 — commit=False lets a caller (ProjectService's Sprint 021
    # convention, reused by AppointmentService) fold this write into its
    # own transaction instead of committing here. Every existing caller
    # keeps the default, unchanged commit-here behavior.
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row


def get_appointment_by_id(
    db: Session, appointment_id: uuid.UUID, tenant_id: uuid.UUID
) -> Appointment | None:
    stmt = select(Appointment).where(
        Appointment.id == appointment_id, Appointment.tenant_id == tenant_id
    )
    return db.scalars(stmt).first()


def list_appointments_by_project(
    db: Session, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> list[Appointment]:
    stmt = (
        select(Appointment)
        .where(Appointment.tenant_id == tenant_id, Appointment.project_id == project_id)
        .order_by(Appointment.scheduled_at.asc())
    )
    return list(db.scalars(stmt))


def update_appointment_status(
    db: Session,
    appointment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    status: str,
    commit: bool = True,
) -> Appointment | None:
    stmt = select(Appointment).where(
        Appointment.id == appointment_id, Appointment.tenant_id == tenant_id
    )
    row = db.scalars(stmt).first()
    if row is None:
        return None
    row.status = status
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row
