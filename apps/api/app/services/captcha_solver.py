"""
滑块验证处理服务
================

实现两部分能力：

1. **智能检测**：从 MTOP API 响应中检测滑块/人机验证需求
   - 关键词：FAIL_SYS_USER_VALIDATE / RGV587_ERROR / 被挤爆啦 / CAPTCHA_NEEDED
   - 提取验证 URL（data.url）

2. **操作指引**：为前端提供详细的分步操作指引
   - 检测到滑块后返回结构化指引数据
   - 包含：访问 URL、操作步骤、Cookie 更新提示

3. **自动拖动**：调用 crawler-service 的 Playwright 滑块求解接口
   - 通过 HTTP 调用 crawler-service 的 /api/goofish/slide-solve
   - 失败时回退到人工处理指引

调用方式：
- detect_captcha(response) -> 检测是否需要滑块
- build_instructions(account_id, captcha_url) -> 构建操作指引
- try_auto_solve(account_id) -> 调用 Playwright 自动求解
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy import text

from ..core.config import settings
from ..core.cookie_crypto import decrypt_cookie_if_needed, encrypt_cookie_for_storage
from ..core.database import async_session

logger = logging.getLogger(__name__)


def _merge_cookies(old_str: str, new_str: str) -> str:
    """增量合并两个 Cookie 字符串，新 Cookie 覆盖同名旧字段。

    浏览器中的 Cookie 只刷新了部分字段（如 cna/isg/x5sec/_m_h5_tk），
    登录态相关 Cookie（如 unb/cookie2/_tb_token_）仍需保留旧的。
    """
    merged = {}
    for part in (old_str or "").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            merged[k.strip()] = v.strip()
    for part in (new_str or "").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            merged[k.strip()] = v.strip()  # 新覆盖旧
    return "; ".join(f"{k}={v}" for k, v in merged.items())


# ============================================================
# 滑块验证检测关键词
# ============================================================
CAPTCHA_KEYWORDS = (
    "FAIL_SYS_USER_VALIDATE",
    "RGV587_ERROR",
    "被挤爆啦",
    "CAPTCHA_NEEDED",
    "xcaptcha",
    "baxia",
    "punish",
)

CAPTCHA_URL_KEYWORDS = (
    "url",
    "captcha_url",
    "captchaUrl",
    "verifyUrl",
    "verify_url",
)


@dataclass
class CaptchaDetectResult:
    """滑块检测结果"""
    detected: bool
    captcha_url: Optional[str] = None
    reason: Optional[str] = None
    raw_response: Optional[dict] = None


@dataclass
class CaptchaInstructions:
    """操作指引"""
    account_id: int
    captcha_url: Optional[str]
    steps: list[str] = field(default_factory=list)
    title: str = "检测到账号需要完成滑块验证"
    auto_solve_available: bool = True
    manual_fallback_url: str = "https://www.goofish.com/"
    message: str = ""


# ============================================================
# 1. 智能检测
# ============================================================
def detect_captcha_from_response(response: dict | str | None) -> CaptchaDetectResult:
    """从 MTOP API 响应中检测滑块验证需求。

    支持两种输入：
    - dict: 完整的 MTOP 响应 JSON
    - str: 响应文本（直接搜索关键词）

    返回 CaptchaDetectResult，包含验证 URL（如果有的话）。
    """
    if not response:
        return CaptchaDetectResult(detected=False)

    if isinstance(response, str):
        text_lower = response.lower()
        for kw in CAPTCHA_KEYWORDS:
            if kw.lower() in text_lower:
                return CaptchaDetectResult(
                    detected=True,
                    reason=f"响应包含关键词: {kw}",
                )
        return CaptchaDetectResult(detected=False)

    # dict 类型：先查 ret 字段，再查 data.url
    ret_list = response.get("ret") or []
    if isinstance(ret_list, list):
        ret_str = " | ".join(str(r) for r in ret_list)
    else:
        ret_str = str(ret_list)

    for kw in CAPTCHA_KEYWORDS:
        if kw in ret_str:
            # 尝试提取验证 URL
            data = response.get("data") or {}
            captcha_url = None
            if isinstance(data, dict):
                for url_key in CAPTCHA_URL_KEYWORDS:
                    if url_key in data and data[url_key]:
                        captcha_url = str(data[url_key])
                        break

            return CaptchaDetectResult(
                detected=True,
                captcha_url=captcha_url,
                reason=f"ret 包含 {kw}",
                raw_response=response,
            )

    # 兜底：检查整个响应的字符串形式
    response_str = str(response)
    for kw in CAPTCHA_KEYWORDS:
        if kw in response_str:
            return CaptchaDetectResult(
                detected=True,
                reason=f"响应包含关键词: {kw}",
                raw_response=response if isinstance(response, dict) else None,
            )

    return CaptchaDetectResult(detected=False)


# ============================================================
# 2. 操作指引
# ============================================================
def build_captcha_instructions(
    account_id: int,
    captcha_url: Optional[str] = None,
    account_name: Optional[str] = None,
) -> CaptchaInstructions:
    """构建详细的滑块验证操作指引。

    返回的指引包含：
    - 自动求解：调用 Playwright 自动拖动（auto_solve_available=True）
    - 人工兜底：4 步指引（访问闲鱼→完成验证→复制 Cookie→更新 Cookie）
    """
    steps = [
        '【方案一·自动求解】点击下方"自动求解"按钮，系统将启动浏览器自动拖动滑块完成验证（推荐先尝试）',
        "【方案二·人工处理】如果自动求解失败，请按以下步骤操作：",
        "  1. 点击访问闲鱼主页 https://www.goofish.com/ 并登录（如已登录可跳过）",
        "  2. 在闲鱼页面完成滑块验证（通常出现在消息、商品发布等场景）",
        "  3. 验证通过后，按 F12 打开开发者工具 → Application → Cookies → 复制 .goofish.com 域下的完整 Cookie",
        '  4. 返回本页面，点击"手动更新 Cookie"按钮，粘贴复制的 Cookie 并保存',
        '  5. 保存后点击"启动连接"，系统会自动刷新 WebSocket Token 并重连',
    ]

    name_prefix = f"账号 {account_name or account_id} " if account_id else ""
    return CaptchaInstructions(
        account_id=account_id,
        captcha_url=captcha_url,
        steps=steps,
        title=f"{name_prefix}检测到滑块验证",
        auto_solve_available=True,
        message=(
            "检测到账号需要完成滑块验证。请先尝试自动求解；"
            "如自动求解失败，请按指引手动完成验证并更新 Cookie。"
            "更新 Cookie 后点击启动连接，会自动刷新 Token，"
            "滑块校验生效会延迟，稍等片刻会自动连接。"
        ),
    )


# ============================================================
# 3. Playwright 自动求解
# ============================================================
# 闲鱼消息页面 URL（对标商业版 xianyu_slider_stealth.py:124）
# 关键：只有消息页面才会出现滑块弹窗，首页本身不会弹出弹窗
CAPTCHA_TARGET_URL = "https://www.goofish.com/im"


async def try_auto_solve(
    account_id: int,
    target_url: Optional[str] = None,
    headless: bool = True,
    max_retries: int = 3,
) -> dict:
    """调用 crawler-service 的 Playwright 滑块求解接口。

    Args:
        account_id: 账号 ID（用于读取 Cookie）
        target_url: 目标页面 URL（默认闲鱼消息页面 https://www.goofish.com/im）
        headless: 是否无头模式（默认 true，在后端运行不弹出浏览器窗口）
        max_retries: 最大重试次数

    Returns:
        {
            "success": bool,
            "solved": bool,
            "captchaDetected": bool,
            "attempts": int,
            "error": Optional[str],
            "durationMs": int,
        }
    """
    # 读取账号 Cookie
    try:
        async with async_session() as db:
            row = (await db.execute(
                text(
                    "SELECT encrypted_cookie FROM xianyu_account_auth "
                    "WHERE account_id = :aid AND deleted = 0 LIMIT 1"
                ),
                {"aid": account_id},
            )).mappings().first()
    except Exception as exc:
        logger.error(
            "读取滑块账号 Cookie 失败 errorType=%s",
            type(exc).__name__,
        )
        return {
            "success": False,
            "solved": False,
            "captchaDetected": False,
            "attempts": 0,
            "error": "读取账号授权信息失败，请稍后重试",
            "durationMs": 0,
        }

    if not row:
        return {
            "success": False,
            "solved": False,
            "captchaDetected": False,
            "attempts": 0,
            "error": "账号不存在或未配置 Cookie",
            "durationMs": 0,
        }

    cookie_str = decrypt_cookie_if_needed(row["encrypted_cookie"])
    if not cookie_str:
        return {
            "success": False,
            "solved": False,
            "captchaDetected": False,
            "attempts": 0,
            "error": "Cookie 解密失败",
            "durationMs": 0,
        }

    # 调用 crawler-service
    crawler_url = settings.crawler_base_url
    endpoint = f"{crawler_url.rstrip('/')}/api/goofish/slide-solve"

    # 内部 token
    internal_token = (
        getattr(settings, "internal_api_token", None)
        or os.environ.get("INTERNAL_API_TOKEN")
        or "dev-only-internal-api-token-change-me-32-chars"
    )
    payload = {
        "cookie": cookie_str,
        "targetUrl": target_url or CAPTCHA_TARGET_URL,
        "headless": headless,
        "maxRetries": max_retries,
        "timeoutMs": 30000,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Internal-Token": internal_token,
    }

    started = time.time()
    try:
        async with httpx.AsyncClient(
            timeout=120.0,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            data = resp.json()
    except Exception as exc:
        logger.error(
            "调用 crawler-service 滑块求解失败 errorType=%s",
            type(exc).__name__,
        )
        return {
            "success": False,
            "solved": False,
            "captchaDetected": False,
            "attempts": 0,
            "error": "滑块求解服务暂不可用，请稍后重试或改为手动处理",
            "durationMs": int((time.time() - started) * 1000),
        }

    duration_ms = int((time.time() - started) * 1000)
    new_cookie_str = data.get("cookieStr") or ""
    merged_cookie = ""

    # 如果过滑块成功且获取了新 Cookie，增量合并到数据库
    # 关键：浏览器中的 Cookie 包含 cna/isg/x5sec 等 JS 写入的风控字段，
    # 这些字段是 requests 无法获取的。必须合并回数据库才能让 Token API 通过。
    if data.get("ok") and data.get("solved") and new_cookie_str:
        merged_cookie = _merge_cookies(cookie_str, new_cookie_str)
        if merged_cookie and merged_cookie != cookie_str:
            try:
                merged_encrypted = encrypt_cookie_for_storage(merged_cookie)
                async with async_session() as db:
                    await db.execute(
                        text(
                            "UPDATE xianyu_account_auth "
                            "SET encrypted_cookie = :enc, updated_time = NOW() "
                            "WHERE account_id = :aid AND deleted = 0"
                        ),
                        {"enc": merged_encrypted, "aid": account_id},
                    )
                    await db.commit()
                logger.info(
                    "滑块求解后 Cookie 已合并并保存到数据库 accountId=%d newFields=%d",
                    account_id,
                    len(new_cookie_str.split(";")),
                )
            except Exception as exc:
                logger.error(
                    "保存合并后的 Cookie 失败 errorType=%s",
                    type(exc).__name__,
                )

    return {
        "success": bool(data.get("ok")),
        "solved": bool(data.get("solved")),
        "captchaDetected": bool(data.get("captchaDetected")),
        "attempts": int(data.get("attempts") or 0),
        "error": data.get("error"),
        "screenshotPath": data.get("screenshotPath"),
        "durationMs": duration_ms,
        "cookieStr": new_cookie_str if data.get("ok") else "",
        "mergedCookie": merged_cookie,
    }


# ============================================================
# 4. 综合处理：检测 + 通知 + 自动求解
# ============================================================
async def _verify_cookie_via_token_api(account_id: int) -> bool:
    """滑块求解成功后，调用 Token API 二次验证 Cookie 是否真正可用。

    滑块求解器在 Cookie Session 已过期时会误报成功（页面跳转到登录页，
    没有滑块组件）。此处通过 Token API 的实际响应来确认 Cookie 真实可用性。

    Args:
        account_id: 账号 ID
    Returns:
        True: Cookie 可用，Token API 返回 SUCCESS
        False: Cookie 已过期（FAIL_SYS_SESSION_EXPIRED）或不可用
    """
    try:
        async with async_session() as db:
            row = (await db.execute(
                text(
                    "SELECT encrypted_cookie, encrypted_token "
                    "FROM xianyu_account_auth "
                    "WHERE account_id = :aid AND deleted = 0 LIMIT 1"
                ),
                {"aid": account_id},
            )).mappings().first()
        if not row:
            logger.warning("_verify_cookie_via_token_api: 账号不存在 accountId=%d", account_id)
            return False

        cookie_str = decrypt_cookie_if_needed(row["encrypted_cookie"])
        if not cookie_str:
            logger.warning("_verify_cookie_via_token_api: Cookie 为空 accountId=%d", account_id)
            return False

        m_h5_tk = None
        if row["encrypted_token"]:
            m_h5_tk = decrypt_cookie_if_needed(row["encrypted_token"])

        # 调用 ws_token 模块的完整 Token 获取流程
        # （会自动尝试 cookie 中的 _m_h5_tk、DB 中的 _m_h5_tk、刷新 _m_h5_tk 三种路径）
        from .ws_token import get_ws_token_with_refreshed_m_h5_tk
        access_token, _, error_type, _ = get_ws_token_with_refreshed_m_h5_tk(cookie_str, m_h5_tk)
        if access_token:
            logger.info(
                "_verify_cookie_via_token_api: Cookie 验证通过 accountId=%d, accessToken长度=%d",
                account_id, len(access_token),
            )
            return True
        logger.warning(
            "_verify_cookie_via_token_api: Cookie 不可用 accountId=%d, error_type=%s",
            account_id, error_type,
        )
        return False
    except Exception:
        logger.error("_verify_cookie_via_token_api 异常 accountId=%d", account_id, exc_info=True)
        return False


async def handle_captcha_for_account(
    account_id: int,
    response: dict | str | None = None,
    auto_solve: bool = False,
) -> dict:
    """综合处理账号的滑块验证场景。

    1. 如果提供了 response，先检测是否真的需要滑块
    2. 如果检测到，写入 cookie_status=0 并通知用户
    3. 如果 auto_solve=True，尝试自动求解
    4. 自动求解成功后，刷新 token 并恢复 cookie_status

    Returns:
        {
            "detected": bool,
            "captchaUrl": Optional[str],
            "instructions": dict,
            "autoSolveResult": Optional[dict],
            "recovered": bool,  # 是否成功恢复
        }
    """
    from .notify_dispatcher import notify_captcha_required

    detected = False
    captcha_url = None
    if response is not None:
        result = detect_captcha_from_response(response)
        detected = result.detected
        captcha_url = result.captcha_url

    instructions = build_captcha_instructions(account_id, captcha_url)
    auto_solve_result = None
    recovered = False

    if detected or auto_solve:
        # 通知用户
        try:
            await notify_captcha_required(
                account_id,
                scene=f"账号触发滑块验证（自动求解={'开启' if auto_solve else '关闭'}）",
            )
        except Exception:
            logger.debug("notify_captcha_required 异常，忽略", exc_info=True)

    if auto_solve and (detected or response is None):
        logger.info("开始为账号 %d 自动求解滑块", account_id)
        auto_solve_result = await try_auto_solve(account_id)

        if auto_solve_result.get("solved"):
            logger.info("账号 %d 滑块自动求解成功", account_id)

            # === 关键二次验证：调用 Token API 确认 Cookie 真实可用 ===
            # 滑块求解器在 Cookie Session 已过期时会误报成功（页面跳转到登录页，
            # 没有滑块组件）。此处用 Token API 做最终验证，避免错误恢复 cookie_status=1
            # 导致后续 ws_client 校验失败。
            cookie_valid = await _verify_cookie_via_token_api(account_id)
            if not cookie_valid:
                logger.warning(
                    "账号 %d 滑块求解器报告成功，但 Token API 验证 Cookie 仍不可用，"
                    "Cookie Session 已真正过期，需要用户重新扫码登录",
                    account_id,
                )
                # 不恢复 cookie_status=1，保持 0 状态，并附带明确错误信息
                try:
                    async with async_session() as db:
                        for table in ("xianyu_account_auth", "xianyu_account_runtime"):
                            await db.execute(
                                text(
                                    f"UPDATE {table} SET cookie_status = 0, "
                                    f"last_login_status_code = 'SESSION_EXPIRED', "
                                    f"last_login_status_message = 'Cookie Session 已过期，请重新扫码登录闲鱼账号', "
                                    f"last_login_check_time = NOW(), updated_time = NOW() "
                                    f"WHERE account_id = :aid"
                                ),
                                {"aid": account_id},
                            )
                        await db.commit()
                except Exception:
                    logger.warning("更新 cookie_status 失败 accountId=%d", account_id, exc_info=True)

                # 在 auto_solve_result 中附加验证失败标记，让前端能展示真实原因
                auto_solve_result["cookieVerified"] = False
                auto_solve_result["error"] = (
                    "滑块已通过，但 Cookie Session 已真正过期（FAIL_SYS_SESSION_EXPIRED），"
                    "请前往账号管理页重新扫码登录闲鱼账号获取新 Cookie"
                )
                # 不标记 recovered=True，让前端引导用户重新登录
            else:
                logger.info("账号 %d Cookie 二次验证通过，恢复 cookie_status=1", account_id)
                recovery_persisted = False

                # 恢复 cookie_status=1，last_login_status_code 必须为 'OK'
                # （_load_ws_credentials 校验要求 login_status_code == "OK"）
                try:
                    async with async_session() as db:
                        for table in ("xianyu_account_auth", "xianyu_account_runtime"):
                            await db.execute(
                                text(
                                    f"UPDATE {table} SET cookie_status = 1, "
                                    f"last_login_status_code = 'OK', "
                                    f"last_login_status_message = '滑块验证已通过（自动求解+Token API 二次验证）', "
                                    f"last_login_check_time = NOW(), updated_time = NOW() "
                                    f"WHERE account_id = :aid"
                                ),
                                {"aid": account_id},
                            )
                        await db.commit()
                    recovery_persisted = True
                except Exception:
                    logger.warning("更新 cookie_status 失败 accountId=%d", account_id, exc_info=True)

                if recovery_persisted:
                    recovered = True
                    # 只有二次验证与数据库状态均成功后，才能解除持久化的
                    # Cookie 失效通知世代；否则未来真实失效会被错误抑制。
                    from .notify_dispatcher import clear_cookie_expired_state

                    await clear_cookie_expired_state(account_id)

                    # 触发 _m_h5_tk 刷新（不触发 ws_token 刷新，避免 Session
                    # 过期时 ws_client 覆盖 cookie_status=0）。
                    try:
                        from .cookie_token_refresher import force_refresh_account
                        await force_refresh_account(account_id, "mh5tk")
                    except Exception:
                        logger.warning("自动刷新 token 失败 accountId=%d", account_id, exc_info=True)
                else:
                    auto_solve_result["cookieVerified"] = True
                    auto_solve_result["error"] = (
                        "Cookie 已通过验证，但恢复状态保存失败；系统仍保持不可用状态，"
                        "请稍后重试，避免自动化任务使用未确认的凭据。"
                    )

    return {
        "detected": detected,
        "captchaUrl": captcha_url,
        "instructions": {
            "title": instructions.title,
            "steps": instructions.steps,
            "message": instructions.message,
            "autoSolveAvailable": instructions.auto_solve_available,
            "manualFallbackUrl": instructions.manual_fallback_url,
        },
        "autoSolveResult": auto_solve_result,
        "recovered": recovered,
    }
