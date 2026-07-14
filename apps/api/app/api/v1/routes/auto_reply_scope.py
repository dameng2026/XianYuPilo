"""
自动回复作用域管理路由。
支持三档作用域：
- 全局：ai-customer-service.enabled（主开关，在 BusinessSettingsService 管理）
- 账号级：user_business_setting 的 auto-reply-account-scopes 配置
- 商品级：xianyu_goods.auto_reply_enabled 列

作用域优先级：商品级 > 账号级 > 全局（NULL 不继承全局，默认关闭）。
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.response import ResultObject
from ....models.entities import XianyuGoods
from ....services.business_settings import (
    load_raw_business_setting,
    save_raw_business_setting,
)
from .internal import verify_internal_or_current_user as verify_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auto-reply-scope", tags=["autoReplyScope"])

ACCOUNT_SCOPES_KEY = "auto-reply-account-scopes"


@router.get("/products")
async def list_products_with_scope(
    request: Request,
    accountId: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """返回商品列表及每个商品的 effective auto_reply 状态。"""
    try:
        goods_list = await _load_goods_rows(db, accountId)

        account_scopes = await _load_account_scopes(db)
        global_enabled = await _load_global_enabled(db)

        items = []
        for g in goods_list:
            effective = _compute_effective(g.get("auto_reply_enabled"), g.get("account_id"), account_scopes, global_enabled)
            items.append({
                "id": g.get("id"),
                "title": g.get("title") or "",
                "accountId": g.get("account_id"),
                "goodsId": g.get("external_goods_id") or g.get("goods_id"),
                "auto_reply_enabled": g.get("auto_reply_enabled"),
                "effective_enabled": effective,
                "account_enabled": account_scopes.get("accounts", {}).get(str(g.get("account_id"))) if account_scopes else None,
                "global_enabled": global_enabled,
            })
        return ResultObject.success({"items": items, "total": len(items)})
    except Exception as e:
        logger.exception("查询商品作用域列表失败")
        return ResultObject.internal_error()


@router.post("/product")
async def update_product_scope(
    request: Request,
    req: Dict[str, Any] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """更新单个商品的 auto_reply_enabled。"""
    try:
        if req is None:
            req = {}
        item_id = req.get("itemId")
        enabled = req.get("enabled")
        if item_id is None or enabled is None:
            return ResultObject.failed("缺少 itemId 或 enabled 参数")
        value = 1 if bool(enabled) else 0
        stmt = update(XianyuGoods).where(
            XianyuGoods.id == int(item_id),
        ).values(auto_reply_enabled=value)
        result = await db.execute(stmt)
        await db.commit()
        if result.rowcount == 0:
            return ResultObject.failed("商品不存在或无权操作")
        logger.info("更新商品 auto_reply_enabled itemId=%s enabled=%s", item_id, value)
        return ResultObject.success({"ok": True, "itemId": int(item_id), "enabled": bool(enabled)})
    except Exception as e:
        logger.exception("更新商品作用域失败 itemId=%s", req.get("itemId") if req else None)
        return ResultObject.internal_error()


@router.post("/account")
async def update_account_scope(
    request: Request,
    req: Dict[str, Any] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """更新账号级 auto_reply 启用状态（存储在 user_business_setting 的 auto-reply-account-scopes 配置中）。"""
    try:
        if req is None:
            req = {}
        account_id = req.get("accountId")
        enabled = req.get("enabled")
        if account_id is None or enabled is None:
            return ResultObject.failed("缺少 accountId 或 enabled 参数")
        scopes = await _load_account_scopes(db)
        accounts = scopes.setdefault("accounts", {})
        accounts[str(int(account_id))] = bool(enabled)
        await _save_account_scopes(db, scopes)
        logger.info("更新账号作用域 accountId=%s enabled=%s", account_id, enabled)
        return ResultObject.success({"ok": True, "accountId": int(account_id), "enabled": bool(enabled)})
    except Exception as e:
        logger.exception("更新账号作用域失败 accountId=%s", req.get("accountId") if req else None)
        return ResultObject.internal_error()


@router.post("/batch")
async def batch_update_scope(
    request: Request,
    req: Dict[str, Any] = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """批量更新商品或账号的 auto_reply 状态。

    Body:
      - {"itemIds": [1,2,3], "enabled": true}  批量更新商品
      - {"accountIds": [1,2], "enabled": true}  批量更新账号
    """
    try:
        if req is None:
            req = {}
        enabled = req.get("enabled")
        if enabled is None:
            return ResultObject.failed("缺少 enabled 参数")
        value = bool(enabled)

        item_ids = req.get("itemIds")
        account_ids = req.get("accountIds")

        if item_ids:
            int_ids = [int(i) for i in item_ids if i is not None]
            if int_ids:
                stmt = update(XianyuGoods).where(
                    XianyuGoods.id.in_(int_ids),
                ).values(auto_reply_enabled=1 if value else 0)
                result = await db.execute(stmt)
                await db.commit()
                logger.info("批量更新商品 auto_reply affected=%s enabled=%s", result.rowcount, value)
                return ResultObject.success({"ok": True, "affected": result.rowcount, "type": "product"})

        if account_ids:
            int_ids = [int(i) for i in account_ids if i is not None]
            if int_ids:
                scopes = await _load_account_scopes(db)
                accounts = scopes.setdefault("accounts", {})
                for aid in int_ids:
                    accounts[str(aid)] = value
                await _save_account_scopes(db, scopes)
                logger.info("批量更新账号作用域 count=%s enabled=%s", len(int_ids), value)
                return ResultObject.success({"ok": True, "affected": len(int_ids), "type": "account"})

        return ResultObject.failed("需要提供 itemIds 或 accountIds 参数")
    except Exception as e:
        logger.exception("批量更新作用域失败")
        return ResultObject.internal_error()


@router.get("/status")
async def get_scope_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """返回全局开关、账号级作用域配置。"""
    try:
        account_scopes = await _load_account_scopes(db)
        global_enabled = await _load_global_enabled(db)
        return ResultObject.success({
            "global_enabled": global_enabled,
            "account_scopes": account_scopes.get("accounts", {}),
        })
    except Exception as e:
        logger.exception("查询作用域状态失败")
        return ResultObject.internal_error()


# ===== 内部辅助方法 =====

async def _load_account_scopes(db: AsyncSession) -> Dict[str, Any]:
    """从 user_business_setting 表读取 auto-reply-account-scopes 配置。"""
    config = await load_raw_business_setting(db, ACCOUNT_SCOPES_KEY)
    return config if isinstance(config, dict) else {"accounts": {}}


async def _save_account_scopes(db: AsyncSession, scopes: Dict[str, Any]):
    """保存 auto-reply-account-scopes 配置到 user_business_setting 表。"""
    await save_raw_business_setting(db, ACCOUNT_SCOPES_KEY, scopes)


async def _load_global_enabled(db: AsyncSession) -> bool:
    """读取 ai-customer-service.enabled 主开关状态。"""
    config = await load_raw_business_setting(db, "ai-customer-service")
    return bool(config.get("enabled", False)) if isinstance(config, dict) else False


async def _load_goods_rows(db: AsyncSession, account_id: Optional[int]) -> list[Dict[str, Any]]:
    """兼容旧表结构的商品查询。

    某些旧版部署数据库缺少 xianyu_goods.raw_payload 等新列。
    这里优先使用显式列 SQL，避免 ORM 按模型全量取列时触发 Unknown column。

    过滤规则与商品管理页（/goods）保持一致：仅返回未删除且属于未删除账号的商品，
    避免展示已删除账号的遗留商品导致两处数量不一致。
    """
    sql = """
        SELECT id, account_id, goods_id, external_goods_id, title, auto_reply_enabled, created_time
        FROM xianyu_goods
        WHERE deleted = 0
          AND account_id IN (SELECT id FROM xianyu_account WHERE deleted = 0)
    """
    params: Dict[str, Any] = {}
    if account_id is not None:
        sql += " AND account_id = :account_id"
        params["account_id"] = account_id
    sql += " ORDER BY created_time DESC"
    result = await db.execute(text(sql), params)
    return [dict(row._mapping) for row in result.fetchall()]


def _compute_effective(
    product_enabled: Optional[int],
    account_id: Optional[int],
    account_scopes: Dict[str, Any],
    global_enabled: bool,
) -> bool:
    """计算商品的 effective auto_reply 状态。

    优先级：商品级 > 账号级 > 全局（NULL 不继承全局，默认关闭）。
    """
    if not global_enabled:
        return False  # 主开关关闭
    if product_enabled is not None:
        return product_enabled == 1  # 商品级覆盖
    accounts = account_scopes.get("accounts", {}) if account_scopes else {}
    if account_id is not None and str(account_id) in accounts:
        return bool(accounts[str(account_id)])  # 账号级
    return False  # 默认关闭（NULL 不继承全局）
