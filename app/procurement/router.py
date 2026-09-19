import datetime as _dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role
from app.auth.models import UserRole
from app.database import crud
from app.database.database import get_db
from app.database.models import PurchaseOrder, User
from app.procurement.models import (
    MaterialAllocationCreate,
    MaterialAllocationOut,
    MaterialRequirementIn,
    MaterialRequirementOut,
    MaterialRequirementUpdate,
    OrderPurchaseOrderRequest,
    OverReceiptError,
    PurchaseOrderCreate,
    PurchaseOrderItemOut,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    PurchaseReceiptCreate,
    PurchaseReceiptOut,
    is_po_late,
)
from app.procurement.pdf import build_purchase_order_pdf
from app.procurement.service import (
    ProjectNotFoundError,
    PurchaseOrderEditStateError,
    PurchaseOrderNotFoundError,
    PurchaseOrderTransitionError,
    RequirementNotFoundError,
    SupplierNotFoundError,
    procurement_service,
)

# No single path prefix — routes live under /projects/{id}/requirements,
# /projects/{id}/allocations, /purchase-orders/..., and
# /catalogue/suppliers/..., same convention as app/appointments/router.py
# and app/variations/router.py.
router = APIRouter(tags=["procurement"], dependencies=[Depends(require_billing_access)])


def _serialize_po(db: Session, purchase_order: PurchaseOrder) -> PurchaseOrderOut:
    items = crud.list_purchase_order_items(db, purchase_order.id)
    item_outs = []
    for item in items:
        received = crud.sum_received_quantity_for_item(db, item.id)
        item_outs.append(
            PurchaseOrderItemOut(
                id=item.id,
                material_requirement_id=item.material_requirement_id,
                catalogue_surface_id=item.catalogue_surface_id,
                catalogue_variant_id=item.catalogue_variant_id,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                unit_cost=item.unit_cost,
                line_total=item.line_total,
                quantity_received=received,
            )
        )
    out = PurchaseOrderOut.model_validate(purchase_order)
    out.items = item_outs
    out.is_late = is_po_late(purchase_order.status, purchase_order.expected_delivery_date, _dt.date.today())
    return out


# --- Suppliers (read) ----------------------------------------------------


