"""
闲鱼网页版扫码登录模块。
直接调用闲鱼官方 API，使用 requests.Session() 自动管理 Cookie。

扫码登录分三阶段采集 Cookie，最终合并保存：
阶段1 get_m_h5_tk()：请求 h5api.m.goofish.com，获取 _m_h5_tk、_m_h5_tk_enc 和其他 Cookie
阶段2 get_login_params()：访问 passport.goofish.com/mini_login.htm，继续采集 Set-Cookie
阶段3 poll_qr_status()：用户确认后，获取 unb 和其他会话 Cookie
合并规则：三阶段 Cookie 全部合并；同名 Cookie 后获取覆盖前值
"""

import hashlib
import io
import json
import logging
import random
import re
import secrets
import threading
import time
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional

import qrcode
import requests

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

APP_KEY = "34839810"
H5_API = "https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/"
LOGIN_PAGE = "https://passport.goofish.com/mini_login.htm"
QR_GENERATE = "https://passport.goofish.com/newlogin/qrcode/generate.do"
QR_QUERY = "https://passport.goofish.com/newlogin/qrcode/query.do"

H_COMMON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://passport.goofish.com/",
    "Origin": "https://passport.goofish.com",
}

H_PAGE = {
    **H_COMMON,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

H_API = {
    **H_COMMON,
    "Accept": "application/json, text/plain, */*",
}

POLL_INTERVAL = 0.8
SESSION_TIMEOUT = 300  # 5 分钟
MAX_ACTIVE_SESSIONS = 32


class QrSessionCapacityError(RuntimeError):
    """Raised when every bounded QR session slot is still active."""

# 上海时区 UTC+8
SHANGHAI_TZ = timezone(timedelta(hours=8))


def _shanghai_now() -> datetime:
    """返回当前上海时间"""
    return datetime.now(SHANGHAI_TZ)


def _json_or_raise(resp: requests.Response, stage: str) -> dict:
    """解析闲鱼接口 JSON；若返回 HTML/纯文本/风控提示，抛出明确错误，避免 Java 侧收到 Invalid... 非 JSON。"""
    text = resp.text or ""
    if resp.status_code >= 400:
        raise RuntimeError(f"{stage} HTTP {resp.status_code}: {text[:200]}")
    content_type = (resp.headers.get("content-type") or "").lower()
    stripped = text.strip()
    if "json" not in content_type and not (stripped.startswith("{") or stripped.startswith("[")):
        raise RuntimeError(f"{stage} 返回非 JSON 内容: {stripped[:200] or '<empty>'}")
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{stage} JSON 解析失败: {stripped[:200] or '<empty>'}") from exc


# ==================== 会话管理 ====================

_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def _session_operation_lock(session_data: dict) -> threading.Lock:
    # ``setdefault`` gives manually restored/test sessions the same single
    # lock even when two worker threads first touch them concurrently.
    return session_data.setdefault("operation_lock", threading.Lock())


def _close_session_data(session_data: dict, *, log_message: str) -> None:
    """Close one detached session after any in-flight operation completes."""

    operation_lock = _session_operation_lock(session_data)
    with operation_lock:
        session = session_data.get("session")
        try:
            if session is not None:
                session.close()
        except Exception as exc:
            logger.debug("%s errorType=%s", log_message, type(exc).__name__)


def _is_terminal_session(session_data: dict) -> bool:
    return str(session_data.get("status") or "").casefold() in {
        "confirmed",
        "expired",
        "cancelled",
        "failed",
        "verification_required",
    }


def _preflight_session_capacity(normalized_owner: str) -> None:
    """Reject an obviously full registry before making upstream requests.

    This is deliberately only a fast preflight. ``generate_qrcode`` repeats
    the admission decision atomically after the QR provider calls because
    another request may consume the last slot in the meantime.
    """

    with _lock:
        owner_can_replace = bool(normalized_owner) and any(
            str(session_data.get("owner_key") or "").strip().casefold()
            == normalized_owner
            for session_data in _sessions.values()
        )
        terminal_can_be_evicted = any(
            _is_terminal_session(session_data)
            for session_data in _sessions.values()
        )
        if (
            len(_sessions) >= MAX_ACTIVE_SESSIONS
            and not owner_can_replace
            and not terminal_can_be_evicted
        ):
            raise QrSessionCapacityError(
                "扫码登录会话已达容量上限，请稍后重试"
            )


def _cleanup_expired():
    """清理过期会话。"""
    return cleanup_expired_sessions()


def cleanup_expired_sessions() -> int:
    """Remove only expired QR sessions and close their HTTP resources."""
    now = time.time()
    with _lock:
        expired = [
            _sessions.pop(sid)
            for sid, session_data in list(_sessions.items())
            if now - float(session_data.get("created_at") or 0) > SESSION_TIMEOUT
        ]
    for session_data in expired:
        _close_session_data(
            session_data,
            log_message="关闭过期扫码会话失败",
        )
    return len(expired)


# ==================== 核心函数 ====================


def _get_m_h5_tk(session: requests.Session) -> str:
    """Step 1: 获取签名令牌 _m_h5_tk。

    闲鱼 API 的 _m_h5_tk cookie 获取流程比较特殊：
    - 第一次 GET 只返回 cookie2，不返回 _m_h5_tk
    - 需要做一次带签名的 POST（即使 token 为空），POST 响应会设置 _m_h5_tk
    - 提取 _m_h5_tk 中的真实 token 后，再用真实 token 做第二次 POST 刷新
    """
    # 第一次 GET — 获取初始 Cookie（cookie2）
    session.get(H5_API, headers=H_API, timeout=20)

    # 第一次 POST — 用空 token 触发 _m_h5_tk 下发
    # 此时服务器会返回 "令牌为空" 错误，但会在 Set-Cookie 中设置 _m_h5_tk
    t_ms = int(time.time() * 1000)
    data_str = '{"bizScene":"home"}'
    sign = hashlib.md5(f"&{t_ms}&{APP_KEY}&{data_str}".encode()).hexdigest()

    session.post(H5_API, headers=H_API, data={
        "jsv": "2.7.2", "appKey": APP_KEY, "t": str(t_ms), "sign": sign,
        "v": "1.0", "type": "originaljson", "dataType": "json",
        "timeout": "20000", "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
        "data": data_str
    }, timeout=20)

    # 从响应 Cookie 中提取 _m_h5_tk
    m_h5_tk = session.cookies.get("_m_h5_tk")
    if not m_h5_tk:
        raise RuntimeError("无法获取 _m_h5_tk Cookie")

    token = m_h5_tk.split("_")[0]
    t_ms2 = int(time.time() * 1000)
    sign2 = hashlib.md5(f"{token}&{t_ms2}&{APP_KEY}&{data_str}".encode()).hexdigest()

    # 第二次 POST — 用真实 token 刷新，获取完整业务 Cookie
    session.post(H5_API, headers=H_API, data={
        "jsv": "2.7.2", "appKey": APP_KEY, "t": str(t_ms2), "sign": sign2,
        "v": "1.0", "type": "originaljson", "dataType": "json",
        "timeout": "20000", "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
        "data": data_str
    }, timeout=20)

    return session.cookies.get("_m_h5_tk", "")


def _get_login_params(session: requests.Session) -> dict:
    """Step 2: 从登录页面提取 loginFormData。"""
    params = {
        "lang": "zh_cn", "appName": "xianyu", "appEntrance": "web",
        "styleType": "vertical", "bizParams": "", "notLoadSsoView": "false",
        "notKeepLogin": "false", "isMobile": "false", "qrCodeFirst": "false",
        "stie": "77", "rnd": str(random.random())
    }
    resp = session.get(LOGIN_PAGE, headers=H_PAGE, params=params, timeout=20)

    match = re.search(r"window\.viewData\s*=\s*(\{.*?\});", resp.text, re.DOTALL)
    if not match:
        match = re.search(r"var\s+viewData\s*=\s*(\{.*?\});", resp.text, re.DOTALL)
    if not match:
        raise RuntimeError("无法从登录页面提取 viewData")

    login_form = json.loads(match.group(1))["loginFormData"]
    login_form["umidTag"] = "SERVER"
    return login_form


def _generate_qrcode(session: requests.Session, login_form: dict) -> str:
    """Step 3: 生成二维码，返回 Base64 图片。"""
    resp = session.get(QR_GENERATE, headers=H_API, params=login_form, timeout=20)
    result = _json_or_raise(resp, "生成二维码")
    qr_data = result.get("content", {}).get("data") or {}

    code_content = qr_data.get("codeContent")
    if not code_content:
        raise RuntimeError(f"二维码内容为空，返回内容: {json.dumps(result, ensure_ascii=False)[:300]}")

    # 更新 login_form，补充 t 和 ck 用于后续轮询
    login_form["t"] = qr_data.get("t", "")
    login_form["ck"] = qr_data.get("ck", "")

    # 生成二维码图片
    img = qrcode.make(code_content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _poll_status(session: requests.Session, login_form: dict, timeout: int = SESSION_TIMEOUT) -> dict:
    """Step 4: 轮询扫码状态，阻塞直到完成或超时。"""
    start = time.time()
    while time.time() - start < timeout:
        resp = session.post(QR_QUERY, headers=H_API, data=login_form, timeout=20)
        data = _json_or_raise(resp, "轮询二维码状态").get("content", {}).get("data") or {}
        status = data["qrCodeStatus"]

        if status == "CONFIRMED":
            if data.get("iframeRedirect"):
                return {"status": "verification_required", "iframe_redirect_url": data.get("iframeRedirectUrl")}
            # 收集关键 Cookie
            cookies = {k: v for k, v in session.cookies.items()}
            return {"status": "confirmed", "cookies": cookies}
        elif status == "EXPIRED":
            return {"status": "expired"}
        elif status == "SCANED":
            logger.info("已扫码，等待确认...")
        elif status != "NEW":
            return {"status": "cancelled"}

        time.sleep(POLL_INTERVAL)

    return {"status": "expired"}


def _poll_status_once(session: requests.Session, login_form: dict) -> dict:
    """单次轮询，非阻塞。"""
    try:
        resp = session.post(QR_QUERY, headers=H_API, data=login_form, timeout=20)
        data = _json_or_raise(resp, "轮询二维码状态").get("content", {}).get("data") or {}
        status = str(data["qrCodeStatus"] or "").upper()

        if status == "CONFIRMED":
            if data.get("iframeRedirect"):
                return {"status": "verification_required", "iframe_redirect_url": data.get("iframeRedirectUrl")}
            cookies = {k: v for k, v in session.cookies.items()}
            return {"status": "confirmed", "cookies": cookies}
        if status == "NEW":
            return {"status": "new"}
        if status == "SCANED":
            return {"status": "scaned"}
        if status == "EXPIRED":
            return {"status": "expired"}
        return {"status": "cancelled"}
    except Exception as exc:
        logger.error(
            "二维码状态轮询失败 errorType=%s",
            type(exc).__name__,
        )
        return {"status": "error", "message": "二维码状态暂时无法获取，请稍后重试"}


# ==================== 公开 API ====================


def generate_qrcode(
    user_id: int = None,
    tenant_id: int = None,
    *,
    owner_key: str | None = None,
) -> dict:
    """
    创建新的扫码登录会话，返回 sessionId 和 Base64 二维码图片。
    user_id/tenant_id: 当前登录用户的上下文，扫码成功后用于归属账号。
    返回: {"sessionId": str, "qrImage": str (base64 data URI)}
    """
    _cleanup_expired()
    normalized_owner = str(owner_key or "").strip().casefold()
    _preflight_session_capacity(normalized_owner)

    session_id = secrets.token_urlsafe(24)
    s = requests.Session()
    s.trust_env = False
    login_form = {}

    try:
        _get_m_h5_tk(s)
        login_form = _get_login_params(s)
        qr_image = _generate_qrcode(s, login_form)
    except Exception as exc:
        try:
            s.close()
        except Exception as close_exc:
            logger.debug(
                "关闭未创建成功的扫码会话失败 errorType=%s",
                type(close_exc).__name__,
            )
        logger.error("生成二维码失败 errorType=%s", type(exc).__name__)
        raise RuntimeError("生成闲鱼登录二维码失败，请稍后重试") from exc

    created_at = time.time()
    session_data = {
        "session": s,
        "login_form": login_form,
        "qr_image": qr_image,
        "status": "new",
        "created_at": created_at,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "owner_key": normalized_owner,
        "operation_lock": threading.Lock(),
    }

    # Network setup happens before admission so a slow upstream request never
    # holds the process-wide registry lock. Admission itself is atomic: one
    # authenticated owner has at most one session and the process has a hard
    # upper bound. Terminal sessions are the only cross-owner eviction
    # candidates; active users are never displaced to admit a new request.
    cleanup_expired_sessions()
    detached: list[dict] = []
    at_capacity = False
    with _lock:
        if normalized_owner:
            for existing_id, existing_data in list(_sessions.items()):
                if (
                    str(existing_data.get("owner_key") or "").strip().casefold()
                    == normalized_owner
                ):
                    detached.append(_sessions.pop(existing_id))

        while len(_sessions) >= MAX_ACTIVE_SESSIONS:
            terminal = [
                (existing_id, existing_data)
                for existing_id, existing_data in _sessions.items()
                if _is_terminal_session(existing_data)
            ]
            if not terminal:
                at_capacity = True
                break
            evicted_id, _ = min(
                terminal,
                key=lambda item: float(item[1].get("created_at") or 0),
            )
            detached.append(_sessions.pop(evicted_id))

        if not at_capacity:
            _sessions[session_id] = session_data

    for old_session_data in detached:
        _close_session_data(
            old_session_data,
            log_message="关闭被替换或回收的扫码会话失败",
        )
    if at_capacity:
        _close_session_data(
            session_data,
            log_message="关闭超出容量的扫码会话失败",
        )
        raise QrSessionCapacityError("扫码登录会话已达容量上限，请稍后重试")

    logger.info(
        "闲鱼扫码登录会话已创建 sessionHash=%s userId=%s tenantId=%s",
        hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12],
        user_id,
        tenant_id,
    )
    return {"sessionId": session_id, "qrImage": qr_image}


def get_session_status(session_id: str) -> dict:
    """
    获取会话状态（单次轮询）。
    确认登录成功后不再返回原始 Cookie，仅返回安全的摘要信息。
    返回: {"status": "new"|"scaned"|"confirmed"|"expired"|"cancelled"|"verification_required", ...}
    """
    _cleanup_expired()

    with _lock:
        sdata = _sessions.get(session_id)
    if not sdata:
        return {"status": "expired", "message": "会话不存在或已过期"}

    operation_lock = _session_operation_lock(sdata)
    close_expired = False
    with operation_lock:
        with _lock:
            if _sessions.get(session_id) is not sdata:
                return {"status": "expired", "message": "会话不存在或已过期"}
            if time.time() - float(sdata.get("created_at") or 0) > SESSION_TIMEOUT:
                _sessions.pop(session_id, None)
                close_expired = True

        if close_expired:
            session = sdata.get("session")
            try:
                if session is not None:
                    session.close()
            except Exception as exc:
                logger.debug(
                    "关闭超时扫码会话失败 errorType=%s",
                    type(exc).__name__,
                )
            return {"status": "expired", "message": "登录超时"}

        # QR confirmation is one-shot. Replaying the immutable terminal result
        # avoids issuing a second request on the same requests.Session and also
        # lets clients safely retry after a lost response.
        terminal_result = sdata.get("terminal_result")
        if _is_terminal_session(sdata) and isinstance(terminal_result, dict):
            replay = dict(terminal_result)
            persistence_result = sdata.get("persistence_result")
            if isinstance(persistence_result, dict):
                replay.update(persistence_result)
            return replay

        polled = _poll_status_once(sdata["session"], sdata["login_form"])
        result = dict(polled)
        status = str(result.get("status") or "error").casefold()
        result["status"] = status

        if status == "confirmed":
            cookies = result.pop("cookies", None) or {}
            unb = str(cookies.get("unb") or "")
            result["unb"] = unb
            result["externalUid"] = unb
            sdata["saved_cookies"] = dict(cookies)
            sdata["terminal_result"] = dict(result)
        elif status in {
            "expired",
            "cancelled",
            "failed",
            "verification_required",
        }:
            sdata["terminal_result"] = dict(result)

        with _lock:
            if _sessions.get(session_id) is sdata:
                sdata["status"] = status

        persistence_result = sdata.get("persistence_result")
        if isinstance(persistence_result, dict):
            result.update(persistence_result)
        return result


def get_session_cookies(session_id: str) -> Optional[dict]:
    """
    内部使用：获取登录成功后的完整 Cookie 数据和用户上下文。
    仅在 status 为 confirmed 时返回有效数据。
    返回: {"cookies": dict, "user_id": int, "tenant_id": int, "cookie_text": str, "unb": str, "m_h5_tk": str}
    """
    with _lock:
        sdata = _sessions.get(session_id)
    if not sdata:
        return None
    operation_lock = _session_operation_lock(sdata)
    with operation_lock:
        with _lock:
            if _sessions.get(session_id) is not sdata:
                return None
            expired = (
                time.time() - float(sdata.get("created_at") or 0)
                > SESSION_TIMEOUT
            )
            if expired:
                _sessions.pop(session_id, None)

        if expired:
            session = sdata.get("session")
            try:
                if session is not None:
                    session.close()
            except Exception as exc:
                logger.debug(
                    "关闭超时扫码会话失败 errorType=%s",
                    type(exc).__name__,
                )
            return None

        # Prefer the cookies captured by get_session_status. If cookies() wins
        # the race, it performs the one permitted poll and records the same
        # terminal state for status() to replay later.
        saved_cookies = sdata.get("saved_cookies")
        if not saved_cookies:
            if _is_terminal_session(sdata):
                return None
            result = _poll_status_once(sdata["session"], sdata["login_form"])
            status = str(result.get("status") or "error").casefold()
            with _lock:
                if _sessions.get(session_id) is sdata:
                    sdata["status"] = status
            if status != "confirmed":
                if status in {
                    "expired",
                    "cancelled",
                    "failed",
                    "verification_required",
                }:
                    sdata["terminal_result"] = {
                        key: value
                        for key, value in result.items()
                        if key != "cookies"
                    }
                return None
            saved_cookies = dict(result.get("cookies") or {})
            unb = str(saved_cookies.get("unb") or "")
            sdata["saved_cookies"] = saved_cookies
            sdata["terminal_result"] = {
                "status": "confirmed",
                "unb": unb,
                "externalUid": unb,
            }

        cookies = dict(saved_cookies)
        return {
            "cookies": cookies,
            "cookie_text": _format_cookies(cookies),
            "unb": cookies.get("unb", ""),
            "m_h5_tk": cookies.get("_m_h5_tk", ""),
            "user_id": sdata.get("user_id"),
            "tenant_id": sdata.get("tenant_id"),
        }


def mark_session_persisted(session_id: str, result: dict) -> bool:
    """Attach a safe persistence receipt for idempotent status retries."""

    with _lock:
        sdata = _sessions.get(session_id)
    if not sdata:
        return False

    operation_lock = _session_operation_lock(sdata)
    with operation_lock:
        with _lock:
            if _sessions.get(session_id) is not sdata:
                return False
            if sdata.get("status") != "confirmed" or not sdata.get("saved_cookies"):
                return False
            sdata["persistence_result"] = {
                key: result[key]
                for key in (
                    "accountId",
                    "cookieStatus",
                    "expireTime",
                    "message",
                    "persisted",
                )
                if key in result
            }
    return True


def get_session_context(session_id: str) -> Optional[dict]:
    """获取会话的用户上下文，不执行轮询。"""
    with _lock:
        sdata = _sessions.get(session_id)
    if not sdata:
        return None
    if time.time() - float(sdata.get("created_at") or 0) > SESSION_TIMEOUT:
        cleanup_session(session_id)
        return None
    return {
        "user_id": sdata.get("user_id"),
        "tenant_id": sdata.get("tenant_id"),
        "owner_key": sdata.get("owner_key"),
        "status": sdata.get("status"),
    }


def cleanup_session(session_id: str):
    """清理指定会话。"""
    with _lock:
        session_data = _sessions.pop(session_id, None)
    if session_data:
        _close_session_data(session_data, log_message="关闭扫码会话失败")


def cleanup_owner_sessions(owner_key: str) -> int:
    """Close only QR sessions created by the authenticated owner."""

    normalized_owner = str(owner_key or "").strip().casefold()
    if not normalized_owner:
        return 0
    with _lock:
        owned = [
            _sessions.pop(session_id)
            for session_id, session_data in list(_sessions.items())
            if str(session_data.get("owner_key") or "").strip().casefold()
            == normalized_owner
        ]
    for session_data in owned:
        _close_session_data(
            session_data,
            log_message="关闭当前用户扫码会话失败",
        )
    return len(owned)


def cleanup_all():
    """清理所有会话。"""
    with _lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for session_data in sessions:
        _close_session_data(session_data, log_message="关闭扫码会话失败")


# ==================== 完整流程（独立运行） ====================


def xianyu_qr_login(blocking: bool = True, timeout: int = SESSION_TIMEOUT) -> dict:
    """
    完整扫码登录流程。
    - blocking=True: 阻塞等待扫码完成
    - blocking=False: 只生成二维码，返回 sessionId 和图片
    """
    s = requests.Session()
    s.trust_env = False
    _get_m_h5_tk(s)
    login_form = _get_login_params(s)
    qr_image = _generate_qrcode(s, login_form)

    if not blocking:
        return {"qr_image": qr_image, "session": s, "login_form": login_form}

    result = _poll_status(s, login_form, timeout)
    result["qr_image"] = qr_image
    return result


# ==================== Cookie 工具函数 ====================


def _format_cookies(cookies: dict) -> str:
    """
    将 dict 格式的 Cookie 合并为完整的 Cookie 字符串。
    格式: "key1=value1; key2=value2; ..."
    """
    if not cookies:
        return ""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _extract_unb(cookies: dict) -> str:
    """从 Cookie dict 中提取 unb"""
    if not cookies:
        return ""
    return cookies.get("unb", "")


def _extract_m_h5_tk(cookies: dict) -> str:
    """从 Cookie dict 中提取 _m_h5_tk"""
    if not cookies:
        return ""
    return cookies.get("_m_h5_tk", "")
