import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.auth.dependencies import get_current_user
from app.auth.models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
    VerificationResendResponse,
    VerifyEmailConfirmRequest,
)
from app.auth.password_change_service import (
    CurrentPasswordIncorrectError,
    PasswordUnchangedError,
    password_change_service,
)
from app.auth.password_reset_service import ResetTokenInvalidError, password_reset_service
from app.auth.rate_limit import (
    email_verification_resend_limiter,
    login_rate_limiter,
    password_change_rate_limiter,
    password_reset_request_limiter,
)
from app.auth.security import create_access_token
from app.auth.service import EmailAlreadyRegisteredError, auth_service
from app.auth.verification_service import (
    VerificationTokenInvalidError,
    email_verification_service,
)
from app.core.config import settings
from app.database import crud
from app.database.database import get_db
from app.database.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Sprint 039 Production Readiness Defect Gate, Blocker 2 — the exact same
# message on every call, whether or not the account exists (the locked
# no-enumeration contract for this blocker).
_FORGOT_PASSWORD_MESSAGE = "If an account exists for that email, we've sent a reset link."


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
    token = create_access_token(
        subject=str(user.id), tenant_id=str(tenant.id), token_version=user.token_version
    )
    return TokenResponse(access_token=token, user=auth_service.build_user_out(db, user))


@router.post("/email/verify/resend", response_model=VerificationResendResponse)
def resend_verification_email(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Sprint 039 Production Readiness Defect Gate, Blocker 2 follow-up
    # (verification resend/token hotfix) — already_verified=True here is
    # not merely informational: it is the caller's only way to know that
    # nothing was actually queued, since this early return skips the
    # cooldown check and send_verification_email() entirely (there is
    # nothing to cool down or send for an account that no longer needs
    # verifying).
    if current_user.email_verified_at is not None:
        return VerificationResendResponse(
            message="Your email is already verified.", already_verified=True
        )
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
    return VerificationResendResponse(message="Verification email sent.", already_verified=False)


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
    token = create_access_token(
        subject=str(user.id), tenant_id=str(user.tenant_id), token_version=user.token_version
    )
    return TokenResponse(access_token=token, user=auth_service.build_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return auth_service.build_user_out(db, current_user)


@router.post("/password/forgot", response_model=MessageResponse)
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    started_at = time.monotonic()
    password_reset_request_limiter.check_and_record(
        data.email, cooldown_seconds=settings.password_reset_request_cooldown_seconds
    )

    # Looked up only to decide whether an audit event is logged — the
    # HTTP response (message and timing) is identical either way, so this
    # lookup itself creates no observable difference (see the response-
    # time floor below, which covers both the found and not-found paths
    # equally).
    target = crud.get_user_by_email(db, data.email)
    password_reset_service.request_reset(db, data.email)
    if target is not None:
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.PASSWORD_RESET_REQUESTED,
                title="Password reset requested",
                description=target.email,
            ),
            tenant_id=target.tenant_id,
        )

    # Sprint 039 Blocker 2's no-enumeration contract: pad to a constant
    # floor so a naturally-faster "no such user" path (skips the token
    # insert and email-send attempt) can't be distinguished from a real
    # one by response time. Only pads up, never truncates a slower call.
    elapsed = time.monotonic() - started_at
    remaining = settings.password_reset_response_floor_seconds - elapsed
    if remaining > 0:
        time.sleep(remaining)

    return MessageResponse(message=_FORGOT_PASSWORD_MESSAGE)


@router.post("/password/reset", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        user = password_reset_service.reset_password(db, data.token, data.new_password)
    except ResetTokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired.",
        )
    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.PASSWORD_CHANGED, title="Password changed", description=user.email
        ),
        tenant_id=user.tenant_id,
    )
    return MessageResponse(message="Your password has been reset. Please sign in again.")


@router.post("/password/change", response_model=TokenResponse)
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Changes the signed-in user's own password (see
    app/auth/password_change_service.py). Every other session is revoked;
    the response carries a fresh token so this one stays signed in."""
    limiter_key = str(current_user.id)
    password_change_rate_limiter.check(
        limiter_key,
        max_attempts=settings.password_change_max_attempts,
        window_seconds=settings.password_change_window_seconds,
    )
    try:
        user = password_change_service.change_password(
            db,
            current_user,
            current_password=data.current_password,
            new_password=data.new_password,
        )
    except CurrentPasswordIncorrectError:
        password_change_rate_limiter.record_failure(
            limiter_key, window_seconds=settings.password_change_window_seconds
        )
        # 400, not 401: the session is valid, and a 401 would sign the
        # client out.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your current password is incorrect.",
        )
    except PasswordUnchangedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose a new password that is different from your current one.",
        )
    password_change_rate_limiter.reset(limiter_key)
    activity_service.log(
        ActivityEventCreate(
            type=ActivityType.PASSWORD_CHANGED, title="Password changed", description=user.email
        ),
        tenant_id=user.tenant_id,
    )
    token = create_access_token(
        subject=str(user.id), tenant_id=str(user.tenant_id), token_version=user.token_version
    )
    return TokenResponse(access_token=token, user=auth_service.build_user_out(db, user))
