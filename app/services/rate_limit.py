from datetime import datetime, timedelta, timezone
import hashlib

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.carewise import RateLimitBucket


def check_rate_limit(db: Session, request: Request, action: str, identifier: str = "") -> None:
    now = datetime.now(timezone.utc)
    window_seconds = settings.auth_rate_limit_window_seconds
    max_attempts = settings.auth_rate_limit_max_attempts
    bucket_key = hashed_bucket_key(action, client_identifier(request, identifier))
    bucket = db.scalar(select(RateLimitBucket).where(RateLimitBucket.bucket_key == bucket_key))
    if bucket is None:
        db.add(
            RateLimitBucket(
                bucket_key=bucket_key,
                action=action,
                attempts="1",
                window_start=now,
            )
        )
        db.commit()
        return

    window_start = as_utc(bucket.window_start)
    if now - window_start >= timedelta(seconds=window_seconds):
        bucket.attempts = "1"
        bucket.window_start = now
        db.commit()
        return

    attempts = int(bucket.attempts or "0") + 1
    bucket.attempts = str(attempts)
    db.commit()
    if attempts > max_attempts:
        retry_after = max(1, window_seconds - int((now - window_start).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def hashed_bucket_key(action: str, identifier: str) -> str:
    return hashlib.sha256(f"{action}:{identifier}".encode("utf-8")).hexdigest()


def client_identifier(request: Request, identifier: str = "") -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",", 1)[0].strip()
    if not client_ip and request.client is not None:
        client_ip = request.client.host
    return "|".join(part for part in (client_ip, identifier.lower().strip()) if part)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
