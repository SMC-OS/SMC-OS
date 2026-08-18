"""Central application configuration.

Sprint 003 — the single pydantic-settings source of truth for every
environment-driven value: the database URL (previously read directly via
python-dotenv in app/database/database.py, see its docstring), JWT signing
config, and the seeded admin account's credentials. Reads from the repo
root .env, same file docker-compose.yml and the previous ad-hoc reads used.
"""

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
_DEVELOPMENT_SEED_EMAIL = "owner@simo-os.local"
_DEVELOPMENT_SEED_PASSWORD = "change-me-on-first-login"
_DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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

    # AI Quotation Generator v1 — optional. The app runs fully normally with
    # both unset; app/quotes/ai_draft.py's AIDraftService only ever
    # constructs an OpenAI client lazily, on first real use, and only if
    # openai_api_key is set. Never required, never a startup dependency.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

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
        if not normalized_seed_email or normalized_seed_email == _DEVELOPMENT_SEED_EMAIL:
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
