"""Bounded, cross-replica retention for the authoritative operation log."""

from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
_LOCK_NAME = "xya:audit-log-retention"


async def _release_lock(db: AsyncSession) -> None:
    """Release the named lock while the session still owns its DB connection."""

    result = await db.execute(
        text("SELECT RELEASE_LOCK(:lock_name)"),
        {"lock_name": _LOCK_NAME},
    )
    if int(result.scalar() or 0) != 1:
        raise RuntimeError("audit retention named lock was not released by its owner")


async def run_audit_retention_once(
    db: AsyncSession,
    *,
    retention_days: int,
    batch_size: int = 10_000,
    idle_interval_seconds: int = 3_600,
    backlog_interval_seconds: int = 60,
) -> dict[str, int | bool]:
    """Delete one bounded batch only when the durable schedule is due.

    A MySQL named lock prevents multiple worker replicas from performing the
    same maintenance batch. The singleton row survives restarts and throttles
    both idle checks and large-backlog draining.
    """
    if not 1 <= int(retention_days) <= 3650:
        raise ValueError("retention_days must be between 1 and 3650")
    if not 1 <= int(batch_size) <= 100_000:
        raise ValueError("batch_size must be between 1 and 100000")
    if not 60 <= int(idle_interval_seconds) <= 86_400:
        raise ValueError("idle_interval_seconds must be between 60 and 86400")
    if not 10 <= int(backlog_interval_seconds) <= 3_600:
        raise ValueError("backlog_interval_seconds must be between 10 and 3600")

    lock_result = await db.execute(
        text("SELECT GET_LOCK(:lock_name, 0)"),
        {"lock_name": _LOCK_NAME},
    )
    if int(lock_result.scalar() or 0) != 1:
        return {"ran": False, "deleted": 0, "lockAcquired": False}

    lock_acquired = True
    try:
        state = (
            await db.execute(
                text(
                    """
                    SELECT
                        next_run_at,
                        CASE
                            WHEN next_run_at IS NULL OR next_run_at <= NOW() THEN 1
                            ELSE 0
                        END AS is_due
                    FROM audit_retention_state
                    WHERE id = 1
                    FOR UPDATE
                    """
                )
            )
        ).first()
        is_due = bool(state[1]) if state else True
        if not is_due:
            # RELEASE_LOCK is connection-scoped. Release it before rollback can
            # return that connection to the pool and make a later execute use a
            # different MySQL session.
            await _release_lock(db)
            lock_acquired = False
            await db.rollback()
            return {"ran": False, "deleted": 0, "lockAcquired": True}

        delete_result = await db.execute(
            text(
                f"""
                DELETE FROM operation_log
                WHERE created_time < DATE_SUB(NOW(), INTERVAL {int(retention_days)} DAY)
                ORDER BY created_time ASC, id ASC
                LIMIT :batch_size
                """
            ),
            {"batch_size": int(batch_size)},
        )
        deleted = max(0, int(delete_result.rowcount or 0))
        next_delay = (
            int(backlog_interval_seconds)
            if deleted >= int(batch_size)
            else int(idle_interval_seconds)
        )
        if deleted:
            await db.execute(
                text(
                    """
                    INSERT INTO operation_log(
                        operator, operation_type, operation_desc, target_type,
                        target_id, ip_address, created_time
                    ) VALUES(
                        'scheduler-worker', 'AUDIT_RETENTION', :description,
                        'audit_log', :target_id, NULL, NOW()
                    )
                    """
                ),
                {
                    "description": json.dumps(
                        {
                            "retentionDays": int(retention_days),
                            "deletedCount": deleted,
                        },
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                    "target_id": f"retention:{int(retention_days)}d",
                },
            )
        await db.execute(
            text(
                f"""
                INSERT INTO audit_retention_state(
                    id, last_run_at, next_run_at, last_deleted_count, updated_time
                ) VALUES(
                    1,
                    NOW(),
                    DATE_ADD(NOW(), INTERVAL {next_delay} SECOND),
                    :deleted,
                    NOW()
                )
                ON DUPLICATE KEY UPDATE
                    last_run_at = VALUES(last_run_at),
                    next_run_at = VALUES(next_run_at),
                    last_deleted_count = VALUES(last_deleted_count),
                    updated_time = NOW()
                """
            ),
            {
                "deleted": deleted,
            },
        )
        # Keep the transaction (and therefore its original connection) open
        # until the named lock is definitely released. The singleton row lock
        # continues to serialize the tiny release-to-commit window.
        await _release_lock(db)
        lock_acquired = False
        await db.commit()
        if deleted:
            logger.info("audit retention removed rows count=%d", deleted)
        return {"ran": True, "deleted": deleted, "lockAcquired": True}
    except BaseException:
        if lock_acquired:
            try:
                await _release_lock(db)
                lock_acquired = False
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "audit retention lock release failed errorType=%s",
                    type(exc).__name__,
                )
        await db.rollback()
        raise
