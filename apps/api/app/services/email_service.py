"""邮箱验证码服务：Redis 存储验证码 + SMTP 发送。

验证码流程：
1. POST /api/auth/email/code  →  generate_code() → store_code() → send_verification_email()
2. POST /api/auth/email/login  →  verify_code() → 查找 admin → 签发 token

Redis 键设计：
- email_code:{email}:{purpose}     验证码本体，TTL 5 分钟
- email_rate:{email}               发送频率限制，TTL 60 秒
- email_attempts:{email}:{purpose} 验证尝试次数，TTL 5 分钟，上限 5 次
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.redis_client import (
    RedisUnavailableError,
    redis_delete,
    redis_get,
    redis_incr,
    redis_set,
)
from ..core.secret_store import decrypt_secret, encrypt_secret
from ..models.entities import XianyuSysSetting

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────
CODE_TTL_SECONDS = 5 * 60          # 验证码有效期 5 分钟
RATE_LIMIT_TTL_SECONDS = 60        # 发送频率限制 60 秒
MAX_VERIFY_ATTEMPTS = 5            # 最大验证尝试次数
ATTEMPTS_TTL_SECONDS = 5 * 60      # 尝试计数窗口与验证码同生命周期

CODE_KEY_PREFIX = "email_code:"
RATE_KEY_PREFIX = "email_rate:"
ATTEMPTS_KEY_PREFIX = "email_attempts:"

SMTP_CONFIG_SETTING_KEY = "admin_email_smtp_config"
SMTP_PASSWORD_PURPOSE = "admin_email.smtpPass"

PURPOSE_TEXT_MAP: dict[str, str] = {
    "login": "登录",
    "register": "注册",
    "reset": "重置密码",
}


# ── 验证码生成与存储 ──────────────────────────────────────────
def generate_code() -> str:
    """生成 6 位数字验证码。"""
    return f"{random.randint(0, 999999):06d}"


async def store_code(email: str, purpose: str, code: str) -> None:
    """将验证码存入 Redis，TTL 5 分钟。同时重置尝试计数。"""
    key = f"{CODE_KEY_PREFIX}{email}:{purpose}"
    await redis_set(key, code, ex=CODE_TTL_SECONDS)
    # 清除之前的尝试计数
    await redis_delete(f"{ATTEMPTS_KEY_PREFIX}{email}:{purpose}")


async def verify_code(email: str, purpose: str, code: str) -> tuple[bool, str]:
    """校验验证码。返回 (是否成功, 消息)。

    - 验证码不存在或已过期 → (False, "验证码已过期，请重新获取")
    - 尝试次数超限       → (False, "验证码错误次数过多，请重新获取")
    - 验证码不匹配       → (False, "验证码错误")  并递增尝试计数
    - 验证码匹配         → (True, "验证成功")    并删除验证码
    """
    code_key = f"{CODE_KEY_PREFIX}{email}:{purpose}"
    attempts_key = f"{ATTEMPTS_KEY_PREFIX}{email}:{purpose}"

    stored = await redis_get(code_key)
    if not stored:
        return False, "验证码已过期，请重新获取"

    # 检查尝试次数
    attempts_str = await redis_get(attempts_key)
    attempts = int(attempts_str) if attempts_str else 0
    if attempts >= MAX_VERIFY_ATTEMPTS:
        await redis_delete(code_key)
        await redis_delete(attempts_key)
        return False, "验证码错误次数过多，请重新获取"

    if stored != code:
        await redis_incr(attempts_key, expire=ATTEMPTS_TTL_SECONDS)
        return False, "验证码错误"

    # 验证成功，清理
    await redis_delete(code_key)
    await redis_delete(attempts_key)
    return True, "验证成功"


async def check_send_rate(email: str) -> bool:
    """检查是否被频率限制。返回 True 表示被限制（60 秒内已发送过）。"""
    key = f"{RATE_KEY_PREFIX}{email}"
    return bool(await redis_get(key))


async def _mark_sent(email: str) -> None:
    """标记已发送，设置 60 秒频率限制。"""
    await redis_set(f"{RATE_KEY_PREFIX}{email}", "1", ex=RATE_LIMIT_TTL_SECONDS)


# ── SMTP 配置读写 ─────────────────────────────────────────────
async def load_email_smtp_config(db: AsyncSession) -> dict[str, Any]:
    """从 xianyu_sys_setting 读取 SMTP 配置。返回 dict（密码已解密）。"""
    result = await db.execute(
        select(XianyuSysSetting).where(
            XianyuSysSetting.setting_key == SMTP_CONFIG_SETTING_KEY
        )
    )
    setting = result.scalar_one_or_none()
    if not setting or not setting.setting_value:
        return {}
    try:
        config = json.loads(setting.setting_value)
    except Exception:
        return {}
    if not isinstance(config, dict):
        return {}
    # 解密密码
    raw_pass = config.get("smtpPass") or ""
    if raw_pass:
        config["smtpPass"] = decrypt_secret(raw_pass, purpose=SMTP_PASSWORD_PURPOSE) or ""
    return config


async def save_email_smtp_config(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """保存 SMTP 配置。密码使用 secret_store 加密。返回存储后的配置（含加密密码）。

    统一使用 camelCase 键名存储，与 load_email_smtp_config 和 send_verification_email 的读取逻辑一致。
    """
    # 将 snake_case 键名统一转换为 camelCase
    key_map = {
        "smtp_host": "smtpHost",
        "smtp_port": "smtpPort",
        "smtp_user": "smtpUser",
        "smtp_pass": "smtpPass",
        "from_email": "fromEmail",
        "from_name": "fromName",
    }
    config = {}
    for k, v in payload.items():
        config[key_map.get(k, k)] = v

    raw_pass = str(config.get("smtpPass") or "").strip()
    if raw_pass:
        config["smtpPass"] = encrypt_secret(raw_pass, purpose=SMTP_PASSWORD_PURPOSE) or ""
    else:
        # 保留原有密码
        existing = await load_email_smtp_config(db)
        config["smtpPass"] = encrypt_secret(
            existing.get("smtpPass") or "", purpose=SMTP_PASSWORD_PURPOSE
        ) or ""

    value = json.dumps(config, ensure_ascii=False)
    result = await db.execute(
        select(XianyuSysSetting).where(
            XianyuSysSetting.setting_key == SMTP_CONFIG_SETTING_KEY
        )
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.setting_value = value
    else:
        db.add(XianyuSysSetting(setting_key=SMTP_CONFIG_SETTING_KEY, setting_value=value))
    await db.commit()
    return config


def build_public_smtp_config(config: dict[str, Any]) -> dict[str, Any]:
    """返回不含密码明文的公开视图。密码字段返回 True/False 表示是否已配置。"""
    public = dict(config)
    # 同时处理 camelCase 和 snake_case 的密码字段
    for key in ("smtpPass", "smtp_pass"):
        if key in public:
            public[key] = bool(public[key])
    return public


# ── SMTP 发送 ─────────────────────────────────────────────────
def _build_message(
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body: str,
) -> str:
    """构建纯文本邮件消息。"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    return msg.as_string()


