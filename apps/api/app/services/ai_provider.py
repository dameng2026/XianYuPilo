from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.upload_security import (
    UnsafeRemoteURLError,
    request_public_https,
    validate_public_https_url_syntax,
)
from app.services.open_source_config import load_open_source_config_from_store

logger = logging.getLogger(__name__)

AI_NOT_CONFIGURED_ERROR = "AI Provider 未启用或缺少 baseUrl/apiKey/model"
_PLACEHOLDER_API_KEYS = {
    "test",
    "test-key",
    "test_api_key",
    "your-api-key",
    "your_api_key",
    "replace-with-your-key",
    "replace_me",
    "changeme",
    "change-me",
    "demo",
    "example",
    "placeholder",
}

_model_config_cache: Dict[str, Any] = {}
_model_config_cache_ts: float = 0
_MODEL_CONFIG_TTL = 60

_DEFAULT_POLISH_FORBIDDEN_KEYWORDS: list[str] = ["盗版", "破解版", "毕设"]
_polish_restriction_cache: str = ""
_polish_restriction_cache_ts: float = 0
_polish_forbidden_list_cache: list[str] = []
_polish_forbidden_list_ts: float = 0


def invalidate_model_config_cache() -> None:
    global _model_config_cache, _model_config_cache_ts
    global _polish_restriction_cache, _polish_restriction_cache_ts
    global _polish_forbidden_list_cache, _polish_forbidden_list_ts

    _model_config_cache = {}
    _model_config_cache_ts = 0
    _polish_restriction_cache = ""
    _polish_restriction_cache_ts = 0
    _polish_forbidden_list_cache = []
    _polish_forbidden_list_ts = 0


def is_ai_configured(config: Optional[Dict[str, Any]]) -> bool:
    if not config:
        return False
    base_url = str(config.get("base_url") or config.get("baseUrl") or "").strip()
    api_key = str(config.get("api_key") or config.get("apiKey") or "").strip()
    model = str(
        config.get("model")
        or config.get("modelName")
        # Read legacy data during upgrade, but only modelName is written now.
        or config.get("realModel")
        or ""
    ).strip()
    enabled = config.get("enabled")
    if enabled is None:
        enabled = True
    normalized_key = api_key.lower().replace("_", "-").strip()
    collapsed_key = normalized_key.replace("-", "").replace(" ", "")
    placeholder_key = (
        not api_key
        or normalized_key.startswith("sk-test")
        or normalized_key in _PLACEHOLDER_API_KEYS
        or collapsed_key in {item.replace("-", "").replace("_", "") for item in _PLACEHOLDER_API_KEYS}
    )
    try:
        validate_public_https_url_syntax(base_url)
        endpoint_safe = True
    except UnsafeRemoteURLError:
        endpoint_safe = False
    return bool(
        enabled
        and endpoint_safe
        and base_url
        and model
        and api_key
        and not placeholder_key
    )


async def _load_chat_model_config_from_db() -> Optional[Dict[str, Any]]:
    global _model_config_cache, _model_config_cache_ts
    import time as _time

    now = _time.time()
    if _model_config_cache and (now - _model_config_cache_ts) < _MODEL_CONFIG_TTL:
        return _model_config_cache or None

    try:
        config = await load_open_source_config_from_store()
        general_model = (config or {}).get("generalModel") or {}
        merged = {
            "providerName": str(general_model.get("provider") or "").strip(),
            "modelName": str(general_model.get("modelName") or general_model.get("realModel") or "").strip(),
            "baseUrl": str(general_model.get("baseUrl") or "").strip(),
            "apiKey": str(general_model.get("apiKey") or "").strip(),
            "requestTimeout": int(general_model.get("requestTimeout") or settings.ai_provider_timeout_seconds or 30),
            "polishKeywords": str(general_model.get("polishKeywords") or "").strip(),
            "polishForbiddenKeywords": str(general_model.get("polishForbiddenKeywords") or "").strip(),
        }
        merged["enabled"] = is_ai_configured({
            "enabled": True,
            "baseUrl": merged["baseUrl"],
            "apiKey": merged["apiKey"],
            "modelName": merged["modelName"],
        })

        if not any(merged.values()):
            _model_config_cache = {}
            _model_config_cache_ts = now
            return None

        _model_config_cache = merged
        _model_config_cache_ts = now
        logger.info(
            "Loaded general model config from system settings: provider=%s model=%s endpointConfigured=%s",
            merged.get("providerName"),
            merged.get("modelName"),
            bool(merged.get("baseUrl")),
        )
        return merged
    except Exception as exc:
        logger.debug(
            "Failed to read general model config from system settings errorType=%s",
            type(exc).__name__,
        )
        _model_config_cache = {}
        _model_config_cache_ts = now
        return None


