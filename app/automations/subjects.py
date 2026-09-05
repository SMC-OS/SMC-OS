"""Building the flat subject dict an automation's conditions and action
templates see (Sprint 036, Workstream G).

This module is the allowlist. Nothing about a customer, quote or project
is visible to a user-authored automation unless it is named here, and the
dict is built by explicit key rather than by reflection — so adding a
column to a table never silently widens what an automation can read or
interpolate into a task title.

Values are plain JSON-shaped scalars (str/float/bool/None) so a condition
comparison and a `{placeholder}` substitution behave predictably. Dates
are rendered ISO-8601; nothing here emits a Python object.
"""

from datetime import date, datetime


def _iso(value) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return None


def customer_subject(customer) -> dict:
    return {
        "id": str(customer.id),
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "customer_type": customer.customer_type,
        "company_name": customer.company_name,
        "city": customer.city,
        "postcode": customer.postcode,
        "created_at": _iso(customer.created_at),
    }


def quote_subject(quote, *, customer_name: str | None = None) -> dict:
    return {
        "id": str(quote.id),
        "quote_kind": quote.quote_kind,
        "title": quote.title or "",
        "trade": quote.trade,
        "status": quote.status,
        "currency": quote.currency,
        # `total` is a price offered or committed to, never recognised
        # revenue — the same distinction Sprint 025 locked in for the
        # dashboard. Named `total` here because that is the column name a
        # rule author sees, and documented so nobody builds a "revenue
        # over £X" rule believing it means income.
        "total": quote.total,
        "site_city": quote.site_city,
        "site_postcode": quote.site_postcode,
        "valid_until": _iso(quote.valid_until),
        "customer_id": str(quote.customer_id) if quote.customer_id else None,
        "customer_name": customer_name or "",
        "created_at": _iso(quote.created_at),
    }


def project_subject(
    project, *, customer_name: str | None = None, previous_status: str | None = None
) -> dict:
    return {
        "id": str(project.id),
        "name": project.name,
        "status": project.status,
        # Only present for project.status_changed. A rule that reads it
        # under any other trigger sees None, which no comparison operator
        # treats as a match (see conditions._compare) — so such a rule
        # never fires rather than firing on everything.
        "previous_status": previous_status,
        "project_type": project.project_type,
        "site_city": project.site_city,
        "site_postcode": project.site_postcode,
        "start_date": _iso(project.start_date),
        "target_completion_date": _iso(project.target_completion_date),
        "estimated_value": project.estimated_value,
        "customer_id": str(project.customer_id) if project.customer_id else None,
        "customer_name": customer_name or "",
        "assigned_user_id": str(project.assigned_user_id) if project.assigned_user_id else None,
        "created_at": _iso(project.created_at),
    }


def render(template: str, subject: dict) -> str:
    """Substitute `{field}` placeholders from the subject.

    Deliberately NOT str.format(): `"{0.__class__}".format(obj)` and
    `"{x!r}"` are real attribute-traversal and repr-leak vectors when the
    template is user-authored, and format spec parsing gives a rule author
    a way to raise inside a dispatch. This walks the allowlisted keys
    instead, so the only thing a template can ever produce is a value this
    module already decided to expose, and an unknown placeholder is left
    verbatim rather than raising.
    """
    rendered = template
    for key, value in subject.items():
        placeholder = "{" + key + "}"
        if placeholder in rendered:
            rendered = rendered.replace(placeholder, "" if value is None else str(value))
    return rendered
