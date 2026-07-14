import logging
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from ....core.database import get_db
from ....core.response import ResultObject
from ....models.entities import XianyuMessage, XianyuChatMessage
from ....schemas.common import MsgListReqDTO, MsgDTO
from ....services.ws_storage import (
    get_online_conversations,
    get_online_conversations_paged,
    get_context_messages,
    _fetch_remote_conversation_user_info,
    _save_conversation_user_info,
)
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/msg")


def normalize_context_params(s_id=None, peer_user_id=None, peer_key=None):
    """统一归一化上下文查询参数。

    - s_id 允许 sid:xxx、裸 sid、sid@goofish，入库查询时统一转为裸 sid
    - peer_user_id 必须为真实 UID，不允许带 sid: 前缀
    - peer_key 仅为兜底，从中提取 s_id
    """
    s_id = str(s_id or "").strip()
    peer_user_id = str(peer_user_id or "").strip()
    peer_key = str(peer_key or "").strip()

    if s_id.startswith("sid:"):
        s_id = s_id[4:]
    if s_id.endswith("@goofish"):
        s_id = s_id[:-8]

    if peer_user_id.startswith("sid:"):
        if not s_id:
            s_id = peer_user_id[4:]
        peer_user_id = ""
    if peer_user_id.endswith("@goofish"):
        peer_user_id = peer_user_id[:-8]

    if peer_key.startswith("sid:"):
        if not s_id:
            s_id = peer_key[4:]
        peer_key = ""
    elif peer_key.endswith("@goofish") and not s_id:
        s_id = peer_key[:-8]

    return s_id, peer_user_id, peer_key


def message_to_dto(msg: XianyuMessage) -> MsgDTO:
    """将新实体 XianyuMessage 转换为 MsgDTO"""
    return MsgDTO(
        id=msg.id,
        xianyu_account_id=msg.account_id,
        session_id=str(msg.conversation_id) if msg.conversation_id else None,
        from_user_id=msg.from_user_id,
        to_user_id=msg.to_user_id,
        content=msg.content,
        message_type=msg.message_type,
        direction=msg.direction,
        created_time=str(msg.created_time) if msg.created_time else None,
    )


