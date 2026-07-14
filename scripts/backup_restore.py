#!/usr/bin/env python3
"""Fail-closed backup creation, verification, and isolated restore rehearsal.

The operator deliberately exposes a narrow command surface.  Production
backup bytes flow directly from Docker into ``age`` encryption; restore bytes
flow directly from ``age`` into brand-new, labelled rehearsal resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Mapping, Protocol


EXPECTED_COMPONENTS = ("api_data", "api_uploads", "mysql_data", "redis_data")
ENCRYPTED_COMPONENTS = (
    "api_data",
    "api_uploads",
    "mysql_data",
    "redis_data",
    "audit_data",
)
ENCRYPTED_COMPONENT_SUFFIXES = {
    "api_data": ".tar.age",
    "api_uploads": ".tar.age",
    "mysql_data": ".sql.age",
    "redis_data": ".rdb.age",
    "audit_data": ".sql.age",
}
ENCRYPTED_BACKUP_MODE = "encrypted-application-quiesced-v1"
AGE_HEADER = b"age-encryption.org/v1\n"
AGE_RECIPIENT_RE = re.compile(r"^age1[0-9a-z]{20,120}$")
MANIFEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "backupId",
        "createdAt",
        "productionProject",
        "verifiedAt",
        "components",
    }
)
MANIFEST_V2_FIELDS = MANIFEST_FIELDS | frozenset({"mode"})
COMPONENT_FIELDS = frozenset({"name", "archive", "bytes", "sha256"})
MARKER_FIELDS = frozenset(
    {"schemaVersion", "backupId", "completedAt", "manifestSha256"}
)
RETENTION_CATALOG_FIELDS = frozenset({"schemaVersion", "records"})
RETENTION_RECORD_FIELDS = frozenset(
    {"backupId", "createdAt", "verifiedAt", "legalHold"}
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
SENSITIVE_OPTION_WORDS = frozenset(
    {
        "credential",
        "credentials",
        "key",
        "passphrase",
        "password",
        "passwd",
        "secret",
        "token",
    }
)
SAFE_TAR_MEMBER_TYPES = frozenset(
    {
        tarfile.REGTYPE,
        tarfile.AREGTYPE,
        tarfile.DIRTYPE,
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
    }
)


class BackupContractError(ValueError):
    """Raised when backup evidence violates the fail-closed contract."""


@dataclass(frozen=True)
class ValidatedComponent:
    name: str
    archive: PurePosixPath
    bytes: int
    sha256: str


@dataclass(frozen=True)
class ValidatedBackup:
    schema_version: int
    backup_id: uuid.UUID
    created_at: datetime
    production_project: str
    verified_at: datetime | None
    completed_at: datetime
    components: tuple[ValidatedComponent, ...]
    raw_manifest: dict[str, object]


@dataclass(frozen=True)
class RetentionRecord:
    backup_id: uuid.UUID
    created_at: datetime
    verified_at: datetime | None
    legal_hold: bool = False


@dataclass(frozen=True)
class RetentionDecision:
    backup_id: uuid.UUID
    action: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RetentionPlan:
    generated_at: datetime
    decisions: tuple[RetentionDecision, ...]
    destructive: bool = False


@dataclass(frozen=True)
class BackupCreateConfig:
    destination: Path
    env_file: Path
    recipient_file: Path
    production_project: str


class BackupRunner(Protocol):
    """Small injectable execution seam used by the production operator."""

    def require_tools(self) -> None: ...

    def compose_capture(self, *arguments: str) -> bytes: ...

    def compose_run(self, *arguments: str) -> None: ...

    def compose_encrypt(
        self,
        component: str,
        source_arguments: tuple[str, ...],
        destination: Path,
        recipient: str,
    ) -> None: ...


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BackupContractError("JSON contains a duplicate key")
        result[key] = value
    return result


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, object], bytes]:
    if path.is_symlink() or not path.is_file():
        raise BackupContractError(f"{label} must be a regular file")
    try:
        raw = path.read_bytes()
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except BackupContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BackupContractError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise BackupContractError(f"{label} must be a JSON object")
    return payload, raw


def _require_exact_fields(
    payload: Mapping[str, object], expected: frozenset[str], *, label: str
) -> None:
    if set(payload) != expected:
        raise BackupContractError(f"{label} fields do not exactly match schema version 1")


def _parse_uuid(value: object, *, label: str) -> uuid.UUID:
    if not isinstance(value, str):
        raise BackupContractError(f"{label} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise BackupContractError(f"{label} must be a canonical UUID") from error
    if str(parsed) != value:
        raise BackupContractError(f"{label} must be a canonical lowercase UUID")
    return parsed


def _parse_utc_timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise BackupContractError(f"{label} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise BackupContractError(f"{label} must be a valid UTC timestamp") from error
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise BackupContractError(f"{label} must be in UTC")
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_component_archive(
    value: object, *, component: str, schema_version: int
) -> PurePosixPath:
    suffix = (
        ".tar"
        if schema_version == 1
        else ENCRYPTED_COMPONENT_SUFFIXES.get(component, "")
    )
    expected = PurePosixPath("components") / f"{component}{suffix}"
    if not isinstance(value, str) or value != expected.as_posix():
        raise BackupContractError(
            f"component {component} archive must be {expected.as_posix()}"
        )
    return expected


def _validate_tar_archive(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise BackupContractError("component archive must be a regular file")
    try:
        with tarfile.open(path, mode="r:*") as archive:
            validate_tar_members(archive.getmembers())
    except BackupContractError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise BackupContractError("component archive must be a readable tar archive") from error


def _validate_age_object(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise BackupContractError("encrypted component must be a regular file")
    try:
        with path.open("rb") as handle:
            header = handle.read(len(AGE_HEADER))
    except OSError as error:
        raise BackupContractError("encrypted component must be readable") from error
    if header != AGE_HEADER:
        raise BackupContractError("encrypted component must use age format")


def validate_backup_bundle(bundle_directory: Path) -> ValidatedBackup:
    """Validate a completed backup bundle without mutating or extracting it."""

    root = bundle_directory.resolve()
    if bundle_directory.is_symlink() or not root.is_dir():
        raise BackupContractError("backup bundle must be a regular directory")

    manifest, manifest_bytes = _read_json_object(
        root / "manifest.json", label="manifest"
    )
    schema_version = manifest.get("schemaVersion")
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise BackupContractError("manifest schemaVersion must be 1 or 2")
    _require_exact_fields(
        manifest,
        MANIFEST_FIELDS if schema_version == 1 else MANIFEST_V2_FIELDS,
        label="manifest",
    )
    if schema_version == 2 and manifest.get("mode") != ENCRYPTED_BACKUP_MODE:
        raise BackupContractError("encrypted manifest mode is unsupported")
    backup_id = _parse_uuid(manifest.get("backupId"), label="manifest backupId")
    created_at = _parse_utc_timestamp(
        manifest.get("createdAt"), label="manifest createdAt"
    )
    production_project = manifest.get("productionProject")
    if (
        not isinstance(production_project, str)
        or not production_project
        or production_project.strip() != production_project
    ):
        raise BackupContractError(
            "manifest productionProject must be a non-empty exact value"
        )
    verified_value = manifest.get("verifiedAt")
    verified_at = (
        None
        if verified_value is None
        else _parse_utc_timestamp(verified_value, label="manifest verifiedAt")
    )
    if verified_at is not None and verified_at < created_at:
        raise BackupContractError("manifest verifiedAt cannot precede createdAt")

    raw_components = manifest.get("components")
    if not isinstance(raw_components, list):
        raise BackupContractError("manifest components must be an array")
    expected_components = (
        EXPECTED_COMPONENTS if schema_version == 1 else ENCRYPTED_COMPONENTS
    )
    components: dict[str, ValidatedComponent] = {}
    for raw_component in raw_components:
        if not isinstance(raw_component, dict):
            raise BackupContractError("every manifest component must be an object")
        _require_exact_fields(raw_component, COMPONENT_FIELDS, label="component")
        name = raw_component.get("name")
        if (
            not isinstance(name, str)
            or name not in expected_components
            or name in components
        ):
            raise BackupContractError(
                "component names must be unique required component names"
            )
        archive = _safe_component_archive(
            raw_component.get("archive"),
            component=name,
            schema_version=schema_version,
        )
        byte_count = raw_component.get("bytes")
        digest = raw_component.get("sha256")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 1
        ):
            raise BackupContractError(f"component {name} bytes must be a positive integer")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise BackupContractError(f"component {name} sha256 must be lowercase SHA-256")
        archive_path = root.joinpath(*archive.parts)
        if archive_path.is_symlink() or not archive_path.is_file():
            raise BackupContractError(f"component {name} archive must be a regular file")
        if archive_path.stat().st_size != byte_count:
            raise BackupContractError(f"component {name} byte count does not match")
        if _sha256(archive_path) != digest:
            raise BackupContractError(f"component {name} SHA-256 does not match")
        if schema_version == 1:
            _validate_tar_archive(archive_path)
        else:
            _validate_age_object(archive_path)
        components[name] = ValidatedComponent(name, archive, byte_count, digest)
    if set(components) != set(expected_components):
        raise BackupContractError(
            "manifest must contain every required backup component exactly once"
        )

    marker, _marker_bytes = _read_json_object(root / "COMPLETE", label="COMPLETE marker")
    _require_exact_fields(marker, MARKER_FIELDS, label="COMPLETE marker")
    if (
        type(marker.get("schemaVersion")) is not int
        or marker.get("schemaVersion") != schema_version
    ):
        raise BackupContractError(
            "COMPLETE marker schemaVersion must match the manifest"
        )
    marker_backup_id = _parse_uuid(marker.get("backupId"), label="COMPLETE backupId")
    if marker_backup_id != backup_id:
        raise BackupContractError("COMPLETE marker backupId does not match manifest")
    completed_at = _parse_utc_timestamp(
        marker.get("completedAt"), label="COMPLETE completedAt"
    )
    if completed_at < created_at:
        raise BackupContractError("COMPLETE completedAt cannot precede createdAt")
    if verified_at is not None and completed_at < verified_at:
        raise BackupContractError("COMPLETE completedAt cannot precede verifiedAt")
    manifest_digest = marker.get("manifestSha256")
    if (
        not isinstance(manifest_digest, str)
        or SHA256_RE.fullmatch(manifest_digest) is None
    ):
        raise BackupContractError("COMPLETE manifestSha256 must be lowercase SHA-256")
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_digest:
        raise BackupContractError("COMPLETE marker does not match manifest bytes")

    return ValidatedBackup(
        schema_version=schema_version,
        backup_id=backup_id,
        created_at=created_at,
        production_project=production_project,
        verified_at=verified_at,
        completed_at=completed_at,
        components=tuple(components[name] for name in expected_components),
        raw_manifest=dict(manifest),
    )


def _resolve_tar_link_target(
    member_path: PurePosixPath, target: str, *, relative_to_parent: bool
) -> PurePosixPath:
    if (
        not target
        or "\x00" in target
        or "\\" in target
        or target.startswith("/")
        or WINDOWS_DRIVE_RE.match(target)
    ):
        raise BackupContractError("tar link target must be relative")
    target_path = PurePosixPath(target)
    if target_path.is_absolute():
        raise BackupContractError("tar link target must be relative")
    resolved = list(member_path.parent.parts) if relative_to_parent else []
    for part in target_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not resolved:
                raise BackupContractError("tar link target escapes archive root")
            resolved.pop()
            continue
        resolved.append(part)
    return PurePosixPath(*resolved)


def validate_restore_project_name(name: str, *, production_project: str) -> str:
    """Return a safe isolated Compose project name or fail closed."""

    if (
        not isinstance(production_project, str)
        or not production_project
        or production_project.strip() != production_project
    ):
        raise BackupContractError("production project name must be a non-empty exact value")
    if not isinstance(name, str) or name.strip() != name:
        raise BackupContractError("restore project must use restore-<canonical UUID>")
    if name.casefold() == production_project.casefold():
        raise BackupContractError("restore project must not equal the production project")
    prefix = "restore-"
    if not name.startswith(prefix):
        raise BackupContractError("restore project must use restore-<canonical UUID>")
    restore_id = _parse_uuid(name[len(prefix) :], label="restore project UUID")
    canonical = f"{prefix}{restore_id}"
    if name != canonical:
        raise BackupContractError("restore project must use restore-<canonical UUID>")
    return name


def _as_utc(value: datetime, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BackupContractError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def plan_retention(
    records: Iterable[RetentionRecord],
    *,
    now: datetime,
    max_age_days: int = 30,
    keep_verified: int = 7,
) -> RetentionPlan:
    """Compute retention decisions; this function performs no filesystem I/O."""

    if (
        isinstance(max_age_days, bool)
        or not isinstance(max_age_days, int)
        or max_age_days < 0
    ):
        raise BackupContractError("max_age_days must be a non-negative integer")
    if (
        isinstance(keep_verified, bool)
        or not isinstance(keep_verified, int)
        or keep_verified < 0
    ):
        raise BackupContractError("keep_verified must be a non-negative integer")
    generated_at = _as_utc(now, label="retention plan time")
    materialized = tuple(records)
    seen: set[uuid.UUID] = set()
    normalized: list[tuple[RetentionRecord, datetime, datetime | None]] = []
    for record in materialized:
        if not isinstance(record, RetentionRecord) or not isinstance(
            record.backup_id, uuid.UUID
        ):
            raise BackupContractError("retention records must use UUID backup identifiers")
        if record.backup_id in seen:
            raise BackupContractError("retention records must have unique backup identifiers")
        seen.add(record.backup_id)
        if type(record.legal_hold) is not bool:
            raise BackupContractError("retention legal_hold must be boolean")
        created_at = _as_utc(record.created_at, label="retention created_at")
        verified_at = (
            None
            if record.verified_at is None
            else _as_utc(record.verified_at, label="retention verified_at")
        )
        if created_at > generated_at:
            raise BackupContractError("retention created_at cannot be in the future")
        if verified_at is not None and verified_at < created_at:
            raise BackupContractError("retention verified_at cannot precede created_at")
        if verified_at is not None and verified_at > generated_at:
            raise BackupContractError("retention verified_at cannot be in the future")
        normalized.append((record, created_at, verified_at))

    latest_backup = max(
        normalized,
        key=lambda item: (item[1], str(item[0].backup_id)),
        default=None,
    )
    verified = sorted(
        (item for item in normalized if item[2] is not None),
        key=lambda item: (item[2], item[1], str(item[0].backup_id)),
        reverse=True,
    )
    latest_verified_id = verified[0][0].backup_id if verified else None
    kept_verified_ids = {item[0].backup_id for item in verified[:keep_verified]}
    cutoff = generated_at - timedelta(days=max_age_days)

    decisions: list[RetentionDecision] = []
    for record, created_at, _verified_at in sorted(
        normalized,
        key=lambda item: (item[1], str(item[0].backup_id)),
        reverse=True,
    ):
        reasons: list[str] = []
        if record.legal_hold:
            reasons.append("legal_hold")
        if record.backup_id == latest_verified_id:
            reasons.append("latest_verified")
        if record.backup_id in kept_verified_ids:
            reasons.append("verified_retention_count")
        if latest_backup is not None and record.backup_id == latest_backup[0].backup_id:
            reasons.append("latest_backup")
        if created_at >= cutoff:
            reasons.append("within_retention_window")
        action = "keep" if reasons else "delete_candidate"
        if not reasons:
            reasons.append("expired_unprotected")
        decisions.append(RetentionDecision(record.backup_id, action, tuple(reasons)))

    return RetentionPlan(generated_at, tuple(decisions), destructive=False)


def load_retention_catalog(path: Path) -> tuple[RetentionRecord, ...]:
    """Load a strict, non-secret retention catalog for read-only planning."""

    payload, _raw = _read_json_object(path, label="retention catalog")
    _require_exact_fields(payload, RETENTION_CATALOG_FIELDS, label="retention catalog")
    if (
        type(payload.get("schemaVersion")) is not int
        or payload.get("schemaVersion") != 1
    ):
        raise BackupContractError("retention catalog schemaVersion must be 1")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise BackupContractError("retention catalog records must be an array")
    records: list[RetentionRecord] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            raise BackupContractError("every retention catalog record must be an object")
        _require_exact_fields(
            raw_record, RETENTION_RECORD_FIELDS, label="retention record"
        )
        legal_hold = raw_record.get("legalHold")
        if type(legal_hold) is not bool:
            raise BackupContractError("retention legalHold must be boolean")
        verified_value = raw_record.get("verifiedAt")
        records.append(
            RetentionRecord(
                backup_id=_parse_uuid(
                    raw_record.get("backupId"), label="retention backupId"
                ),
                created_at=_parse_utc_timestamp(
                    raw_record.get("createdAt"), label="retention createdAt"
                ),
                verified_at=(
                    None
                    if verified_value is None
                    else _parse_utc_timestamp(
                        verified_value, label="retention verifiedAt"
                    )
                ),
                legal_hold=legal_hold,
            )
        )
    return tuple(records)


def _format_utc(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


MYSQL_DUMP_SCRIPT = """set -eu
export MYSQL_PWD="$(cat "$MYSQL_ROOT_PASSWORD_FILE")"
exec mysqldump --protocol=socket --user=root --single-transaction --quick \
  --skip-lock-tables --no-tablespaces --routines --events --triggers \
  --hex-blob --set-gtid-purged=OFF --databases "$MYSQL_DATABASE"