def _smtp_send_sync(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_email: str,
    to_email: str,
    message: str,
    timeout_seconds: int,
) -> dict:
    """执行阻塞 SMTP I/O；调用方须在 worker 线程中运行。"""
    if smtp_port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            smtp_host, smtp_port, timeout=max(timeout_seconds, 10), context=context
        ) as smtp:
            smtp.login(smtp_user, smtp_pass)
            return smtp.sendmail(from_email, [to_email], message)

    with smtplib.SMTP(
        smtp_host, smtp_port, timeout=max(timeout_seconds, 10)
    ) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        return smtp.sendmail(from_email, [to_email], message)


async def send_verification_email(
    db: AsyncSession,
    email: str,
    purpose: str,
) -> str:
    """发送验证码邮件。返回生成的验证码。

    raises:
        ValueError: SMTP 未配置或配置不完整、被频率限制
        RedisUnavailableError: Redis 不可用
    """
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("邮箱不能为空")
    if purpose not in PURPOSE_TEXT_MAP:
        raise ValueError("无效的验证码用途")

    # 频率限制
    if await check_send_rate(email):
        raise ValueError("发送过于频繁，请 60 秒后重试")

    # 加载 SMTP 配置
    config = await load_email_smtp_config(db)
    smtp_host = str(config.get("smtpHost") or "").strip()
    smtp_port = int(config.get("smtpPort") or 0)
    smtp_user = str(config.get("smtpUser") or "").strip()
    smtp_pass = str(config.get("smtpPass") or "").strip()
    from_email = str(config.get("fromEmail") or "").strip() or smtp_user
    from_name = str(config.get("fromName") or "").strip() or "闲鱼助手"

    if not smtp_host or not smtp_port or not smtp_user or not smtp_pass:
        raise ValueError(
            "邮件服务未配置，请先在系统设置中配置 SMTP 服务器信息"
        )

    # 生成并存储验证码
    code = generate_code()
    await store_code(email, purpose, code)

    purpose_text = PURPOSE_TEXT_MAP[purpose]
    subject = f"【闲鱼助手】您的{purpose_text}验证码"
    body = (
        f"您正在进行{purpose_text}操作。\n\n"
        f"验证码：{code}\n\n"
        f"验证码 5 分钟内有效，请勿告知他人。\n"
        f"如非本人操作，请忽略此邮件。\n"
    )

    message = _build_message(from_email, from_name, email, subject, body)

    # 在 worker 线程中执行阻塞 SMTP I/O
    try:
        await asyncio.to_thread(
            _smtp_send_sync,
            smtp_host,
            smtp_port,
            smtp_user,
            smtp_pass,
            from_email,
            email,
            message,
            30,
        )
    except Exception:
        logger.error("发送验证码邮件失败 to=%s purpose=%s", email, purpose, exc_info=True)
        # 发送失败时清除验证码，避免无效验证码残留
        await redis_delete(f"{CODE_KEY_PREFIX}{email}:{purpose}")
        raise ValueError("验证码邮件发送失败，请检查 SMTP 配置或稍后重试")

    await _mark_sent(email)
    logger.info("验证码邮件已发送 to=%s purpose=%s", email, purpose)
    return code
