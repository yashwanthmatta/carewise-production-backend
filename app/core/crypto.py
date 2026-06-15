from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    try:
        return Fernet(settings.field_encryption_key.encode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("CAREWISE_FIELD_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_field(value: str | None) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_field(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return "[unreadable encrypted field]"
