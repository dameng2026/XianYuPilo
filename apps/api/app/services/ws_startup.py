"""
WebSocket startup service.

On application startup, automatically read all logged-in Xianyu accounts
and start their WebSocket connections.
"""
import asyncio
import logging

from sqlalchemy import text

from ..core.cookie_crypto import decrypt_cookie_if_needed
from ..core.database import async_session
from .ai_reply_batcher import (
    AiAutoReplyBatcher,
    AiAutoReplyBatcherCapacityError,
)
from .business_settings import AI_CS_SETTING_KEY, load_business_setting
from .message_automation_outbox import (
    DispatchDisposition,
    NonRetryableOutboxError,
    OutboxClaim,
    RetryableOutboxError,
    UnknownOutboxError,
    complete_deferred_messages,
    enqueue_message_automation,
    fail_deferred_messages,
    load_claim_message,
    notify_message_automation_worker,
    settle_deferred_messages,
    start_message_automation_outbox_worker,
    stop_message_automation_outbox_worker,
)
from .ws_client import ws_manager
from .ws_storage import save_chat_message, stable_chat_message_uid

logger = logging.getLogger(__name__)


async def _run_delivery_after_message_saved(account_id: int, msg: dict):
    """Run delivery through its durable coordinator and propagate local failure."""
    try:
        from .ws_delivery_handler import (
            _process_delivery,
            is_bargain_success_message,
            is_payment_message,
        )

        payment_event = is_payment_message(msg)
        if not payment_event and not is_bargain_success_message(msg):
            return None
        async with async_session() as db:
            try:
                outcome = await _process_delivery(db, account_id, msg)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        # Notifications are secondary to the exactly-once delivery boundary;
        # their failure must not replay a buyer-facing delivery message.
        if outcome is not None and payment_event and not outcome.repeated:
            try:
                from .notify_dispatcher import notify_new_order

                await notify_new_order(account_id, msg)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "New-order notification failed accountId=%d errorType=%s",
                    account_id,
                    type(exc).__name__,
                )
        return outcome
    except Exception as exc:
        logger.error(
            "自动发货处理异常 accountId=%d errorType=%s",
            account_id,
            type(exc).__name__,
        )
        raise


def _normalize_xianyu_user_id(value: object) -> str:
    """Compare Xianyu ids independently of the optional @goofish suffix."""
    return str(value or "").strip().lower().removesuffix("@goofish")


def _should_trigger_ai_auto_reply(
    msg: dict,
    seller_external_uid: str = "",
) -> tuple[bool, int, str, str]:
    """Return whether the message should enter AI auto-reply flow."""
    direction = str(msg.get("direction") or "IN").upper()
    content_type = msg.get("contentType", 1)
    try:
        content_type_int = int(content_type) if str(content_type).isdigit() else 1
    except (TypeError, ValueError):
        content_type_int = 1

    sender_user_id = str(msg.get("senderUserId") or "").strip()
    msg_content = str(msg.get("msgContent") or "").strip()
    sid = str(msg.get("sId") or msg.get("sid") or "").strip()
    reminder_content = str(msg.get("reminderContent") or "").strip()
    system_reminder_codes = {"PIC_DEAL_ERROR", "业务通知", "BIZ_NOTIFICATION"}
    looks_like_partial_buyer_text = (
        content_type_int == 1
        and not sender_user_id
        and bool(msg_content)
        and bool(sid)
        and reminder_content not in system_reminder_codes
    )
    is_system_message = (
        content_type_int != 1
        or (not sender_user_id and not looks_like_partial_buyer_text)
        or reminder_content in system_reminder_codes
    )
    is_seller_echo = bool(
        sender_user_id
        and seller_external_uid
        and _normalize_xianyu_user_id(sender_user_id) == _normalize_xianyu_user_id(seller_external_uid)
    )
    if is_seller_echo:
        logger.warning(
            "拦截 AI 自动回复回环：收到卖家自己发出的消息 senderPresent=%s sessionPresent=%s",
            bool(sender_user_id),
            bool(sid),
        )
    return direction == "IN" and not is_system_message and not is_seller_echo, content_type_int, sender_user_id, reminder_content


