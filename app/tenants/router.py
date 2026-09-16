import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role
from app.auth.models import UserRole
from app.database.database import get_db
from app.database.models import User
from app.tenants import branding
from app.tenants.models import (
    OnboardingStateOut,
    TenantCreate,
    TenantOnboardingUpdate,
    TenantOut,
    TenantProfileOut,
    TenantProfileUpdate,
)
from app.tenants.service import tenant_service

# Sprint 008: requires the existing seeded-owner token (now require_billing_access),
# same posture as app/customers/router.py — NOT tenant-scoped auth (that's
# Sprint 009). This just avoids an unauthenticated public write endpoint by
# reusing the one auth gate that already exists. These routes are internal
# scaffolding, not yet wired to any real signup flow.
#
# Sprint 012 (ADR-029) — GET (list) and GET/{id} previously returned every
# tenant in the system to any authenticated caller (a real cross-tenant
# leak: name/slug/status of every other company, predating this sprint).
# Both now return only the caller's own tenant. POST was audited per
# ADR-029 and left unchanged: creating a new, unlinked tenant doesn't read
# or expose any other tenant's existing data, so it isn't an isolation
# leak — it's a separate, pre-existing tenant-lifecycle question (should
# this route even still be reachable now that POST /api/v1/auth/signup is
# the real way to create a workspace?) explicitly out of scope for a
# tenant-*isolation* sprint.
router = APIRouter(
    prefix="/tenants", tags=["tenants"], dependencies=[Depends(require_billing_access)]
)


@router.get("", response_model=list[TenantOut])
def get_my_tenant(
    limit: int = 20,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    # `limit` is accepted (unused) only to avoid a 422 for existing callers
    # passing ?limit= — the response is always the caller's own tenant, at
    # most one row, never another tenant's.
    tenant = tenant_service.get(db, current_user.tenant_id)
    return [tenant] if tenant is not None else []


# Sprint 034 — company identity. Declared BEFORE /{tenant_id} on purpose:
# FastAPI matches in declaration order, and "me" would otherwise be parsed
# as a uuid path param and 422 before ever reaching this handler.
#
# Both routes are hard-scoped to the caller's own tenant — there is no
# tenant_id parameter to tamper with, so no cross-tenant write is
# expressible through this API at all (ADR-029's posture, enforced by
# construction rather than by a check).
@router.get("/me/profile", response_model=TenantProfileOut)
def get_my_company_profile(
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    tenant = tenant_service.get(db, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant_service.to_profile(tenant)


@router.patch("/me/profile", response_model=TenantProfileOut)
def update_my_company_profile(
    data: TenantProfileUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    """Owner-only: this is the business's legal and statutory identity as it
    appears on every quote and invoice its customers receive, so it sits
    alongside billing and team management rather than with general staff
    settings."""
    tenant = tenant_service.update_identity(db, current_user.tenant_id, data)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant_service.to_profile(tenant)


# --- Sprint 036 (Workstream J) — onboarding ---


@router.get("/me/onboarding", response_model=OnboardingStateOut)
def get_onboarding_state(
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    """Whether this workspace still needs setting up, and what it has so
    far. Readable by any member so the UI can decide what to show without
    a role check of its own; the writes below stay Owner-only."""
    state = tenant_service.onboarding_state(db, current_user.tenant_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return state


@router.patch("/me/onboarding", response_model=TenantProfileOut)
def update_onboarding(
    data: TenantOnboardingUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    """Owner-only, same class as company identity: what the business does
    and what currency it works in are workspace-wide settings, not
    personal preferences."""
    tenant = tenant_service.update_onboarding(db, current_user.tenant_id, data)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant_service.to_profile(tenant)


# --- Sprint 036 (Workstream I) — real logo upload ---


@router.get("/me/logo")
def get_my_logo(
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    """Serve this tenant's uploaded logo.

    Hard-scoped to the caller's own tenant: there is no id parameter, so
    no request can ask for another workspace's logo. The stored filename
    is never exposed to a client — the file is only ever reachable through
    this route, which resolves it from the caller's own row.
    """
    tenant = tenant_service.get(db, current_user.tenant_id)
    if tenant is None or not tenant.logo_storage_filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo uploaded")

    path = branding.logo_path(tenant.logo_storage_filename)
    if not path.is_file():
        # The row says there is a logo but the file is gone — an ephemeral
        # volume reset, most likely (see ADR-032's accepted limitation).
        # A 404 is the honest answer; the row is left alone so an operator
        # can see that a logo was configured.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo uploaded")

    return Response(
        content=path.read_bytes(),
        media_type=branding.content_type_for(tenant.logo_storage_filename),
        # Private: this is one workspace's asset behind an authenticated
        # route, and a shared cache must never hand it to another caller.
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.post("/me/logo", response_model=TenantProfileOut)
def upload_my_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    """Owner-only: the logo appears on every customer-facing document this
    business issues, the same class of decision as its registered address.

    Replacing a logo deletes the previous file — a logo is current state,
    not a record, and orphaned files on a volume are a real operational
    cost with no upside. The delete happens only after the new file has
    been written and the row updated, so a failed upload never destroys
    the working logo.
    """
    try:
        storage_filename = branding.save_logo(file)
    except branding.DisallowedLogoTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{exc.extension or 'That file type'} is not supported. "
                "Upload a PNG, JPG or WebP image."
            ),
        )
    except branding.LogoTooLargeError:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Logo must be 2MB or smaller",
        )

    tenant = tenant_service.get(db, current_user.tenant_id)
    if tenant is None:
        branding.delete_logo(storage_filename)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    previous = tenant.logo_storage_filename
    tenant = tenant_service.set_logo_file(db, current_user.tenant_id, storage_filename)
    branding.delete_logo(previous)
    return tenant_service.to_profile(tenant)


@router.delete("/me/logo", response_model=TenantProfileOut)
def delete_my_logo(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    tenant = tenant_service.get(db, current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    previous = tenant.logo_storage_filename
    tenant = tenant_service.set_logo_file(db, current_user.tenant_id, None)
    branding.delete_logo(previous)
    return tenant_service.to_profile(tenant)


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: uuid.UUID,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    # Cross-tenant lookups 404, never 403 (ADR-028's precedent) — confirming
    # that another tenant's id exists at all is itself a leak.
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant = tenant_service.get(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(data: TenantCreate, db: Session = Depends(get_db)):
    return tenant_service.create(db, data)
