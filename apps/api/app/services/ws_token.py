"""
WebSocket Token 获取模块。
通过闲鱼 H5 API 获取 WebSocket 连接所需的 accessToken。
"""
import hashlib
import json
import logging
import re
import time
from typing import Optional, Tuple
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

APP_KEY = "34839810"
H5_API_BASE = "https://h5api.m.goofish.com/h5"
TOKEN_API = f"{H5_API_BASE}/mtop.taobao.idlemessage.pc.login.token/1.0/"
# _m_h5_tk 刷新 API（参考 Java XianyuApiUtils.refreshMH5Tk）
REFRESH_MH5TK_API = "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get"
REFRESH_MH5TK_URL = f"{H5_API_BASE}/{REFRESH_MH5TK_API}/1.0/"

# _call_token_api 返回的特殊标记：表示遇到滑块/人机验证（FAIL_SYS_USER_VALIDATE）
CAPTCHA_NEEDED = "__CAPTCHA_NEEDED__"

# ============================================================================
# accessToken 内存缓存（对标商业版 xy_token_cache 表）
# ============================================================================
# 商业版通过数据库表 xy_token_cache（5-10 小时 TTL）缓存 accessToken，99% 的连接
# 命中缓存跳过 mtop API 调用，实现 3 秒内连接。开源版用进程内字典实现等价功能，
# 避免每次连接都走 4 级降级链（最坏 125 秒）。
#
# 缓存键：unb（用户 ID）
# 缓存值：{access_token, m_h5_tk, device_id, cookie_str, expire_at}
# TTL：4 小时（比商业版略短，平衡安全性与性能）
_TOKEN_CACHE_TTL = 4 * 3600  # 4 小时
_token_cache: dict[str, dict] = {}


def cache_token(
    unb: str,
    access_token: str,
    m_h5_tk: str,
    cookie_str: str,
    ttl: int = _TOKEN_CACHE_TTL,
) -> None:
    """缓存 accessToken，按 unb 为键。"""
    if not unb or not access_token:
        return
    _token_cache[unb] = {
        "access_token": access_token,
        "m_h5_tk": m_h5_tk,
        "cookie_str": cookie_str,
        "expire_at": time.time() + ttl,
    }
    logger.info("Token 缓存已写入 unb=%s ttl=%ds", unb, ttl)


def get_cached_token(unb: str) -> Optional[dict]:
    """读取缓存的 accessToken。过期或不存在返回 None。"""
    if not unb:
        return None
    entry = _token_cache.get(unb)
    if not entry:
        return None
    if time.time() >= entry.get("expire_at", 0):
        _token_cache.pop(unb, None)
        logger.info("Token 缓存已过期 unb=%s", unb)
        return None
    return entry


def invalidate_cached_token(unb: str) -> None:
    """使缓存的 accessToken 失效（Cookie 失效或重新扫码登录时调用）。"""
    if unb and _token_cache.pop(unb, None):
        logger.info("Token 缓存已清除 unb=%s", unb)


def invalidate_all_cached_tokens() -> None:
    """清除所有缓存的 accessToken。"""
    count = len(_token_cache)
    _token_cache.clear()
    if count:
        logger.info("已清除全部 Token 缓存（%d 条）", count)

H_API = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/146.0.7680.177 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
    # 关键：Origin 头缺失会导致 mtop Token API 触发风控（FAIL_SYS_USER_VALIDATE），
    # 服务端据此判断请求是否来自浏览器。商业版始终携带此头。
    "Origin": "https://www.goofish.com",
    "Referer": "https://www.goofish.com/",
    # 浏览器指纹头，降低被风控拦截的概率
    "sec-ch-ua": '"Chromium";v="146", "Google Chrome";v="146", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "same-site",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "priority": "u=1, i",
}


def _make_sign(token: str, t_ms: int, data_str: str) -> str:
    """生成 Mtop 签名。"""
    raw = f"{token}&{t_ms}&{APP_KEY}&{data_str}"
    return hashlib.md5(raw.encode()).hexdigest()


