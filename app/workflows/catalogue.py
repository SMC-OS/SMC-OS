"""GeoCore's system (GeoCore-provided, immutable) workflow template
library — GeoCore Premium OS Plan 01, Task 2.

Every trade in `app.trades.catalogue.TRADES` gets a workflow here whose
stage vocabulary matches how that trade actually runs a job (a stone job
has "Template"/"Fabrication"; an electrical job has "First Fix"/"Second
Fix"/"Certification") while every stage still maps to one of the 13
stable `WorkflowRole`s so cross-trade reporting stays possible.

This module is data, not a place for business logic: nothing here reads
a project or makes a decision. `template_for_trade()` is the only lookup
function, and its fallback (unknown/absent/"other" trade -> "general_v1")
is deliberately the same safe default `default_quote_kind()` already uses
for the quote side of this vocabulary.
"""

from app.workflows.models import SystemWorkflowStage, SystemWorkflowTemplate, WorkflowRole


def _slug(label: str) -> str:
    """Stable machine key from a display label — lowercase, non-alphanumerics
    collapsed to a single underscore. Business logic must never derive
    behaviour from the *label* (which is freely rewordable); this exists
    only to avoid hand-typing a parallel key for every stage below."""
    out = []
    prev_underscore = False
    for ch in label.lower():
        if ch.isalnum():
            out.append(ch)
            prev_underscore = False
        elif not prev_underscore:
            out.append("_")
            prev_underscore = True
    return "".join(out).strip("_")


def _build(trade_key: str, name: str, stages: list[tuple[str, WorkflowRole]]) -> SystemWorkflowTemplate:
    built = tuple(
        SystemWorkflowStage(
            key=_slug(label),
            label=label,
            role=role,
            position=position,
            terminal=(position == len(stages) - 1),
        )
        for position, (label, role) in enumerate(stages)
    )
    key = "general_v1" if trade_key == "other" else f"{trade_key}_v1"
    return SystemWorkflowTemplate(key=key, name=name, trade_key=trade_key, stages=built)


_R = WorkflowRole

