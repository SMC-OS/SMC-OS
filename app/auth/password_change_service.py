"""Settings > Security "Change password" for the signed-in user.

Rules:

- Only the authenticated caller's own password can change. The router
  passes the `User` resolved from their token; nothing in the request
  body can name another account (ChangePasswordRequest forbids extra
  fields), so an Owner cannot use this to change a teammate's password.
- The current password must verify against the stored bcrypt hash, and
  the new one must differ from it. Both checks reuse
  app/auth/security.py; there is no second password system.
- The change goes through crud.set_user_password, the same write the
  reset flow uses, which increments `token_version`. Every JWT issued
  before the change is then rejected by get_current_user, so all other
  sessions are signed out. The router mints a fresh token for the caller
  alone, who has just proved they know the current password.
- A "Your GeoCore password was changed" notice goes to the account's
  verified email through DeliveryService after the change is committed.
  A provider failure is recorded on the communication row by
  DeliveryService itself and never undoes the change. Anything unexpected
  here is logged without passwords, hashes or tokens.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.communications.models import CommunicationType
from app.communications.service import DeliveryService, delivery_service
from app.communications.templates import render_password_changed
from app.core.config import settings
from app.database import crud
from app.database.models import User

logger = logging.getLogger(__name__)

_UK = ZoneInfo("Europe/London")


class CurrentPasswordIncorrectError(Exception):
    """The submitted current password does not match."""


class PasswordUnchangedError(Exception):
    """The new password is the same as the current one."""


def _matches(password: str, password_hash: str) -> bool:
    try:
        return verify_password(password, password_hash)
    except ValueError:
        # bcrypt refuses over-long input; it cannot be the stored password.
        return False


class PasswordChangeService:
    def __init__(self, delivery: DeliveryService | None = None) -> None:
        self._delivery = delivery or delivery_service

    def change_password(
        self, db: Session, user: User, *, current_password: str, new_password: str
    ) -> User:
        if not _matches(current_password, user.password_hash):
            raise CurrentPasswordIncorrectError()
        if _matches(new_password, user.password_hash):
            raise PasswordUnchangedError()

        updated = crud.set_user_password(db, user.id, password_hash=hash_password(new_password))
        if updated is None:
            raise CurrentPasswordIncorrectError()
        self._notify(db, updated)
        return updated

    def _notify(self, db: Session, user: User) -> None:
        if user.email_verified_at is None:
            return
        try:
            tenant = crud.get_tenant_by_id(db, user.tenant_id)
            if tenant is None:
                return
            changed_at = datetime.now(timezone.utc).astimezone(_UK)
            rendered = render_password_changed(
                tenant_display_name=tenant.name,
                recipient_name=user.name,
                changed_at_label=(
                    f"{changed_at.strftime('%A')} {changed_at.day} "
                    f"{changed_at.strftime('%B %Y at %H:%M')} (UK time)"
                ),
                reset_url=f"{settings.frontend_base_url}/forgot-password",
            )
            self._delivery.send(
                db,
                tenant=tenant,
                message_type=CommunicationType.PASSWORD_CHANGED,
                recipient=user.email,
                subject=rendered.subject,
                html=rendered.html,
                text=rendered.text,
                dedupe_key=f"password-changed:{user.id}:{user.token_version}",
            )
        except Exception:
            db.rollback()
            logger.warning(
                "Password-changed notification could not be sent for user %s", user.id
            )


password_change_service = PasswordChangeService()