@router.post("/list", response_model=ResultObject[dict])
async def list_messages(
    req: MsgListReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        page_num = max(req.page_num or 1, 1)
        page_size = max(min(req.page_size or 20, 100), 1)
        account_id = req.xianyu_account_id
        s_id = req.session_id
        where_sql = ["deleted = 0"]
        params = {}
        if account_id is not None:
            where_sql.append("account_id = :account_id")
            params["account_id"] = account_id
        if s_id:
            where_sql.append("s_id = :s_id")
            params["s_id"] = str(s_id)

        where_clause = " AND ".join(where_sql)
        total_result = await db.execute(
            text(f"SELECT COUNT(*) FROM xianyu_chat_message WHERE {where_clause}"),
            params,
        )
        total = total_result.scalar() or 0

        offset = (page_num - 1) * page_size
        params.update({"offset": offset, "limit": page_size})
        rows = await db.execute(
            text(f"""
                SELECT id, account_id, s_id, sender_user_id, msg_content, content_type, direction, message_time
                FROM xianyu_chat_message
                WHERE {where_clause}
                ORDER BY message_time ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        records = []
        for row in rows.mappings().all():
            records.append(MsgDTO(
                id=row["id"],
                xianyu_account_id=row["account_id"],
                session_id=str(row["s_id"]) if row["s_id"] is not None else None,
                from_user_id=row["sender_user_id"],
                to_user_id=None,
                content=row["msg_content"],
                message_type=str(row["content_type"]),
                direction=row["direction"],
                created_time=str(row["message_time"]) if row["message_time"] is not None else None,
            ))

        pages = math.ceil(total / page_size) if total > 0 else 0
        return ResultObject.success({
            "records": records,
            "total": total,
            "pageNum": page_num,
            "pageSize": page_size,
            "pages": pages
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Message list unavailable errorType=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="会话消息暂不可用，请稍后重试。",
        ) from exc


@router.post("/context")
async def message_context(
    req: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取会话上下文消息（从 xianyu_chat_message 表查询）。"""
    try:
        account_id = req.get("xianyuAccountId") or req.get("accountId")
        s_id = req.get("sessionId") or req.get("sId") or req.get("sid") or req.get("cid")
        peer_user_id = req.get("peerUserId") or req.get("peer_user_id") or ""
        peer_key = req.get("peerKey") or req.get("peer_key") or ""
        limit = req.get("limit", 50)
        offset = req.get("offset", 0)
        user_id = current_user.get("user_id")
        logger.info(
            "message_context request hasAccount=%s hasSession=%s hasPeer=%s limit=%s offset=%s",
            bool(account_id), bool(s_id), bool(peer_user_id), limit, offset,
        )
        # user_id=0 表示内部系统调用，不按用户过滤
        if user_id == 0:
            user_id = None
            logger.info("message_context: user_id=0 转为 None")
        
        # 统一参数归一化
        s_id, peer_user_id, _ = normalize_context_params(
            s_id=s_id, peer_user_id=peer_user_id, peer_key=peer_key
        )
        
        if not account_id:
            raise HTTPException(status_code=422, detail="accountId 不能为空。")
        if not s_id and not peer_user_id:
            raise HTTPException(status_code=422, detail="必须提供 sid、sessionId 或 peerUserId。")
        try:
            normalized_account_id = int(account_id)
            normalized_limit = int(limit)
            normalized_offset = int(offset)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="账号或分页参数格式无效。") from exc
        if normalized_account_id <= 0:
            raise HTTPException(status_code=422, detail="accountId 必须为正整数。")
        if not 1 <= normalized_limit <= 200 or normalized_offset < 0:
            raise HTTPException(
                status_code=422,
                detail="limit 必须在 1 到 200 之间，offset 不能小于 0。",
            )

        messages, total = await get_context_messages(
            db,
            normalized_account_id,
            s_id,
            normalized_limit,
            normalized_offset,
            user_id=user_id,
            peer_user_id=peer_user_id,
        )
        return ResultObject.success({"messages": messages, "total": total})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Message context unavailable errorType=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="会话消息暂不可用，请稍后重试。",
        ) from exc

@router.get("/online/conversations")
async def online_conversations(
    xianyu_account_id: int = Query(..., alias="xianyuAccountId", gt=0),
    cursor: int | None = Query(None, alias="cursor"),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    limit: int | None = Query(None, alias="limit", ge=1, le=100),
        db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取在线会话列表（实时调用 IM WebSocket，支持 cursor 分页）。

    修复问题：之前从 xianyu_chat_message 表聚合，只有收到消息的会话才出现；
    且后台拉取 live conversations 有 page<3 限制，导致会话列表不完全。
    现在改为实时调用 IM WebSocket /r/Conversation/listNewestPagination，
    支持 cursor 真分页，能加载所有会话。
    """
    user_id = current_user.get("user_id")
    if user_id == 0:
        user_id = None
    logger.info(
        "online_conversations: xianyuAccountId=%s cursor=%s pageSize=%s limit=%s",
                     xianyu_account_id, cursor, page_size, limit,
    )
    try:
        # 兼容旧参数 limit：如果传了 limit 且没传 cursor，用旧逻辑（DB 聚合）
        if limit is not None and cursor is None:
            conversations = await get_online_conversations(
                db=db, account_id=xianyu_account_id,
                limit=limit, user_id=user_id,
            )
            return ResultObject.success({"conversations": conversations, "hasMore": False, "nextCursor": None})

        # 新逻辑：实时 IM + cursor 分页
        result = await get_online_conversations_paged(
            db=db, account_id=xianyu_account_id,
            cursor=cursor, page_size=page_size, user_id=user_id,
        )
        return ResultObject.success(result)
    except Exception as exc:
        logger.error(
            "Online conversations unavailable accountId=%d errorType=%s",
            xianyu_account_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="在线会话暂不可用，请稍后重试。",
        ) from exc


@router.post("/avatars")
async def batch_query_avatars(
    req: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """批量查询会话用户头像和昵称。

    模仿目标项目 xianyu-auto-reply 的头像查询机制：
    - 前端找出缺头像的会话，分批调用此端点
    - 后端调用 mtop.taobao.idlemessage.pc.user.query 查询
    - 写入 DB 缓存并返回结果

    请求体：{accountId, queries: [{cid, sid}, ...]}
    响应：{items: [{cid, avatar, nick}, ...]}
    """
    account_id = req.get("accountId") or req.get("xianyuAccountId")
    queries = req.get("queries")
    if not account_id:
        raise HTTPException(status_code=422, detail="accountId 不能为空。")
    try:
        normalized_account_id = int(account_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="accountId 格式无效。") from exc
    if normalized_account_id <= 0:
        raise HTTPException(status_code=422, detail="accountId 必须为正整数。")
    if queries is None or not isinstance(queries, list):
        raise HTTPException(status_code=422, detail="queries 必须为数组。")
    if not queries:
        return ResultObject.success({
            "items": [],
            "requestedCount": 0,
            "attemptedCount": 0,
            "resolvedCount": 0,
            "providerFailureCount": 0,
            "unresolvedCount": 0,
            "partial": False,
            "cachePersisted": True,
        })

    items = []
    attempted_count = 0
    provider_failure_count = 0
    cache_persisted = True
    cache_updates: list[tuple[str, str, str]] = []
    for q in queries:
        if not isinstance(q, dict):
            continue
        cid = str(q.get("cid") or q.get("sid") or "").strip()
        if not cid:
            continue
        attempted_count += 1
        try:
            info = await _fetch_remote_conversation_user_info(normalized_account_id, cid)
            if not isinstance(info, dict):
                raise RuntimeError("avatar provider returned an invalid response")
        except Exception as exc:
            logger.warning(
                "Avatar provider query failed accountId=%d errorType=%s",
                normalized_account_id,
                type(exc).__name__,
            )
            provider_failure_count += 1
            continue
        avatar = info.get("avatar") or ""
        nick = info.get("nick") or ""
        if avatar or nick:
            cache_updates.append((cid, avatar, nick))
            items.append({"cid": cid, "avatar": avatar, "nick": nick})

    if attempted_count == 0:
        raise HTTPException(status_code=422, detail="queries 中没有有效的 cid 或 sid。")
    if provider_failure_count == attempted_count:
        raise HTTPException(
            status_code=503,
            detail="头像查询服务暂不可用，请稍后重试。",
        )

    # Provider calls may block for seconds. Finish that phase before the first
    # database write so the request transaction never pins a pool connection
    # across the next remote avatar lookup.
    for cid, avatar, nick in cache_updates:
        try:
            await _save_conversation_user_info(
                db,
                normalized_account_id,
                cid,
                avatar,
                nick,
            )
        except Exception as exc:
            cache_persisted = False
            logger.warning(
                "Avatar cache write failed accountId=%d errorType=%s",
                normalized_account_id,
                type(exc).__name__,
            )

    try:
        await db.commit()
    except Exception as exc:
        cache_persisted = False
        logger.warning(
            "Avatar cache commit failed accountId=%d errorType=%s",
            normalized_account_id,
            type(exc).__name__,
        )
    unresolved_count = attempted_count - len(items) - provider_failure_count
    return ResultObject.success({
        "items": items,
        "requestedCount": len(queries),
        "attemptedCount": attempted_count,
        "resolvedCount": len(items),
        "providerFailureCount": provider_failure_count,
        "unresolvedCount": max(0, unresolved_count),
        "partial": provider_failure_count > 0 or not cache_persisted,
        "cachePersisted": cache_persisted,
    })