async def _load_ai_reply_delay_seconds() -> float:
    """Read the configured quiet period before one merged AI reply."""
    try:
        async with async_session() as db:
            config = await load_business_setting(db, AI_CS_SETTING_KEY)
        return float(config.get("replyDelaySeconds", 8))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "读取 AI 回复延迟失败，使用默认 8 秒 errorType=%s",
            type(exc).__name__,
        )
        return 8.0


async def _dispatch_ai_auto_reply_batch(
    account_id: int,
    messages: list[dict],
    seller_external_uid: str,
) -> None:
    """Invoke AI once after a conversation has been quiet for its configured delay."""
    if not messages:
        return
    latest = messages[-1]
    contents = [str(item.get("msgContent") or "").strip() for item in messages]
    contents = [content for content in contents if content]
    if not contents:
        await complete_deferred_messages(messages)
        return
    try:
        from .automation_runtime import (
            _build_ai_reply_command,
            process_incoming_message,
        )

        async with async_session() as reply_db:
            payload = {
                "accountId": account_id,
                "buyerId": latest.get("senderUserId"),
                "buyerName": latest.get("senderUserName"),
                "content": "\n".join(contents),
                "batchedContents": contents,
                "contentAlreadyPersisted": True,
                "messageType": latest.get("messageType") or "text",
                "pnmId": latest.get("pnmId"),
                "sourceMessageUids": [
                    str(item.get("_sourceMessageUid") or "").strip()
                    for item in messages
                    if str(item.get("_sourceMessageUid") or "").strip()
                ],
                "sId": latest.get("sId"),
                "latestMessageTime": latest.get("messageTime") or latest.get("message_time"),
                "goodsId": latest.get("xyGoodsId"),
                "itemTitle": latest.get("goodsTitle") or latest.get("reminderContent"),
                "sellerExternalUid": seller_external_uid,
            }
            command = _build_ai_reply_command(payload)
            await process_incoming_message(reply_db, payload)
            attempt_row = (
                await reply_db.execute(
                    text(
                        "SELECT state, retry_safe, last_error_code "
                        "FROM ai_auto_reply_attempt WHERE event_key = :event_key LIMIT 1"
                    ),
                    {"event_key": command.event_key},
                )
            ).mappings().first()
            await reply_db.commit()
    except Exception as exc:
        await fail_deferred_messages(messages, exc)
        logger.error(
            "AI 自动回复异常 accountId=%d errorType=%s",
            account_id,
            type(exc).__name__,
        )
        return
    if not attempt_row:
        await complete_deferred_messages(messages)
        return
    state = str(attempt_row.get("state") or "failed")
    retry_safe = bool(attempt_row.get("retry_safe"))
    error_code = str(attempt_row.get("last_error_code") or f"ai_{state}")
    if state == "confirmed":
        await complete_deferred_messages(messages)
    elif state == "unknown":
        await settle_deferred_messages(
            messages,
            state="unknown",
            retry_safe=False,
            error_code=error_code,
        )
    elif state == "failed" and not retry_safe:
        await settle_deferred_messages(
            messages,
            state="failed",
            retry_safe=False,
            error_code=error_code,
        )
    else:
        # generation/local-finalization failures and in-progress attempts may
        # safely re-enter the durable AI coordinator. Its message_sending/
        # unknown boundary prevents any blind buyer-facing resend.
        await settle_deferred_messages(
            messages,
            state="failed",
            retry_safe=True,
            error_code=error_code,
        )


ai_auto_reply_batcher = AiAutoReplyBatcher(
    _dispatch_ai_auto_reply_batch,
    delay_seconds=_load_ai_reply_delay_seconds,
)


async def _run_ai_auto_reply_after_message_saved(
    account_id: int,
    msg: dict,
    seller_external_uid: str,
) -> None:
    """Validate and enqueue a newly persisted inbound message for one AI turn."""
    should_trigger, content_type_int, sender_user_id, reminder_content = _should_trigger_ai_auto_reply(
        msg,
        seller_external_uid,
    )
    if not should_trigger:
        if str(msg.get("direction") or "IN").upper() == "IN":
            logger.info(
                "跳过 AI 自动回复（非买家文本）accountId=%d contentType=%s senderPresent=%s reminderPresent=%s",
                account_id,
                content_type_int,
                bool(sender_user_id),
                bool(reminder_content),
            )
        return
    ai_auto_reply_batcher.enqueue(account_id, msg, seller_external_uid)


