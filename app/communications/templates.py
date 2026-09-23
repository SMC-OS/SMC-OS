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


def render_email_verification(
    *, tenant_display_name: str, recipient_name: str, verify_url: str
) -> RenderedEmail:
    subject = "Verify your email for GeoCore"
    safe_name = _escape(recipient_name)
    safe_url = _escape(verify_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader="Confirm your email to finish setting up your GeoCore account",
        body_html_lines=[
            f"Hi {safe_name},",
            "Please confirm this is your email address to finish setting up your GeoCore account.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">Verify your email</a>',
            "This link expires in 24 hours. If you didn't create a GeoCore account, you can safely "
            "ignore this email.",
        ],
        body_text_lines=[
            f"Hi {recipient_name},",
            "Please confirm this is your email address to finish setting up your GeoCore account.",
            f"Verify your email: {verify_url}",
            "This link expires in 24 hours. If you didn't create a GeoCore account, you can safely "
            "ignore this email.",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_password_reset(*, tenant_display_name: str, recipient_name: str, reset_url: str) -> RenderedEmail:
    subject = "Reset your GeoCore password"
    safe_name = _escape(recipient_name)
    safe_url = _escape(reset_url)

    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader="Reset your GeoCore password",
        body_html_lines=[
            f"Hi {safe_name},",
            "We received a request to reset your GeoCore password.",
            f'<a href="{safe_url}" style="display:inline-block;background:#173b2c;color:#ffffff;'
            'text-decoration:none;padding:10px 20px;border-radius:6px;">Reset your password</a>',
            "This link expires in 1 hour and can only be used once. If you didn't request "
            "this, you can safely ignore this email — your password won't be changed.",
        ],
        body_text_lines=[
            f"Hi {recipient_name},",
            "We received a request to reset your GeoCore password.",
            f"Reset your password: {reset_url}",
            "This link expires in 1 hour and can only be used once. If you didn't request "
            "this, you can safely ignore this email — your password won't be changed.",
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


_BUTTON_STYLE = (
    "display:inline-block;background:#173b2c;color:#ffffff;"
    "text-decoration:none;padding:10px 20px;border-radius:6px;"
)


def render_trial_ending(
    *, tenant_display_name: str, recipient_name: str, days_remaining: int, trial_end_label: str, upgrade_url: str
) -> RenderedEmail:
    """Phase B — sent once when a no-card trial has 3 days or fewer left."""
    day_word = "day" if days_remaining == 1 else "days"
    subject = f"Your GeoCore free trial ends in {days_remaining} {day_word}"
    safe_name = _escape(recipient_name)
    safe_url = _escape(upgrade_url)
    safe_end = _escape(trial_end_label)
    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader=f"Your free trial ends on {trial_end_label}",
        body_html_lines=[
            f"Hi {safe_name},",
            f"Your 14-day GeoCore free trial ends on <strong>{safe_end}</strong>.",
            "To keep using your workspace without interruption, choose a plan and add your payment "
            "details. Your data stays exactly as it is.",
            f'<a href="{safe_url}" style="{_BUTTON_STYLE}">Choose a plan</a>',
            "If you subscribe before the trial ends, you won't be charged until it ends.",
        ],
        body_text_lines=[
            f"Hi {recipient_name},",
            f"Your 14-day GeoCore free trial ends on {trial_end_label}.",
            "To keep using your workspace without interruption, choose a plan and add your payment "
            "details. Your data stays exactly as it is.",
            f"Choose a plan: {upgrade_url}",
            "If you subscribe before the trial ends, you won't be charged until it ends.",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_trial_ended(*, tenant_display_name: str, recipient_name: str, upgrade_url: str) -> RenderedEmail:
    """Phase B — sent once after a no-card trial has ended unconverted."""
    subject = "Your GeoCore free trial has ended"
    safe_name = _escape(recipient_name)
    safe_url = _escape(upgrade_url)
    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader="Choose a plan to pick up where you left off",
        body_html_lines=[
            f"Hi {safe_name},",
            "Your 14-day GeoCore free trial has ended. Your workspace and everything in it are "
            "kept safe — nothing has been deleted.",
            "Choose a plan and add your payment details to pick up exactly where you left off.",
            f'<a href="{safe_url}" style="{_BUTTON_STYLE}">Choose a plan</a>',
        ],
        body_text_lines=[
            f"Hi {recipient_name},",
            "Your 14-day GeoCore free trial has ended. Your workspace and everything in it are "
            "kept safe — nothing has been deleted.",
            "Choose a plan and add your payment details to pick up exactly where you left off.",
            f"Choose a plan: {upgrade_url}",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_demo_request_sales_notification(
    *, tenant_display_name: str, summary_lines: list[str], customer_url: str | None
) -> RenderedEmail:
    """Phase B — internal alert to GeoCore's own sales workspace owners.
    `summary_lines` are plain "Label: value" strings, escaped here."""
    subject = "New GeoCore demo request"
    html_lines = ["A new demo request has arrived from the GeoCore website."]
    html_lines += [_escape(line) for line in summary_lines]
    text_lines = ["A new demo request has arrived from the GeoCore website.", *summary_lines]
    if customer_url:
        html_lines.append(f'<a href="{_escape(customer_url)}" style="{_BUTTON_STYLE}">Open in GeoCore</a>')
        text_lines.append(f"Open in GeoCore: {customer_url}")
    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader="New demo request from the GeoCore website",
        body_html_lines=html_lines,
        body_text_lines=text_lines,
    )
    return RenderedEmail(subject=subject, html=html, text=text)


def render_demo_request_confirmation(*, tenant_display_name: str, recipient_name: str) -> RenderedEmail:
    """Phase B — confirmation to the prospect who requested a demo. Makes
    no promise about timing: only that the request arrived."""
    subject = "We've received your GeoCore demo request"
    safe_name = _escape(recipient_name)
    html, text = _wrap(
        tenant_display_name=tenant_display_name,
        preheader="Thanks — we'll be in touch to arrange your demo",
        body_html_lines=[
            f"Hi {safe_name},",
            "Thank you for requesting a GeoCore demo. We've received your details and a member of "
            "the team will be in touch to arrange a time that suits you.",
            "If you'd like to explore on your own in the meantime, every plan includes a 14-day "
            "free trial. No card required.",
        ],
        body_text_lines=[
            f"Hi {recipient_name},",
            "Thank you for requesting a GeoCore demo. We've received your details and a member of "
            "the team will be in touch to arrange a time that suits you.",
            "If you'd like to explore on your own in the meantime, every plan includes a 14-day "
            "free trial. No card required.",
        ],
    )
    return RenderedEmail(subject=subject, html=html, text=text)