async def _resolve_ai_config() -> Dict[str, Any]:
    db_config = await _load_chat_model_config_from_db()
    if db_config:
        base_url = str(db_config.get("baseUrl") or "").strip()
        api_key = str(db_config.get("apiKey") or "").strip()
        model = str(db_config.get("modelName") or db_config.get("realModel") or "").strip()
        enabled = bool(db_config.get("enabled", True))
        if base_url and api_key and model and enabled:
            return {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
                "enabled": True,
                "source": "settings",
                "request_timeout": int(db_config.get("requestTimeout") or settings.ai_provider_timeout_seconds or 30),
            }

    base_url = (settings.ai_provider_base_url or "").strip()
    return {
        "base_url": base_url,
        "api_key": (settings.ai_provider_api_key or "").strip(),
        "model": (settings.ai_provider_model or "").strip(),
        "enabled": bool(
            settings.ai_provider_enabled
            and base_url
            and settings.ai_provider_api_key
            and settings.ai_provider_model
        ),
        "source": "env",
        "request_timeout": int(settings.ai_provider_timeout_seconds or 30),
    }


def _parse_keyword_list(raw: Any) -> list[str]:
    if not raw:
        return []
    text = str(raw).strip()
    if not text or text.lower() in {"none", "null"}:
        return []
    parts = re.split(r"[,\n\r，、\s]+", text)
    seen: list[str] = []
    for part in parts:
        keyword = part.strip()
        if keyword and keyword not in seen:
            seen.append(keyword)
    return seen


async def get_polish_keywords_restriction() -> str:
    global _polish_restriction_cache, _polish_restriction_cache_ts
    import time as _time

    now = _time.time()
    if _polish_restriction_cache and (now - _polish_restriction_cache_ts) < _MODEL_CONFIG_TTL:
        return _polish_restriction_cache

    forbidden: list[str] = list(_DEFAULT_POLISH_FORBIDDEN_KEYWORDS)
    required: list[str] = []

    try:
        cfg = await _load_chat_model_config_from_db()
        if cfg:
            for keyword in _parse_keyword_list(cfg.get("polishForbiddenKeywords")):
                if keyword not in forbidden:
                    forbidden.append(keyword)
            required = _parse_keyword_list(cfg.get("polishKeywords"))
    except Exception as exc:
        logger.debug(
            "Failed to read polish restriction config errorType=%s",
            type(exc).__name__,
        )

    parts: list[str] = []
    if required:
        parts.append("【必须包含的关键词】润色结果中必须出现以下关键词：" + "、".join(required))
    if forbidden:
        parts.append("【绝对禁止的关键词】润色结果中不得出现以下关键词及其变体：" + "、".join(forbidden))

    restriction = "\n".join(parts)
    _polish_restriction_cache = restriction
    _polish_restriction_cache_ts = now
    return restriction


async def get_polish_forbidden_keywords() -> list[str]:
    global _polish_forbidden_list_cache, _polish_forbidden_list_ts
    import time as _time

    now = _time.time()
    if _polish_forbidden_list_cache and (now - _polish_forbidden_list_ts) < _MODEL_CONFIG_TTL:
        return list(_polish_forbidden_list_cache)

    forbidden: list[str] = list(_DEFAULT_POLISH_FORBIDDEN_KEYWORDS)
    try:
        cfg = await _load_chat_model_config_from_db()
        if cfg:
            for keyword in _parse_keyword_list(cfg.get("polishForbiddenKeywords")):
                if keyword and keyword not in forbidden:
                    forbidden.append(keyword)
    except Exception as exc:
        logger.debug(
            "Failed to read polish forbidden keywords errorType=%s",
            type(exc).__name__,
        )

    _polish_forbidden_list_cache = list(forbidden)
    _polish_forbidden_list_ts = now
    return forbidden


