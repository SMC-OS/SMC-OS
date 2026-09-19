"""GeoCore Premium OS Plan 05 (Sprint 044) — procurement + materials
operations orchestration. Route-level pattern (ADR-019): no repository
interface, request-scoped Session via get_db().
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.automations.dispatcher import automation_dispatcher
from app.database import crud
from app.database.models import ProjectCostEntry, PurchaseOrder, PurchaseOrderItem
from app.procurement.models import (
    PO_ALLOWED_TRANSITIONS,
    MaterialAllocationCreate,
    MaterialRequirementIn,
    MaterialRequirementUpdate,
    OrderPurchaseOrderRequest,
    OverReceiptError,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseReceiptCreate,
    derive_po_status,
    next_requirement_status,
)
from app.quotes.general import GeneralQuoteLineRequest, price as price_lines


class ProjectNotFoundError(Exception):
    """Tenant-scoped lookup hides existence — same convention as every
    other module's own ProjectNotFoundError (ADR-029)."""


class RequirementNotFoundError(Exception):
    pass


class SupplierNotFoundError(Exception):
    pass


class PurchaseOrderNotFoundError(Exception):
    pass


class PurchaseOrderEditStateError(Exception):
    """Raised when a non-draft PO's commercial fields are edited."""


class PurchaseOrderTransitionError(Exception):
    """Raised when a requested status transition is not legal from the
    PO's current status (see PO_ALLOWED_TRANSITIONS)."""


def _next_po_reference(db: Session, tenant_id: uuid.UUID) -> str:
    """Sequential, human-readable, **per tenant** (`PO-001`, `PO-002`, …)
    — see ADR-050 for why this differs from a Variation's per-project
    numbering. Count-then-format has the same benign race as Variation's
    own numbering; the table's UNIQUE(tenant_id, reference) constraint is
    the real backstop."""
    count = crud.count_purchase_orders_for_tenant(db, tenant_id)
    return f"PO-{count + 1:03d}"


def _price_items(items: list, vat_rate: float):
    lines = [
        GeneralQuoteLineRequest(description=item.description, quantity=item.quantity, unit_price=item.unit_cost)
        for item in items
    ]
    return price_lines(lines, vat_rate=vat_rate, discount_amount=None)


