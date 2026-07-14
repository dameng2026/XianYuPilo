# -*- coding: utf-8 -*-
"""
Redis 客户端（可选内存回退）
===========================
- 使用 redis.asyncio 提供 async 客户端
- 普通缓存调用可在 Redis 不可用时回退到进程内存
- 认证、撤销等跨副本安全状态必须显式禁用回退并 fail-closed
- 提供：get_redis、is_redis_available、redis_get、redis_set、redis_incr、redis_expire、redis_delete、redis_exists
"""
import asyncio
import logging
import time
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)


class RedisUnavailableError(RuntimeError):
    """A caller requiring shared Redis state could not reach that state."""

# 延迟导入 redis.asyncio，缺失时降级
try:
    import redis.asyncio as aioredis  # type: ignore
    _REDIS_PKG_AVAILABLE = True
except ImportError:  # pragma: no cover
    aioredis = None  # type: ignore
    _REDIS_PKG_AVAILABLE = False
    logger.warning("redis 包未安装；仅允许显式启用的非安全调用回退到内存")

_redis_client = None
_redis_init_failed = False
_redis_last_failure_at = 0.0
_REDIS_RETRY_SECONDS = 5.0

# 内存回退存储：key -> {"value": ..., "expire": float|None}
_mem_store: dict = {}
_mem_lock = asyncio.Lock()


async def get_redis():
    """获取 Redis 客户端单例。Redis 不可用时返回 None。"""
    global _redis_client, _redis_init_failed, _redis_last_failure_at
    # Contract tests intentionally use the bounded in-memory adapter. Reaching
    # a developer's Redis here makes the suite depend on workstation state and
    # leaves one async client spanning pytest's function-scoped event loops.
    # Fail-closed production behavior is tested after switching APP_ENV away
    # from ``test`` and injecting the Redis boundary explicitly.
    if (settings.app_env or "").strip().casefold() == "test":
        return None
    if not _REDIS_PKG_AVAILABLE:
        return None
    if _redis_init_failed and time.monotonic() - _redis_last_failure_at < _REDIS_RETRY_SECONDS:
        return None
    if _redis_init_failed:
        _redis_init_failed = False
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=(settings.redis_password or None),
            db=0,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # 测试连接
        await _redis_client.ping()
        logger.info("Redis 连接成功 %s:%s", settings.redis_host, settings.redis_port)
        return _redis_client
    except Exception:
        logger.warning("Redis 连接失败", exc_info=True)
        _redis_init_failed = True
        _redis_last_failure_at = time.monotonic()
        if _redis_client is not None:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
        _redis_client = None
        return None


async def close_redis() -> None:
    """Close the shared Redis connection pool during application shutdown."""
    global _redis_client
    client, _redis_client = _redis_client, None
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            logger.debug("Redis close failed", exc_info=True)


async def _invalidate_redis_client(client) -> None:
    """Evict and close a Redis client after an observed connection failure."""

    global _redis_client, _redis_init_failed, _redis_last_failure_at
    if _redis_client is client:
        _redis_client = None
        _redis_init_failed = True
        _redis_last_failure_at = time.monotonic()
    try:
        await client.aclose()
    except Exception:
        logger.debug("Redis invalidation close failed", exc_info=True)


async def is_redis_available() -> bool:
    """Redis 是否可用（已连接）。"""
    client = await get_redis()
    if client is None:
        return False
    try:
        if bool(await client.ping()):
            return True
    except Exception:
        logger.warning("Redis health probe failed", exc_info=True)
    await _invalidate_redis_client(client)
    return False


def _mem_cleanup():
    """清理内存中过期的项。"""
    now = time.time()
    expired = [k for k, v in _mem_store.items() if v.get("expire") is not None and v["expire"] <= now]
    for k in expired:
        _mem_store.pop(k, None)


async def redis_get(
    key: str,
    *,
    allow_memory_fallback: bool = True,
) -> Optional[str]:
    """GET，返回字符串或 None。"""
    client = await get_redis()
    if client is not None:
        try:
            return await client.get(key)
        except Exception as exc:
            await _invalidate_redis_client(client)
            if not allow_memory_fallback:
                raise RedisUnavailableError("shared Redis GET is unavailable") from exc
            logger.debug("redis_get 失败，回退内存", exc_info=True)
    elif not allow_memory_fallback:
        raise RedisUnavailableError("shared Redis GET is unavailable")
    async with _mem_lock:
        _mem_cleanup()
        item = _mem_store.get(key)
        return item["value"] if item else None


