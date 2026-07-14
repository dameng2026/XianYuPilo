import logging
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from ....core.config import settings
from ....core.response import ResultObject
from ..deps import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal")


def verify_internal_token(x_internal_token: Optional[str] = Header(None)) -> None:
    """内部接口保护。Phase 1 起 fail-closed：令牌为空或不匹配均拒绝。"""
    if not x_internal_token:
        raise HTTPException(status_code=401, detail="暂未登录或token已经过期")

    expected = (getattr(settings, "internal_api_token", "") or "").strip()
    if not expected:
        logger.error("INTERNAL_API_TOKEN 未配置，拒绝内部接口调用")
        raise HTTPException(status_code=503, detail="INTERNAL_API_TOKEN is not configured")
    if not hmac.compare_digest(str(x_internal_token), expected):
        raise HTTPException(status_code=403, detail="invalid internal token")


async def verify_internal_or_current_user(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    x_internal_token: Optional[str] = Header(None),
) -> None:
    if current_user is not None:
        return
    verify_internal_token(x_internal_token)


@router.get("/health")
async def internal_health(_: None = Depends(verify_internal_token)):
    return ResultObject.success({
        "service": "xianyu-assistant-api",
        "status": "ok",
        "boundary": "python-execution-only",
    })
