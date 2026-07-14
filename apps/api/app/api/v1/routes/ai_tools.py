import logging
import re
from typing import Any

from fastapi import APIRouter, Depends

from ....core.camel import CamelModel
from ....core.response import ResultObject
from ....services.ai_provider import (
    AI_NOT_CONFIGURED_ERROR,
    _resolve_ai_config,
    generate_text,
    is_ai_configured,
)
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-tools", tags=["ai-tools"])

AI_SETTINGS_HINT = "未配置通用模型，请先前往系统设置中的“模型配置”填写 baseUrl、apiKey 与模型名称。"


class RewriteGoodsReqDTO(CamelModel):
    title: str = ""
    description: str = ""


class CategorySuggestReqDTO(CamelModel):
    title: str = ""
    description: str = ""
    categories: list[dict[str, Any]] = []


def _normalize_text(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"\s+", "", raw)


def _fallback_rewrite(title: str, description: str) -> str:
    safe_title = str(title or "").strip() or "闲置好物"
    lines = [line.strip(" -·•\t") for line in re.split(r"[\r\n]+", str(description or "")) if line.strip()]
    lines = lines[:3]
    if not lines:
        lines = [
            f"{safe_title}实拍在售，细节以图片和页面信息为准。",
            "欢迎咨询成色、库存、发货方式等信息。",
        ]
    notes = [
        "下单前请先确认库存与规格，避免缺货影响发货。",
        "默认按页面说明发货，特殊要求可提前沟通。",
    ]
    content = [f"【{safe_title}】"]
    for idx, line in enumerate(lines + notes, start=1):
        content.append(f"{idx}. {line}")
    return "\n".join(content)


def _category_name(option: dict[str, Any]) -> str:
    return str(option.get("name") or option.get("categoryName") or option.get("category_name") or "").strip()


def _category_path(option: dict[str, Any]) -> str:
    return str(option.get("path") or option.get("categoryPath") or option.get("category_path") or "").strip()


def _category_tokens(option: dict[str, Any]) -> list[str]:
    raw_parts = [_category_name(option), _category_path(option)]
    tokens: list[str] = []
    for part in raw_parts:
        if not part:
            continue
        for token in [part, *re.split(r"[\s>/＞|,，、;；()\[\]（）-]+", part)]:
            normalized = _normalize_text(token)
            if len(normalized) < 2:
                continue
            if normalized not in tokens:
                tokens.append(normalized)
    return tokens


def _match_category(option: dict[str, Any], full_text: str) -> int:
    name = _normalize_text(_category_name(option))
    path = _normalize_text(_category_path(option))
    score = 0
    if name and name in full_text:
        score += max(8, len(name))
    if path and path in full_text:
        score += max(6, len(path) // 2)
    for token in _category_tokens(option):
        if token in full_text:
            score += min(6, len(token))
    return score


def _suggest_category(categories: list[dict[str, Any]], title: str, description: str) -> tuple[dict[str, Any] | None, int]:
    full_text = _normalize_text(f"{title} {description}")
    if not full_text:
        return None, 0
    best_option: dict[str, Any] | None = None
    best_score = 0
    for option in categories:
        score = _match_category(option, full_text)
        if score > best_score:
            best_option = option
            best_score = score
    return best_option, best_score


@router.get("/status")
async def get_ai_tools_status(current_user: dict = Depends(get_current_user)):
    cfg = await _resolve_ai_config()
    provider_configured = is_ai_configured(cfg)
    return ResultObject.success({
        "configured": provider_configured,
        "providerConfigured": provider_configured,
        "mode": "provider" if provider_configured else "blocked",
        "message": "AI 模型已配置，可直接使用。" if provider_configured else AI_SETTINGS_HINT,
    })


@router.post("/rewrite-goods")
async def rewrite_goods(
    req: RewriteGoodsReqDTO,
    current_user: dict = Depends(get_current_user),
):
    title = str(req.title or "").strip()
    description = str(req.description or "").strip()
    fallback = _fallback_rewrite(title, description)

    cfg = await _resolve_ai_config()
    if not is_ai_configured(cfg):
        return ResultObject.success({
            "ok": False,
            "configured": False,
            "mode": "template",
            "errorCode": "NOT_CONFIGURED",
            "message": AI_SETTINGS_HINT,
            "fallbackContent": fallback,
        })

    ai_result = await generate_text(
        scene="goods_rewrite",
        system_prompt=(
            "你是闲鱼商品文案助手。请将输入整理为适合商品详情页展示的中文描述。"
            "要求：保留事实，不夸大，不编造参数；输出简洁、分点清晰，可直接粘贴到商品描述。"
        ),
        user_prompt=f"商品标题：{title}\n原始描述：{description or '无'}",
        temperature=0.4,
    )
    if ai_result.get("ok") and ai_result.get("content"):
        return ResultObject.success({
            "ok": True,
            "content": ai_result["content"].strip(),
            "mode": "provider",
            "configured": True,
        })

    if ai_result.get("error"):
        logger.warning("AI 改写不可用，已回退到模板文案: %s", ai_result["error"])

    return ResultObject.success({
        "ok": False,
        "configured": True,
        "mode": "provider",
        "errorCode": "AI_ERROR",
        "message": str(ai_result.get("error") or "AI 生成失败，请稍后重试"),
        "fallbackContent": fallback,
    })


@router.post("/category-suggest")
async def category_suggest(
    req: CategorySuggestReqDTO,
    current_user: dict = Depends(get_current_user),
):
    categories = list(req.categories or [])
    matched, score = _suggest_category(categories, req.title, req.description)
    provider_configured = is_ai_configured(await _resolve_ai_config())
    if not provider_configured:
        return ResultObject.success({
            "enabled": False,
            "configured": False,
            "providerConfigured": False,
            "matched": False,
            "errorCode": "NOT_CONFIGURED",
            "message": AI_SETTINGS_HINT,
            "reason": AI_SETTINGS_HINT,
        })
    if not matched:
        return ResultObject.success({
            "enabled": True,
            "configured": True,
            "providerConfigured": provider_configured,
            "matched": False,
            "reason": "未命中明显的分类关键词，请手动确认分类。",
        })

    return ResultObject.success({
        "enabled": True,
        "configured": True,
        "providerConfigured": provider_configured,
        "matched": True,
        "category": matched,
        "reason": f"根据标题/描述关键词匹配分类，得分 {score}",
    })
