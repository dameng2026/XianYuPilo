import json
import re
from copy import deepcopy
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .ai_auto_reply_policy import (
    DEFAULT_POLICY_TIMEZONE,
    SUPPORTED_POLICY_TIMEZONES,
)

AI_CS_SETTING_KEY = "ai-customer-service"
MESSAGE_SETTINGS_KEY = "message-settings"
DELIVERY_SETTINGS_KEY = "delivery-settings"
PRODUCT_OP_SETTINGS_KEY = "product-op-settings"

DEFAULT_AI_CS_SYSTEM_PROMPT = """你是店里负责接待买家的客服，平时就按正常店铺客服的口吻接待，不要主动提自己是AI，也不要用平台公告式语气说话。
每次回复前，先结合当前商品信息、用户自定义知识库/聊天规则，再参考系统默认规则来回答。
回复目标是帮助买家继续了解商品、减少顾虑、推进成交；说话自然一点，简短一点，像真人聊天，但不要过度热情或闲聊跑题。
只能依据已知商品信息、知识库和规则回答，不能编造成色、库存、价格、赠品、售后、物流时效或额外服务承诺。
信息够明确时，直接给答案；信息不够时，就自然地说“这个细节我这边暂时确认不了”或“我帮您再核实一下”，再引导买家看商品页或等人工处理。
涉及平台规则、退款、投诉、赔偿、维权、改地址、线下交易、加微信等风险问题时，不要硬答，礼貌收口并转人工。"""
ACCOUNT_SCOPES_KEY = "auto-reply-account-scopes"

ALLOWED_BUSINESS_SETTING_CATEGORIES = {
    AI_CS_SETTING_KEY,
    MESSAGE_SETTINGS_KEY,
    DELIVERY_SETTINGS_KEY,
    PRODUCT_OP_SETTINGS_KEY,
    ACCOUNT_SCOPES_KEY,
}
_POLICY_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class BusinessSettingValidationError(ValueError):
    """Operator-correctable business-setting validation failure."""


def validate_ai_customer_service_config(
    config: dict[str, Any],
) -> dict[str, Any]:
    """Validate and canonicalize fields that control runtime side effects."""
    candidate = build_default_business_setting(AI_CS_SETTING_KEY)
    candidate.update(deepcopy(config or {}))

    timezone_name = str(candidate.get("timeZone") or "").strip()
    if timezone_name not in SUPPORTED_POLICY_TIMEZONES:
        raise BusinessSettingValidationError(
            "工作时段时区无效，请选择页面提供的明确时区"
        )
    candidate["timeZone"] = timezone_name

    mode = str(candidate.get("mode") or "").strip().casefold()
    if mode not in {"auto", "hybrid", "manual"}:
        raise BusinessSettingValidationError("接待模式无效")
    candidate["mode"] = mode

    for field, label in (
        ("enabled", "AI 自动回复主开关"),
        ("workHours24", "全天时段开关"),
        ("pauseOnHumanIntervene", "人工干预暂停开关"),
        ("safeMode", "关键词安全模式开关"),
    ):
        if not isinstance(candidate.get(field), bool):
            raise BusinessSettingValidationError(f"{label}必须是布尔值")

    start = str(candidate.get("workStart") or "").strip()
    end = str(candidate.get("workEnd") or "").strip()
    if not _POLICY_TIME_RE.fullmatch(start) or not _POLICY_TIME_RE.fullmatch(end):
        raise BusinessSettingValidationError("工作时段必须使用 HH:MM 格式")
    if not candidate["workHours24"] and start == end:
        raise BusinessSettingValidationError("非全天工作时段的开始与结束时间不能相同")
    candidate["workStart"] = start
    candidate["workEnd"] = end

    for field, minimum, maximum, label in (
        ("maxDailyReplies", 1, 10_000, "每日最大回复数"),
        ("humanInterventionPauseMinutes", 1, 1_440, "人工接管暂停时长"),
    ):
        raw_value = candidate.get(field)
        if isinstance(raw_value, bool):
            raise BusinessSettingValidationError(f"{label}必须是整数")
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise BusinessSettingValidationError(f"{label}必须是整数") from exc
        if value < minimum or value > maximum:
            raise BusinessSettingValidationError(
                f"{label}必须在 {minimum} 到 {maximum} 之间"
            )
        candidate[field] = value

    return candidate


def _entry(name: str, content: str, source: str = "default") -> dict[str, str]:
    return {"name": name, "content": content, "source": source}


def _default_ai_knowledge_bases() -> list[dict[str, str]]:
    return [
        _entry("默认商品知识", "优先根据当前商品标题、价格、配置、成色、库存和发货说明回答；没有明确信息时不要猜测。"),
        _entry("默认接待边界", "你是店铺客服，不替平台解释规则，不承诺站外交易、加联系方式或平台未明确提供的服务。"),
    ]


