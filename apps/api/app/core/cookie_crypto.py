"""Cookie encryption/decryption helpers for persistent credential storage.

Storage format: enc:v1:{base64url(iv)}:{base64url(cipher_text_with_tag)}
Legacy plaintext values are returned as-is for backward compatibility.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
DEV_SECRET = "dev-only-cookie-crypto-secret-change-me-32-chars"

_dev_secret_warned = False


def _get_secret() -> str:
    """Return the configured cookie crypto secret.

    In dev environment (APP_ENV=dev), falls back to DEV_SECRET with a warning
    when COOKIE_CRYPTO_SECRET is unset or still equal to DEV_SECRET. In any
    other environment, raises RuntimeError to prevent silently using a weak key.
    """
    global _dev_secret_warned
    app_env = getattr(settings, "app_env", "dev").strip().lower()
    secret = getattr(settings, "cookie_crypto_secret", "") or ""
    if not secret or secret == DEV_SECRET:
        if app_env == "dev":
            if not _dev_secret_warned:
                logger.warning(
                    "COOKIE_CRYPTO_SECRET 未配置或仍为默认值，开发环境回退使用 DEV_SECRET。"
                    "生产环境必须显式配置一个强随机的 COOKIE_CRYPTO_SECRET。"
                )
                _dev_secret_warned = True
            return DEV_SECRET
        raise RuntimeError(
            "COOKIE_CRYPTO_SECRET 未配置或仍为默认开发密钥，禁止在非 dev 环境"
            "（当前 APP_ENV=%s）使用，请显式设置一个强随机密钥。" % app_env
        )
    return secret


def _derive_key(secret: str) -> bytes:
    return hashlib.sha256((secret or DEV_SECRET).encode("utf-8")).digest()


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def encrypt_cookie_for_storage(cookie: Optional[str]) -> Optional[str]:
    if not cookie or cookie.startswith(PREFIX):
        return cookie
    key = _derive_key(_get_secret())
    iv = os.urandom(12)
    cipher = AESGCM(key).encrypt(iv, cookie.encode("utf-8"), None)
    return f"{PREFIX}{_b64e(iv)}:{_b64e(cipher)}"


def decrypt_cookie_if_needed(stored: Optional[str]) -> Optional[str]:
    if not stored or not stored.startswith(PREFIX):
        return stored
    try:
        _, _, iv_b64, cipher_b64 = stored.split(":", 3)
        key = _derive_key(_get_secret())
        plain = AESGCM(key).decrypt(_b64d(iv_b64), _b64d(cipher_b64), None)
        return plain.decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Cookie 解密失败，请检查 COOKIE_CRYPTO_SECRET 是否与加密该数据时使用的密钥一致") from exc
