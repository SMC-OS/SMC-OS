import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role
from app.auth.models import UserRole
from app.database.database import get_db
from app.database.models import User
from app.financials.models import (
    ProjectCostEntryIn,
    ProjectCostEntryOut,
    ProjectCostEntryUpdate,
    ProjectFinancialSummary,
)
from app.financials.service import CostEntryNotFoundError, ProjectNotFoundError, financials_service

# Same no-single-prefix convention as app/appointments/router.py — every
# route lives under /projects/{project_id}/..., stated in full per route.
# Read and write are both OWNER+STAFF, matching the existing precedent
# for quotes/projects (require_billing_access alone gates GET; no
# codebase precedent hides commercial figures from Staff — see ADR-048).
router = APIRouter(tags=["financials"], dependencies=[Depends(require_billing_access)])


@router.get("/projects/{project_id}/financials/summary", response_model=ProjectFinancialSummary)
def get_financial_summary(
    project_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return financials_service.get_summary(db, project_id, current_user.tenant_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("/projects/{project_id}/costs", response_model=list[ProjectCostEntryOut])
def list_costs(
    project_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return financials_service.list_cost_entries(db, project_id, current_user.tenant_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.post(
    "/projects/{project_id}/costs", response_model=ProjectCostEntryOut, status_code=status.HTTP_201_CREATED
)
def create_cost(
    project_id: uuid.UUID,
    data: ProjectCostEntryIn,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return financials_service.create_cost_entry(
            db, project_id, current_user.tenant_id, current_user.id, data
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/projects/{project_id}/costs/{cost_entry_id}", response_model=ProjectCostEntryOut)
def update_cost(
    project_id: uuid.UUID,
    cost_entry_id: uuid.UUID,
    data: ProjectCostEntryUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        return financials_service.update_cost_entry(
            db, project_id, cost_entry_id, current_user.tenant_id, data
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except CostEntryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost entry not found")


@router.delete("/projects/{project_id}/costs/{cost_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cost(
    project_id: uuid.UUID,
    cost_entry_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    try:
        financials_service.delete_cost_entry(db, project_id, cost_entry_id, current_user.tenant_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except CostEntryNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost entry not found")
