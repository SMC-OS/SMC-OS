"""Resend webhook signature verification (Sprint 038, Phase 2).

Resend delivers webhooks via Svix, and documents Svix's own signing
scheme as the verification method (no Resend-specific library needed —
this implements the publicly documented Svix algorithm directly over
`hmac`/`hashlib`/`base64`, the same "no extra SDK for what stdlib already
does" choice app/communications/provider.py made for sending):

  * Headers `svix-id`, `svix-timestamp`, `svix-signature` accompany every
    delivery.
  * The signed content is exactly `{svix-id}.{svix-timestamp}.{raw body}`.
  * The secret is issued as `whsec_<base64>`; the `whsec_` prefix is
    stripped and the remainder base64-decoded to get the raw HMAC key.
  * The signature is `base64(HMAC-SHA256(key, signed_content))`.
  * `svix-signature` can carry multiple space-separated `v1,<sig>` entries
    (Svix rotates signing secrets) — a match against any one is valid.

Verification never trusts a payload without this check succeeding first —
same ordering as app/billing/service.py's Stripe webhook handling.
"""

import base64
import hmac
import time
from dataclasses import dataclass
from hashlib import sha256


class WebhookSignatureError(Exception):
    """Raised when a webhook request fails signature verification, is
    missing required headers, or its timestamp is outside the replay
    tolerance. Turned into a 400 by the router — never processed."""


# Svix's own recommended replay tolerance. A request timestamped further
# from "now" than this in either direction is rejected outright, signature
# aside — this bounds how long a captured, still-correctly-signed request
# could be replayed.
_TIMESTAMP_TOLERANCE_SECONDS = 5 * 60


@dataclass(frozen=True)
class VerifiedWebhookRequest:
    svix_id: str
    body: bytes


def verify_svix_signature(
    *,
    body: bytes,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
    secret: str,
    now: float | None = None,
) -> VerifiedWebhookRequest:
    if not svix_id or not svix_timestamp or not svix_signature:
        raise WebhookSignatureError("Missing required Svix headers.")

    try:
        timestamp = int(svix_timestamp)
    except ValueError:
        raise WebhookSignatureError("Invalid svix-timestamp header.") from None

    current = now if now is not None else time.time()
    if abs(current - timestamp) > _TIMESTAMP_TOLERANCE_SECONDS:
        raise WebhookSignatureError("Webhook timestamp is outside the allowed tolerance.")

    secret_b64 = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(secret_b64)
    except Exception:
        raise WebhookSignatureError("Malformed webhook secret.") from None

    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed_content, sha256).digest()).decode()

    # svix-signature is space-separated "v1,<base64sig>" entries — accept
    # a match against any one (secret rotation support).
    provided_signatures = [
        part.split(",", 1)[1]
        for part in svix_signature.split()
        if "," in part
    ]
    if not any(hmac.compare_digest(expected, provided) for provided in provided_signatures):
        raise WebhookSignatureError("Signature verification failed.")

    return VerifiedWebhookRequest(svix_id=svix_id, body=body)
