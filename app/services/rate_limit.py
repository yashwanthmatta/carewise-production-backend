from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.carewise import RateLimitBucket


def check_rate_limit(
    db: Session,
    request: Request,
    action: str,
    identifier: str = "",
    max_attempts: int | None = None,
    window_seconds: int | None = None,
    by_ip: bool = True,
) -> None:
    now = datetime.now(timezone.utc)
    window_seconds = window_seconds or settings.auth_rate_limit_window_seconds
    max_attempts = max_attempts or settings.auth_rate_limit_max_attempts
    # by_ip=False counts attempts per account no matter where they come from, so guesses
    # spread over many addresses are still limited.
    key = client_identifier(request, identifier) if by_ip else f"account|{identifier.lower().strip()}"
    bucket_key = hashed_bucket_key(action, key)
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


def client_address(request: Request) -> str:
    """The caller's address. The browser can put anything at the start of X-Forwarded-For;
    the hosting proxy appends the real address, so read from the right and skip private
    hops added inside the host's network."""
    hops = [hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",") if hop.strip()]
    for hop in reversed(hops):
        try:
            address = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not (address.is_private or address.is_loopback or address.is_link_local):
            return hop
    return request.client.host if request.client is not None else ""


def client_identifier(request: Request, identifier: str = "") -> str:
    client_ip = client_address(request)
    return "|".join(part for part in (client_ip, identifier.lower().strip()) if part)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
