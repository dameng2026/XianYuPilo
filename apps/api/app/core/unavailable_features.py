from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException


ACCOUNT_AUTO_RATE_UNAVAILABLE = (
    "当前版本没有自动评价运行时消费者，保存的文本或外部 API 地址不会被调用。"
    "为避免假成功和无用途配置，自动评价接口已停用；只有实现真实订单触发、"
    "幂等控制和结果核验后才能重新开放。"
)

ACCOUNT_STRATEGY_UNAVAILABLE = (
    "当前版本没有消费账号级消息等待、定时补发货或自动擦亮配置的运行时执行器，"
    "这些设置不会生效。为避免假成功，账号策略接口已停用；请使用已有且可核验的"
    "自动回复、自动发货或独立定时任务功能。"
)

ACCOUNT_LOGIN_CREDENTIAL_UNAVAILABLE = (
    "当前版本仅支持扫码或 Cookie 授权闲鱼账号，没有账号密码登录或会话续期执行器。"
    "为避免存储无用途的高风险凭据，此接口已停用且不会回显遗留信息；"
    "请使用扫码登录，并由管理员按生产文档清理历史凭据。"
)

FACE_VERIFICATION_UNAVAILABLE = (
    "当前版本没有人脸验证事件来源，也没有可靠的提醒或已读状态持久化。"
    "此接口已停用；请在闲鱼官方客户端完成验证，然后回到账号页刷新登录状态。"
)


def feature_unavailable(detail: str) -> NoReturn:
    """Fail a retired, never-executed feature with an actionable HTTP status."""

    raise HTTPException(status_code=410, detail=detail)
