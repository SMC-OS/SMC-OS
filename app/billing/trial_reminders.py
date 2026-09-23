"""Phase B — trial-expiry reminder emails for the no-card trial.

Two emails per trial, each sent at most once:

- "trial ending" when an app-run trial has 3 days or fewer left;
- "trial ended" once it has expired without the tenant subscribing.

Sent to the workspace's verified Owners through the existing
DeliveryService, whose `dedupe_key` makes each send idempotent: running
this job daily (or re-running it by hand) never emails anyone twice, and
it needs no new database columns. Paid, grandfathered and Stripe-managed
subscriptions are never touched — only rows app/billing/trial.py treats
as an app-run trial.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.billing.trial import trial_status
from app.communications.models import CommunicationType
from app.communications.service import DeliveryService, delivery_service
from app.communications.templates import render_trial_ended, render_trial_ending
from app.core.config import settings
from app.database import crud
from app.database.models import Subscription

_UK = ZoneInfo("Europe/London")


@dataclass
class TrialReminderResult:
    examined: int = 0
    ending_sent: int = 0
    ended_sent: int = 0
    skipped_not_due: int = 0
    skipped_no_recipient: int = 0
    retried: int = 0
    # True when this deployment cannot send email (no provider key, or no
    # real frontend URL for the links): nothing is attempted or recorded.
    skipped_email_unconfigured: bool = False


def _uk_date_label(moment: datetime) -> str:
    local = moment.astimezone(_UK)
    return f"{local.strftime('%A')} {local.day} {local.strftime('%B %Y')}"


class TrialReminderService:
    def __init__(self, delivery: DeliveryService | None = None) -> None:
        self._delivery = delivery or delivery_service

    def run(self, db: Session, *, now: datetime | None = None) -> TrialReminderResult:
        now = now or datetime.now(timezone.utc)
        result = TrialReminderResult()
        # Never record a send that cannot happen: a failed row is stored
        # under the reminder's dedupe key, so running this where email is
        # not configured (e.g. a worker missing RESEND_API_KEY or
        # FRONTEND_BASE_URL) must be a no-op, not a silent "already sent".
        if not settings.resend_api_key or "localhost" in settings.frontend_base_url:
            result.skipped_email_unconfigured = True
            return result
        candidates = db.scalars(
            select(Subscription).where(
                Subscription.status == "trialing",
                Subscription.stripe_subscription_id.is_(None),
                Subscription.trial_end.is_not(None),
                Subscription.legacy_grandfathered.is_(False),
            )
        ).all()

        upgrade_url = f"{settings.frontend_base_url}/pricing"
        for subscription in candidates:
            result.examined += 1
            status = trial_status(subscription, now)
            if status is None or status.state == "active":
                result.skipped_not_due += 1
                continue

            tenant = crud.get_tenant_by_id(db, subscription.tenant_id)
            owners = [
                user
                for user in crud.list_users_by_tenant(db, subscription.tenant_id)
                if user.role == UserRole.OWNER.value and user.is_active and user.email_verified_at is not None
            ]
            if tenant is None or not owners:
                result.skipped_no_recipient += 1
                continue

            for owner in owners:
                if status.state == "expired":
                    rendered = render_trial_ended(
                        tenant_display_name=tenant.name, recipient_name=owner.name, upgrade_url=upgrade_url
                    )
                    message_type = CommunicationType.TRIAL_ENDED
                    dedupe_key = f"trial-ended:{subscription.id}:{owner.id}"
                else:
                    rendered = render_trial_ending(
                        tenant_display_name=tenant.name,
                        recipient_name=owner.name,
                        days_remaining=status.days_remaining,
                        trial_end_label=_uk_date_label(status.trial_end),
                        upgrade_url=upgrade_url,
                    )
                    message_type = CommunicationType.TRIAL_ENDING
                    dedupe_key = f"trial-ending:{subscription.id}:{owner.id}"

                existing = crud.get_communication_by_dedupe_key(db, tenant.id, dedupe_key)
                if existing is not None:
                    # Sent (or suppressed) already: never twice. A failed
                    # attempt is retried within DeliveryService's own
                    # bounded, retryable-only policy instead of being
                    # treated as delivered.
                    if existing.status == "failed":
                        retried = self._delivery.retry(db, existing.id)
                        if retried is not None and retried.status != "failed":
                            result.retried += 1
                    continue
                self._delivery.send(
                    db,
                    tenant=tenant,
                    message_type=message_type,
                    recipient=owner.email,
                    subject=rendered.subject,
                    html=rendered.html,
                    text=rendered.text,
                    dedupe_key=dedupe_key,
                )
                if status.state == "expired":
                    result.ended_sent += 1
                else:
                    result.ending_sent += 1
        return result


trial_reminder_service = TrialReminderService()
