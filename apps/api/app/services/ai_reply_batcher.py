"""Per-conversation batching and duplicate suppression for AI auto replies."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable


logger = logging.getLogger(__name__)

MessageBatchHandler = Callable[[int, list[dict], str], Awaitable[None]]
DelayResolver = Callable[[], float | Awaitable[float]]
ConversationKey = tuple[int, str, str]


class AiAutoReplyBatcherCapacityError(RuntimeError):
    """The bounded in-process quiet-period queue is temporarily full."""


@dataclass
class _PendingConversation:
    messages: list[dict] = field(default_factory=list)
    seller_external_uid: str = ""
    revision: int = 0
    task: asyncio.Task | None = None


class AiAutoReplyBatcher:
    """Accumulate a buyer's consecutive messages before one AI invocation.

    The batcher is intentionally in-process: the WebSocket callback and the AI
    sender run in the same API worker.  Database-level message de-duplication
    remains the authoritative guard across restarts; this class prevents a
    replayed callback from becoming a second request in the active worker.
    """

    def __init__(
        self,
        handler: MessageBatchHandler,
        delay_seconds: float | DelayResolver = 8,
        recent_ttl_seconds: float = 15 * 60,
        semantic_dedup_ttl_seconds: float = 90,
        max_batch_messages: int = 20,
        max_message_chars: int = 4_000,
        max_batch_chars: int = 12_000,
        max_pending_conversations: int = 1_024,
        max_recent_conversations: int = 4_096,
    ) -> None:
        self._handler = handler
        self._delay_seconds = delay_seconds
        self._recent_ttl_seconds = recent_ttl_seconds
        self._semantic_dedup_ttl_seconds = max(1.0, min(semantic_dedup_ttl_seconds, recent_ttl_seconds))
        self._max_batch_messages = max(1, min(int(max_batch_messages), 100))
        self._max_message_chars = max(1, min(int(max_message_chars), 20_000))
        self._max_batch_chars = max(1, min(int(max_batch_chars), 100_000))
        self._max_pending_conversations = max(
            1, min(int(max_pending_conversations), 10_000)
        )
        self._max_recent_conversations = max(
            self._max_pending_conversations,
            min(int(max_recent_conversations), 50_000),
        )
        self._pending: dict[ConversationKey, _PendingConversation] = {}
        self._recent_message_ids: dict[ConversationKey, dict[str, float]] = {}
        # Some IM replays arrive with a new PNM id for the same buyer text.
        # Keep a short, content-level replay guard in addition to the stable
        # PNM guard.  It deliberately expires much sooner so a buyer can still
        # repeat a real question later in the conversation.
        self._recent_semantic_messages: dict[ConversationKey, dict[str, float]] = {}
        self._recent_conversation_touched: dict[ConversationKey, float] = {}
        self._closing = False

    def enqueue(self, account_id: int, message: dict, seller_external_uid: str) -> bool:
        """Queue an inserted inbound message. Returns False for a replay."""
        key = self._conversation_key(account_id, message)
        if not key:
            return False

        fingerprint = self._message_fingerprint(message)
        now = time.monotonic()
        if self._closing:
            raise AiAutoReplyBatcherCapacityError("AI batcher is shutting down")
        self._prune_recent_conversations(now)
        recent = self._recent_message_ids.get(key, {})
        self._prune_recent(recent, now)
        if fingerprint in recent:
            self._recent_conversation_touched[key] = now
            logger.info(
                "AI 自动回复跳过重复回调 accountId=%d",
                account_id,
            )
            return False

        semantic_fingerprint = self._semantic_fingerprint(message)
        recent_semantic = self._recent_semantic_messages.get(key, {})
        self._prune_recent(recent_semantic, now, self._semantic_dedup_ttl_seconds)
        if semantic_fingerprint in recent_semantic:
            self._recent_conversation_touched[key] = now
            logger.warning(
                "AI 自动回复跳过同内容重放 accountId=%d",
                account_id,
            )
            return False
        if key not in self._pending and len(self._pending) >= self._max_pending_conversations:
            raise AiAutoReplyBatcherCapacityError("AI batch queue is full")

        self._recent_conversation_touched[key] = now
        recent = self._recent_message_ids.setdefault(key, recent)
        recent[fingerprint] = now
        recent_semantic = self._recent_semantic_messages.setdefault(
            key,
            recent_semantic,
        )
        recent_semantic[semantic_fingerprint] = now

        state = self._pending.setdefault(key, _PendingConversation())
        self._prune_recent_conversations(now)
        bounded_message = dict(message)
        bounded_message["msgContent"] = str(
            message.get("msgContent") or message.get("msg_content") or ""
        )[: self._max_message_chars]
        state.messages.append(bounded_message)
        state.messages = state.messages[-self._max_batch_messages :]
        # Allocate the prompt budget newest-first so the buyer's latest
        # question is preserved when a noisy conversation exceeds the cap.
        remaining = self._max_batch_chars
        bounded_reversed: list[dict] = []
        for item in reversed(state.messages):
            if remaining <= 0:
                break
            item_copy = dict(item)
            item_content = str(item_copy.get("msgContent") or "")
            item_copy["msgContent"] = item_content[:remaining]
            remaining -= len(item_copy["msgContent"])
            bounded_reversed.append(item_copy)
        state.messages = list(reversed(bounded_reversed))
        state.seller_external_uid = seller_external_uid or state.seller_external_uid
        state.revision += 1

        if state.task is None or state.task.done():
            state.task = asyncio.create_task(
                self._run(key, state),
                name="ai-reply.quiet-period",
            )
        return True

    def start(self) -> None:
        """Open the batcher for one application lifespan."""

        if self._pending:
            raise RuntimeError("cannot start AI batcher with pending conversations")
        self._closing = False

    async def shutdown(self) -> None:
        """Reject new work, cancel owned timers, and clear transient PII."""

        self._closing = True
        tasks = tuple(
            state.task
            for state in self._pending.values()
            if state.task is not None and not state.task.done()
        )
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.clear()
        self._recent_message_ids.clear()
        self._recent_semantic_messages.clear()
        self._recent_conversation_touched.clear()

    async def drain(self) -> None:
        """Wait for currently scheduled batches; useful for deterministic tests."""
        while True:
            tasks = [state.task for state in self._pending.values() if state.task and not state.task.done()]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=False)

    async def _run(self, key: ConversationKey, state: _PendingConversation) -> None:
        try:
            while True:
                observed_revision = state.revision
                delay = await self._resolve_delay_seconds()
                if delay:
                    await asyncio.sleep(delay)

                # A later buyer message resets the quiet period so all related
                # messages are submitted to the model as one conversation turn.
                if state.revision != observed_revision:
                    continue

                batch = list(state.messages)
                state.messages.clear()
                if batch:
                    await self._handler(key[0], batch, state.seller_external_uid)

                if not state.messages:
                    self._pending.pop(key, None)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._pending.pop(key, None)
            logger.error(
                "AI 自动回复批处理任务异常 errorType=%s",
                type(exc).__name__,
            )

    async def _resolve_delay_seconds(self) -> float:
        value = self._delay_seconds
        if callable(value):
            value = value()
            if inspect.isawaitable(value):
                value = await value
        try:
            return max(0.0, min(float(value), 120.0))
        except (TypeError, ValueError):
            return 8.0

    @staticmethod
    def _conversation_key(account_id: int, message: dict) -> ConversationKey | None:
        sid = str(message.get("sId") or message.get("sid") or "").strip()
        buyer_id = str(message.get("senderUserId") or message.get("sender_user_id") or "").strip()
        if not account_id or not sid or not buyer_id:
            return None
        return account_id, sid, buyer_id

    @staticmethod
    def _message_fingerprint(message: dict) -> str:
        pnm_id = str(message.get("pnmId") or message.get("pnm_id") or "").strip()
        if pnm_id:
            raw = f"pnm:{pnm_id}"
        else:
            raw = "|".join([
                str(message.get("sId") or message.get("sid") or "").strip(),
                str(message.get("senderUserId") or message.get("sender_user_id") or "").strip(),
                str(message.get("messageTime") or message.get("message_time") or "").strip(),
                str(message.get("msgContent") or message.get("msg_content") or "").strip(),
            ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _semantic_fingerprint(message: dict) -> str:
        """Identify a replay even when the upstream PNM id changes."""
        content = " ".join(str(
            message.get("msgContent") or message.get("msg_content") or ""
        ).split())
        raw = "|".join([
            str(message.get("sId") or message.get("sid") or "").strip(),
            str(message.get("senderUserId") or message.get("sender_user_id") or "").strip(),
            content,
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _prune_recent(
        self,
        recent: dict[str, float],
        now: float,
        ttl_seconds: float | None = None,
    ) -> None:
        ttl = self._recent_ttl_seconds if ttl_seconds is None else ttl_seconds
        expired = [fingerprint for fingerprint, seen_at in recent.items() if now - seen_at >= ttl]
        for fingerprint in expired:
            recent.pop(fingerprint, None)

    def _prune_recent_conversations(self, now: float) -> None:
        expired = [
            key
            for key, touched_at in self._recent_conversation_touched.items()
            if key not in self._pending
            and now - touched_at >= self._recent_ttl_seconds
        ]
        for key in expired:
            self._drop_recent_conversation(key)

        overflow = (
            len(self._recent_conversation_touched)
            - self._max_recent_conversations
        )
        if overflow <= 0:
            return
        eviction_candidates = sorted(
            (
                (touched_at, key)
                for key, touched_at in self._recent_conversation_touched.items()
                if key not in self._pending
            ),
            key=lambda item: (item[0], item[1]),
        )
        for _touched_at, key in eviction_candidates[:overflow]:
            self._drop_recent_conversation(key)

    def _drop_recent_conversation(self, key: ConversationKey) -> None:
        self._recent_conversation_touched.pop(key, None)
        self._recent_message_ids.pop(key, None)
        self._recent_semantic_messages.pop(key, None)
