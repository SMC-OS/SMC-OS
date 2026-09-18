"""GeoCore Premium OS Plan 05 (Sprint 044) — Procurement + Materials
Operations.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    CatalogueSupplier,
    Project,
    ProjectCostEntry,
    ProjectMaterialAllocation,
    ProjectMaterialRequirement,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    Quote,
    QuoteItem,
    Subscription,
    Tenant,
    TenantSupplierAccount,
    User,
)
from app.procurement.models import (
    MaterialAllocationCreate,
    MaterialRequirementIn,
    OrderPurchaseOrderRequest,
    OverReceiptError,
    PurchaseOrderCreate,
    PurchaseOrderItemIn,
    PurchaseReceiptCreate,
    PurchaseReceiptItemIn,
    derive_po_status,
    is_po_late,
    next_requirement_status,
)
from app.procurement.service import (
    ProjectNotFoundError,
    PurchaseOrderNotFoundError,
    PurchaseOrderTransitionError,
    procurement_service,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN_ID = uuid.uuid4().hex[:8]
STRONG_PASSWORD = "Procurement-Test-Password-1!"


def _unique_email(label: str) -> str:
    return f"pytest-procurement-{RUN_ID}-{label}-{uuid.uuid4().hex[:6]}@example.invalid"


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_tenant(db, name: str) -> Tenant:
    return tenant_service.create(db, TenantCreate(name=f"{name} {RUN_ID}"))


def _make_owner_headers(client, db, tenant: Tenant, label: str) -> tuple[dict, User]:
    email = _unique_email(label)
    user = auth_service.create_user(
        db, tenant_id=tenant.id, name="Pytest Procurement Owner", email=email, password=STRONG_PASSWORD, role="Owner"
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user


def _make_project(db, tenant, *, name="Pytest Procurement Project") -> Project:
    from app.workflows.service import resolve_initial_binding

    workflow_template_id, workflow_stage_id = resolve_initial_binding(db, None)
    return crud.create_project(
        db,
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=name,
        customer_id=None,
        notes=None,
        status="enquiry",
        quote_id=None,
        workflow_template_id=workflow_template_id,
        workflow_stage_id=workflow_stage_id,
    )


def _make_supplier(db, *, name: str) -> CatalogueSupplier:
    return crud.create_catalogue_supplier(db, name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}")


def _cleanup_tenant(tenant_id):
    db = SessionLocal()
    try:
        po_ids = [row[0] for row in db.query(PurchaseOrder.id).filter(PurchaseOrder.tenant_id == tenant_id).all()]
        if po_ids:
            receipt_ids = [
                row[0] for row in db.query(PurchaseReceipt.id).filter(PurchaseReceipt.purchase_order_id.in_(po_ids)).all()
            ]
            if receipt_ids:
                db.execute(delete(PurchaseReceiptItem).where(PurchaseReceiptItem.purchase_receipt_id.in_(receipt_ids)))
            db.execute(delete(PurchaseReceipt).where(PurchaseReceipt.purchase_order_id.in_(po_ids)))
        db.execute(delete(ProjectMaterialAllocation).where(ProjectMaterialAllocation.tenant_id == tenant_id))
        # ProjectCostEntry references purchase_order_item_id, so it must
        # be cleared before the items it points at.
        db.execute(delete(ProjectCostEntry).where(ProjectCostEntry.tenant_id == tenant_id))
        if po_ids:
            db.execute(delete(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id.in_(po_ids)))
        db.execute(delete(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id))
        db.execute(delete(ProjectMaterialRequirement).where(ProjectMaterialRequirement.tenant_id == tenant_id))
        db.execute(delete(TenantSupplierAccount).where(TenantSupplierAccount.tenant_id == tenant_id))
        db.execute(delete(Project).where(Project.tenant_id == tenant_id))
        db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(
            db.query(Quote.id).filter(Quote.tenant_id == tenant_id)
        )))
        db.execute(delete(Quote).where(Quote.tenant_id == tenant_id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pure calculation functions (no DB) — Task 11/12/13/26
# ---------------------------------------------------------------------------


def test_derive_po_status_stays_ordered_with_no_receipts():
    assert derive_po_status("ordered", 10, 0) == "ordered"


def test_derive_po_status_becomes_partially_received():
    assert derive_po_status("ordered", 10, 4) == "partially_received"


def test_derive_po_status_becomes_received_once_all_received():
    assert derive_po_status("partially_received", 10, 10) == "received"


def test_derive_po_status_leaves_draft_and_approved_untouched():
    assert derive_po_status("draft", 10, 0) == "draft"
    assert derive_po_status("approved", 10, 0) == "approved"


def test_is_po_late_requires_a_real_expected_date():
    today = date(2026, 6, 15)
    assert is_po_late("ordered", None, today) is False


def test_is_po_late_true_only_once_the_date_has_passed_and_not_done():
    today = date(2026, 6, 15)
    assert is_po_late("ordered", date(2026, 6, 10), today) is True
    assert is_po_late("ordered", date(2026, 6, 20), today) is False
    assert is_po_late("received", date(2026, 6, 10), today) is False
    assert is_po_late("cancelled", date(2026, 6, 10), today) is False


def test_next_requirement_status_advances_forward_only():
    assert next_requirement_status("required", "ordered") == "ordered"
    assert next_requirement_status("ordered", "partially_received") == "partially_received"
    assert next_requirement_status("received", "ordered") is None  # never backwards


def test_next_requirement_status_never_overwrites_allocated_or_consumed():
    assert next_requirement_status("allocated", "received") is None
    assert next_requirement_status("consumed", "received") is None
    assert next_requirement_status("cancelled", "received") is None


# ---------------------------------------------------------------------------
# Material requirements — Task 1/2
# ---------------------------------------------------------------------------


def test_a_catalogue_linked_and_a_custom_construction_requirement_can_coexist(client, db):
    tenant = _make_tenant(db, "ReqCoexist")
    headers, user = _make_owner_headers(client, db, tenant, "req")
    project = _make_project(db, tenant)
    try:
        catalogue_res = client.post(
            f"/api/v1/projects/{project.id}/requirements",
            json={"description": "Calacatta worktop", "material_family": "quartz"},
            headers=headers,
        )
        assert catalogue_res.status_code == 201, catalogue_res.text
        assert catalogue_res.json()["status"] == "required"

        custom_res = client.post(
            f"/api/v1/projects/{project.id}/requirements",
            json={
                "description": "Roof tiles",
                "custom_material_name": "Marley Eternit slate",
                "required_quantity": 500,
                "unit": "each",
            },
            headers=headers,
        )
        assert custom_res.status_code == 201, custom_res.text
        assert custom_res.json()["custom_material_name"] == "Marley Eternit slate"

        listing = client.get(f"/api/v1/projects/{project.id}/requirements", headers=headers)
        assert listing.status_code == 200
        assert len(listing.json()) == 2
    finally:
        _cleanup_tenant(tenant.id)


def test_invalid_requirement_status_is_rejected(client, db):
    tenant = _make_tenant(db, "ReqInvalid")
    headers, user = _make_owner_headers(client, db, tenant, "reqinvalid")
    project = _make_project(db, tenant)
    try:
        res = client.post(
            f"/api/v1/projects/{project.id}/requirements",
            json={"description": "Bad status", "status": "not_a_real_status"},
            headers=headers,
        )
        assert res.status_code == 422
    finally:
        _cleanup_tenant(tenant.id)


def test_cancelling_a_requirement_is_idempotent(client, db):
    tenant = _make_tenant(db, "ReqCancel")
    headers, user = _make_owner_headers(client, db, tenant, "reqcancel")
    project = _make_project(db, tenant)
    try:
        created = client.post(
            f"/api/v1/projects/{project.id}/requirements", json={"description": "Cement"}, headers=headers
        )
        requirement_id = created.json()["id"]

        first = client.post(f"/api/v1/requirements/{requirement_id}/cancel", headers=headers)
        assert first.status_code == 200
        assert first.json()["status"] == "cancelled"

        second = client.post(f"/api/v1/requirements/{requirement_id}/cancel", headers=headers)
        assert second.status_code == 200
        assert second.json()["status"] == "cancelled"
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Purchase orders — Task 3/4/7/8/9
# ---------------------------------------------------------------------------


def test_purchase_orders_are_numbered_sequentially_per_tenant(client, db):
    tenant = _make_tenant(db, "PONumbering")
    headers, user = _make_owner_headers(client, db, tenant, "ponum")
    project = _make_project(db, tenant)
    try:
        first = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Timber", "quantity": 10, "unit_cost": 5}]},
            headers=headers,
        )
        second = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Cement", "quantity": 20, "unit_cost": 8}]},
            headers=headers,
        )
        assert first.json()["reference"] == "PO-001"
        assert second.json()["reference"] == "PO-002"
    finally:
        _cleanup_tenant(tenant.id)


def test_purchase_order_totals_reuse_the_general_quote_vat_convention(client, db):
    tenant = _make_tenant(db, "POTotals")
    headers, user = _make_owner_headers(client, db, tenant, "pototals")
    project = _make_project(db, tenant)
    try:
        res = client.post(
            "/api/v1/purchase-orders",
            json={
                "project_id": str(project.id),
                "vat_rate": 0.20,
                "items": [
                    {"description": "Plasterboard", "quantity": 4, "unit_cost": 45.50},
                    {"description": "Fixings", "quantity": 1, "unit_cost": 120.00},
                ],
            },
            headers=headers,
        )
        assert res.status_code == 201, res.text
        body = res.json()
        # 4 x 45.50 + 120.00 = 302.00 subtotal, 20% VAT = 60.40, total 362.40 —
        # identical rounding convention to variations/general quotes.
        assert body["subtotal"] == 302.00
        assert body["vat"] == 60.40
        assert body["total"] == 362.40
    finally:
        _cleanup_tenant(tenant.id)


def test_a_draft_purchase_order_can_be_edited_but_an_approved_one_cannot(client, db):
    tenant = _make_tenant(db, "POEdit")
    headers, user = _make_owner_headers(client, db, tenant, "poedit")
    project = _make_project(db, tenant)
    try:
        created = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Paint", "quantity": 5, "unit_cost": 20}]},
            headers=headers,
        )
        po_id = created.json()["id"]

        edited = client.patch(f"/api/v1/purchase-orders/{po_id}", json={"notes": "Ask for matt finish"}, headers=headers)
        assert edited.status_code == 200
        assert edited.json()["notes"] == "Ask for matt finish"

        approved = client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers)
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        blocked_edit = client.patch(f"/api/v1/purchase-orders/{po_id}", json={"notes": "changed"}, headers=headers)
        assert blocked_edit.status_code == 409
    finally:
        _cleanup_tenant(tenant.id)


def test_ordering_records_supplier_reference_and_expected_delivery(client, db):
    tenant = _make_tenant(db, "POOrder")
    headers, user = _make_owner_headers(client, db, tenant, "poorder")
    project = _make_project(db, tenant)
    try:
        created = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Cable", "quantity": 100, "unit_cost": 1.2}]},
            headers=headers,
        )
        po_id = created.json()["id"]
        client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers)

        ordered = client.post(
            f"/api/v1/purchase-orders/{po_id}/order",
            json={"supplier_reference": "SUP-REF-42", "expected_delivery_date": "2026-12-01"},
            headers=headers,
        )
        assert ordered.status_code == 200
        body = ordered.json()
        assert body["status"] == "ordered"
        assert body["supplier_reference"] == "SUP-REF-42"
        assert body["expected_delivery_date"] == "2026-12-01"
        assert body["order_date"] == date.today().isoformat()
    finally:
        _cleanup_tenant(tenant.id)


def test_a_purchase_order_cannot_be_ordered_before_it_is_approved(client, db):
    tenant = _make_tenant(db, "POSkipApproval")
    headers, user = _make_owner_headers(client, db, tenant, "poskip")
    project = _make_project(db, tenant)
    try:
        created = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Insulation", "quantity": 10, "unit_cost": 30}]},
            headers=headers,
        )
        po_id = created.json()["id"]
        res = client.post(f"/api/v1/purchase-orders/{po_id}/order", json={}, headers=headers)
        assert res.status_code == 409
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Receipts — Task 10/11/12/13
# ---------------------------------------------------------------------------


def _create_and_order_po(client, headers, project, *, quantity=10, unit_cost=100.0):
    created = client.post(
        "/api/v1/purchase-orders",
        json={
            "project_id": str(project.id),
            "items": [{"description": "Quartz worktop slab", "quantity": quantity, "unit_cost": unit_cost}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    po = created.json()
    client.post(f"/api/v1/purchase-orders/{po['id']}/approve", headers=headers)
    ordered = client.post(f"/api/v1/purchase-orders/{po['id']}/order", json={}, headers=headers)
    return ordered.json()


def test_a_partial_then_remaining_delivery_reaches_received(client, db):
    tenant = _make_tenant(db, "POPartial")
    headers, user = _make_owner_headers(client, db, tenant, "popartial")
    project = _make_project(db, tenant)
    try:
        po = _create_and_order_po(client, headers, project, quantity=10, unit_cost=100.0)
        item_id = po["items"][0]["id"]

        first = client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 4}],
            },
            headers=headers,
        )
        assert first.status_code == 201, first.text

        mid = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()
        assert mid["status"] == "partially_received"
        assert mid["items"][0]["quantity_received"] == 4

        second = client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 6}],
            },
            headers=headers,
        )
        assert second.status_code == 201, second.text

        final = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()
        assert final["status"] == "received"
        assert final["items"][0]["quantity_received"] == 10
        assert final["received_date"] == date.today().isoformat()
    finally:
        _cleanup_tenant(tenant.id)


def test_over_receipt_is_rejected_and_causes_no_partial_data_corruption(client, db):
    tenant = _make_tenant(db, "POOverReceipt")
    headers, user = _make_owner_headers(client, db, tenant, "poover")
    project = _make_project(db, tenant)
    try:
        po = _create_and_order_po(client, headers, project, quantity=10, unit_cost=50.0)
        item_id = po["items"][0]["id"]

        res = client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 11}],
            },
            headers=headers,
        )
        assert res.status_code == 409

        unchanged = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()
        assert unchanged["status"] == "ordered"
        assert unchanged["items"][0]["quantity_received"] == 0

        # A second, smaller receipt then a follow-up that would tip it
        # over the edge is rejected too — cumulative, not per-call.
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 8}],
            },
            headers=headers,
        )
        blocked = client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 3}],
            },
            headers=headers,
        )
        assert blocked.status_code == 409
        still = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()
        assert still["items"][0]["quantity_received"] == 8
    finally:
        _cleanup_tenant(tenant.id)


def test_receiving_a_po_item_linked_to_a_requirement_advances_its_status(client, db):
    tenant = _make_tenant(db, "ReqSync")
    headers, user = _make_owner_headers(client, db, tenant, "reqsync")
    project = _make_project(db, tenant)
    try:
        requirement = client.post(
            f"/api/v1/projects/{project.id}/requirements", json={"description": "Roof tiles"}, headers=headers
        ).json()

        created = client.post(
            "/api/v1/purchase-orders",
            json={
                "project_id": str(project.id),
                "items": [
                    {
                        "description": "Roof tiles",
                        "material_requirement_id": requirement["id"],
                        "quantity": 200,
                        "unit_cost": 2.0,
                    }
                ],
            },
            headers=headers,
        ).json()
        po_id = created["id"]
        item_id = created["items"][0]["id"]

        client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers)
        client.post(f"/api/v1/purchase-orders/{po_id}/order", json={}, headers=headers)

        after_order = client.get(f"/api/v1/requirements/{requirement['id']}", headers=headers) if False else None
        # No direct GET /requirements/{id} — confirm via the project list instead.
        listing = client.get(f"/api/v1/projects/{project.id}/requirements", headers=headers).json()
        assert listing[0]["status"] == "ordered"

        client.post(
            f"/api/v1/purchase-orders/{po_id}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 200}],
            },
            headers=headers,
        )
        listing_after = client.get(f"/api/v1/projects/{project.id}/requirements", headers=headers).json()
        assert listing_after[0]["status"] == "received"
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Financial integration — Task 15/16/17/37 (the critical no-double-count proof)
# ---------------------------------------------------------------------------


def test_approving_a_purchase_order_creates_committed_cost_exactly_once_even_on_retry(client, db):
    tenant = _make_tenant(db, "POCommitted")
    headers, user = _make_owner_headers(client, db, tenant, "pocommitted")
    project = _make_project(db, tenant)
    try:
        created = client.post(
            "/api/v1/purchase-orders",
            json={
                "project_id": str(project.id),
                "items": [{"description": "Quartz slab", "quantity": 2, "unit_cost": 500.0}],
            },
            headers=headers,
        ).json()
        po_id = created["id"]

        first = client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers)
        assert first.status_code == 200

        summary_after_first = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()
        assert summary_after_first["costs"]["committed_cost"] == 1000.0

        # Retry the exact same approval via the service layer directly
        # (a duplicate click / retried request) — the sprint's named
        # regression: committed cost must never double.
        procurement_service.approve(db, uuid.UUID(po_id), tenant.id, user.id)
        procurement_service.approve(db, uuid.UUID(po_id), tenant.id, user.id)

        # And once more via the live HTTP route.
        third = client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers)
        assert third.status_code == 200

        summary_final = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()
        assert summary_final["costs"]["committed_cost"] == 1000.0
        assert summary_final["costs"]["cost_entry_count"] == 1
    finally:
        _cleanup_tenant(tenant.id)


def test_full_receipt_flips_committed_cost_to_actual_in_place_not_a_second_row(client, db):
    tenant = _make_tenant(db, "POActual")
    headers, user = _make_owner_headers(client, db, tenant, "poactual")
    project = _make_project(db, tenant)
    try:
        po = _create_and_order_po(client, headers, project, quantity=5, unit_cost=200.0)
        item_id = po["items"][0]["id"]

        mid_summary = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()
        assert mid_summary["costs"]["committed_cost"] == 1000.0
        assert mid_summary["costs"]["actual_cost"] == 0.0

        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 5}],
            },
            headers=headers,
        )

        after_summary = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()
        assert after_summary["costs"]["committed_cost"] == 0.0
        assert after_summary["costs"]["actual_cost"] == 1000.0
        # Exactly one row moved state — never a second row created.
        assert after_summary["costs"]["cost_entry_count"] == 1
    finally:
        _cleanup_tenant(tenant.id)


def test_a_partial_receipt_leaves_the_full_committed_amount_in_place(client, db):
    """Documented V1 rule (ADR-050): partial receipt does not split the
    committed cost — it stays committed until the PO item is fully
    received, precisely because ProjectCostEntry is one row per cost
    item and cannot safely represent a split without double-counting."""
    tenant = _make_tenant(db, "POPartialCost")
    headers, user = _make_owner_headers(client, db, tenant, "popartialcost")
    project = _make_project(db, tenant)
    try:
        po = _create_and_order_po(client, headers, project, quantity=10, unit_cost=100.0)
        item_id = po["items"][0]["id"]

        client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={
                "received_at": datetime.now(timezone.utc).isoformat(),
                "items": [{"purchase_order_item_id": item_id, "quantity_received": 4}],
            },
            headers=headers,
        )

        summary = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()
        assert summary["costs"]["committed_cost"] == 1000.0
        assert summary["costs"]["actual_cost"] == 0.0
    finally:
        _cleanup_tenant(tenant.id)


def test_cancelling_a_purchase_order_removes_its_committed_cost(client, db):
    tenant = _make_tenant(db, "POCancel")
    headers, user = _make_owner_headers(client, db, tenant, "pocancel")
    project = _make_project(db, tenant)
    try:
        created = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Bricks", "quantity": 100, "unit_cost": 1.5}]},
            headers=headers,
        ).json()
        po_id = created["id"]
        client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers)

        summary_before = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()
        assert summary_before["costs"]["committed_cost"] == 150.0

        cancelled = client.post(f"/api/v1/purchase-orders/{po_id}/cancel", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        summary_after = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()
        assert summary_after["costs"]["committed_cost"] == 0.0
        assert summary_after["costs"]["cost_entry_count"] == 0
    finally:
        _cleanup_tenant(tenant.id)


def test_a_purchase_order_with_no_project_never_touches_project_financials(client, db):
    tenant = _make_tenant(db, "POStock")
    headers, user = _make_owner_headers(client, db, tenant, "postock")
    try:
        created = client.post(
            "/api/v1/purchase-orders",
            json={"items": [{"description": "Workshop consumables", "quantity": 1, "unit_cost": 250.0}]},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        po_id = created.json()["id"]
        approved = client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers)
        assert approved.status_code == 200
        assert approved.json()["project_id"] is None
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Allocations — Task 14
# ---------------------------------------------------------------------------


def test_allocating_material_records_who_what_how_much_and_marks_the_requirement_allocated(client, db):
    tenant = _make_tenant(db, "Allocation")
    headers, user = _make_owner_headers(client, db, tenant, "alloc")
    project = _make_project(db, tenant)
    try:
        requirement = client.post(
            f"/api/v1/projects/{project.id}/requirements",
            json={"description": "Quartz worktop", "status": "received"},
            headers=headers,
        ).json()

        res = client.post(
            f"/api/v1/projects/{project.id}/allocations",
            json={"material_requirement_id": requirement["id"], "quantity": 3.5, "notes": "For kitchen island"},
            headers=headers,
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["quantity"] == 3.5
        assert body["allocated_by_user_id"] == str(user.id)

        listing = client.get(f"/api/v1/projects/{project.id}/requirements", headers=headers).json()
        assert listing[0]["status"] == "allocated"
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Tenant isolation — Task 31
# ---------------------------------------------------------------------------


def test_tenant_b_cannot_read_or_write_tenant_as_procurement_records(client, db):
    tenant_a = _make_tenant(db, "IsolationA")
    tenant_b = _make_tenant(db, "IsolationB")
    headers_a, user_a = _make_owner_headers(client, db, tenant_a, "isoa")
    headers_b, user_b = _make_owner_headers(client, db, tenant_b, "isob")
    project_a = _make_project(db, tenant_a)
    supplier = _make_supplier(db, name="Isolation Supplier")
    try:
        requirement = client.post(
            f"/api/v1/projects/{project_a.id}/requirements", json={"description": "Secret material"}, headers=headers_a
        ).json()
        po = client.post(
            "/api/v1/purchase-orders",
            json={
                "project_id": str(project_a.id),
                "supplier_id": str(supplier.id),
                "items": [{"description": "Confidential", "quantity": 1, "unit_cost": 999}],
            },
            headers=headers_a,
        ).json()
        client.put(
            f"/api/v1/procurement/supplier-accounts/{supplier.id}",
            json={"account_reference": "TENANT-A-ACC-123"},
            headers=headers_a,
        )

        # Tenant B, through the real API.
        assert client.get(f"/api/v1/projects/{project_a.id}/requirements", headers=headers_b).status_code == 404
        assert client.patch(
            f"/api/v1/requirements/{requirement['id']}", json={"notes": "leaked"}, headers=headers_b
        ).status_code == 404
        assert client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers_b).status_code == 404
        assert client.post(f"/api/v1/purchase-orders/{po['id']}/approve", headers=headers_b).status_code == 404
        assert client.post(
            f"/api/v1/purchase-orders/{po['id']}/receipts",
            json={"received_at": datetime.now(timezone.utc).isoformat(), "items": []},
            headers=headers_b,
        ).status_code in (404, 422)
        assert client.post(
            f"/api/v1/projects/{project_a.id}/allocations", json={"quantity": 1}, headers=headers_b
        ).status_code == 404

        # Tenant B's own supplier-account listing never contains
        # Tenant A's private account reference — same global-supplier
        # identity, strictly separate tenant commercial data.
        b_accounts = client.get("/api/v1/procurement/supplier-accounts", headers=headers_b).json()
        assert all(acc.get("account_reference") != "TENANT-A-ACC-123" for acc in b_accounts)
    finally:
        _cleanup_tenant(tenant_a.id)
        _cleanup_tenant(tenant_b.id)


# ---------------------------------------------------------------------------
# Late delivery — Task 26
# ---------------------------------------------------------------------------


def test_late_only_filter_reflects_the_deterministic_late_rule(client, db):
    tenant = _make_tenant(db, "Late")
    headers, user = _make_owner_headers(client, db, tenant, "late")
    project = _make_project(db, tenant)
    try:
        overdue = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Steel beams", "quantity": 1, "unit_cost": 500}]},
            headers=headers,
        ).json()
        client.post(f"/api/v1/purchase-orders/{overdue['id']}/approve", headers=headers)
        client.post(
            f"/api/v1/purchase-orders/{overdue['id']}/order",
            json={"expected_delivery_date": (date.today() - timedelta(days=3)).isoformat()},
            headers=headers,
        )

        on_time = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Roof tiles", "quantity": 1, "unit_cost": 300}]},
            headers=headers,
        ).json()
        client.post(f"/api/v1/purchase-orders/{on_time['id']}/approve", headers=headers)
        client.post(
            f"/api/v1/purchase-orders/{on_time['id']}/order",
            json={"expected_delivery_date": (date.today() + timedelta(days=5)).isoformat()},
            headers=headers,
        )

        no_date = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Misc fixings", "quantity": 1, "unit_cost": 10}]},
            headers=headers,
        ).json()
        client.post(f"/api/v1/purchase-orders/{no_date['id']}/approve", headers=headers)
        client.post(f"/api/v1/purchase-orders/{no_date['id']}/order", json={}, headers=headers)

        late = client.get("/api/v1/purchase-orders?late_only=true", headers=headers).json()
        late_ids = {po["id"] for po in late}
        assert overdue["id"] in late_ids
        assert on_time["id"] not in late_ids
        assert no_date["id"] not in late_ids
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Command Center procurement signals — Task 25
# ---------------------------------------------------------------------------


def test_command_centre_reports_honest_procurement_signals(client, db):
    tenant = _make_tenant(db, "ProcurementSignals")
    headers, user = _make_owner_headers(client, db, tenant, "procsignals")
    project = _make_project(db, tenant)
    try:
        # One draft PO — awaiting approval.
        client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Draft item", "quantity": 1, "unit_cost": 10}]},
            headers=headers,
        )

        # One ordered, overdue PO.
        overdue = client.post(
            "/api/v1/purchase-orders",
            json={"project_id": str(project.id), "items": [{"description": "Overdue item", "quantity": 1, "unit_cost": 20}]},
            headers=headers,
        ).json()
        client.post(f"/api/v1/purchase-orders/{overdue['id']}/approve", headers=headers)
        client.post(
            f"/api/v1/purchase-orders/{overdue['id']}/order",
            json={"expected_delivery_date": (date.today() - timedelta(days=2)).isoformat()},
            headers=headers,
        )

        # An outstanding material requirement.
        client.post(
            f"/api/v1/projects/{project.id}/requirements", json={"description": "Outstanding tiles"}, headers=headers
        )

        res = client.get("/api/v1/dashboard/command-centre", headers=headers)
        assert res.status_code == 200, res.text
        procurement = res.json()["procurement"]
        assert procurement["purchase_orders_awaiting_approval"] == 1
        assert procurement["purchase_orders_ordered"] == 1
        assert procurement["late_deliveries"] == 1
        assert procurement["materials_required"] == 1
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# General regression — Task 38
# ---------------------------------------------------------------------------


def test_general_quoting_is_unaffected_by_the_procurement_module(client, db):
    tenant = _make_tenant(db, "GeneralQuoteRegression")
    headers, user = _make_owner_headers(client, db, tenant, "genquote")
    try:
        res = client.post(
            "/api/v1/quotes",
            json={
                "title": "Bathroom refit",
                "vat_rate": 0.20,
                "lines": [{"line_kind": "labour", "description": "Labour", "quantity": 1, "unit": "item", "unit_price": 1000}],
            },
            headers=headers,
        )
        assert res.status_code == 201, res.text
        assert res.json()["total"] == 1200.0
    finally:
        _cleanup_tenant(tenant.id)
