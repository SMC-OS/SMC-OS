"""Public "Request a Demo" HTTP surface (Sprint 041).

Deliberately public: no auth, no tenant, no card. Rate-limited per
submitted email via the same CooldownLimiter shape as
app/auth/rate_limit.py's other public-endpoint limiters. No list/admin
endpoint is exposed by this router — an internal review surface is out of
scope for this plan (see the Master Spec).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.rate_limit import demo_request_limiter
from app.core.config import settings
from app.database.database import get_db
from app.demo_requests.models import DemoRequestCreate, DemoRequestSubmitOut
from app.demo_requests.service import create_demo_request

router = APIRouter(prefix="/demo-requests", tags=["demo-requests"])


@router.post("", response_model=DemoRequestSubmitOut, status_code=status.HTTP_201_CREATED)
def submit_demo_request(data: DemoRequestCreate, db: Session = Depends(get_db)):
    demo_request_limiter.check_and_record(
        data.email, cooldown_seconds=settings.demo_request_cooldown_seconds
    )
    create_demo_request(db, data)
    return DemoRequestSubmitOut()