async def execute_message_automation_claim(
    claim: OutboxClaim,
) -> DispatchDisposition:
    """Dispatch one leased branch without confirming deferred AI work early."""

    msg = await load_claim_message(claim)
    if msg is None:
        raise NonRetryableOutboxError("source_message_unavailable")
    if claim.branch == "delivery":
        outcome = await _run_delivery_after_message_saved(claim.account_id, msg)
        if outcome is None:
            return "completed"
        status = str(outcome.status or "")
        error_code = str(outcome.error_code or "delivery_dispatch_failed")
        if status == "unknown":
            raise UnknownOutboxError(error_code)
        if status == "failed":
            if outcome.retry_safe:
                raise RetryableOutboxError(error_code)
            raise NonRetryableOutboxError(error_code)
        if status == "in_progress":
            raise RetryableOutboxError("delivery_attempt_in_progress")
        return "completed"
    if claim.branch != "ai":
        raise NonRetryableOutboxError("unsupported_automation_branch")

    # Account identity is required to reject seller echoes safely.  A lookup
    # failure must be retried, never treated as if the packet came from a buyer.
    async with async_session() as db:
        row = await db.execute(
            text("SELECT id, external_uid FROM xianyu_account WHERE id = :aid LIMIT 1"),
            {"aid": claim.account_id},
        )
        account = row.mappings().first()
        if not account or not str(account.get("external_uid") or "").strip():
            raise NonRetryableOutboxError("seller_identity_unavailable")
        seller_external_uid = str(account["external_uid"]).strip()

    should_trigger, content_type, sender_user_id, reminder_content = (
        _should_trigger_ai_auto_reply(msg, seller_external_uid)
    )
    if not should_trigger:
        if str(msg.get("direction") or "IN").upper() == "IN":
            logger.info(
                "AI follow-up skipped accountId=%d contentType=%s senderPresent=%s reminderPresent=%s",
                claim.account_id,
                content_type,
                bool(sender_user_id),
                bool(reminder_content),
            )
        return "completed"

    if claim.attempt_count > 1:
        # A retry must not be swallowed by the in-memory recent-message cache
        # that already saw the first enqueue. Re-enter the durable AI attempt
        # directly; its persisted send boundary decides whether generation,
        # local finalization, or no action is safe.
        await _dispatch_ai_auto_reply_batch(
            claim.account_id,
            [msg],
            seller_external_uid,
        )
        return "deferred"

    try:
        queued = ai_auto_reply_batcher.enqueue(
            claim.account_id,
            msg,
            seller_external_uid,
        )
    except AiAutoReplyBatcherCapacityError as exc:
        raise RetryableOutboxError("ai_batch_capacity") from exc
    # A genuinely queued row stays processing until the quiet-period batch
    # handler has completed.  A replay rejected by the debounce is terminal.
    return "deferred" if queued else "completed"


async def on_message_callback(account_id: int, msg: dict) -> None:
    """
    Persist the message quickly and defer heavy side effects.

    This callback runs on the WebSocket receive loop, so it must return fast
    enough to avoid delaying the next sync cycle.
    """
    seller_external_uid = ""
    saved_message_id = None
    try:
        async with async_session() as db:
            try:
                seller_uid_row = await db.execute(
                    text("SELECT external_uid FROM xianyu_account WHERE id = :aid LIMIT 1"),
                    {"aid": account_id},
                )
                seller_external_uid = seller_uid_row.scalar_one_or_none() or ""
                saved_message_id = await save_chat_message(db, account_id, msg, seller_external_uid=seller_external_uid)
                if saved_message_id is not None:
                    source_message_uid = stable_chat_message_uid(
                        msg,
                        seller_external_uid,
                    )
                    await enqueue_message_automation(
                        db,
                        account_id=account_id,
                        chat_message_id=int(saved_message_id),
                        source_message_uid=source_message_uid,
                    )
                await db.commit()
                logger.debug(
                    "消息已保存 accountId=%d inserted=%s",
                    account_id,
                    saved_message_id is not None,
                )
            except Exception as exc:
                await db.rollback()
                logger.error(
                    "保存消息失败 accountId=%d errorType=%s",
                    account_id,
                    type(exc).__name__,
                )
                return
    except Exception as exc:
        logger.error("创建数据库会话失败 errorType=%s", type(exc).__name__)
        return

    # Only newly inserted messages may trigger side effects.  The database
    # returns None for a replay, which used to still create another AI request.
    if saved_message_id is None:
        logger.debug(
            "跳过重复消息后续处理 accountId=%d",
            account_id,
        )
        return

    msg["_persistedMessageId"] = int(saved_message_id)
    msg["_sourceMessageUid"] = stable_chat_message_uid(msg, seller_external_uid)

    # This is only a latency hint. Durability comes from the rows committed in
    # the same transaction as the message, so a crash here cannot lose work.
    notify_message_automation_worker()


