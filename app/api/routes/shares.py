import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import DoctorShare
from app.schemas.carewise import (
    DoctorShareCreatedOut,
    DoctorShareIn,
    DoctorShareOut,
    DoctorShareViewIn,
    DoctorShareViewOut,
)
from app.services.audit import write_audit
from app.services.rate_limit import check_rate_limit

# "Share with my doctor": the family creates a read-only link that expires and can be
# turned off. The link token is shown once; only its hash is stored.
router = APIRouter()

MAX_SNAPSHOT_BYTES = 60_000
MAX_ACTIVE_SHARES = 20
NOT_AVAILABLE = "This link has expired or was turned off. Ask the family for a new one."


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def share_out(share: DoctorShare) -> dict:
    return {
        "id": share.id,
        "label": decrypt_field(share.encrypted_label),
        "expires_at": as_utc(share.expires_at),
        "revoked": share.revoked_at is not None,
        "view_count": share.view_count or 0,
        "last_viewed_at": as_utc(share.last_viewed_at) if share.last_viewed_at else None,
        "created_at": share.created_at,
    }


@router.post("", response_model=DoctorShareCreatedOut)
def create_share(
    payload: DoctorShareIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    body = json.dumps(payload.snapshot, separators=(",", ":"))
    if len(body.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The summary is too large to share.")
    now = datetime.now(timezone.utc)
    active = db.scalar(
        select(func.count(DoctorShare.id)).where(
            DoctorShare.user_id == user.user_id,
            DoctorShare.revoked_at.is_(None),
            DoctorShare.expires_at > now,
        )
    )
    if (active or 0) >= MAX_ACTIVE_SHARES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turn off an older link before making a new one.")
    token = secrets.token_urlsafe(32)
    share = DoctorShare(
        user_id=user.user_id,
        token_hash=hash_token(token),
        encrypted_label=encrypt_field(payload.label.strip()),
        encrypted_snapshot=encrypt_field(body),
        expires_at=now + timedelta(days=payload.days),
        view_count=0,
    )
    db.add(share)
    db.flush()
    write_audit(db, user.user_id, "", "doctor_share_created", "doctor_share", share.id, {"days": payload.days})
    db.commit()
    db.refresh(share)
    return {**share_out(share), "token": token}


@router.get("", response_model=list[DoctorShareOut])
def list_shares(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    shares = db.scalars(
        select(DoctorShare).where(DoctorShare.user_id == user.user_id).order_by(DoctorShare.created_at.desc()).limit(50)
    ).all()
    return [share_out(share) for share in shares]


@router.post("/{share_id}/revoke", response_model=DoctorShareOut)
def revoke_share(
    share_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    share = db.get(DoctorShare, share_id)
    if share is None or share.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    if share.revoked_at is None:
        share.revoked_at = datetime.now(timezone.utc)
        write_audit(db, user.user_id, "", "doctor_share_revoked", "doctor_share", share.id, {})
        db.commit()
        db.refresh(share)
    return share_out(share)


# The doctor's side: no account needed, the token is the key. The token is sent in the
# body (not the URL) so it does not end up in server logs.
@router.post("/view", response_model=DoctorShareViewOut)
def view_share(payload: DoctorShareViewIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "doctor_share_view", max_attempts=60, window_seconds=3600)
    share = db.scalar(select(DoctorShare).where(DoctorShare.token_hash == hash_token(payload.token)))
    now = datetime.now(timezone.utc)
    if share is None or share.revoked_at is not None or as_utc(share.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_AVAILABLE)
    share.view_count = (share.view_count or 0) + 1
    share.last_viewed_at = now
    write_audit(db, "doctor_link", "", "doctor_share_viewed", "doctor_share", share.id, {"views": share.view_count})
    db.commit()
    try:
        snapshot = json.loads(decrypt_field(share.encrypted_snapshot))
    except json.JSONDecodeError:
        snapshot = {}
    return {
        "label": decrypt_field(share.encrypted_label),
        "snapshot": snapshot if isinstance(snapshot, dict) else {},
        "expires_at": as_utc(share.expires_at),
        "created_at": share.created_at,
    }
