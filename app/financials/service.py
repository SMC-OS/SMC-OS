"""GeoCore Premium OS Plan 04 (Sprint 043) — project financial summary.

The pure calculation functions (`resolve_base_contract`, `build_cost_
summary`, `build_contract_summary`, `build_profitability_summary`) take
no Session and are exhaustively unit-testable with plain values — the
same "pure function, DB access stays in the orchestrating call" shape
app/quotes/general.py's `price()` already established. Route-level
pattern for everything else (ADR-019): no repository interface.
"""

import uuid

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.automations.dispatcher import automation_dispatcher
from app.database import crud
from app.database.models import ProjectCostEntry
from app.financials.models import (
    ContractSummary,
    CostSummary,
    ProfitabilitySummary,
    ProjectCostEntryIn,
    ProjectCostEntryUpdate,
    ProjectFinancialSummary,
)

# Documented, conservative V1 default (Task 21 — "use a conservative
# internal default only if the Master Spec/architecture supports that").
# No per-tenant threshold setting exists yet; see ADR-048. Revisit once a
# real settings surface exists rather than silently inventing one now.
MARGIN_RISK_THRESHOLD_PERCENT = 15.0


class ProjectNotFoundError(Exception):
    """Raised when the target Project doesn't resolve under the caller's
    own tenant — same tenant-scoped-lookup-hides-existence convention as
    app/appointments/service.py (ADR-029)."""


def resolve_base_contract(project, quote) -> tuple[float | None, str | None]:
    """Task 9's hierarchy, V1: the only safe, non-fabricated source for a
    project's base contract value today is the approved quote it was
    handed off from — `Project.quote_id` is only ever set by
    QuoteService.handoff, which itself refuses any quote whose status is
    not "approved" (see app/quotes/service.py). `Project.estimated_value`
    is deliberately NOT used as a fallback: its own docstring in
    app/database/models.py states it "legitimately moves" and is
    "editable afterwards" — exactly the "rough estimate silently treated
    as a signed contract" Task 9 forbids. A project with no linked quote
    has an unset (`None`) base contract, not an invented zero.
    """
    if quote is not None and quote.total is not None:
        return quote.total, "approved_quote"
    return None, None


def build_cost_summary(cost_sums: dict[str, float], entry_count: int, workflow_role: str | None) -> CostSummary:
    """Forecast cost = SUM(budgeted) + SUM(committed) + SUM(actual).

    Safe from double-counting only because ProjectCostEntry models one
    cost item as a single row whose `state` is edited in place as it
    graduates from budgeted -> committed -> actual (see the model's own
    docstring) — there is no revision/supersession tracking, so this
    formula is deliberately the simple sum Task 3 permits rather than a
    fabricated attempt at overlap detection GeoCore cannot actually make
    (ADR-047).

    `cost_data_status` (Task 4) is never a claim about *completeness* of
    recorded costs — GeoCore has no way to know that. "complete" fires
    only on a real, independent signal: the project's own workflow has
    reached the `completed` role, so costs recorded by then are the
    presumed-final picture (ADR-048). Zero entries is always "none",
    regardless of workflow stage.
    """
    budgeted = cost_sums.get("budgeted", 0.0)
    committed = cost_sums.get("committed", 0.0)
    actual = cost_sums.get("actual", 0.0)
    forecast = round(budgeted + committed + actual, 2)

    if entry_count == 0:
        status = "none"
    elif workflow_role == "completed":
        status = "complete"
    else:
        status = "partial"

    return CostSummary(
        budgeted_cost=round(budgeted, 2),
        committed_cost=round(committed, 2),
        actual_cost=round(actual, 2),
        forecast_cost=forecast,
        cost_data_status=status,
        cost_entry_count=entry_count,
    )


def build_contract_summary(
    base_contract_value: float | None, base_contract_source: str | None, approved_variations_total: float
) -> ContractSummary:
    """Current Contract Value = Base Contract + SUM(approved variations),
    always *derived*, never maintained by incrementing a counter (Task
    8/10) — so re-deriving it after approving the same variation twice
    (or any retried request) can never double it. `None` when there is
    no base contract to add to, rather than treating the variations
    total alone as a contract value."""
    approved_variations_total = round(approved_variations_total, 2)
    current = (
        round(base_contract_value + approved_variations_total, 2)
        if base_contract_value is not None
        else None
    )
    return ContractSummary(
        base_contract_value=base_contract_value,
        base_contract_source=base_contract_source,
        approved_variations_total=approved_variations_total,
        current_contract_value=current,
    )


