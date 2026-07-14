"""Read-only, bounded access to the versioned marketplace category tree."""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path


_CATEGORIES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "categories.json"
)
_MAX_CATEGORY_BYTES = 2 * 1024 * 1024
_cache_lock = threading.Lock()
_cache_signature: tuple[int, int] | None = None
_cache_value: dict | None = None


class CategoryDataError(RuntimeError):
    """The versioned category artifact is missing, invalid, or oversized."""


def _load_category_artifact(path: Path) -> tuple[tuple[int, int], dict]:
    try:
        stat_result = path.stat()
    except OSError as exc:
        raise CategoryDataError("分类树版本文件不存在或不可读取") from exc
    if stat_result.st_size <= 0 or stat_result.st_size > _MAX_CATEGORY_BYTES:
        raise CategoryDataError("分类树版本文件大小不合法")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CategoryDataError("分类树版本文件格式无效") from exc
    if not isinstance(payload, dict):
        raise CategoryDataError("分类树版本文件顶层必须是对象")
    tree = payload.get("cation", payload.get("categories"))
    if not isinstance(tree, list):
        raise CategoryDataError("分类树版本文件缺少分类列表")
    return (stat_result.st_mtime_ns, stat_result.st_size), payload


def load_categories() -> dict:
    """Return an isolated snapshot of the immutable category artifact.

    Runtime writes were intentionally removed: changing application files is
    not durable across containers and races across replicas. New marketplace
    candidates remain available in each auto-category response and the base
    tree is updated only through a reviewed release.
    """

    global _cache_signature, _cache_value
    with _cache_lock:
        try:
            stat_result = _CATEGORIES_PATH.stat()
            signature = (stat_result.st_mtime_ns, stat_result.st_size)
        except OSError as exc:
            raise CategoryDataError("分类树版本文件不存在或不可读取") from exc
        if _cache_value is None or signature != _cache_signature:
            signature, payload = _load_category_artifact(_CATEGORIES_PATH)
            _cache_signature = signature
            _cache_value = payload
        return copy.deepcopy(_cache_value)
