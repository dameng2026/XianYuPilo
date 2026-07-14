from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "pwd",
    "secret",
    "client-secret",
    "client_secret",
    "api-key",
    "api_key",
    "apikey",
    "access-token",
    "access_token",
    "accesstoken",
    "refresh-token",
    "refresh_token",
    "refreshtoken",
    "id-token",
    "id_token",
    "token",
    "_m_h5_tk",
    "signature",
    "sign",
    "csrf",
    "session",
}

_KEY_PATTERN = (
    r"authorization|proxy[-_]?authorization|set[-_]?cookie|cookie|password|passwd|pwd|"
    r"client[-_]?secret|secret|api[-_]?key|apikey|access[-_]?token|accesstoken|"
    r"refresh[-_]?token|refreshtoken|id[-_]?token|token|_m_h5_tk|signature|sign|csrf|session"
)
_QUOTED_ASSIGNMENT_RE = re.compile(
    rf"(?i)(?P<prefix>['\"]?(?:{_KEY_PATTERN})['\"]?\s*[:=]\s*)(?P<quote>['\"])(?P<value>.*?)(?P=quote)"
)
_UNQUOTED_ASSIGNMENT_RE = re.compile(
    rf"(?i)(?P<prefix>\b(?:{_KEY_PATTERN})\b\s*[:=]\s*)(?P<value>[^\s,;}}\]&]+)"
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+")


def _normalized_key(value: Any) -> str:
    return str(value).strip().casefold().replace(" ", "_")


def is_sensitive_key(value: Any) -> bool:
    key = _normalized_key(value)
    return key in _SENSITIVE_KEYS or key.replace("_", "-") in _SENSITIVE_KEYS


def redact_sensitive_text(value: Any, *, max_length: int | None = None) -> str:
    """Remove common credentials from log/error text without echoing prefixes."""
    text = str(value if value is not None else "")
    text = _BEARER_RE.sub(rf"\1{REDACTED}", text)
    text = _QUOTED_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('prefix')}{match.group('quote')}{REDACTED}{match.group('quote')}",
        text,
    )
    text = _UNQUOTED_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}",
        text,
    )
    if max_length is not None and len(text) > max_length:
        return f"{text[:max_length]}..."
    return text


def redact_sensitive(value: Any) -> Any:
    """Recursively redact secrets before serialising diagnostic structures."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if is_sensitive_key(key) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def safe_exception_message(exc: BaseException, *, max_length: int = 500) -> str:
    return redact_sensitive_text(str(exc), max_length=max_length)


def _sanitize_record(record: logging.LogRecord) -> None:
    try:
        rendered = record.getMessage()
    except Exception:
        rendered = str(record.msg)
    sanitized = redact_sensitive_text(rendered)
    if sanitized != rendered:
        record.msg = sanitized
        record.args = ()

    if record.exc_info and record.exc_info[1] is not None:
        raw_exception = str(record.exc_info[1])
        # A normal traceback is valuable, but a traceback containing a secret
        # would append the original exception text after the redacted message.
        if redact_sensitive_text(raw_exception) != raw_exception:
            record.exc_info = None
            record.exc_text = None
    elif record.exc_text:
        record.exc_text = redact_sensitive_text(record.exc_text)


def install_log_redaction() -> None:
    """Install process-wide redaction before application modules start logging."""
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, "_xianyu_redacting_factory", False):
        return

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current_factory(*args, **kwargs)
        _sanitize_record(record)
        return record

    redacting_factory._xianyu_redacting_factory = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(redacting_factory)
