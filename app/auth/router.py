from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.models import LoginRequest, SignupRequest, TokenResponse, UserOut
from app.auth.security import create_access_token
from app.auth.service import EmailAlreadyRegisteredError, auth_service
from app.database.database import get_db
from app.database.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    try:
        tenant, user = auth_service.signup(db, data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id))
    return TokenResponse(access_token=token, user=auth_service.build_user_out(db, user))


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, credentials.email, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(subject=str(user.id), tenant_id=str(user.tenant_id))
    return TokenResponse(access_token=token, user=auth_service.build_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return auth_service.build_user_out(db, current_user)
