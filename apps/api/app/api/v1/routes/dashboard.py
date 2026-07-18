import logging
from datetime import datetime, timedelta, date
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date, Float, or_
from ....core.database import get_db
from ....core.response import ResultObject
from ....models.entities import (
    XianyuAccount, XianyuGoods, XianyuTradeOrder, XianyuMessage, DeliveryRecord
)
from ....schemas.dashboard import DashboardStatsRespDTO
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard")


@router.post("/stats", response_model=ResultObject[DashboardStatsRespDTO])
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        account_count_result = await db.execute(
            select(func.count()).select_from(XianyuAccount).where(XianyuAccount.deleted == 0)
        )
        account_count = account_count_result.scalar() or 0

        # 仅统计有效账号（deleted=0）的商品，已退出账号的旧商品不在前台展示
        valid_account_ids = select(XianyuAccount.id).where(XianyuAccount.deleted == 0)
        goods_common_filters = (
            XianyuGoods.deleted == 0,
            XianyuGoods.account_id.in_(valid_account_ids),
        )

        item_count_result = await db.execute(
            select(func.count()).select_from(XianyuGoods).where(*goods_common_filters)
        )
        item_count = item_count_result.scalar() or 0

        selling_item_count_result = await db.execute(
            select(func.count()).where(
                XianyuGoods.status == 1,
                *goods_common_filters,
            )
        )
        selling_item_count = selling_item_count_result.scalar() or 0

        off_shelf_item_count_result = await db.execute(
            select(func.count()).where(
                XianyuGoods.status == 0,
                *goods_common_filters,
            )
        )
        off_shelf_item_count = off_shelf_item_count_result.scalar() or 0

        sold_item_count_result = await db.execute(
            select(func.count()).where(
                XianyuGoods.status == 2,
                *goods_common_filters,
            )
        )
        sold_item_count = sold_item_count_result.scalar() or 0

        # 从 delivery_record 获取发货统计
        delivery_stats = await _get_delivery_stats(db)

        return ResultObject.success(DashboardStatsRespDTO(
            account_count=account_count,
            item_count=item_count,
            selling_item_count=selling_item_count,
            off_shelf_item_count=off_shelf_item_count,
            sold_item_count=sold_item_count,
            delivery_success_count=delivery_stats["success"],
            delivery_fail_count=delivery_stats["failed"],
            pending_delivery_count=delivery_stats["pending"]
        ))
    except Exception:
        logger.error("获取首页统计数据失败", exc_info=True)
        return ResultObject.internal_error("统计数据暂时不可用，请稍后重试")


