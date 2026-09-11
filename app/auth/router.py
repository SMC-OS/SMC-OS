from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.dependencies import get_current_user
from app.auth.models import (
    LoginRequest,
    MessageResponse,
    SignupRequest,
    TokenResponse,
    UserOut,
    VerifyEmailConfirmRequest,
)
from app.auth.rate_limit import email_verification_resend_limiter, login_rate_limiter
from app.auth.security import create_access_token
from app.auth.service import EmailAlreadyRegisteredError, auth_service
from app.auth.verification_service import (
    VerificationTokenInvalidError,
    email_verification_service,
)
from app.core.config import settings
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
    email_verification_service.send_verification_email(db, user)
    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.EMAIL_VERIFICATION_REQUESTED,
            title="Verification email sent",
            description=user.email,
        ),
        tenant_id=tenant.id,
    )
    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id))
    return TokenResponse(access_token=token, user=auth_service.build_user_out(db, user))


@router.post("/email/verify/resend", response_model=MessageResponse)
def resend_verification_email(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.email_verified_at is not None:
        return MessageResponse(message="Your email is already verified.")
    email_verification_resend_limiter.check_and_record(
        str(current_user.id),
        cooldown_seconds=settings.email_verification_resend_cooldown_seconds,
    )
    email_verification_service.send_verification_email(db, current_user)
    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.EMAIL_VERIFICATION_REQUESTED,
            title="Verification email re-sent",
            description=current_user.email,
        ),
        tenant_id=current_user.tenant_id,
    )
    return MessageResponse(message="Verification email sent.")


@router.post("/email/verify/confirm", response_model=MessageResponse)
def confirm_email_verification(data: VerifyEmailConfirmRequest, db: Session = Depends(get_db)):
    try:
        user = email_verification_service.verify(db, data.token)
    except VerificationTokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired.",
        )
    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.EMAIL_VERIFIED, title="Email verified", description=user.email
        ),
        tenant_id=user.tenant_id,
    )
    return MessageResponse(message="Email verified.")


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    login_rate_limiter.check(
        credentials.email,
        max_attempts=settings.login_rate_limit_max_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    user = auth_service.authenticate(db, credentials.email, credentials.password)
    if user is None:
        login_rate_limiter.record_failure(
            credentials.email, window_seconds=settings.login_rate_limit_window_seconds
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    login_rate_limiter.reset(credentials.email)
    token = create_access_token(subject=str(user.id), tenant_id=str(user.tenant_id))
    return TokenResponse(access_token=token, user=auth_service.build_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return auth_service.build_user_out(db, current_user)
