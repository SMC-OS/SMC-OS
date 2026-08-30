"""AppointmentService — Sprint 022. Route-level code taking a
request-scoped session via get_db(), same pattern every business module in
this repo follows (ADR-019). See docs/SPRINTS/sprint-022.md's Locked
Contract.
"""

import uuid

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.appointments.models import AppointmentCreate, AppointmentTransitionTarget
from app.database import crud
from app.database.models import Appointment

_TERMINAL_STATUSES = {"completed", "cancelled"}


class ProjectNotFoundError(Exception):
    """Raised when the target Project doesn't resolve under the caller's
    own tenant — same tenant-scoped-lookup-hides-existence convention as
    every relationship check in this codebase (ADR-029)."""


class AppointmentTransitionError(Exception):
    """Raised when a status transition would leave a terminal appointment
    (completed/cancelled) for a *different* state — including the other
    terminal status or reverting to scheduled. Decision 3
    (sprint-022.md): a repeat call with the *same* terminal status the
    appointment already has is NOT an error — see
    AppointmentService.transition_status's idempotent early return."""


class AppointmentService:
    def create(
        self,
        db: Session,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        data: AppointmentCreate,
    ) -> Appointment:
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        try:
            appointment = crud.create_appointment(
                db,
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                project_id=project_id,
                created_by_user_id=created_by_user_id,
                scheduled_at=data.scheduled_at,
                notes=data.notes,
                commit=False,
            )

            # Sprint 021's caller-owned-transaction convention: this write
            # and the one above share the same not-yet-committed `db`.
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.SITE_VISIT_SCHEDULED,
                    title="Site visit scheduled",
                    description=f"Project {project_id} site visit {appointment.id} scheduled",
                ),
                tenant_id=tenant_id,
                db=db,
            )

            db.commit()
        except Exception:
            db.rollback()
            raise

        return appointment

    def list_for_project(
        self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> list[Appointment]:
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return crud.list_appointments_by_project(db, tenant_id, project_id)

    def transition_status(
        self,
        db: Session,
        appointment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        target: AppointmentTransitionTarget,
    ) -> Appointment | None:
        appointment = crud.get_appointment_by_id(db, appointment_id, tenant_id)
        if appointment is None:
            return None

        target_value = target.value

        if appointment.status in _TERMINAL_STATUSES:
            if appointment.status == target_value:
                # Decision 3 — idempotent retry: same target as the
                # already-terminal status, no mutation, no new activity.
                return appointment
            raise AppointmentTransitionError(appointment.status)

        activity_type = (
            ActivityType.SITE_VISIT_COMPLETED
            if target_value == "completed"
            else ActivityType.SITE_VISIT_CANCELLED
        )
        title = "Site visit completed" if target_value == "completed" else "Site visit cancelled"

        try:
            updated = crud.update_appointment_status(
                db, appointment_id, tenant_id, target_value, commit=False
            )
            activity_service.log(
                ActivityEventCreate(
                    type=activity_type,
                    title=title,
                    description=f"Site visit {appointment_id} {target_value}",
                ),
                tenant_id=tenant_id,
                db=db,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        return updated


appointment_service = AppointmentService()
