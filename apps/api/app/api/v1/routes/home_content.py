import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.response import ResultObject
from ....services.commercial_bridge import (
    CommercialBridgeCapabilityUnavailable,
    CommercialBridgeError,
    CommercialBridgeNotConfigured,
    proxy_get_carousel_list,
)
from ....services.local_home_content import load_local_home_content
# 轮播图和公告为公共可读接口，无需登录认证

logger = logging.getLogger(__name__)

router = APIRouter(tags=["home-content"])


def _carousel_unavailable_response(
    message: str,
    *,
    configured: bool,
    reason: str,
) -> JSONResponse:
    result = ResultObject(
        code=503,
        msg=message,
        data={
            "status": "unavailable",
            "reason": reason,
            "commercialBridgeConfigured": configured,
            "retrySafe": False,
        },
    )
    return JSONResponse(
        status_code=503,
        content=result.model_dump(by_alias=True),
    )


@router.get("/carousel/list", response_model=ResultObject[list])
async def get_carousel_list(
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await proxy_get_carousel_list(db)
        return ResultObject.success(payload)
    except CommercialBridgeCapabilityUnavailable:
        return _carousel_unavailable_response(
            "广告轮播已关闭：商业桥尚未证明仅已支付广告可进入展示接口",
            configured=True,
            reason="commercial_bridge_paid_placement_required",
        )
    except CommercialBridgeNotConfigured:
        return _carousel_unavailable_response(
            "广告轮播尚未接通商业服务；未确认付费的内容不会回退展示",
            configured=False,
            reason="commercial_bridge_not_configured",
        )
    except CommercialBridgeError:
        logger.warning("Commercial carousel bridge request failed")
        return ResultObject.failed(
            "广告轮播暂不可用；只有已确认付费且通过展示校验的广告才会显示",
            code=503,
        )


@router.get("/announcement/list", response_model=ResultObject[list])
async def get_announcement_list(
    db: AsyncSession = Depends(get_db),
):
    del db
    try:
        local_content = await asyncio.to_thread(load_local_home_content)
        return ResultObject.success(local_content.get("announcements", []))
    except RuntimeError:
        logger.error("Local announcement content storage is unavailable")
        return ResultObject.failed("公告内容服务暂不可用，请联系管理员检查内容存储", code=503)
