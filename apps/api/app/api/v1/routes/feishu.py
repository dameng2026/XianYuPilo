"""
飞书自建应用事件回调路由
========================

接收飞书开放平台的事件回调：
1. URL 验证（challenge 请求）
2. 消息接收事件（im.message.receive_v1）
3. 其他事件（暂不处理）

URL: POST /api/feishu/webhook

注意：此路由不需要登录鉴权，但需要校验飞书的 Verification Token。
飞书在配置事件订阅 URL 时会发送 challenge 请求验证所有权。
"""
import json
import hashlib
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.response import ResultObject
from app.core.redis_client import redis_delete, redis_set, redis_set_if_absent
from app.services.feishu_bot import (
    _load_feishu_app_config,
    decrypt_encrypted_event,
    make_url_verification_response,
    parse_message_event,
    send_text_message,
    verify_event_signature,
)
from app.services.feishu_chat import handle_feishu_user_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.post("/webhook")
async def feishu_webhook(request: Request):
    """飞书事件回调入口。

    飞书会在以下场景调用此接口：
    1. 配置事件订阅 URL 时发送 challenge 请求
    2. 用户向机器人发送消息时发送 im.message.receive_v1 事件
    3. 其他已订阅事件

    飞书事件回调 v2.0 schema：
    {
      "schema": "2.0",
      "header": {
        "event_id": "...",
        "event_type": "im.message.receive_v1",
        "create_time": "...",
        "token": "...",  // Verification Token
        "app_id": "...",
        "tenant_key": "..."
      },
      "event": { ... }
    }

    加密场景下：
    {
      "encrypt": "<base64_aes_encrypted_payload>"
    }
    """
    claimed_event_key: str | None = None
    try:
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid json"})

        # === 处理加密事件 ===
        # 单租户模式：直接使用默认租户 ID 1 加载配置
        tenant_id = 1
        if "encrypt" in body:
            config = await _load_feishu_app_config(tenant_id)
            if not config:
                logger.warning("飞书事件回调但租户未配置自建应用: tenant_id=%d", tenant_id)
                return JSONResponse(status_code=200, content={"code": 0, "msg": "not configured"})
            encrypt_key = config.get("encryptKey") or config.get("encrypt_key") or ""
            if not encrypt_key:
                logger.warning("飞书事件加密但未配置 encrypt_key")
                return JSONResponse(status_code=400, content={"error": "decrypt failed"})
            try:
                body = decrypt_encrypted_event(encrypt_key, body["encrypt"])
            except Exception:
                logger.warning("飞书事件加密但无法解密")
                return JSONResponse(status_code=400, content={"error": "decrypt failed"})
        # === 加载飞书应用配置 ===
        config = await _load_feishu_app_config(tenant_id)
        if not config:
            logger.warning("飞书事件回调但租户未配置自建应用: tenant_id=%d", tenant_id)
            return JSONResponse(status_code=200, content={"code": 0, "msg": "not configured"})

        # === 校验 Verification Token ===
        verification_token = config.get("verificationToken", "")
        if not verify_event_signature(verification_token, body, dict(request.headers)):
            logger.warning("飞书事件 Token 校验失败: tenant_id=%d", tenant_id)
            return JSONResponse(status_code=401, content={"error": "invalid token"})

        # === URL 验证（challenge 请求）===
        if "challenge" in body:
            challenge = body["challenge"]
            logger.info("飞书 URL 验证 challenge: tenant_id=%d", tenant_id)
            return JSONResponse(status_code=200, content=make_url_verification_response(challenge))

        # === 事件去重（基于 event_id）===
        header = body.get("header", {})
        event_id = header.get("event_id", "")
        if event_id:
            claimed_event_key = await _claim_event(str(event_id))
            if not claimed_event_key:
                logger.debug("飞书事件重复或正在处理，已忽略")
                return JSONResponse(status_code=200, content={"code": 0, "msg": "duplicate"})

        # === 处理消息接收事件 ===
        event_type = header.get("event_type", "")
        if event_type == "im.message.receive_v1":
            message_data = parse_message_event(body)
            if not message_data:
                logger.warning("飞书消息事件解析失败")
                await _complete_event_claim(claimed_event_key)
                claimed_event_key = None
                return JSONResponse(status_code=200, content={"code": 0, "msg": "parse failed"})

            user_open_id = message_data["sender_open_id"]
            content = message_data["content"]
            message_type = message_data["message_type"]

            # 仅处理文本消息（图片/文件等暂不处理）
            if message_type != "text":
                # 非文本消息回复提示
                sent = await send_text_message(
                    user_open_id,
                    "目前仅支持文本消息，请发送文字内容与我对话。"
                )
                if not sent:
                    raise RuntimeError("飞书非文本提示发送失败")
                await _complete_event_claim(claimed_event_key)
                claimed_event_key = None
                return JSONResponse(status_code=200, content={"code": 0, "msg": "ok"})

            if not content.strip():
                await _complete_event_claim(claimed_event_key)
                claimed_event_key = None
                return JSONResponse(status_code=200, content={"code": 0, "msg": "empty"})

            # 调用 AI 对话处理
            logger.info(
                "飞书文本消息已接收 tenant_id=%d contentLength=%d",
                tenant_id,
                len(content),
            )
            reply = await handle_feishu_user_message(
                user_open_id=user_open_id,
                message_content=content,
            )
            # AI 已经在 handle_feishu_user_message 内部触发了对应的发送动作
            # 这里仅返回 200 让飞书知道事件已处理
            reply = str(reply or "").strip()
            if not reply:
                raise RuntimeError("feishu reply was empty")
            # The handler computes the text/status reply but does not send it.
            # Complete the provider event only after an explicit send
            # acknowledgement. False or an exception remains retryable and
            # must never be reported as a successful webhook delivery.
            delivered = await send_text_message(user_open_id, reply)
            if delivered is not True:
                raise RuntimeError("feishu reply delivery was not confirmed")
            await _complete_event_claim(claimed_event_key)
            claimed_event_key = None
            return JSONResponse(status_code=200, content={"code": 0, "msg": "ok"})

        # 其他事件暂不处理
        logger.debug("飞书事件类型当前未处理")
        await _complete_event_claim(claimed_event_key)
        claimed_event_key = None
        return JSONResponse(status_code=200, content={"code": 0, "msg": "ignored"})

    except Exception as exc:
        logger.error(
            "飞书 webhook 异常 errorType=%s",
            type(exc).__name__,
        )
        if claimed_event_key:
            await _release_event_claim(claimed_event_key)
        # 5xx instructs Feishu to retry. The short processing lease prevents
        # concurrent duplicates; a failed attempt releases its claim.
        return JSONResponse(status_code=500, content={"code": 1, "msg": "retry"})


