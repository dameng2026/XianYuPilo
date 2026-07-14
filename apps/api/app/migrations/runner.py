from __future__ import annotations

import logging
import re
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
DEFAULT_LOCK_NAME = "xianyu_assistant_schema_migration"
_MIGRATION_FILE = re.compile(
    r"^(?P<version>\d+)[_-](?P<description>[A-Za-z0-9][A-Za-z0-9_-]*)\.sql$",
    re.IGNORECASE,
)

_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migration (
  version VARCHAR(64) NOT NULL,
  description VARCHAR(255) NOT NULL,
  checksum CHAR(64) NULL,
  applied_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Applied database migrations'
""".strip()


class MigrationDiscoveryError(ValueError):
    """The migration directory is missing, ambiguous, or malformed."""


class SQLParseError(ValueError):
    """A migration script cannot be split safely into driver statements."""


class MigrationLockError(RuntimeError):
    """Another migration runner owns the database advisory lock."""


class SchemaDriftError(RuntimeError):
    """The database contains versions unknown to this application build."""

    def __init__(self, unknown: tuple[str, ...]) -> None:
        self.unknown = unknown
        super().__init__(
            "database migration history contains unknown version(s): "
            + ", ".join(unknown)
        )


class MigrationChecksumError(RuntimeError):
    """An already-recorded migration no longer matches its SQL file."""

    def __init__(self, modified: tuple[str, ...]) -> None:
        self.modified = modified
        super().__init__(
            "applied migration checksum mismatch for version(s): "
            + ", ".join(modified)
        )


class PendingMigrationsError(RuntimeError):
    """The application build and database schema are not compatible yet."""

    def __init__(
        self,
        pending: tuple[str, ...],
        unknown: tuple[str, ...] = (),
        modified: tuple[str, ...] = (),
        unverified: tuple[str, ...] = (),
        integrity_supported: bool = True,
    ) -> None:
        self.pending = pending
        self.unknown = unknown
        self.modified = modified
        self.unverified = unverified
        self.integrity_supported = integrity_supported
        parts: list[str] = []
        if pending:
            parts.append("pending=" + ",".join(pending))
        if unknown:
            parts.append("unknown=" + ",".join(unknown))
        if modified:
            parts.append("modified=" + ",".join(modified))
        if unverified:
            parts.append("unverified=" + ",".join(unverified))
        if not integrity_supported:
            parts.append("history-metadata=legacy")
        super().__init__("database schema is not current (" + "; ".join(parts) + ")")


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    description: str
    path: Path
    source: str
    checksum: str


@dataclass(frozen=True, slots=True)
class SchemaStatus:
    available: tuple[str, ...]
    applied: tuple[str, ...]
    pending: tuple[str, ...]
    unknown: tuple[str, ...]
    history_exists: bool
    integrity_supported: bool
    modified: tuple[str, ...]
    unverified: tuple[str, ...]

    @property
    def current(self) -> bool:
        return (
            self.history_exists
            and self.integrity_supported
            and not self.pending
            and not self.unknown
            and not self.modified
            and not self.unverified
        )


@dataclass(frozen=True, slots=True)
class UpgradeResult:
    applied: tuple[str, ...]
    skipped: tuple[str, ...]


def discover_migrations(directory: Path | str = DEFAULT_MIGRATIONS_DIR) -> tuple[Migration, ...]:
    """Discover every numbered SQL file and return strict numeric order.

    Unnumbered SQL files and duplicate numeric versions are rejected instead of
    being silently omitted. This makes adding a future ``004``/``005`` file an
    automatic operation while preventing two releases from claiming one slot.
    """

    root = Path(directory).resolve()
    if not root.is_dir():
        raise MigrationDiscoveryError(f"migration directory does not exist: {root}")

    migrations: list[Migration] = []
    seen_numbers: dict[int, Path] = {}
    for path in sorted(root.glob("*.sql"), key=lambda item: item.name.casefold()):
        match = _MIGRATION_FILE.fullmatch(path.name)
        if match is None:
            raise MigrationDiscoveryError(
                f"migration filename must be <number>_<description>.sql: {path.name}"
            )
        version = match.group("version")
        if len(version) > 64:
            raise MigrationDiscoveryError(
                f"migration version exceeds 64 characters: {path.name}"
            )
        numeric_version = int(version)
        previous = seen_numbers.get(numeric_version)
        if previous is not None:
            raise MigrationDiscoveryError(
                "duplicate migration version "
                f"{numeric_version}: {previous.name}, {path.name}"
            )
        seen_numbers[numeric_version] = path
        description = match.group("description").replace("_", " ").replace("-", " ")
        if len(description) > 255:
            raise MigrationDiscoveryError(
                f"migration description exceeds 255 characters: {path.name}"
            )
        try:
            source = path.read_text(encoding="utf-8").lstrip("\ufeff")
        except UnicodeError as exc:
            raise MigrationDiscoveryError(
                f"migration must be valid UTF-8: {path.name}"
            ) from exc
        migrations.append(
            Migration(
                version=version,
                description=description,
                path=path.resolve(),
                source=source,
                checksum=sha256(source.encode("utf-8")).hexdigest(),
            )
        )

    if not migrations:
        raise MigrationDiscoveryError(f"no numbered SQL migrations found in {root}")

    migrations.sort(key=lambda migration: (int(migration.version), migration.version))
    return tuple(migrations)


def split_sql_script(script: str) -> tuple[str, ...]:
    """Split MySQL SQL at semicolons outside strings, identifiers, and comments.

    The parser intentionally supports ordinary migration DDL/DML and prepared
    statements, including MySQL doubled-quote and backslash escaping. Stored
    procedure ``DELIMITER`` directives are outside this runner's interface and
    should be placed behind an explicit future parser extension.
    """

    source = script.lstrip("\ufeff")
    statements: list[str] = []
    buffer: list[str] = []
    state = "normal"
    quote = ""
    block_is_executable = False
    index = 0

    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""

        if state == "line_comment":
            if char in "\r\n":
                buffer.append(char)
                state = "normal"
            index += 1
            continue

        if state == "block_comment":
            if block_is_executable:
                buffer.append(char)
            if char == "*" and following == "/":
                if block_is_executable:
                    buffer.append(following)
                else:
                    buffer.append(" ")
                index += 2
                state = "normal"
                block_is_executable = False
                continue
            index += 1
            continue

        if state == "quoted":
            buffer.append(char)
            if char == "\\" and index + 1 < len(source):
                buffer.append(source[index + 1])
                index += 2
                continue
            if char == quote:
                if following == quote:
                    buffer.append(following)
                    index += 2
                    continue
                state = "normal"
                quote = ""
            index += 1
            continue

        if char in {"'", '"', "`"}:
            state = "quoted"
            quote = char
            buffer.append(char)
            index += 1
            continue

        if char == "#":
            state = "line_comment"
            index += 1
            continue

        if (
            char == "-"
            and following == "-"
            and (index + 2 >= len(source) or source[index + 2].isspace())
        ):
            state = "line_comment"
            index += 2
            continue

        if char == "/" and following == "*":
            block_is_executable = index + 2 < len(source) and source[index + 2] in {"!", "+"}
            state = "block_comment"
            if block_is_executable:
                buffer.extend((char, following))
            index += 2
            continue

        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                if re.match(r"(?is)^\s*DELIMITER\b", statement):
                    raise SQLParseError("DELIMITER directives are not supported")
                statements.append(statement)
            buffer.clear()
            index += 1
            continue

        buffer.append(char)
        index += 1

    if state == "quoted":
        raise SQLParseError("unterminated quoted string or identifier")
    if state == "block_comment":
        raise SQLParseError("unterminated block comment")

    trailing = "".join(buffer).strip()
    if trailing:
        if re.match(r"(?is)^\s*DELIMITER\b", trailing):
            raise SQLParseError("DELIMITER directives are not supported")
        statements.append(trailing)
    return tuple(statements)


class MigrationRunner:
    """Apply and inspect versioned migrations through one database connection."""

    def __init__(
        self,
        engine: Any,
        migrations_dir: Path | str = DEFAULT_MIGRATIONS_DIR,
        *,
        lock_name: str = DEFAULT_LOCK_NAME,
        lock_timeout_seconds: int = 30,
    ) -> None:
        if not 1 <= lock_timeout_seconds <= 300:
            raise ValueError("lock_timeout_seconds must be between 1 and 300")
        if not lock_name or len(lock_name.encode("utf-8")) > 64:
            raise ValueError("lock_name must be between 1 and 64 UTF-8 bytes")
        self._engine = engine
        self._migrations_dir = Path(migrations_dir)
        self._lock_name = lock_name
        self._lock_timeout_seconds = lock_timeout_seconds

    def migrations(self) -> tuple[Migration, ...]:
        return discover_migrations(self._migrations_dir)

    async def status(self) -> SchemaStatus:
        migrations = self.migrations()
        async with self._engine.connect() as connection:
            history_exists = await self._history_exists(connection)
            integrity_supported = (
                await self._checksum_column_exists(connection) if history_exists else False
            )
            history = (
                await self._read_history(
                    connection,
                    integrity_supported=integrity_supported,
                )
                if history_exists
                else {}
            )
        return self._build_status(
            migrations,
            history,
            history_exists=history_exists,
            integrity_supported=integrity_supported,
        )

    async def assert_current(self) -> SchemaStatus:
        status = await self.status()
        if not status.current:
            raise PendingMigrationsError(
                status.pending,
                status.unknown,
                status.modified,
                status.unverified,
                status.integrity_supported,
            )
        return status

    async def upgrade(self) -> UpgradeResult:
        migrations = self.migrations()
        applied_now: list[str] = []
        acquired = False

        async with self._engine.connect() as connection:
            try:
                lock = await connection.execute(
                    text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
                    {
                        "lock_name": self._lock_name,
                        "timeout_seconds": self._lock_timeout_seconds,
                    },
                )
                if lock.scalar() != 1:
                    raise MigrationLockError(
                        "database migration lock was unavailable before the timeout"
                    )
                acquired = True

                await connection.execute(text(_HISTORY_TABLE_SQL))
                await connection.commit()
                if not await self._checksum_column_exists(connection):
                    # Legacy 002 installations created the history table before
                    # checksums existed. The advisory lock makes this metadata
                    # upgrade single-flight and interruption-safe.
                    await connection.exec_driver_sql(
                        "ALTER TABLE schema_migration "
                        "ADD COLUMN checksum CHAR(64) NULL AFTER description"
                    )
                    await connection.commit()

                history = await self._read_history(
                    connection,
                    integrity_supported=True,
                )
                applied = set(history)
                known = {migration.version for migration in migrations}
                unknown = tuple(sorted(applied - known))
                if unknown:
                    raise SchemaDriftError(unknown)

                migrations_by_version = {
                    migration.version: migration for migration in migrations
                }
                modified = tuple(
                    version
                    for version, recorded_checksum in history.items()
                    if recorded_checksum
                    and recorded_checksum != migrations_by_version[version].checksum
                )
                if modified:
                    raise MigrationChecksumError(modified)

                # Existing history rows without checksums are trusted once at
                # adoption, then pinned. There is no truthful way to reconstruct
                # the exact bytes used by an older manual migration.
                unverified = tuple(
                    version for version, checksum in history.items() if not checksum
                )
                for version in unverified:
                    migration = migrations_by_version[version]
                    await connection.execute(
                        text(
                            "UPDATE schema_migration "
                            "SET checksum = :checksum, description = :description "
                            "WHERE version = :version AND checksum IS NULL"
                        ),
                        {
                            "version": version,
                            "description": migration.description,
                            "checksum": migration.checksum,
                        },
                    )
                if unverified:
                    await connection.commit()

                for migration in migrations:
                    if migration.version in applied:
                        continue
                    statements = split_sql_script(migration.source)
                    if not statements:
                        raise SQLParseError(
                            f"migration contains no executable SQL: {migration.path.name}"
                        )
                    try:
                        for statement in statements:
                            await connection.exec_driver_sql(statement)
                        await connection.execute(
                            text(
                                "INSERT INTO schema_migration "
                                "(version, description, checksum) "
                                "VALUES (:version, :description, :checksum)"
                            ),
                            {
                                "version": migration.version,
                                "description": migration.description,
                                "checksum": migration.checksum,
                            },
                        )
                        await connection.commit()
                    except BaseException:
                        try:
                            await connection.rollback()
                        except Exception:
                            logger.warning(
                                "Rollback after failed database migration also failed",
                                exc_info=True,
                            )
                        raise
                    applied.add(migration.version)
                    applied_now.append(migration.version)
                    logger.info(
                        "Applied database migration version=%s file=%s",
                        migration.version,
                        migration.path.name,
                    )
            finally:
                if acquired:
                    # A failed 001 may have disabled FK checks, and a failed
                    # PREPARE/EXECUTE sequence may leave its named statement on
                    # a pooled connection. Restore session safety before the
                    # connection can return to the pool; connection loss still
                    # releases both resources server-side.
                    try:
                        await connection.exec_driver_sql(
                            "SET @migration_cleanup = 'SELECT 1'"
                        )
                        # MySQL implicitly deallocates an existing prepared
                        # statement when the same name is prepared again.
                        await connection.exec_driver_sql(
                            "PREPARE migration_stmt FROM @migration_cleanup"
                        )
                        await connection.exec_driver_sql(
                            "DEALLOCATE PREPARE migration_stmt"
                        )
                    except Exception:
                        pass
                    try:
                        await connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
                    except Exception:
                        logger.warning(
                            "Failed to restore migration connection session safeguards",
                            exc_info=True,
                        )
                    try:
                        await connection.execute(
                            text("SELECT RELEASE_LOCK(:lock_name)"),
                            {"lock_name": self._lock_name},
                        )
                    except Exception:
                        logger.warning("Failed to release database migration lock", exc_info=True)

        applied_set = set(applied_now)
        skipped = tuple(
            migration.version for migration in migrations if migration.version not in applied_set
        )
        return UpgradeResult(applied=tuple(applied_now), skipped=skipped)

    @staticmethod
    async def _history_exists(connection: Any) -> bool:
        result = await connection.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'schema_migration'"
            )
        )
        return bool(result.scalar() or 0)

    @staticmethod
    async def _checksum_column_exists(connection: Any) -> bool:
        result = await connection.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'schema_migration' "
                "AND COLUMN_NAME = 'checksum'"
            )
        )
        return bool(result.scalar() or 0)

    @staticmethod
    async def _read_history(
        connection: Any,
        *,
        integrity_supported: bool,
    ) -> dict[str, str | None]:
        if integrity_supported:
            result = await connection.execute(
                text("SELECT version, checksum FROM schema_migration ORDER BY version")
            )
            return {
                str(row[0]): str(row[1]) if row[1] else None
                for row in result.all()
            }
        result = await connection.execute(
            text("SELECT version FROM schema_migration ORDER BY version")
        )
        return {str(row[0]): None for row in result.all()}

    @staticmethod
    def _build_status(
        migrations: tuple[Migration, ...],
        history: dict[str, str | None],
        *,
        history_exists: bool,
        integrity_supported: bool,
    ) -> SchemaStatus:
        available = tuple(migration.version for migration in migrations)
        available_set = set(available)
        applied_set = set(history)
        pending = tuple(version for version in available if version not in applied_set)
        unknown = tuple(sorted(applied_set - available_set))
        migrations_by_version = {
            migration.version: migration for migration in migrations
        }
        modified = tuple(
            version
            for version, checksum in history.items()
            if version in migrations_by_version
            and checksum
            and checksum != migrations_by_version[version].checksum
        )
        unverified = tuple(
            version
            for version, checksum in history.items()
            if version in migrations_by_version and not checksum
        )
        return SchemaStatus(
            available=available,
            applied=tuple(sorted(history)),
            pending=pending,
            unknown=unknown,
            history_exists=history_exists,
            integrity_supported=integrity_supported,
            modified=modified,
            unverified=unverified,
        )


def _default_runner() -> MigrationRunner:
    from app.core.database import engine

    return MigrationRunner(engine)


async def get_schema_status() -> SchemaStatus:
    return await _default_runner().status()


async def assert_schema_current() -> SchemaStatus:
    return await _default_runner().assert_current()


async def upgrade_schema() -> UpgradeResult:
    from app.core.config import settings
    from app.core.database import create_configured_engine

    migration_engine = create_configured_engine(settings.mysql_migration_url)
    try:
        return await MigrationRunner(migration_engine).upgrade()
    finally:
        await migration_engine.dispose()
