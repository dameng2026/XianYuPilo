from __future__ import annotations

import asyncio
import copy
import hashlib
import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings

logger = logging.getLogger(__name__)


class CommercialBridgeError(RuntimeError):
    """Raised when the commercial backend bridge cannot complete a request."""


class CommercialBridgeNotConfigured(CommercialBridgeError):
    """Raised when the open-source instance has no bridge token/config."""


class CommercialBridgeCapabilityUnavailable(CommercialBridgeError):
    """Raised when a high-risk bridge capability has not been proven safe."""


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


_NON_AD_PAYMENT_MARKERS = (
    "赞助",
    "捐赠",
    "打赏",
    "sponsor",
    "donate",
    "donation",
    "tip jar",
)


def _is_fake_local_email(value: Any) -> bool:
    text = _as_text(value).casefold()
    return "@" in text and text.rsplit("@", 1)[-1].endswith(".local")


def _is_non_ad_payment_card(card: dict[str, Any]) -> bool:
    searchable = " ".join(
        _as_text(card.get(field))
        for field in (
            "label",
            "title",
            "desc",
            "placeholderText",
            "actionText",
            "actionValue",
        )
    ).casefold()
    return any(marker in searchable for marker in _NON_AD_PAYMENT_MARKERS)


def _sanitize_about_content(value: dict[str, Any]) -> dict[str, Any]:
    """Enforce the open-source edition's only-commercial-payment boundary."""

    sanitized = copy.deepcopy(value)
    cards = sanitized.get("communityCards")
    if isinstance(cards, list):
        sanitized["communityCards"] = [
            card
            for card in cards
            if isinstance(card, dict) and not _is_non_ad_payment_card(card)
        ]

    supports = sanitized.get("supports")
    if isinstance(supports, list):
        for support in supports:
            if not isinstance(support, dict):
                continue
            if support.get("actionType") == "mailto" and _is_fake_local_email(
                support.get("actionValue")
            ):
                support["actionType"] = "toast"
                support["actionValue"] = "部署方尚未配置真实联系方式。"

    legal_docs = sanitized.get("legalDocs")
    if isinstance(legal_docs, dict):
        for key in ("supportEmail", "feedbackEmail", "businessEmail"):
            if _is_fake_local_email(legal_docs.get(key)):
                legal_docs[key] = ""
    return sanitized


def _require_list(value: Any, action: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CommercialBridgeError(f"{action} 返回格式异常")
    return value


def _normalize_path(value: str, fallback: str) -> str:
    text = _as_text(value) or fallback
    if not text.startswith("/"):
        text = f"/{text}"
    return text.rstrip("/") or fallback


def get_commercial_bridge_config() -> dict[str, Any]:
    admin_health_path = _normalize_path(
        _as_text(settings.commercial_backend_admin_health_path)
        or _as_text(settings.commercial_backend_health_path),
        "/admin-api/health",
    )
    return {
        "baseUrl": _as_text(settings.commercial_backend_base_url).rstrip("/"),
        "bridgePrefix": _normalize_path(
            settings.commercial_backend_bridge_prefix,
            "/admin-api/open-source-bridge",
        ),
        "adminHealthPath": admin_health_path,
        "healthPath": admin_health_path,
        "userHealthPath": _normalize_path(
            settings.commercial_backend_user_health_path,
            "/api/health",
        ),
        "accessToken": _as_text(settings.commercial_backend_access_token),
        "siteCode": _as_text(settings.commercial_backend_site_code) or "open-source",
        "siteName": _as_text(settings.commercial_backend_site_name) or "开源版",
        "timeoutSeconds": max(int(settings.commercial_backend_timeout_seconds or 15), 3),
        "mutationIdempotencyEnabled": bool(
            settings.commercial_backend_mutation_idempotency_enabled
        ),
        "paymentIdempotencyEnabled": bool(
            settings.commercial_backend_payment_idempotency_enabled
        ),
        "paidAdPlacementEnforced": bool(
            settings.commercial_backend_paid_ad_placement_enforced
        ),
        "frontendUrl": _as_text(settings.commercial_frontend_url),
        "adminUrl": _as_text(settings.commercial_admin_url),
    }


def commercial_bridge_is_configured(config: dict[str, Any] | None = None) -> bool:
    bridge = config or get_commercial_bridge_config()
    return bool(bridge["baseUrl"] and bridge["accessToken"])


def require_ad_payment_order_capability() -> dict[str, Any]:
    """Fail before local persistence unless the remote idempotency contract is enabled."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接地址或访问令牌")
    if not config["paymentIdempotencyEnabled"]:
        raise CommercialBridgeCapabilityUnavailable(
            "商业桥尚未确认支持支付订单幂等键"
        )
    return config


def require_commercial_mutation_capability() -> dict[str, Any]:
    """Fail closed until non-payment bridge writes have a proven idempotency contract."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接地址或访问令牌")
    if not config["mutationIdempotencyEnabled"]:
        raise CommercialBridgeCapabilityUnavailable(
            "商业桥尚未确认支持广告申请写入幂等键"
        )
    return config


