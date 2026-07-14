"""
飞书对话式 AI 助手
==================

接收飞书用户消息 → AI 意图分析 → 返回可信的可用能力：

支持的意图：
1. **request_qrcode**（请求二维码登录）
   - 用户消息包含"二维码"、"扫码"、"登录"、"过期的 Cookie 怎么办"等
   - 当前明确回复不可用，并引导到 Web 管理端的账号管理页安全扫码
   - 飞书不会启动 crawler、发送失效二维码或创建后台登录任务

2. **account_status_query**（账号状态查询）
   - 用户消息包含"账号状态"、"连接情况"、"在线吗"等
   - 触发：查询所有账号 cookie_status / WS 连接状态 → 文本回复

3. **general_chat**（通用闲聊）
   - 兜底意图，AI 自由回复

会话状态管理：
- 每个飞书用户（open_id）一个会话上下文
- 保留最近 10 轮对话历史
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from ..core.database import async_session
from .ai_provider import generate_text
from .feishu_bot import (
    _load_feishu_app_config,
    send_text_message,
)

logger = logging.getLogger(__name__)


# ============================================================
# 会话状态管理
# ============================================================
@dataclass
class FeishuChatSession:
    """飞书用户会话状态"""
    user_open_id: str
    # 对话历史：[{role: "user"/"assistant", content: str}]
    history: list[dict[str, str]] = field(default_factory=list)
    # 最后活跃时间戳
    last_active: float = field(default_factory=time.time)


# 全局会话表：open_id -> FeishuChatSession
_SESSIONS: dict[str, FeishuChatSession] = {}
# 超过 1 小时未活跃即过期；同时设置硬上限，防止随机 open_id 撑满进程内存。
_SESSION_TTL_SECONDS = 3600
_SESSION_MAX_ENTRIES = 1000
_ALLOWED_INTENTS = frozenset({
    "request_qrcode",
    "account_status_query",
    "general_chat",
})


def _evict_lru_sessions_until(limit: int) -> None:
    limit = max(int(limit), 0)
    overflow = len(_SESSIONS) - limit
    if overflow <= 0:
        return
    oldest = sorted(
        _SESSIONS.items(),
        key=lambda item: (item[1].last_active, item[0]),
    )[:overflow]
    for open_id, _session in oldest:
        _SESSIONS.pop(open_id, None)


def _get_session(open_id: str) -> FeishuChatSession:
    """获取或创建飞书用户会话"""
    now = time.time()
    _purge_expired_sessions(now=now)
    if open_id not in _SESSIONS:
        _evict_lru_sessions_until(max(_SESSION_MAX_ENTRIES - 1, 0))
        _SESSIONS[open_id] = FeishuChatSession(
            user_open_id=open_id,
            last_active=now,
        )
    session = _SESSIONS[open_id]
    session.last_active = now
    return session


def _purge_expired_sessions(*, now: float | None = None) -> None:
    """清理过期会话并将会话表收敛到硬上限。"""
    now = time.time() if now is None else now
    expired = [k for k, v in _SESSIONS.items() if now - v.last_active > _SESSION_TTL_SECONDS]
    for k in expired:
        _SESSIONS.pop(k, None)
    _evict_lru_sessions_until(_SESSION_MAX_ENTRIES)


# ============================================================
# AI 意图分析
# ============================================================
INTENT_SYSTEM_PROMPT = """你是闲鱼助手的智能助手，负责分析用户消息的意图并触发对应动作。

支持的意图类型：
1. request_qrcode - 用户请求二维码登录/扫码登录。该意图只用于返回当前不可用状态并引导用户到 Web 账号管理页，不触发自动登录。
2. account_status_query - 用户查询账号状态。触发词包括："账号状态"、"连接情况"、"在线吗"、"哪个账号在线"、"账号掉线"等。
3. general_chat - 通用闲聊，与账号/登录无关的对话。

输出格式：仅输出 JSON，不要任何额外文字。
{
  "intent": "request_qrcode | account_status_query | general_chat",
  "confidence": 0.0-1.0,
  "response": "对用户消息的简短回复（用于 general_chat 时直接发送）",
  "account_nickname": "如果用户提到具体账号名称，提取出来；否则为空字符串"
}