def validate_polish_output(title: str, body: str, forbidden_keywords: list[str]) -> tuple[list[str], list[str]]:
    if not forbidden_keywords:
        return [], []

    title_lower = str(title or "").lower()
    body_lower = str(body or "").lower()

    def _scan(text_lower: str) -> list[str]:
        hits: list[str] = []
        for keyword in forbidden_keywords:
            lowered = str(keyword or "").strip().lower()
            if lowered and lowered in text_lower and lowered not in [item.lower() for item in hits]:
                hits.append(keyword)
        return hits

    return _scan(title_lower), _scan(body_lower)


def mask_forbidden_keywords(text: str, forbidden_keywords: list[str]) -> str:
    if not text or not forbidden_keywords:
        return text

    result = str(text)
    for keyword in forbidden_keywords:
        plain = str(keyword or "").strip()
        if not plain:
            continue
        result = re.compile(re.escape(plain), re.IGNORECASE).sub("*" * len(plain), result)
    return result


async def enforce_polish_restriction(title: str, body: str) -> tuple[str, str, list[str]]:
    forbidden = await get_polish_forbidden_keywords()
    if not forbidden:
        return title or "", body or "", []

    title_hits, body_hits = validate_polish_output(title, body, forbidden)
    all_hits: list[str] = []
    for keyword in title_hits + body_hits:
        if keyword not in all_hits:
            all_hits.append(keyword)

    if not all_hits:
        return title or "", body or "", []

    masked_title = mask_forbidden_keywords(title or "", forbidden)
    masked_body = mask_forbidden_keywords(body or "", forbidden)
    logger.warning("[POLISH_FORBIDDEN] hitCount=%d", len(all_hits))
    return masked_title, masked_body, all_hits


async def generate_text(
    scene: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    messages: list[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    cfg = await _resolve_ai_config()
    base_url = (cfg["base_url"] or "").rstrip("/")
    if base_url and not base_url.endswith("/v1"):
        base_url += "/v1"

    result: Dict[str, Any] = {
        "requestId": request_id,
        "scene": scene,
        "provider": "openai-compatible",
        "model": cfg["model"],
        "configured": is_ai_configured({**cfg, "base_url": base_url}),
        "configSource": cfg["source"],
    }
    if not result["configured"]:
        result.update({"ok": False, "error": AI_NOT_CONFIGURED_ERROR})
        return result

    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt or ""},
            {"role": "user", "content": user_prompt or ""},
        ]
    elif system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + list(messages)

    payload = {
        "model": cfg["model"],
        "temperature": temperature,
        "messages": messages,
    }

    try:
        response = await request_public_https(
            f"{base_url}/chat/completions",
            method="POST",
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            timeout_seconds=max(int(cfg.get("request_timeout") or 30), 5),
            max_request_bytes=512 * 1024,
            max_response_bytes=1024 * 1024,
        )
        result["httpStatus"] = response.status_code
        if response.status_code < 200 or response.status_code >= 300:
            result.update({"ok": False, "error": f"AI Provider returned HTTP {response.status_code}"})
            return result
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("invalid provider response")
        choices = data.get("choices") or []
        content = ""
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            content = (
                (choices[0].get("message") or {}).get("content")
                or choices[0].get("text")
                or ""
            ).strip()
        result.update({"ok": bool(content), "content": content, "usage": data.get("usage") or {}})
        return result
    except UnsafeRemoteURLError as exc:
        logger.warning("AI Provider endpoint rejected or unavailable: kind=%s", exc.__class__.__name__)
        result.update({"ok": False, "error": "AI Provider endpoint must be a reachable public HTTPS address"})
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI Provider request failed: kind=%s", exc.__class__.__name__)
        result.update({"ok": False, "error": "AI Provider request failed"})
        return result
