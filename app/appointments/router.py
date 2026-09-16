import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.appointments.models import AppointmentCreate, AppointmentOut, AppointmentStatusUpdate
from app.appointments.service import (
    AppointmentTransitionError,
    ProjectNotFoundError,
    appointment_service,
)
from app.auth.dependencies import require_role, require_verified_email
from app.auth.models import UserRole
from app.database.database import get_db
from app.database.models import User

# No single path prefix — routes live under both /projects/{id}/appointments
# and /appointments/{id}/status, so each route below declares its own full
# path instead of sharing one prefix, the way every other module's router
# does. dependencies=[Depends(require_verified_email)] still applies auth to
# every route here, same convention as app/customers/router.py etc.
router = APIRouter(tags=["appointments"], dependencies=[Depends(require_verified_email)])


@router.post(
    "/projects/{project_id}/appointments",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_appointment(
    project_id: uuid.UUID,
    data: AppointmentCreate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return appointment_service.create(
            db, project_id, current_user.tenant_id, current_user.id, data
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("/projects/{project_id}/appointments", response_model=list[AppointmentOut])
def list_appointments(
    project_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return appointment_service.list_for_project(db, project_id, current_user.tenant_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/appointments/{appointment_id}/status", response_model=AppointmentOut)
def update_appointment_status(
    appointment_id: uuid.UUID,
    data: AppointmentStatusUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        appointment = appointment_service.transition_status(
            db, appointment_id, current_user.tenant_id, data.status
        )
    except AppointmentTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment cannot transition from its current status",
        )
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appointment