def extract_m_h5_tk_from_cookie(cookie_str: str) -> Optional[str]:
    """从 Cookie 字符串中提取 _m_h5_tk 值。

    _m_h5_tk 格式: `{token}_{timestamp}` (下划线前的部分用于签名)
    """
    if not cookie_str:
        return None
    match = re.search(r'_m_h5_tk=([^;]+)', cookie_str)
    if match:
        return match.group(1)
    return None


def extract_unb_from_cookie(cookie_str: str) -> Optional[str]:
    """从 Cookie 字符串中提取 unb（用户 ID）值。"""
    if not cookie_str:
        return None
    match = re.search(r'unb=([^;]+)', cookie_str)
    if match:
        return match.group(1)
    return None


def generate_device_id(user_id: str) -> str:
    """生成与账号绑定的固定 deviceId（UUID v4 风格 + unb）。

    与商业版 xianyu_utils.generate_device_id 对齐，但使用 user_id 作为随机种子，
    确保同一账号每次生成相同的 deviceId（确定性）。这样 _call_token_api 和
    ws_client.device_id 属性可以独立调用并得到一致结果，满足"Token API 的
    deviceId 必须与 WS /reg 的 did 完全一致"的约束。

    - 生成标准 UUID v4 格式（36 字符）
    - 末尾拼接 "-" + user_id（unb）
    - 关键特性：deviceId 与账号 unb 绑定，与 _m_h5_tk 完全解耦，
      token 刷新不会改变 deviceId，服务端识别为"已知设备的正常令牌更新"，
      避免因 device 身份变化触发 FAIL_SYS_USER_VALIDATE 风控。
    """
    import random as _random
    # 使用 user_id 作为种子，确保同一账号每次生成相同的 deviceId
    rng = _random.Random(user_id or "")
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    result = []
    for i in range(36):
        if i in (8, 13, 18, 23):
            result.append("-")
        elif i == 14:
            result.append("4")
        elif i == 19:
            rand_val = int(16 * rng.random())
            result.append(chars[(rand_val & 0x3) | 0x8])
        else:
            rand_val = int(16 * rng.random())
            result.append(chars[rand_val])
    return "".join(result) + "-" + (user_id or "")


