"""Seeded automation templates (Sprint 036, Workstream G).

Templates are **definitions, not rows**. Nothing here is written to any
tenant's database until a user explicitly activates it. Auto-creating
automations at signup would mean a workspace starts producing tasks and
notifications nobody asked for, from rules they have never read — which is
how automation features come to be distrusted and switched off wholesale.

What they do buy: nobody should have to understand a trigger/condition/
action model to get value on day one. Activating "Follow up unanswered
quotes" is one click; editing it afterwards is how someone learns what the
model actually is.

Every template uses only internal actions. None of them contacts a
customer, because GeoCore has no channel to do so — the review-request
template drafts a message for a human to send, and says so.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AutomationTemplate:
    key: str
    name: str
    description: str
    trigger_type: str
    conditions: tuple[dict, ...]
    actions: tuple[dict, ...]


TEMPLATES: tuple[AutomationTemplate, ...] = (
    AutomationTemplate(
        key="follow_up_unanswered_quotes",
        name="Follow up unanswered quotes",
        description=(
            "When a quote is nearing the end of its validity and still "
            "hasn't been approved, create a follow-up task so it doesn't "
            "quietly expire."
        ),
        trigger_type="quote.expiring",
        conditions=(),
        actions=(
            {
                "type": "create_task",
                "config": {
                    "title": "Follow up quote: {title}",
                    "body": (
                        "{customer_name} hasn't responded to this quote and it "
                        "expires on {valid_until}. Give them a call."
                    ),
                    "due_in_days": 0,
                },
            },
        ),
    ),
    AutomationTemplate(
        key="approved_quote_to_project",
        name="Approved quote → project",
        description=(
            "When a quote is approved, turn it into a project automatically "
            "so the job is booked in without re-typing anything."
        ),
        trigger_type="quote.approved",
        conditions=(),
        actions=(
            {"type": "create_project_from_quote", "config": {}},
            {
                "type": "create_notification",
                "config": {
                    "title": "Quote approved",
                    "message": "{title} was approved — the project is ready.",
                },
            },
        ),
    ),
    AutomationTemplate(
        key="project_starts_tomorrow",
        name="Project starts tomorrow",
        description=(
            "The day before a project's start date, notify the team so "
            "materials, access and labour are confirmed."
        ),
        trigger_type="project.starting",
        conditions=(),
        actions=(
            {
                "type": "create_notification",
                "config": {
                    "title": "Starting tomorrow: {name}",
                    "message": "{name} starts on {start_date}. Confirm access, materials and the team.",
                },
            },
        ),
    ),
    AutomationTemplate(
        key="completed_project_review_request",
        name="Project completed → prepare review request",
        description=(
            "When a project is completed, draft a review request for you to "
            "check and send. GeoCore prepares the message; a person sends it."
        ),
        trigger_type="project.completed",
        conditions=(),
        actions=(
            {
                "type": "draft_message",
                "config": {
                    "title": "Review request ready to send to {customer_name}",
                    "body": (
                        "Hi {customer_name},\n\nThanks for choosing us for {name}. "
                        "If you're happy with the work, a short review would mean "
                        "a lot to us and helps other people find us.\n\n"
                        "Thanks again."
                    ),
                    "due_in_days": 2,
                },
            },
        ),
    ),
    AutomationTemplate(
        key="new_customer_welcome_task",
        name="New customer → first contact task",
        description=(
            "When a customer is added, create a task to make first contact "
            "within 24 hours, so no enquiry sits untouched."
        ),
        trigger_type="customer.created",
        conditions=(),
        actions=(
            {
                "type": "create_task",
                "config": {
                    "title": "First contact: {name}",
                    "body": "New customer added. Call or email within 24 hours.",
                    "due_in_days": 1,
                },
            },
        ),
    ),
)

TEMPLATE_KEYS: frozenset[str] = frozenset(template.key for template in TEMPLATES)

_BY_KEY = {template.key: template for template in TEMPLATES}


def get(key: str) -> AutomationTemplate | None:
    return _BY_KEY.get(key)
