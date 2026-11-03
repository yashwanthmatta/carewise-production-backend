"""Continue with Google, Apple or Microsoft, and the account's list of sign-in methods.

Flow (website and app):
1. The browser makes a random secret, keeps it, and calls /start with its SHA-256 hash.
2. It goes to the provider's page. The provider returns to /callback here.
3. /callback checks the state (single use, 10 minutes), trades the code for an ID token and
   verifies it. It changes nothing yet: it sends the browser back with a one-time code in the
   URL fragment (never a token, never health data).
4. The browser posts that code with its secret to /exchange. Only then is the account signed
   in, created or linked. A link sent to someone else cannot finish in their browser.

Accounts are matched only by the provider's stable subject id. An email address alone never
joins two accounts: if the email already has an account, the person is asked to sign in to
that account first and connect the provider from Account.
"""

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import issue_token_pair, make_challenge
from app.core.config import settings
from app.core.security import CurrentUser, get_current_user, verify_password
from app.db.session import get_db
from app.models.carewise import AuthFlowToken, User, UserIdentity
from app.schemas.carewise import TokenResponse
from app.services import oidc
from app.services.audit import write_audit
from app.services.rate_limit import check_rate_limit

router = APIRouter()

STATE_MINUTES = 10
HANDOFF_SECONDS = 120
ProviderName = Literal["google", "apple", "microsoft"]


class StartIn(BaseModel):
    platform: Literal["web", "app"] = "web"
    # SHA-256 (hex) of a random secret the browser keeps until /exchange.
    binding: str = Field(pattern=r"^[0-9a-f]{64}$")


class StartOut(BaseModel):
    authorization_url: str


class ExchangeIn(BaseModel):
    code: str = Field(min_length=20, max_length=200)
    secret: str = Field(min_length=32, max_length=200)


class ExchangeOut(TokenResponse):
    linked: str = ""  # provider name when this finished connecting a provider to the account
    created: bool = False


class RemoveIn(BaseModel):
    password: str = ""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def store_flow(db: Session, kind: str, payload: dict, lifetime: timedelta) -> str:
    value = secrets.token_urlsafe(32)
    db.add(AuthFlowToken(kind=kind, token_hash=hash_value(value), payload=json.dumps(payload), expires_at=now_utc() + lifetime))
    return value


def take_flow(db: Session, kind: str, value: str) -> dict | None:
    """Use a state or hand-off value once. Expired, used or unknown values give None."""
    if not value:
        return None
    row = db.scalar(select(AuthFlowToken).where(AuthFlowToken.token_hash == hash_value(value), AuthFlowToken.kind == kind))
    if row is None or row.used_at is not None or as_utc(row.expires_at) < now_utc():
        return None
    row.used_at = now_utc()
    return json.loads(row.payload or "{}")


def return_url(platform: str) -> str:
    if platform == "app":
        return settings.clean_env_value(settings.sign_in_app_return_url)
    web = settings.clean_env_value(settings.sign_in_web_return_url) or settings.clean_env_value(settings.frontend_url)
    return web.rstrip("/") + "/"


def back_to_app(platform: str, **fragment: str) -> RedirectResponse:
    # Fragments are not sent to any server, so the one-time code stays out of server logs.
    query = "&".join(f"{key}={value}" for key, value in fragment.items())
    return RedirectResponse(f"{return_url(platform)}#{query}", status_code=status.HTTP_303_SEE_OTHER)


