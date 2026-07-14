"""Versioned database migration interface.

Callers only need :class:`MigrationRunner` (or the convenience functions at
the bottom of this module). SQL discovery, parsing, locking, and history
bookkeeping stay behind that interface.
"""

from .runner import (
    Migration,
    MigrationDiscoveryError,
    MigrationChecksumError,
    MigrationLockError,
    MigrationRunner,
    PendingMigrationsError,
    SQLParseError,
    SchemaDriftError,
    SchemaStatus,
    UpgradeResult,
    assert_schema_current,
    discover_migrations,
    get_schema_status,
    split_sql_script,
    upgrade_schema,
)

__all__ = [
    "Migration",
    "MigrationDiscoveryError",
    "MigrationChecksumError",
    "MigrationLockError",
    "MigrationRunner",
    "PendingMigrationsError",
    "SQLParseError",
    "SchemaDriftError",
    "SchemaStatus",
    "UpgradeResult",
    "assert_schema_current",
    "discover_migrations",
    "get_schema_status",
    "split_sql_script",
    "upgrade_schema",
]
