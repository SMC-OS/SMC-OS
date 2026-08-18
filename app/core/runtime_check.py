"""Read-only runtime configuration preflight command."""

import json
import sys

from pydantic import ValidationError
from sqlalchemy.engine import make_url


def _validation_messages(error: ValidationError) -> list[str]:
    """Return rule messages without Pydantic inputs, which may be secrets."""
    return [str(item["msg"]) for item in error.errors()]


def main() -> int:
    """Validate environment settings and print a sanitized configuration summary."""
    try:
        # Import lazily: config.py preserves its existing eager `settings` singleton,
        # whose production validation must be rendered safely by this command.
        from app.core.config import Settings

        settings = Settings()
    except ValidationError as error:
        for message in _validation_messages(error):
            print(f"Runtime configuration is invalid: {message}", file=sys.stderr)
        return 1

    database = make_url(settings.database_url)
    summary = {
        "app_env": settings.app_env.value,
        "cors_origin_count": len(settings.cors_allowed_origins),
        "database_host": database.host,
        "database_name": database.database,
        "seed_data_enabled": settings.seed_data_enabled,
        "upload_dir": settings.upload_dir,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
