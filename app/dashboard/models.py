from pydantic import BaseModel


class PipelineCounts(BaseModel):
    """Count of the caller's tenant's Projects currently in each pipeline
    status (app.projects.models.ProjectStatus). All 7 keys always present,
    0 if none — never a sparse/partial dict (docs/SPRINTS/sprint-025.md §3)."""

    enquiry: int
    quoted: int
    booked: int
    templated: int
    fabricated: int
    installed: int
    complete: int


class PipelineRoleCounts(BaseModel):
    """GeoCore Premium OS Plan 01 (Sprint 040, Task 7) — the semantic,
    trade-adaptive sibling of PipelineCounts above: one field per
    WorkflowRole (app.workflows.models.WorkflowRole), always all 13
    present and 0 if none, same never-sparse contract. A stone project on
    "Fabrication" and an electrical project on "First Fix" both count
    under `in_progress` here, which is what lets the Command Centre show
    one company-wide pipeline across every trade instead of 27 trade-
    shaped ones. `pipeline` on CommandCentreResponse stays exactly as
    it was — this is an addition, not a replacement, during the Project
    360 / Command Centre UI rollout (Tasks 8-9)."""

    lead: int
    survey: int
    quoted: int
    approved: int
    procurement: int
    scheduled: int
    in_progress: int
    inspection: int
    snagging: int
    handover: int
    completed: int
    on_hold: int
    cancelled: int


class QuoteFunnel(BaseModel):
    """`handed_off` is independently queried from Project.quote_id, not
    derived from `approved` — never assume handed_off <= approved in the
    UI without re-reading docs/SPRINTS/sprint-025.md §3's exact semantics."""

    draft: int
    approved: int
    handed_off: int


class QuotedValue(BaseModel):
    """Neither field is "revenue" — a quote total is a price offered or
    committed to, not recognized income (docs/SPRINTS/sprint-025.md §1)."""

    quoted_value: float
    approved_quoted_value: float


class SiteVisitCounts(BaseModel):
    scheduled: int
    completed: int
    cancelled: int


class FollowUpAttention(BaseModel):
    """Tenant-wide unread count of project-sourced follow-up
    notifications — not scoped to the viewing user (docs/SPRINTS/
    sprint-025.md §3)."""

    unread_follow_ups: int


class FinancialSignals(BaseModel):
    """GeoCore Premium OS Plan 04 (Sprint 043), Task 20 — scoped to
    projects that have a real base contract (a linked, handed-off quote);
    an enquiry with no quote yet has nothing meaningful to report here.
    Never a company-wide margin percentage — Task 20 forbids showing a
    confident average when underlying cost data is incomplete for some
    projects, so only counts are exposed, never an aggregate margin."""

    approved_contract_value: float
    approved_variations_value: float
    projects_with_margin_risk: int
    projects_with_missing_cost_data: int
    projects_with_a_contract: int


class ProcurementSignals(BaseModel):
    """GeoCore Premium OS Plan 05 (Sprint 044), Task 25 — high-value
    operational procurement signals only, each backed by a real,
    explainable rule (never invented metric clutter). `projects_blocked_
    by_materials` counts a project only when it is genuinely gate-blocked
    right now (materials_ready unmet at its *current* stage), not merely
    "has an outstanding requirement somewhere"."""

    materials_required: int
    purchase_orders_awaiting_approval: int
    purchase_orders_ordered: int
    late_deliveries: int
    materials_due_this_week: int
    projects_blocked_by_materials: int


class CommandCentreResponse(BaseModel):
    customers: int
    pipeline: PipelineCounts
    pipeline_by_role: PipelineRoleCounts
    quotes: QuoteFunnel
    value: QuotedValue
    site_visits: SiteVisitCounts
    follow_up: FollowUpAttention
    financials: FinancialSignals
    procurement: ProcurementSignals
