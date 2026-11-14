"""STONE-GATE / DEF-003 -- the material-ready gate must reflect what really
arrived. Each test states required behaviour, against the seeded stone_v1
fabrication stage rather than a hand-configured gate."""

import uuid
from datetime import datetime, timezone

import pytest

from app.database import crud
from app.workflows.gates import evaluate_stage_gates
from tests.test_procurement import (
    _cleanup_tenant,
    _make_owner_headers,
    _make_project,
    _make_tenant,
    db,  # noqa: F401 - pytest fixture
)

CREATED = (200, 201)


def _fabrication(session):
    template = crud.get_system_workflow_template_by_key(session, "stone_v1")
    return crud.get_workflow_stage_by_key(session, template.id, "fabrication")


def _codes(session, project, tenant):
    session.expire_all()
    return [b.code for b in evaluate_stage_gates(session, project, tenant.id, _fabrication(session))]


def _requirement(client, headers, project, **fields):
    body = {"description": "Calacatta 20mm", **fields}
    response = client.post(f"/api/v1/projects/{project.id}/requirements", json=body, headers=headers)
    assert response.status_code in CREATED, response.text
    return response.json()


def _po(client, headers, project, items):
    response = client.post(
        "/api/v1/purchase-orders",
        json={"project_id": str(project.id), "items": [{"unit_cost": 10.0, **i} for i in items]},
        headers=headers,
    )
    assert response.status_code in CREATED, response.text
    return response.json()


def _linked_po(client, headers, project, requirement, quantity):
    return _po(
        client,
        headers,
        project,
        [{"description": "Slab", "material_requirement_id": requirement["id"], "quantity": quantity}],
    )


def _order(client, headers, po_id):
    assert client.post(f"/api/v1/purchase-orders/{po_id}/approve", headers=headers).status_code == 200
    assert client.post(f"/api/v1/purchase-orders/{po_id}/order", json={}, headers=headers).status_code == 200


def _receive(client, headers, po_id, lines, **extra):
    return client.post(
        f"/api/v1/purchase-orders/{po_id}/receipts",
        json={
            "received_at": datetime.now(timezone.utc).isoformat(),
            "items": [{"purchase_order_item_id": i, "quantity_received": q} for i, q in lines],
            **extra,
        },
        headers=headers,
    )


def _status(client, headers, project, requirement_id):
    rows = client.get(f"/api/v1/projects/{project.id}/requirements", headers=headers).json()
    return next(r["status"] for r in rows if r["id"] == requirement_id)


@pytest.fixture()
def job(client, db):  # noqa: F811
    tenant = _make_tenant(db, f"StoneGate{uuid.uuid4().hex[:6]}")
    headers, _ = _make_owner_headers(client, db, tenant, "stonegate")
    project = _make_project(db, tenant)
    yield tenant, headers, project
    _cleanup_tenant(tenant.id)


def test_linked_full_receipt_clears_the_gate(client, db, job):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10, unit="m2")
    assert _codes(db, project, tenant) == ["materials_ready"]
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    assert _codes(db, project, tenant) == ["materials_ready"]
    assert _receive(client, headers, po["id"], [(po["items"][0]["id"], 10)]).status_code in CREATED
    assert _status(client, headers, project, req["id"]) == "received"
    assert _codes(db, project, tenant) == []


def test_partial_receipt_keeps_the_gate_closed(client, db, job):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    _receive(client, headers, po["id"], [(po["items"][0]["id"], 4)])
    assert _status(client, headers, project, req["id"]) == "partially_received"
    assert _codes(db, project, tenant) == ["materials_ready"]


def test_decimal_part_deliveries_can_complete_an_order(client, db, job):  # noqa: F811
    """1.1 + 1.1 + 1.1 is 3.3000000000000003 in binary floats; the last real
    delivery must not be refused as an over-receipt."""
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=3.3)
    po = _linked_po(client, headers, project, req, 3.3)
    _order(client, headers, po["id"])
    for _ in range(3):
        response = _receive(client, headers, po["id"], [(po["items"][0]["id"], 1.1)])
        assert response.status_code in CREATED, response.text
    assert _status(client, headers, project, req["id"]) == "received"
    assert _codes(db, project, tenant) == []


def test_receiving_less_than_required_does_not_open_the_gate(client, db, job):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 5)
    _order(client, headers, po["id"])
    _receive(client, headers, po["id"], [(po["items"][0]["id"], 5)])
    assert _status(client, headers, project, req["id"]) == "partially_received"
    assert _codes(db, project, tenant) == ["materials_ready"]