def require_paid_ad_placement_capability() -> dict[str, Any]:
    """Fail closed until the provider proves unpaid ads cannot be served."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接地址或访问令牌")
    if not config["paidAdPlacementEnforced"]:
        raise CommercialBridgeCapabilityUnavailable(
            "商业桥尚未证明仅已支付广告可激活并进入展示接口"
        )
    return config


def require_paid_ad_creation_capabilities() -> dict[str, Any]:
    """Require both halves of the paid-ad write contract.

    An advertising application is not a standalone lead form in the open-source
    product: a successful application must be able to continue into the
    application-scoped payment flow.  Keeping this check in the bridge service
    prevents callers from bypassing the UI availability gate and creating a
    half-complete commercial workflow.
    """

    # Placement enforcement is independent from transport idempotency. All
    # three attestations are mandatory before a paid-ad workflow may start.
    require_paid_ad_placement_capability()
    config = require_commercial_mutation_capability()
    if not config["paymentIdempotencyEnabled"]:
        raise CommercialBridgeCapabilityUnavailable(
            "商业桥尚未确认支持广告支付订单幂等键"
        )
    return config


def _require_idempotency_key(payload: dict[str, Any]) -> str:
    key = _as_text(payload.get("idempotencyKey"))
    if not key:
        raise CommercialBridgeCapabilityUnavailable("商业写入缺少幂等键")
    return key


def _bridge_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {
        "X-Open-Source-Token": config["accessToken"],
        "X-Open-Source-Site-Code": config["siteCode"],
    }
    # Attach the persistent instance token so the commercial backend can
    # attribute advertising applications and payment records to this specific
    # open-source deployment.  Loaded once on startup into an in-memory cache.
    try:
        from ..core.instance import get_instance_token
        instance_token = get_instance_token()
        if instance_token:
            headers["X-Open-Source-Instance-Token"] = instance_token
    except Exception:
        logger.debug("instance token unavailable for bridge request", exc_info=True)
    site_name = _as_text(config.get("siteName"))
    if site_name:
        try:
            site_name.encode("ascii")
        except UnicodeEncodeError:
            logger.debug("Skip non-ascii open-source site name header for bridge request: %s", site_name)
        else:
            headers["X-Open-Source-Site-Name"] = site_name
    if config["frontendUrl"]:
        headers["X-Open-Source-Frontend-Url"] = config["frontendUrl"]
    if config["adminUrl"]:
        headers["X-Open-Source-Admin-Url"] = config["adminUrl"]
    return headers


def _unwrap_result(payload: Any, action: str) -> Any:
    if not isinstance(payload, dict):
        raise CommercialBridgeError(f"{action} 返回格式异常")
    raw_code = payload.get("code", 500)
    try:
        code = int(raw_code)
    except (TypeError, ValueError):
        code = 500
    message = str(payload.get("msg") or payload.get("message") or f"{action} 失败").strip()
    if code not in (0, 200):
        raise CommercialBridgeError(message)
    return payload.get("data")


def _rewrite_uploads_urls(data: Any, base_url: str) -> Any:
    """Pass through image URLs unchanged.

    Relative /uploads/... paths are kept as-is so the open-source API can proxy
    them to the commercial backend via the /uploads/{path} fallback handler in
    main.py. This avoids cross-origin image loading issues in the browser.
    """
    return data


async def _probe_health_url(config: dict[str, Any], path: str, scope: str) -> tuple[bool, str]:
    timeout = httpx.Timeout(config["timeoutSeconds"], connect=5.0)
    url = f"{config['baseUrl']}{path}"
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(url)
        if 300 <= response.status_code < 400:
            return False, f"商业版{scope}健康检查拒绝重定向"
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict) and str(data.get("status") or "").upper() == "UP":
                return True, f"商业版{scope}健康检查正常"
            if int(payload.get("code", 500)) in (0, 200):
                return True, f"商业版{scope}健康检查正常"
        return True, f"商业版{scope}可访问"
    except httpx.HTTPStatusError as exc:
        return False, f"商业版{scope}健康检查返回 HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        return False, f"商业版{scope}健康检查失败: {exc}"
    except ValueError:
        return True, f"商业版{scope}可访问"


def _compose_health_message(
    *,
    user_ok: bool,
    admin_ok: bool,
    user_message: str,
    admin_message: str,
) -> str:
    if user_ok and admin_ok:
        return "商业版用户端和管理端健康检查正常"
    if admin_ok and not user_ok:
        return f"商业版管理端健康检查正常，但用户端异常: {user_message}"
    if user_ok and not admin_ok:
        return f"商业版用户端健康检查正常，但管理端异常: {admin_message}"
    if user_message and admin_message and user_message != admin_message:
        return f"{admin_message}；{user_message}"
    return admin_message or user_message or "商业版健康检查不可用"


async def _probe_health(config: dict[str, Any]) -> dict[str, Any]:
    if not config["baseUrl"]:
        return {
            "bridgeHealthOk": False,
            "adminHealthOk": False,
            "userHealthOk": False,
            "message": "未配置商业版后端地址",
        }

    (user_ok, user_message), (admin_ok, admin_message) = await asyncio.gather(
        _probe_health_url(config, config["userHealthPath"], "用户端"),
        _probe_health_url(config, config["adminHealthPath"], "管理端"),
    )
    return {
        "bridgeHealthOk": admin_ok,
        "adminHealthOk": admin_ok,
        "userHealthOk": user_ok,
        "message": _compose_health_message(
            user_ok=user_ok,
            admin_ok=admin_ok,
            user_message=user_message,
            admin_message=admin_message,
        ),
    }


async def _request_bridge(
    config: dict[str, Any],
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> Any:
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接地址或访问令牌")

    timeout = httpx.Timeout(config["timeoutSeconds"], connect=5.0)
    request_url = f"{config['baseUrl']}{config['bridgePrefix']}{path}"
    try:
        headers = _bridge_headers(config)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        async with httpx.AsyncClient(
            timeout=timeout,
            # Never forward the bridge credential to a redirect target. A
            # deployment must expose one canonical HTTPS origin.
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.request(
                method.upper(),
                request_url,
                params={k: v for k, v in (params or {}).items() if v not in (None, "")},
                json=json_data,
                headers=headers,
            )
        if 300 <= response.status_code < 400:
            raise CommercialBridgeError("商业版桥接接口返回了不安全的重定向")
        response.raise_for_status()
        return _unwrap_result(response.json(), f"商业版桥接接口 {path}")
    except CommercialBridgeError:
        raise
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise CommercialBridgeError(f"商业版桥接接口未部署: {path}") from exc
        if exc.response.status_code in (401, 403):
            raise CommercialBridgeError("商业版桥接令牌无效或没有接口权限") from exc
        raise CommercialBridgeError(
            f"商业版桥接接口返回 HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise CommercialBridgeError(f"调用商业版桥接接口失败: {exc}") from exc
    except ValueError as exc:
        raise CommercialBridgeError(f"解析商业版桥接接口响应失败: {exc}") from exc


async def get_commercial_bridge_runtime() -> dict[str, Any]:
    config = get_commercial_bridge_config()
    health_status = await _probe_health(config)
    health_ok = bool(health_status.get("bridgeHealthOk"))
    health_message = str(health_status.get("message") or "").strip()
    configured = commercial_bridge_is_configured(config)

    runtime = {
        "commercialBridgeConfigured": configured,
        "commercialBridgeConnected": False,
        "commercialBridgeMode": "commercial" if configured else "local-fallback",
        "commercialBridgeHealthOk": health_ok,
        "commercialAdminHealthOk": bool(health_status.get("adminHealthOk")),
        "commercialUserHealthOk": bool(health_status.get("userHealthOk")),
        "commercialBridgeSiteCode": config["siteCode"],
        "commercialBridgeMessage": health_message,
        "commercialMutationIdempotencyEnabled": config["mutationIdempotencyEnabled"],
        "commercialPaymentIdempotencyEnabled": config["paymentIdempotencyEnabled"],
        "commercialPaidAdPlacementEnforced": config["paidAdPlacementEnforced"],
        "commercialFrontendUrl": config["frontendUrl"],
        "commercialAdminUrl": config["adminUrl"],
    }

    if not configured:
        if health_ok:
            runtime["commercialBridgeMessage"] = (
                f"{health_message}，但尚未配置桥接 token 或桥接接口，当前使用本地兜底"
            )
        else:
            runtime["commercialBridgeMessage"] = (
                f"{health_message or '未配置商业版桥接，且健康检查不可用'}，当前使用本地兜底"
            )
        return runtime

    try:
        await _request_bridge(config, "GET", "/health")
        runtime["commercialBridgeConnected"] = True
        runtime["commercialBridgeMessage"] = (
            f"商业版桥接已接通，{health_message}" if health_message else "商业版桥接已接通"
        )
    except CommercialBridgeError as exc:
        if health_ok:
            runtime["commercialBridgeMessage"] = f"{health_message}，但桥接未完成: {exc}"
        else:
            runtime["commercialBridgeMessage"] = str(exc)

    return runtime


async def proxy_get_carousel_list(db: AsyncSession) -> list[dict[str, Any]]:
    del db
    # Home carousel is an advertising placement supported by the application
    # workflow, so serving is disabled until the commercial side proves its
    # paid-only activation contract.
    config = require_paid_ad_placement_capability()
    data = await _request_bridge(
        config,
        "GET",
        "/home/carousels",
    )
    if isinstance(data, list):
        return _rewrite_uploads_urls(data, config["baseUrl"])
    return []


async def proxy_get_text_ad_list(db: AsyncSession) -> list[dict[str, Any]]:
    del db
    config = require_paid_ad_placement_capability()
    data = await _request_bridge(
        config,
        "GET",
        "/ads/text",
    )
    return _require_list(data, "文字广告接口")


async def proxy_get_ad_plan_list(db: AsyncSession) -> list[dict[str, Any]]:
    del db
    data = await _request_bridge(
        get_commercial_bridge_config(),
        "GET",
        "/ads/plans",
    )
    return _require_list(data, "广告套餐接口")


async def proxy_list_ad_applications(
    db: AsyncSession,
    *,
    current: int,
    size: int,
) -> dict[str, Any]:
    del db
    return await _request_bridge(
        get_commercial_bridge_config(),
        "GET",
        "/ads/applications/mine",
        params={
            "current": current,
            "size": size,
        },
    )


async def proxy_create_ad_application(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    del db
    config = require_paid_ad_creation_capabilities()
    idempotency_key = _require_idempotency_key(payload)
    return await _request_bridge(
        config,
        "POST",
        "/ads/applications",
        json_data={
            "positionType": _as_text(payload.get("positionType")) or "sidebar_text",
            "planCode": _as_text(payload.get("planCode")),
            "companyName": _as_text(payload.get("companyName")),
            "contact": _as_text(payload.get("contact")),
            "contactName": _as_text(payload.get("contactName")),
            "contactPhone": _as_text(payload.get("contactPhone")),
            "contactWechat": _as_text(payload.get("contactWechat")),
            "title": _as_text(payload.get("title")),
            "landingUrl": _as_text(payload.get("landingUrl")),
            "creativeImageUrl": _as_text(payload.get("creativeImageUrl")),
            "budget": _as_text(payload.get("budget")),
            "startDate": _as_text(payload.get("startDate")),
            "durationDays": _as_text(payload.get("durationDays")),
            "remark": _as_text(payload.get("remark")),
            "idempotencyKey": idempotency_key,
            "sourceSiteCode": config["siteCode"],
            "sourceSiteName": config["siteName"],
        },
        idempotency_key=idempotency_key,
    )


async def proxy_get_ad_payment_methods(db: AsyncSession) -> list[dict[str, Any]]:
    del db
    # Payment methods double as the page's paid-ad write-readiness gate.  Do
    # not advertise a usable method unless both application and payment writes
    # have verified idempotency contracts.
    config = require_paid_ad_creation_capabilities()
    data = await _request_bridge(
        config,
        "GET",
        "/ads/payment/methods",
    )
    return _require_list(data, "广告支付方式接口")


async def proxy_create_ad_payment_order(
    db: AsyncSession,
    application_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    del db
    config = require_paid_ad_creation_capabilities()
    idempotency_key = _as_text(payload.get("idempotencyKey"))
    if not idempotency_key:
        raise CommercialBridgeCapabilityUnavailable("支付订单缺少幂等键")
    return await _request_bridge(
        config,
        "POST",
        f"/ads/applications/{application_id}/payment-order",
        json_data={
            "paymentMethod": _as_text(payload.get("paymentMethod")),
            "idempotencyKey": idempotency_key,
        },
        idempotency_key=idempotency_key,
    )


async def proxy_get_ad_payment_order(
    db: AsyncSession,
    order_no: str,
) -> dict[str, Any]:
    del db
    return await _request_bridge(
        get_commercial_bridge_config(),
        "GET",
        f"/ads/payment/orders/{order_no}",
    )


async def proxy_close_ad_payment_order(
    db: AsyncSession,
    order_no: str,
) -> dict[str, Any]:
    del db
    config = require_ad_payment_order_capability()
    normalized_order_no = _as_text(order_no)
    idempotency_key = (
        "ad-payment-close:"
        + hashlib.sha256(normalized_order_no.encode("utf-8")).hexdigest()
    )
    return await _request_bridge(
        config,
        "POST",
        f"/ads/payment/orders/{normalized_order_no}/close",
        json_data={"idempotencyKey": idempotency_key},
        idempotency_key=idempotency_key,
    )


async def proxy_get_about_content() -> dict[str, Any]:
    """从商业版后端获取关于页内容（含微信群二维码、赞助码等 communityCards）。

    桥接启用时调用商业版 GET /about 端点，获取后台配置的 communityCards。
    商业版返回的 imageUrl 为相对路径（如 /uploads/images/...），
    需拼接商业版后端 origin 后才能被开源版前端直接加载。
    桥接未配置或调用失败时降级到本地默认内容。
    """
    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        return default_about_content()
    try:
        data = await _request_bridge(config, "GET", "/about")
        if isinstance(data, dict) and data:
            _rewrite_community_card_image_urls(data, config["baseUrl"])
            data["bridgeEnabled"] = True
            return data
    except CommercialBridgeError as exc:
        logger.warning("proxy_get_about_content fallback to local: %s", exc)
    return default_about_content()


def _rewrite_community_card_image_urls(content: dict[str, Any], base_url: str) -> None:
    """将 communityCards 中的相对 imageUrl 拼接为商业版后端的绝对 URL。"""
    origin = base_url.rstrip("/")
    cards = content.get("communityCards")
    if not isinstance(cards, list):
        return
    for card in cards:
        if not isinstance(card, dict):
            continue
        url = _as_text(card.get("imageUrl"))
        if url and url.startswith("/"):
            card["imageUrl"] = f"{origin}{url}"


# ---------------------------------------------------------------------------
# Feedback bridge — forward user feedback to the commercial backend when the
# bridge is configured.  Each function raises CommercialBridgeError on failure
# so the caller can fall back to local storage.
# ---------------------------------------------------------------------------


async def proxy_list_feedback(
    *,
    current: int,
    size: int,
    status: str = "",
    category: str = "",
) -> dict[str, Any]:
    """Bridge: list feedback records from the commercial backend."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接")
    params: dict[str, Any] = {"current": current, "size": size}
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    data = await _request_bridge(config, "GET", "/feedback", params=params)
    if isinstance(data, dict):
        data.setdefault("storageMode", "bridge")
    return data