async def redis_set(
    key: str,
    value: str,
    ex: Optional[int] = None,
    *,
    allow_memory_fallback: bool = True,
) -> bool:
    """SET，ex 为秒。"""
    client = await get_redis()
    if client is not None:
        try:
            await client.set(key, value, ex=ex)
            return True
        except Exception as exc:
            await _invalidate_redis_client(client)
            if not allow_memory_fallback:
                raise RedisUnavailableError("shared Redis SET is unavailable") from exc
            logger.debug("redis_set 失败，回退内存", exc_info=True)
    elif not allow_memory_fallback:
        raise RedisUnavailableError("shared Redis SET is unavailable")
    async with _mem_lock:
        _mem_cleanup()
        _mem_store[key] = {
            "value": value,
            "expire": (time.time() + ex) if ex else None,
        }
        return True


async def redis_set_if_absent(key: str, value: str, ex: Optional[int] = None) -> bool:
    """Atomic SET NX with the same bounded in-memory development fallback."""

    client = await get_redis()
    if client is not None:
        try:
            return bool(await client.set(key, value, ex=ex, nx=True))
        except Exception:
            await _invalidate_redis_client(client)
            logger.debug("redis_set_if_absent 失败，回退内存", exc_info=True)
    async with _mem_lock:
        _mem_cleanup()
        if key in _mem_store:
            return False
        _mem_store[key] = {
            "value": value,
            "expire": (time.time() + ex) if ex else None,
        }
        return True


async def redis_incr(
    key: str,
    expire: Optional[int] = None,
    *,
    allow_memory_fallback: bool = True,
) -> int:
    """INCR，可选设置过期。返回递增后的值。"""
    client = await get_redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            if expire is not None:
                pipe.expire(key, expire)
            results = await pipe.execute()
            return int(results[0])
        except Exception as exc:
            await _invalidate_redis_client(client)
            if not allow_memory_fallback:
                raise RedisUnavailableError("shared Redis INCR is unavailable") from exc
            logger.debug("redis_incr 失败，回退内存", exc_info=True)
    elif not allow_memory_fallback:
        raise RedisUnavailableError("shared Redis INCR is unavailable")
    async with _mem_lock:
        _mem_cleanup()
        item = _mem_store.get(key)
        cur = int(item["value"]) if item else 0
        cur += 1
        _mem_store[key] = {
            "value": str(cur),
            "expire": (time.time() + expire) if expire else (item["expire"] if item else None),
        }
        return cur


async def redis_expire(key: str, seconds: int) -> bool:
    """EXPIRE。"""
    client = await get_redis()
    if client is not None:
        try:
            return bool(await client.expire(key, seconds))
        except Exception:
            await _invalidate_redis_client(client)
            logger.debug("redis_expire 失败，回退内存", exc_info=True)
    async with _mem_lock:
        _mem_cleanup()
        item = _mem_store.get(key)
        if item is None:
            return False
        item["expire"] = time.time() + seconds
        return True


async def redis_delete(
    key: str,
    *,
    allow_memory_fallback: bool = True,
) -> int:
    """DEL，返回删除数量。"""
    client = await get_redis()
    if client is not None:
        try:
            return int(await client.delete(key))
        except Exception as exc:
            await _invalidate_redis_client(client)
            if not allow_memory_fallback:
                raise RedisUnavailableError("shared Redis DEL is unavailable") from exc
            logger.debug("redis_delete 失败，回退内存", exc_info=True)
    elif not allow_memory_fallback:
        raise RedisUnavailableError("shared Redis DEL is unavailable")
    async with _mem_lock:
        return 1 if _mem_store.pop(key, None) is not None else 0


async def redis_exists(
    key: str,
    *,
    allow_memory_fallback: bool = True,
) -> bool:
    """EXISTS。"""
    client = await get_redis()
    if client is not None:
        try:
            return bool(await client.exists(key))
        except Exception as exc:
            await _invalidate_redis_client(client)
            if not allow_memory_fallback:
                raise RedisUnavailableError("shared Redis EXISTS is unavailable") from exc
            logger.debug("redis_exists 失败，回退内存", exc_info=True)
    elif not allow_memory_fallback:
        raise RedisUnavailableError("shared Redis EXISTS is unavailable")
    async with _mem_lock:
        _mem_cleanup()
        return key in _mem_store