def test_one_of_two_linked_lines_does_not_open_the_gate(client, db, job):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project)
    po = _po(
        client,
        headers,
        project,
        [
            {"description": "Slab A", "material_requirement_id": req["id"], "quantity": 5},
            {"description": "Slab B", "material_requirement_id": req["id"], "quantity": 5},
        ],
    )
    _order(client, headers, po["id"])
    _receive(client, headers, po["id"], [(po["items"][0]["id"], 5)])
    assert _codes(db, project, tenant) == ["materials_ready"]
    _receive(client, headers, po["id"], [(po["items"][1]["id"], 5)])
    assert _codes(db, project, tenant) == []


@pytest.mark.parametrize("state", ["draft", "approved", "cancelled"])
def test_a_po_not_on_order_cannot_receive_or_open_the_gate(client, db, job, state):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    if state != "draft":
        assert client.post(f"/api/v1/purchase-orders/{po['id']}/approve", headers=headers).status_code == 200
    if state == "cancelled":
        assert client.post(f"/api/v1/purchase-orders/{po['id']}/cancel", headers=headers).status_code == 200
    response = _receive(client, headers, po["id"], [(po["items"][0]["id"], 10)])
    assert response.status_code == 409, response.text
    assert _codes(db, project, tenant) == ["materials_ready"]


def test_cancelling_the_only_po_releases_the_ordered_requirement(client, db, job):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    assert _status(client, headers, project, req["id"]) == "ordered"
    assert client.post(f"/api/v1/purchase-orders/{po['id']}/cancel", headers=headers).status_code == 200
    assert _status(client, headers, project, req["id"]) == "required"
    assert _codes(db, project, tenant) == ["materials_ready"]


def test_unlinked_po_item_can_be_linked_after_ordering_and_catches_up(client, db, job):  # noqa: F811
    """The reported STONE-GATE symptom: everything delivered, gate still shut,
    because the line was never linked, with no way to repair it afterwards."""
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _po(client, headers, project, [{"description": "Slab", "quantity": 10}])
    _order(client, headers, po["id"])
    item_id = po["items"][0]["id"]
    _receive(client, headers, po["id"], [(item_id, 10)])
    assert _codes(db, project, tenant) == ["materials_ready"]
    response = client.post(
        f"/api/v1/purchase-orders/{po['id']}/items/{item_id}/link-requirement",
        json={"material_requirement_id": req["id"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert _status(client, headers, project, req["id"]) == "received"
    assert _codes(db, project, tenant) == []


def test_po_item_cannot_link_another_projects_or_tenants_requirement(client, db, job):  # noqa: F811
    tenant, headers, project = job
    other_project = _make_project(db, tenant, name="Other job")
    foreign_req = _requirement(client, headers, other_project)
    other_tenant = _make_tenant(db, f"StoneGateB{uuid.uuid4().hex[:6]}")
    try:
        headers_b, _ = _make_owner_headers(client, db, other_tenant, "stonegateb")
        project_b = _make_project(db, other_tenant)
        tenant_b_req = _requirement(client, headers_b, project_b)
        for requirement_id in (foreign_req["id"], tenant_b_req["id"]):
            response = client.post(
                "/api/v1/purchase-orders",
                json={
                    "project_id": str(project.id),
                    "items": [
                        {
                            "description": "Slab",
                            "material_requirement_id": requirement_id,
                            "quantity": 1,
                            "unit_cost": 1.0,
                        }
                    ],
                },
                headers=headers,
            )
            assert response.status_code in (404, 409, 422), response.text
    finally:
        _cleanup_tenant(other_tenant.id)


def test_retried_delivery_with_same_key_is_not_counted_twice(client, db, job):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    item_id = po["items"][0]["id"]
    key = str(uuid.uuid4())
    first = _receive(client, headers, po["id"], [(item_id, 5)], idempotency_key=key)
    second = _receive(client, headers, po["id"], [(item_id, 5)], idempotency_key=key)
    assert first.status_code in CREATED, first.text
    assert second.status_code in CREATED, second.text
    assert first.json()["id"] == second.json()["id"]
    assert _status(client, headers, project, req["id"]) == "partially_received"
    assert _codes(db, project, tenant) == ["materials_ready"]


# --- Phase 2 hardening: transactions, concurrency, ledger, ownership -----


def _costs(client, headers, project):
    return client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers).json()["costs"]


def _receipt_count(client, headers, po_id):
    return len(client.get(f"/api/v1/purchase-orders/{po_id}/receipts", headers=headers).json())


def test_no_requirements_leaves_the_materials_gate_open(client, db, job):  # noqa: F811
    tenant, _headers, project = job
    assert _codes(db, project, tenant) == []


def test_one_received_requirement_does_not_clear_another_outstanding_one(client, db, job):  # noqa: F811
    tenant, headers, project = job
    done = _requirement(client, headers, project, required_quantity=2)
    _requirement(client, headers, project, description="Edge profile", required_quantity=1)
    po = _linked_po(client, headers, project, done, 2)
    _order(client, headers, po["id"])
    _receive(client, headers, po["id"], [(po["items"][0]["id"], 2)])
    assert _status(client, headers, project, done["id"]) == "received"
    assert _codes(db, project, tenant) == ["materials_ready"]


def test_duplicate_lines_for_one_item_in_a_delivery_cannot_over_receive(client, db, job):  # noqa: F811
    _tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    item_id = po["items"][0]["id"]
    response = _receive(client, headers, po["id"], [(item_id, 6), (item_id, 6)])
    assert response.status_code == 409, response.text
    assert _receipt_count(client, headers, po["id"]) == 0
    assert _status(client, headers, project, req["id"]) == "ordered"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "0"])