"""
AUDIT_DUMP_SCRIPT = """set -eu
export MYSQL_PWD="$(cat "$MYSQL_ROOT_PASSWORD_FILE")"
exec mysqldump --protocol=socket --user=root --single-transaction --quick \
  --skip-lock-tables --no-tablespaces --triggers --hex-blob \
  --set-gtid-purged=OFF "$MYSQL_DATABASE" operation_log audit_retention_state
"""
REDIS_RDB_SCRIPT = """set -eu
export REDISCLI_AUTH="$(cat "$REDIS_PASSWORD_FILE")"
exec redis-cli --no-auth-warning --rdb /dev/stdout
"""


def _read_age_recipient(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise BackupContractError("age recipient file must be a regular file")
    try:
        raw = path.read_bytes()
        recipient = raw.decode("ascii").rstrip("\n")
    except (OSError, UnicodeError) as error:
        raise BackupContractError("age recipient file must be readable ASCII") from error
    if (
        b"\x00" in raw
        or b"\r" in raw
        or raw not in (recipient.encode("ascii"), recipient.encode("ascii") + b"\n")
        or AGE_RECIPIENT_RE.fullmatch(recipient) is None
    ):
        raise BackupContractError(
            "age recipient file must contain one native age recipient"
        )
    return recipient


def _validate_production_project(value: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", value) is None
    ):
        raise BackupContractError("production project name is invalid")
    if value.startswith("restore-"):
        raise BackupContractError("production project must not use the restore namespace")
    return value


def _fsync_file(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError as error:
        raise BackupContractError("backup output could not be durably written") from error


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise BackupContractError("backup directory could not be durably written") from error


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    data = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except FileExistsError as error:
        raise BackupContractError("backup metadata temporary file already exists") from error
    except OSError as error:
        raise BackupContractError("backup metadata could not be written") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _remove_created_directory(path: Path, *, parent: Path) -> None:
    """Remove only an exact, newly-created child directory after a failed run."""

    resolved_parent = parent.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_parent or not path.name.startswith(".backup-"):
        raise BackupContractError("refused unsafe incomplete-backup cleanup")
    if path.exists():
        shutil.rmtree(path)


def _component_source_arguments(component: str) -> tuple[str, ...]:
    if component == "mysql_data":
        return ("exec", "-T", "mysql", "sh", "-ec", MYSQL_DUMP_SCRIPT)
    if component == "audit_data":
        return ("exec", "-T", "mysql", "sh", "-ec", AUDIT_DUMP_SCRIPT)
    if component == "redis_data":
        return ("exec", "-T", "redis", "sh", "-ec", REDIS_RDB_SCRIPT)
    if component in ("api_uploads", "api_data"):
        source = "/app/uploads" if component == "api_uploads" else "/app/data"
        return (
            "run",
            "--rm",
            "--no-deps",
            "--read-only",
            "--entrypoint",
            "tar",
            "api",
            "--numeric-owner",
            "--format=pax",
            "-C",
            source,
            "-cf",
            "-",
            ".",
        )
    raise BackupContractError("unknown backup component")


def create_backup(
    config: BackupCreateConfig,
    *,
    runner: BackupRunner,
    backup_id: uuid.UUID | None = None,
    now: Callable[[], datetime] | None = None,
) -> Path:
    """Create one encrypted bundle and publish it by an atomic directory rename."""

    if not isinstance(config, BackupCreateConfig):
        raise BackupContractError("backup creation configuration is invalid")
    identifier = uuid.uuid4() if backup_id is None else backup_id
    if not isinstance(identifier, uuid.UUID) or identifier.version != 4:
        raise BackupContractError("backup identifier must be a version 4 UUID")
    clock = (lambda: datetime.now(timezone.utc)) if now is None else now
    created_at = _as_utc(clock(), label="backup creation time")
    project = _validate_production_project(config.production_project)
    destination = config.destination.resolve()
    if config.destination.is_symlink() or not destination.is_dir():
        raise BackupContractError("backup destination must be an existing regular directory")
    recipient = _read_age_recipient(config.recipient_file)
    staging = destination / f".backup-{identifier}.partial"
    final = destination / f"backup-{identifier}"
    if staging.exists() or staging.is_symlink() or final.exists() or final.is_symlink():
        raise BackupContractError("backup output identifier already exists")

    runner.require_tools()
    running = {
        line.strip()
        for line in runner.compose_capture("ps", "--services", "--status", "running")
        .decode("utf-8", errors="strict")
        .splitlines()
        if line.strip()
    }
    required_running = {"mysql", "redis", "api", "worker"}
    if not required_running.issubset(running):
        raise BackupContractError("required production services are not all running")

    components: list[dict[str, object]] = []
    restart_required = False
    published = False
    try:
        staging.mkdir(mode=0o700)
        component_directory = staging / "components"
        component_directory.mkdir(mode=0o700)

        restart_required = True
        runner.compose_run("stop", "--timeout", "370", "worker", "api")
        for component in (
            "mysql_data",
            "audit_data",
            "redis_data",
            "api_uploads",
            "api_data",
        ):
            suffix = ENCRYPTED_COMPONENT_SUFFIXES[component]
            archive = component_directory / f"{component}{suffix}"
            runner.compose_encrypt(
                component,
                _component_source_arguments(component),
                archive,
                recipient,
            )
            _validate_age_object(archive)
            _fsync_file(archive)
            components.append(
                {
                    "name": component,
                    "archive": f"components/{component}{suffix}",
                    "bytes": archive.stat().st_size,
                    "sha256": _sha256(archive),
                }
            )

        runner.compose_run("start", "api", "worker")
        restart_required = False

        component_by_name = {item["name"]: item for item in components}
        manifest = {
            "schemaVersion": 2,
            "backupId": str(identifier),
            "createdAt": _format_utc(created_at),
            "productionProject": project,
            "verifiedAt": None,
            "mode": ENCRYPTED_BACKUP_MODE,
            "components": [
                component_by_name[name] for name in ENCRYPTED_COMPONENTS
            ],
        }
        manifest_path = staging / "manifest.json"
        _write_json_atomic(manifest_path, manifest)
        completed_at = _as_utc(clock(), label="backup completion time")
        if completed_at < created_at:
            raise BackupContractError("backup completion time cannot precede creation")
        _write_json_atomic(
            staging / "COMPLETE",
            {
                "schemaVersion": 2,
                "backupId": str(identifier),
                "completedAt": _format_utc(completed_at),
                "manifestSha256": _sha256(manifest_path),
            },
        )
        validate_backup_bundle(staging)
        _fsync_directory(component_directory)
        _fsync_directory(staging)
        os.replace(staging, final)
        published = True
        _fsync_directory(destination)
        return final
    except (UnicodeError, OSError, subprocess.SubprocessError) as error:
        raise BackupContractError("encrypted backup creation failed") from error
    finally:
        if restart_required:
            try:
                runner.compose_run("start", "api", "worker")
            except Exception as restart_error:
                if sys.exc_info()[0] is None:
                    raise BackupContractError(
                        "production writers could not be restarted"
                    ) from restart_error
        if not published and staging.exists():
            _remove_created_directory(staging, parent=destination)


class _NoEchoArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid command arguments\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _NoEchoArgumentParser(
        description=(
            "Validate backup evidence and compute non-destructive "
            "restore/retention plans."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_bundle = commands.add_parser(
        "validate-bundle",
        help="validate manifest, COMPLETE marker, hashes, and tar safety",
    )
    validate_bundle.add_argument("--bundle", required=True, type=Path)

    validate_restore = commands.add_parser(
        "validate-restore-project", help="validate an isolated restore project name"
    )
    validate_restore.add_argument("--project", required=True)
    validate_restore.add_argument("--production-project", required=True)

    retention = commands.add_parser(
        "plan-retention", help="print a non-destructive retention plan"
    )
    retention.add_argument("--catalog", required=True, type=Path)
    retention.add_argument("--as-of", help="RFC 3339 UTC timestamp; defaults to current UTC")
    retention.add_argument("--max-age-days", type=int, default=30)
    retention.add_argument("--keep-verified", type=int, default=7)
    return parser


def _contains_sensitive_option(arguments: Iterable[str]) -> bool:
    for argument in arguments:
        if not argument.startswith("--"):
            continue
        option = argument.split("=", 1)[0][2:]
        words = {word for word in re.split(r"[-_]", option.casefold()) if word}
        if words & SENSITIVE_OPTION_WORDS:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _contains_sensitive_option(arguments):
        print("ERROR: secret-bearing command-line options are forbidden")
        return 2
    parser = _build_parser()
    args = parser.parse_args(arguments)
    try:
        if args.command == "validate-bundle":
            backup = validate_backup_bundle(args.bundle)
            print(
                f"VALID backup bundle {backup.backup_id}; "
                f"components={len(backup.components)}"
            )
            return 0
        if args.command == "validate-restore-project":
            project = validate_restore_project_name(
                args.project, production_project=args.production_project
            )
            print(f"VALID isolated restore project {project}")
            return 0
        if args.command == "plan-retention":
            records = load_retention_catalog(args.catalog)
            as_of = (
                datetime.now(timezone.utc)
                if args.as_of is None
                else _parse_utc_timestamp(args.as_of, label="retention as-of")
            )
            plan = plan_retention(
                records,
                now=as_of,
                max_age_days=args.max_age_days,
                keep_verified=args.keep_verified,
            )
            output = {
                "schemaVersion": 1,
                "mode": "plan",
                "destructive": plan.destructive,
                "generatedAt": _format_utc(plan.generated_at),
                "decisions": [
                    {
                        "backupId": str(decision.backup_id),
                        "action": decision.action,
                        "reasons": list(decision.reasons),
                    }
                    for decision in plan.decisions
                ],
            }
            print(json.dumps(output, ensure_ascii=True, sort_keys=True))
            return 0
    except BackupContractError as error:
        print(f"ERROR: {error}")
        return 2
    parser.error("unknown command")
    return 2


def validate_tar_members(members: Iterable[tarfile.TarInfo]) -> None:
    """Validate tar metadata without extracting any member."""

    seen: set[PurePosixPath] = set()
    for member in members:
        name = member.name
        if (
            not name
            or "\x00" in name
            or "\\" in name
            or name.startswith("/")
            or WINDOWS_DRIVE_RE.match(name)
        ):
            raise BackupContractError("tar member path must be relative")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise BackupContractError("tar member path traversal is forbidden")
        if path in seen:
            raise BackupContractError("duplicate tar member paths are forbidden")
        seen.add(path)
        if member.isdev():
            raise BackupContractError("tar device and FIFO members are forbidden")
        if member.type not in SAFE_TAR_MEMBER_TYPES:
            raise BackupContractError("unsupported tar member type is forbidden")
        if member.issym():
            _resolve_tar_link_target(path, member.linkname, relative_to_parent=True)
        elif member.islnk():
            _resolve_tar_link_target(path, member.linkname, relative_to_parent=False)


__all__ = [
    "BackupContractError",
    "EXPECTED_COMPONENTS",
    "RetentionDecision",
    "RetentionPlan",
    "RetentionRecord",
    "ValidatedBackup",
    "ValidatedComponent",
    "load_retention_catalog",
    "main",
    "plan_retention",
    "validate_backup_bundle",
    "validate_restore_project_name",
    "validate_tar_members",
]


if __name__ == "__main__":
    raise SystemExit(main())