def require_provider(provider: str) -> None:
    if provider not in oidc.PROVIDERS or not oidc.configured(provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This sign-in option is not available.")


@router.get("/providers")
def providers():
    return {"providers": oidc.enabled_providers()}


def start_flow(db: Session, provider: str, payload: StartIn, intent: str, user_id: str = "") -> StartOut:
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = oidc.pkce_pair()
    state = store_flow(
        db,
        "state",
        {
            "provider": provider,
            "intent": intent,
            "user_id": user_id,
            "platform": payload.platform,
            "binding": payload.binding,
            "nonce": nonce,
            "verifier": verifier,
        },
        timedelta(minutes=STATE_MINUTES),
    )
    db.commit()
    return StartOut(authorization_url=oidc.authorization_url(provider, state, nonce, challenge))


@router.post("/oidc/{provider}/start", response_model=StartOut)
def start(provider: ProviderName, payload: StartIn, request: Request, db: Session = Depends(get_db)):
    require_provider(provider)
    check_rate_limit(db, request, "oidc_start", provider, max_attempts=30, window_seconds=900)
    return start_flow(db, provider, payload, "signin")


@router.post("/oidc/{provider}/link-start", response_model=StartOut)
def link_start(
    provider: ProviderName,
    payload: StartIn,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_provider(provider)
    check_rate_limit(db, request, "oidc_link_start", user.user_id, max_attempts=10, window_seconds=900)
    return start_flow(db, provider, payload, "link", user.user_id)


async def callback_params(request: Request) -> dict[str, str]:
    params = dict(request.query_params)
    if request.method == "POST":  # Apple form_post
        form = await request.form()
        params.update({key: str(value) for key, value in form.items()})
    return params


async def callback(provider: str, request: Request, db: Session) -> RedirectResponse:
    params = await callback_params(request)
    flow = take_flow(db, "state", params.get("state", ""))
    db.commit()
    if flow is None or flow.get("provider") != provider:
        return back_to_app("web", **{"signin-error": "expired"})
    platform = flow.get("platform", "web")
    if params.get("error"):
        # The person closed the provider's page or said no. Nothing was changed.
        return back_to_app(platform, **{"signin-error": "cancelled"})
    try:
        token = oidc.exchange_code(provider, params.get("code", ""), flow["verifier"])
        identity = oidc.verify_id_token(provider, token, flow["nonce"])
    except oidc.SignInError as error:
        return back_to_app(platform, **{"signin-error": "failed" if error.code == "exchange_failed" else "invalid"})
    code = store_flow(
        db,
        "handoff",
        {
            "intent": flow["intent"],
            "user_id": flow.get("user_id", ""),
            "binding": flow["binding"],
            "provider": identity.provider,
            "subject": identity.subject,
            "email": identity.email,
            "email_verified": identity.email_verified,
            "personal": identity.personal_account,
        },
        timedelta(seconds=HANDOFF_SECONDS),
    )
    db.commit()
    return back_to_app(platform, **{"signin-code": code})


@router.get("/oidc/{provider}/callback")
async def callback_get(provider: ProviderName, request: Request, db: Session = Depends(get_db)):
    return await callback(provider, request, db)


@router.post("/oidc/{provider}/callback")
async def callback_post(provider: ProviderName, request: Request, db: Session = Depends(get_db)):
    return await callback(provider, request, db)


def refuse(code: str, message: str, http_status: int = status.HTTP_409_CONFLICT) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def sign_in_user(db: Session, user: User, identity: UserIdentity, **extra) -> ExchangeOut:
    if user.role != "patient":
        # Clinic and admin accounts use email, password and two-step sign-in.
        raise refuse("staff_account", "Clinic accounts sign in with email and password.", status.HTTP_403_FORBIDDEN)
    identity.last_used_at = now_utc()
    if user.totp_enabled:
        db.commit()
        return ExchangeOut(access_token="", two_factor_required=True, challenge=make_challenge(user.id), **extra)
    write_audit(db, user.id, "", "user_login", "user", user.id, {"method": identity.provider})
    tokens = issue_token_pair(db, user)
    db.commit()
    return ExchangeOut(**tokens.model_dump(), **extra)


@router.post("/oidc/exchange", response_model=ExchangeOut)
def exchange(payload: ExchangeIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "oidc_exchange", "", max_attempts=30, window_seconds=900)
    flow = take_flow(db, "handoff", payload.code)
    db.commit()
    if flow is None or not secrets.compare_digest(flow.get("binding", ""), hash_value(payload.secret)):
        raise refuse("expired", "We couldn't finish signing you in. Please try again.", status.HTTP_400_BAD_REQUEST)
    provider, subject, email = flow["provider"], flow["subject"], flow.get("email", "")
    existing = db.scalar(select(UserIdentity).where(UserIdentity.provider == provider, UserIdentity.subject == subject))

    if flow["intent"] == "link":
        owner = db.get(User, flow.get("user_id", ""))
        if owner is None:
            raise refuse("expired", "We couldn't finish signing you in. Please try again.", status.HTTP_400_BAD_REQUEST)
        if existing and existing.user_id != owner.id:
            raise refuse("identity_in_use", "That account is already connected to a different FollowThrough account.")
        if existing is None:
            db.add(UserIdentity(user_id=owner.id, provider=provider, subject=subject, email=email, last_used_at=now_utc()))
            write_audit(db, owner.id, "", "sign_in_method_added", "user", owner.id, {"method": provider})
        db.commit()
        return ExchangeOut(access_token="", linked=provider)

    if existing:
        user = db.get(User, existing.user_id)
        if user is None:
            raise refuse("expired", "We couldn't finish signing you in. Please try again.", status.HTTP_400_BAD_REQUEST)
        return sign_in_user(db, user, existing)

    if email and db.scalar(select(User).where(func.lower(User.email) == email)):
        raise refuse(
            "email_in_use",
            "This email is already linked to an account. Sign in to that account first to connect this method.",
        )
    if not flow.get("email_verified"):
        # Work or school Microsoft accounts and unconfirmed addresses cannot open an account
        # by themselves; they can be connected to an existing account from Account.
        raise refuse(
            "needs_existing_account",
            "Create your account with email first, then connect this sign-in method from Account.",
            status.HTTP_403_FORBIDDEN,
        )
    if settings.staff_role_for(email):
        raise refuse("staff_account", "Clinic accounts sign in with email and password.", status.HTTP_403_FORBIDDEN)
    user = User(email=email, password_hash="", role="patient", email_verified="true")
    db.add(user)
    db.flush()
    identity = UserIdentity(user_id=user.id, provider=provider, subject=subject, email=email)
    db.add(identity)
    write_audit(db, user.id, "", "user_created", "user", user.id, {"role": "patient", "method": provider})
    return sign_in_user(db, user, identity, created=True)


@router.get("/identities")
def list_identities(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.get(User, user.user_id)
    rows = db.scalars(select(UserIdentity).where(UserIdentity.user_id == user.user_id).order_by(UserIdentity.created_at)).all()
    return {
        "email": account.email if account else user.email,
        "email_verified": bool(account and account.email_verified == "true"),
        "has_password": bool(account and account.password_hash),
        "two_factor": bool(account and account.totp_enabled),
        "available": oidc.enabled_providers(),
        "identities": [
            {
                "id": row.id,
                "provider": row.provider,
                "email": row.email,
                "created_at": row.created_at,
                "last_used_at": row.last_used_at,
            }
            for row in rows
        ],
    }


@router.post("/identities/{identity_id}/remove")
def remove_identity(
    identity_id: str,
    payload: RemoveIn,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_rate_limit(db, request, "identity_remove", user.user_id, max_attempts=10, window_seconds=900)
    account = db.get(User, user.user_id)
    row = db.get(UserIdentity, identity_id)
    if account is None or row is None or row.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    others = db.scalar(
        select(func.count(UserIdentity.id)).where(UserIdentity.user_id == user.user_id, UserIdentity.id != row.id)
    )
    if not account.password_hash and not others:
        raise refuse(
            "last_method",
            "This is your only way to sign in. Set a password with \"Forgot password\" first, then remove it.",
        )
    if account.password_hash and not verify_password(payload.password, account.password_hash):
        raise refuse("password", "Enter your current password to remove a sign-in method.", status.HTTP_403_FORBIDDEN)
    db.delete(row)
    write_audit(db, user.user_id, "", "sign_in_method_removed", "user", user.user_id, {"method": row.provider})
    db.commit()
    return {"status": "removed"}
