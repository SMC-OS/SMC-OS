"""Service layer for public demo-request submission (Sprint 041; Phase B
adds follow-up).

A demo request is a sales lead for GeoCore itself, not data belonging to
any customer workspace. Phase B makes it visible and actionable without a
second, parallel CRM: when settings.platform_sales_tenant_id names
GeoCore's own sales workspace, each request

1. becomes (or updates) a company customer record in that workspace's
   existing CRM, carrying every detail the prospect gave;
2. adds a "Demo request received" entry to that workspace's activity feed;
3. emails that workspace's verified Owners a sales notification; and
4. emails the prospect a confirmation.

All four are best-effort: the request row is committed first, and nothing
after it can fail the public form. With no sales workspace configured,
only the row is stored and nobody is emailed — no recipient is guessed.
This is not a separate "Try demo" sandbox: /demo in the app is a local,
fully synthetic workspace and never touches this module.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.models import UserRole
from app.communications.models import CommunicationType
from app.communications.service import DeliveryService, delivery_service
from app.communications.templates import (
    render_demo_request_confirmation,
    render_demo_request_sales_notification,
)
from app.core.config import settings
from app.database import crud
from app.database.models import Customer, DemoRequest, Tenant
from app.demo_requests.models import DemoRequestCreate

logger = logging.getLogger("simo_os")


def create_demo_request(
    db: Session, data: DemoRequestCreate, delivery: DeliveryService | None = None
) -> DemoRequest | None:
    """Persists a demo request, then runs the sales follow-up. Returns None
    (nothing written, nobody emailed) when the honeypot field was filled —
    the caller still returns a normal success response so a bot gets no
    signal that it was caught."""
    if data.website:
        return None

    row = DemoRequest(
        id=uuid.uuid4(),
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        company_name=data.company_name,
        team_size=data.team_size,
        trades=data.trades,
        current_system=data.current_system,
        message=data.message,
        preferred_contact_method=data.preferred_contact_method,
        status="new",
        source="marketing_homepage",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    try:
        _follow_up(db, row, delivery or delivery_service)
    except Exception:  # noqa: BLE001 — the stored request must never be lost to a follow-up failure
        logger.exception("Demo request follow-up failed", extra={"event": "demo_request_follow_up_failed"})
        db.rollback()
    return row


def _sales_tenant(db: Session) -> Tenant | None:
    raw = (settings.platform_sales_tenant_id or "").strip()
    if not raw:
        return None
    try:
        tenant_id = uuid.UUID(raw)
    except ValueError:
        logger.warning("PLATFORM_SALES_TENANT_ID is not a valid id; demo follow-up skipped")
        return None
    tenant = crud.get_tenant_by_id(db, tenant_id)
    if tenant is None:
        logger.warning("PLATFORM_SALES_TENANT_ID names no existing workspace; demo follow-up skipped")
    return tenant


def _summary_lines(row: DemoRequest) -> list[str]:
    lines = [
        f"Name: {row.first_name} {row.last_name}",
        f"Company: {row.company_name}",
        f"Email: {row.email}",
    ]
    if row.phone:
        lines.append(f"Phone: {row.phone}")
    lines.append(f"Team size: {row.team_size}")
    if row.trades:
        lines.append(f"Trades: {', '.join(row.trades)}")
    if row.current_system:
        lines.append(f"Current system: {row.current_system}")
    if row.preferred_contact_method:
        lines.append(f"Preferred contact: {row.preferred_contact_method}")
    if row.message:
        lines.append(f"Message: {row.message}")
    return lines


def _upsert_customer(db: Session, tenant: Tenant, row: DemoRequest) -> Customer:
    """One customer per prospect email within the sales workspace: a
    repeat request appends to the existing record instead of creating a
    duplicate contact."""
    note = "Demo request received via the GeoCore website.\n" + "\n".join(_summary_lines(row))
    existing = db.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
            func.lower(Customer.email) == row.email.strip().lower(),
        )
    ).first()
    if existing is not None:
        existing.notes = f"{existing.notes}\n\n{note}" if existing.notes else note
        db.commit()
        db.refresh(existing)
        return existing
    return crud.create_customer(
        db,
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=f"{row.first_name} {row.last_name}".strip(),
        email=row.email,
        phone=row.phone,
        customer_type="company",
        company_name=row.company_name,
        notes=note,
    )


def _follow_up(db: Session, row: DemoRequest, delivery: DeliveryService) -> None:
    tenant = _sales_tenant(db)
    if tenant is None:
        return

    customer = _upsert_customer(db, tenant, row)
    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.DEMO_REQUEST_RECEIVED,
            title="Demo request received",
            description=f"{row.first_name} {row.last_name}, {row.company_name}",
        ),
        tenant_id=tenant.id,
    )

    customer_url = f"{settings.frontend_base_url}/customers/{customer.id}"
    notification = render_demo_request_sales_notification(
        tenant_display_name=tenant.name, summary_lines=_summary_lines(row), customer_url=customer_url
    )
    owners = [
        user
        for user in crud.list_users_by_tenant(db, tenant.id)
        if user.role == UserRole.OWNER.value and user.is_active and user.email_verified_at is not None
    ]
    for owner in owners:
        delivery.send(
            db,
            tenant=tenant,
            message_type=CommunicationType.DEMO_REQUEST_SALES_NOTIFICATION,
            recipient=owner.email,
            subject=notification.subject,
            html=notification.html,
            text=notification.text,
            dedupe_key=f"demo-request-sales:{row.id}:{owner.id}",
            customer_id=customer.id,
        )

    confirmation = render_demo_request_confirmation(tenant_display_name=tenant.name, recipient_name=row.first_name)
    delivery.send(
        db,
        tenant=tenant,
        message_type=CommunicationType.DEMO_REQUEST_CONFIRMATION,
        recipient=row.email,
        subject=confirmation.subject,
        html=confirmation.html,
        text=confirmation.text,
        dedupe_key=f"demo-request-confirmation:{row.id}",
        customer_id=customer.id,
    )
