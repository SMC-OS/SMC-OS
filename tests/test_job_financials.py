"""GeoCore Premium OS Plan 04 (Sprint 043) — Job Financials + Variations.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Project,
    ProjectCostEntry,
    Quote,
    QuoteItem,
    Subscription,
    Tenant,
    User,
    Variation,
    VariationItem,
)
from app.financials.service import (
    build_contract_summary,
    build_cost_summary,
    build_profitability_summary,
    financials_service,
    resolve_base_contract,
)
from app.financials.models import ProjectCostEntryIn, ProjectCostEntryUpdate
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service
from app.variations.models import VariationCreate, VariationItemIn, VariationUpdate
from app.variations.service import (
    VariationEditStateError,
    VariationTransitionError,
    variation_service,
)

RUN_ID = uuid.uuid4().hex[:8]
STRONG_PASSWORD = "Financials-Test-Password-1!"


def _unique_email(label: str) -> str:
    return f"pytest-financials-{RUN_ID}-{label}-{uuid.uuid4().hex[:6]}@example.invalid"


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_tenant(db, name: str) -> Tenant:
    return tenant_service.create(db, TenantCreate(name=f"{name} {RUN_ID}"))


def _make_owner_headers(client, db, tenant: Tenant, label: str) -> dict:
    email = _unique_email(label)
    user = auth_service.create_user(
        db, tenant_id=tenant.id, name="Pytest Financials Owner", email=email, password=STRONG_PASSWORD, role="Owner"
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user


def _make_project(db, tenant, *, name="Pytest Financials Project", quote_id=None) -> Project:
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
        quote_id=quote_id,
        workflow_template_id=workflow_template_id,
        workflow_stage_id=workflow_stage_id,
    )


def _make_project_with_approved_quote(client, headers, db, tenant) -> Project:
    """A real base contract, exactly the way one is created in production:
    price a general quote, approve it, hand it off."""
    create = client.post(
        "/api/v1/quotes",
        json={
            "title": f"Pytest Financials Job {uuid.uuid4().hex[:6]}",
            "vat_rate": 0.20,
            "lines": [
                {"line_kind": "labour", "description": "Labour", "quantity": 1, "unit": "item", "unit_price": 20000.0}
            ],
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    quote_id = create.json()["id"]

    approve = client.post(f"/api/v1/quotes/{quote_id}/approve", headers=headers)
    assert approve.status_code == 200, approve.text

    handoff = client.post(f"/api/v1/quotes/{quote_id}/handoff", headers=headers)
    assert handoff.status_code == 200, handoff.text
    project_id = handoff.json()["id"]

    return crud.get_project_by_id(db, uuid.UUID(project_id), tenant.id)


def _cleanup_tenant(tenant_id):
    db = SessionLocal()
    try:
        variation_ids = [row[0] for row in db.query(Variation.id).filter(Variation.tenant_id == tenant_id).all()]
        if variation_ids:
            db.execute(delete(VariationItem).where(VariationItem.variation_id.in_(variation_ids)))
        db.execute(delete(Variation).where(Variation.tenant_id == tenant_id))
        db.execute(delete(ProjectCostEntry).where(ProjectCostEntry.tenant_id == tenant_id))
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
# Task 1/3/4 — pure calculation functions (no DB)
# ---------------------------------------------------------------------------


def test_resolve_base_contract_uses_the_linked_approved_quotes_total():
    class FakeQuote:
        total = 24000.0

    value, source = resolve_base_contract(project=None, quote=FakeQuote())
    assert value == 24000.0
    assert source == "approved_quote"


def test_resolve_base_contract_is_unset_not_zero_when_no_quote_is_linked():
    value, source = resolve_base_contract(project=None, quote=None)
    assert value is None
    assert source is None


def test_forecast_cost_sums_all_three_states_without_double_counting():
    summary = build_cost_summary({"budgeted": 1000.0, "committed": 500.0, "actual": 200.0}, entry_count=3, workflow_role="in_progress")
    assert summary.budgeted_cost == 1000.0
    assert summary.committed_cost == 500.0
    assert summary.actual_cost == 200.0
    assert summary.forecast_cost == 1700.0


def test_cost_data_status_is_none_when_no_entries_exist():
    summary = build_cost_summary({}, entry_count=0, workflow_role="in_progress")
    assert summary.cost_data_status == "none"
    assert summary.forecast_cost == 0.0


def test_cost_data_status_is_partial_while_the_project_is_still_open():
    summary = build_cost_summary({"actual": 100.0}, entry_count=1, workflow_role="in_progress")
    assert summary.cost_data_status == "partial"


def test_cost_data_status_is_complete_once_the_project_workflow_is_completed():
    summary = build_cost_summary({"actual": 100.0}, entry_count=1, workflow_role="completed")
    assert summary.cost_data_status == "complete"


def test_current_contract_value_is_base_plus_approved_variations():
    contract = build_contract_summary(24000.0, "approved_quote", 3250.0)
    assert contract.current_contract_value == 27250.0
    assert contract.approved_variations_total == 3250.0


def test_current_contract_value_is_none_when_base_contract_is_unknown():
    contract = build_contract_summary(None, None, 3250.0)
    assert contract.current_contract_value is None
    # Approved variations are still a real, independently-computable number.
    assert contract.approved_variations_total == 3250.0


def test_profitability_never_fabricates_a_margin_from_a_single_small_cost():
    """Task 4's explicit warning: one small recorded cost must never
    produce a confident-looking margin percentage."""
    contract = build_contract_summary(24000.0, "approved_quote", 0.0)
    costs = build_cost_summary({}, entry_count=0, workflow_role="in_progress")
    profitability = build_profitability_summary(contract, costs)
    assert profitability.forecast_gross_profit is None
    assert profitability.forecast_gross_margin_percent is None
    assert profitability.margin_risk is False


def test_profitability_computes_once_real_cost_data_exists():
    contract = build_contract_summary(24000.0, "approved_quote", 0.0)
    costs = build_cost_summary({"actual": 20000.0}, entry_count=1, workflow_role="in_progress")
    profitability = build_profitability_summary(contract, costs)
    assert profitability.forecast_gross_profit == 4000.0
    assert profitability.forecast_gross_margin_percent == pytest.approx(16.6667, rel=1e-3)
    assert profitability.margin_risk is False


def test_profitability_flags_margin_risk_below_the_conservative_threshold():
    contract = build_contract_summary(24000.0, "approved_quote", 0.0)
    costs = build_cost_summary({"actual": 22000.0}, entry_count=1, workflow_role="in_progress")
    profitability = build_profitability_summary(contract, costs)
    assert profitability.forecast_gross_margin_percent == pytest.approx(8.333, rel=1e-3)
    assert profitability.margin_risk is True


def test_profitability_never_computed_on_a_null_or_zero_contract():
    contract = build_contract_summary(None, None, 0.0)
    costs = build_cost_summary({"actual": 100.0}, entry_count=1, workflow_role="in_progress")
    assert build_profitability_summary(contract, costs).forecast_gross_margin_percent is None

    zero_contract = build_contract_summary(0.0, "approved_quote", 0.0)
    assert build_profitability_summary(zero_contract, costs).forecast_gross_margin_percent is None


# ---------------------------------------------------------------------------
# Task 2/3/26 — cost ledger CRUD + aggregation, through the real service
# ---------------------------------------------------------------------------


def test_cost_crud_and_state_aggregation_end_to_end(client, db):
    tenant = _make_tenant(db, "CostLedgerTenant")
    headers, user = _make_owner_headers(client, db, tenant, "cost-ledger")
    try:
        project = _make_project(db, tenant)

        budgeted = financials_service.create_cost_entry(
            db, project.id, tenant.id, user.id,
            ProjectCostEntryIn(category="material", state="budgeted", description="Kitchen units", total_cost=4000.0),
        )
        committed = financials_service.create_cost_entry(
            db, project.id, tenant.id, user.id,
            ProjectCostEntryIn(category="subcontractor", state="committed", description="Electrician", total_cost=1500.0),
        )
        actual = financials_service.create_cost_entry(
            db, project.id, tenant.id, user.id,
            ProjectCostEntryIn(category="labour", state="actual", description="Own labour", total_cost=800.0),
        )

        summary = financials_service.get_summary(db, project.id, tenant.id)
        assert summary.costs.budgeted_cost == 4000.0
        assert summary.costs.committed_cost == 1500.0
        assert summary.costs.actual_cost == 800.0
        assert summary.costs.forecast_cost == 6300.0
        assert summary.costs.cost_data_status == "partial"

        updated = financials_service.update_cost_entry(
            db, project.id, budgeted.id, tenant.id, ProjectCostEntryUpdate(state="committed", total_cost=4200.0)
        )
        assert updated.state == "committed"
        assert updated.total_cost == 4200.0

        summary = financials_service.get_summary(db, project.id, tenant.id)
        assert summary.costs.budgeted_cost == 0.0
        assert summary.costs.committed_cost == pytest.approx(4200.0 + 1500.0)

        financials_service.delete_cost_entry(db, project.id, actual.id, tenant.id)
        entries = financials_service.list_cost_entries(db, project.id, tenant.id)
        assert {e.id for e in entries} == {budgeted.id, committed.id}
    finally:
        _cleanup_tenant(tenant.id)


def test_invalid_cost_category_and_state_are_rejected():
    with pytest.raises(Exception):
        ProjectCostEntryIn(category="not-a-real-category", state="budgeted", description="x", total_cost=1)
    with pytest.raises(Exception):
        ProjectCostEntryIn(category="material", state="not-a-real-state", description="x", total_cost=1)


def test_negative_cost_is_rejected():
    with pytest.raises(Exception):
        ProjectCostEntryIn(category="material", state="budgeted", description="x", total_cost=-1)


# ---------------------------------------------------------------------------
# Task 22 — tenant isolation for costs
# ---------------------------------------------------------------------------


def test_tenant_b_cannot_read_or_write_tenant_as_costs(client, db):
    tenant_a = _make_tenant(db, "CostIsoA")
    tenant_b = _make_tenant(db, "CostIsoB")
    headers_a, user_a = _make_owner_headers(client, db, tenant_a, "cost-iso-a")
    headers_b, _ = _make_owner_headers(client, db, tenant_b, "cost-iso-b")
    try:
        project = _make_project(db, tenant_a)
        entry = financials_service.create_cost_entry(
            db, project.id, tenant_a.id, user_a.id,
            ProjectCostEntryIn(category="material", state="actual", description="Secret cost", total_cost=999.0),
        )

        # Read
        resp = client.get(f"/api/v1/projects/{project.id}/costs", headers=headers_b)
        assert resp.status_code == 404

        # Write (create)
        resp = client.post(
            f"/api/v1/projects/{project.id}/costs",
            json={"category": "material", "state": "actual", "description": "x", "total_cost": 1},
            headers=headers_b,
        )
        assert resp.status_code == 404

        # Update / delete
        resp = client.patch(
            f"/api/v1/projects/{project.id}/costs/{entry.id}",
            json={"total_cost": 1},
            headers=headers_b,
        )
        assert resp.status_code == 404
        resp = client.delete(f"/api/v1/projects/{project.id}/costs/{entry.id}", headers=headers_b)
        assert resp.status_code == 404

        # Financial summary
        resp = client.get(f"/api/v1/projects/{project.id}/financials/summary", headers=headers_b)
        assert resp.status_code == 404

        # Tenant A can still read its own data untouched.
        resp = client.get(f"/api/v1/projects/{project.id}/costs", headers=headers_a)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
    finally:
        _cleanup_tenant(tenant_a.id)
        _cleanup_tenant(tenant_b.id)


# ---------------------------------------------------------------------------
# Task 5/6/7 — variation numbering, items, VAT
# ---------------------------------------------------------------------------


def test_variations_are_numbered_sequentially_per_project(client, db):
    tenant = _make_tenant(db, "VariationNumberingTenant")
    headers, user = _make_owner_headers(client, db, tenant, "var-numbering")
    try:
        project = _make_project(db, tenant)
        v1 = variation_service.create(db, project.id, tenant.id, user.id, VariationCreate(title="First"))
        v2 = variation_service.create(db, project.id, tenant.id, user.id, VariationCreate(title="Second"))
        assert v1.reference == "V-001"
        assert v2.reference == "V-002"

        # A second, independent project's own numbering starts at V-001 again.
        other_project = _make_project(db, tenant, name="Another project")
        v_other = variation_service.create(db, other_project.id, tenant.id, user.id, VariationCreate(title="Elsewhere"))
        assert v_other.reference == "V-001"
    finally:
        _cleanup_tenant(tenant.id)


def test_variation_totals_reuse_the_general_quote_vat_rounding_convention(client, db):
    tenant = _make_tenant(db, "VariationVatTenant")
    headers, user = _make_owner_headers(client, db, tenant, "var-vat")
    try:
        project = _make_project(db, tenant)
        variation = variation_service.create(
            db, project.id, tenant.id, user.id,
            VariationCreate(
                title="Extra sockets",
                vat_rate=0.20,
                items=[
                    VariationItemIn(description="Sockets", quantity=4, unit="item", unit_price=45.50),
                    VariationItemIn(description="Cabling", quantity=1, unit="item", unit_price=120.0),
                ],
            ),
        )
        # 4 x 45.50 = 182.00, + 120.00 = 302.00 subtotal; VAT 20% = 60.40; total 362.40.
        assert variation.subtotal == 302.0
        assert variation.vat == 60.4
        assert variation.total == 362.4
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Task 8 — approval idempotency (the critical regression)
# ---------------------------------------------------------------------------


def test_approving_a_variation_twice_increases_the_contract_exactly_once(client, db):
    tenant = _make_tenant(db, "ApprovalIdempotencyTenant")
    headers, user = _make_owner_headers(client, db, tenant, "approval-idempotency")
    try:
        project = _make_project_with_approved_quote(client, headers, db, tenant)
        variation = variation_service.create(
            db, project.id, tenant.id, user.id,
            VariationCreate(title="Extra works", vat_rate=0, items=[VariationItemIn(description="Extra", quantity=1, unit_price=3250.0)]),
        )

        first = variation_service.approve(db, variation.id, tenant.id, user.id)
        summary_after_first = financials_service.get_summary(db, project.id, tenant.id)

        # Retry — same approval request, simulating a client retry/double-click.
        second = variation_service.approve(db, variation.id, tenant.id, user.id)
        summary_after_second = financials_service.get_summary(db, project.id, tenant.id)

        assert first.status == "approved"
        assert second.status == "approved"
        assert first.approved_at == second.approved_at
        assert summary_after_first.contract.current_contract_value == summary_after_second.contract.current_contract_value
        assert summary_after_second.contract.approved_variations_total == 3250.0

        # Approving it a third time via the HTTP route too — still idempotent.
        resp = client.post(f"/api/v1/variations/{variation.id}/approve", headers=headers)
        assert resp.status_code == 200
        summary_after_third = financials_service.get_summary(db, project.id, tenant.id)
        assert summary_after_third.contract.approved_variations_total == 3250.0
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Task 9/10 — base contract + current contract, end to end
# ---------------------------------------------------------------------------


def test_current_contract_reflects_only_approved_variations(client, db):
    tenant = _make_tenant(db, "ContractValueTenant")
    headers, user = _make_owner_headers(client, db, tenant, "contract-value")
    try:
        project = _make_project_with_approved_quote(client, headers, db, tenant)
        summary = financials_service.get_summary(db, project.id, tenant.id)
        assert summary.contract.base_contract_value == 24000.0
        assert summary.contract.base_contract_source == "approved_quote"
        assert summary.contract.current_contract_value == 24000.0

        draft = variation_service.create(db, project.id, tenant.id, user.id, VariationCreate(title="Draft only", vat_rate=0, items=[VariationItemIn(description="x", quantity=1, unit_price=1000.0)]))
        sent = variation_service.create(db, project.id, tenant.id, user.id, VariationCreate(title="Sent only", vat_rate=0, items=[VariationItemIn(description="x", quantity=1, unit_price=2000.0)]))
        variation_service.send(db, sent.id, tenant.id)
        rejected = variation_service.create(db, project.id, tenant.id, user.id, VariationCreate(title="Rejected", vat_rate=0, items=[VariationItemIn(description="x", quantity=1, unit_price=5000.0)]))
        variation_service.reject(db, rejected.id, tenant.id)
        approved = variation_service.create(db, project.id, tenant.id, user.id, VariationCreate(title="Approved", vat_rate=0, items=[VariationItemIn(description="x", quantity=1, unit_price=3250.0)]))
        variation_service.approve(db, approved.id, tenant.id, user.id)

        summary = financials_service.get_summary(db, project.id, tenant.id)
        # Only the approved variation's 3250 counts — draft/sent/rejected do not.
        assert summary.contract.approved_variations_total == 3250.0
        assert summary.contract.current_contract_value == 27250.0
    finally:
        _cleanup_tenant(tenant.id)


def test_base_contract_is_unset_for_a_project_with_no_linked_quote(db):
    tenant = _make_tenant(db, "NoQuoteContractTenant")
    try:
        project = _make_project(db, tenant)
        summary = financials_service.get_summary(db, project.id, tenant.id)
        assert summary.contract.base_contract_value is None
        assert summary.contract.current_contract_value is None
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Task 24 — approved variations are locked
# ---------------------------------------------------------------------------


def test_an_approved_variation_cannot_be_edited(client, db):
    tenant = _make_tenant(db, "VariationLockTenant")
    headers, user = _make_owner_headers(client, db, tenant, "var-lock")
    try:
        project = _make_project(db, tenant)
        variation = variation_service.create(db, project.id, tenant.id, user.id, VariationCreate(title="Locked"))
        variation_service.approve(db, variation.id, tenant.id, user.id)

        with pytest.raises(VariationEditStateError):
            variation_service.update(db, variation.id, tenant.id, VariationUpdate(title="Rewritten"))

        resp = client.patch(f"/api/v1/variations/{variation.id}", json={"title": "Rewritten"}, headers=headers)
        assert resp.status_code == 409
    finally:
        _cleanup_tenant(tenant.id)


def test_an_approved_variation_cannot_be_rejected_or_voided(db):
    tenant = _make_tenant(db, "VariationTerminalTenant")
    try:
        project = _make_project(db, tenant)
        # No user id needed for a direct service call with created_by None.
        variation = crud.create_variation(
            db, tenant_id=tenant.id, project_id=project.id, reference="V-001", title="x",
            status="approved", vat_rate=0.2, subtotal=0, vat=0, total=0,
        )
        with pytest.raises(VariationTransitionError):
            variation_service.reject(db, variation.id, tenant.id)
        with pytest.raises(VariationTransitionError):
            variation_service.void(db, variation.id, tenant.id)
    finally:
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Task 22 — tenant isolation for variations
# ---------------------------------------------------------------------------


def test_tenant_b_cannot_read_or_approve_tenant_as_variation(client, db):
    tenant_a = _make_tenant(db, "VarIsoA")
    tenant_b = _make_tenant(db, "VarIsoB")
    headers_a, user_a = _make_owner_headers(client, db, tenant_a, "var-iso-a")
    headers_b, _ = _make_owner_headers(client, db, tenant_b, "var-iso-b")
    try:
        project = _make_project(db, tenant_a)
        variation = variation_service.create(db, project.id, tenant_a.id, user_a.id, VariationCreate(title="Tenant A's"))

        resp = client.get(f"/api/v1/variations/{variation.id}", headers=headers_b)
        assert resp.status_code == 404

        resp = client.post(f"/api/v1/variations/{variation.id}/approve", headers=headers_b)
        assert resp.status_code == 404

        resp = client.get(f"/api/v1/projects/{project.id}/variations", headers=headers_b)
        assert resp.status_code == 404

        # Never actually approved by Tenant B's attempt.
        fresh = crud.get_variation_by_id(db, variation.id, tenant_a.id)
        assert fresh.status == "draft"
    finally:
        _cleanup_tenant(tenant_a.id)
        _cleanup_tenant(tenant_b.id)


# ---------------------------------------------------------------------------
# Task 25 — construction/general quoting is untouched
# ---------------------------------------------------------------------------


def test_general_quoting_is_unaffected_by_the_financials_and_variations_modules(client, db):
    tenant = _make_tenant(db, "GeneralQuoteRegressionTenant")
    headers, _ = _make_owner_headers(client, db, tenant, "general-regression")
    try:
        resp = client.post(
            "/api/v1/quotes",
            json={
                "title": "Bathroom refit",
                "vat_rate": 0.20,
                "lines": [{"line_kind": "labour", "description": "Strip out", "quantity": 2, "unit": "day", "unit_price": 320.0}],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["quote_kind"] == "general"
        assert body["total"] == 768.0  # 640 + 20% VAT
    finally:
        _cleanup_tenant(tenant.id)
