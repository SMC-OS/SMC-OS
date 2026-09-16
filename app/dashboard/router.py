from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role
from app.auth.models import UserRole
from app.dashboard.models import CommandCentreResponse
from app.dashboard.service import build_command_centre
from app.database.database import get_db
from app.database.models import User

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_billing_access)]
)


@router.get("/command-centre", response_model=CommandCentreResponse)
def command_centre(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    return build_command_centre(db, current_user.tenant_id)