def test_non_finite_or_non_positive_quantities_are_rejected(client, db, job, bad):  # noqa: F811
    _tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    body = '{"received_at": "%s", "items": [{"purchase_order_item_id": "%s", "quantity_received": %s}]}' % (
        datetime.now(timezone.utc).isoformat(),
        po["items"][0]["id"],
        bad,
    )
    response = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receipts",
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert _receipt_count(client, headers, po["id"]) == 0


def test_a_failure_mid_receipt_writes_nothing(client, db, job, monkeypatch):  # noqa: F811
    """Receipt rows, cost ledger, requirement and PO status commit together."""
    from app.procurement.service import ProcurementService

    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    before = _costs(client, headers, project)

    def boom(*_args, **_kwargs):
        raise RuntimeError("injected failure after the receipt rows were flushed")

    monkeypatch.setattr(ProcurementService, "_sync_requirement", boom)
    with pytest.raises(RuntimeError):
        _receive(client, headers, po["id"], [(po["items"][0]["id"], 10)])
    monkeypatch.undo()

    assert _receipt_count(client, headers, po["id"]) == 0
    assert client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()["status"] == "ordered"
    assert _costs(client, headers, project) == before
    assert _status(client, headers, project, req["id"]) == "ordered"
    # And the same delivery then succeeds normally.
    assert _receive(client, headers, po["id"], [(po["items"][0]["id"], 10)]).status_code in CREATED
    assert _codes(db, project, tenant) == []


def test_cost_moves_committed_to_actual_once_across_partials_and_retries(client, db, job):  # noqa: F811
    _tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=4)
    po = _po(
        client,
        headers,
        project,
        [{"description": "Slab", "material_requirement_id": req["id"], "quantity": 4, "unit_cost": 250.0}],
    )
    _order(client, headers, po["id"])
    item_id = po["items"][0]["id"]
    assert _costs(client, headers, project)["committed_cost"] == 1000.0
    _receive(client, headers, po["id"], [(item_id, 1)], idempotency_key=f"k-part-{uuid.uuid4()}")
    assert _costs(client, headers, project)["committed_cost"] == 1000.0
    final_key = f"k-final-{uuid.uuid4()}"
    for _ in range(2):  # the final delivery, retried after a lost response
        assert _receive(client, headers, po["id"], [(item_id, 3)], idempotency_key=final_key).status_code in CREATED
    costs = _costs(client, headers, project)
    assert costs["committed_cost"] == 0.0
    assert costs["actual_cost"] == 1000.0
    assert costs["cost_entry_count"] == 1
    assert _receipt_count(client, headers, po["id"]) == 2


def test_a_reused_key_cannot_change_what_was_recorded(client, db, job):  # noqa: F811
    _tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    other = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    _order(client, headers, other["id"])
    item_id = po["items"][0]["id"]
    key = f"k1-{uuid.uuid4()}"
    assert _receive(client, headers, po["id"], [(item_id, 2)], idempotency_key=key).status_code in CREATED
    changed = _receive(client, headers, po["id"], [(item_id, 9)], idempotency_key=key)
    assert changed.status_code == 409, changed.text
    elsewhere = _receive(client, headers, other["id"], [(other["items"][0]["id"], 2)], idempotency_key=key)
    assert elsewhere.status_code == 409, elsewhere.text
    assert _receipt_count(client, headers, po["id"]) == 1
    assert _receipt_count(client, headers, other["id"]) == 0


