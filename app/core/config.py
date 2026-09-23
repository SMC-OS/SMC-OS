"""Central application configuration.

Sprint 003 — the single pydantic-settings source of truth for every
environment-driven value: the database URL (previously read directly via
python-dotenv in app/database/database.py, see its docstring), JWT signing
config, and the seeded admin account's credentials. Reads from the repo
root .env, same file docker-compose.yml and the previous ad-hoc reads used.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
_DEVELOPMENT_DATABASE_URL = "postgresql+psycopg://simo:simo@localhost:5432/simo_os"
_DEVELOPMENT_JWT_SECRET = "dev-only-insecure-secret-change-me"
_DEVELOPMENT_SEED_EMAIL = "owner@geocore.local"
# Sprint 034 (Phase 2) — the pre-rebrand default. Still rejected in
# production: a deployment that kept the old value in its environment
# through the rename must not silently start passing this guard just
# because the constant above changed.
_LEGACY_DEVELOPMENT_SEED_EMAILS = frozenset({"owner@simo-os.local"})
_DEVELOPMENT_SEED_PASSWORD = "change-me-on-first-login"
_DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Sprint 041 — apps/marketing's dev server (`next dev --port 3001`),
    # now calling GET /billing/plans and POST /demo-requests directly
    # from the browser.
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]


class AppEnvironment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    seed_data_enabled: bool = True
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(_DEVELOPMENT_CORS_ORIGINS)
    )
    readiness_timeout_seconds: float = 2.0

    database_url: str = _DEVELOPMENT_DATABASE_URL

    jwt_secret_key: str = _DEVELOPMENT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Sprint 026 (docs/SPRINTS/sprint-026.md Contract B) — POST /auth/login
    # brute-force throttle: this many failed attempts per email within this
    # many seconds before further attempts are rejected with 429. Not a
    # secret; safe defaults, no production-only validation needed.
    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: float = 60.0

    seed_admin_email: str = _DEVELOPMENT_SEED_EMAIL
    seed_admin_password: str = _DEVELOPMENT_SEED_PASSWORD

    # Sprint 011 — staff invitation links expire this many days after
    # creation. Computed Python-side at invitation-creation time, same
    # style as the JWT `exp` claim below (not a DB server_default).
    invitation_expire_days: int = 7

    # Sprint 013 — customer portal links expire this many days after
    # creation, computed the same Python-side way as invitation_expire_days.
    # Deliberately much longer: an invitation is a one-time "join now"
    # prompt, a portal link is meant to stay usable for roughly the
    # duration of a job so a customer can keep checking status.
    portal_link_expire_days: int = 90

    # Sprint 016 (docs/DECISIONS.md ADR-032) — local disk directory for
    # uploaded client-portal documents. Created on startup if missing.
    # Deliberately NOT S3/object storage this sprint — accepted limitation:
    # does not survive a redeploy to a different host, does not scale past
    # one running instance. See ADR-032.
    upload_dir: str = "./uploads"

    # AI Provider selection — optional. The app runs fully normally with
    # no provider configured; all AI features report themselves unavailable
    # honestly rather than falling back to a limited builtin. Valid values:
    # "openai", "gemini". Default: "openai" (preserves existing behaviour
    # when OPENAI_API_KEY is set).
    ai_provider: str = "openai"

    # OpenAI — optional. Used when AI_PROVIDER=openai.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Google Gemini — optional. Used when AI_PROVIDER=gemini. Model is
    # configurable via GEMINI_MODEL; default is a verified current Flash
    # model, but staging/production must set the exact verified model
    # explicitly rather than relying on this default.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Sprint 032 (Workstream A) — Stripe billing. All optional; the app
    # runs fully normally with none configured (app/billing/router.py
    # returns 503 for anything that needs Stripe, same "ships dark until
    # configured" pattern as openai_api_key above). Price IDs are read
    # from config, never hardcoded (see app/billing/plans.py).
    #
    # Sprint 039 Production Readiness Defect Gate, Blocker 3 — widened
    # from 2 self-service plans to 4 (Starter/Team added; Pro/Business
    # keep their Sprint 032 setting names but must be repointed to NEW
    # Stripe Price objects at the new locked amounts — see
    # docs/SPRINTS/sprint-039.md §14.3 for the exact owner-gate spec of
    # what to create in Stripe and which of these 8 variables each one
    # fills). No value here is a real Stripe id; none is fabricated.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter_monthly: str | None = None
    stripe_price_starter_annual: str | None = None
    stripe_price_team_monthly: str | None = None
    stripe_price_team_annual: str | None = None
    stripe_price_pro_monthly: str | None = None
    stripe_price_pro_annual: str | None = None
    stripe_price_business_monthly: str | None = None
    stripe_price_business_annual: str | None = None
    # Where Stripe Checkout/Customer Portal redirect back to after
    # completion/cancellation — the deployed frontend's own origin.
    frontend_base_url: str = "http://localhost:3000"

    # Sprint 038 — transactional email (Resend). Same "ships dark until
    # configured" pattern as openai_api_key/stripe_secret_key above: the
    # app runs fully normally with both unset, and
    # app/communications/provider.py's ResendEmailProvider only ever
    # constructs its HTTP client lazily, on first real send attempt.
    # DeliveryService returns a truthful "unavailable" result rather than
    # a fake success when unset — nothing ever claims an email was sent
    # without a real provider-accepted send. Sends from a dedicated
    # subdomain (never the apex, which carries this domain's Microsoft 365
    # mail — see docs/DNS_GEOCORE_ONE.md) so DNS for it is entirely
    # additive; no existing mail record is ever touched.
    resend_api_key: str | None = None
    resend_webhook_secret: str | None = None
    email_sending_domain: str = "send.geocore.one"

    # Sprint 039 Production Readiness Defect Gate, Blocker 1 — email
    # verification. Tokens sent through app/communications' DeliveryService
    # (Resend), same "ships dark until configured" pattern as everything
    # else in this section: with no resend_api_key set, DeliveryService
    # truthfully records the send as unavailable rather than blocking
    # signup or fabricating success.
    email_verification_token_expire_hours: int = 24
    email_verification_resend_cooldown_seconds: float = 60.0
    # A fixed instant, not "now" at request time — computed once, at the
    # moment this migration/feature is deployed, and never moved
    # afterwards (docs/SPRINTS/sprint-039.md's locked contract for this
    # blocker). Every user created before this timestamp is exempt from
    # verification enforcement for legacy_verification_grace_days from
    # this same fixed instant — see app/auth/dependencies.py's
    # require_verified_email(). Deliberately a Settings field (not a
    # bare module constant) so tests can override it to exercise the
    # grace-period boundary without waiting on a real clock.
    identity_security_cutover_at: datetime = datetime(2026, 9, 11, tzinfo=timezone.utc)
    legacy_verification_grace_days: int = 30

    # Sprint 039 Production Readiness Defect Gate, Blocker 2 — password
    # recovery. Deliberately much shorter than Blocker 1's 24h email
    # verification token: a reset token grants immediate account
    # takeover if intercepted, so a narrow window matters more than
    # convenience here.
    password_reset_token_expire_hours: int = 1
    password_reset_request_cooldown_seconds: float = 60.0
    # Sprint 039 Blocker 2 — POST /auth/password/forgot always takes at
    # least this long to respond, win or lose (padded in the router),
    # so a timing side-channel can't distinguish "email exists" from
    # "email doesn't exist" the way a naturally-faster not-found path
    # otherwise would. Not a secret; safe to be a plain setting.
    password_reset_response_floor_seconds: float = 0.3

    # Sprint 041 — public POST /demo-requests (GeoCore Premium OS Plan
    # 02). Same CooldownLimiter shape/reasoning as the two settings above.
    demo_request_cooldown_seconds: float = 60.0

    # Phase B — GeoCore's own sales workspace. When set to a real tenant
    # id, every public demo request also becomes a customer record (plus
    # an activity entry) in that workspace's existing CRM, its Owners are
    # emailed, and the prospect gets a confirmation. Unset (the default),
    # requests are still stored but nobody is emailed — no address or
    # workspace is ever guessed.
    platform_sales_tenant_id: str | None = None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def normalize_cors_allowed_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            origins = value.split(",")
        elif isinstance(value, list):
            origins = value
        else:
            raise ValueError("CORS_ALLOWED_ORIGINS must be a comma-separated string or list")

        normalized = []
        for origin in origins:
            if not isinstance(origin, str) or not origin.strip():
                raise ValueError("CORS_ALLOWED_ORIGINS must not contain empty entries")
            normalized.append(origin.strip())
        return normalized

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "Settings":
        if self.readiness_timeout_seconds <= 0 or self.readiness_timeout_seconds > 2:
            raise ValueError("READINESS_TIMEOUT_SECONDS must be greater than 0 and no greater than 2")

        if self.app_env is not AppEnvironment.PRODUCTION:
            return self

        self._validate_production_secrets()
        self._validate_production_cors()
        self._validate_production_storage_and_database()
        return self

    def _validate_production_secrets(self) -> None:
        normalized_jwt_secret = self.jwt_secret_key.strip()
        normalized_seed_email = self.seed_admin_email.strip()
        normalized_seed_password = self.seed_admin_password.strip()
        if (
            not normalized_jwt_secret
            or len(normalized_jwt_secret) < 32
            or normalized_jwt_secret == _DEVELOPMENT_JWT_SECRET
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be non-blank, at least 32 characters, and not the development default"
            )
        if (
            not normalized_seed_email
            or normalized_seed_email == _DEVELOPMENT_SEED_EMAIL
            or normalized_seed_email in _LEGACY_DEVELOPMENT_SEED_EMAILS
        ):
            raise ValueError("SEED_ADMIN_EMAIL must be non-blank and not the development default")
        if (
            not normalized_seed_password
            or len(normalized_seed_password) < 12
            or normalized_seed_password == _DEVELOPMENT_SEED_PASSWORD
        ):
            raise ValueError(
                "SEED_ADMIN_PASSWORD must be non-blank, at least 12 characters, and not the development default"
            )
        if self.seed_data_enabled:
            raise ValueError("SEED_DATA_ENABLED must be false in production")

    def _validate_production_cors(self) -> None:
        if not self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one origin in production")

        for origin in self.cors_allowed_origins:
            if origin == "*":
                raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*'")
            try:
                parsed = urlsplit(origin)
                port = parsed.port
            except ValueError:
                raise ValueError("CORS_ALLOWED_ORIGINS entries must be valid origins") from None
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or (port is not None and not 1 <= port <= 65535)
            ):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS entries must be HTTPS origins with scheme and host only"
                )

    def _validate_production_storage_and_database(self) -> None:
        if not self.upload_dir.strip() or not (
            Path(self.upload_dir).is_absolute() or PurePosixPath(self.upload_dir).is_absolute()
        ):
            raise ValueError("UPLOAD_DIR must be an absolute path in production")

        if not self.database_url.strip() or self.database_url == _DEVELOPMENT_DATABASE_URL:
            raise ValueError("DATABASE_URL must not use the development database in production")
        try:
            make_url(self.database_url)
        except Exception:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy database URL") from None

settings = Settings()
