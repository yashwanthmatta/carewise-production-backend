from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "carewise-api"}


@router.get("/ready")
def ready():
    checks = {
        "database": database_ready(),
        "configuration": configuration_ready(),
        "storage": storage_ready(),
    }
    if not all(checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}


@router.get("/features")
def features():
    return {
        "storage_backend": settings.storage_backend,
        "report_uploads": True,
        "text_extraction": True,
        "pdf_text_extraction": True,
        "image_ocr": bool(settings.clean_env_value(settings.openai_api_key)),
        "ocr_model": settings.openai_ocr_model if settings.clean_env_value(settings.openai_api_key) else "",
        "stripe_checkout": bool(settings.clean_env_value(settings.stripe_secret_key)),
        "stripe_webhook": bool(settings.clean_env_value(settings.stripe_webhook_secret)),
        "password_reset": True,
        "email_delivery": settings.email_delivery_enabled,
        "auth_rate_limit": True,
        "auth_session": True,
        "refresh_tokens": True,
        "email_verification": True,
    }


def database_ready() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def configuration_ready() -> bool:
    try:
        settings.validate_for_startup()
        return True
    except RuntimeError:
        return False


def storage_ready() -> bool:
    if settings.storage_backend == "local":
        return bool(settings.clean_env_value(settings.local_storage_dir))
    if settings.storage_backend == "s3":
        return bool(
            settings.clean_env_value(settings.s3_bucket)
            and settings.clean_env_value(settings.s3_endpoint_url)
        )
    return False