class ProcurementService:
    # --- Material requirements -------------------------------------------

    def create_requirement(
        self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID, actor_user_id: uuid.UUID | None,
        data: MaterialRequirementIn,
    ):
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        requirement = crud.create_material_requirement(
            db, tenant_id=tenant_id, project_id=project_id, created_by_user_id=actor_user_id,
            **data.model_dump(),
        )
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.MATERIAL_REQUIREMENT_CREATED,
                title="Material requirement added",
                description=f"{project.name} — {requirement.description}",
            ),
            tenant_id=tenant_id,
        )
        automation_dispatcher.dispatch_material_requirement_created(db, requirement, project)
        return requirement

    def list_requirements(self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID):
        if crud.get_project_by_id(db, project_id, tenant_id) is None:
            raise ProjectNotFoundError(project_id)
        return crud.list_material_requirements_by_project(db, project_id, tenant_id)

    def update_requirement(
        self, db: Session, requirement_id: uuid.UUID, tenant_id: uuid.UUID, data: MaterialRequirementUpdate
    ):
        requirement = crud.get_material_requirement_by_id(db, requirement_id, tenant_id)
        if requirement is None:
            raise RequirementNotFoundError(requirement_id)
        changes = data.model_dump(exclude_unset=True)
        requirement = crud.update_material_requirement(db, requirement, changes)
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.MATERIAL_REQUIREMENT_EDITED,
                title="Material requirement edited",
                description=requirement.description,
            ),
            tenant_id=tenant_id,
        )
        return requirement

    def cancel_requirement(self, db: Session, requirement_id: uuid.UUID, tenant_id: uuid.UUID):
        requirement = crud.get_material_requirement_by_id(db, requirement_id, tenant_id)
        if requirement is None:
            raise RequirementNotFoundError(requirement_id)
        if requirement.status == "cancelled":
            return requirement
        requirement = crud.update_material_requirement(db, requirement, {"status": "cancelled"})
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.MATERIAL_REQUIREMENT_CANCELLED,
                title="Material requirement cancelled",
                description=requirement.description,
            ),
            tenant_id=tenant_id,
        )
        return requirement

    # --- Tenant supplier accounts -----------------------------------------

    def upsert_supplier_account(self, db: Session, tenant_id: uuid.UUID, supplier_id: uuid.UUID, fields: dict):
        supplier = crud.get_catalogue_supplier_by_id(db, supplier_id)
        if supplier is None:
            raise SupplierNotFoundError(supplier_id)
        return crud.upsert_tenant_supplier_account(db, tenant_id=tenant_id, supplier_id=supplier_id, fields=fields)

    def list_supplier_accounts(self, db: Session, tenant_id: uuid.UUID):
        return crud.list_tenant_supplier_accounts(db, tenant_id)

    # --- Purchase orders ----------------------------------------------------

    def create_purchase_order(
        self, db: Session, tenant_id: uuid.UUID, actor_user_id: uuid.UUID | None, data: PurchaseOrderCreate
    ) -> PurchaseOrder:
        if data.project_id is not None and crud.get_project_by_id(db, data.project_id, tenant_id) is None:
            raise ProjectNotFoundError(data.project_id)

        totals = _price_items(data.items, data.vat_rate)
        reference = _next_po_reference(db, tenant_id)
        purchase_order = crud.create_purchase_order(
            db,
            tenant_id=tenant_id,
            project_id=data.project_id,
            supplier_id=data.supplier_id,
            reference=reference,
            expected_delivery_date=data.expected_delivery_date,
            notes=data.notes,
            vat_rate=data.vat_rate,
            subtotal=totals.subtotal,
            vat=totals.vat,
            total=totals.total,
            created_by_user_id=actor_user_id,
        )
        crud.replace_purchase_order_items(
            db,
            purchase_order.id,
            [
                {
                    "material_requirement_id": item.material_requirement_id,
                    "catalogue_surface_id": item.catalogue_surface_id,
                    "catalogue_variant_id": item.catalogue_variant_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "unit_cost": item.unit_cost,
                    "line_total": line_total,
                }
                for item, line_total in zip(data.items, totals.line_totals)
            ],
        )
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PURCHASE_ORDER_CREATED,
                title="Purchase order created",
                description=f"{purchase_order.reference} (£{purchase_order.total:,.2f})",
            ),
            tenant_id=tenant_id,
        )
        return purchase_order

    def get_purchase_order(self, db: Session, purchase_order_id: uuid.UUID, tenant_id: uuid.UUID) -> PurchaseOrder:
        purchase_order = crud.get_purchase_order_by_id(db, purchase_order_id, tenant_id)
        if purchase_order is None:
            raise PurchaseOrderNotFoundError(purchase_order_id)
        return purchase_order

    def list_purchase_orders(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        status: str | None = None,
        late_only: bool = False,
    ):
        return crud.list_purchase_orders(
            db, tenant_id, project_id=project_id, supplier_id=supplier_id, status=status, late_only=late_only
        )

    def update_purchase_order(
        self, db: Session, purchase_order_id: uuid.UUID, tenant_id: uuid.UUID, data: PurchaseOrderUpdate
    ) -> PurchaseOrder:
        purchase_order = self.get_purchase_order(db, purchase_order_id, tenant_id)
        if purchase_order.status != "draft":
            raise PurchaseOrderEditStateError(purchase_order_id)

        changes = data.model_dump(exclude_unset=True, exclude={"items"})
        if data.items is not None:
            vat_rate = changes.get("vat_rate", purchase_order.vat_rate)
            totals = _price_items(data.items, vat_rate)
            changes["subtotal"] = totals.subtotal
            changes["vat"] = totals.vat
            changes["total"] = totals.total
            crud.replace_purchase_order_items(
                db,
                purchase_order.id,
                [
                    {
                        "material_requirement_id": item.material_requirement_id,
                        "catalogue_surface_id": item.catalogue_surface_id,
                        "catalogue_variant_id": item.catalogue_variant_id,
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit": item.unit,
                        "unit_cost": item.unit_cost,
                        "line_total": line_total,
                    }
                    for item, line_total in zip(data.items, totals.line_totals)
                ],
            )
        if changes:
            purchase_order = crud.update_purchase_order(db, purchase_order, changes)
        return purchase_order

    def approve(self, db: Session, purchase_order_id: uuid.UUID, tenant_id: uuid.UUID, actor_user_id: uuid.UUID):
        purchase_order = self.get_purchase_order(db, purchase_order_id, tenant_id)
        already_approved = purchase_order.status == "approved"
        purchase_order = self._transition(db, purchase_order, target="approved")

        # Idempotent by construction: _create_committed_costs checks for
        # an existing linked cost entry per PO item before creating one,
        # so a retried/duplicate approval call can never double the
        # committed cost this PO contributes (Task 37, ADR-050).
        if purchase_order.project_id is not None:
            self._create_committed_costs(db, purchase_order, actor_user_id)

        if not already_approved:
            purchase_order = crud.update_purchase_order(
                db, purchase_order, {"approved_at": datetime.now(timezone.utc), "approved_by_user_id": actor_user_id}
            )
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.PURCHASE_ORDER_APPROVED,
                    title="Purchase order approved",
                    description=f"{purchase_order.reference} (£{purchase_order.total:,.2f})",
                ),
                tenant_id=tenant_id,
            )
            automation_dispatcher.dispatch_purchase_order_approved(db, purchase_order, self._project_name(db, purchase_order))
        return purchase_order

    def order(
        self, db: Session, purchase_order_id: uuid.UUID, tenant_id: uuid.UUID, data: OrderPurchaseOrderRequest
    ):
        purchase_order = self.get_purchase_order(db, purchase_order_id, tenant_id)
        already_ordered = purchase_order.status in {"ordered", "partially_received", "received"}
        purchase_order = self._transition(db, purchase_order, target="ordered")

        fields = {"order_date": date.today()}
        if data.supplier_reference is not None:
            fields["supplier_reference"] = data.supplier_reference
        if data.expected_delivery_date is not None:
            fields["expected_delivery_date"] = data.expected_delivery_date
        purchase_order = crud.update_purchase_order(db, purchase_order, fields)

        if not already_ordered:
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.PURCHASE_ORDER_ORDERED,
                    title="Purchase order marked as ordered",
                    description=purchase_order.reference,
                ),
                tenant_id=tenant_id,
            )
            automation_dispatcher.dispatch_purchase_order_ordered(db, purchase_order, self._project_name(db, purchase_order))
            self._sync_requirement_statuses(db, purchase_order, "ordered")
        return purchase_order

    def cancel(self, db: Session, purchase_order_id: uuid.UUID, tenant_id: uuid.UUID):
        purchase_order = self.get_purchase_order(db, purchase_order_id, tenant_id)
        if purchase_order.status == "cancelled":
            return purchase_order
        purchase_order = self._transition(db, purchase_order, target="cancelled")

        # Committed cost this PO contributed is removed — never left as a
        # phantom commitment on a project that no longer has this order
        # (Task 16). The PO's own ActivityLog entry below is the audit
        # trail for the removal; no per-row entry is added on top of it.
        for entry in crud.list_cost_entries_by_purchase_order(db, purchase_order.id):
            crud.delete_project_cost_entry(db, entry)

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PURCHASE_ORDER_CANCELLED,
                title="Purchase order cancelled",
                description=purchase_order.reference,
            ),
            tenant_id=tenant_id,
        )
        return purchase_order

    def _transition(self, db: Session, purchase_order: PurchaseOrder, *, target: str) -> PurchaseOrder:
        if purchase_order.status == target:
            return purchase_order
        allowed = PO_ALLOWED_TRANSITIONS.get(purchase_order.status, set())
        if target not in allowed:
            raise PurchaseOrderTransitionError(f"{purchase_order.status} -> {target}")
        return crud.update_purchase_order(db, purchase_order, {"status": target})

    def _create_committed_costs(self, db: Session, purchase_order: PurchaseOrder, actor_user_id: uuid.UUID | None):
        items = crud.list_purchase_order_items(db, purchase_order.id)
        for item in items:
            if crud.get_cost_entry_by_purchase_order_item(db, item.id) is not None:
                continue
            crud.create_project_cost_entry(
                db,
                tenant_id=purchase_order.tenant_id,
                project_id=purchase_order.project_id,
                category="material",
                state="committed",
                description=item.description,
                total_cost=item.line_total,
                quantity=item.quantity,
                unit=item.unit,
                unit_cost=item.unit_cost,
                purchase_order_id=purchase_order.id,
                purchase_order_item_id=item.id,
                created_by_user_id=actor_user_id,
            )

    def _project_name(self, db: Session, purchase_order: PurchaseOrder) -> str | None:
        if purchase_order.project_id is None:
            return None
        project = crud.get_project_by_id(db, purchase_order.project_id, purchase_order.tenant_id)
        return project.name if project else None

    def _sync_requirement_statuses(self, db: Session, purchase_order: PurchaseOrder, po_item_status: str):
        for item in crud.list_purchase_order_items(db, purchase_order.id):
            if item.material_requirement_id is None:
                continue
            requirement = crud.get_material_requirement_by_id(
                db, item.material_requirement_id, purchase_order.tenant_id
            )
            if requirement is None:
                continue
            target = next_requirement_status(requirement.status, po_item_status)
            if target is not None:
                crud.update_material_requirement(db, requirement, {"status": target})

    # --- Receipts -------------------------------------------------------

    def record_receipt(
        self,
        db: Session,
        purchase_order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        data: PurchaseReceiptCreate,
    ):
        purchase_order = self.get_purchase_order(db, purchase_order_id, tenant_id)

        # Over-receipt safety (Task 11) — validated for every line before
        # any row is written, so a rejected receipt never partially
        # applies.
        item_by_id: dict[uuid.UUID, PurchaseOrderItem] = {
            item.id: item for item in crud.list_purchase_order_items(db, purchase_order.id)
        }
        for line in data.items:
            item = item_by_id.get(line.purchase_order_item_id)
            if item is None:
                raise PurchaseOrderNotFoundError(line.purchase_order_item_id)
            already_received = crud.sum_received_quantity_for_item(db, item.id)
            if already_received + line.quantity_received > item.quantity:
                raise OverReceiptError(item.id, item.quantity, already_received, line.quantity_received)

        receipt = crud.create_purchase_receipt(
            db,
            tenant_id=tenant_id,
            purchase_order_id=purchase_order.id,
            received_at=data.received_at,
            received_by_user_id=actor_user_id,
            delivery_reference=data.delivery_reference,
            notes=data.notes,
            items=[
                {"purchase_order_item_id": line.purchase_order_item_id, "quantity_received": line.quantity_received}
                for line in data.items
            ],
        )

        # Per-item effects: a fully-received item's committed cost row
        # flips in place to `actual` (never a second row — see ADR-050's
        # documented V1 rule: partial receipt does not split the amount,
        # it stays committed until the item itself is fully received).
        for line in data.items:
            item = item_by_id[line.purchase_order_item_id]
            received_total = crud.sum_received_quantity_for_item(db, item.id)
            item_status = derive_po_status("ordered", item.quantity, received_total)
            if item_status == "received":
                self._mark_item_cost_actual(db, item.id)
            if item.material_requirement_id is not None:
                requirement = crud.get_material_requirement_by_id(db, item.material_requirement_id, tenant_id)
                if requirement is not None:
                    target = next_requirement_status(requirement.status, item_status)
                    if target is not None:
                        crud.update_material_requirement(db, requirement, {"status": target})

        # Overall PO status: derived across every item, not just the
        # ones this receipt touched (Task 12).
        all_items = crud.list_purchase_order_items(db, purchase_order.id)
        ordered_qty = sum(item.quantity for item in all_items)
        received_qty = sum(crud.sum_received_quantity_for_item(db, item.id) for item in all_items)
        new_status = derive_po_status(purchase_order.status, ordered_qty, received_qty)
        if new_status != purchase_order.status:
            fields = {"status": new_status}
            if new_status == "received":
                fields["received_date"] = data.received_at.date()
            purchase_order = crud.update_purchase_order(db, purchase_order, fields)
            project_name = self._project_name(db, purchase_order)
            if new_status == "received":
                automation_dispatcher.dispatch_purchase_order_received(db, purchase_order, project_name)
            elif new_status == "partially_received":
                automation_dispatcher.dispatch_purchase_order_partially_received(db, purchase_order, project_name)

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PURCHASE_ORDER_RECEIPT_RECORDED,
                title="Delivery recorded",
                description=f"{purchase_order.reference} — {len(data.items)} line(s)",
            ),
            tenant_id=tenant_id,
        )
        return receipt

    def _mark_item_cost_actual(self, db: Session, purchase_order_item_id: uuid.UUID):
        entry: ProjectCostEntry | None = crud.get_cost_entry_by_purchase_order_item(db, purchase_order_item_id)
        if entry is not None and entry.state != "actual":
            crud.update_project_cost_entry(db, entry, {"state": "actual"})

    def list_receipts(self, db: Session, purchase_order_id: uuid.UUID, tenant_id: uuid.UUID):
        purchase_order = self.get_purchase_order(db, purchase_order_id, tenant_id)
        return crud.list_purchase_receipts(db, purchase_order.id)

    # --- Allocations ------------------------------------------------------

    def allocate_material(
        self,
        db: Session,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        data: MaterialAllocationCreate,
    ):
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        allocation = crud.create_material_allocation(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            material_requirement_id=data.material_requirement_id,
            purchase_order_item_id=data.purchase_order_item_id,
            quantity=data.quantity,
            allocated_by_user_id=actor_user_id,
            notes=data.notes,
        )

        if data.material_requirement_id is not None:
            requirement = crud.get_material_requirement_by_id(db, data.material_requirement_id, tenant_id)
            if requirement is not None and requirement.status not in {"allocated", "consumed", "cancelled"}:
                crud.update_material_requirement(db, requirement, {"status": "allocated"})

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.MATERIAL_ALLOCATED,
                title="Material allocated",
                description=f"{project.name} — {allocation.quantity:g}",
            ),
            tenant_id=tenant_id,
        )
        automation_dispatcher.dispatch_material_allocated(db, allocation, project.name)
        return allocation

    def list_allocations(self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID):
        if crud.get_project_by_id(db, project_id, tenant_id) is None:
            raise ProjectNotFoundError(project_id)
        return crud.list_material_allocations_by_project(db, project_id, tenant_id)


procurement_service = ProcurementService()
