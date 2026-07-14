import datetime
import json
from collections import defaultdict
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.response import ResultObject
from ....schemas.order import ManualDeliveryReqDTO
from ....services.manual_delivery import (
    ManualDeliveryCommand,
    ManualDeliveryCoordinator,
    ManualDeliveryError,
    SqlManualDeliveryAttemptStore,
    XianyuManualDeliveryGateway,
)
from ....models.entities import (
    DeliveryRecord,
    DeliveryRule,
    GoodsOffShelfAttempt,
    ManualDeliveryAttempt,
    RemoteGoodsDeleteAttempt,
    XianyuAccount,
    XianyuGoods,
    XianyuGoodsSyncTask,
    XianyuTradeOrder,
    XianyuTradeOrderItem,
)
from ..deps import get_current_user

router = APIRouter(tags=["commerceCompat"])
CONFIG_TIMINGS = ("payDelivery", "confirmDelivery", "reviewDelivery")


def get_manual_delivery_coordinator(
    db: AsyncSession = Depends(get_db),
) -> ManualDeliveryCoordinator:
    return ManualDeliveryCoordinator(
        store=SqlManualDeliveryAttemptStore(db),
        gateway=XianyuManualDeliveryGateway(),
    )


def _format_datetime(value: Optional[datetime.datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat(sep=" ", timespec="seconds")


def _db_goods_status_to_fe(value: Optional[int]) -> int:
    mapping = {1: 0, 0: 1, 2: 2, 3: 3}
    return mapping.get(value, 1 if value is None else value)


def _fe_goods_status_to_db(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    mapping = {0: 1, 1: 0, 2: 2, 3: 3}
    return mapping.get(int(value), int(value))


def _json_loads(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _delivery_type_from_mode(mode: Any) -> Optional[int]:
    normalized = str(mode or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"kami", "card"}:
        return 0
    if normalized == "text":
        return 1
    return 2


def _delivery_type_from_rule(rule: DeliveryRule | None) -> Optional[int]:
    if rule is None or not rule.delivery_mode:
        return None
    return _delivery_type_from_mode(rule.delivery_mode)


def _config_has_timings(config: dict[str, Any]) -> bool:
    for timing in CONFIG_TIMINGS:
        timing_config = config.get(timing)
        if isinstance(timing_config, dict) and timing_config:
            return True
    return False


def _delivery_meta_from_config(config: dict[str, Any]) -> dict[str, Any]:
    enabled = False
    first_type: Optional[int] = None
    enabled_type: Optional[int] = None

    for timing in CONFIG_TIMINGS:
        timing_config = config.get(timing)
        if not isinstance(timing_config, dict) or not timing_config:
            continue

        timing_type = _delivery_type_from_mode(timing_config.get("mode"))
        if first_type is None and timing_type is not None:
            first_type = timing_type

        raw_enabled = timing_config.get("enabled", 1)
        is_enabled = str(raw_enabled).strip().lower() not in {"0", "false", "off", "no"}
        if is_enabled:
            enabled = True
            if enabled_type is None and timing_type is not None:
                enabled_type = timing_type

    return {
        "on": enabled,
        "type": enabled_type if enabled_type is not None else first_type,
        "configured": _config_has_timings(config),
    }


def _delivery_meta_from_rule(rule: DeliveryRule | None) -> dict[str, Any]:
    return {
        "on": bool(rule and rule.status == 1),
        "type": _delivery_type_from_rule(rule),
        "configured": rule is not None,
    }


def _goods_images(goods: XianyuGoods) -> list[str]:
    images: list[str] = []
    raw = goods.image_urls
    if isinstance(raw, list):
        images.extend(str(item) for item in raw if item)
    for candidate in [goods.cover_pic, goods.image_url]:
        if candidate and candidate not in images:
            images.append(candidate)
    return images


def _goods_to_record(
    goods: XianyuGoods,
    delivery_meta: Optional[dict[str, Any]] = None,
    remote_delete_meta: Optional[dict[str, Any]] = None,
    off_shelf_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    images = _goods_images(goods)
    cover = goods.cover_pic or goods.image_url or (images[0] if images else None)
    auto_reply_enabled = goods.auto_reply_enabled if goods.auto_reply_enabled is not None else 0
    delivery_meta = delivery_meta or {}
    return {
        "id": goods.id,
        "accountId": goods.account_id,
        "xianyuAccountId": goods.account_id,
        "externalGoodsId": goods.external_goods_id,
        "xyGoodsId": goods.external_goods_id,
        "goodsId": goods.goods_id,
        "title": goods.title or "",
        "description": goods.description or "",
        "price": goods.price,
        "soldPrice": goods.sold_price or goods.price,
        "stock": goods.stock,
        "quantity": goods.quantity if goods.quantity is not None else goods.stock,
        "imageUrl": goods.image_url or cover,
        "mainImageUrl": goods.image_url or cover,
        "coverPic": cover,
        "imageUrls": images,
        "detailUrl": goods.detail_url,
        "detailInfo": goods.detail_info,
        "category": goods.category,
        "status": _db_goods_status_to_fe(goods.status),
        "skuCount": 1,
        "exposureCount": goods.exposure_count or 0,
        "viewCount": goods.view_count or 0,
        "wantCount": goods.want_count or 0,
        "autoReplyEnabled": auto_reply_enabled,
        "auto_reply_enabled": auto_reply_enabled,
        "xianyuAutoReplyOn": 1 if auto_reply_enabled == 1 else 0,
        "xianyuAutoDeliveryOn": 1 if delivery_meta.get("on") else 0,
        "autoDeliveryType": delivery_meta.get("type"),
        "remoteDeleteAttempt": remote_delete_meta,
        "offShelfAttempt": off_shelf_meta,
        "createdTime": _format_datetime(goods.created_time),
        "updatedTime": _format_datetime(goods.updated_time),
        "created_time": _format_datetime(goods.created_time),
        "updated_time": _format_datetime(goods.updated_time),
    }


async def _load_goods_delivery_meta(
    db: AsyncSession,
    goods_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not goods_ids:
        return {}

    legacy_result = await db.execute(
        select(DeliveryRule)
        .where(
            DeliveryRule.deleted == 0,
            DeliveryRule.goods_id.in_(goods_ids),
        )
        .order_by(DeliveryRule.status.desc(), DeliveryRule.updated_time.desc(), DeliveryRule.id.desc())
    )
    legacy_rules: dict[int, DeliveryRule] = {}
    for rule in legacy_result.scalars():
        if rule.goods_id not in legacy_rules:
            legacy_rules[rule.goods_id] = rule

    placeholders = ", ".join(f":goods_id_{index}" for index, _ in enumerate(goods_ids))
    params = {f"goods_id_{index}": goods_id for index, goods_id in enumerate(goods_ids)}
    config_rows = (
        await db.execute(
            text(
                f"""
                SELECT goods_id, config_json
                FROM delivery_goods_config
                WHERE deleted = 0
                  AND goods_id IN ({placeholders})
                """
            ),
            params,
        )
    ).mappings().all()
    config_map = {
        int(row["goods_id"]): _json_loads(row.get("config_json"), {})
        for row in config_rows
    }

    delivery_meta: dict[int, dict[str, Any]] = {}
    for goods_id in goods_ids:
        config = config_map.get(goods_id)
        if isinstance(config, dict) and _config_has_timings(config):
            delivery_meta[goods_id] = _delivery_meta_from_config(config)
            continue

        legacy_rule = legacy_rules.get(goods_id)
        if legacy_rule is not None:
            delivery_meta[goods_id] = _delivery_meta_from_rule(legacy_rule)

    return delivery_meta


async def _load_goods_remote_delete_meta(
    db: AsyncSession,
    goods_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not goods_ids:
        return {}
    attempts = (
        await db.execute(
            select(RemoteGoodsDeleteAttempt).where(
                RemoteGoodsDeleteAttempt.goods_id.in_(goods_ids)
            )
        )
    ).scalars().all()
    result: dict[int, dict[str, Any]] = {}
    messages = {
        "pending": "删除请求已登记，等待执行",
        "in_progress": "平台删除正在执行，请勿重复操作",
        "remote_confirmed": "平台删除已确认，本地软删除尚未完成",
        "failed": "平台明确拒绝删除，排除问题后可手动重试",
        "unknown": "平台删除结果未知，请先在闲鱼 App 核对，禁止自动重试",
        "confirmed": "平台删除与本地软删除均已完成",
    }
    for attempt in attempts:
        state = str(attempt.state or "pending")
        result[int(attempt.goods_id)] = {
            "attemptId": int(attempt.id),
            "status": state,
            "message": messages.get(state, "删除状态未知，请刷新后重试"),
            "retrySafe": bool(attempt.retry_safe),
            "recovery": {
                "remote_confirmed": "retry_local_finalize",
                "failed": "resolve_and_retry",
                "unknown": "verify_in_xianyu_app",
            }.get(state),
            "errorCode": attempt.last_error_code,
            "remoteConfirmed": attempt.remote_confirmed_at is not None
            or state in {"remote_confirmed", "confirmed"},
            "localDeleted": attempt.local_deleted_at is not None or state == "confirmed",
            "updatedTime": _format_datetime(attempt.updated_time),
        }
    return result


async def _load_goods_off_shelf_meta(
    db: AsyncSession,
    goods_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Load the newest persisted attempt per goods in one bounded query."""
    if not goods_ids:
        return {}
    latest_attempt_ids = (
        select(func.max(GoodsOffShelfAttempt.id).label("attempt_id"))
        .where(GoodsOffShelfAttempt.goods_id.in_(goods_ids))
        .group_by(GoodsOffShelfAttempt.goods_id)
        .subquery()
    )
    attempts = (
        await db.execute(
            select(GoodsOffShelfAttempt)
            .join(
                latest_attempt_ids,
                GoodsOffShelfAttempt.id == latest_attempt_ids.c.attempt_id,
            )
        )
    ).scalars().all()
    result: dict[int, dict[str, Any]] = {}
    messages = {
        "pending": "下架请求已登记，等待执行",
        "in_progress": "平台下架正在执行，请勿重复操作",
        "remote_confirmed": "平台下架已确认，本地状态尚未完成",
        "confirmed": "平台与本地下架状态均已确认",
        "failed": "平台明确未执行下架",
        "unknown": "平台下架结果未知，请先在闲鱼 App 核对，禁止自动重试",
    }
    for attempt in attempts:
        goods_id = int(attempt.goods_id)
        state = str(attempt.state or "pending")
        retry_safe = bool(attempt.retry_safe)
        result[goods_id] = {
            "attemptId": int(attempt.id),
            "status": state,
            "message": messages.get(state, "下架状态未知，请刷新后重试"),
            "retrySafe": retry_safe,
            "recovery": {
                "remote_confirmed": "retry_local_finalize",
                "failed": "resolve_and_retry" if retry_safe else "verify_in_xianyu_app",
                "unknown": "verify_in_xianyu_app",
            }.get(state),
            "errorCode": attempt.last_error_code,
            "remoteConfirmed": attempt.remote_confirmed_at is not None
            or state in {"remote_confirmed", "confirmed"},
            "localConfirmed": attempt.local_confirmed_at is not None or state == "confirmed",
            "updatedTime": _format_datetime(attempt.updated_time),
        }
    return result


def _order_delivery_status(order: XianyuTradeOrder) -> str:
    if (order.order_status or 0) >= 3:
        return "success"
    return "pending"


def _sum_item_quantity(items: list[dict[str, Any]]) -> int:
    total = 0
    for item in items:
        total += max(int(item.get("quantity") or item.get("goodsCount") or 1), 1)
    return total


def _build_order_item_record(
    item: XianyuTradeOrderItem,
    goods_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    external_goods_id = None
    if goods_extra:
        external_goods_id = goods_extra.get("externalGoodsId")
    return {
        "id": item.id,
        "goodsId": item.goods_id,
        "externalGoodsId": external_goods_id or item.goods_id,
        "goodsTitle": item.goods_title or item.goods_name or "",
        "goodsImage": item.goods_image or (goods_extra or {}).get("goodsImage"),
        "goodsPrice": str(item.goods_price) if item.goods_price is not None else None,
        "goodsCount": item.goods_count or item.quantity or 1,
        "quantity": item.quantity or item.goods_count or 1,
        "skuId": item.sku_id,
        "skuName": item.sku_name,
    }


def _build_order_record(
    order: XianyuTradeOrder,
    items: list[dict[str, Any]],
    manual_attempt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manual_attempt = manual_attempt or {}
    quantity_total = _sum_item_quantity(items)
    shipped = (order.order_status or 0) >= 3
    attempt_status = str(manual_attempt.get("state") or "").strip()
    message_confirmed = bool(manual_attempt.get("messageConfirmed"))
    attempt_quantity = int(manual_attempt.get("quantityRequested") or 0)
    first_external_goods_id = items[0].get("externalGoodsId") if items else None
    return {
        "id": order.id,
        "accountId": order.account_id,
        "xianyuAccountId": order.account_id,
        "externalOrderId": order.external_order_id,
        "orderId": order.external_order_id,
        "orderStatus": order.order_status,
        "totalAmount": order.total_amount,
        "buyerName": order.buyer_name,
        "buyerId": order.buyer_id,
        "createTime": _format_datetime(order.create_time),
        "payTime": _format_datetime(order.pay_time),
        "shipTime": _format_datetime(order.ship_time),
        "confirmTime": _format_datetime(order.confirm_time),
        "buyerMessage": order.buyer_message,
        "itemId": order.item_id or first_external_goods_id,
        "items": items,
        "itemSummary": " / ".join(
            filter(None, [f"{item.get('goodsTitle') or '-'} x{item.get('goodsCount') or 1}" for item in items[:2]])
        ),
        "quantityTotal": quantity_total,
        "quantityRequested": attempt_quantity or quantity_total,
        "quantitySent": (attempt_quantity or quantity_total) if (message_confirmed or shipped) else 0,
        "deliveryStatus": attempt_status or _order_delivery_status(order),
        "deliveryMethod": manual_attempt.get("deliveryMethod") or "manual_text",
        "deliveryContent": manual_attempt.get("deliveryContent") or order.buyer_message or "",
        "deliveryFailReason": manual_attempt.get("errorMessage") or "",
        "platformSyncTime": manual_attempt.get("updatedTime") or _format_datetime(order.updated_time),
        "manualDeliveryAttempt": manual_attempt.get("publicAttempt"),
        "isBargain": order.is_bargain,
        "isRated": order.is_rated,
        "isRedFlower": order.is_red_flower,
        "createdTime": _format_datetime(order.created_time),
        "updatedTime": _format_datetime(order.updated_time),
    }


async def _load_manual_delivery_attempts(
    db: AsyncSession,
    order_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not order_ids:
        return {}
    rows = (
        await db.execute(
            select(ManualDeliveryAttempt, DeliveryRecord)
            .outerjoin(DeliveryRecord, DeliveryRecord.id == ManualDeliveryAttempt.delivery_record_id)
            .where(ManualDeliveryAttempt.order_id.in_(order_ids))
        )
    ).all()
    result: dict[int, dict[str, Any]] = {}
    for attempt, record in rows:
        state = str(attempt.state or "pending")
        message_confirmed = attempt.message_confirmed_at is not None
        platform_confirmed = attempt.platform_confirmed_at is not None
        updated_time = _format_datetime(attempt.updated_time)
        lease_active = bool(attempt.lease_until and attempt.lease_until > datetime.datetime.now())
        public_status = state
        public_retry_scope = attempt.retry_scope
        public_retry_safe = bool(attempt.retry_safe)
        public_error_code = attempt.last_error_code
        public_error_message = attempt.error_message or ""
        if state == "pending":
            if lease_active:
                public_status = "in_progress"
                public_retry_safe = False
            elif attempt.message_started_at is not None and not message_confirmed:
                public_status = "unknown"
                public_retry_safe = False
                public_retry_scope = "message"
                public_error_code = "message_result_unknown_after_recovery"
                public_error_message = "上次发送在确认前中断，请先在闲鱼 App 核对，系统已禁止自动重发"
            else:
                public_status = "failed"
                public_retry_safe = True
                public_retry_scope = "message"
                public_error_code = "execution_interrupted_before_send"
                public_error_message = "执行在发送消息前中断，可使用原发货内容安全重试"
        elif state == "message_sent" and lease_active:
            public_status = "in_progress"
            public_retry_safe = False
        result[int(attempt.order_id)] = {
            "state": public_status,
            "deliveryMethod": f"manual_{attempt.delivery_mode or 'text'}",
            "deliveryContent": record.content if record is not None else "",
            "errorMessage": public_error_message,
            "quantityRequested": int(attempt.quantity_requested or 1),
            "messageConfirmed": message_confirmed,
            "updatedTime": updated_time,
            "publicAttempt": {
                "attemptId": int(attempt.id),
                "status": public_status,
                "retryScope": public_retry_scope,
                "retrySafe": public_retry_safe,
                "messageConfirmed": message_confirmed,
                "platformConfirmed": platform_confirmed,
                "errorCode": public_error_code,
                "updatedTime": updated_time,
            },
        }
    return result


@router.get("/goods", response_model=ResultObject)
async def list_goods(
    account_id: Optional[int] = Query(None, alias="accountId"),
    xianyu_account_id: Optional[int] = Query(None, alias="xianyuAccountId"),
    keyword: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    exclude_status: Optional[int] = Query(None, alias="excludeStatus"),
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    account_filter = account_id if account_id is not None else xianyu_account_id
    valid_account_ids = select(XianyuAccount.id).where(XianyuAccount.deleted == 0)
    query = select(XianyuGoods).where(
        XianyuGoods.deleted == 0,
        XianyuGoods.account_id.in_(valid_account_ids),
    )
    if account_filter is not None:
        query = query.where(XianyuGoods.account_id == account_filter)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                XianyuGoods.title.like(like),
                XianyuGoods.external_goods_id.like(like),
                XianyuGoods.goods_id.like(like),
            )
        )
    db_status = _fe_goods_status_to_db(status)
    if db_status is not None:
        query = query.where(XianyuGoods.status == db_status)
    excluded_db_status = _fe_goods_status_to_db(exclude_status)
    if excluded_db_status is not None:
        query = query.where(XianyuGoods.status != excluded_db_status)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    offset = (current - 1) * size
    result = await db.execute(query.order_by(XianyuGoods.id.desc()).offset(offset).limit(size))
    goods_list = result.scalars().all()
    goods_ids = [int(goods.id) for goods in goods_list]
    delivery_meta = await _load_goods_delivery_meta(db, goods_ids)
    remote_delete_meta = await _load_goods_remote_delete_meta(db, goods_ids)
    off_shelf_meta = await _load_goods_off_shelf_meta(db, goods_ids)
    records = [
        _goods_to_record(
            goods,
            delivery_meta.get(int(goods.id)),
            remote_delete_meta.get(int(goods.id)),
            off_shelf_meta.get(int(goods.id)),
        )
        for goods in goods_list
    ]
    return ResultObject.success({
        "records": records,
        "total": total,
        "current": current,
        "size": size,
    })


@router.get("/goods/stats", response_model=ResultObject)
async def goods_stats(
    account_id: Optional[int] = Query(None, alias="accountId"),
    xianyu_account_id: Optional[int] = Query(None, alias="xianyuAccountId"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    account_filter = account_id if account_id is not None else xianyu_account_id
    # 仅统计有效账号（deleted=0）的商品，已退出账号的旧商品不在前台展示
    valid_account_ids = select(XianyuAccount.id).where(XianyuAccount.deleted == 0)
    goods_filters = [XianyuGoods.deleted == 0, XianyuGoods.account_id.in_(valid_account_ids)]
    if account_filter is not None:
        goods_filters.append(XianyuGoods.account_id == account_filter)

    total = (
        await db.execute(
            select(func.count()).select_from(XianyuGoods).where(*goods_filters)
        )
    ).scalar() or 0
    on_sale = (
        await db.execute(
            select(func.count()).select_from(XianyuGoods).where(*goods_filters, XianyuGoods.status == 1)
        )
    ).scalar() or 0
    off_shelf_or_draft = total - on_sale

    goods_ids = (
        await db.execute(
            select(XianyuGoods.id).where(*goods_filters)
        )
    ).scalars().all()
    delivery_meta = await _load_goods_delivery_meta(db, [int(goods_id) for goods_id in goods_ids])
    auto_delivery_on = sum(1 for goods_id in goods_ids if delivery_meta.get(int(goods_id), {}).get("on"))

    auto_reply_filters = [XianyuGoods.deleted == 0, XianyuGoods.account_id.in_(valid_account_ids), XianyuGoods.auto_reply_enabled == 1]
    if account_filter is not None:
        auto_reply_filters.append(XianyuGoods.account_id == account_filter)
    auto_reply_accounts = (
        await db.execute(
            select(func.count(func.distinct(XianyuGoods.account_id))).where(*auto_reply_filters)
        )
    ).scalar() or 0

    return ResultObject.success({
        "total": total,
        "onSale": on_sale,
        "offShelfOrDraft": off_shelf_or_draft,
        "autoDeliveryOn": auto_delivery_on,
        "autoReplyAccounts": auto_reply_accounts,
    })


@router.post("/goods", response_model=ResultObject)
async def create_goods(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    goods = XianyuGoods(
        account_id=body.get("accountId") or body.get("xianyuAccountId"),
        goods_id=body.get("goodsId"),
        external_goods_id=body.get("externalGoodsId") or body.get("xyGoodsId"),
        title=body.get("title"),
        description=body.get("description"),
        price=str(body.get("price")) if body.get("price") is not None else None,
        sold_price=str(body.get("soldPrice")) if body.get("soldPrice") is not None else None,
        cover_pic=body.get("coverPic") or body.get("imageUrl"),
        image_url=body.get("imageUrl") or body.get("coverPic"),
        image_urls=body.get("imageUrls") if isinstance(body.get("imageUrls"), list) else None,
        stock=int(body.get("stock") or 0),
        quantity=int(body.get("quantity") or body.get("stock") or 0),
        detail_url=body.get("detailUrl"),
        detail_info=body.get("detailInfo"),
        category=body.get("category"),
        status=_fe_goods_status_to_db(body.get("status")) or 1,
        auto_reply_enabled=body.get("autoReplyEnabled") if body.get("autoReplyEnabled") is not None else body.get("auto_reply_enabled"),
        deleted=0,
    )
    db.add(goods)
    await db.commit()
    await db.refresh(goods)
    delivery_meta = await _load_goods_delivery_meta(db, [int(goods.id)])
    return ResultObject.success(_goods_to_record(goods, delivery_meta.get(int(goods.id))), "商品创建成功")


@router.get("/goods/{goods_id}", response_model=ResultObject)
async def goods_detail(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(XianyuGoods).where(XianyuGoods.id == goods_id, XianyuGoods.deleted == 0)
    )
    goods = result.scalar_one_or_none()
    if not goods:
        return ResultObject.failed("商品不存在", 404)
    delivery_meta = await _load_goods_delivery_meta(db, [goods_id])
    remote_delete_meta = await _load_goods_remote_delete_meta(db, [goods_id])
    off_shelf_meta = await _load_goods_off_shelf_meta(db, [goods_id])
    return ResultObject.success(
        _goods_to_record(
            goods,
            delivery_meta.get(goods_id),
            remote_delete_meta.get(goods_id),
            off_shelf_meta.get(goods_id),
        )
    )


@router.put("/goods/{goods_id}", response_model=ResultObject)
async def update_goods(
    goods_id: int,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(XianyuGoods).where(XianyuGoods.id == goods_id, XianyuGoods.deleted == 0)
    )
    goods = result.scalar_one_or_none()
    if not goods:
        return ResultObject.failed("商品不存在", 404)

    if "accountId" in body or "xianyuAccountId" in body:
        goods.account_id = body.get("accountId") or body.get("xianyuAccountId")
    if "goodsId" in body:
        goods.goods_id = body.get("goodsId")
    if "externalGoodsId" in body or "xyGoodsId" in body:
        goods.external_goods_id = body.get("externalGoodsId") or body.get("xyGoodsId")
    if "title" in body:
        goods.title = body.get("title")
    if "description" in body:
        goods.description = body.get("description")
    if "price" in body:
        goods.price = str(body.get("price")) if body.get("price") is not None else None
    if "soldPrice" in body:
        goods.sold_price = str(body.get("soldPrice")) if body.get("soldPrice") is not None else None
    if "stock" in body:
        goods.stock = int(body.get("stock") or 0)
    if "quantity" in body:
        goods.quantity = int(body.get("quantity") or 0)
    if "imageUrl" in body:
        goods.image_url = body.get("imageUrl")
    if "coverPic" in body:
        goods.cover_pic = body.get("coverPic")
    if "imageUrls" in body and isinstance(body.get("imageUrls"), list):
        goods.image_urls = body.get("imageUrls")
    if "detailUrl" in body:
        goods.detail_url = body.get("detailUrl")
    if "detailInfo" in body:
        goods.detail_info = body.get("detailInfo")
    if "category" in body:
        goods.category = body.get("category")
    if "status" in body:
        mapped = _fe_goods_status_to_db(body.get("status"))
        if mapped is not None:
            goods.status = mapped
    if "autoReplyEnabled" in body:
        goods.auto_reply_enabled = 1 if body.get("autoReplyEnabled") else 0
    if "auto_reply_enabled" in body:
        goods.auto_reply_enabled = body.get("auto_reply_enabled")
    goods.updated_time = datetime.datetime.now()

    await db.commit()
    await db.refresh(goods)
    delivery_meta = await _load_goods_delivery_meta(db, [goods_id])
    remote_delete_meta = await _load_goods_remote_delete_meta(db, [goods_id])
    off_shelf_meta = await _load_goods_off_shelf_meta(db, [goods_id])
    return ResultObject.success(
        _goods_to_record(
            goods,
            delivery_meta.get(goods_id),
            remote_delete_meta.get(goods_id),
            off_shelf_meta.get(goods_id),
        ),
        "商品更新成功",
    )


@router.delete("/goods/{goods_id}", response_model=ResultObject)
async def delete_goods(goods_id: int, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    return await delete_goods_local(goods_id, db, _)


@router.delete("/goods/{goods_id}/local", response_model=ResultObject)
async def delete_goods_local(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(XianyuGoods).where(XianyuGoods.id == goods_id, XianyuGoods.deleted == 0)
    )
    goods = result.scalar_one_or_none()
    if not goods:
        return ResultObject.failed("商品不存在", 404)
    goods.deleted = 1
    goods.updated_time = datetime.datetime.now()
    await db.commit()
    return ResultObject.success({"id": goods_id, "deleted": True}, "商品记录已删除")


@router.delete("/goods/{goods_id}/remote", response_model=ResultObject)
async def delete_goods_remote(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """远程删除商品：标记为已从闲鱼删除（status=3），本地记录保留。"""
    result = await db.execute(
        select(XianyuGoods).where(XianyuGoods.id == goods_id, XianyuGoods.deleted == 0)
    )
    goods = result.scalar_one_or_none()
    if not goods:
        return ResultObject.failed("商品不存在", 404)
    goods.status = 3
    goods.updated_time = datetime.datetime.now()
    await db.commit()
    return ResultObject.success({"id": goods_id, "status": 3}, "商品已标记为远程删除")


@router.get("/orders", response_model=ResultObject)
async def list_orders(
    account_id: Optional[int] = Query(None, alias="accountId"),
    keyword: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    sync: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    # sync=true 时先从闲鱼拉取最新订单入库，再返回本地查询结果
    if sync and account_id is not None:
        from ....services.xianyu_order_sync import sync_orders_for_account
        try:
            await sync_orders_for_account(account_id=int(account_id))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("list_orders 同步失败: accountId=%s error=%s", account_id, exc)

    query = select(XianyuTradeOrder).where(XianyuTradeOrder.deleted == 0)
    if account_id is not None:
        query = query.where(XianyuTradeOrder.account_id == account_id)
    if status is not None:
        query = query.where(XianyuTradeOrder.order_status == status)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                XianyuTradeOrder.external_order_id.like(like),
                XianyuTradeOrder.buyer_name.like(like),
                XianyuTradeOrder.buyer_id.like(like),
                XianyuTradeOrder.item_id.like(like),
            )
        )

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    offset = (current - 1) * size
    result = await db.execute(query.order_by(XianyuTradeOrder.id.desc()).offset(offset).limit(size))
    orders = result.scalars().all()
    order_ids = [int(order.id) for order in orders]

    items_by_order: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if order_ids:
        item_result = await db.execute(
            select(XianyuTradeOrderItem)
            .where(
                XianyuTradeOrderItem.deleted == 0,
                XianyuTradeOrderItem.order_id.in_(order_ids),
            )
            .order_by(XianyuTradeOrderItem.id.asc())
        )
        order_items = item_result.scalars().all()
        goods_ids = sorted({int(item.goods_id) for item in order_items if item.goods_id})
        goods_extra: dict[int, dict[str, Any]] = {}
        if goods_ids:
            goods_result = await db.execute(
                select(XianyuGoods).where(XianyuGoods.id.in_(goods_ids), XianyuGoods.deleted == 0)
            )
            for goods in goods_result.scalars():
                goods_extra[int(goods.id)] = {
                    "externalGoodsId": goods.external_goods_id,
                    "goodsImage": goods.cover_pic or goods.image_url,
                }
        for item in order_items:
            extra = goods_extra.get(int(item.goods_id)) if item.goods_id else None
            items_by_order[int(item.order_id)].append(_build_order_item_record(item, extra))

    attempts_by_order = await _load_manual_delivery_attempts(db, order_ids)
    records = [
        _build_order_record(
            order,
            items_by_order.get(int(order.id), []),
            attempts_by_order.get(int(order.id)),
        )
        for order in orders
    ]
    return ResultObject.success({
        "records": records,
        "total": total,
        "current": current,
        "size": size,
    })


@router.get("/orders/{order_id}", response_model=ResultObject)
async def order_detail(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(XianyuTradeOrder).where(XianyuTradeOrder.id == order_id, XianyuTradeOrder.deleted == 0)
    )
    order = result.scalar_one_or_none()
    if not order:
        return ResultObject.failed("订单不存在", 404)

    item_result = await db.execute(
        select(XianyuTradeOrderItem)
        .where(
            XianyuTradeOrderItem.deleted == 0,
            XianyuTradeOrderItem.order_id == order_id,
        )
        .order_by(XianyuTradeOrderItem.id.asc())
    )
    order_items = item_result.scalars().all()
    goods_ids = sorted({int(item.goods_id) for item in order_items if item.goods_id})
    goods_extra: dict[int, dict[str, Any]] = {}
    if goods_ids:
        goods_result = await db.execute(
            select(XianyuGoods).where(XianyuGoods.id.in_(goods_ids), XianyuGoods.deleted == 0)
        )
        for goods in goods_result.scalars():
            goods_extra[int(goods.id)] = {
                "externalGoodsId": goods.external_goods_id,
                "goodsImage": goods.cover_pic or goods.image_url,
            }
    items = [
        _build_order_item_record(item, goods_extra.get(int(item.goods_id)) if item.goods_id else None)
        for item in order_items
    ]
    attempts_by_order = await _load_manual_delivery_attempts(db, [int(order.id)])
    return ResultObject.success(
        _build_order_record(order, items, attempts_by_order.get(int(order.id)))
    )


@router.put("/orders/{order_id}", response_model=ResultObject)
async def update_order(
    order_id: int,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(XianyuTradeOrder).where(XianyuTradeOrder.id == order_id, XianyuTradeOrder.deleted == 0)
    )
    order = result.scalar_one_or_none()
    if not order:
        return ResultObject.failed("订单不存在", 404)
    if "orderStatus" in body:
        order.order_status = int(body.get("orderStatus"))
    if "buyerMessage" in body:
        order.buyer_message = body.get("buyerMessage")
    order.updated_time = datetime.datetime.now()
    await db.commit()
    return ResultObject.success({"id": order_id}, "订单更新成功")


@router.post("/orders/{order_id}/manual-delivery", response_model=ResultObject)
async def manual_delivery(
    order_id: int,
    body: ManualDeliveryReqDTO,
    coordinator: ManualDeliveryCoordinator = Depends(get_manual_delivery_coordinator),
    _: dict = Depends(get_current_user),
):
    command = ManualDeliveryCommand(
        delivery_mode=body.delivery_mode,
        delivery_content=body.delivery_content,
        quantity_requested=body.quantity_requested,
        idempotency_key=body.idempotency_key,
    )
    try:
        outcome = await coordinator.execute(order_id, command)
    except ManualDeliveryError as exc:
        data = {
            "status": "failed",
            "message": exc.public_message,
            "errorCode": exc.error_code,
            "orderId": order_id,
            "retrySafe": False,
            **exc.data,
        }
        result = ResultObject(code=exc.http_status, msg=exc.public_message, data=data)
        return JSONResponse(
            status_code=exc.http_status,
            content=result.model_dump(by_alias=True),
        )

    status_code = {
        "success": 200,
        "in_progress": 409,
        "pending": 409,
        "message_sent": 502,
        "failed": 502,
        "unknown": 409,
    }[outcome.status]
    result = ResultObject(
        code=status_code,
        msg=outcome.message,
        data=outcome.to_data(),
    )
    return JSONResponse(
        status_code=status_code,
        content=result.model_dump(by_alias=True),
    )


@router.post("/orders/{order_id}/sync", response_model=ResultObject)
async def sync_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(XianyuTradeOrder).where(XianyuTradeOrder.id == order_id, XianyuTradeOrder.deleted == 0)
    )
    order = result.scalar_one_or_none()
    if not order:
        return ResultObject.failed("订单不存在", 404)
    # 调用闲鱼 API 同步该账号的全部订单（闲鱼接口不支持单订单拉取，整账号同步后该订单会更新）
    from ....services.xianyu_order_sync import sync_orders_for_account
    sync_result = await sync_orders_for_account(account_id=int(order.account_id))
    if not sync_result.get("success"):
        return ResultObject.failed(f"订单同步失败: {sync_result.get('error', '未知错误')}")
    return ResultObject.success({
        "ok": True,
        "orderId": order_id,
        "syncResult": sync_result,
        "message": "订单同步完成",
    })


@router.post("/orders/sync", response_model=ResultObject)
async def sync_orders(
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    account_id = body.get("accountId")
    if account_id is None:
        return ResultObject.validate_failed("缺少 accountId 参数")
    account_id = int(account_id)
    # 调用闲鱼 API 同步该账号的已售订单
    from ....services.xianyu_order_sync import sync_orders_for_account
    sync_result = await sync_orders_for_account(account_id=account_id)
    if not sync_result.get("success"):
        return ResultObject.failed(f"订单同步失败: {sync_result.get('error', '未知错误')}")
    # 同步完成后查询本地订单数量
    count_result = await db.execute(
        select(func.count()).select_from(XianyuTradeOrder).where(
            XianyuTradeOrder.deleted == 0,
            XianyuTradeOrder.account_id == account_id,
        )
    )
    count = count_result.scalar() or 0
    return ResultObject.success({
        "ok": True,
        "accountId": account_id,
        "count": count,
        "syncResult": sync_result,
        "message": f"账号 {account_id} 的订单同步完成，共 {sync_result.get('total', 0)} 条，本地累计 {count} 条",
    })


@router.get("/item/syncTasks", response_model=ResultObject)
async def list_goods_sync_tasks(
    account_id: Optional[int] = Query(None, alias="accountId"),
    status: Optional[str] = Query(None),
    current: int = Query(1, ge=1),
    size: int = Query(5, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = select(XianyuGoodsSyncTask).where(XianyuGoodsSyncTask.deleted == 0)
    if account_id is not None:
        query = query.where(XianyuGoodsSyncTask.account_id == account_id)
    if status:
        query = query.where(XianyuGoodsSyncTask.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    offset = (current - 1) * size
    result = await db.execute(
        query.order_by(XianyuGoodsSyncTask.created_time.desc(), XianyuGoodsSyncTask.id.desc()).offset(offset).limit(size)
    )
    records = []
    for task in result.scalars():
        records.append({
            "id": task.id,
            "syncId": task.sync_id,
            "accountId": task.account_id,
            "status": task.status,
            "progress": task.progress or 0,
            "total": task.total_count or 0,
            "newCount": task.new_count or 0,
            "updatedCount": task.updated_count or 0,
            "skippedCount": task.skipped_count or 0,
            "offShelfCount": task.off_shelf_count or 0,
            "durationSeconds": task.duration_seconds or 0,
            "errorMessage": task.error_message,
            "createdTime": _format_datetime(task.created_time),
            "updatedTime": _format_datetime(task.updated_time),
            "startedTime": _format_datetime(task.started_time),
            "finishedTime": _format_datetime(task.finished_time),
        })
    return ResultObject.success({
        "records": records,
        "total": total,
        "current": current,
        "size": size,
    })
