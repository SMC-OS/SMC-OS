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

from sqlalchemy import func, or_ as sa_or, select
from sqlalchemy.orm import Session

from app.database.models import (
    ActivityLog,
    Appointment,
    Automation,
    AutomationRun,
    Communication,
    Customer,
    Document,
    EmailSuppression,
    Invitation,
    Material,
    Message,
    NotificationRecord,
    PipelineStage,
    PortalLink,
    ProcessedEmailEvent,
    ProcessedStripeEvent,
    Project,
    Quote,
    QuoteItem,
    Subscription,
    Task,
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
    # Sprint 036 (Workstream D) — the construction customer record. Every
    # one is keyword-only with a default, so every existing caller
    # (CustomerService.create, ProjectService.convert_to_customer) keeps
    # working untouched and a three-field customer stays a valid customer.
    customer_type: str = "individual",
    company_name: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    city: str | None = None,
    postcode: str | None = None,
    notes: str | None = None,
    commit: bool = True,
) -> Customer:
    row = Customer(
        id=id,
        tenant_id=tenant_id,
        name=name,
        email=email,
        phone=phone,
        customer_type=customer_type,
        company_name=company_name,
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        postcode=postcode,
        notes=notes,
    )
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
    # Sprint 036 (Workstream F). Keyword-only with defaults, so the
    # quote-handoff caller and every existing test keep working with the
    # original signature.
    project_type: str | None = None,
    description: str | None = None,
    site_address_line1: str | None = None,
    site_address_line2: str | None = None,
    site_city: str | None = None,
    site_postcode: str | None = None,
    start_date=None,
    target_completion_date=None,
    estimated_value: float | None = None,
) -> Project:
    row = Project(
        id=id,
        tenant_id=tenant_id,
        name=name,
        customer_id=customer_id,
        notes=notes,
        status=status,
        quote_id=quote_id,
        project_type=project_type,
        description=description,
        site_address_line1=site_address_line1,
        site_address_line2=site_address_line2,
        site_city=site_city,
        site_postcode=site_postcode,
        start_date=start_date,
        target_completion_date=target_completion_date,
        estimated_value=estimated_value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# Sprint 036 (Workstream D/F) — the first partial-update helpers in this
# module. Both take an already-validated dict of column -> value from
# their service and apply only the keys present, so "field omitted" and
# "field explicitly set to null" stay distinguishable all the way from the
# HTTP body to the row (see CustomerUpdate/ProjectUpdate's
# model_dump(exclude_unset=True)).
#
# The allowlists are the point: a caller cannot reach tenant_id, id,
# created_at or status through these, so no partial update can move a row
# between tenants or bypass the status-transition rules in
# ProjectService.update_status.
_CUSTOMER_UPDATABLE = frozenset(
    {
        "name",
        "email",
        "phone",
        "customer_type",
        "company_name",
        "address_line1",
        "address_line2",
        "city",
        "postcode",
        "notes",
    }
)

_PROJECT_UPDATABLE = frozenset(
    {
        "name",
        "notes",
        "customer_id",
        "project_type",
        "description",
        "site_address_line1",
        "site_address_line2",
        "site_city",
        "site_postcode",
        "start_date",
        "target_completion_date",
        "estimated_value",
    }
)


def update_customer(
    db: Session, customer_id: uuid.UUID, tenant_id: uuid.UUID, changes: dict
) -> Customer | None:
    row = get_customer_by_id(db, customer_id, tenant_id)
    if row is None:
        return None
    for field, value in changes.items():
        if field in _CUSTOMER_UPDATABLE:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


def update_project(
    db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID, changes: dict
) -> Project | None:
    row = get_project_by_id(db, project_id, tenant_id)
    if row is None:
        return None
    for field, value in changes.items():
        if field in _PROJECT_UPDATABLE:
            setattr(row, field, value)
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


def create_general_quote(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    currency: str,
    fields: dict,
) -> Quote:
    """Sprint 036 (Workstream E) — the general construction quote's own
    INSERT, separate from create_quote() above rather than adding a dozen
    more keyword arguments to it.

    They are separate because they write genuinely different rows.
    create_quote() writes a stone quote: every slab column populated,
    quote_kind 'stone'. This writes a general quote: every slab column
    left NULL, quote_kind 'general'. Folding both into one function with
    twenty-odd optional parameters would make it possible to construct a
    row that is neither — a "general" quote carrying a half-populated
    material, or a stone quote with no dimensions — which is exactly the
    state the quote_kind discriminator exists to make unrepresentable.

    `fields` is a dict of already-validated column values from
    QuoteService, filtered through _GENERAL_QUOTE_COLUMNS so a caller
    cannot reach tenant_id, status or a slab column through it.
    """
    row = Quote(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        quote_kind="general",
        currency=currency,
        # The pre-Sprint-036 flag columns are frozen at their stone
        # meaning and are not part of a general quote at all. They are
        # set explicitly rather than left to the server default so it is
        # visible here that their absence is a decision, not an oversight.
        island=False,
        waterfall=0,
        splashback=False,
        upstands=False,
        **{key: value for key, value in fields.items() if key in _GENERAL_QUOTE_COLUMNS},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# The only columns a general-quote create/update may write. Everything
# else on `quotes` — tenant_id, customer_id, quote_kind, status,
# approved_*, and every slab column — is either set explicitly by the
# service or off limits to a client-supplied payload entirely.
_GENERAL_QUOTE_COLUMNS = frozenset(
    {
        "title",
        "trade",
        "site_address_line1",
        "site_address_line2",
        "site_city",
        "site_postcode",
        "scope_of_works",
        "notes",
        "exclusions",
        "terms",
        "valid_until",
        "postcode",
        "vat_rate",
        "subtotal",
        "discount_amount",
        "price_before_vat",
        "vat",
        "total",
    }
)


def update_general_quote(
    db: Session, quote_id: uuid.UUID, tenant_id: uuid.UUID, changes: dict
) -> Quote | None:
    """Sprint 036 — partial update of a general quote's envelope and
    recomputed totals. Same allowlist as create: `customer_id` is applied
    separately by the service (it needs a tenant-ownership check the
    allowlist cannot express), and no key outside
    _GENERAL_QUOTE_COLUMNS can be written through here at all."""
    row = get_quote_by_id(db, quote_id, tenant_id)
    if row is None:
        return None
    for field, value in changes.items():
        if field in _GENERAL_QUOTE_COLUMNS or field == "customer_id":
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


def replace_quote_items(db: Session, quote: Quote, items: list[dict]) -> None:
    """Sprint 036 — wholesale replacement of a quote's line items.

    Uses the existing `Quote.items` relationship with its
    delete-orphan cascade (the one relationship() in this schema) rather
    than a bulk DELETE, so ordering, the cascade and the identity map stay
    consistent with how items are read everywhere else. One commit, so a
    failed replacement leaves the previous set intact rather than a quote
    with no lines.
    """
    quote.items.clear()
    db.flush()
    for index, item in enumerate(items):
        quote.items.append(QuoteItem(id=uuid.uuid4(), position=index, **item))
    db.commit()
    db.refresh(quote)


def mark_quote_sent(
    db: Session, quote_id: uuid.UUID, tenant_id: uuid.UUID, sent_at: datetime
) -> Quote | None:
    row = get_quote_by_id(db, quote_id, tenant_id)
    if row is None:
        return None
    row.status = "sent"
    row.sent_at = sent_at
    db.commit()
    db.refresh(row)
    return row


def list_projects_with_start_date(db: Session) -> list[Project]:
    """Sprint 036 — every project that has a start date at all, for the
    automation scan. Deliberately not tenant-scoped, same rationale as
    list_projects_by_status (Sprint 024): the job has no caller. The scan
    itself groups rules by tenant and only ever evaluates a project
    against its own workspace's rules."""
    stmt = select(Project).where(Project.start_date.is_not(None))
    return list(db.scalars(stmt))


def list_projects_in_date_window(
    db: Session, tenant_id: uuid.UUID, start: date, end: date
) -> list[Project]:
    """Sprint 036 (Workstream K) — projects whose start OR target
    completion date falls in the window. Both are returned by the same
    query so the calendar makes one round trip and then emits one item per
    date it finds, rather than two queries the caller has to merge."""
    stmt = (
        select(Project)
        .where(
            Project.tenant_id == tenant_id,
            sa_or(
                Project.start_date.between(start, end),
                Project.target_completion_date.between(start, end),
            ),
        )
        .order_by(Project.start_date.asc().nullslast())
    )
    return list(db.scalars(stmt))


def list_quotes_expiring_in_window(
    db: Session, tenant_id: uuid.UUID, start: date, end: date
) -> list[Quote]:
    stmt = (
        select(Quote)
        .where(
            Quote.tenant_id == tenant_id,
            Quote.valid_until.is_not(None),
            Quote.valid_until.between(start, end),
        )
        .order_by(Quote.valid_until.asc())
    )
    return list(db.scalars(stmt))


def list_appointments_in_window(
    db: Session, tenant_id: uuid.UUID, start: datetime, end: datetime
) -> list[Appointment]:
    stmt = (
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.scheduled_at >= start,
            Appointment.scheduled_at <= end,
        )
        .order_by(Appointment.scheduled_at.asc())
    )
    return list(db.scalars(stmt))


def list_quotes_by_status(db: Session, status: str) -> list[Quote]:
    """Sprint 036 — deliberately NOT tenant-scoped, for exactly the same
    reason as list_projects_by_status (Sprint 024): the automation scan job
    has no caller and therefore no tenant, and tags every side effect with
    the subject row's own tenant_id."""
    stmt = select(Quote).where(Quote.status == status)
    return list(db.scalars(stmt))


def create_quote(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    material: str,
    thickness: str,
    kitchen_length: float,
    quantity: int,
    length_mm: float,
    width_mm: float,
    thickness_mm: float | None,
    unit_input: str,
    island: bool,
    waterfall: int,
    splashback: bool,
    splashback_length_mm: float | None,
    upstands: bool,
    upstands_length_mm: float | None,
    postcode: str | None,
    price_per_slab: float,
    price_before_vat: float,
    vat: float,
    total: float,
    # Sprint 036 — keyword-only with defaults so every existing caller and
    # test that predates this sprint keeps working with the old signature.
    currency: str = "GBP",
    subtotal: float | None = None,
) -> Quote:
    row = Quote(
        id=id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        quote_kind="stone",
        currency=currency,
        subtotal=subtotal,
        material=material,
        thickness=thickness,
        kitchen_length=kitchen_length,
        quantity=quantity,
        length_mm=length_mm,
        width_mm=width_mm,
        thickness_mm=thickness_mm,
        unit_input=unit_input,
        island=island,
        waterfall=waterfall,
        splashback=splashback,
        splashback_length_mm=splashback_length_mm,
        upstands=upstands,
        upstands_length_mm=upstands_length_mm,
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


def create_quote_items(db: Session, items: list[dict]) -> list[QuoteItem]:
    """Bulk-creates the QuoteItem rows for a just-created Quote (Sprint
    033, Workstream C). Each dict must include `quote_id`; `id`/
    `created_at` are filled in if not already present. One commit for
    the whole batch — callers create the Quote header first, in the same
    request, so there's nothing to roll back independently here."""
    rows = []
    for item in items:
        item = {**item}
        item.setdefault("id", uuid.uuid4())
        rows.append(QuoteItem(**item))
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


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


# Sprint 032 (Workstream A) — subscriptions/billing.


def get_subscription_by_tenant_id(db: Session, tenant_id: uuid.UUID) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
    return db.scalars(stmt).first()


def get_subscription_by_stripe_subscription_id(
    db: Session, stripe_subscription_id: str
) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    return db.scalars(stmt).first()


def get_subscription_by_stripe_customer_id(
    db: Session, stripe_customer_id: str
) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.stripe_customer_id == stripe_customer_id)
    return db.scalars(stmt).first()


def upsert_subscription(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    plan: str,
    billing_period: str,
    status: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    stripe_price_id: str | None = None,
    current_period_end=None,
    cancel_at_period_end: bool = False,
) -> Subscription:
    row = get_subscription_by_tenant_id(db, tenant_id)
    if row is None:
        row = Subscription(id=uuid.uuid4(), tenant_id=tenant_id)
        db.add(row)

    row.plan = plan
    row.billing_period = billing_period
    row.status = status
    if stripe_customer_id is not None:
        row.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id is not None:
        row.stripe_subscription_id = stripe_subscription_id
    if stripe_price_id is not None:
        row.stripe_price_id = stripe_price_id
    row.current_period_end = current_period_end
    row.cancel_at_period_end = cancel_at_period_end

    db.commit()
    db.refresh(row)
    return row


def mark_stripe_event_processed(db: Session, event_id: str, event_type: str) -> bool:
    """Returns True if this call recorded the event (first delivery),
    False if it was already processed (a retried webhook delivery) — the
    caller must skip re-applying side effects in the False case."""
    if db.get(ProcessedStripeEvent, event_id) is not None:
        return False
    db.add(ProcessedStripeEvent(id=event_id, event_type=event_type))
    db.commit()
    return True


# ---------------------------------------------------------------------
# Sprint 036 — tasks, automations and automation runs.
# ---------------------------------------------------------------------


def create_task(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    title: str,
    body: str | None = None,
    status: str = "open",
    due_at: datetime | None = None,
    assigned_user_id: uuid.UUID | None = None,
    created_by_user_id: uuid.UUID | None = None,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> Task:
    row = Task(
        id=id,
        tenant_id=tenant_id,
        title=title,
        body=body,
        status=status,
        due_at=due_at,
        assigned_user_id=assigned_user_id,
        created_by_user_id=created_by_user_id,
        source_type=source_type,
        source_id=source_id,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_task_by_id(db: Session, task_id: uuid.UUID, tenant_id: uuid.UUID) -> Task | None:
    stmt = select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
    return db.scalars(stmt).first()


def get_task_by_dedupe_key(db: Session, dedupe_key: str) -> Task | None:
    """Not tenant-scoped, exactly like get_notification_by_dedupe_key
    (Sprint 024): dedupe_key is globally unique by construction (it embeds
    the automation id, which embeds the tenant), and the constraint being
    global is what makes it a real backstop."""
    return db.scalars(select(Task).where(Task.dedupe_key == dedupe_key)).first()


def list_tasks(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[Task]:
    stmt = select(Task).where(Task.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    # Due first (soonest at the top), then newest. NULLS LAST so an
    # undated task never outranks one that is actually due.
    stmt = stmt.order_by(Task.due_at.asc().nullslast(), Task.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def list_tasks_in_window(
    db: Session, tenant_id: uuid.UUID, start: datetime, end: datetime
) -> list[Task]:
    stmt = (
        select(Task)
        .where(
            Task.tenant_id == tenant_id,
            Task.due_at.is_not(None),
            Task.due_at >= start,
            Task.due_at <= end,
        )
        .order_by(Task.due_at.asc())
    )
    return list(db.scalars(stmt))


def count_open_tasks(db: Session, tenant_id: uuid.UUID) -> int:
    return (
        db.query(Task)
        .filter(Task.tenant_id == tenant_id, Task.status == "open")
        .count()
    )


def update_task_status(
    db: Session,
    task_id: uuid.UUID,
    tenant_id: uuid.UUID,
    status: str,
    completed_at: datetime | None,
) -> Task | None:
    row = get_task_by_id(db, task_id, tenant_id)
    if row is None:
        return None
    row.status = status
    row.completed_at = completed_at
    db.commit()
    db.refresh(row)
    return row


def create_automation(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    name: str,
    description: str | None,
    trigger_type: str,
    conditions: list,
    actions: list,
    enabled: bool = True,
    template_key: str | None = None,
    created_by_user_id: uuid.UUID | None = None,
) -> Automation:
    row = Automation(
        id=id,
        tenant_id=tenant_id,
        name=name,
        description=description,
        trigger_type=trigger_type,
        conditions=conditions,
        actions=actions,
        enabled=enabled,
        template_key=template_key,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_automation_by_id(
    db: Session, automation_id: uuid.UUID, tenant_id: uuid.UUID
) -> Automation | None:
    stmt = select(Automation).where(
        Automation.id == automation_id, Automation.tenant_id == tenant_id
    )
    return db.scalars(stmt).first()


def list_automations(db: Session, tenant_id: uuid.UUID, limit: int = 100) -> list[Automation]:
    stmt = (
        select(Automation)
        .where(Automation.tenant_id == tenant_id)
        .order_by(Automation.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def list_enabled_automations_for_trigger(
    db: Session, tenant_id: uuid.UUID, trigger_type: str
) -> list[Automation]:
    """The dispatch query. Tenant-scoped and enabled-only, both in SQL
    rather than filtered in Python: an automation belonging to another
    tenant must never be loaded at all, not merely skipped after loading."""
    stmt = (
        select(Automation)
        .where(
            Automation.tenant_id == tenant_id,
            Automation.trigger_type == trigger_type,
            Automation.enabled.is_(True),
        )
        .order_by(Automation.created_at.asc())
    )
    return list(db.scalars(stmt))


def list_enabled_automations_by_trigger_all_tenants(
    db: Session, trigger_type: str
) -> list[Automation]:
    """Deliberately NOT tenant-scoped — the same rationale as
    list_projects_by_status (Sprint 024): the scan job has no caller and
    therefore no tenant. Every side effect it creates is tagged with the
    subject row's own tenant_id, never a caller's."""
    stmt = select(Automation).where(
        Automation.trigger_type == trigger_type, Automation.enabled.is_(True)
    )
    return list(db.scalars(stmt))


def update_automation(
    db: Session, automation_id: uuid.UUID, tenant_id: uuid.UUID, changes: dict
) -> Automation | None:
    row = get_automation_by_id(db, automation_id, tenant_id)
    if row is None:
        return None
    for field, value in changes.items():
        if field in _AUTOMATION_UPDATABLE:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


_AUTOMATION_UPDATABLE = frozenset(
    {"name", "description", "trigger_type", "conditions", "actions", "enabled"}
)


def delete_automation(db: Session, automation_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    row = get_automation_by_id(db, automation_id, tenant_id)
    if row is None:
        return False
    # Runs are deleted first: automation_runs.automation_id is a NOT NULL
    # FK, so the parent cannot go while history references it. The history
    # of a deleted rule has no reader — the rule it explains is gone — so
    # cascading is correct here rather than orphaning it.
    db.query(AutomationRun).filter(AutomationRun.automation_id == automation_id).delete()
    db.delete(row)
    db.commit()
    return True


def create_automation_run(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    automation_id: uuid.UUID,
    trigger_type: str,
    subject_type: str | None,
    subject_id: uuid.UUID | None,
    status: str,
    detail: str | None,
    dedupe_key: str | None,
) -> AutomationRun:
    row = AutomationRun(
        id=id,
        tenant_id=tenant_id,
        automation_id=automation_id,
        trigger_type=trigger_type,
        subject_type=subject_type,
        subject_id=subject_id,
        status=status,
        detail=detail,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_automation_run_by_dedupe_key(db: Session, dedupe_key: str) -> AutomationRun | None:
    return db.scalars(
        select(AutomationRun).where(AutomationRun.dedupe_key == dedupe_key)
    ).first()


def list_automation_runs(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    automation_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[AutomationRun]:
    stmt = select(AutomationRun).where(AutomationRun.tenant_id == tenant_id)
    if automation_id is not None:
        stmt = stmt.where(AutomationRun.automation_id == automation_id)
    stmt = stmt.order_by(AutomationRun.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


# Sprint 038 — communications (outbound email ledger). See
# app/database/models.py's Communication docstring for why this isn't
# named `Message`/`get_message_*` (that name is app/messages's portal-chat
# feature already).


def create_communication(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    message_type: str,
    recipient: str,
    sender_identity: str,
    subject: str,
    body_html: str,
    body_text: str,
    dedupe_key: str,
    channel: str = "email",
    direction: str = "outbound",
    status: str = "draft",
    customer_id: uuid.UUID | None = None,
    quote_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    invitation_id: uuid.UUID | None = None,
    automation_id: uuid.UUID | None = None,
    automation_run_id: uuid.UUID | None = None,
) -> Communication:
    row = Communication(
        id=id,
        tenant_id=tenant_id,
        message_type=message_type,
        recipient=recipient,
        sender_identity=sender_identity,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        dedupe_key=dedupe_key,
        channel=channel,
        direction=direction,
        status=status,
        customer_id=customer_id,
        quote_id=quote_id,
        project_id=project_id,
        invitation_id=invitation_id,
        automation_id=automation_id,
        automation_run_id=automation_run_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_communication_by_dedupe_key(
    db: Session, tenant_id: uuid.UUID, dedupe_key: str
) -> Communication | None:
    stmt = select(Communication).where(
        Communication.tenant_id == tenant_id, Communication.dedupe_key == dedupe_key
    )
    return db.scalars(stmt).first()


def update_communication_result(
    db: Session,
    communication_id: uuid.UUID,
    *,
    status: str,
    provider: str | None = None,
    provider_message_id: str | None = None,
    failure_category: str | None = None,
    failure_detail: str | None = None,
    last_attempted_at: datetime | None = None,
    increment_attempt: bool = True,
) -> Communication | None:
    row = db.get(Communication, communication_id)
    if row is None:
        return None
    row.status = status
    if provider is not None:
        row.provider = provider
    row.provider_message_id = provider_message_id
    row.failure_category = failure_category
    row.failure_detail = failure_detail
    if last_attempted_at is not None:
        row.last_attempted_at = last_attempted_at
    if increment_attempt:
        row.attempt_count += 1
    db.commit()
    db.refresh(row)
    return row


def list_communications(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    customer_id: uuid.UUID | None = None,
    quote_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    invitation_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[Communication]:
    stmt = select(Communication).where(Communication.tenant_id == tenant_id)
    if customer_id is not None:
        stmt = stmt.where(Communication.customer_id == customer_id)
    if quote_id is not None:
        stmt = stmt.where(Communication.quote_id == quote_id)
    if project_id is not None:
        stmt = stmt.where(Communication.project_id == project_id)
    if invitation_id is not None:
        stmt = stmt.where(Communication.invitation_id == invitation_id)
    stmt = stmt.order_by(Communication.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_latest_communication_for_invitation(
    db: Session, tenant_id: uuid.UUID, invitation_id: uuid.UUID
) -> Communication | None:
    stmt = (
        select(Communication)
        .where(Communication.tenant_id == tenant_id, Communication.invitation_id == invitation_id)
        .order_by(Communication.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def get_email_suppression(db: Session, tenant_id: uuid.UUID, email: str) -> EmailSuppression | None:
    stmt = select(EmailSuppression).where(
        EmailSuppression.tenant_id == tenant_id, EmailSuppression.email == email
    )
    return db.scalars(stmt).first()


def create_email_suppression(
    db: Session,
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,
    email: str,
    reason: str,
    source_communication_id: uuid.UUID | None = None,
) -> EmailSuppression:
    row = EmailSuppression(
        id=id,
        tenant_id=tenant_id,
        email=email,
        reason=reason,
        source_communication_id=source_communication_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_email_suppressions(db: Session, tenant_id: uuid.UUID, limit: int = 100) -> list[EmailSuppression]:
    stmt = (
        select(EmailSuppression)
        .where(EmailSuppression.tenant_id == tenant_id)
        .order_by(EmailSuppression.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def get_communication_by_provider_message_id(db: Session, provider_message_id: str) -> Communication | None:
    """Not tenant-scoped at lookup — the webhook that calls this doesn't
    know a tenant. Safe: `provider_message_id` is the provider's own
    globally-unique id for one specific send, generated once and never
    guessable/shared, so at most one row can ever match; the caller reads
    `tenant_id` off the row it finds rather than assuming one."""
    stmt = select(Communication).where(Communication.provider_message_id == provider_message_id)
    return db.scalars(stmt).first()


def mark_email_event_processed(db: Session, event_id: str, event_type: str) -> bool:
    """Returns True if this call recorded the event (first delivery),
    False if it was already processed (a retried webhook delivery) — the
    caller must skip re-applying side effects in the False case. Same
    shape as mark_stripe_event_processed."""
    if db.get(ProcessedEmailEvent, event_id) is not None:
        return False
    db.add(ProcessedEmailEvent(id=event_id, event_type=event_type))
    db.commit()
    return True


def list_retryable_communications(db: Session, *, limit: int = 100) -> list[Communication]:
    """Failed sends a retry worker should attempt again — `transient`
    (the provider itself signalled "try later") or `unavailable` (no
    provider was configured at send time, which may no longer be true).
    Deliberately excludes `permanent` (a retry cannot fix a rejected
    request) and `suppressed` (retrying would defeat the suppression
    list's purpose). Not tenant-scoped — this is a scheduled job with no
    caller, same rationale as list_quotes_by_status/
    list_projects_with_start_date; each row still carries its own
    tenant_id for the retry itself to use."""
    stmt = (
        select(Communication)
        .where(
            Communication.status == "failed",
            Communication.failure_category.in_(["transient", "unavailable"]),
        )
        .order_by(Communication.last_attempted_at.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


# --- Pipeline stages (Sprint 039, Workstream D) -------------------------
#
# A tenant's own project pipeline. Always read whole and ordered — this is
# configuration for one tenant, never a table anything queries into or
# joins against, which is why `projects.status` stays a plain String with
# no FK to here (see PipelineStage's own docstring).


def list_pipeline_stages(db: Session, tenant_id: uuid.UUID) -> list[PipelineStage]:
    stmt = (
        select(PipelineStage)
        .where(PipelineStage.tenant_id == tenant_id)
        .order_by(PipelineStage.position)
    )
    return list(db.scalars(stmt))


def create_pipeline_stages(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    stages: list[dict],
    template_key: str | None = None,
    commit: bool = True,
) -> list[PipelineStage]:
    rows = [
        PipelineStage(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            key=stage["key"],
            label=stage["label"],
            role=stage["role"],
            position=stage["position"],
            template_key=template_key,
        )
        for stage in stages
    ]
    db.add_all(rows)
    if commit:
        db.commit()
    else:
        db.flush()
    return rows


def delete_pipeline_stages(db: Session, tenant_id: uuid.UUID, *, commit: bool = True) -> None:
    db.query(PipelineStage).filter(PipelineStage.tenant_id == tenant_id).delete(
        synchronize_session=False
    )
    if commit:
        db.commit()
    else:
        db.flush()


def move_projects_to_stage(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    from_key: str,
    to_key: str,
    commit: bool = True,
) -> int:
    """Bulk-move every project on one stage to another, within one tenant.

    Only ever called by pipeline_config.apply_template, i.e. only when a
    person has explicitly asked to switch their pipeline having been shown
    the mapping first.
    """
    moved = (
        db.query(Project)
        .filter(Project.tenant_id == tenant_id, Project.status == from_key)
        .update({Project.status: to_key}, synchronize_session=False)
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return moved


def list_projects_in_role(db: Session, role: str) -> list[Project]:
    """Every project, across every tenant, sitting at a stage with `role`.

    The cross-tenant counterpart of `list_projects_by_status`, for the
    scheduled jobs that have no caller and therefore no tenant of their
    own (app/notifications/follow_up_service.py, app/automations/scan.py).
    Joins each project to its *own* tenant's pipeline, so "the first
    stage" resolves per tenant rather than to one shared literal.

    A project whose tenant has no configured stages matches nothing here.
    That is correct rather than a gap: every tenant is seeded at creation
    (app/tenants/service.py) and every pre-existing one was seeded by
    Sprint 039's migration, so an unseeded tenant means something is
    genuinely wrong — and a follow-up job silently inventing stages for it
    would hide that.
    """
    stmt = (
        select(Project)
        .join(
            PipelineStage,
            (PipelineStage.tenant_id == Project.tenant_id)
            & (PipelineStage.key == Project.status),
        )
        .where(PipelineStage.role == role)
    )
    return list(db.scalars(stmt))
