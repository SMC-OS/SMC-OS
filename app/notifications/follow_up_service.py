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
from app.notifications import preferences
from app.database.models import Project
from app.notifications.models import NotificationType
from app.projects import pipeline as project_pipeline

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

        # Sprint 039 — selected by the stage's trade-neutral *role*, not
        # by a literal "enquiry" key: this job runs across every tenant at
        # once (it has no caller and no tenant of its own), and different
        # tenants call their first stage different things.
        stale_enquiries = crud.list_projects_in_role(db, project_pipeline.LEAD)

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
                # Sprint 039 (Workstream B) — through the preference gate
                # rather than straight to crud, so a user who has muted
                # project activity genuinely stops getting these rather
                # than having them hidden client-side.
                created = preferences.notify(
                    db,
                    tenant_id=project.tenant_id,
                    recipient_user_id=recipient_id,
                    category="project_activity",
                    title="Enquiry needs follow-up",
                    message=f"{project.name} has had no progress since it was created.",
                    dedupe_key=dedupe_key,
                    notification_type=NotificationType.WARNING.value,
                    source_type="project",
                    source_id=project.id,
                    now=now,
                )
                if created is None:
                    # Muted, or a concurrent run won the dedupe race.
                    # Counted as "already existed" rather than "created",
                    # which is what the caller's own summary means by it:
                    # nothing new was written.
                    result.skipped_existing += 1
                    continue
                preferences.send_email_copy(
                    db,
                    tenant_id=project.tenant_id,
                    recipient_user_id=recipient_id,
                    category="project_activity",
                    headline="Enquiry needs follow-up",
                    detail=f"{project.name} has had no progress since it was created.",
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
