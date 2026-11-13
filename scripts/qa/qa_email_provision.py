"""One-time isolated QA email fixture; no public admission changes, no token output.

Run only inside the exact QA API container with owner-designated Gmail alias.
Never use a real existing account, print credentials, or send to another address.
"""
import os
import re
import sys

def main():
    from sqlalchemy import select
    from app.auth.models import SignupRequest
    from app.auth.service import auth_service
    from app.auth.verification_service import email_verification_service, verification_delivery_outcome
    from app.auth.password_reset_service import password_reset_service
    from app.communications.models import CommunicationType
    from app.core.config import settings
    from app.database import crud
    from app.database.database import SessionLocal
    from app.database.models import Communication

    if (os.environ.get("RAILWAY_PROJECT_ID") != "a16eaf0a-b5a5-4e8e-b79e-4d191457638e"
        or os.environ.get("RAILWAY_ENVIRONMENT_ID") != "f948241d-446f-43ed-bff0-5d12decffd50"
        or os.environ.get("RAILWAY_SERVICE_ID") != "40d0cad3-0c01-467a-910e-6c9f818fd2bf"
        or settings.new_account_admission != "closed"
        or settings.frontend_base_url.rstrip("/") != "https://geocore-web-qa-acceptance.up.railway.app"
        or settings.email_sending_domain != "send.geocore.one"
        or not settings.resend_api_key):
        raise RuntimeError("wrong environment, admission, sender or frontend")

    recipient = os.environ["QA_EMAIL_RECIPIENT"]
    run = os.environ["QA_EMAIL_RUN"]
    password = os.environ["QA_EMAIL_PW"]
    if not re.fullmatch(r"[a-zA-Z0-9.]+\+geocore-qa-[0-9]+-[0-9]+@gmail\.com", recipient):
        raise RuntimeError("not a run-specific Gmail test alias")
    if not recipient.endswith("+geocore-qa-" + run + "@gmail.com"):
        raise RuntimeError("alias does not match the run")
    company = "GeoCore email acceptance " + run
    db = SessionLocal()
    try:
        user = crud.get_user_by_email(db, recipient)
        if user is None:
            tenant, user = auth_service.signup(db, SignupRequest(
                company_name=company, name="GeoCore QA Tester", email=recipient,
                password=password))
            # This is the same real verification service invoked by the signup route.
            outcome, _ = verification_delivery_outcome(email_verification_service.send_verification_email(db, user))
            if outcome != "sent":
                raise RuntimeError("initial verification provider acceptance failed")
            password_reset_service.request_reset(db, recipient)
        else:
            # Startup may retry. Never send duplicate emails or modify existing accounts.
            tenant = crud.get_tenant_by_id(db, user.tenant_id)
            if tenant is None or tenant.name != company or auth_service.authenticate(db, recipient, password) is None:
                raise RuntimeError("existing account does not belong to this run")
        for kind in (CommunicationType.EMAIL_VERIFICATION, CommunicationType.PASSWORD_RESET):
            rows = db.scalars(select(Communication).where(
                Communication.tenant_id == user.tenant_id,
                Communication.recipient == recipient,
                Communication.message_type == kind.value)).all()
            accepted = [r for r in rows if r.status in {"sent", "delivered"} and r.provider_message_id]
            if not accepted:
                raise RuntimeError("provider acceptance missing for " + kind.value)
            print("EMAILQA|PASS|" + kind.value + "|provider accepted", flush=True)
        print("EMAILQA|DONE", flush=True)
    finally:
        db.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("EMAILQA|FAILED|" + type(exc).__name__, flush=True)
        sys.exit(1)
