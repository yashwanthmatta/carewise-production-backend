import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_cron_token(x_carewise_cron_token: str = Header(default="")) -> None:
    """Scheduled jobs (reminder calls, nightly cleanup) send this shared secret."""
    expected = settings.clean_env_value(settings.reminder_cron_token)
    if not expected or not hmac.compare_digest(expected, x_carewise_cron_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed.")