def _call_token_api(cookie_str: str, m_h5_tk: str) -> Optional[str]:
    """调用 Mtop Token API 获取 accessToken。返回 None 表示失败。"""
    token = m_h5_tk.split("_")[0] if "_" in m_h5_tk else m_h5_tk
    if not token:
        return None

    t_ms = int(time.time() * 1000)
    # data 中包含业务层 appKey（与 URL 中的网关 appKey=34839810 不同，缺一不可）
    # deviceId 使用与账号 unb 绑定的固定 UUID（商业版对齐），而非 _m_h5_tk 的 token 部分。
    # 这样 token 刷新时 deviceId 保持稳定，服务端识别为"已知设备的正常令牌更新"，
    # 避免因 device 身份变化触发 FAIL_SYS_USER_VALIDATE 风控。
    # 注意：此 deviceId 必须与 WS /reg 时的 did 完全一致
    unb = extract_unb_from_cookie(cookie_str) or ""
    device_id = generate_device_id(unb)
    data_dict = {
        "appKey": "444e9908a51d1cb236a27862abc769c9",
        "deviceId": device_id,
    }
    data_str = json.dumps(data_dict, separators=(",", ":"))
    sign = _make_sign(token, t_ms, data_str)
    logger.debug("_call_token_api: credential_present=%s deviceId_bound_to_unb=%s", bool(token and m_h5_tk), bool(unb))

    params = {
        "jsv": "2.7.2",
        "appKey": APP_KEY,
        "t": str(t_ms),
        "sign": sign,
        "v": "1.0",
        "type": "originaljson",
        "accountSite": "xianyu",
        "dataType": "json",
        "timeout": "20000",
        "api": "mtop.taobao.idlemessage.pc.login.token",
        "sessionOption": "AutoLoginOnly",
        # SPM 埋点链路（商业版对齐）：模拟从首页侧边栏进入 IM 的真实浏览路径，
        # 服务端据此判断请求来源真实性，降低风控触发概率。
        "spm_cnt": "a21ybx.im.0.0",
        "spm_pre": "a21ybx.home.sidebar.1.4c053da6vYwnmf",
        "log_id": "4c053da6vYwnmf",
    }

    form_data = {
        "data": data_str,
    }

    headers = {
        **H_API,
        "Cookie": cookie_str,
        "Referer": "https://www.goofish.com/",
    }

    try:
        with requests.Session() as session:
            session.trust_env = False
            resp = session.post(TOKEN_API, params=params, data=form_data, headers=headers, timeout=20)
        data = resp.json()
        ret = data.get("ret", [])
        if ret and ret[0].startswith("SUCCESS"):
            access_token = data.get("data", {}).get("accessToken")
            if access_token:
                logger.info(
                    "_call_token_api 成功: accessToken长度=%d",
                    len(access_token),
                )
                return access_token
        # 检查是否是滑块/人机验证（FAIL_SYS_USER_VALIDATE）
        ret_str = " ".join(ret) if isinstance(ret, list) else str(ret)
        if "FAIL_SYS_USER_VALIDATE" in ret_str:
            logger.warning("_call_token_api: 遇到滑块/人机验证")
            return CAPTCHA_NEEDED
        logger.warning("_call_token_api 失败: httpStatus=%s ret=%s", resp.status_code, ret_str[:300])
        return None
    except Exception:
        logger.warning("_call_token_api 异常", exc_info=True)
        return None


