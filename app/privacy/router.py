import io
import json
import hashlib
import secrets
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role_and_billing
from app.auth.models import UserRole
from app.compliance.internal_auth import require_internal_compliance_auth
from app.database.database import get_db
from app.database.models import ActivityLog, Customer, Document, MarketingPreference, MarketingUnsubscribeToken, Project, Quote, Tenant, User, WorkspaceDeletion, WorkspaceExport
from app.core.config import settings

router = APIRouter(prefix="/privacy", tags=["privacy"])
_RECOVERY_DAYS = 30


class DeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(pattern="^DELETE WORKSPACE$")


class DeletionStatus(BaseModel):
    state: str
    requested_at: datetime | None = None
    eligible_for_purge_at: datetime | None = None


class ExportRequestOut(BaseModel):
    id: uuid.UUID


class MarketingPreferenceOut(BaseModel):
    enabled: bool
    source: str
    updated_at: datetime | None = None


class MarketingPreferenceIn(BaseModel):
    enabled: bool


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _status(row: WorkspaceDeletion | None) -> DeletionStatus:
    if row is None: return DeletionStatus(state="active")
    if row.purged_at: return DeletionStatus(state="purged", requested_at=row.requested_at, eligible_for_purge_at=row.eligible_for_purge_at)
    if row.cancelled_at: return DeletionStatus(state="active")
    now = datetime.now(timezone.utc)
    return DeletionStatus(state="eligible_for_purge" if now >= row.eligible_for_purge_at else "deletion_requested", requested_at=row.requested_at, eligible_for_purge_at=row.eligible_for_purge_at)


