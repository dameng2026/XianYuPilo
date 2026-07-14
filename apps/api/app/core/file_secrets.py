from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

MAX_SECRET_FILE_BYTES = 64 * 1024


class FileSecretConfigurationError(ValueError):
    """A sanitized startup error for invalid file-backed secret settings."""


def read_file_secret(
    path_value: object,
    *,
    field_name: str,
    required: bool = True,
) -> str:
    """Read one UTF-8 logical line without exposing its path or contents."""

    try:
        secret_path = Path(str(path_value))
        with secret_path.open("rb") as secret_stream:
            raw = secret_stream.read(MAX_SECRET_FILE_BYTES + 1)
    except (OSError, ValueError, TypeError):
        raise FileSecretConfigurationError(
            f"{field_name}_FILE could not be read securely"
        ) from None
    if len(raw) > MAX_SECRET_FILE_BYTES:
        raise FileSecretConfigurationError(
            f"{field_name}_FILE exceeds the maximum allowed size"
        )
    try:
        value = raw.decode("utf-8")
    except UnicodeError:
        raise FileSecretConfigurationError(
            f"{field_name}_FILE must contain valid UTF-8"
        ) from None

    if value.endswith("\r\n"):
        value = value[:-2]
    elif value.endswith("\n"):
        value = value[:-1]
    if "\n" in value or "\r" in value:
        raise FileSecretConfigurationError(
            f"{field_name}_FILE must contain exactly one logical line"
        )
    if "\0" in value:
        raise FileSecretConfigurationError(
            f"{field_name}_FILE contains an invalid control character"
        )
    if required and not value.strip():
        raise FileSecretConfigurationError(
            f"{field_name}_FILE must not be empty"
        )
    return value


def resolve_file_secret_values(
    values: Mapping[str, Any],
    *,
    secret_fields: Iterable[str],
    optional_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Resolve ``field``/``field_file`` pairs in an isolated settings map."""

    resolved = dict(values)
    optional = frozenset(optional_fields)
    for field_name in secret_fields:
        file_field_name = f"{field_name}_file"
        file_path = resolved.pop(file_field_name, "")
        direct_value = resolved.get(field_name, "")
        if direct_value not in (None, "") and file_path not in (None, ""):
            environment_name = field_name.upper()
            raise FileSecretConfigurationError(
                f"{environment_name} and {environment_name}_FILE cannot both be configured"
            )
        if file_path not in (None, ""):
            resolved[field_name] = read_file_secret(
                file_path,
                field_name=field_name.upper(),
                required=field_name not in optional,
            )
    return resolved
