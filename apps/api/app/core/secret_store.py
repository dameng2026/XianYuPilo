from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings


PREFIX = "secret:v1:"
_PURPOSE_RE = re.compile(r"^[a-z0-9_.-]{1,80}$")


def _purpose(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    if not _PURPOSE_RE.fullmatch(normalized):
        raise ValueError("invalid secret purpose")
    return normalized


def _key() -> bytes:
    return hashlib.sha256(settings.cookie_crypto_secret.encode("utf-8")).digest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def is_encrypted_secret(value: Optional[str]) -> bool:
    return bool(value and value.startswith(PREFIX))


def encrypt_secret(value: Optional[str], *, purpose: str) -> Optional[str]:
    if value in (None, "") or is_encrypted_secret(value):
        return value
    normalized_purpose = _purpose(purpose)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(
        nonce,
        str(value).encode("utf-8"),
        normalized_purpose.encode("ascii"),
    )
    return f"{PREFIX}{normalized_purpose}:{_encode(nonce)}:{_encode(ciphertext)}"


def decrypt_secret(value: Optional[str], *, purpose: str) -> Optional[str]:
    if value in (None, "") or not is_encrypted_secret(value):
        # Legacy plaintext remains readable and is encrypted on the next save.
        return value
    normalized_purpose = _purpose(purpose)
    try:
        _, _, stored_purpose, nonce, ciphertext = str(value).split(":", 4)
        if stored_purpose != normalized_purpose:
            raise ValueError("secret purpose mismatch")
        plaintext = AESGCM(_key()).decrypt(
            _decode(nonce),
            _decode(ciphertext),
            normalized_purpose.encode("ascii"),
        )
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise RuntimeError(
            "Sensitive configuration could not be decrypted; verify COOKIE_CRYPTO_SECRET"
        ) from exc
