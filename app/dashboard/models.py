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
