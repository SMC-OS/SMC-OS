"""Sprint 039 Production Readiness Defect Gate — final auth/trial gates.

Password creation policy, enforced at every point a password is newly
chosen: signup (SignupRequest), password reset (ResetPasswordRequest),
and invitation-accept (AcceptInvitationRequest) — see each model's
`_password_policy` field_validator in app/auth/models.py and
app/invitations/models.py.

Deliberately NOT consulted at login: app/auth/security.py's
verify_password() only compares a submitted password against the
stored bcrypt hash. A user whose password predates this policy (or
was created before it existed) keeps logging in with it unchanged —
this module has no opinion on historical passwords, only on new ones.
"""

import re

PASSWORD_MIN_LENGTH = 10

# Order matters: this is also the order failures are reported in, and
# the frontend's apps/web/lib/passwordPolicy.ts mirrors both the
# thresholds and the messages so the two stay visibly in sync.
_REQUIREMENTS: list[tuple[str, re.Pattern[str]]] = [
    ("at least one uppercase letter", re.compile(r"[A-Z]")),
    ("at least one lowercase letter", re.compile(r"[a-z]")),
    ("at least one number", re.compile(r"[0-9]")),
    ("at least one special character", re.compile(r"[^A-Za-z0-9]")),
]


def validate_password_strength(password: str) -> str:
    """Raises ValueError (with a human-readable message) on the first
    unmet requirement; returns the password unchanged otherwise.

    A Pydantic `@field_validator` turns the ValueError into a 422
    automatically — this function never touches the HTTP layer
    directly, so it works identically from any of the three models
    that call it.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")
    for message, pattern in _REQUIREMENTS:
        if not pattern.search(password):
            raise ValueError(f"Password must contain {message}.")
    return password
