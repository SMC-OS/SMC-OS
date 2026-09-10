from pydantic import BaseModel


class PipelineCounts(BaseModel):
    """Count of the caller's tenant's Projects at each pipeline *role*.

    Sprint 039 (Workstream D, §4 Decision 3) re-keyed this from the seven
    stone-named stages to the eight trade-neutral roles
    (app/projects/pipeline.py). That is what makes the dashboard read
    correctly for a roofing business and a worktop fabricator at the same
    time: a stone tenant's `templated`, `fabricated` and `installed` jobs
    all count as `in_progress`, without a single project row changing.

    All 8 keys always present, 0 if none — never a sparse/partial dict
    (docs/SPRINTS/sprint-025.md §3)."""

    lead: int
    quoted: int
    approved: int
    scheduled: int
    in_progress: int
    on_hold: int
    completed: int
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


class CommandCentreResponse(BaseModel):
    customers: int
    pipeline: PipelineCounts
    quotes: QuoteFunnel
    value: QuotedValue
    site_visits: SiteVisitCounts
    follow_up: FollowUpAttention
