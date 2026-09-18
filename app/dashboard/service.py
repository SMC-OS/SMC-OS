import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.dashboard.models import (
    CommandCentreResponse,
    FinancialSignals,
    FollowUpAttention,
    PipelineCounts,
    PipelineRoleCounts,
    ProcurementSignals,
    QuoteFunnel,
    QuotedValue,
    SiteVisitCounts,
)
from app.database import crud
from app.financials.service import financials_service
from app.projects.models import ProjectStatus
from app.appointments.models import AppointmentStatus
from app.workflows.gates import evaluate_stage_gates
from app.workflows.models import WorkflowRole


def _build_financial_signals(db: Session, tenant_id: uuid.UUID) -> FinancialSignals:
    """GeoCore Premium OS Plan 04 (Sprint 043), Task 20 — bounded per-
    project loop, not a single SQL aggregate (see
    crud.list_projects_with_a_base_contract's own docstring for why).
    Scoped to projects with a real base contract only — an enquiry with
    no quote yet has nothing meaningful to report."""
    projects = crud.list_projects_with_a_base_contract(db, tenant_id)
    approved_contract_value = 0.0
    margin_risk_count = 0
    missing_cost_data_count = 0
    for project in projects:
        summary = financials_service.get_summary(db, project.id, tenant_id)
        if summary.contract.current_contract_value is not None:
            approved_contract_value += summary.contract.current_contract_value
        if summary.profitability.margin_risk:
            margin_risk_count += 1
        if summary.costs.cost_data_status == "none":
            missing_cost_data_count += 1

    return FinancialSignals(
        approved_contract_value=round(approved_contract_value, 2),
        approved_variations_value=crud.sum_approved_variations_total_for_tenant(db, tenant_id),
        projects_with_margin_risk=margin_risk_count,
        projects_with_missing_cost_data=missing_cost_data_count,
        projects_with_a_contract=len(projects),
    )


def _build_procurement_signals(db: Session, tenant_id: uuid.UUID) -> ProcurementSignals:
    """GeoCore Premium OS Plan 05 (Sprint 044), Task 25 — every count
    except `projects_blocked_by_materials` is a single grouped/filtered
    SQL aggregate (O(1) queries, same convention as every other Command
    Centre figure). The blocked-projects count is a deliberate, documented
    exception — same bounded per-project-loop pattern
    `_build_financial_signals` already uses for margin risk — because
    confirming a project is genuinely gate-blocked needs a real
    evaluate_stage_gates() call against its current stage, not just "has
    an outstanding requirement"."""
    today = date.today()
    week_ahead = today + timedelta(days=7)

    po_counts = crud.count_purchase_orders_by_status(db, tenant_id)

    blocked_count = 0
    for project in crud.list_projects_with_blocking_material_requirements(db, tenant_id):
        if project.workflow_stage_ref is None:
            continue
        blockers = evaluate_stage_gates(db, project, tenant_id, project.workflow_stage_ref)
        if any(b.code == "materials_ready" for b in blockers):
            blocked_count += 1

    return ProcurementSignals(
        materials_required=crud.count_material_requirements_outstanding(db, tenant_id),
        purchase_orders_awaiting_approval=po_counts.get("draft", 0),
        purchase_orders_ordered=po_counts.get("ordered", 0) + po_counts.get("partially_received", 0),
        late_deliveries=crud.count_late_purchase_orders(db, tenant_id, today),
        materials_due_this_week=crud.count_purchase_orders_due_this_week(db, tenant_id, today, week_ahead),
        projects_blocked_by_materials=blocked_count,
    )


def build_command_centre(db: Session, tenant_id: uuid.UUID) -> CommandCentreResponse:
    """Six aggregate SQL queries total (docs/SPRINTS/sprint-025.md §3) —
    every count/sum below is one grouped or scalar query, never a per-row
    Python loop, so this stays O(1) queries regardless of how many
    Projects/Quotes/Appointments the tenant has. `financials` below is
    the one deliberate exception — see its own docstring."""
    project_counts = crud.count_projects_by_status(db, tenant_id)
    project_role_counts = crud.count_projects_by_role(db, tenant_id)
    quote_counts = crud.count_quotes_by_status(db, tenant_id)
    appointment_counts = crud.count_appointments_by_status(db, tenant_id)

    return CommandCentreResponse(
        customers=crud.count_customers(db, tenant_id),
        pipeline=PipelineCounts(
            **{status.value: project_counts.get(status.value, 0) for status in ProjectStatus}
        ),
        pipeline_by_role=PipelineRoleCounts(
            **{role.value: project_role_counts.get(role.value, 0) for role in WorkflowRole}
        ),
        quotes=QuoteFunnel(
            draft=quote_counts.get("draft", 0),
            approved=quote_counts.get("approved", 0),
            handed_off=crud.count_handed_off_projects(db, tenant_id),
        ),
        value=QuotedValue(
            quoted_value=crud.sum_quotes_revenue(db, tenant_id),
            approved_quoted_value=crud.sum_approved_quotes_value(db, tenant_id),
        ),
        site_visits=SiteVisitCounts(
            **{
                status.value: appointment_counts.get(status.value, 0)
                for status in AppointmentStatus
            }
        ),
        follow_up=FollowUpAttention(
            unread_follow_ups=crud.count_unread_follow_up_notifications(db, tenant_id)
        ),
        financials=_build_financial_signals(db, tenant_id),
        procurement=_build_procurement_signals(db, tenant_id),
    )
