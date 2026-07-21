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


# ============================================================
# 会话级自动回复运行时状态（人工干预自动暂停/恢复）
# ============================================================
#
# 业务规则：
#   1. 人工发送消息后，会话级 auto_reply_paused=1（人工干预暂停）
#   2. 买家发送"开启自动回复"指令 → 自动恢复（仅当未被用户手动关闭）
#   3. 距上次人工回复 > 1 分钟，买家发新消息时自动恢复
#   4. 用户在网站手动点击按钮关闭时，auto_reply_manual_disabled=1，
#      禁止自动恢复，仅允许用户手动开启


async def _resolve_conversation_by_sid(
    db: AsyncSession,
    account_id: int,
    sid: str,
    peer_user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """通过 sId 反查消息表找到对端身份，再匹配 xianyu_conversation。
    如果传入 peer_user_id，直接使用该值作为对端身份候选。
    """
    if not sid and not peer_user_id:
        return None

    sid_norm = (sid or "").strip()
    if sid_norm.startswith("sid:"):
        sid_norm = sid_norm[4:]
    sid_goofish = f"{sid_norm}@goofish" if sid_norm and not sid_norm.endswith("@goofish") else sid_norm

    peer_id_candidates: list[str] = []
    if peer_user_id:
        v = str(peer_user_id).strip()
        if v:
            peer_id_candidates.append(v)
            if v.endswith("@goofish") and v[:-8] not in peer_id_candidates:
                peer_id_candidates.append(v[:-8])
            elif not v.endswith("@goofish") and f"{v}@goofish" not in peer_id_candidates:
                peer_id_candidates.append(f"{v}@goofish")

    if sid_norm:
        sid_peer_row = (await db.execute(text("""
            SELECT peer_external_uid, sender_user_id, receiver_user_id
            FROM xianyu_chat_message
            WHERE account_id = :account_id
              AND deleted = 0
              AND s_id COLLATE utf8mb4_unicode_ci IN (:sid, :sid_goofish)
            ORDER BY id DESC LIMIT 1
        """), {
            "account_id": account_id,
            "sid": sid_norm,
            "sid_goofish": sid_goofish,
        })).mappings().first()
        if sid_peer_row:
            for key in ("peer_external_uid", "sender_user_id", "receiver_user_id"):
                v = str(sid_peer_row.get(key) or "").strip()
                if v and v not in peer_id_candidates:
                    peer_id_candidates.append(v)

    if not peer_id_candidates:
        return None

    placeholders = ", ".join([f":p{i}" for i in range(len(peer_id_candidates))])
    params = {"account_id": account_id}
    for i, v in enumerate(peer_id_candidates):
        params[f"p{i}"] = v

    conv_row = (await db.execute(text(f"""
        SELECT id, account_id, external_buyer_id, peer_external_uid, peer_key,
               auto_reply_paused, auto_reply_manual_disabled,
               last_manual_reply_at, last_auto_reply_at
        FROM xianyu_conversation
        WHERE account_id = :account_id
          AND (
              external_buyer_id IN ({placeholders})
              OR peer_external_uid IN ({placeholders})
              OR peer_key IN ({placeholders})
          )
        ORDER BY id DESC LIMIT 1
    """), params)).mappings().first()
    return dict(conv_row) if conv_row else None


@router.post("/conversation-toggle")
async def toggle_conversation_auto_reply(
    request: Request,
    req: Dict[str, Any] | None = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """会话级自动回复手动开关。
    用户在网站点击按钮开启/关闭时调用，与人工干预触发的自动暂停区分：
    - enabled=true：手动开启（清除暂停 + 清除手动关闭标记）
    - enabled=false：手动关闭（设置暂停 + 设置手动关闭标记，禁止自动恢复）
    """
    try:
        payload = req or {}
        account_id = payload.get("accountId")
        sid = payload.get("sid") or payload.get("sId") or payload.get("sessionId")
        peer_user_id = payload.get("peerUserId") or payload.get("peerId")
        enabled = payload.get("enabled")
        if account_id is None or enabled is None or (not sid and not peer_user_id):
            return ResultObject.failed("缺少 accountId、enabled 或 sid/peerUserId 参数")

        conv = await _resolve_conversation_by_sid(
            db, int(account_id), str(sid or ""), peer_user_id
        )
        if not conv:
            return ResultObject.failed("未找到对应会话", code=404)

        conversation_id = int(conv["id"])
        if bool(enabled):
            # 手动开启：清除暂停 + 清除手动关闭标记 + 重置人工回复时间戳
            await db.execute(text("""
                UPDATE xianyu_conversation
                SET auto_reply_paused = 0,
                    auto_reply_manual_disabled = 0,
                    last_manual_reply_at = NULL,
                    updated_time = NOW()
                WHERE id = :conversation_id
            """), {"conversation_id": conversation_id})
            logger.info(
                "conversation auto reply manual resume accountId=%s convId=%d",
                account_id, conversation_id
            )
        else:
            # 手动关闭：设置暂停 + 设置手动关闭标记（禁止自动恢复）
            await db.execute(text("""
                UPDATE xianyu_conversation
                SET auto_reply_paused = 1,
                    auto_reply_manual_disabled = 1,
                    updated_time = NOW()
                WHERE id = :conversation_id
            """), {"conversation_id": conversation_id})
            logger.info(
                "conversation auto reply manual pause accountId=%s convId=%d",
                account_id, conversation_id
            )

        await db.commit()
        return ResultObject.success({
            "ok": True,
            "conversationId": conversation_id,
            "accountId": int(account_id),
            "enabled": bool(enabled),
            "autoReplyPaused": 0 if bool(enabled) else 1,
            "autoReplyManualDisabled": 0 if bool(enabled) else 1,
        })
    except Exception as exc:
        logger.exception("切换会话自动回复状态失败")
        return ResultObject.internal_error()


@router.get("/conversation-status")
async def get_conversation_auto_reply_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """查询会话级自动回复状态。
    返回字段：
      - autoReplyPaused：会话级是否暂停（0否 1是）
      - autoReplyManualDisabled：是否被用户手动关闭（0否 1是）
      - lastManualReplyAt：最后人工回复时间戳（毫秒）
      - lastAutoReplyAt：最后 AI 自动回复时间戳（毫秒）
      - effectiveEnabled：综合账号级/全局开关后的"配置层"是否启用
      - runningEnabled：实际是否在自动回复（配置层启用 且 会话级未暂停）
    """
    try:
        account_id = request.query_params.get("accountId")
        sid = request.query_params.get("sid") or request.query_params.get("sId") or request.query_params.get("sessionId")
        peer_user_id = request.query_params.get("peerUserId") or request.query_params.get("peerId")
        if not account_id or (not sid and not peer_user_id):
            return ResultObject.failed("缺少 accountId 或 sid/peerUserId 参数")

        conv = await _resolve_conversation_by_sid(
            db, int(account_id), str(sid or ""), peer_user_id
        )
        if not conv:
            # 会话尚未建立时，按"未暂停"返回，让前端按账号级/全局开关展示
            account_scopes = await _load_account_scopes(db)
            global_enabled = await _load_global_enabled(db)
            accounts = account_scopes.get("accounts", {}) if account_scopes else {}
            account_enabled = bool(accounts.get(str(account_id))) if str(account_id) in accounts else True
            effective = bool(global_enabled) and account_enabled
            return ResultObject.success({
                "conversationId": None,
                "autoReplyPaused": 0,
                "autoReplyManualDisabled": 0,
                "lastManualReplyAt": None,
                "lastAutoReplyAt": None,
                "effectiveEnabled": effective,
                "runningEnabled": effective,
            })

        conversation_id = int(conv["id"])
        auto_reply_paused = int(conv.get("auto_reply_paused") or 0)
        auto_reply_manual_disabled = int(conv.get("auto_reply_manual_disabled") or 0)
        last_manual_at = conv.get("last_manual_reply_at")
        last_auto_at = conv.get("last_auto_reply_at")

        # 综合账号级/全局开关
        account_scopes = await _load_account_scopes(db)
        global_enabled = await _load_global_enabled(db)
        accounts = account_scopes.get("accounts", {}) if account_scopes else {}
        account_enabled = bool(accounts.get(str(account_id))) if str(account_id) in accounts else True
        effective = bool(global_enabled) and account_enabled
        running = effective and auto_reply_paused == 0

        return ResultObject.success({
            "conversationId": conversation_id,
            "autoReplyPaused": auto_reply_paused,
            "autoReplyManualDisabled": auto_reply_manual_disabled,
            "lastManualReplyAt": int(last_manual_at) if last_manual_at is not None else None,
            "lastAutoReplyAt": int(last_auto_at) if last_auto_at is not None else None,
            "effectiveEnabled": effective,
            "runningEnabled": running,
            "pausedReason": "manual_disable" if auto_reply_manual_disabled == 1
                            else ("manual_intervention" if auto_reply_paused == 1 else None),
        })
    except Exception as exc:
        logger.exception("查询会话自动回复状态失败")
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