def _default_ai_chat_rules() -> list[dict[str, str]]:
    return [
        _entry("回复风格", "语气自然礼貌，尽量简短，先回答问题本身，再顺手推进成交。"),
        _entry("身份表达", "不要主动强调自己是 AI；答不上来时自然表示需要再核实。"),
        _entry("信息约束", "只能根据商品信息和知识库回答，不编造成色、库存、价格、物流或售后承诺。"),
        _entry("风险转人工", "遇到退款、投诉、赔付、改地址、线下交易、加微信等风险问题时，礼貌收口并转人工。"),
    ]


def build_default_business_setting(setting_key: str) -> dict[str, Any]:
    if setting_key == AI_CS_SETTING_KEY:
        return {
            "enabled": False,
            "mode": "hybrid",
            "workHours24": True,
            "workStart": "09:00",
            "workEnd": "22:00",
            "timeZone": DEFAULT_POLICY_TIMEZONE,
            "persona": "专业客服",
            "tone": "friendly",
            "language": "zh-CN",
            "replyDelaySeconds": 8,
            "carryContext": True,
            "pauseOnHumanIntervene": True,
            "humanInterventionPauseMinutes": 30,
            "systemPrompt": DEFAULT_AI_CS_SYSTEM_PROMPT,
            "welcomeMessage": "您好，欢迎咨询这件商品，配置、成色、价格和发货问题都可以直接问我。",
            "transferThreshold": 85,
            "sessionTimeoutMinutes": 30,
            "blacklistKeywords": "低价、加微、微信、私聊",
            "maxDailyReplies": 200,
            "knowledgeBase": "",
            "knowledgeBases": _default_ai_knowledge_bases(),
            "chatRules": _default_ai_chat_rules(),
            "defaultKnowledgeBases": _default_ai_knowledge_bases(),
            "defaultChatRules": _default_ai_chat_rules(),
            "safeMode": True,
            "handoffKeywords": "退款、投诉、赔付、维权、改地址",
        }
    if setting_key == MESSAGE_SETTINGS_KEY:
        return {
            "autoMarkRead": True,
            "retentionDays": 30,
            "blockKeywords": "微信、加我、加微、私聊、低价、外站",
            "blacklistUsers": "",
            "quickReplies": "[]",
            "notifyOnNewMessage": True,
            "soundEnabled": True,
            "showBotTag": True,
            "mergeSameBuyer": True,
        }
    if setting_key == DELIVERY_SETTINGS_KEY:
        return {
            "autoConfirmDelivery": True,
            "defaultDelaySeconds": 10,
            "retryCount": 2,
            "stockAlertThreshold": 5,
            "defaultMode": "text",
            "defaultContent": "您好，感谢您的购买，这是商品内容，请注意查收。",
            "appendContent": "请妥善保存商品内容，避免泄露。",
            "failureRetryPolicy": "retry_then_manual",
            "lowStockPolicy": "offshelf_notify",
            "exceptionNotify": True,
            "autoDisableOnLowStock": True,
            "segmentSend": False,
            "header": "",
            "footer": "",
        }
    if setting_key == PRODUCT_OP_SETTINGS_KEY:
        return {
            "syncIntervalMinutes": 60,
            "priceChangeLimitPercent": 20,
            "stockLowerBound": 1,
            "autoShelfOffOnZeroStock": True,
            "autoShelfOffOnLowStock": False,
            "lowStockThreshold": 3,
            "priceFloorPercent": 50,
            "allowAutoAdjustPrice": False,
            "syncOnLogin": True,
            "notifyOnShelfOff": True,
        }
    return {}


