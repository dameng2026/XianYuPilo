"""
滑块验证处理路由
================
提供前端调用的滑块验证接口：
- POST /captcha/detect   检测 API 响应是否需要滑块验证
- POST /captcha/instructions   获取操作指引
- POST /captcha/auto-solve   调用 Playwright 自动求解
- POST /captcha/handle   综合处理：检测 + 通知 + 自动求解
"""
import logging
from fastapi import APIRouter, Depends

from ....core.response import ResultObject
from ..deps import get_current_user
from ....services.captcha_solver import (
    detect_captcha_from_response,
    build_captcha_instructions,
    try_auto_solve,
    handle_captcha_for_account,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/captcha", tags=["captcha"])


@router.post("/detect", response_model=ResultObject[dict])
async def detect_captcha(
    data: dict = {},
    current_user: dict = Depends(get_current_user),
):
    """检测 API 响应是否包含滑块验证需求。

    请求体: {"response": <dict 或 str>, "accountId": 1}
    """
    try:
        response = data.get("response")
        account_id = data.get("accountId")

        result = detect_captcha_from_response(response)
        return ResultObject.success({
            "detected": result.detected,
            "captchaUrl": result.captcha_url,
            "reason": result.reason,
            "accountId": account_id,
        })
    except Exception as exc:
        logger.error("滑块检测失败 errorType=%s", type(exc).__name__)
        return ResultObject.internal_error()


@router.post("/instructions", response_model=ResultObject[dict])
async def get_instructions(
    data: dict = {},
    current_user: dict = Depends(get_current_user),
):
    """获取滑块验证操作指引。

    请求体: {"accountId": 1, "captchaUrl": "https://...", "accountName": "xxx"}
    """
    try:
        account_id = int(data.get("accountId") or 0)
        captcha_url = data.get("captchaUrl")
        account_name = data.get("accountName")

        instructions = build_captcha_instructions(account_id, captcha_url, account_name)
        return ResultObject.success({
            "accountId": instructions.account_id,
            "captchaUrl": instructions.captcha_url,
            "title": instructions.title,
            "steps": instructions.steps,
            "message": instructions.message,
            "autoSolveAvailable": instructions.auto_solve_available,
            "manualFallbackUrl": instructions.manual_fallback_url,
        })
    except Exception as exc:
        logger.error("获取滑块指引失败 errorType=%s", type(exc).__name__)
        return ResultObject.internal_error()


@router.post("/auto-solve", response_model=ResultObject[dict])
async def auto_solve_captcha(
    data: dict = {},
    current_user: dict = Depends(get_current_user),
):
    """调用 Playwright 自动求解滑块。

    请求体: {
        "accountId": 1,
        "targetUrl": "https://www.goofish.com/",  # 可选
        "headless": false,  # 可选，默认 false
        "maxRetries": 3    # 可选
    }
    """
    try:
        account_id = int(data.get("accountId") or 0)
        if not account_id:
            return ResultObject.validate_failed("accountId 不能为空")

        target_url = data.get("targetUrl")
        headless = bool(data.get("headless", False))
        max_retries = int(data.get("maxRetries") or 3)

        result = await try_auto_solve(
            account_id=account_id,
            target_url=target_url,
            headless=headless,
            max_retries=max_retries,
        )
        return ResultObject.success(result)
    except Exception as exc:
        logger.error("自动求解滑块失败 errorType=%s", type(exc).__name__)
        return ResultObject.internal_error()


@router.post("/handle", response_model=ResultObject[dict])
async def handle_captcha(
    data: dict = {},
    current_user: dict = Depends(get_current_user),
):
    """综合处理滑块验证场景：检测 + 通知 + 自动求解。

    请求体: {
        "accountId": 1,
        "tenantId": 1,
        "response": <dict 或 str>,    # 可选，用于检测
        "autoSolve": true              # 是否自动求解
    }
    """
    try:
        account_id = int(data.get("accountId") or 0)
        response = data.get("response")
        auto_solve = bool(data.get("autoSolve", False))
        if not account_id:
            return ResultObject.validate_failed("accountId 不能为空")
        result = await handle_captcha_for_account(
            account_id=account_id,
            response=response,
            auto_solve=auto_solve,
        )
        return ResultObject.success(result)
    except Exception as exc:
        logger.error("综合处理滑块失败 errorType=%s", type(exc).__name__)
        return ResultObject.internal_error()
