"""
WebSocket 控制 API（前端 websocket.js 调用）
=============================================
参考项目状态：
- refreshCookie / updateToken / refreshToken：参考项目 Java 网关仅作健康检查占位
- checkLogin：参考项目 Java + XianyuAccountAuthStatusService.check()
- updateCookie：参考项目 Java + XianyuAccountService.updateCookie()（开源版 account.py 已有等价实现）
- passwordLogin / clearCaptchaWait / retryAutoCaptcha / confirmManualVerification /
  pendingManualVerification：参考项目仅 .bak 桩，从未真正实现

开源版策略：复用 account.py 已有 update_account_cookie；其余实现为功能桩或健康检查。
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.response import ResultObject
from ....models.entities import XianyuAccount, XianyuAccountAuth
from ....services.ws_client import ws_manager
from ..deps import get_current_user
from .account import update_account_cookie as _account_update_cookie

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/websocket", tags=["websocket-control"])


def _parse_account_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _require_account_credential(
    db: AsyncSession,
    account_id: int,
    *,
    require_cookie: bool,
    require_token: bool = False,
) -> None:
    """Distinguish missing credentials from a storage outage."""

    try:
        result = await db.execute(
            select(
                XianyuAccount.id,
                XianyuAccountAuth.id,
                XianyuAccountAuth.encrypted_cookie,
                XianyuAccountAuth.encrypted_token,
            )
            .outerjoin(
                XianyuAccountAuth,
                and_(
                    XianyuAccountAuth.account_id == XianyuAccount.id,
                    XianyuAccountAuth.deleted == 0,
                ),
            )
            .where(
                XianyuAccount.id == account_id,
                XianyuAccount.deleted == 0,
            )
            .limit(1)
        )
        row = result.first()
    except Exception as exc:
        logger.error(
            "Account credential preflight failed accountId=%d errorType=%s",
            account_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="账号凭据存储暂不可用，请稍后重试。",
        ) from exc

    if row is None:
        raise HTTPException(status_code=404, detail="账号不存在。")
    if row[1] is None:
        raise HTTPException(
            status_code=422,
            detail="账号尚未建立登录凭据，请先扫码登录。",
        )
    if require_cookie and not str(row[2] or "").strip():
        raise HTTPException(
            status_code=422,
            detail="账号缺少 Cookie，请先重新扫码登录或更新 Cookie。",
        )
    if require_token and not str(row[3] or "").strip():
        raise HTTPException(
            status_code=422,
            detail="账号缺少 WebSocket Token 凭据，请重新扫码登录。",
        )


@router.post("/refreshCookie")
async def ws_refresh_cookie(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Reload the account's stored credentials and restart its WS client."""
    account_id = _parse_account_id(data.get("xianyuAccountId") or data.get("accountId"))
    if account_id is None or account_id <= 0:
        raise HTTPException(status_code=422, detail="accountId 必须为正整数。")
    await _require_account_credential(
        db,
        account_id,
        require_cookie=True,
        require_token=True,
    )
    try:
        restarted = await ws_manager.restart_account(account_id)
    except Exception as exc:
        logger.error(
            "refreshCookie failed accountId=%d errorType=%s",
            account_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Cookie 重载服务暂不可用，请稍后重试。",
        ) from exc
    if not restarted:
        raise HTTPException(
            status_code=503,
            detail="未执行 Cookie 重载：账号不存在或凭据不完整，请先更新 Cookie 后重试。",
        )
    client = ws_manager.get_client(account_id)
    connected = bool(client and getattr(client, "is_connected", False))
    return ResultObject.success({
        "credentialReloaded": True,
        "connected": connected,
        "connectionConfirmed": connected,
        "status": "connected" if connected else "reconnecting",
        "message": "已加载已保存的 Cookie 并触发 WebSocket 重连。",
    })


