import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_field, encrypt_field
from app.db.session import get_db
from app.models.carewise import EarlyAccessSignup, ProductFeedback, UsageCounter
from app.schemas.carewise import (
    EARLY_ACCESS_ROLES,
    SIGNAL_SOURCES,
    USAGE_EVENTS,
    EarlyAccessIn,
    FeedbackCommentIn,
    FeedbackIn,
    SignalAccepted,
    UsageEventIn,
)
from app.services.rate_limit import check_rate_limit

# Anonymous product signals: a daily counter per action, a "was this helpful?"
# answer, and an early-access list. No report text, IP address or account id is
# stored; rate limiting uses the same hashed buckets as sign-in.
router = APIRouter()


def clean_source(source: str) -> str:
    return source if source in SIGNAL_SOURCES else "web"


@router.post("/events", response_model=SignalAccepted)
def record_event(payload: UsageEventIn, request: Request, db: Session = Depends(get_db)):
    if payload.name not in USAGE_EVENTS:
        raise HTTPException(status_code=422, detail="Unknown event.")
    check_rate_limit(db, request, "product_event", max_attempts=120)
    day = datetime.now(timezone.utc).date().isoformat()
    source = clean_source(payload.source)
    counter = db.scalar(
        select(UsageCounter).where(UsageCounter.day == day, UsageCounter.name == payload.name, UsageCounter.source == source)
    )
    if counter is None:
        db.add(UsageCounter(day=day, name=payload.name, source=source, count=1))
    else:
        counter.count = (counter.count or 0) + 1
    db.commit()
    return SignalAccepted()


@router.post("/feedback", response_model=SignalAccepted)
def record_feedback(payload: FeedbackIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "product_feedback", max_attempts=20)
    feedback = ProductFeedback(
        helpful="yes" if payload.helpful else "no",
        encrypted_comment=encrypt_field(payload.comment.strip()),
        source=clean_source(payload.source),
    )
    db.add(feedback)
    db.commit()
    return SignalAccepted(id=feedback.id)


# The answer is saved on the first tap; an optional comment can follow once.
@router.post("/feedback/{feedback_id}/comment", response_model=SignalAccepted)
def add_feedback_comment(feedback_id: str, payload: FeedbackCommentIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "product_feedback", max_attempts=20)
    feedback = db.get(ProductFeedback, feedback_id)
    if feedback is None or feedback.encrypted_comment:
        raise HTTPException(status_code=404, detail="Feedback not found.")
    feedback.encrypted_comment = encrypt_field(payload.comment.strip())
    db.commit()
    return SignalAccepted(id=feedback.id)


@router.post("/early-access", response_model=SignalAccepted)
def join_early_access(payload: EarlyAccessIn, request: Request, db: Session = Depends(get_db)):
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Please agree to be contacted about early access.")
    check_rate_limit(db, request, "early_access", max_attempts=5)
    email = str(payload.email).strip().lower()
    email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
    role = payload.role if payload.role in EARLY_ACCESS_ROLES else "other"
    existing = db.scalar(select(EarlyAccessSignup).where(EarlyAccessSignup.email_hash == email_hash))
    if existing is None:
        db.add(
            EarlyAccessSignup(
                email_hash=email_hash,
                encrypted_email=encrypt_field(email),
                role=role,
                encrypted_note=encrypt_field(payload.note.strip()),
                source=clean_source(payload.source),
            )
        )
    else:
        # Signing up twice is fine; keep one row and the latest answers.
        existing.role = role
        if payload.note.strip():
            existing.encrypted_note = encrypt_field(payload.note.strip())
    db.commit()
    return SignalAccepted()


@router.get("/summary")
def founder_summary(
    request: Request,
    x_founder_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    configured = settings.clean_env_value(settings.founder_token)
    if not configured:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    check_rate_limit(db, request, "founder_summary", max_attempts=30)
    if not hmac.compare_digest(x_founder_token.encode("utf-8"), configured.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Founder token required.")

    counters = db.execute(
        select(UsageCounter.day, UsageCounter.name, UsageCounter.source, UsageCounter.count).order_by(UsageCounter.day.desc())
    ).all()
    totals: dict[str, int] = {}
    for _, name, _, count in counters:
        totals[name] = totals.get(name, 0) + (count or 0)
    helpful = dict(db.execute(select(ProductFeedback.helpful, func.count()).group_by(ProductFeedback.helpful)).all())
    comments = db.scalars(
        select(ProductFeedback).where(ProductFeedback.encrypted_comment != "").order_by(ProductFeedback.created_at.desc()).limit(100)
    ).all()
    signups = db.scalars(select(EarlyAccessSignup).order_by(EarlyAccessSignup.created_at.desc())).all()
    return {
        "usage_totals": totals,
        "usage_by_day": [{"day": day, "name": name, "source": source, "count": count} for day, name, source, count in counters[:400]],
        "helpful": {"yes": helpful.get("yes", 0), "no": helpful.get("no", 0)},
        "comments": [
            {"helpful": item.helpful, "comment": decrypt_field(item.encrypted_comment), "source": item.source, "created_at": item.created_at}
            for item in comments
        ],
        "early_access": [
            {
                "email": decrypt_field(item.encrypted_email),
                "role": item.role,
                "note": decrypt_field(item.encrypted_note),
                "source": item.source,
                "created_at": item.created_at,
            }
            for item in signups
        ],
    }
