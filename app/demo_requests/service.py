"""Service layer for public demo-request submission (Sprint 041)."""

import uuid

from sqlalchemy.orm import Session

from app.database.models import DemoRequest
from app.demo_requests.models import DemoRequestCreate


def create_demo_request(db: Session, data: DemoRequestCreate) -> DemoRequest | None:
    """Persists a demo request. Returns None (nothing written) when the
    honeypot field was filled — the caller still returns a normal success
    response so a bot gets no signal that it was caught."""
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
    return row