示例：
- 用户："我需要二维码登录" → {"intent":"request_qrcode","confidence":0.95,"response":"","account_nickname":""}
- 用户："小龙云设计账号掉线了吗" → {"intent":"account_status_query","confidence":0.9,"response":"","account_nickname":"小龙云设计"}
- 用户："你好" → {"intent":"general_chat","confidence":0.95,"response":"你好！我是闲鱼助手，可以帮你查询账号状态并提供使用指引。有什么我可以帮你的吗？","account_nickname":""}
"""


async def _analyze_intent(message: str, history: list[dict[str, str]]) -> dict[str, Any]:
    """调用 AI 模型分析用户消息意图。

    Returns:
        {"intent": str, "confidence": float, "response": str, "account_nickname": str}
    """
    try:
        # 构造历史对话（最近 6 轮）
        recent_history = history[-6:] if len(history) > 6 else history
        messages = [{"role": "system", "content": INTENT_SYSTEM_PROMPT}]
        for h in recent_history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        result = await generate_text(
            scene="feishu_chat_intent",
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_prompt=message,
            messages=messages,
            temperature=0.3,
        )
        if not result.get("ok"):
            logger.warning("AI 意图分析失败")
            return {
                "intent": "general_chat",
                "confidence": 0.0,
                "response": "抱歉，我暂时无法处理你的消息，请稍后再试。",
                "account_nickname": "",
            }
        content = result.get("content", "").strip()
        # 尝试解析 JSON
        try:
            data = json.loads(content)
            return {
                "intent": data.get("intent", "general_chat"),
                "confidence": float(data.get("confidence", 0.0)),
                "response": data.get("response", ""),
                "account_nickname": data.get("account_nickname", ""),
            }
        except json.JSONDecodeError:
            # AI 未按格式返回，按 general_chat 处理
            return {
                "intent": "general_chat",
                "confidence": 0.5,
                "response": content or "我理解了你的消息。",
                "account_nickname": "",
            }
    except Exception as exc:
        logger.error(
            "AI 意图分析异常 errorType=%s",
            type(exc).__name__,
        )
        return {
            "intent": "general_chat",
            "confidence": 0.0,
            "response": "抱歉，处理消息时出现异常。",
            "account_nickname": "",
        }


# ============================================================
# 退役动作：飞书二维码登录
# ============================================================
async def _handle_request_qrcode(
    session: FeishuChatSession,
    user_open_id: str,
    account_nickname: str = "",
) -> str:
    """Truthfully retire Feishu QR login without issuing any side effect."""
    del session, user_open_id, account_nickname
    return (
        "飞书对话中的二维码自动登录当前不可用。请打开 Web 管理端的账号管理页，"
        "选择对应闲鱼账号并使用“重新扫码”完成安全登录。飞书仍可用于查询账号状态和普通对话。"
    )


# ============================================================
# 业务动作：账号状态查询
# ============================================================
async def _handle_account_status_query(
    account_nickname: str = "",
) -> str:
    """查询账号状态并返回文本报告"""
    try:
        from .ws_client import ws_manager
        async with async_session() as db:
            if account_nickname:
                rows = (await db.execute(
                    text(
                        "SELECT a.id, a.nickname, a.external_uid, "
                        "auth.cookie_status, auth.last_login_status_code, "
                        "auth.last_login_status_message, auth.last_login_check_time "
                        "FROM xianyu_account a "
                        "JOIN xianyu_account_auth auth "
                        "  ON auth.account_id = a.id "
                        "WHERE a.deleted = 0 "
                        "AND COALESCE(auth.deleted, 0) = 0 "
                        "AND a.nickname LIKE :nick "
                        "ORDER BY a.id ASC"
                    ),
                    {"nick": f"%{account_nickname}%"},
                )).mappings().all()
            else:
                rows = (await db.execute(
                    text(
                        "SELECT a.id, a.nickname, a.external_uid, "
                        "auth.cookie_status, auth.last_login_status_code, "
                        "auth.last_login_status_message, auth.last_login_check_time "
                        "FROM xianyu_account a "
                        "JOIN xianyu_account_auth auth "
                        "  ON auth.account_id = a.id "
                        "WHERE a.deleted = 0 "
                        "AND COALESCE(auth.deleted, 0) = 0 "
                        "ORDER BY a.id ASC"
                    ),
                    {},
                )).mappings().all()

        if not rows:
            return f"未找到{'名称包含「' + account_nickname + '」的' if account_nickname else '任何'}账号。"

        lines = [f"账号状态报告（共 {len(rows)} 个账号）：", ""]
        for r in rows:
            account_id = int(r["id"])
            nickname = r["nickname"] or ""
            cookie_status = int(r["cookie_status"] or 0)
            status_code = r["last_login_status_code"] or ""
            status_msg = r["last_login_status_message"] or ""

            # 查询 WS 连接状态
            ws_status = ws_manager.get_status(account_id)
            ws_connected = ws_status.get("connected", False)

            cookie_text = "✅ 有效" if cookie_status == 1 else "❌ 失效"
            ws_text = "🟢 已连接" if ws_connected else "⚪ 未连接"
            lines.append(f"• {nickname}（ID: {account_id}）")
            lines.append(f"  Cookie: {cookie_text} | WS: {ws_text}")
            if cookie_status == 0 and status_msg:
                lines.append(f"  失效原因: {status_msg}")
            lines.append("")

        lines.append("如需重新登录，请前往 Web 管理端的账号管理页安全扫码。")
        return "\n".join(lines)
    except Exception as exc:
        logger.error(
            "查询账号状态失败 errorType=%s",
            type(exc).__name__,
        )
        return "查询账号状态失败，请稍后再试。"


# ============================================================
# 主入口：处理飞书用户消息
# ============================================================
async def handle_feishu_user_message(
    user_open_id: str,
    message_content: str,
) -> str:
    """处理飞书用户消息，返回给用户的回复文本。

    内部流程：
    1. 获取/创建会话
    2. AI 意图分析
    3. 根据意图触发对应动作
    4. 记录对话历史
    """
    _purge_expired_sessions()
    session = _get_session(user_open_id)

    # 记录用户消息到历史
    session.history.append({"role": "user", "content": message_content})
    if len(session.history) > 20:
        session.history = session.history[-10:]

    try:
        # AI 意图分析
        intent_data = await _analyze_intent(message_content, session.history)
        proposed_intent = str(intent_data.get("intent") or "").strip()
        intent = (
            proposed_intent
            if proposed_intent in _ALLOWED_INTENTS
            else "general_chat"
        )
        try:
            confidence = float(intent_data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence):
            confidence = 0.0
        confidence = min(max(confidence, 0.0), 1.0)
        account_nickname = intent_data.get("account_nickname", "")
        ai_response = intent_data.get("response", "")

        logger.info(
            "飞书消息意图分析 intent=%s confidence=%.2f",
            intent,
            confidence,
        )

        # 根据意图触发动作
        if intent == "request_qrcode" and confidence >= 0.6:
            reply = await _handle_request_qrcode(session, user_open_id, account_nickname
            )
        elif intent == "account_status_query" and confidence >= 0.6:
            reply = await _handle_account_status_query(account_nickname)
        else:
            # 通用闲聊
            reply = ai_response or "我收到了你的消息，有什么我可以帮你的吗？"

        # 记录助手回复到历史
        session.history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as exc:
        logger.error(
            "处理飞书用户消息异常 errorType=%s",
            type(exc).__name__,
        )
        return "处理消息时出现异常，请稍后再试。"


# ============================================================
# 主动通知：Cookie Session 过期时推送飞书通知
# ============================================================
async def notify_session_expired_via_feishu_app(
    account_id: int,
    account_name: str,
) -> None:
    """Cookie Session 过期时通过飞书自建应用推送通知。

    通知内容包含账号名称，并引导用户到 Web 管理端安全扫码。
    """
    try:
        config = await _load_feishu_app_config(1)
        if not config or not config.get("receiveId"):
            return  # 未配置接收者，跳过

        await send_text_message(config["receiveId"],
            (
                f"⚠️ 账号「{account_name}」（ID: {account_id}）Cookie Session 已过期，"
                f"WebSocket 已断开连接。\n\n"
                f"系统已自动尝试滑块验证，但 Cookie Session 真正过期，需要重新登录。\n\n"
                f"💡 请前往 Web 管理端的账号管理页，选择该账号并使用“重新扫码”完成安全登录。"
            ),
            receive_id_type=config.get("receiveIdType", "open_id"),
        )
    except Exception as exc:
        logger.warning(
            "通过飞书自建应用通知 Session 过期失败 errorType=%s",
            type(exc).__name__,
        )