@router.get("/catalogue/suppliers")
def list_suppliers(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    return [
        {"id": s.id, "name": s.name, "slug": s.slug}
        for s in crud.list_catalogue_suppliers(db)
    ]


@router.get("/procurement/supplier-accounts")
def list_supplier_accounts(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    return procurement_service.list_supplier_accounts(db, current_user.tenant_id)


@router.put("/procurement/supplier-accounts/{supplier_id}")
def upsert_supplier_account(
    supplier_id: uuid.UUID,
    fields: dict,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return procurement_service.upsert_supplier_account(db, current_user.tenant_id, supplier_id, fields)
    except SupplierNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")


# --- Material requirements ------------------------------------------------


@router.get("/projects/{project_id}/requirements", response_model=list[MaterialRequirementOut])
def list_requirements(
    project_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return procurement_service.list_requirements(db, project_id, current_user.tenant_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.post(
    "/projects/{project_id}/requirements", response_model=MaterialRequirementOut, status_code=status.HTTP_201_CREATED
)
def create_requirement(
    project_id: uuid.UUID,
    data: MaterialRequirementIn,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return procurement_service.create_requirement(db, project_id, current_user.tenant_id, current_user.id, data)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/requirements/{requirement_id}", response_model=MaterialRequirementOut)
def update_requirement(
    requirement_id: uuid.UUID,
    data: MaterialRequirementUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return procurement_service.update_requirement(db, requirement_id, current_user.tenant_id, data)
    except RequirementNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")


@router.post("/requirements/{requirement_id}/cancel", response_model=MaterialRequirementOut)
def cancel_requirement(
    requirement_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return procurement_service.cancel_requirement(db, requirement_id, current_user.tenant_id)
    except RequirementNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")


# --- Purchase orders ------------------------------------------------------


@router.get("/purchase-orders", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    project_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    late_only: bool = False,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    orders = procurement_service.list_purchase_orders(
        db,
        current_user.tenant_id,
        project_id=project_id,
        supplier_id=supplier_id,
        status=status_filter,
        late_only=late_only,
    )
    return [_serialize_po(db, po) for po in orders]


@router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    data: PurchaseOrderCreate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        po = procurement_service.create_purchase_order(db, current_user.tenant_id, current_user.id, data)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return _serialize_po(db, po)


@router.get("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderOut)
def get_purchase_order(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        po = procurement_service.get_purchase_order(db, purchase_order_id, current_user.tenant_id)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return _serialize_po(db, po)


@router.patch("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderOut)
def update_purchase_order(
    purchase_order_id: uuid.UUID,
    data: PurchaseOrderUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        po = procurement_service.update_purchase_order(db, purchase_order_id, current_user.tenant_id, data)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    except PurchaseOrderEditStateError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a draft purchase order can be edited")
    return _serialize_po(db, po)


@router.post("/purchase-orders/{purchase_order_id}/approve", response_model=PurchaseOrderOut)
def approve_purchase_order(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        po = procurement_service.approve(db, purchase_order_id, current_user.tenant_id, current_user.id)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    except PurchaseOrderTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Purchase order cannot be approved from its current status"
        )
    return _serialize_po(db, po)


@router.post("/purchase-orders/{purchase_order_id}/order", response_model=PurchaseOrderOut)
def order_purchase_order(
    purchase_order_id: uuid.UUID,
    data: OrderPurchaseOrderRequest,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        po = procurement_service.order(db, purchase_order_id, current_user.tenant_id, data)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    except PurchaseOrderTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Purchase order cannot be ordered from its current status"
        )
    return _serialize_po(db, po)


@router.post("/purchase-orders/{purchase_order_id}/cancel", response_model=PurchaseOrderOut)
def cancel_purchase_order(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        po = procurement_service.cancel(db, purchase_order_id, current_user.tenant_id)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    except PurchaseOrderTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Purchase order cannot be cancelled from its current status"
        )
    return _serialize_po(db, po)


@router.get("/purchase-orders/{purchase_order_id}/pdf")
def download_purchase_order_pdf(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        po = procurement_service.get_purchase_order(db, purchase_order_id, current_user.tenant_id)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")

    items = crud.list_purchase_order_items(db, po.id)
    project = crud.get_project_by_id(db, po.project_id, current_user.tenant_id) if po.project_id else None
    supplier = crud.get_catalogue_supplier_by_id(db, po.supplier_id) if po.supplier_id else None
    tenant = crud.get_tenant_by_id(db, current_user.tenant_id)

    pdf_bytes = build_purchase_order_pdf(po, items, project=project, supplier=supplier, tenant=tenant)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{po.reference}.pdf"'},
    )


# --- Receipts ---------------------------------------------------------


@router.get("/purchase-orders/{purchase_order_id}/receipts", response_model=list[PurchaseReceiptOut])
def list_receipts(
    purchase_order_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        receipts = procurement_service.list_receipts(db, purchase_order_id, current_user.tenant_id)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return [
        PurchaseReceiptOut(
            id=r.id,
            purchase_order_id=r.purchase_order_id,
            received_at=r.received_at,
            received_by_user_id=r.received_by_user_id,
            delivery_reference=r.delivery_reference,
            notes=r.notes,
            created_at=r.created_at,
            items=crud.list_purchase_receipt_items(db, r.id),
        )
        for r in receipts
    ]


@router.post(
    "/purchase-orders/{purchase_order_id}/receipts",
    response_model=PurchaseReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def record_receipt(
    purchase_order_id: uuid.UUID,
    data: PurchaseReceiptCreate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        receipt = procurement_service.record_receipt(
            db, purchase_order_id, current_user.tenant_id, current_user.id, data
        )
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order item not found")
    except OverReceiptError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return PurchaseReceiptOut(
        id=receipt.id,
        purchase_order_id=receipt.purchase_order_id,
        received_at=receipt.received_at,
        received_by_user_id=receipt.received_by_user_id,
        delivery_reference=receipt.delivery_reference,
        notes=receipt.notes,
        created_at=receipt.created_at,
        items=crud.list_purchase_receipt_items(db, receipt.id),
    )


# --- Allocations --------------------------------------------------------


@router.get("/projects/{project_id}/allocations", response_model=list[MaterialAllocationOut])
def list_allocations(
    project_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return procurement_service.list_allocations(db, project_id, current_user.tenant_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.post(
    "/projects/{project_id}/allocations", response_model=MaterialAllocationOut, status_code=status.HTTP_201_CREATED
)
def allocate_material(
    project_id: uuid.UUID,
    data: MaterialAllocationCreate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return procurement_service.allocate_material(db, project_id, current_user.tenant_id, current_user.id, data)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