def _parse_config_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return {}
        try:
            parsed = json.loads(text_value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _normalize_entry_list(
    value: Any,
    fallback_text: str = "",
    prefix: str = "条目",
    source: str = "user",
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw_items = value if isinstance(value, list) else []
    for index, raw_item in enumerate(raw_items, start=1):
        if isinstance(raw_item, dict):
            content = str(raw_item.get("content") or "").strip()
            if not content:
                continue
            name = str(raw_item.get("name") or f"{prefix}{index}").strip() or f"{prefix}{index}"
            item_source = str(raw_item.get("source") or source).strip() or source
            items.append({"name": name, "content": content, "source": item_source})
            continue

        content = str(raw_item or "").strip()
        if content:
            items.append({"name": f"{prefix}{index}", "content": content, "source": source})

    fallback = str(fallback_text or "").strip()
    if not items and fallback:
        items.append({"name": f"{prefix}1", "content": fallback, "source": source})
    return items


def _join_entry_contents(items: list[dict[str, str]]) -> str:
    contents = [str(item.get("content") or "").strip() for item in items]
    return "\n\n".join([content for content in contents if content])


def _looks_like_legacy_text(value: Any, markers: list[str]) -> bool:
    text_value = str(value or "").strip()
    return bool(text_value) and any(marker in text_value for marker in markers)


def _canonical_legacy_bool(
    value: Any,
    *,
    fallback: bool,
    preserve_unknown: bool = False,
) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    return value if preserve_unknown and value is not None else fallback


def normalize_ai_customer_service_config(
    config: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = deepcopy(config)
    default_config = deepcopy(defaults or build_default_business_setting(AI_CS_SETTING_KEY))

    knowledge_bases = _normalize_entry_list(
        normalized.get("knowledgeBases"),
        str(normalized.get("knowledgeBase") or ""),
        "知识库",
    )
    chat_rules = _normalize_entry_list(normalized.get("chatRules"), "", "规则")
    default_knowledge_bases = _normalize_entry_list(
        default_config.get("knowledgeBases"),
        "",
        "默认知识库",
        "default",
    )
    default_chat_rules = _normalize_entry_list(
        default_config.get("chatRules"),
        "",
        "默认规则",
        "default",
    )

    normalized["knowledgeBases"] = knowledge_bases
    normalized["chatRules"] = chat_rules
    normalized["defaultKnowledgeBases"] = default_knowledge_bases
    normalized["defaultChatRules"] = default_chat_rules
    normalized["knowledgeBase"] = _join_entry_contents(knowledge_bases)

    # Older JSON payloads used 0/1 or string booleans. Canonicalize them before
    # any runtime truthiness check. An unknown main-switch value becomes false;
    # unknown policy values remain non-boolean so the policy module denies them.
    normalized["enabled"] = _canonical_legacy_bool(
        normalized.get("enabled"),
        fallback=False,
    )
    normalized["workHours24"] = _canonical_legacy_bool(
        normalized.get("workHours24"),
        fallback=False,
        preserve_unknown=True,
    )
    normalized["pauseOnHumanIntervene"] = _canonical_legacy_bool(
        normalized.get("pauseOnHumanIntervene"),
        fallback=True,
        preserve_unknown=True,
    )
    normalized["safeMode"] = _canonical_legacy_bool(
        normalized.get("safeMode"),
        fallback=True,
        preserve_unknown=True,
    )

    legacy_system_markers = ["你是本店的AI客服", "使用“您好”", "欢迎光临本店"]
    legacy_welcome_markers = ["欢迎光临本店", "商品拍下后", "8小时内发货"]
    if _looks_like_legacy_text(normalized.get("systemPrompt"), legacy_system_markers):
        normalized["systemPrompt"] = default_config.get("systemPrompt")
    if _looks_like_legacy_text(normalized.get("welcomeMessage"), legacy_welcome_markers):
        normalized["welcomeMessage"] = default_config.get("welcomeMessage")

    return normalized


def merge_business_setting_with_defaults(setting_key: str, source: dict[str, Any] | None) -> dict[str, Any]:
    defaults = build_default_business_setting(setting_key)
    merged = deepcopy(defaults)
    if source:
        merged.update(source)
    if setting_key == AI_CS_SETTING_KEY:
        return normalize_ai_customer_service_config(merged, defaults)
    return merged


async def load_raw_business_setting(
    db: AsyncSession,
    setting_key: str,
    user_id: int = 0,
) -> dict[str, Any]:
    stmt = text(
        """
        SELECT config_json
        FROM user_business_setting
        WHERE setting_key = :key
          AND deleted = 0
        ORDER BY CASE WHEN user_id = :user_id THEN 0 ELSE 1 END, id DESC
        LIMIT 1
        """
    )
    result = await db.execute(stmt, {"key": setting_key, "user_id": user_id})
    row = result.first()
    if not row:
        return {}
    return _parse_config_json(row[0])


async def load_business_setting(
    db: AsyncSession,
    setting_key: str,
    user_id: int = 0,
) -> dict[str, Any]:
    raw = await load_raw_business_setting(db, setting_key, user_id=user_id)
    return merge_business_setting_with_defaults(setting_key, raw)


async def save_raw_business_setting(
    db: AsyncSession,
    setting_key: str,
    config: dict[str, Any],
    user_id: int = 0,
) -> dict[str, Any]:
    config_json = json.dumps(config, ensure_ascii=False)

    lookup_stmt = text(
        """
        SELECT id
        FROM user_business_setting
        WHERE setting_key = :key
          AND user_id = :user_id
          AND deleted = 0
        ORDER BY id DESC
        LIMIT 1
        """
    )
    result = await db.execute(lookup_stmt, {"key": setting_key, "user_id": user_id})
    row = result.first()

    if row:
        await db.execute(
            text(
                """
                UPDATE user_business_setting
                SET config_json = :config_json, updated_time = NOW()
                WHERE id = :id
                """
            ),
            {"id": row[0], "config_json": config_json},
        )
    else:
        await db.execute(
            text(
                """
                INSERT INTO user_business_setting (user_id, setting_key, config_json, created_time, updated_time, deleted)
                VALUES (:user_id, :key, :config_json, NOW(), NOW(), 0)
                """
            ),
            {"user_id": user_id, "key": setting_key, "config_json": config_json},
        )

    await db.commit()
    return config


async def save_business_setting(
    db: AsyncSession,
    setting_key: str,
    config: dict[str, Any],
    user_id: int = 0,
) -> dict[str, Any]:
    if setting_key == AI_CS_SETTING_KEY:
        config = validate_ai_customer_service_config(config)
    merged = merge_business_setting_with_defaults(setting_key, config)
    await save_raw_business_setting(db, setting_key, merged, user_id=user_id)
    return merged
