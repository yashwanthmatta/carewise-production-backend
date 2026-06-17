from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.db.session import get_db
from app.models.carewise import PasswordResetToken, User
from app.schemas.carewise import (
    LoginRequest,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    PasswordResetRequestOut,
    SignupRequest,
    TokenResponse,
)
from app.services.audit import write_audit

router = APIRouter()


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
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
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.email, user.role))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login.")
    write_audit(db, user.id, "", "user_login", "user", user.id, {})
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.email, user.role))


@router.post("/password-reset/request", response_model=PasswordResetRequestOut)
def request_password_reset(payload: PasswordResetRequestIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    reset_token = ""
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
        write_audit(db, user.id, "", "password_reset_requested", "user", user.id, {})
        db.commit()

    response_token = reset_token if reset_token and not settings.is_production else ""
    return PasswordResetRequestOut(
        status="ok",
        delivery_status="email_provider_not_configured",
        reset_token=response_token,
    )


@router.post("/password-reset/confirm", response_model=TokenResponse)
def confirm_password_reset(payload: PasswordResetConfirmIn, db: Session = Depends(get_db)):
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
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.email, user.role))


def token_is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < datetime.now(timezone.utc)
