"""全自动滑块失败指数退避
====================
策略（仅自动路径 / 全自动）：
- 成功：清空 fail_count，允许立即再求
- 失败：fail_count += 1，冷却 = min(6h, 30min * 2^(fail_count-1))
  即 30m -> 60m -> 120m -> 240m -> 360m(封顶)
- 手动触发 (manual / manual_retry) 默认也尊重退避，但可 force=True 跳过
  （当前产品要求全自动，手动同样遵守退避，避免狂点把 punish 打满）

状态持久化到 xianyu_captcha_backoff，进程重启不丢失。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text

from ..core.database import async_session

logger = logging.getLogger(__name__)

BASE_COOLDOWN_SEC = 30 * 60          # 30 分钟
MAX_COOLDOWN_SEC = 6 * 60 * 60       # 6 小时
_ENSURABLE = False


def _cooldown_seconds(fail_count: int) -> int:
    if fail_count <= 0:
        return 0
    # 2^(n-1) * 30min，封顶 6h
    sec = BASE_COOLDOWN_SEC * (2 ** max(0, fail_count - 1))
    return int(min(MAX_COOLDOWN_SEC, sec))


async def ensure_backoff_table() -> None:
    """幂等建表，避免迁移未跑导致退避失效。"""
    global _ENSURABLE
    if _ENSURABLE:
        return
    try:
        async with async_session() as db:
            await db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS xianyu_captcha_backoff (
                      account_id BIGINT NOT NULL,
                      fail_count INT NOT NULL DEFAULT 0,
                      next_allowed_at DATETIME NULL,
                      last_fail_at DATETIME NULL,
                      last_success_at DATETIME NULL,
                      last_error VARCHAR(512) DEFAULT '',
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                      PRIMARY KEY (account_id),
                      KEY idx_cb_next_allowed (next_allowed_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            )
            await db.commit()
        _ENSURABLE = True
    except Exception:
        logger.warning("ensure_captcha_backoff_table 失败", exc_info=True)


async def get_backoff_status(account_id: int) -> dict[str, Any]:
    await ensure_backoff_table()
    try:
        async with async_session() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT fail_count, next_allowed_at, last_fail_at, last_success_at, last_error "
                        "FROM xianyu_captcha_backoff "
                        "WHERE account_id = :aid LIMIT 1"
                    ),
                    {"aid": account_id},
                )
            ).mappings().first()
        if not row:
            return {
                "failCount": 0,
                "allowed": True,
                "nextAllowedAt": None,
                "remainingSec": 0,
                "lastError": "",
            }
        next_at: Optional[datetime] = row.get("next_allowed_at")
        now = datetime.now()
        remaining = 0
        allowed = True
        if next_at and next_at > now:
            allowed = False
            remaining = int((next_at - now).total_seconds())
        return {
            "failCount": int(row.get("fail_count") or 0),
            "allowed": allowed,
            "nextAllowedAt": str(next_at) if next_at else None,
            "remainingSec": remaining,
            "lastError": str(row.get("last_error") or ""),
        }
    except Exception:
        logger.warning("get_captcha_backoff 失败 accountId=%d", account_id, exc_info=True)
        # 读失败时不阻断（fail-open），避免表异常导致永不可求
        return {
            "failCount": 0,
            "allowed": True,
            "nextAllowedAt": None,
            "remainingSec": 0,
            "lastError": "",
        }


async def assert_auto_solve_allowed(
    account_id: int,
    *,
    force: bool = False,
) -> Optional[dict[str, Any]]:
    """若处于冷却期返回阻断信息 dict；允许则返回 None。

    冷却限制已取消：始终返回 None，允许立即重试。失败计数仍会记录到
    xianyu_captcha_backoff 表以便观察，但不再阻断求解。
    """
    return None


async def record_solve_success(account_id: int) -> None:
    await ensure_backoff_table()
    try:
        async with async_session() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO xianyu_captcha_backoff
                      (account_id, fail_count, next_allowed_at, last_success_at, last_error, updated_at)
                    VALUES (:aid, 0, NULL, NOW(), '', NOW())
                    ON DUPLICATE KEY UPDATE
                      fail_count = 0,
                      next_allowed_at = NULL,
                      last_success_at = NOW(),
                      last_error = '',
                      updated_at = NOW()
                    """
                ),
                {"aid": account_id},
            )
            await db.commit()
        logger.info("滑块退避已重置(成功) accountId=%d", account_id)
    except Exception:
        logger.warning("record_captcha_backoff_success 失败 accountId=%d", account_id, exc_info=True)


async def record_solve_failure(
    account_id: int,
    error: str = "",
) -> dict[str, Any]:
    """记录失败并计算下次允许时间，返回退避状态。"""
    await ensure_backoff_table()
    st = await get_backoff_status(account_id)
    fail_count = int(st.get("failCount") or 0) + 1
    cool = _cooldown_seconds(fail_count)
    next_at = datetime.now() + timedelta(seconds=cool)
    err = (error or "")[:500]
    try:
        async with async_session() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO xianyu_captcha_backoff
                      (account_id, fail_count, next_allowed_at, last_fail_at, last_error, updated_at)
                    VALUES (:aid, :fc, :na, NOW(), :err, NOW())
                    ON DUPLICATE KEY UPDATE
                      fail_count = :fc,
                      next_allowed_at = :na,
                      last_fail_at = NOW(),
                      last_error = :err,
                      updated_at = NOW()
                    """
                ),
                {
                    "aid": account_id,
                    "fc": fail_count,
                    "na": next_at,
                    "err": err,
                },
            )
            await db.commit()
        logger.warning(
            "滑块退避已更新(失败) accountId=%d failCount=%d cooldownSec=%d next=%s",
            account_id, fail_count, cool, next_at.isoformat(sep=" ", timespec="seconds"),
        )
    except Exception:
        logger.warning("record_captcha_backoff_failure 失败 accountId=%d", account_id, exc_info=True)
    return {
        "failCount": fail_count,
        "cooldownSec": cool,
        "nextAllowedAt": next_at.isoformat(sep=" ", timespec="seconds"),
        "allowed": False,
        "remainingSec": cool,
        "lastError": err,
    }
