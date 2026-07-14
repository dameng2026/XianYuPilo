import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.redis_client import get_redis
from ....core.response import ResultObject
from ....models.entities import (
    DeliveryRecord,
    Notification,
    XianyuAccount,
    XianyuConversation,
    XianyuGoods,
    XianyuTradeOrder,
)
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/navigation", tags=["navigation"])


async def count_rows(db: AsyncSession, model) -> int:
    statement = select(func.count()).select_from(model)
    deleted_column = getattr(model, "deleted", None)
    if deleted_column is not None:
        statement = statement.where(deleted_column == 0)
    # 商品表需进一步排除已退出账号的旧商品，保持前台统计与列表一致
    if model is XianyuGoods:
        valid_account_ids = select(XianyuAccount.id).where(XianyuAccount.deleted == 0)
        statement = statement.where(XianyuGoods.account_id.in_(valid_account_ids))
    result = await db.execute(statement)
    return int(result.scalar() or 0)


@router.get("/overview", response_model=ResultObject[dict])
async def get_navigation_overview(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del current_user
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = await db.execute(
            select(func.count()).select_from(XianyuTradeOrder).where(
                XianyuTradeOrder.deleted == 0,
                func.coalesce(
                    XianyuTradeOrder.create_time,
                    XianyuTradeOrder.created_time,
                ) >= today_start
            )
        )
        pending_orders = await db.execute(
            select(func.count()).select_from(DeliveryRecord).where(
                DeliveryRecord.deleted == 0,
                DeliveryRecord.delivery_status == "pending",
            )
        )
        return ResultObject.success({
            "accountCount": await count_rows(db, XianyuAccount),
            "goodsCount": await count_rows(db, XianyuGoods),
            "todayOrderCount": int(today_orders.scalar() or 0),
            "messageCount": await count_rows(db, XianyuConversation),
            "pendingCount": int(pending_orders.scalar() or 0),
        })
    except Exception:
        logger.error("Navigation overview query failed")
        return ResultObject.internal_error("导航概览暂不可用，请稍后重试")


@router.get("/notifications", response_model=ResultObject[list])
async def get_navigation_notifications(
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del current_user
    try:
        result = await db.execute(
            select(Notification)
            .where(Notification.deleted == 0)
            .order_by(Notification.id.desc())
            .limit(limit)
        )
        notifications = result.scalars().all()
        return ResultObject.success([
            {
                "id": item.id,
                "title": item.title or "系统通知",
                "content": item.content or "",
                "status": item.is_read,
                "type": item.notification_type or "info",
                "createdTime": str(item.created_time) if item.created_time else None,
            }
            for item in notifications
        ])
    except Exception:
        logger.error("Navigation notification query failed")
        return ResultObject.internal_error("通知列表暂不可用，请稍后重试")


@router.get("/system-status", response_model=ResultObject[list])
async def get_navigation_system_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del current_user
    db_status = 0
    db_message = "数据库探测失败"
    try:
        result = await db.execute(text("SELECT 1"))
        db_status = 1 if int(result.scalar() or 0) == 1 else 0
        db_message = "数据库连接探测通过" if db_status == 1 else "数据库探测返回异常结果"
    except Exception:
        logger.warning("Navigation database health probe failed")

    redis_status = 0
    redis_message = "Redis 不可用，当前为单实例内存回退；不满足多实例生产要求"
    try:
        redis_client = await get_redis()
        if redis_client is not None and bool(await redis_client.ping()):
            redis_status = 1
            redis_message = "Redis 连接探测通过"
    except Exception:
        logger.warning("Navigation Redis health probe failed")

    return ResultObject.success([
        {
            "id": "api",
            "nodeName": "API 服务",
            "status": 1,
            "message": "当前 API 请求已成功处理",
        },
        {
            "id": "db",
            "nodeName": "数据库服务",
            "status": db_status,
            "message": db_message,
        },
        {
            "id": "redis",
            "nodeName": "Redis 缓存",
            "status": redis_status,
            "message": redis_message,
        },
        {
            "id": "crawler",
            "nodeName": "采集服务",
            "status": None,
            "message": "当前接口未探测采集服务，状态未知",
        },
    ])
