"""EmailProvider abstraction (Sprint 038, docs/SPRINTS/sprint-038.md §6).

`DeliveryService` is the only thing that ever imports a concrete provider
class; app/invitations, app/quotes and app/automations only ever talk to
`DeliveryService`. This is the same layering `app/billing/service.py`
already uses for Stripe: a domain service, one lazily-constructed vendor
client, and a typed "not configured" exception the caller turns into a
truthful unavailable result rather than a fake success.

`ResendEmailProvider` sends over plain HTTPS via `httpx` (already a
dependency — no new SDK). It is never called with a real `resend_api_key`
until an owner has created the account and applied the DNS records in
docs/SPRINTS/sprint-038.md §4 — until then every call raises
`EmailProviderUnavailable`, exactly like `AIDraftService`/`BillingService`
when their own provider keys are unset.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings


class EmailProviderUnavailable(Exception):
    """Raised when no provider is configured. DeliveryService catches this
    and records a truthful `failed`/`unavailable` communication row —
    never raised past the service boundary to break a caller's own flow
    (creating an invitation must still succeed even if delivery can't be
    attempted)."""


@dataclass(frozen=True)
class EmailMessage:
    """Everything a provider needs to attempt one send. `idempotency_key`
    is passed to the provider's own idempotency mechanism where it has
    one (Resend supports an `Idempotency-Key` header) as a second,
    provider-side layer on top of DeliveryService's own dedupe_key check —
    defence in depth, same reasoning as the DB UNIQUE constraint backing
    dedupe_key."""

    recipient: str
    sender_identity: str
    subject: str
    html: str
    text: str
    idempotency_key: str
    reply_to: str | None = None


class SendOutcome(str, Enum):
    ACCEPTED = "accepted"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(frozen=True)
class SendResult:
    outcome: SendOutcome
    provider_message_id: str | None = None
    # Short, safe, user-facing text only — never a raw provider response
    # body or stack trace (contract: docs/SPRINTS/sprint-038.md §3.4-5).
    detail: str | None = None


class EmailProvider(ABC):
    """Storage/transport interface for outbound email. Concrete providers
    (ResendEmailProvider today) are the only code that imports a vendor
    SDK/HTTP client."""

    @abstractmethod
    def send(self, message: EmailMessage) -> SendResult: ...


class ResendEmailProvider(EmailProvider):
    def __init__(self, http_client=None) -> None:
        # Constructor-injectable for tests, same shape as
        # BillingService.__init__(self, stripe_module=None) — a test hands
        # in a mock client directly rather than monkeypatching a private
        # attribute after construction.
        self._client = http_client

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not settings.resend_api_key:
            raise EmailProviderUnavailable("Email delivery is not configured.")

        import httpx  # imported lazily, mirrors billing/ai_draft's vendor-SDK pattern

        self._client = httpx.Client(
            base_url="https://api.resend.com",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            timeout=10.0,
        )
        return self._client

    def send(self, message: EmailMessage) -> SendResult:
        client = self._get_client()

        payload = {
            "from": message.sender_identity,
            "to": [message.recipient],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        if message.reply_to:
            payload["reply_to"] = message.reply_to

        try:
            response = client.post(
                "/emails",
                json=payload,
                headers={"Idempotency-Key": message.idempotency_key},
            )
        except Exception as exc:  # network/timeout/DNS — always retryable
            return SendResult(
                outcome=SendOutcome.TRANSIENT_FAILURE,
                detail=f"Could not reach the email provider ({type(exc).__name__}).",
            )

        if response.status_code in (200, 201):
            data = response.json()
            return SendResult(outcome=SendOutcome.ACCEPTED, provider_message_id=data.get("id"))

        # 429 (rate limited) and 5xx are the provider's own signal that a
        # retry may succeed later; everything else (400/401/403/404/422 —
        # a malformed request, a bad key, an unverified sender domain) is
        # not something a bounded retry can fix.
        if response.status_code == 429 or response.status_code >= 500:
            return SendResult(
                outcome=SendOutcome.TRANSIENT_FAILURE,
                detail=f"The email provider returned a temporary error ({response.status_code}).",
            )
        return SendResult(
            outcome=SendOutcome.PERMANENT_FAILURE,
            detail=f"The email provider rejected the request ({response.status_code}).",
        )


def resolve_sender_identity(tenant) -> tuple[str, str | None]:
    """(From-header value, Reply-To address) for a tenant's outbound mail.

    Deliberately reuses app.tenants.identity.resolve()'s exact display-name
    fallback chain (trading name -> legal name -> workspace name) so the
    name a customer sees in their inbox matches the name on the PDF
    letterhead. Never sends "From" a tenant's own address — GeoCore has no
    way to verify a tenant controls it, and doing so would be a spoofing
    risk the provider's own domain verification exists specifically to
    prevent. Instead: `"{Tenant} via GeoCore" <noreply@send.geocore.one>`,
    Reply-To the tenant's own configured contact email when set, so a
    customer's reply still reaches the business, not GeoCore.
    """

    from app.tenants.identity import resolve as resolve_identity

    identity = resolve_identity(tenant)
    display_name = identity.display_name or "GeoCore"
    # A display name may itself contain characters ('"', '\') that would
    # break the quoted-string header syntax below; escape rather than
    # reject, since a business's real trading name is not something this
    # code gets to refuse.
    safe_display_name = display_name.replace("\\", "\\\\").replace('"', '\\"')
    from_header = f'"{safe_display_name} via GeoCore" <noreply@{settings.email_sending_domain}>'

    reply_to = None
    if tenant is not None:
        contact_email = getattr(tenant, "contact_email", None)
        if contact_email and contact_email.strip():
            reply_to = contact_email.strip()

    return from_header, reply_to
