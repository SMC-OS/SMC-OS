import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role
from app.auth.models import UserRole
from app.database import crud
from app.database.database import get_db
from app.database.models import User, Variation
from app.variations.models import VariationCreate, VariationItemOut, VariationOut, VariationUpdate
from app.variations.pdf import build_variation_pdf
from app.variations.service import (
    ProjectNotFoundError,
    VariationEditStateError,
    VariationNotFoundError,
    VariationTransitionError,
    variation_service,
)

# No single path prefix — routes live under both /projects/{id}/variations
# and /variations/{id}/..., same convention as app/appointments/router.py.
router = APIRouter(tags=["variations"], dependencies=[Depends(require_billing_access)])


def _serialize(db: Session, variation: Variation) -> VariationOut:
    items = crud.list_variation_items(db, variation.id)
    return VariationOut(
        id=variation.id,
        project_id=variation.project_id,
        reference=variation.reference,
        title=variation.title,
        description=variation.description,
        status=variation.status,
        vat_rate=variation.vat_rate,
        subtotal=variation.subtotal,
        vat=variation.vat,
        total=variation.total,
        requested_by=variation.requested_by,
        approved_at=variation.approved_at,
        approved_by_user_id=variation.approved_by_user_id,
        created_by_user_id=variation.created_by_user_id,
        created_at=variation.created_at,
        updated_at=variation.updated_at,
        items=[VariationItemOut.model_validate(item) for item in items],
    )


@router.get("/projects/{project_id}/variations", response_model=list[VariationOut])
def list_variations(
    project_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variations = variation_service.list_for_project(db, project_id, current_user.tenant_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return [_serialize(db, v) for v in variations]


@router.post(
    "/projects/{project_id}/variations", response_model=VariationOut, status_code=status.HTTP_201_CREATED
)
def create_variation(
    project_id: uuid.UUID,
    data: VariationCreate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.create(
            db, project_id, current_user.tenant_id, current_user.id, data
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return _serialize(db, variation)


@router.get("/variations/{variation_id}", response_model=VariationOut)
def get_variation(
    variation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.get(db, variation_id, current_user.tenant_id)
    except VariationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variation not found")
    return _serialize(db, variation)


@router.patch("/variations/{variation_id}", response_model=VariationOut)
def update_variation(
    variation_id: uuid.UUID,
    data: VariationUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.update(db, variation_id, current_user.tenant_id, data)
    except VariationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variation not found")
    except VariationEditStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only a draft variation can be edited"
        )
    return _serialize(db, variation)


@router.post("/variations/{variation_id}/send", response_model=VariationOut)
def send_variation(
    variation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.send(db, variation_id, current_user.tenant_id)
    except VariationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variation not found")
    except VariationTransitionError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Variation cannot be sent from its current status")
    return _serialize(db, variation)


@router.post("/variations/{variation_id}/approve", response_model=VariationOut)
def approve_variation(
    variation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.approve(
            db, variation_id, current_user.tenant_id, current_user.id
        )
    except VariationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variation not found")
    except VariationTransitionError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Variation cannot be approved from its current status")
    return _serialize(db, variation)


@router.post("/variations/{variation_id}/reject", response_model=VariationOut)
def reject_variation(
    variation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.reject(db, variation_id, current_user.tenant_id)
    except VariationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variation not found")
    except VariationTransitionError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Variation cannot be rejected from its current status")
    return _serialize(db, variation)


@router.post("/variations/{variation_id}/void", response_model=VariationOut)
def void_variation(
    variation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.void(db, variation_id, current_user.tenant_id)
    except VariationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variation not found")
    except VariationTransitionError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Variation cannot be voided from its current status")
    return _serialize(db, variation)


@router.get("/variations/{variation_id}/pdf")
def download_variation_pdf(
    variation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        variation = variation_service.get(db, variation_id, current_user.tenant_id)
    except VariationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variation not found")

    project = crud.get_project_by_id(db, variation.project_id, current_user.tenant_id)
    customer = (
        crud.get_customer_by_id(db, project.customer_id, current_user.tenant_id)
        if project and project.customer_id
        else None
    )
    tenant = crud.get_tenant_by_id(db, current_user.tenant_id)
    items = crud.list_variation_items(db, variation.id)

    pdf_bytes = build_variation_pdf(variation, items, project=project, customer=customer, tenant=tenant)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{variation.reference}.pdf"'},
    )
