from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .runner import (
    MigrationChecksumError,
    MigrationDiscoveryError,
    MigrationLockError,
    MigrationRunner,
    SQLParseError,
    SchemaDriftError,
)


async def _run(command: str) -> int:
    from app.core.config import settings
    from app.core.database import create_configured_engine

    engine = create_configured_engine(settings.mysql_migration_url)
    runner = MigrationRunner(engine)
    try:
        if command == "upgrade":
            result = await runner.upgrade()
            print(
                json.dumps(
                    {
                        "status": "current",
                        "applied": list(result.applied),
                        "skipped": list(result.skipped),
                    },
                    separators=(",", ":"),
                )
            )
            return 0

        status = await runner.status()
        print(
            json.dumps(
                {
                    "status": "current" if status.current else "pending",
                    "historyExists": status.history_exists,
                    "applied": list(status.applied),
                    "pending": list(status.pending),
                    "unknown": list(status.unknown),
                    "modified": list(status.modified),
                    "unverified": list(status.unverified),
                    "integritySupported": status.integrity_supported,
                },
                separators=(",", ":"),
            )
        )
        return 0 if status.current else 3
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.migrations",
        description="Inspect or apply Xianyu Assistant database migrations",
    )
    parser.add_argument("command", choices=("upgrade", "status"))
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        return asyncio.run(_run(args.command))
    except Exception as exc:
        # Never render the SQLAlchemy URL. Migration/version information is
        # useful; connection credentials and resolved environment are not.
        from app.core.logging_security import safe_exception_message

        safe_domain_error = isinstance(
            exc,
            (
                MigrationChecksumError,
                MigrationDiscoveryError,
                MigrationLockError,
                SQLParseError,
                SchemaDriftError,
            ),
        )
        detail = (
            safe_exception_message(exc)
            if safe_domain_error
            else "database operation failed; connection details were suppressed"
        )
        print(
            "migration command failed "
            f"({type(exc).__name__}): {detail}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