@router.get("/summary")
async def get_dashboard_summary(
    target_date: date | None = Query(default=None, alias="date"),
    days: Annotated[int, Query(ge=1, le=90)] = 1,
    account_id: int | None = Query(default=None, alias="accountId"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取数据面板汇总统计（兼容前端 DataPage.vue）"""
    try:
        selected_date = target_date or date.today()
        period_start = selected_date - timedelta(days=days - 1)
        day_start = datetime.combine(period_start, datetime.min.time())
        day_end = datetime.combine(selected_date, datetime.min.time()) + timedelta(days=1)

        # 平台订单创建时间优先；只有旧数据缺失 create_time 时才回退本地入库时间。
        order_event_time = func.coalesce(
            XianyuTradeOrder.create_time,
            XianyuTradeOrder.created_time,
        )
        order_filters = [
            XianyuTradeOrder.deleted == 0,
            order_event_time >= day_start,
            order_event_time < day_end,
        ]
        if account_id is not None:
            order_filters.append(XianyuTradeOrder.account_id == account_id)
        today_order_result = await db.execute(
            select(func.count()).select_from(XianyuTradeOrder).where(*order_filters)
        )
        today_order_count = today_order_result.scalar() or 0

        # 发货统计 — 从 delivery_record 表统计（不要查 xianyu_trade_order.delivery_status）
        delivery_stats = await _get_delivery_stats(
            db, start=day_start, end=day_end, account_id=account_id
        )

        # AI 自动回复数
        reply_filters = [
            XianyuMessage.is_auto_reply == 1,
            XianyuMessage.deleted == 0,
            XianyuMessage.created_time >= day_start,
            XianyuMessage.created_time < day_end,
        ]
        if account_id is not None:
            reply_filters.append(XianyuMessage.account_id == account_id)
        auto_reply_result = await db.execute(
            select(func.count()).select_from(XianyuMessage).where(*reply_filters)
        )
        auto_reply_count = auto_reply_result.scalar() or 0

        # 消息总数（用于趋势明细对比）
        message_filters = [
            XianyuMessage.deleted == 0,
            XianyuMessage.created_time >= day_start,
            XianyuMessage.created_time < day_end,
        ]
        if account_id is not None:
            message_filters.append(XianyuMessage.account_id == account_id)
        message_count_result = await db.execute(
            select(func.count()).select_from(XianyuMessage).where(*message_filters)
        )
        message_count = message_count_result.scalar() or 0

        # 账号数与商品数（仅当未指定账号时返回全量统计，前端用于指标卡）
        if account_id is None:
            account_count_result = await db.execute(
                select(func.count()).select_from(XianyuAccount).where(XianyuAccount.deleted == 0)
            )
            account_count = account_count_result.scalar() or 0
            valid_account_ids = select(XianyuAccount.id).where(XianyuAccount.deleted == 0)
            goods_common_filters = (
                XianyuGoods.deleted == 0,
                XianyuGoods.account_id.in_(valid_account_ids),
            )
            goods_count_result = await db.execute(
                select(func.count()).select_from(XianyuGoods).where(*goods_common_filters)
            )
            goods_count = goods_count_result.scalar() or 0
            selling_goods_count_result = await db.execute(
                select(func.count()).where(XianyuGoods.status == 1, *goods_common_filters)
            )
            selling_goods_count = selling_goods_count_result.scalar() or 0
            sold_goods_count_result = await db.execute(
                select(func.count()).where(XianyuGoods.status == 2, *goods_common_filters)
            )
            total_sold_count = sold_goods_count_result.scalar() or 0
        else:
            account_count = 1
            goods_filters = (
                XianyuGoods.deleted == 0,
                XianyuGoods.account_id == account_id,
            )
            goods_count_result = await db.execute(
                select(func.count()).select_from(XianyuGoods).where(*goods_filters)
            )
            goods_count = goods_count_result.scalar() or 0
            selling_goods_count_result = await db.execute(
                select(func.count()).where(XianyuGoods.status == 1, *goods_filters)
            )
            selling_goods_count = selling_goods_count_result.scalar() or 0
            sold_goods_count_result = await db.execute(
                select(func.count()).where(XianyuGoods.status == 2, *goods_filters)
            )
            total_sold_count = sold_goods_count_result.scalar() or 0

        # 当日销售额 — total_amount 是字符串类型，逐行求和以避免数据库隐式转换的不确定性
        amount_rows_result = await db.execute(
            select(XianyuTradeOrder.total_amount).where(*order_filters)
        )
        today_sales_amount = 0.0
        for row in amount_rows_result:
            try:
                if row.total_amount:
                    today_sales_amount += float(row.total_amount)
            except (TypeError, ValueError):
                continue
        today_sales_amount = round(today_sales_amount, 2)

        return ResultObject.success({
            "todayOrderCount": today_order_count,
            "orderCount": today_order_count,
            "deliverySuccessCount": delivery_stats["success"],
            "deliveryFailCount": delivery_stats["failed"],
            "pendingDeliveryCount": delivery_stats["pending"],
            "autoReplyCount": auto_reply_count,
            "aiReplyCount": auto_reply_count,
            "messageCount": message_count,
            "accountCount": account_count,
            "goodsCount": goods_count,
            "sellingGoodsCount": selling_goods_count,
            "totalSoldCount": total_sold_count,
            "todaySalesAmount": round(today_sales_amount, 2),
            "periodDays": days,
            "periodStart": period_start.isoformat(),
            "periodEnd": selected_date.isoformat(),
        })
    except Exception:
        logger.error("获取数据面板汇总失败", exc_info=True)
        return ResultObject.internal_error("统计数据暂时不可用，请稍后重试")


@router.get("/sales-trend")
async def get_dashboard_sales_trend(
    days: int = Query(default=7, ge=1, le=90),
    target_date: date | None = Query(default=None, alias="date"),
    account_id: int | None = Query(default=None, alias="accountId"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取近 N 天销售趋势（兼容前端 DataPage.vue）"""
    try:
        end_date = target_date or date.today()
        date_labels = [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        start_date = end_date - timedelta(days=days - 1)
        range_end = end_date + timedelta(days=1)
        delivery_event_time = func.coalesce(
            DeliveryRecord.completed_time,
            DeliveryRecord.delivery_time,
            DeliveryRecord.updated_time,
            DeliveryRecord.created_time,
        )

        # 每日发货成功数 — 从 delivery_record 统计
        success_filters = [
            DeliveryRecord.deleted == 0,
            or_(DeliveryRecord.delivery_status == "success", DeliveryRecord.status == 2),
            cast(delivery_event_time, Date) >= start_date,
            cast(delivery_event_time, Date) < range_end,
        ]
        if account_id is not None:
            success_filters.append(DeliveryRecord.account_id == account_id)
        success_rows_result = await db.execute(
            select(
                cast(delivery_event_time, Date).label("d"),
                func.count().label("c")
            ).where(*success_filters).group_by(cast(delivery_event_time, Date))
        )
        success_map = {str(row.d): row.c for row in success_rows_result}

        # 每日发货失败数 — 从 delivery_record 统计
        fail_filters = [
            DeliveryRecord.deleted == 0,
            or_(DeliveryRecord.delivery_status == "failed", DeliveryRecord.status.in_([3, 6, 7])),
            cast(delivery_event_time, Date) >= start_date,
            cast(delivery_event_time, Date) < range_end,
        ]
        if account_id is not None:
            fail_filters.append(DeliveryRecord.account_id == account_id)
        fail_rows_result = await db.execute(
            select(
                cast(delivery_event_time, Date).label("d"),
                func.count().label("c")
            ).where(*fail_filters).group_by(cast(delivery_event_time, Date))
        )
        fail_map = {str(row.d): row.c for row in fail_rows_result}

        # 每日 AI 回复数
        reply_filters = [
            XianyuMessage.is_auto_reply == 1,
            XianyuMessage.deleted == 0,
            cast(XianyuMessage.created_time, Date) >= start_date,
            cast(XianyuMessage.created_time, Date) < range_end,
        ]
        if account_id is not None:
            reply_filters.append(XianyuMessage.account_id == account_id)
        reply_rows_result = await db.execute(
            select(
                cast(XianyuMessage.created_time, Date).label("d"),
                func.count().label("c")
            ).where(*reply_filters).group_by(cast(XianyuMessage.created_time, Date))
        )
        reply_map = {str(row.d): row.c for row in reply_rows_result}

        # 每日订单数
        order_event_time = func.coalesce(
            XianyuTradeOrder.create_time,
            XianyuTradeOrder.created_time,
        )
        order_filters = [
            XianyuTradeOrder.deleted == 0,
            cast(order_event_time, Date) >= start_date,
            cast(order_event_time, Date) < range_end,
        ]
        if account_id is not None:
            order_filters.append(XianyuTradeOrder.account_id == account_id)
        order_rows_result = await db.execute(
            select(
                cast(order_event_time, Date).label("d"),
                func.count().label("c")
            ).where(*order_filters).group_by(cast(order_event_time, Date))
        )
        order_map = {str(row.d): row.c for row in order_rows_result}

        # 每日消息总数
        msg_filters = [
            XianyuMessage.deleted == 0,
            cast(XianyuMessage.created_time, Date) >= start_date,
            cast(XianyuMessage.created_time, Date) < range_end,
        ]
        if account_id is not None:
            msg_filters.append(XianyuMessage.account_id == account_id)
        msg_rows_result = await db.execute(
            select(
                cast(XianyuMessage.created_time, Date).label("d"),
                func.count().label("c")
            ).where(*msg_filters).group_by(cast(XianyuMessage.created_time, Date))
        )
        msg_map = {str(row.d): row.c for row in msg_rows_result}

        return ResultObject.success({
            "dates": date_labels,
            "orderCount": [order_map.get(d, 0) for d in date_labels],
            "messageCount": [msg_map.get(d, 0) for d in date_labels],
            "deliveryCount": [(success_map.get(d, 0) + fail_map.get(d, 0)) for d in date_labels],
            "deliverySuccess": [success_map.get(d, 0) for d in date_labels],
            "deliveryFail": [fail_map.get(d, 0) for d in date_labels],
            "aiReplyCount": [reply_map.get(d, 0) for d in date_labels],
            "aiReplies": [reply_map.get(d, 0) for d in date_labels],
        })
    except Exception:
        logger.error("获取销售趋势失败", exc_info=True)
        return ResultObject.internal_error("趋势数据暂时不可用，请稍后重试")


async def _get_delivery_stats(
    db: AsyncSession,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    account_id: int | None = None,
) -> dict:
    """从 delivery_record 表统计发货成功/失败/待处理数量（按租户隔离）"""
    try:
        # 发货成功
        def status_query(status: str):
            status_conditions = {
                "success": or_(DeliveryRecord.delivery_status == "success", DeliveryRecord.status == 2),
                "failed": or_(DeliveryRecord.delivery_status == "failed", DeliveryRecord.status.in_([3, 6, 7])),
                "pending": or_(DeliveryRecord.delivery_status == "pending", DeliveryRecord.status.in_([0, 1, 5])),
            }
            conditions = [
                DeliveryRecord.deleted == 0,
                status_conditions[status],
            ]
            event_time = DeliveryRecord.created_time
            if status in {"success", "failed"}:
                event_time = func.coalesce(
                    DeliveryRecord.completed_time,
                    DeliveryRecord.delivery_time,
                    DeliveryRecord.updated_time,
                    DeliveryRecord.created_time,
                )
            if start is not None:
                conditions.append(event_time >= start)
            if end is not None:
                conditions.append(event_time < end)
            if account_id is not None:
                conditions.append(DeliveryRecord.account_id == account_id)
            return select(func.count()).select_from(DeliveryRecord).where(*conditions)

        success_result = await db.execute(status_query("success"))
        success_count = success_result.scalar() or 0

        # 发货失败
        fail_result = await db.execute(status_query("failed"))
        fail_count = fail_result.scalar() or 0

        # 待发货
        pending_result = await db.execute(status_query("pending"))
        pending_count = pending_result.scalar() or 0

        return {"success": success_count, "failed": fail_count, "pending": pending_count}
    except Exception:
        logger.warning("查询 delivery_record 失败", exc_info=True)
        raise