@router.get("/config/check")
async def feishu_config_check(request: Request):
    """检查飞书自建应用配置是否完整（用于前端配置页面的连通性测试）"""
    from app.api.v1.deps import get_current_user_optional
    current_user = await get_current_user_optional(request)
    if not current_user:
        return ResultObject.validate_failed("未登录")
    config = await _load_feishu_app_config(1)
    if not config:
        return ResultObject.failed("未配置飞书自建应用")
    return ResultObject.success({
        "configured": True,
        "appId": config.get("appId", "")[:8] + "..." if config.get("appId") else "",
        "hasSecret": bool(config.get("appSecret")),
        "hasVerificationToken": bool(config.get("verificationToken")),
        "hasEncryptKey": bool(config.get("encryptKey")),
        "receiveId": config.get("receiveId", ""),
        "receiveIdType": config.get("receiveIdType", "open_id"),
    })


# ============================================================
# 辅助函数
# ============================================================

_EVENT_PROCESSING_TTL_SECONDS = 60
_EVENT_DONE_TTL_SECONDS = 24 * 60 * 60


async def _claim_event(event_id: str) -> str | None:
    """Acquire a cross-process event lease without storing the provider event ID."""

    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    key = f"feishu:event:{digest}"
    claimed = await redis_set_if_absent(
        key,
        "processing",
        ex=_EVENT_PROCESSING_TTL_SECONDS,
    )
    return key if claimed else None


async def _complete_event_claim(key: str | None) -> None:
    if key:
        await redis_set(key, "done", ex=_EVENT_DONE_TTL_SECONDS)


async def _release_event_claim(key: str | None) -> None:
    if key:
        await redis_delete(key)


def _resolve_tenant_id_from_tenant_key(tenant_key: str, body: dict) -> int | None:
    """单租户模式：直接返回默认租户 ID 1。"""
    return 1



async def _find_single_feishu_app_tenant_async() -> int | None:
    """单租户模式：直接返回默认租户 ID 1。"""
    return 1



def _find_single_feishu_app_tenant() -> int | None:
    """单租户模式：直接返回默认租户 ID 1。"""
    return 1



def _find_single_feishu_app_tenant_sync() -> int | None:
    """单租户模式：直接返回默认租户 ID 1。"""
    return 1