def test_concurrent_deliveries_cannot_together_over_receive(client, db, job):  # noqa: F811
    """Two sessions race to receive 6 of an ordered 10. The PO row lock makes
    the second wait and then see the first, so exactly one is accepted."""
    import threading

    from app.database.database import SessionLocal
    from app.procurement.models import OverReceiptError, PurchaseReceiptCreate
    from app.procurement.service import procurement_service

    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    payload = PurchaseReceiptCreate(
        received_at=datetime.now(timezone.utc),
        items=[{"purchase_order_item_id": po["items"][0]["id"], "quantity_received": 6}],
    )
    barrier = threading.Barrier(2)
    outcomes = []

    def deliver():
        session = SessionLocal()
        try:
            barrier.wait()
            procurement_service.record_receipt(session, uuid.UUID(po["id"]), tenant.id, None, payload)
            outcomes.append("ok")
        except OverReceiptError:
            outcomes.append("over")
        finally:
            session.close()

    threads = [threading.Thread(target=deliver) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(outcomes) == ["ok", "over"]
    assert _receipt_count(client, headers, po["id"]) == 1
    assert _status(client, headers, project, req["id"]) == "partially_received"


def test_failed_link_leaves_the_line_unlinked(client, db, job, monkeypatch):  # noqa: F811
    from app.procurement.service import ProcurementService

    _tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _po(client, headers, project, [{"description": "Slab", "quantity": 10}])
    _order(client, headers, po["id"])
    item_id = po["items"][0]["id"]

    def boom(*_args, **_kwargs):
        raise RuntimeError("injected failure after the link was flushed")

    monkeypatch.setattr(ProcurementService, "_sync_requirement", boom)
    with pytest.raises(RuntimeError):
        client.post(
            f"/api/v1/purchase-orders/{po['id']}/items/{item_id}/link-requirement",
            json={"material_requirement_id": req["id"]},
            headers=headers,
        )
    monkeypatch.undo()
    line = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers).json()["items"][0]
    assert line["material_requirement_id"] is None


def test_receipt_after_cancellation_is_refused_and_delivered_goods_still_count(client, db, job):  # noqa: F811
    tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _linked_po(client, headers, project, req, 10)
    _order(client, headers, po["id"])
    _receive(client, headers, po["id"], [(po["items"][0]["id"], 4)])
    assert client.post(f"/api/v1/purchase-orders/{po['id']}/cancel", headers=headers).status_code == 200
    assert _receive(client, headers, po["id"], [(po["items"][0]["id"], 6)]).status_code == 409
    assert _status(client, headers, project, req["id"]) == "partially_received"
    assert _codes(db, project, tenant) == ["materials_ready"]
    # A replacement order for the balance completes the requirement.
    replacement = _linked_po(client, headers, project, req, 6)
    _order(client, headers, replacement["id"])
    _receive(client, headers, replacement["id"], [(replacement["items"][0]["id"], 6)])
    assert _status(client, headers, project, req["id"]) == "received"
    assert _codes(db, project, tenant) == []


def test_allocation_cannot_clear_another_projects_gate(client, db, job):  # noqa: F811
    tenant, headers, project = job
    other_project = _make_project(db, tenant, name="Other job")
    foreign = _requirement(client, headers, other_project, required_quantity=1)
    response = client.post(
        f"/api/v1/projects/{project.id}/allocations",
        json={"material_requirement_id": foreign["id"], "quantity": 1},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert _status(client, headers, other_project, foreign["id"]) == "required"
    assert _codes(db, other_project, tenant) == ["materials_ready"]


def test_another_workspace_cannot_receive_or_link_on_this_po(client, db, job):  # noqa: F811
    _tenant, headers, project = job
    req = _requirement(client, headers, project, required_quantity=10)
    po = _po(client, headers, project, [{"description": "Slab", "quantity": 10}])
    _order(client, headers, po["id"])
    item_id = po["items"][0]["id"]
    intruder = _make_tenant(db, f"StoneGateX{uuid.uuid4().hex[:6]}")
    try:
        intruder_headers, _ = _make_owner_headers(client, db, intruder, "stonegatex")
        assert _receive(client, intruder_headers, po["id"], [(item_id, 10)]).status_code == 404
        link = client.post(
            f"/api/v1/purchase-orders/{po['id']}/items/{item_id}/link-requirement",
            json={"material_requirement_id": req["id"]},
            headers=intruder_headers,
        )
        assert link.status_code == 404, link.text
    finally:
        _cleanup_tenant(intruder.id)
    assert _receipt_count(client, headers, po["id"]) == 0
