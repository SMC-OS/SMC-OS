"""Sprint 015 (docs/DECISIONS.md ADR-031) — team management: list a
tenant's users, deactivate a Staff member's access. See app/users/service.py
for the self-deactivation guard and app/auth/dependencies.py's
get_current_user for how is_active is enforced on every later request.

Named TeamMemberOut, not UserOut, to avoid colliding with
app.auth.models.UserOut (the /auth/me response shape) — different response,
different route family.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str | None = None
    is_active: bool
    created_at: datetime
