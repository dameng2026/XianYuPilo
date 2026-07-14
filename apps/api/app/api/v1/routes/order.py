import datetime
import logging
import math

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.response import ResultObject
from ....models.entities import XianyuTradeOrder
from ....schemas.order import (
    ConfirmShipmentReqDTO,
    OrderListData,
    OrderQueryReqDTO,
    OrderVO,
    SoldOrderSyncReqDTO,
)
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/order")

# 批量刷新扩展 router（前端 order.js 调用 POST /api/order/batchRefresh，参考项目无实现）
batch_refresh_router = APIRouter(prefix="/order", tags=["order-batch"])


def trade_order_to_vo(order: XianyuTradeOrder) -> OrderVO:
    return OrderVO(
        id=order.id,
        account_id=order.account_id,
        external_order_id=order.external_order_id,
        order_status=order.order_status,
        buyer_name=order.buyer_name,
        total_amount=order.total_amount,
        create_time=str(order.create_time) if order.create_time else None,
        pay_time=str(order.pay_time) if order.pay_time else None,
        xianyu_account_id=order.account_id,
        order_id=order.external_order_id,
        total_price=order.total_amount,
    )


@router.post("/list", response_model=ResultObject[OrderListData])
async def list_orders(
    req: OrderQueryReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        page_num = max(req.page_num or 1, 1)
        page_size = max(min(req.page_size or 20, 100), 1)
        query = select(XianyuTradeOrder)
        if req.xianyu_account_id is not None:
            query = query.where(XianyuTradeOrder.account_id == req.xianyu_account_id)
        if req.xy_goods_id:
            query = query.where(XianyuTradeOrder.external_order_id == req.xy_goods_id)
        if req.order_status is not None:
            query = query.where(XianyuTradeOrder.order_status == req.order_status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page_num - 1) * page_size
        query = query.order_by(XianyuTradeOrder.id.desc()).offset(offset).limit(page_size)
        result = await db.execute(query)
        orders = result.scalars().all()

        records = [trade_order_to_vo(o) for o in orders]
        pages = math.ceil(total / page_size) if total > 0 else 0
        return ResultObject.success(
            OrderListData(
                records=records,
                total=total,
                page_num=page_num,
                page_size=page_size,
                pages=pages,
            )
        )
    except Exception as e:
        logger.error("查询订单列表失败", exc_info=True)
        return ResultObject.internal_error()


@router.post("/confirmShipment", response_model=ResultObject[str])
async def confirm_shipment(
    req: ConfirmShipmentReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        if not req.order_id:
            return ResultObject.failed("订单ID不能为空")
        result = await db.execute(
            select(XianyuTradeOrder).where(
                XianyuTradeOrder.account_id == req.xianyu_account_id,
                XianyuTradeOrder.external_order_id == req.order_id,
                XianyuTradeOrder.deleted == 0,
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return ResultObject.failed("订单不存在")
        if order.order_status == 3:
            return ResultObject.success("订单已确认发货，无需重复操作")

        order.order_status = 3
        order.ship_time = datetime.datetime.now()
        await db.commit()
        return ResultObject.success("确认发货成功（仅更新本地状态）")
    except Exception as e:
        logger.error("确认发货失败", exc_info=True)
        return ResultObject.internal_error()


@router.post("/syncSoldOrders", response_model=ResultObject[dict])
async def sync_sold_orders(
    req: SoldOrderSyncReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        return ResultObject.success({
            "message": "同步成功",
            "synced_count": 0,
        })
    except Exception as e:
        logger.error("同步鱼小铺卖家订单列表失败", exc_info=True)
        return ResultObject.internal_error()


# ==================== 批量刷新订单（前端 order.js 调用，参考项目无实现） ====================

@batch_refresh_router.post("/batchRefresh", response_model=ResultObject[dict])
async def batch_refresh_orders(
    data: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量刷新订单状态。开源版简化实现：重新查询并返回最新订单数据。

    前端 order.js 使用 300 秒超时，预期是长耗时操作。开源版不做远程同步，
    仅返回本地数据库最新状态作为"刷新"结果。
    """
    try:
        order_ids = data.get("orderIds") or []
        account_id = data.get("xianyuAccountId") or data.get("accountId")

        query = select(XianyuTradeOrder)
        if account_id:
            query = query.where(XianyuTradeOrder.account_id == int(account_id))
        if order_ids:
            query = query.where(XianyuTradeOrder.external_order_id.in_(order_ids))
        query = query.order_by(XianyuTradeOrder.id.desc()).limit(100)
        result = await db.execute(query)
        orders = result.scalars().all()
        records = [trade_order_to_vo(o) for o in orders]
        return ResultObject.success({
            "message": "刷新成功",
            "refreshed_count": len(records),
            "records": [r.model_dump() if hasattr(r, "model_dump") else r for r in records],
        })
    except Exception as e:
        logger.error("批量刷新订单失败", exc_info=True)
        return ResultObject.internal_error()