# Each entry: trade_key -> (display name, [(stage label, role), ...]).
# Every sequence starts "Enquiry" (LEAD) and ends "Complete" (COMPLETED) —
# enforced by tests/test_workflows.py, not just convention here.
_SPEC: dict[str, tuple[str, list[tuple[str, WorkflowRole]]]] = {
    "stone": (
        "Stone & Worktops",
        [
            ("Enquiry", _R.LEAD),
            ("Measure / Site Visit", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Deposit", _R.PROCUREMENT),
            ("Material Ordered / Reserved", _R.PROCUREMENT),
            ("Template", _R.IN_PROGRESS),
            ("Fabrication", _R.IN_PROGRESS),
            ("QC", _R.INSPECTION),
            ("Installation", _R.IN_PROGRESS),
            ("Snagging", _R.SNAGGING),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "general_building": (
        "General Building",
        [
            ("Enquiry", _R.LEAD),
            ("Site Visit", _R.SURVEY),
            ("Estimate / Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Deposit", _R.PROCUREMENT),
            ("Pre-Start", _R.SCHEDULED),
            ("In Progress", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Snagging", _R.SNAGGING),
            ("Handover", _R.HANDOVER),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "renovation": (
        "Renovation",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Scope", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Procurement", _R.PROCUREMENT),
            ("Strip-Out", _R.IN_PROGRESS),
            ("Main Works", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Snagging", _R.SNAGGING),
            ("Handover", _R.HANDOVER),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "extension": (
        "Extensions",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Pre-Construction", _R.SCHEDULED),
            ("Groundworks", _R.IN_PROGRESS),
            ("Structure", _R.IN_PROGRESS),
            ("First Fix", _R.IN_PROGRESS),
            ("Second Fix", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Snagging", _R.SNAGGING),
            ("Handover", _R.HANDOVER),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "electrical": (
        "Electrical",
        [
            ("Enquiry", _R.LEAD),
            ("Site Assessment", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Scheduled", _R.SCHEDULED),
            ("First Fix", _R.IN_PROGRESS),
            ("Second Fix", _R.IN_PROGRESS),
            ("Testing", _R.INSPECTION),
            ("Certification", _R.INSPECTION),
            ("Snagging", _R.SNAGGING),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "plumbing": (
        "Plumbing",
        [
            ("Enquiry", _R.LEAD),
            ("Site Assessment", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Materials", _R.PROCUREMENT),
            ("First Fix", _R.IN_PROGRESS),
            ("Second Fix", _R.IN_PROGRESS),
            ("Pressure / Test Check", _R.INSPECTION),
            ("Commissioning", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "heating_hvac": (
        "Heating / HVAC",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Equipment Ordered", _R.PROCUREMENT),
            ("Installation", _R.IN_PROGRESS),
            ("Testing", _R.INSPECTION),
            ("Commissioning", _R.INSPECTION),
            ("Certification", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "carpentry": (
        "Carpentry & Joinery",
        [
            ("Enquiry", _R.LEAD),
            ("Measure", _R.SURVEY),
            ("Design / Specification", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Materials", _R.PROCUREMENT),
            ("Workshop / Fabrication", _R.IN_PROGRESS),
            ("Installation", _R.IN_PROGRESS),
            ("Finishing", _R.IN_PROGRESS),
            ("QC", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "kitchen": (
        "Kitchens",
        [
            ("Enquiry", _R.LEAD),
            ("Measure", _R.SURVEY),
            ("Design", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Procurement", _R.PROCUREMENT),
            ("Strip-Out", _R.IN_PROGRESS),
            ("First Fix", _R.IN_PROGRESS),
            ("Units / Fitting", _R.IN_PROGRESS),
            ("Worktops", _R.IN_PROGRESS),
            ("Second Fix", _R.IN_PROGRESS),
            ("Snagging", _R.SNAGGING),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "bathroom": (
        "Bathrooms",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Procurement", _R.PROCUREMENT),
            ("Strip-Out", _R.IN_PROGRESS),
            ("Plumbing First Fix", _R.IN_PROGRESS),
            ("Waterproofing", _R.IN_PROGRESS),
            ("Tiling / Fitting", _R.IN_PROGRESS),
            ("Second Fix", _R.IN_PROGRESS),
            ("Testing", _R.INSPECTION),
            ("Snagging", _R.SNAGGING),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "roofing": (
        "Roofing",
        [
            ("Enquiry", _R.LEAD),
            ("Roof Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Materials", _R.PROCUREMENT),
            ("Scaffolding / Access", _R.SCHEDULED),
            ("Strip-Off", _R.IN_PROGRESS),
            ("Installation", _R.IN_PROGRESS),
            ("Weatherproofing", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "flooring": (
        "Flooring",
        [
            ("Enquiry", _R.LEAD),
            ("Measure", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Material Ordered", _R.PROCUREMENT),
            ("Subfloor Preparation", _R.IN_PROGRESS),
            ("Installation", _R.IN_PROGRESS),
            ("Finishing", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "tiling": (
        "Tiling",
        [
            ("Enquiry", _R.LEAD),
            ("Measure", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Materials", _R.PROCUREMENT),
            ("Preparation / Waterproofing", _R.IN_PROGRESS),
            ("Tiling", _R.IN_PROGRESS),
            ("Grouting / Finishing", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "decorating": (
        "Painting & Decorating",
        [
            ("Enquiry", _R.LEAD),
            ("Site Visit", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Colour / Specification", _R.PROCUREMENT),
            ("Preparation", _R.IN_PROGRESS),
            ("Painting / Decoration", _R.IN_PROGRESS),
            ("Touch-Ups", _R.SNAGGING),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "plastering_rendering": (
        "Plastering & Rendering",
        [
            ("Enquiry", _R.LEAD),
            ("Site Visit", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Preparation", _R.IN_PROGRESS),
            ("Base Coat", _R.IN_PROGRESS),
            ("Finish Coat", _R.IN_PROGRESS),
            ("Dry / Cure", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "brickwork_masonry": (
        "Brickwork & Masonry",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Materials", _R.PROCUREMENT),
            ("Setting Out", _R.IN_PROGRESS),
            ("Construction", _R.IN_PROGRESS),
            ("Pointing / Finishing", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "groundworks": (
        "Groundworks",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Permits / Pre-Start", _R.SCHEDULED),
            ("Excavation", _R.IN_PROGRESS),
            ("Drainage / Sub-Base", _R.IN_PROGRESS),
            ("Concrete / Foundations", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "drainage": (
        "Drainage",
        [
            ("Enquiry", _R.LEAD),
            ("Investigation", _R.SURVEY),
            ("Survey / CCTV", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Excavation / Access", _R.IN_PROGRESS),
            ("Repair / Installation", _R.IN_PROGRESS),
            ("Testing", _R.INSPECTION),
            ("Reinstatement", _R.IN_PROGRESS),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "windows_doors": (
        "Windows & Doors",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Manufacture / Order", _R.PROCUREMENT),
            ("Delivery", _R.PROCUREMENT),
            ("Installation", _R.IN_PROGRESS),
            ("Adjustment", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Handover", _R.HANDOVER),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "glazing": (
        "Glazing",
        [
            ("Enquiry", _R.LEAD),
            ("Measure", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Glass Ordered", _R.PROCUREMENT),
            ("Delivery", _R.PROCUREMENT),
            ("Installation", _R.IN_PROGRESS),
            ("Sealing", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "landscaping": (
        "Landscaping",
        [
            ("Enquiry", _R.LEAD),
            ("Site Survey", _R.SURVEY),
            ("Design / Scope", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Procurement", _R.PROCUREMENT),
            ("Ground Preparation", _R.IN_PROGRESS),
            ("Hard Landscaping", _R.IN_PROGRESS),
            ("Soft Landscaping", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Handover", _R.HANDOVER),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "fencing": (
        "Fencing",
        [
            ("Enquiry", _R.LEAD),
            ("Measure", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Materials", _R.PROCUREMENT),
            ("Ground Preparation", _R.IN_PROGRESS),
            ("Installation", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "demolition_stripout": (
        "Demolition / Strip-Out",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Safety / Pre-Start", _R.SCHEDULED),
            ("Isolation", _R.IN_PROGRESS),
            ("Strip-Out / Demolition", _R.IN_PROGRESS),
            ("Waste Removal", _R.IN_PROGRESS),
            ("Site Clearance", _R.IN_PROGRESS),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "insulation": (
        "Insulation",
        [
            ("Enquiry", _R.LEAD),
            ("Survey", _R.SURVEY),
            ("Specification", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Materials", _R.PROCUREMENT),
            ("Preparation", _R.IN_PROGRESS),
            ("Installation", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Certification / Record", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "steelwork": (
        "Structural Steelwork",
        [
            ("Enquiry", _R.LEAD),
            ("Survey / Drawings", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Engineering / Approval", _R.SCHEDULED),
            ("Fabrication", _R.IN_PROGRESS),
            ("Delivery", _R.PROCUREMENT),
            ("Installation", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "scaffolding": (
        "Scaffolding",
        [
            ("Enquiry", _R.LEAD),
            ("Site Survey", _R.SURVEY),
            ("Design / Load Requirement", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Permit / Pre-Start", _R.SCHEDULED),
            ("Erection", _R.IN_PROGRESS),
            ("Inspection / Handover", _R.HANDOVER),
            ("In Use", _R.IN_PROGRESS),
            ("Dismantle", _R.IN_PROGRESS),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "solar_renewables": (
        "Solar & Renewables",
        [
            ("Enquiry", _R.LEAD),
            ("Site Survey", _R.SURVEY),
            ("Design / Yield Assessment", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Permissions / Grid", _R.SCHEDULED),
            ("Equipment Ordered", _R.PROCUREMENT),
            ("Installation", _R.IN_PROGRESS),
            ("Electrical Connection", _R.IN_PROGRESS),
            ("Testing / Commissioning", _R.INSPECTION),
            ("Certification", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
    "other": (
        "General / Custom Trade",
        [
            ("Enquiry", _R.LEAD),
            ("Site Visit", _R.SURVEY),
            ("Quote", _R.QUOTED),
            ("Approved", _R.APPROVED),
            ("Scheduled", _R.SCHEDULED),
            ("In Progress", _R.IN_PROGRESS),
            ("Inspection", _R.INSPECTION),
            ("Complete", _R.COMPLETED),
        ],
    ),
}

SYSTEM_WORKFLOWS: dict[str, SystemWorkflowTemplate] = {
    (
        "general_v1" if trade_key == "other" else f"{trade_key}_v1"
    ): _build(trade_key, name, stages)
    for trade_key, (name, stages) in _SPEC.items()
}

_GENERAL_TEMPLATE = SYSTEM_WORKFLOWS["general_v1"]


def template_for_trade(trade_key: str | None) -> SystemWorkflowTemplate:
    """The system workflow for a trade key. An unknown or absent trade
    (never assumed to be stone) gets the same safe general fallback as
    the "other" trade itself — mirrors
    `app.trades.catalogue.default_quote_kind`'s "the general case is the
    default" convention."""
    if trade_key is None:
        return _GENERAL_TEMPLATE
    key = "general_v1" if trade_key == "other" else f"{trade_key}_v1"
    return SYSTEM_WORKFLOWS.get(key, _GENERAL_TEMPLATE)
