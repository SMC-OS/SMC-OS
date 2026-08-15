"""Central application configuration.

Sprint 003 — the single pydantic-settings source of truth for every
environment-driven value: the database URL (previously read directly via
python-dotenv in app/database/database.py, see its docstring), JWT signing
config, and the seeded admin account's credentials. Reads from the repo
root .env, same file docker-compose.yml and the previous ad-hoc reads used.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://simo:simo@localhost:5432/simo_os"

    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    seed_admin_email: str = "owner@simo-os.local"
    seed_admin_password: str = "change-me-on-first-login"

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

    # AI Quotation Generator v1 — optional. The app runs fully normally with
    # both unset; app/quotes/ai_draft.py's AIDraftService only ever
    # constructs an OpenAI client lazily, on first real use, and only if
    # openai_api_key is set. Never required, never a startup dependency.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"


settings = Settings()
