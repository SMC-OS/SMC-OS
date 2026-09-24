"""Staging verification of the 72-byte password hotfix.

Runs INSIDE the staging API container and calls the live API process on
localhost, then checks the database directly. Every account it creates
is synthetic (company name starts "HOTFIX72 <run>", emails end
@example.invalid) and is deleted at the end, pass or fail. It never
prints a password, hash or token.

    cat scripts/staging/verify_password_byte_limit.py | \\
      railway ssh --service simo-api-staging --environment staging -- python - --confirm-staging

Safety guard (checked before any request or write):
- RAILWAY_ENVIRONMENT_NAME must be exactly "staging";
- the database host must not be the production database host;
- the production sales workspace must not exist in the connected database.
APP_ENV is deliberately NOT used: the staging runbook sets
APP_ENV=production on staging (production-grade runtime checks), so it
says nothing about which environment this is.

Refuses to run without --confirm-staging.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailVerificationToken,
    Invitation,
    PasswordResetToken,
    Subscription,
    Tenant,
    User,
)

PRODUCTION_DB_HOST = "simo-postgres-production.railway.internal"
PRODUCTION_SALES_TENANT_ID = "e36f3837-a9b7-4810-bb10-1fcd919292b5"


def safety_refusal(environment_name: str | None, db_host: str | None, production_tenant_present: bool) -> str | None:
    """Why this run must not proceed, or None when it is safe. Pure, so it
    is unit-tested without a database. Never includes a secret."""
    name = (environment_name or "").strip()
    if not name:
        return "RAILWAY_ENVIRONMENT_NAME is not set; this is not a known staging container."
    if name.lower() == "production":
        return "RAILWAY_ENVIRONMENT_NAME is production."
    if name != "staging":
        return f"RAILWAY_ENVIRONMENT_NAME is {name!r}, not 'staging'."
    if (db_host or "").strip().lower() == PRODUCTION_DB_HOST:
        return "the database host is the production database."
    if production_tenant_present:
        return "the connected database contains the production sales workspace."
    return None


def environment_refusal(db) -> str | None:
    """Reads only the Railway environment name, the database HOST (never
    the URL or credentials) and one existence check. The host is checked
    before any connection is made."""
    name = os.environ.get("RAILWAY_ENVIRONMENT_NAME")
    host = make_url(settings.database_url).host
    early = safety_refusal(name, host, production_tenant_present=False)
    if early:
        return early
    try:
        present = bool(
            db.execute(
                text("select count(*) from tenants where id = :tid"),
                {"tid": PRODUCTION_SALES_TENANT_ID},
            ).scalar()
        )
    except Exception:
        db.rollback()
        return "could not confirm the database is not production (query failed)."
    return safety_refusal(name, host, production_tenant_present=present)


RUN = uuid.uuid4().hex[:8]
PREFIX = f"HOTFIX72 {RUN}"
VALID = "Hotfix-Valid-Pass-1!"
VALID_2 = "Hotfix-Other-Pass-2!"
LONG_ASCII = "Aa1!" + "a" * 69  # 73 bytes
LONG_UTF8 = "Aa1!" + "\u00e9" * 35  # 39 characters, 74 bytes
OK_72_BYTES = "Aa1!" + "\u00e9" * 34  # 38 characters, 72 bytes
TOO_LONG_MESSAGE = "Password must be at most 72 bytes long."
SECRETS = (VALID, VALID_2, LONG_ASCII, LONG_UTF8, OK_72_BYTES)

RESULTS: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: object = "") -> bool:
    RESULTS.append((label, bool(ok), str(detail)))
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail != "" and not ok else ""))
    return bool(ok)


def email(tag: str) -> str:
    return f"hotfix72-{tag}-{RUN}@example.invalid"


def clean_response(r: httpx.Response) -> bool:
    body = r.text
    return not any(s in body for s in SECRETS) and "Traceback" not in body and "$2b$" not in body


def main(argv: list[str]) -> int:
    if "--confirm-staging" not in argv:
        print("Refusing to run without --confirm-staging.")
        return 2
    db = SessionLocal()
    refusal = environment_refusal(db)
    if refusal:
        db.close()
        print(f"Refusing to run: {refusal}")
        return 2
    print("Safety guard: RAILWAY_ENVIRONMENT_NAME=staging, non-production database host, "
          "production sales workspace absent. Proceeding.")

    port = os.environ.get("PORT", "8000")
    root = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60)
    api = httpx.Client(base_url=f"http://127.0.0.1:{port}/api/v1", timeout=60)
    try:
        ready = root.get("/ready")
        check("/ready is ready with the database reachable", ready.status_code == 200 and "reachable" in ready.text, ready.text[:120])

        # A. Over-long signup
        for label, pw in (("73 ASCII bytes", LONG_ASCII), ("74 UTF-8 bytes / 39 chars", LONG_UTF8)):
            company, mail = f"{PREFIX} long {label}", email("long-" + label.split()[0])
            r = api.post("/auth/signup", json={"company_name": company, "name": "Hotfix", "email": mail, "password": pw})
            check(f"A signup {label}: 422", r.status_code == 422, r.status_code)
            check(f"A signup {label}: approved message", TOO_LONG_MESSAGE in r.text)
            check(f"A signup {label}: no password echo / traceback", clean_response(r))
            db.expire_all()
            check(f"A signup {label}: no workspace created", db.scalar(select(Tenant).where(Tenant.name == company)) is None)
            check(f"A signup {label}: no user created", crud.get_user_by_email(db, mail) is None)

        # B. Over-long login, unknown account
        unknown = api.post("/auth/login", json={"email": email("nobody"), "password": LONG_UTF8})
        check("B login unknown email + over-long password: 401", unknown.status_code == 401, unknown.status_code)
        check("B login: no password echo", clean_response(unknown))

        # C. Normal signup: trial, no Stripe, verification unchanged
        owner_mail = email("owner")
        r = api.post(
            "/auth/signup",
            json={"company_name": f"{PREFIX} owner", "name": "Hotfix Owner", "email": owner_mail,
                  "password": VALID, "plan": "pro", "billing_period": "monthly"},
        )
        if not check("C normal signup: 201", r.status_code == 201, r.status_code):
            return 1
        body = r.json()["user"]
        check("C signup: email starts unverified", body["email_verified_at"] is None and body["verification_required"] is True)
        tenant_id, owner_id = uuid.UUID(body["tenant_id"]), uuid.UUID(body["id"])
        db.expire_all()
        sub = crud.get_subscription_by_tenant_id(db, tenant_id)
        check("C signup: 14-day trial started", sub is not None and sub.status == "trialing"
              and sub.trial_end - sub.trial_start == timedelta(days=14))
        check("C signup: plan carried through (pro monthly)", sub is not None and (sub.plan, sub.billing_period) == ("pro", "monthly"))
        check("C signup: no Stripe customer or subscription", sub is not None and not sub.stripe_customer_id and not sub.stripe_subscription_id)
        check("C signup: verification email token issued",
              db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.user_id == owner_id)) is not None)

        # Normal login, and the same 401 for an existing account with an over-long password
        check("Login with the valid password: 200", api.post("/auth/login", json={"email": owner_mail, "password": VALID}).status_code == 200)
        known = api.post("/auth/login", json={"email": owner_mail, "password": LONG_UTF8})
        check("Login existing account + over-long password: 401", known.status_code == 401, known.status_code)
        check("Login: identical body for known and unknown accounts", known.json() == unknown.json())

        # Synthetic owner is marked verified so invites and settings work
        crud.set_user_email_verified_at(db, owner_id, datetime.now(timezone.utc))

        # CHANGE PASSWORD
        session_a = api.post("/auth/login", json={"email": owner_mail, "password": VALID}).json()["access_token"]
        session_b = api.post("/auth/login", json={"email": owner_mail, "password": VALID}).json()["access_token"]
        h = {"Authorization": f"Bearer {session_a}"}
        r = api.post("/auth/password/change", json={"current_password": VALID, "new_password": LONG_UTF8}, headers=h)
        check("Change password over-long new password: 422", r.status_code == 422, r.status_code)
        check("Change password: no password echo", clean_response(r))
        r = api.post("/auth/password/change", json={"current_password": VALID, "new_password": VALID_2}, headers=h)
        check("Change password valid: 200", r.status_code == 200, r.status_code)
        fresh = r.json()["access_token"] if r.status_code == 200 else ""
        check("Change password: other session revoked", api.get("/auth/me", headers={"Authorization": f"Bearer {session_b}"}).status_code == 401)
        check("Change password: this session kept (fresh token)", api.get("/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200)
        check("Change password: new password logs in", api.post("/auth/login", json={"email": owner_mail, "password": VALID_2}).status_code == 200)

        # PASSWORD RESET (token minted like the emailed link)
        raw = secrets.token_urlsafe(32)
        token_row = crud.create_password_reset_token(
            db, id=uuid.uuid4(), user_id=owner_id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        r = api.post("/auth/password/reset", json={"token": raw, "new_password": LONG_UTF8})
        check("Reset over-long password: 422", r.status_code == 422, r.status_code)
        check("Reset: no password echo", clean_response(r))
        db.expire_all()
        check("Reset: token still unused after rejection", db.get(PasswordResetToken, token_row.id).used_at is None)
        check("Reset: old password still valid", api.post("/auth/login", json={"email": owner_mail, "password": VALID_2}).status_code == 200)
        r = api.post("/auth/password/reset", json={"token": raw, "new_password": OK_72_BYTES})
        check("Reset same link with a 72-byte password: 200", r.status_code == 200, r.status_code)
        check("Reset: new password logs in", api.post("/auth/login", json={"email": owner_mail, "password": OK_72_BYTES}).status_code == 200)

        # INVITE ACCEPTANCE
        owner_token = api.post("/auth/login", json={"email": owner_mail, "password": OK_72_BYTES}).json()["access_token"]
        invitee = email("invitee")
        r = api.post("/invitations", json={"email": invitee}, headers={"Authorization": f"Bearer {owner_token}"})
        if check("Invite created: 201", r.status_code == 201, r.status_code):
            invite_token = r.json()["token"]
            r = api.post(f"/invitations/token/{invite_token}/accept", json={"name": "Hotfix Staff", "password": LONG_UTF8})
            check("Invite accept over-long password: 422", r.status_code == 422, r.status_code)
            check("Invite accept: no password echo", clean_response(r))
            db.expire_all()
            check("Invite accept: no user created", crud.get_user_by_email(db, invitee) is None)
            status_now = api.get(f"/invitations/token/{invite_token}").json().get("status")
            check("Invite: still pending", status_now == "pending", status_now)
            r = api.post(f"/invitations/token/{invite_token}/accept", json={"name": "Hotfix Staff", "password": VALID})
            check("Invite accept valid password: 200", r.status_code == 200, r.status_code)
            check("Invitee logs in", api.post("/auth/login", json={"email": invitee, "password": VALID}).status_code == 200)
    finally:
        db.rollback()
        tenants = db.scalars(select(Tenant).where(Tenant.name.like(f"{PREFIX}%"))).all()
        for tenant in tenants:
            user_ids = [u.id for u in db.scalars(select(User).where(User.tenant_id == tenant.id))]
            if user_ids:
                db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id.in_(user_ids)))
                db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids)))
            for model in (Invitation, Communication, ActivityLog, Subscription, User):
                db.execute(delete(model).where(model.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
        left_tenants = db.scalars(select(Tenant).where(Tenant.name.like(f"{PREFIX}%"))).all()
        left_users = db.scalars(select(User).where(User.email.like(f"hotfix72-%-{RUN}@example.invalid"))).all()
        check(f"Cleanup: removed {len(tenants)} synthetic workspaces, none left", not left_tenants and not left_users)
        db.close()

    failed = [label for label, ok, _ in RESULTS if not ok]
    print(f"\nRun {RUN}: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed.")
    print("PASSWORD HOTFIX STAGING CHECKS: " + ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
