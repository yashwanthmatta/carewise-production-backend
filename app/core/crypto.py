"""Field encryption with versioned keys.

Every value is encrypted with Fernet (AES-128-CBC with an HMAC-SHA256 tag, from the
`cryptography` library) and stored as ``ftenc:<key id>:<Fernet token>``, so each stored value
names the key that encrypted it. New values always use the current key; values written under an
older key, and older values written before key ids existed (a bare Fernet token), stay readable as
long as their key is still configured.

Keys come only from the environment (see ``Settings.field_encryption_key_ring``) and are never
logged. A value that cannot be decrypted raises ``FieldDecryptionError``: callers never receive an
empty string or a placeholder in place of someone's health information.
"""

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


logger = logging.getLogger(__name__)

PREFIX = "ftenc:"
LEGACY_KEY_ID = "k1"


class FieldDecryptionError(Exception):
    """A stored value could not be decrypted with any configured key."""

    def __init__(self, key_id: str):
        super().__init__(f"Stored value could not be decrypted (key id: {key_id}).")
        self.key_id = key_id


def _legacy_fernet(raw_key: str) -> Fernet:
    # Kept for values written before key ids existed: the original key setting accepted any
    # string and hashed it into a Fernet key when it was not one already.
    try:
        return Fernet(raw_key.encode("utf-8"))
    except ValueError:
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest()))


@lru_cache
def _key_ring() -> tuple[str, dict[str, Fernet]]:
    current, keys = settings.field_encryption_key_ring
    ring = {key_id: (_legacy_fernet(raw) if key_id == LEGACY_KEY_ID else Fernet(raw.encode("utf-8"))) for key_id, raw in keys.items()}
    return current, ring


def reset_key_ring_cache() -> None:
    """For tests and for a process that has just been given new key settings."""
    _key_ring.cache_clear()


def current_key_id() -> str:
    return _key_ring()[0]


def configured_key_ids() -> list[str]:
    return sorted(_key_ring()[1])


def key_id_of(value: str | None) -> str:
    """Which key a stored value needs: a key id, "legacy" (bare Fernet token), "plaintext" or "empty"."""
    if not value:
        return "empty"
    if value.startswith(PREFIX):
        return value[len(PREFIX):].split(":", 1)[0]
    if value.startswith("gAAAAA"):
        return "legacy"
    return "plaintext"


def encrypt_field(value: str | None) -> str:
    if not value:
        return ""
    key_id, ring = _key_ring()
    token = ring[key_id].encrypt(value.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{key_id}:{token}"


def decrypt_field(value: str | None) -> str:
    if not value:
        return ""
    _, ring = _key_ring()
    if value.startswith(PREFIX):
        key_id, _, token = value[len(PREFIX):].partition(":")
        fernet = ring.get(key_id)
        if fernet is None:
            logger.error("field_decrypt_failed key_id=%s reason=key_not_configured", key_id)
            raise FieldDecryptionError(key_id)
        try:
            return fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as error:
            logger.error("field_decrypt_failed key_id=%s reason=invalid_token", key_id)
            raise FieldDecryptionError(key_id) from error
    # A bare Fernet token from before key ids: try the original key first, then the others.
    ordered = [ring[LEGACY_KEY_ID]] if LEGACY_KEY_ID in ring else []
    ordered += [fernet for key_id, fernet in ring.items() if key_id != LEGACY_KEY_ID]
    for fernet in ordered:
        try:
            return fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            continue
    logger.error("field_decrypt_failed key_id=legacy reason=invalid_token")
    raise FieldDecryptionError("legacy")


BYTES_PREFIX = PREFIX.encode("ascii")


def encrypt_bytes(value: bytes) -> bytes:
    key_id, ring = _key_ring()
    return BYTES_PREFIX + key_id.encode("ascii") + b":" + ring[key_id].encrypt(value)


def decrypt_bytes(value: bytes) -> bytes:
    _, ring = _key_ring()
    if value.startswith(BYTES_PREFIX):
        key_id, _, token = value[len(BYTES_PREFIX):].partition(b":")
        fernet = ring.get(key_id.decode("ascii", "replace"))
        if fernet is None:
            raise FieldDecryptionError(key_id.decode("ascii", "replace"))
        try:
            return fernet.decrypt(token)
        except InvalidToken as error:
            raise FieldDecryptionError(key_id.decode("ascii", "replace")) from error
    for fernet in ring.values():
        try:
            return fernet.decrypt(value)
        except InvalidToken:
            continue
    raise FieldDecryptionError("legacy")


class EncryptedText(TypeDecorator):
    """A text column encrypted before it reaches the database.

    Reads accept three forms so existing rows keep working while they are migrated:
    a versioned token, a bare Fernet token, or plaintext written before the column was encrypted.
    Writes always store a versioned token under the current key. Empty strings stay empty, so
    "no value" needs no key and reveals nothing.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        return encrypt_field(value)

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        if key_id_of(value) == "plaintext":
            return value
        return decrypt_field(value)
