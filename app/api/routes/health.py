from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "carewise-api"}


@router.get("/ready")
def ready():
    return {"status": "ready"}


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
