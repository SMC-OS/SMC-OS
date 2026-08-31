"""FollowUpService — Sprint 024 (docs/SPRINTS/sprint-024.md). Pure domain
service: takes an explicit `now`, does no I/O beyond the given `db`
session, prints nothing — fully unit-testable and reusable by both tests
and app/jobs/follow_up.py's CLI wrapper.

Locked to a single automation rule this sprint: Stale Enquiry Follow-up.
Candidates B (quote follow-up) and C (site visit reminder), evaluated and
deferred in the discovery doc, can reuse this same module/shape later.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.database import crud
from app.database.models import Project
from app.notifications.models import NotificationType
from app.projects.models import ProjectStatus

# Sprint 024 §3 — the only per-Project timestamp this schema has ever had
# (no separate "last touched" column exists or is being added). A plain
# constant, not configuration: the smallest coherent choice, trivially
# adjustable later without a schema change.
STALE_ENQUIRY_THRESHOLD = timedelta(days=7)


@dataclass
class FollowUpRunResult:
    examined: int = 0
    created: int = 0
    skipped_existing: int = 0
    skipped_not_due: int = 0
    skipped_no_recipient: int = 0


class FollowUpService:
    def run(self, db: Session, now: datetime) -> FollowUpRunResult:
        result = FollowUpRunResult()

        stale_enquiries = crud.list_projects_by_status(db, ProjectStatus.ENQUIRY.value)

        for project in stale_enquiries:
            result.examined += 1

            if project.created_at > now - STALE_ENQUIRY_THRESHOLD:
                result.skipped_not_due += 1
                continue

            recipient_id = self._resolve_recipient(db, project)
            if recipient_id is None:
                result.skipped_no_recipient += 1
                continue

            dedupe_key = f"stale_enquiry_follow_up:{project.id}"
            if crud.get_notification_by_dedupe_key(db, dedupe_key) is not None:
                result.skipped_existing += 1
                continue

            try:
                crud.create_notification(
                    db,
                    id=uuid.uuid4(),
                    tenant_id=project.tenant_id,
                    title="Enquiry needs follow-up",
                    message=f"{project.name} has had no progress since it was created.",
                    type=NotificationType.WARNING.value,
                    timestamp=now,
                    read=False,
                    recipient_user_id=recipient_id,
                    source_type="project",
                    source_id=project.id,
                    dedupe_key=dedupe_key,
                )
                result.created += 1
            except IntegrityError:
                # A concurrent run raced us to the same dedupe_key — the DB
                # unique constraint is the hard backstop the pre-check
                # above is defending in depth, not replacing (Sprint 024
                # §6). Roll back so this session stays usable for the next
                # Project in this same run (§8 — one Project's failure
                # must never affect another's already-committed result).
                db.rollback()
                result.skipped_existing += 1

        return result

    def _resolve_recipient(self, db: Session, project: Project) -> uuid.UUID | None:
        """Sprint 024 §5: assigned Staff/Owner first; else the tenant's
        earliest-created Owner; else None (skip, never crash)."""
        if project.assigned_user_id is not None:
            assignee = crud.get_user_by_id(db, project.assigned_user_id)
            if assignee is not None and assignee.tenant_id == project.tenant_id:
                return assignee.id

        tenant_users = crud.list_users_by_tenant(db, project.tenant_id)
        owners = [u for u in tenant_users if u.role == UserRole.OWNER.value]
        return owners[0].id if owners else None


follow_up_service = FollowUpService()
