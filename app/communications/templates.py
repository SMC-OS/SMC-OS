"""Email templates (Sprint 038, docs/SPRINTS/sprint-038.md §5).

No templating library (Jinja2 or similar) is added as a dependency — every
template here is a small, explicit Python function building a subject/html
/text triple. This mirrors app/quotes/pdf.py's own approach to safe
document generation (an `_escape()` helper, plain string building, no
templating engine) rather than introducing a second way of doing the same
thing in this codebase.

Every piece of tenant/customer/quote content is passed through `_escape()`
before it reaches the HTML string — nothing here ever lets tenant- or
user-authored text (a company name, a customer name, a quote title) break
out of the surrounding markup or inject executable content. Plain-text
bodies need no escaping (there is no markup to break out of) but still go
through the same content, so the two never drift apart.

Only `render_invitation` is called anywhere in Phase 1
(app/invitations/service.py). The rest exist now, fully tested, ready for
Phase 3 to wire to real triggers (quote send/follow-up, project lifecycle,
review requests) without adding new escaping/rendering surface area at
that point — see docs/SPRINTS/sprint-038.md §7's phase table.
"""

from dataclasses import dataclass
from html import escape as _escape


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def _wrap(*, tenant_display_name: str, preheader: str, body_html_lines: list[str], body_text_lines: list[str]) -> tuple[str, str]:
    """The shared envelope every template renders inside. Deliberately
    minimal inline-styled HTML (no external stylesheet, no images by
    default) — the common, safe baseline for transactional email
    rendering across mail clients, and nothing here depends on
    GeoCore-hosted assets being reachable from an arbitrary inbox."""

    safe_tenant = _escape(tenant_display_name)
    safe_preheader = _escape(preheader)
    html = f"""<!doctype html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f2;font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;">
<span style="display:none;font-size:1px;color:#f4f4f2;">{safe_preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;padding:32px;">
<tr><td style="font-size:14px;color:#6b7060;padding-bottom:16px;">{safe_tenant}</td></tr>
{''.join(f'<tr><td style="padding-bottom:14px;font-size:15px;line-height:1.5;">{line}</td></tr>' for line in body_html_lines)}
<tr><td style="padding-top:24px;font-size:12px;color:#9a9a90;border-top:1px solid #ececea;">
Sent via GeoCore on behalf of {safe_tenant}.
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    text = "\n\n".join(body_text_lines + [f"— {tenant_display_name}, sent via GeoCore"])
    return html, text


def render_invitation(*, tenant_display_name: str, inviter_name: str, accept_url: str) -> RenderedEmail:
    subject = f"You've been invited to join {tenant_display_name} on GeoCore"
    safe_tenant = _escape(tenant_display_name)
    safe_inviter = _escape(inviter_name)
    safe_url = _escape(accept_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"{inviter_name} invited you to join {tenant_display_name} on GeoCore",
        body_html_lines=[
            f"<strong>{safe_inviter}</strong> has invited you to join <strong>{safe_tenant}</strong> "
            "on GeoCore.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">Accept invitation</a>',
            "This link expires automatically, per your organisation's invitation settings. If you "
            "weren't expecting this, you can safely ignore this email.",
        ],
        body_text_lines=[
            f"{inviter_name} has invited you to join {tenant_display_name} on GeoCore.",
            f"Accept your invitation: {accept_url}",
            "This link expires automatically. If you weren't expecting this, you can safely ignore "
            "this email.",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_quote_sent(*, tenant_display_name: str, customer_name: str, quote_title: str, portal_url: str) -> RenderedEmail:
    subject = f"Your quote from {tenant_display_name}: {quote_title}"
    safe_customer = _escape(customer_name)
    safe_title = _escape(quote_title)
    safe_tenant = _escape(tenant_display_name)
    safe_url = _escape(portal_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"Your quote is ready to view: {quote_title}",
        body_html_lines=[
            f"Hi {safe_customer},",
            f"{safe_tenant} has prepared a quote for you — <strong>{safe_title}</strong>.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">View your quote</a>',
        ],
        body_text_lines=[
            f"Hi {customer_name},",
            f"{tenant_display_name} has prepared a quote for you — {quote_title}.",
            f"View your quote: {portal_url}",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_quote_follow_up(*, tenant_display_name: str, customer_name: str, quote_title: str, portal_url: str) -> RenderedEmail:
    subject = f"Following up: your quote from {tenant_display_name}"
    safe_customer = _escape(customer_name)
    safe_title = _escape(quote_title)
    safe_tenant = _escape(tenant_display_name)
    safe_url = _escape(portal_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"Just checking in about your quote: {quote_title}",
        body_html_lines=[
            f"Hi {safe_customer},",
            f"Just checking in — your quote from {safe_tenant} (<strong>{safe_title}</strong>) is "
            "still available. Let us know if you have any questions.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">View your quote</a>',
        ],
        body_text_lines=[
            f"Hi {customer_name},",
            f"Just checking in — your quote from {tenant_display_name} ({quote_title}) is still "
            "available. Let us know if you have any questions.",
            f"View your quote: {portal_url}",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_project_confirmation(*, tenant_display_name: str, customer_name: str, project_title: str, portal_url: str) -> RenderedEmail:
    subject = f"Your project has been booked: {project_title}"
    safe_customer = _escape(customer_name)
    safe_title = _escape(project_title)
    safe_tenant = _escape(tenant_display_name)
    safe_url = _escape(portal_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"Your project with {tenant_display_name} is booked",
        body_html_lines=[
            f"Hi {safe_customer},",
            f"Good news — <strong>{safe_title}</strong> has been booked with {safe_tenant}.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">View project</a>',
        ],
        body_text_lines=[
            f"Hi {customer_name},",
            f"Good news — {project_title} has been booked with {tenant_display_name}.",
            f"View project: {portal_url}",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_project_update(*, tenant_display_name: str, customer_name: str, project_title: str, update_text: str, portal_url: str) -> RenderedEmail:
    subject = f"An update on your project: {project_title}"
    safe_customer = _escape(customer_name)
    safe_title = _escape(project_title)
    safe_tenant = _escape(tenant_display_name)
    safe_update = _escape(update_text)
    safe_url = _escape(portal_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"An update on {project_title}",
        body_html_lines=[
            f"Hi {safe_customer},",
            f"{safe_tenant} has an update on <strong>{safe_title}</strong>:",
            f'<div style="background:#f4f4f2;border-radius:6px;padding:12px 16px;">{safe_update}</div>',
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">View project</a>',
        ],
        body_text_lines=[
            f"Hi {customer_name},",
            f"{tenant_display_name} has an update on {project_title}:",
            update_text,
            f"View project: {portal_url}",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_project_completion(*, tenant_display_name: str, customer_name: str, project_title: str, portal_url: str) -> RenderedEmail:
    subject = f"Your project is complete: {project_title}"
    safe_customer = _escape(customer_name)
    safe_title = _escape(project_title)
    safe_tenant = _escape(tenant_display_name)
    safe_url = _escape(portal_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"{project_title} is now complete",
        body_html_lines=[
            f"Hi {safe_customer},",
            f"<strong>{safe_title}</strong> is now complete. Thank you for choosing {safe_tenant}.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">View project</a>',
        ],
        body_text_lines=[
            f"Hi {customer_name},",
            f"{project_title} is now complete. Thank you for choosing {tenant_display_name}.",
            f"View project: {portal_url}",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_review_request(*, tenant_display_name: str, customer_name: str, project_title: str, review_url: str) -> RenderedEmail:
    subject = f"How did we do? {tenant_display_name}"
    safe_customer = _escape(customer_name)
    safe_title = _escape(project_title)
    safe_tenant = _escape(tenant_display_name)
    safe_url = _escape(review_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"Share your feedback on {project_title}",
        body_html_lines=[
            f"Hi {safe_customer},",
            f"Now that <strong>{safe_title}</strong> is complete, {safe_tenant} would really "
            "appreciate a quick review.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">Leave a review</a>',
        ],
        body_text_lines=[
            f"Hi {customer_name},",
            f"Now that {project_title} is complete, {tenant_display_name} would really appreciate a "
            "quick review.",
            f"Leave a review: {review_url}",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_workspace_alert(
    *, tenant_display_name: str, recipient_name: str, headline: str, detail: str
) -> RenderedEmail:
    """An email copy of an in-app notification (Sprint 039, Workstream B).

    The one template in this module addressed to a **colleague**, not to a
    customer, and it says so: no portal link, no marketing tone, and a
    closing line pointing at where the setting that produced it lives.
    Nobody receives one of these without having turned the email channel
    on for that category themselves — it is off by default.
    """
    subject = f"{headline} — {tenant_display_name}"
    safe_recipient = _escape(recipient_name)
    safe_headline = _escape(headline)
    safe_detail = _escape(detail)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=headline,
        body_html_lines=[
            f"Hi {safe_recipient},",
            f"<strong>{safe_headline}</strong>",
            safe_detail,
            "You're getting this because you turned on email for this kind of "
            "notification in GeoCore. You can turn it off again in Settings "
            "&rarr; Notifications.",
        ],
        body_text_lines=[
            f"Hi {recipient_name},",
            headline,
            detail,
            "You're getting this because you turned on email for this kind of "
            "notification in GeoCore. You can turn it off again in Settings > "
            "Notifications.",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)
