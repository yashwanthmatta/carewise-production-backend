import hashlib
import hmac
import json
import time
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
from app.core.crypto import decrypt_field, encrypt_field
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
    TwoFactorCodeIn,
    TwoFactorEnabledOut,
    TwoFactorLoginIn,
    TwoFactorSetupOut,
    UserSessionOut,
)
from app.services import email_delivery, totp
from app.services.audit import write_audit
from app.services.rate_limit import check_rate_limit

router = APIRouter()


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "auth_signup", payload.email)
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.")
    # Anyone can create a patient account; clinician and admin roles come only from
    # the staff list, because they can see other people's reports.
    if payload.role != "patient" and settings.staff_role_for(payload.email) != payload.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clinician and admin accounts are set up by the FollowThrough Health team.",
        )
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
    check_rate_limit(db, request, "auth_login_account", payload.email, max_attempts=20, window_seconds=900, by_ip=False)
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login.")
    if user.totp_enabled:
        db.commit()
        return TokenResponse(access_token="", two_factor_required=True, challenge=make_challenge(user.id))
    write_audit(db, user.id, "", "user_login", "user", user.id, {})
    token_response = issue_token_pair(db, user)
    db.commit()
    return token_response


# ----- Two-step sign-in -----------------------------------------------------------
CHALLENGE_SECONDS = 300


def make_challenge(user_id: str) -> str:
    expires = int(time.time()) + CHALLENGE_SECONDS
    body = f"{user_id}.{expires}"
    signature = hmac.new(settings.jwt_secret.encode(), f"2fa:{body}".encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_challenge(challenge: str) -> str | None:
    try:
        user_id, expires, signature = challenge.rsplit(".", 2)
    except ValueError:
        return None
    expected = hmac.new(settings.jwt_secret.encode(), f"2fa:{user_id}.{expires}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature) or not expires.isdigit() or int(expires) < time.time():
        return None
    return user_id


def use_second_factor(user: User, code: str) -> bool:
    """Accept a fresh authenticator code, or a one-time recovery code (which is then spent)."""
    secret = decrypt_field(user.encrypted_totp_secret) if user.encrypted_totp_secret else ""
    step = totp.matching_step(secret, code) if secret else None
    if step is not None and step > (user.totp_last_step or 0):
        user.totp_last_step = step
        return True
    hashes = json.loads(user.recovery_code_hashes or "[]")
    wanted = totp.hash_recovery_code(code)
    if wanted in hashes:
        hashes.remove(wanted)
        user.recovery_code_hashes = json.dumps(hashes)
        return True
    return False


@router.post("/login/two-factor", response_model=TokenResponse)
def login_two_factor(payload: TwoFactorLoginIn, request: Request, db: Session = Depends(get_db)):
    user_id = read_challenge(payload.challenge)
    check_rate_limit(db, request, "auth_two_factor", user_id or "unknown")
    if user_id:
        # Six-digit codes: at most 10 tries per account every 15 minutes, from anywhere.
        check_rate_limit(db, request, "auth_two_factor_account", user_id, max_attempts=10, window_seconds=900, by_ip=False)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again.")
    if not use_second_factor(user, payload.code):
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That code didn't work.")
    write_audit(db, user.id, "", "user_login", "user", user.id, {"two_factor": True})
    token_response = issue_token_pair(db, user)
    db.commit()
    return token_response


@router.post("/two-factor/setup", response_model=TwoFactorSetupOut)
def two_factor_setup(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.get(User, user.user_id)
    if account.totp_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is already on.")
    secret = totp.new_secret()
    account.encrypted_totp_secret = encrypt_field(secret)
    account.totp_last_step = 0
    db.commit()
    return TwoFactorSetupOut(secret=secret, otpauth_url=totp.otpauth_url(secret, account.email))


@router.post("/two-factor/enable", response_model=TwoFactorEnabledOut)
def two_factor_enable(
    payload: TwoFactorCodeIn, request: Request, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    check_rate_limit(db, request, "auth_two_factor", user.user_id)
    account = db.get(User, user.user_id)
    secret = decrypt_field(account.encrypted_totp_secret) if account.encrypted_totp_secret else ""
    step = totp.matching_step(secret, payload.code) if secret else None
    if account.totp_enabled or step is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That code didn't work. Check the time on your phone and try again.")
    codes = totp.new_recovery_codes()
    account.totp_enabled = 1
    account.totp_last_step = step
    account.recovery_code_hashes = json.dumps([totp.hash_recovery_code(code) for code in codes])
    revoke_sessions(db, user.user_id)
    write_audit(db, user.user_id, "", "two_factor_enabled", "user", user.user_id, {})
    db.commit()
    return TwoFactorEnabledOut(enabled=True, recovery_codes=codes)


@router.post("/two-factor/disable", response_model=TwoFactorEnabledOut)
def two_factor_disable(
    payload: TwoFactorCodeIn, request: Request, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    check_rate_limit(db, request, "auth_two_factor", user.user_id)
    account = db.get(User, user.user_id)
    if not account.totp_enabled or not use_second_factor(account, payload.code):
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That code didn't work.")
    account.totp_enabled = 0
    account.encrypted_totp_secret = ""
    account.recovery_code_hashes = ""
    revoke_sessions(db, user.user_id)
    write_audit(db, user.user_id, "", "two_factor_disabled", "user", user.user_id, {})
    db.commit()
    return TwoFactorEnabledOut(enabled=False)


@router.get("/me", response_model=UserSessionOut)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.get(User, user.user_id)
    return UserSessionOut(
        id=user.user_id,
        email=user.email,
        role=user.role,
        email_verified=account.email_verified == "true" if account else False,
        two_factor_enabled=bool(account.totp_enabled) if account else False,
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
    revoke_sessions(db, user.id)
    write_audit(db, user.id, "", "password_reset_completed", "user", user.id, {})
    if user.totp_enabled:
        db.commit()
        return TokenResponse(access_token="", two_factor_required=True, challenge=make_challenge(user.id))
    token_response = issue_token_pair(db, user)
    db.commit()
    return token_response


def revoke_sessions(db: Session, user_id: str) -> None:
    # After a password or sign-in change, every device has to sign in again.
    for record in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.status == "active")):
        record.status = "revoked"


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