async def proxy_get_feedback_stats() -> dict[str, Any]:
    """Bridge: get feedback statistics from the commercial backend."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接")
    data = await _request_bridge(config, "GET", "/feedback/stats")
    if isinstance(data, dict):
        data.setdefault("storageMode", "bridge")
    return data


async def proxy_get_feedback_detail(feedback_id: int) -> dict[str, Any]:
    """Bridge: get a single feedback record from the commercial backend."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接")
    data = await _request_bridge(config, "GET", f"/feedback/{feedback_id}")
    if isinstance(data, dict):
        data.setdefault("storageMode", "bridge")
    return data


async def proxy_submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    """Bridge: submit a new feedback record to the commercial backend."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接")
    idempotency_key = _as_text(payload.get("idempotencyKey"))
    data = await _request_bridge(
        config,
        "POST",
        "/feedback",
        json_data={
            "category": _as_text(payload.get("category")),
            "title": _as_text(payload.get("title")),
            "content": _as_text(payload.get("content")),
            "contact": _as_text(payload.get("contact")),
            "idempotencyKey": idempotency_key,
        },
        idempotency_key=idempotency_key,
    )
    if isinstance(data, dict):
        data.setdefault("storageMode", "bridge")
    return data


async def proxy_append_feedback_reply(
    feedback_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Bridge: append a reply to an existing feedback record."""

    config = get_commercial_bridge_config()
    if not commercial_bridge_is_configured(config):
        raise CommercialBridgeNotConfigured("未配置商业版桥接")
    idempotency_key = _as_text(payload.get("idempotencyKey"))
    data = await _request_bridge(
        config,
        "POST",
        f"/feedback/{feedback_id}/reply",
        json_data={
            "content": _as_text(payload.get("content")),
            "idempotencyKey": idempotency_key,
        },
        idempotency_key=idempotency_key,
    )
    if isinstance(data, dict):
        data.setdefault("storageMode", "bridge")
    return data


