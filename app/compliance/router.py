import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.internal_auth import require_internal_compliance_auth
from app.database.database import get_db
from app.database.models import CopyrightCase

router = APIRouter(prefix="/compliance", tags=["compliance"])


class CopyrightReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reporter_name: str = Field(min_length=1, max_length=200)
    reporter_email: str = Field(min_length=3, max_length=320)
    work_description: str = Field(min_length=1, max_length=5000)
    location: str = Field(min_length=1, max_length=2000)
    statement: str = Field(min_length=1, max_length=5000)


class CopyrightCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    created_at: datetime


class CopyrightCaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(received|under_review|actioned|closed)$")
    internal_notes: str | None = Field(default=None, max_length=5000)


@router.post("/copyright-reports", response_model=CopyrightCaseOut, status_code=status.HTTP_201_CREATED)
def create_copyright_report(payload: CopyrightReportIn, db: Session = Depends(get_db)):
    row = CopyrightCase(id=uuid.uuid4(), **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/internal/copyright-reports", response_model=list[CopyrightCaseOut], dependencies=[Depends(require_internal_compliance_auth)])
def list_copyright_reports(db: Session = Depends(get_db)):
    return list(db.scalars(select(CopyrightCase).order_by(CopyrightCase.created_at.desc())))


@router.patch("/internal/copyright-reports/{case_id}", response_model=CopyrightCaseOut, dependencies=[Depends(require_internal_compliance_auth)])
def update_copyright_report(case_id: uuid.UUID, payload: CopyrightCaseUpdate, db: Session = Depends(get_db)):
    row = db.get(CopyrightCase, case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Copyright case not found")
    row.status = payload.status
    row.internal_notes = payload.internal_notes
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
