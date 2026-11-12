"""Provision ONE synthetic, verified owner for browser acceptance on staging.

Approval item A2 covers running this on staging. It is a staging data
write: it creates one workspace and one owner (with the automatic no-card
trial) and marks that owner's e-mail verified, because a synthetic
`.invalid` address cannot receive mail. That shortcut is NOT evidence that
sign-up e-mail delivery works; the `inbox` gate stays separate.

Refuses to run when:
  * APP_ENV is production, or Railway says the environment is production;
  * not on Railway staging and the database is not on 127.0.0.1/localhost;
  * the e-mail does not end in `.invalid`;
  * --confirm-environment does not name the detected environment.

The password is read from the SYNTHETIC_OWNER_PASSWORD environment variable
and never printed. Output: the tenant id only.

Usage (staging, inside the API container, after approval):
  SYNTHETIC_OWNER_PASSWORD=... python scripts/qa/provision_synthetic_owner.py \
      --email stone-gate-<run>@acceptance.invalid --company "Stone-gate acceptance <run>" \
      --confirm-environment staging
Isolated QA (project geocore-qa-20261110, environment acceptance): --confirm-environment acceptance.
Local dry run: same, with --confirm-environment local.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse


ISOLATED_QA_PROJECT = "geocore-qa-20261110"


def detected_environment(database_url: str, app_env: str) -> str:
    """Classify where this process runs. Railway's identity wins over APP_ENV.

    APP_ENV is "production" on staging and on the isolated QA environment as well (the
    runbook requires it there), so it cannot distinguish them from production. When Railway
    tells us the environment name we trust that; APP_ENV and the database host are only
    consulted when the process is not on Railway at all.
    """
    railway_env = (os.environ.get("RAILWAY_ENVIRONMENT_NAME") or "").strip().lower()
    project = (os.environ.get("RAILWAY_PROJECT_NAME") or "").strip().lower()
    if railway_env:
        if railway_env == "production":
            return "production"
        if railway_env == "staging":
            return "staging"
        if railway_env == "acceptance" and project == ISOLATED_QA_PROJECT:
            return "acceptance"
        return "unknown"
    if app_env == "production":
        return "production"
    host = (urlparse(database_url.replace("+psycopg", "")).hostname or "").lower()
    if host in {"127.0.0.1", "localhost"}:
        return "local"
    return "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--name", default="Synthetic Acceptance Owner")
    parser.add_argument("--confirm-environment", required=True, choices=["staging", "acceptance", "local"])
    parser.add_argument("--idempotent", action="store_true",
                        help="succeed without changes when this e-mail already exists (a pre-deploy step must never fail a later redeploy)")
    args = parser.parse_args(argv)

    # Run piped over `railway ssh ... python -` (the image has no scripts/ directory) there is no
    # __file__; the working directory of the API container is the application root.
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..") if "__file__" in globals() else os.getcwd()
    sys.path.insert(0, os.path.abspath(root))
    from app.core.config import settings

    env = detected_environment(settings.database_url, settings.app_env.value)
    if env != args.confirm_environment:
        print(f"REFUSED: detected environment is {env!r}, not {args.confirm_environment!r}", file=sys.stderr)
        return 2
    if not args.email.lower().endswith(".invalid"):
        print("REFUSED: synthetic owners must use a reserved .invalid address", file=sys.stderr)
        return 2
    password = os.environ.get("SYNTHETIC_OWNER_PASSWORD")
    if not password:
        print("REFUSED: set SYNTHETIC_OWNER_PASSWORD", file=sys.stderr)
        return 2

    from app.auth.models import SignupRequest
    from app.auth.service import EmailAlreadyRegisteredError, auth_service
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        try:
            tenant, user = auth_service.signup(
                db, SignupRequest(company_name=args.company, name=args.name, email=args.email, password=password)
            )
        except EmailAlreadyRegisteredError:
            if args.idempotent:
                db.rollback()
                print(f"already provisioned in {env}; nothing changed")
                return 0
            raise
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
        print(f"provisioned tenant {tenant.id} in {env}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