def default_about_content() -> dict[str, Any]:
    return copy.deepcopy(
        {
            "heroTitle": "XianYuAssistant 开源版",
            "heroBadgeText": "付费广告商业桥",
            "heroDescription": "开源单管理员版本提供本地核心能力；只有付费广告申请、支付与展示会连接商业版后端。",
            "serviceStatusText": "本地核心能力；付费广告桥按需配置",
            "logs": [
                {
                    "v": "开源版",
                    "t": "",
                    "tone": "major",
                    "d": "当前版本已完成固定账号密码登录、系统配置整合与付费广告商业桥边界；未配置的广告能力会明确显示为不可用。",
                    "sections": [
                        {
                            "t": "登录与账号",
                            "d": "保留固定管理员账号密码登录模式，扫码登录仅用于闲鱼店铺授权，避免误连到外部旧环境。",
                        },
                        {
                            "t": "系统配置",
                            "d": "通用模型、向量模型、RAG 知识库与高德地图配置已统一收敛到系统配置页。",
                        },
                        {
                            "t": "广告商业桥",
                            "d": "开源版只通过服务端桥接接口处理付费广告申请、支付与展示，不暴露商业版数据库，也不让前端持有 bridge token。",
                        },
                    ],
                    "tags": ["固定账号登录", "系统配置整合", "付费广告桥", "广告合作"],
                }
            ],
            "supports": [
                {
                    "label": "反馈建议",
                    "icon": "aboutSupportFeedback",
                    "tone": "violet",
                    "desc": "提交使用问题、需求建议和联调备注，形成开源版闭环反馈。",
                    "actionType": "route",
                    "actionValue": "feedback",
                    "actionMessage": "正在前往反馈建议...",
                },
                {
                    "label": "广告合作",
                    "icon": "aboutSupportWeb",
                    "tone": "blue",
                    "desc": "仅在真实付费广告桥接通后查看套餐、提交申请并支付；未配置时入口会明确禁用操作。",
                    "actionType": "route",
                    "actionValue": "ad-application",
                    "actionMessage": "正在前往广告合作...",
                },
                {
                    "label": "系统配置",
                    "icon": "aboutSupportDoc",
                    "tone": "green",
                    "desc": "统一管理通用模型、向量模型、RAG 知识库与高德地图配置。",
                    "actionType": "route",
                    "actionValue": "settings-ai-cs",
                    "actionMessage": "正在前往系统配置...",
                },
                {
                    "label": "商务联系",
                    "icon": "aboutSupportChat",
                    "tone": "orange",
                    "desc": "当前默认部署未配置商务联系人，请由部署方补充真实入口。",
                    "actionType": "toast",
                    "actionValue": "部署方尚未配置商务联系方式。",
                },
            ],
            "communityCards": [
                {
                    "label": "交流群",
                    "title": "微信群二维码",
                    "desc": "用于当前部署自行维护的版本通知、使用答疑、投放交流与功能建议收集。",
                    "placeholderText": "GROUP",
                    "hint": "配置后可扫码",
                    "tone": "blue",
                    "actionType": "toast",
                    "actionText": "配置后可扫码",
                    "actionValue": "当前部署尚未配置交流二维码，请联系部署管理员。",
                },
                {
                    "label": "联系方式",
                    "title": "商务合作联系方式",
                    "desc": "广告投放、功能合作、联名活动或技术支持需求，可直接通过这里建立联系。",
                    "value": "",
                    "hint": "当前未配置",
                    "tone": "green",
                    "actionType": "toast",
                    "actionText": "不可用",
                    "actionValue": "部署方尚未配置商务联系方式。",
                },
            ],
            "links": [
                {
                    "label": "用户协议",
                    "icon": "aboutShield",
                    "actionText": "查看",
                    "actionType": "legal",
                    "actionValue": "terms",
                },
                {
                    "label": "隐私政策",
                    "icon": "aboutEye",
                    "actionText": "查看",
                    "actionType": "legal",
                    "actionValue": "privacy",
                },
                {
                    "label": "版本说明",
                    "icon": "refresh",
                    "actionText": "查看",
                    "actionType": "toast",
                    "actionValue": "当前版本已包含固定账号登录、系统配置整合与付费广告商业桥。",
                },
                {
                    "label": "导出诊断日志",
                    "icon": "download",
                    "actionText": "导出",
                    "actionType": "download",
                    "actionValue": "diagnostics",
                },
            ],
            "legalDocs": {
                "termsUrl": "",
                "privacyUrl": "",
                "supportEmail": "",
                "feedbackEmail": "",
                "businessEmail": "",
            },
        }
    )


