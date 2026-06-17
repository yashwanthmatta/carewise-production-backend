from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    CurrentUser,
    create_access_token,
    create_email_verification_token,
    create_refresh_token,
    create_reset_token,
    get_current_user,
    hash_email_verification_token,
    hash_password,
    hash_refresh_token,
    hash_reset_token,
    verify_password,
)
from app.db.session import get_db
from app.models.carewise import EmailVerificationToken, PasswordResetToken, RefreshToken, User
from app.schemas.carewise import (
    EmailVerificationConfirmIn,
    EmailVerificationRequestOut,
    LoginRequest,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    PasswordResetRequestOut,
    RefreshTokenIn,
    SignupRequest,
    TokenResponse,
    UserSessionOut,
)
from app.services import email_delivery
from app.services.audit import write_audit
from app.services.rate_limit import check_rate_limit

router = APIRouter()


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "auth_signup", payload.email)
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()
    write_audit(db, user.id, "", "user_created", "user", user.id, {"role": user.role})
    issue_email_verification(db, user)
    token_response = issue_token_pair(db, user)
    db.commit()
    return token_response


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "auth_login", payload.email)
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login.")
    write_audit(db, user.id, "", "user_login", "user", user.id, {})
    token_response = issue_token_pair(db, user)
    db.commit()
    return token_response


@router.get("/me", response_model=UserSessionOut)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.get(User, user.user_id)
    return UserSessionOut(
        id=user.user_id,
        email=user.email,
        role=user.role,
        email_verified=account.email_verified == "true" if account else False,
    )


@router.post("/email-verification/request", response_model=EmailVerificationRequestOut)
def request_email_verification(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.get(User, user.user_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authentication token.")
    if account.email_verified == "true":
        return EmailVerificationRequestOut(status="ok", delivery_status="already_verified")
    verification_token, _ = issue_email_verification(db, account)
    db.commit()
    response_token = verification_token if verification_token and not settings.is_production else ""
    return EmailVerificationRequestOut(
        status="ok",
        delivery_status="email_queued" if settings.email_delivery_enabled else "email_provider_not_configured",
        verification_token=response_token,
    )


@router.post("/email-verification/confirm", response_model=UserSessionOut)
def confirm_email_verification(payload: EmailVerificationConfirmIn, db: Session = Depends(get_db)):
    verification_record = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_email_verification_token(payload.token),
            EmailVerificationToken.status == "active",
            EmailVerificationToken.used_at.is_(None),
        )
    )
    if verification_record is None or token_is_expired(verification_record.expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")
    account = db.get(User, verification_record.user_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")
    account.email_verified = "true"
    verification_record.status = "used"
    verification_record.used_at = datetime.now(timezone.utc)
    write_audit(db, account.id, "", "email_verified", "user", account.id, {})
    db.commit()
    return UserSessionOut(id=account.id, email=account.email, role=account.role, email_verified=True)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshTokenIn, db: Session = Depends(get_db)):
    refresh_record = active_refresh_token(db, payload.refresh_token)
    if refresh_record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.")
    user = db.get(User, refresh_record.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.")
    refresh_record.status = "used"
    refresh_record.used_at = datetime.now(timezone.utc)
    token_response = issue_token_pair(db, user)
    write_audit(db, user.id, "", "refresh_token_rotated", "user", user.id, {})
    db.commit()
    return token_response


@router.post("/logout")
def logout(payload: RefreshTokenIn, db: Session = Depends(get_db)):
    refresh_record = active_refresh_token(db, payload.refresh_token)
    if refresh_record is not None:
        refresh_record.status = "revoked"
        refresh_record.used_at = datetime.now(timezone.utc)
        write_audit(db, refresh_record.user_id, "", "refresh_token_revoked", "user", refresh_record.user_id, {})
        db.commit()
    return {"status": "ok"}


@router.post("/password-reset/request", response_model=PasswordResetRequestOut)
def request_password_reset(payload: PasswordResetRequestIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "password_reset_request", payload.email)
    user = db.scalar(select(User).where(User.email == payload.email))
    reset_token = ""
    public_delivery_status = "email_queued" if settings.email_delivery_enabled else "email_provider_not_configured"
    audit_delivery_status = public_delivery_status
    if user is not None:
        reset_token = create_reset_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_reset_token(reset_token),
                status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_minutes),
            )
        )
        if settings.email_delivery_enabled:
            try:
                email_delivery.send_password_reset_email(user.email, reset_token)
                audit_delivery_status = "email_sent"
            except Exception:
                audit_delivery_status = "email_failed"
        write_audit(
            db,
            user.id,
            "",
            "password_reset_requested",
            "user",
            user.id,
            {"delivery_status": audit_delivery_status},
        )
        db.commit()

    response_token = reset_token if reset_token and not settings.is_production else ""
    return PasswordResetRequestOut(
        status="ok",
        delivery_status=public_delivery_status,
        reset_token=response_token,
    )


@router.post("/password-reset/confirm", response_model=TokenResponse)
def confirm_password_reset(payload: PasswordResetConfirmIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "password_reset_confirm")
    token_hash = hash_reset_token(payload.token)
    reset_record = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.status == "active",
            PasswordResetToken.used_at.is_(None),
        )
    )
    if reset_record is None or token_is_expired(reset_record.expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    user = db.get(User, reset_record.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    user.password_hash = hash_password(payload.new_password)
    reset_record.status = "used"
    reset_record.used_at = datetime.now(timezone.utc)
    write_audit(db, user.id, "", "password_reset_completed", "user", user.id, {})
    token_response = issue_token_pair(db, user)
    db.commit()
    return token_response


def token_is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < datetime.now(timezone.utc)


def issue_token_pair(db: Session, user: User) -> TokenResponse:
    refresh_token = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        )
    )
    return TokenResponse(
        access_token=create_access_token(user.id, user.email, user.role),
        refresh_token=refresh_token,
    )


def issue_email_verification(db: Session, user: User) -> tuple[str, str]:
    verification_token = create_email_verification_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_email_verification_token(verification_token),
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.email_verification_token_minutes),
        )
    )
    delivery_status = "email_provider_not_configured"
    if settings.email_delivery_enabled:
        try:
            email_delivery.send_email_verification(user.email, verification_token)
            delivery_status = "email_sent"
        except Exception:
            delivery_status = "email_failed"
    write_audit(db, user.id, "", "email_verification_requested", "user", user.id, {"delivery_status": delivery_status})
    return verification_token, delivery_status


def active_refresh_token(db: Session, refresh_token: str) -> RefreshToken | None:
    refresh_record = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token),
            RefreshToken.status == "active",
            RefreshToken.used_at.is_(None),
        )
    )
    if refresh_record is None or token_is_expired(refresh_record.expires_at):
        return None
    return refresh_record