def refresh_m_h5_tk(cookie_str: str) -> Tuple[Optional[str], Optional[str]]:
    """刷新 _m_h5_tk 令牌。

    参考 Java XianyuApiUtils.refreshMH5Tk，使用 Session 维持会话，
    执行 3 步刷新流程：
      1. GET 请求获取初始 Cookie（cookie2）
      2. 空 token POST 触发服务端下发新 _m_h5_tk
      3. 真实 token POST 激活令牌

    Args:
        cookie_str: 原始 Cookie 字符串（含已过期的 _m_h5_tk）

    Returns:
        (new_cookie_str, new_m_h5_tk) 或 (None, None) 表示刷新失败
    """
    if not cookie_str:
        logger.warning("refresh_m_h5_tk: cookie_str 为空")
        return None, None

    data_str = json.dumps({"bizScene": "home"}, separators=(",", ":"))

    session = requests.Session()
    session.trust_env = False
    session.headers.update(H_API)

    # 将原始 cookie 注入到 Session，模拟 Java CookieManager 还原 Cookie 到会话
    try:
        for part in cookie_str.split(";"):
            trimmed = part.strip()
            eq_idx = trimmed.find("=")
            if eq_idx > 0:
                name = trimmed[:eq_idx].strip()
                value = trimmed[eq_idx + 1:].strip()
                session.cookies.set(name, value, domain=".goofish.com")
    except Exception:
        logger.warning("refresh_m_h5_tk: 还原 Cookie 到会话失败", exc_info=True)
        return None, None

    try:
        # Step 1: GET 获取初始 Cookie（cookie2）
        logger.info("refresh_m_h5_tk: Step 1 - GET %s", REFRESH_MH5TK_URL)
        get_resp = session.get(REFRESH_MH5TK_URL, timeout=15)
        get_resp.raise_for_status()

        # Step 2: 空 token POST — 触发 _m_h5_tk 下发
        t1 = int(time.time() * 1000)
        empty_sign = _make_sign("", t1, data_str)
        post_body = (
            f"jsv=2.7.2&appKey={APP_KEY}&t={t1}&sign={empty_sign}"
            f"&v=1.0&type=originaljson&dataType=json&timeout=20000"
            f"&api={REFRESH_MH5TK_API}&data={quote(data_str)}"
        )

        logger.info("refresh_m_h5_tk: Step 2 - 空 token POST")
        post_resp = session.post(
            REFRESH_MH5TK_URL,
            data=post_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        post_resp.raise_for_status()

        # 提取新 _m_h5_tk
        new_m_h5_tk = None
        for c in session.cookies:
            if c.name == "_m_h5_tk":
                new_m_h5_tk = c.value
                break

        if not new_m_h5_tk:
            logger.warning("refresh_m_h5_tk: 服务器未下发新 _m_h5_tk 令牌")
            return None, None

        token = new_m_h5_tk.split("_")[0] if "_" in new_m_h5_tk else new_m_h5_tk
        logger.info("refresh_m_h5_tk: 获取到新 _m_h5_tk")

        # Step 3: 真实 token POST — 激活令牌
        t2 = int(time.time() * 1000)
        real_sign = _make_sign(token, t2, data_str)
        post_body2 = (
            f"jsv=2.7.2&appKey={APP_KEY}&t={t2}&sign={real_sign}"
            f"&v=1.0&type=originaljson&dataType=json&timeout=20000"
            f"&api={REFRESH_MH5TK_API}&data={quote(data_str)}"
        )

        logger.info("refresh_m_h5_tk: Step 3 - 真实 token POST")
        post_resp2 = session.post(
            REFRESH_MH5TK_URL,
            data=post_body2,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        post_resp2.raise_for_status()

        # 合并所有 cookie 到新的 cookie 字符串
        # 先以原始 cookie 为基础，再用 Session 中的新值覆盖
        cookie_map = {}
        for part in cookie_str.split(";"):
            trimmed = part.strip()
            eq_idx = trimmed.find("=")
            if eq_idx > 0:
                cookie_map[trimmed[:eq_idx].strip()] = trimmed[eq_idx + 1:].strip()

        for c in session.cookies:
            if c.name and c.value:
                cookie_map[c.name] = c.value

        new_cookie_parts = [f"{k}={v}" for k, v in cookie_map.items()]
        new_cookie_str = "; ".join(new_cookie_parts)

        logger.info("refresh_m_h5_tk: refresh succeeded credentialPresent=true")
        return new_cookie_str, new_m_h5_tk

    except Exception:
        logger.warning("refresh_m_h5_tk: 刷新异常", exc_info=True)
        return None, None


def get_ws_token(cookie_str: str, m_h5_tk: str) -> Optional[str]:
    """获取 WebSocket 连接用的 accessToken。

    Args:
        cookie_str: 闲鱼登录 Cookie 字符串
        m_h5_tk: _m_h5_tk cookie 值（含 token 前缀），来自 xianyu_account_auth.encrypted_token

    Returns:
        accessToken 字符串，失败返回 None
    """
    if not cookie_str:
        logger.error("get_ws_token: cookie_str 为空")
        return None

    # 先试 DB 里的 m_h5_tk
    logger.info("get_ws_token: DB credential_present=%s", bool(m_h5_tk))
    if m_h5_tk:
        result = _call_token_api(cookie_str, m_h5_tk)
        if result == CAPTCHA_NEEDED:
            logger.warning("DB 中的 _m_h5_tk 触发滑块验证，尝试从 Cookie 提取")
        elif result:
            logger.info("获取 WebSocket Token 成功, 长度=%d", len(result))
            return result
        else:
            logger.warning("DB 中的 _m_h5_tk 已过期，尝试从 Cookie 字符串提取")

    # 降级：从 Cookie 字符串中提取 _m_h5_tk
    cookie_m_h5_tk = extract_m_h5_tk_from_cookie(cookie_str)
    logger.info("get_ws_token: Cookie credential_present=%s", bool(cookie_m_h5_tk))
    if cookie_m_h5_tk:
        logger.info("从 Cookie 字符串中提取到 _m_h5_tk")
        result = _call_token_api(cookie_str, cookie_m_h5_tk)
        if result == CAPTCHA_NEEDED:
            logger.error("Cookie 中的 _m_h5_tk 也触发滑块验证，需要更换 Cookie")
        elif result:
            logger.info("使用 Cookie 中的 _m_h5_tk 获取 WS Token 成功, 长度=%d", len(result))
            return result
        else:
            logger.error("Cookie 中的 _m_h5_tk 也已过期")

    logger.error("获取 WebSocket Token 失败：无法获取有效的 _m_h5_tk 签名")
    return None


def get_ws_token_with_refreshed_m_h5_tk(
    cookie_str: str, m_h5_tk: str
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """获取 accessToken，同时返回实际生效的 _m_h5_tk。

    优先从内存缓存读取 accessToken（对标商业版 xy_token_cache），
    缓存未命中时才调用 mtop Token API。如果 DB 中的 m_h5_tk 过期了，依次尝试：
      1. 从 Cookie 字符串中提取 _m_h5_tk
      2. 调用 refresh_m_h5_tk 刷新令牌（3 步流程）

    Returns:
        (accessToken, effective_m_h5_tk, error_type, refreshed_cookie_str)
        - error_type: None (成功), "captcha" (滑块验证), "expired" (已过期)
        - effective_m_h5_tk: 实际生效的 _m_h5_tk（可能是刷新后的）
        - refreshed_cookie_str: 如果刷新了 _m_h5_tk，返回新的 cookie 字符串（含新 token）
        - 调用方应更新 xianyu_account_auth.encrypted_token 和 encrypted_cookie。
    """
    if not cookie_str:
        return None, None, None, None

    # === 优先从缓存读取 accessToken（对标商业版 xy_token_cache）===
    # 商业版 99% 的连接命中缓存跳过 mtop API 调用，实现 3 秒内连接。
    # 缓存按 unb 为键，TTL 4 小时。Cookie 变更时通过 invalidate_cached_token 清除。
    unb = extract_unb_from_cookie(cookie_str) or ""
    if unb:
        cached = get_cached_token(unb)
        if cached:
            cached_at = cached.get("m_h5_tk", "")
            cached_cookie = cached.get("cookie_str", "")
            # 仅当 cookie 和 m_h5_tk 都未变更时才命中缓存，
            # 避免 Cookie 刷新后仍用过期的 token
            if cached_at and cached_cookie and cached_at == m_h5_tk and cached_cookie == cookie_str:
                logger.info(
                    "get_ws_token_with_refreshed: 命中缓存 unb=%s, 跳过 mtop API 调用",
                    unb,
                )
                return cached["access_token"], cached_at, None, None
            else:
                logger.info(
                    "get_ws_token_with_refreshed: 缓存存在但凭据已变更，清除缓存 unb=%s",
                    unb,
                )
                invalidate_cached_token(unb)

    # === 先尝试从 cookie 中提取 _m_h5_tk ===
    # 关键：cookie 中的 _m_h5_tk 会随 WS 连接发送给服务端，服务端会校验其与 accessToken 的关联性
    # 如果使用 DB 中旧的 _m_h5_tk 生成 accessToken，但 WS 连接时 cookie 中却是新的 _m_h5_tk，
    # 服务端发现不匹配会静默丢弃连接。因此必须优先使用 cookie 中的 _m_h5_tk。
    cookie_m_h5_tk = extract_m_h5_tk_from_cookie(cookie_str)
    logger.info(
        "get_ws_token_with_refreshed: cookie_credential=%s db_credential=%s cache_hit=%s",
        bool(cookie_m_h5_tk), bool(m_h5_tk), False,
    )
    if cookie_m_h5_tk:
        result = _call_token_api(cookie_str, cookie_m_h5_tk)
        if result == CAPTCHA_NEEDED:
            logger.warning("Cookie 中的 _m_h5_tk 触发滑块验证")
        elif result:
            logger.info(
                "get_ws_token_with_refreshed: 使用 Cookie 中的 _m_h5_tk 成功, "
                "与 DB 一致=%s",
                "是" if cookie_m_h5_tk == m_h5_tk else "否",
            )
            # 写入缓存，下次连接直接命中
            if unb:
                cache_token(unb, result, cookie_m_h5_tk, cookie_str)
            return result, cookie_m_h5_tk, None, None
        else:
            logger.warning("Cookie 中的 _m_h5_tk 已过期，尝试 DB 中的 _m_h5_tk")
    else:
        logger.warning("Cookie 字符串中未找到 _m_h5_tk")

    # 再试 DB 里的（作为兜底）
    logger.info("get_ws_token_with_refreshed: DB credential_present=%s", bool(m_h5_tk))
    if m_h5_tk:
        result = _call_token_api(cookie_str, m_h5_tk)
        if result == CAPTCHA_NEEDED:
            logger.warning("DB 中的 _m_h5_tk 触发滑块验证，尝试从 Cookie 提取")
        elif result:
            if unb:
                cache_token(unb, result, m_h5_tk, cookie_str)
            return result, m_h5_tk, None, None
        else:
            logger.warning("DB 中的 _m_h5_tk 已过期，尝试从 Cookie 字符串提取")

    # 从 Cookie 提取（第二次尝试，与 DB 都过期的情况）
    if not cookie_m_h5_tk:
        cookie_m_h5_tk = extract_m_h5_tk_from_cookie(cookie_str)
    if cookie_m_h5_tk:
        result = _call_token_api(cookie_str, cookie_m_h5_tk)
        if result == CAPTCHA_NEEDED:
            # 不直接返回，继续尝试 refresh_m_h5_tk 刷新令牌。
            # 刷新后的新 _m_h5_tk（不同 token 前缀）可能绕过风控标记，
            # 因为 FAIL_SYS_USER_VALIDATE 通常与具体 token 绑定。
            logger.warning("Cookie 中的 _m_h5_tk 也触发滑块验证，继续尝试刷新 _m_h5_tk")
        elif result:
            if unb:
                cache_token(unb, result, cookie_m_h5_tk, cookie_str)
            return result, cookie_m_h5_tk, None, None

    # 最后尝试：刷新 _m_h5_tk（参考 Java refreshMH5Tk 三部曲）
    logger.info(
        "get_ws_token_with_refreshed: 尝试刷新 _m_h5_tk cookieCredential=%s",
        bool(cookie_m_h5_tk),
    )
    new_cookie_str, new_m_h5_tk = refresh_m_h5_tk(cookie_str)
    if new_cookie_str and new_m_h5_tk:
        logger.info("get_ws_token_with_refreshed: _m_h5_tk 刷新成功，使用新令牌调用 Token API")
        result = _call_token_api(new_cookie_str, new_m_h5_tk)
        if result == CAPTCHA_NEEDED:
            logger.error("刷新后的 _m_h5_tk 也触发滑块验证，需要更换 Cookie")
            return None, None, "captcha", None
        elif result:
            logger.info("使用刷新后的 _m_h5_tk 获取 WS Token 成功, 长度=%d", len(result))
            # 刷新后的 cookie_str 变了，用新 cookie 缓存
            new_unb = extract_unb_from_cookie(new_cookie_str) or unb
            if new_unb:
                cache_token(new_unb, result, new_m_h5_tk, new_cookie_str)
            return result, new_m_h5_tk, None, new_cookie_str
        else:
            logger.error("刷新后的 _m_h5_tk 调用 Token API 仍然失败")
            return None, None, "expired", None
    else:
        logger.error("_m_h5_tk 刷新失败，Cookie 可能已完全失效")

    return None, None, "expired", None