def build_profitability_summary(contract: ContractSummary, costs: CostSummary) -> ProfitabilitySummary:
    """Task 11's guards, applied literally: no contract, a zero/negative
    contract, or zero recorded cost entries all mean "cannot honestly
    compute a margin" — `None`, never a fabricated figure (Task 4's
    "23.7% margin off one small cost" warning applies here directly).
    Actual and forecast are computed independently and never conflated —
    an `actual_gross_margin_percent` reflects only `actual_cost`, even
    while budgeted/committed rows exist for the same project."""
    current = contract.current_contract_value
    has_cost_data = costs.cost_entry_count > 0
    can_compute = current is not None and current > 0 and has_cost_data

    forecast_profit = round(current - costs.forecast_cost, 2) if can_compute else None
    forecast_margin = round(forecast_profit / current * 100, 2) if can_compute else None
    actual_profit = round(current - costs.actual_cost, 2) if can_compute else None
    actual_margin = round(actual_profit / current * 100, 2) if can_compute else None

    margin_risk = forecast_margin is not None and forecast_margin < MARGIN_RISK_THRESHOLD_PERCENT

    return ProfitabilitySummary(
        forecast_gross_profit=forecast_profit,
        forecast_gross_margin_percent=forecast_margin,
        actual_gross_profit=actual_profit,
        actual_gross_margin_percent=actual_margin,
        margin_risk=margin_risk,
    )


class FinancialsService:
    def get_summary(
        self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> ProjectFinancialSummary:
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        quote = (
            crud.get_quote_by_id(db, project.quote_id, tenant_id)
            if project.quote_id is not None
            else None
        )
        base_contract_value, base_contract_source = resolve_base_contract(project, quote)
        approved_variations_total = crud.sum_approved_variations_total(db, project_id, tenant_id)
        contract = build_contract_summary(
            base_contract_value, base_contract_source, approved_variations_total
        )

        cost_sums = crud.sum_cost_by_state(db, project_id, tenant_id)
        entry_count = crud.count_project_cost_entries(db, project_id, tenant_id)
        workflow_role = project.workflow_stage_ref.role if project.workflow_stage_ref else None
        costs = build_cost_summary(cost_sums, entry_count, workflow_role)

        profitability = build_profitability_summary(contract, costs)

        return ProjectFinancialSummary(
            project_id=project_id, contract=contract, costs=costs, profitability=profitability
        )

    def list_cost_entries(
        self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> list[ProjectCostEntry]:
        if crud.get_project_by_id(db, project_id, tenant_id) is None:
            raise ProjectNotFoundError(project_id)
        return crud.list_project_cost_entries(db, project_id, tenant_id)

    def create_cost_entry(
        self,
        db: Session,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        data: ProjectCostEntryIn,
    ) -> ProjectCostEntry:
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        entry = crud.create_project_cost_entry(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            created_by_user_id=actor_user_id,
            **data.model_dump(),
        )

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PROJECT_COST_ADDED,
                title="Cost recorded",
                description=f"{project.name} — {entry.description} (£{entry.total_cost:,.2f})",
            ),
            tenant_id=tenant_id,
        )
        automation_dispatcher.dispatch_cost_added(db, entry, project)
        self._check_margin_risk(db, project, tenant_id)
        return entry

    def update_cost_entry(
        self,
        db: Session,
        project_id: uuid.UUID,
        cost_entry_id: uuid.UUID,
        tenant_id: uuid.UUID,
        data: ProjectCostEntryUpdate,
    ) -> ProjectCostEntry:
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        entry = crud.get_project_cost_entry_by_id(db, cost_entry_id, project_id, tenant_id)
        if entry is None:
            raise CostEntryNotFoundError(cost_entry_id)

        changes = data.model_dump(exclude_unset=True)
        entry = crud.update_project_cost_entry(db, entry, changes)

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PROJECT_COST_EDITED,
                title="Cost edited",
                description=f"{project.name} — {entry.description} (£{entry.total_cost:,.2f})",
            ),
            tenant_id=tenant_id,
        )
        self._check_margin_risk(db, project, tenant_id)
        return entry

    def delete_cost_entry(
        self, db: Session, project_id: uuid.UUID, cost_entry_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> None:
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        entry = crud.get_project_cost_entry_by_id(db, cost_entry_id, project_id, tenant_id)
        if entry is None:
            raise CostEntryNotFoundError(cost_entry_id)

        description = entry.description
        total_cost = entry.total_cost
        crud.delete_project_cost_entry(db, entry)

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PROJECT_COST_DELETED,
                title="Cost deleted",
                description=f"{project.name} — {description} (£{total_cost:,.2f})",
            ),
            tenant_id=tenant_id,
        )

    def _check_margin_risk(self, db: Session, project, tenant_id: uuid.UUID) -> None:
        """Task 18 — commercial truth commits first (the cost write above
        is already committed by the time this runs); automation dispatch
        here can never roll it back. Total by construction: any failure
        inside get_summary or the dispatch itself must not surface as an
        error on the cost-write request that triggered it."""
        try:
            summary = self.get_summary(db, project.id, tenant_id)
            if summary.profitability.margin_risk:
                automation_dispatcher.dispatch_margin_risk_detected(
                    db,
                    project,
                    forecast_margin_percent=summary.profitability.forecast_gross_margin_percent,
                    current_contract_value=summary.contract.current_contract_value,
                )
        except Exception:  # noqa: BLE001
            pass


class CostEntryNotFoundError(Exception):
    """Raised when the target cost entry doesn't resolve under the
    caller's own tenant/project — same tenant-scoped-lookup-hides-
    existence convention as ProjectNotFoundError above."""


financials_service = FinancialsService()