@router.post("/checkLogin")
async def ws_check_login(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Check the account's login state against the platform."""
    account_id = _parse_account_id(data.get("xianyuAccountId") or data.get("accountId"))
    if account_id is None or account_id <= 0:
        raise HTTPException(status_code=422, detail="accountId 必须为正数。")
    del db, current_user
    from ....services.cookie_token_refresher import check_cookie_login

    check = await check_cookie_login(account_id)
    if not check.confirmed:
        if check.code == "ACCOUNT_NOT_FOUND":
            raise HTTPException(status_code=404, detail=check.message)
        if check.code == "CREDENTIAL_MISSING":
            raise HTTPException(status_code=422, detail=check.message)
        raise HTTPException(status_code=503, detail=check.message)

    client = ws_manager.get_client(account_id)
    ws_online = bool(client and getattr(client, "is_connected", False))
    status = {
        "loggedIn": check.authenticated,
        "authenticated": check.authenticated,
        "confirmed": True,
        "message": check.message,
        "code": check.code,
        "cookieStatus": 1 if check.authenticated else 0,
        "wsOnline": ws_online,
        "checkedAt": check.checked_at.isoformat(sep=" ", timespec="seconds") if check.checked_at else None,
    }
    return ResultObject.success({**status, "status": status})


@router.post("/updateCookie")
async def ws_update_cookie(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新 Cookie。复用 account.py 的 update_account_cookie 实现。"""
    account_id = _parse_account_id(data.get("xianyuAccountId") or data.get("accountId"))
    cookie = data.get("cookie") or data.get("cookies")
    if account_id is None or account_id <= 0:
        raise HTTPException(status_code=422, detail="accountId 必须为正整数。")
    if not cookie:
        raise HTTPException(status_code=422, detail="cookie 不能为空。")
    try:
        await _require_account_credential(db, account_id, require_cookie=False)
        # account.update_account_cookie 接收 data: dict，统一 {"accountId":..., "cookie":...}
        result = await _account_update_cookie(
            data={"accountId": account_id, "cookie": cookie},
            db=db,
            current_user=current_user,
        )
        if int(getattr(result, "code", 500)) != 200:
            raise HTTPException(
                status_code=503,
                detail="Cookie 更新未完成，请稍后重试。",
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "updateCookie failed accountId=%d errorType=%s",
            account_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Cookie 更新服务暂不可用，请稍后重试。",
        ) from exc


@router.post("/updateToken")
async def ws_update_token(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retired: this compatibility endpoint never updated a platform token."""
    del data, db, current_user
    raise HTTPException(
        status_code=410,
        detail="旧 Token 更新接口已移除；请更新账号 Cookie 后调用 POST /api/websocket/start。",
    )


@router.post("/refreshToken")
async def ws_refresh_token(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retired: this compatibility endpoint never refreshed a platform token."""
    del data, db, current_user
    raise HTTPException(
        status_code=410,
        detail="旧 Token 刷新接口已移除；请更新账号 Cookie 后调用 POST /api/websocket/start。",
    )


@router.post("/passwordLogin")
async def ws_password_login(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retired: password login has no credential consumer in this build."""
    del data, db, current_user
    raise HTTPException(
        status_code=410,
        detail="密码登录接口已移除；请使用 POST /api/qrlogin/generate 扫码登录。",
    )


@router.post("/clearCaptchaWait")
async def ws_clear_captcha_wait(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retired: no persistent captcha-wait state exists to clear."""
    del data, db, current_user
    raise HTTPException(
        status_code=410,
        detail="验证码等待占位接口已移除；当前版本没有可清理的持久化等待状态。",
    )


@router.post("/retryAutoCaptcha")
async def ws_retry_auto_captcha(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重试自动验证码求解。"""
    account_id = _parse_account_id(data.get("xianyuAccountId") or data.get("accountId"))
    if account_id is None or account_id <= 0:
        raise HTTPException(status_code=422, detail="accountId 必须为正整数。")
    try:
        await _require_account_credential(db, account_id, require_cookie=True)
        from app.services.captcha_solver import handle_captcha_for_account
        result = await handle_captcha_for_account(
            account_id=account_id,
            response=None,
            auto_solve=True,
        )
        if bool(result.get("recovered")):
            return ResultObject.success(result)

        auto_result = result.get("autoSolveResult") or {}
        if auto_result.get("solved") and auto_result.get("cookieVerified") is False:
            raise HTTPException(
                status_code=422,
                detail="Cookie Session 已过期，请重新扫码登录后再试。",
            )
        raise HTTPException(
            status_code=503,
            detail="自动验证码处理未完成，请稍后重试或手动更新 Cookie。",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "retryAutoCaptcha failed accountId=%d errorType=%s",
            account_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="自动验证码服务暂不可用，请稍后重试。",
        ) from exc


@router.post("/confirmManualVerification")
async def ws_confirm_manual_verification(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retired: no verification event exists that this endpoint can confirm."""
    del data, db, current_user
    raise HTTPException(
        status_code=410,
        detail="人工验证确认占位接口已移除；请更新 Cookie 后调用 POST /api/websocket/checkLogin。",
    )


@router.get("/pendingManualVerification")
async def ws_pending_manual_verification(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retired: no authoritative verification-event model exists."""
    del db, current_user
    raise HTTPException(
        status_code=410,
        detail="待人工验证列表已移除；请以账号登录实时校验结果为准。",
    )