def _export_bytes(db: Session, tenant_id: uuid.UUID) -> bytes:
    def rows(model):
        return [{column.name: (str(getattr(row, column.name)) if getattr(row, column.name) is not None else None) for column in model.__table__.columns if column.name not in {"password_hash", "storage_filename"}} for row in db.scalars(select(model).where(model.tenant_id == tenant_id))]
    data = {"customers": rows(Customer), "projects": rows(Project), "quotes": rows(Quote), "documents": rows(Document)}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("workspace-data.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return out.getvalue()


@router.post("/exports", response_model=ExportRequestOut, status_code=status.HTTP_201_CREATED)
def request_export(current_user: User = Depends(require_role_and_billing(UserRole.OWNER)), db: Session = Depends(get_db)):
    row = WorkspaceExport(id=uuid.uuid4(), tenant_id=current_user.tenant_id, requested_by_user_id=current_user.id)
    db.add(row)
    db.commit()
    return ExportRequestOut(id=row.id)


@router.get("/exports/{export_id}/download")
def download_export(export_id: uuid.UUID, current_user: User = Depends(require_role_and_billing(UserRole.OWNER)), db: Session = Depends(get_db)):
    row = db.get(WorkspaceExport, export_id)
    if row is None or row.tenant_id != current_user.tenant_id or row.requested_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Export not found")
    if row.downloaded_at:
        raise HTTPException(status_code=410, detail="Export has already been downloaded")
    row.downloaded_at = datetime.now(timezone.utc)
    payload = _export_bytes(db, current_user.tenant_id)
    db.commit()
    return Response(payload, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=geocore-workspace-export.zip", "Cache-Control": "no-store"})


@router.get("/marketing-preference", response_model=MarketingPreferenceOut)
def get_marketing_preference(current_user: User = Depends(require_role_and_billing(UserRole.OWNER, UserRole.STAFF)), db: Session = Depends(get_db)):
    row = db.scalars(select(MarketingPreference).where(MarketingPreference.tenant_id == current_user.tenant_id, MarketingPreference.email == current_user.email.lower())).first()
    return MarketingPreferenceOut(enabled=False if row is None else row.enabled, source="default" if row is None else row.source, updated_at=None if row is None else row.updated_at)


@router.put("/marketing-preference", response_model=MarketingPreferenceOut)
def set_marketing_preference(payload: MarketingPreferenceIn, current_user: User = Depends(require_role_and_billing(UserRole.OWNER, UserRole.STAFF)), db: Session = Depends(get_db)):
    email = current_user.email.lower()
    row = db.scalars(select(MarketingPreference).where(MarketingPreference.tenant_id == current_user.tenant_id, MarketingPreference.email == email)).first()
    if row is None:
        row = MarketingPreference(id=uuid.uuid4(), tenant_id=current_user.tenant_id, email=email, enabled=payload.enabled, source="authenticated_preferences")
        db.add(row)
    else:
        row.enabled = payload.enabled
        row.source = "authenticated_preferences"
    db.commit(); db.refresh(row)
    return MarketingPreferenceOut(enabled=row.enabled, source=row.source, updated_at=row.updated_at)


@router.post("/marketing-unsubscribe/{token}", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe_marketing(token: str, db: Session = Depends(get_db)):
    row = db.scalars(select(MarketingUnsubscribeToken).where(MarketingUnsubscribeToken.token_hash == _token_hash(token))).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Unsubscribe link not found")
    preference = db.scalars(select(MarketingPreference).where(MarketingPreference.tenant_id == row.tenant_id, MarketingPreference.email == row.email)).first()
    if preference is None:
        db.add(MarketingPreference(id=uuid.uuid4(), tenant_id=row.tenant_id, email=row.email, enabled=False, source="unsubscribe"))
    else:
        preference.enabled = False; preference.source = "unsubscribe"
    db.commit()


@router.get("/workspace-deletion", response_model=DeletionStatus)
def deletion_status(current_user: User = Depends(require_role_and_billing(UserRole.OWNER)), db: Session = Depends(get_db)):
    return _status(db.get(WorkspaceDeletion, current_user.tenant_id))


@router.post("/workspace-deletion", response_model=DeletionStatus)
def request_deletion(_: DeletionRequest, current_user: User = Depends(require_role_and_billing(UserRole.OWNER)), db: Session = Depends(get_db)):
    existing = db.get(WorkspaceDeletion, current_user.tenant_id)
    if existing and not existing.cancelled_at and not existing.purged_at:
        return _status(existing)
    now = datetime.now(timezone.utc)
    row = WorkspaceDeletion(tenant_id=current_user.tenant_id, requested_by_user_id=current_user.id, requested_at=now, eligible_for_purge_at=now + timedelta(days=_RECOVERY_DAYS))
    if existing:
        db.delete(existing)
        db.flush()
    db.add(row)
    db.add(ActivityLog(id=uuid.uuid4(), tenant_id=current_user.tenant_id, type="workspace_deletion_requested", title="Workspace deletion requested", description="Recovery period ends in 30 days."))
    db.commit()
    return _status(row)


@router.post("/workspace-deletion/cancel", response_model=DeletionStatus)
def cancel_deletion(current_user: User = Depends(require_role_and_billing(UserRole.OWNER)), db: Session = Depends(get_db)):
    row = db.get(WorkspaceDeletion, current_user.tenant_id)
    if row is None or row.cancelled_at or row.purged_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No cancellable workspace deletion exists")
    if datetime.now(timezone.utc) >= row.eligible_for_purge_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recovery period has ended")
    row.cancelled_at = datetime.now(timezone.utc)
    db.add(ActivityLog(id=uuid.uuid4(), tenant_id=current_user.tenant_id, type="workspace_deletion_cancelled", title="Workspace deletion cancelled"))
    db.commit()
    return _status(row)


@router.post("/internal/workspace-deletions/{tenant_id}/purge", response_model=DeletionStatus, dependencies=[Depends(require_internal_compliance_auth)])
def purge_workspace(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.get(WorkspaceDeletion, tenant_id)
    if row is None or row.cancelled_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workspace is not eligible for purge")
    if row.purged_at:
        return _status(row)
    if datetime.now(timezone.utc) < row.eligible_for_purge_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recovery period has not ended")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    # Ordinary workspace data is disposed of here. Retained audit, billing,
    # suppression and copyright records are intentionally not deleted.
    for document in db.scalars(select(Document).where(Document.tenant_id == tenant_id)):
        try:
            (Path(settings.upload_dir) / document.storage_filename).unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=409, detail="Workspace files could not be purged") from exc
        db.delete(document)
    db.execute(update(Customer).where(Customer.tenant_id == tenant_id).values(name="Deleted customer", email=None, phone=None, company_name=None, address_line1=None, address_line2=None, city=None, postcode=None, notes=None))
    # Quotes and projects may need to remain as neutral operational/accounting
    # references while legal retention is decided. Clear their site location
    # and free-text fields rather than retaining identifiable workspace data.
    db.execute(update(Project).where(Project.tenant_id == tenant_id).values(name="Deleted project", notes=None, description=None, site_address_line1=None, site_address_line2=None, site_city=None, site_postcode=None))
    db.execute(update(Quote).where(Quote.tenant_id == tenant_id).values(title="Deleted quote", postcode=None, site_address_line1=None, site_address_line2=None, site_city=None, site_postcode=None, scope_of_works=None, notes=None, exclusions=None, terms=None))
    for user in db.scalars(select(User).where(User.tenant_id == tenant_id)):
        user.name = "Deleted user"
        user.email = f"purged-{user.id}@deleted.invalid"
        user.is_active = False
    tenant.name = "Deleted workspace"
    tenant.slug = f"purged-{tenant_id}"
    tenant.legal_name = tenant.trading_name = tenant.address_line1 = tenant.address_line2 = None
    tenant.city = tenant.postcode = tenant.country = tenant.contact_email = tenant.contact_phone = None
    tenant.website = tenant.company_number = tenant.vat_number = tenant.logo_url = tenant.document_footer = None
    tenant.status = "purged"
    row.purged_at = datetime.now(timezone.utc)
    db.add(ActivityLog(id=uuid.uuid4(), tenant_id=tenant_id, type="workspace_purged", title="Workspace marked purged by internal compliance operation"))
    db.commit()
    return _status(row)
