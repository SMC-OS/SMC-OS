"""The events a GeoCore automation can react to (Sprint 036, Workstream G).

Two families, distinguished by how they are evaluated rather than by what
they mean:

  * EVENT triggers fire from the service layer, synchronously, immediately
    after the change that caused them has committed. They are exact —
    "this quote was just approved" — and cannot be missed or repeated.

  * SCAN triggers describe a *state over time* ("this quote expires in
    three days") that no single event corresponds to. They are evaluated
    by app/jobs/automations.py, the same shape as the Sprint 024 follow-up
    job: an explicit `now`, no I/O beyond the session, idempotent through
    a dedupe key so running the job twice in one day creates one task.

Keys are persisted in automations.trigger_type and must stay stable once
shipped. Labels and descriptions are display text.

Nothing here reaches a customer. Every action an automation can take is
internal to the workspace — see app/automations/actions.py.
"""

from dataclasses import dataclass

EVENT = "event"
SCAN = "scan"


@dataclass(frozen=True)
class Trigger:
    key: str
    label: str
    description: str
    kind: str
    # Which entity the automation's conditions are evaluated against, and
    # what a run's subject_id points at.
    subject_type: str


TRIGGERS: tuple[Trigger, ...] = (
    Trigger(
        "customer.created",
        "Customer created",
        "Runs when a new customer is added to the workspace.",
        EVENT,
        "customer",
    ),
    Trigger(
        "quote.created",
        "Quote created",
        "Runs when a new quote is created.",
        EVENT,
        "quote",
    ),
    Trigger(
        "quote.sent",
        "Quote marked as sent",
        "Runs when a quote is marked as sent to the customer.",
        EVENT,
        "quote",
    ),
    Trigger(
        "quote.approved",
        "Quote approved",
        "Runs when a quote is approved.",
        EVENT,
        "quote",
    ),
    Trigger(
        "quote.expiring",
        "Quote approaching expiry",
        "Runs when a sent quote's validity date is approaching and it has "
        "not been approved.",
        SCAN,
        "quote",
    ),
    Trigger(
        "project.created",
        "Project created",
        "Runs when a new project is created.",
        EVENT,
        "project",
    ),
    Trigger(
        "project.status_changed",
        "Project status changed",
        "Runs when a project moves to a new stage.",
        EVENT,
        "project",
    ),
    Trigger(
        "project.starting",
        "Project approaching start date",
        "Runs when a project's start date is approaching.",
        SCAN,
        "project",
    ),
    Trigger(
        "project.completed",
        "Project completed",
        "Runs when a project reaches the completed stage.",
        EVENT,
        "project",
    ),
    # GeoCore Premium OS Plan 04 (Sprint 043) — job financials + variations.
    Trigger(
        "variation.created",
        "Variation created",
        "Runs when a new project variation is created.",
        EVENT,
        "variation",
    ),
    Trigger(
        "variation.sent",
        "Variation sent",
        "Runs when a variation is marked as sent to the customer.",
        EVENT,
        "variation",
    ),
    Trigger(
        "variation.approved",
        "Variation approved",
        "Runs when a variation is approved and its value joins the "
        "project's current contract.",
        EVENT,
        "variation",
    ),
    Trigger(
        "variation.rejected",
        "Variation rejected",
        "Runs when a variation is rejected.",
        EVENT,
        "variation",
    ),
    Trigger(
        "cost.added",
        "Project cost recorded",
        "Runs when a cost is recorded against a project.",
        EVENT,
        "cost_entry",
    ),
    Trigger(
        "margin_risk.detected",
        "Margin risk detected",
        "Runs when a project's forecast margin falls below GeoCore's "
        "margin-risk threshold after a cost is recorded.",
        EVENT,
        "project",
    ),
    # GeoCore Premium OS Plan 05 (Sprint 044) — procurement + materials operations.
    Trigger(
        "material_requirement.created",
        "Material requirement created",
        "Runs when a new material requirement is added to a project.",
        EVENT,
        "material_requirement",
    ),
    Trigger(
        "purchase_order.approved",
        "Purchase order approved",
        "Runs when a purchase order is approved and its committed cost "
        "joins the project's financials.",
        EVENT,
        "purchase_order",
    ),
    Trigger(
        "purchase_order.ordered",
        "Purchase order ordered",
        "Runs when a purchase order is marked as ordered with a supplier.",
        EVENT,
        "purchase_order",
    ),
    Trigger(
        "purchase_order.partially_received",
        "Purchase order partially received",
        "Runs when a delivery is recorded that does not yet complete a "
        "purchase order.",
        EVENT,
        "purchase_order",
    ),
    Trigger(
        "purchase_order.received",
        "Purchase order received",
        "Runs when every line on a purchase order has been received in full.",
        EVENT,
        "purchase_order",
    ),
    Trigger(
        "delivery.overdue",
        "Delivery overdue",
        "Runs when a purchase order's expected delivery date has passed "
        "without the order being received.",
        SCAN,
        "purchase_order",
    ),
    Trigger(
        "material.allocated",
        "Material allocated",
        "Runs when received material is allocated to a project requirement.",
        EVENT,
        "material_allocation",
    ),
)

TRIGGER_KEYS: frozenset[str] = frozenset(trigger.key for trigger in TRIGGERS)

_BY_KEY = {trigger.key: trigger for trigger in TRIGGERS}


def get(key: str) -> Trigger | None:
    return _BY_KEY.get(key)


def subject_type_for(key: str) -> str | None:
    trigger = _BY_KEY.get(key)
    return trigger.subject_type if trigger else None
