from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "carewise-api"}


@router.get("/ready")
def ready(request: Request):
    checks = {
        "database": database_ready(),
        "configuration": configuration_ready(),
        "storage": storage_ready(),
    }
    if not all(checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "checks": checks, "issues": readiness_issues(request, checks)},
        )
    return {"status": "ready", "checks": checks}


@router.get("/features")
def features():
    storage_config = settings.storage_configuration
    return {
        "storage_backend": settings.storage_backend,
        "durable_storage": bool(storage_config["durable"]),
        "storage_ready": bool(storage_config["ready"]),
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


def readiness_issues(request: Request, checks: dict) -> list[str]:
    issues = []
    startup_error = getattr(request.app.state, "startup_error", "")
    if startup_error:
        issues.append(startup_error)
    elif not checks["configuration"]:
        try:
            settings.validate_for_startup()
        except RuntimeError as error:
            issues.append(str(error))
    if not checks["database"]:
        issues.append(
            "Database unreachable. Check that CAREWISE_DATABASE_URL points to a running Postgres database."
        )
    return issues


def configuration_ready() -> bool:
    try:
        settings.validate_for_startup()
        return True
    except RuntimeError:
        return False


def storage_ready() -> bool:
    return bool(settings.storage_configuration["ready"])