async def auto_start_all() -> None:
    """Automatically start WebSocket connections for all logged-in accounts."""
    ai_auto_reply_batcher.start()
    ws_manager.set_message_callback(on_message_callback)

    try:
        from .automation_runtime import recover_ai_auto_reply_attempts

        async with async_session() as recovery_db:
            recovery = await recover_ai_auto_reply_attempts(recovery_db)
        logger.info(
            "AI 自动回复启动恢复完成 confirmed=%d unknown=%d pendingLocal=%d failed=%d",
            recovery["confirmed"],
            recovery["unknown"],
            recovery["message_sent"],
            recovery["failed"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "AI 自动回复启动恢复失败 errorType=%s",
            type(exc).__name__,
        )

    # Reconcile any downstream send boundary before expired outbox leases can
    # re-enter it. The poller then performs both startup catch-up and continuous
    # processing for newly committed messages.
    await start_message_automation_outbox_worker()

    try:
        async with async_session() as db:
            await db.execute(
                text("UPDATE xianyu_account_runtime SET ws_status = 0, online_status = 0 WHERE ws_status = 1 AND deleted = 0")
            )
            await db.commit()
            logger.info("已重置所有残留的 ws_status=1 状态")

            rows = await db.execute(text("""
                SELECT
                    a.id AS account_id,
                    a.external_uid AS unb,
                    auth.encrypted_cookie AS cookie_str,
                    auth.encrypted_token AS m_h5_tk
                FROM xianyu_account a
                JOIN xianyu_account_auth auth ON auth.account_id = a.id
                WHERE a.deleted = 0
                  AND auth.encrypted_cookie IS NOT NULL
                  AND auth.encrypted_cookie != ''
                ORDER BY a.id DESC
                LIMIT 50
            """))
            accounts = rows.mappings().all()

            if not accounts:
                logger.info("没有需要启动 WebSocket 的账号")
                return

            logger.info("自动启动 %d 个账号的 WebSocket 连接", len(accounts))

            for acct in accounts:
                account_id = acct["account_id"]
                unb = acct["unb"] or ""
                cookie_str = decrypt_cookie_if_needed(acct["cookie_str"] or "")
                m_h5_tk = decrypt_cookie_if_needed(acct["m_h5_tk"] or "") or ""

                if not cookie_str or not m_h5_tk:
                    logger.warning("账号 %d 缺少 Cookie 或 Token，跳过", account_id)
                    continue

                try:
                    await ws_manager.start_client(
                        account_id=account_id,
                        cookie_str=cookie_str,
                        m_h5_tk=m_h5_tk,
                        unb=unb,
                    )
                    logger.info("已启动 WebSocket: accountId=%d", account_id)
                except Exception as exc:
                    logger.error(
                        "启动 WebSocket 失败 accountId=%d errorType=%s",
                        account_id,
                        type(exc).__name__,
                    )

                await asyncio.sleep(1)
    except Exception as exc:
        logger.error("自动启动 WebSocket 异常 errorType=%s", type(exc).__name__)


async def stop_all() -> None:
    """Stop all WebSocket connections."""
    await stop_message_automation_outbox_worker()
    await ai_auto_reply_batcher.shutdown()
    await ws_manager.stop_all()
    logger.info("所有 WebSocket 连接已停止")
