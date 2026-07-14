"""Durable single-flight state machine for AI auto-reply delivery.

The model call is retryable, but sending a buyer-facing message is an external
side effect.  This module commits ``message_sending`` before crossing that
boundary.  A process crash or ambiguous acknowledgement after that point is
quarantined as ``unknown`` and is never automatically sent again.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal, Protocol

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.secret_store import decrypt_secret, encrypt_secret
from ..models.entities import AiAutoReplyAttempt, AiAutoReplyDailyQuota


logger = logging.getLogger(__name__)

AI_REPLY_SECRET_PURPOSE = "ai.auto_reply.content"
MAX_AI_REPLY_CHARS = 8_000
_SAFE_CODE_RE = re.compile(r"^[a-z0-9_]{1,64}$")

AttemptAction = Literal[
    "generate",
    "send_message",
    "finalize_local",
    "in_progress",
    "return",
]
AttemptState = Literal[
    "pending",
    "generating",
    "message_sending",
    "message_sent",
    "confirmed",
    "failed",
    "unknown",
]
SendStatus = Literal["confirmed", "failed", "unknown"]


def _now() -> dt.datetime:
    # MySQL DATETIME columns and the rest of this service use deployment-local
    # naive timestamps (the Compose deployment pins Asia/Shanghai).  Mixing a
    # naive UTC value with MySQL NOW() would extend every lease by eight hours.
    return dt.datetime.now()


def _safe_code(value: object, fallback: str) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if _SAFE_CODE_RE.fullmatch(normalized) else fallback


def _error_message(code: str) -> str:
    return {
        "model_generation_failed": "模型生成失败，尚未向买家发送消息，可安全重试",
        "model_reply_empty": "模型未生成可发送内容，尚未向买家发送消息，可安全重试",
        "model_reply_too_long": "模型回复超过安全长度限制，尚未向买家发送消息",
        "websocket_unavailable": "账号消息连接不可用，尚未向买家发送消息，可安全重试",
        "websocket_not_registered": "账号消息连接尚未注册，尚未向买家发送消息，可安全重试",
        "message_rejected": "平台明确拒绝消息，本次未送达，可在排查后重试",
        "message_ack_unknown": "发送结果未确认，请先在闲鱼 App 核对；系统不会自动重发",
        "message_result_unknown": "发送边界发生异常，结果未知；系统不会自动重发",
        "local_message_persist_failed": "平台已确认发送，但本地消息落库失败；后续只补本地状态",
        "reply_decryption_failed": "平台已确认发送，但本地回复内容无法解密；系统不会重发",
        "manual_mode": "当前为人工模式，尚未向买家发送 AI 回复",
        "outside_work_hours": "当前不在配置时区的工作时段，尚未向买家发送 AI 回复",
        "human_intervention_active": "同一会话处于人工接管暂停窗口，尚未发送 AI 回复",
        "handoff_keyword_matched": "买家消息命中转人工关键词，AI 已停答并留给人工处理",
        "blacklist_keyword_matched": "买家消息命中黑名单关键词，AI 已停答并留给人工处理",
        "invalid_reply_mode": "AI 客服接待模式无效，系统已停止自动回复",
        "invalid_policy_timezone": "AI 客服策略时区无效，系统已停止自动回复",
        "invalid_daily_reply_limit": "AI 客服每日额度无效，系统已停止自动回复",
        "invalid_work_hours": "AI 客服工作时段无效，系统已停止自动回复",
        "invalid_human_pause_window": "人工接管暂停时长无效，系统已停止自动回复",
        "invalid_conversation_identity": "会话身份不完整，系统已停止自动回复",
        "invalid_policy_boolean": "AI 客服策略开关格式无效，系统已停止自动回复",
        "policy_check_unavailable": "AI 客服运行策略暂不可核验，尚未向买家发送消息",
    }.get(code, "AI 自动回复状态已更新")


@dataclass(frozen=True)
class AiAutoReplyCommand:
    event_key: str
    request_digest: str
    account_id: int
    source_message_digest: str
    session_id: str
    peer_id: str
    goods_id: str = ""
    seller_external_uid: str = ""
    quota_date: dt.date | None = None
    quota_limit: int = 0
    policy_timezone: str = ""

    def validate(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{64}", self.event_key):
            raise ValueError("event_key must be a lowercase SHA-256 digest")
        if not re.fullmatch(r"[a-f0-9]{64}", self.request_digest):
            raise ValueError("request_digest must be a lowercase SHA-256 digest")
        if not re.fullmatch(r"[a-f0-9]{64}", self.source_message_digest):
            raise ValueError("source_message_digest must be a lowercase SHA-256 digest")
        if int(self.account_id or 0) <= 0:
            raise ValueError("account_id is required")
        if not str(self.session_id or "").strip():
            raise ValueError("session_id is required")
        if not str(self.peer_id or "").strip():
            raise ValueError("peer_id is required")
        if self.quota_date is not None:
            if not 1 <= int(self.quota_limit or 0) <= 10_000:
                raise ValueError("quota_limit must be between 1 and 10000")
            if not str(self.policy_timezone or "").strip():
                raise ValueError("policy_timezone is required with quota_date")


@dataclass(frozen=True)
class AiAutoReplyAttemptLease:
    attempt_id: int
    event_key: str
    state: AttemptState
    action: AttemptAction
    lease_token: str | None
    retry_safe: bool
    repeated: bool = False
    error_code: str | None = None
    local_message_id: int | None = None
    reply_text: str = field(repr=False, default="")


@dataclass(frozen=True)
class AiAutoReplySendResult:
    status: SendStatus
    error_code: str | None = None
    retry_safe: bool = False

    @classmethod
    def confirmed(cls) -> "AiAutoReplySendResult":
        return cls(status="confirmed", retry_safe=False)

    @classmethod
    def failed(
        cls,
        error_code: str = "message_rejected",
        *,
        retry_safe: bool = True,
    ) -> "AiAutoReplySendResult":
        return cls(
            status="failed",
            error_code=_safe_code(error_code, "message_rejected"),
            retry_safe=bool(retry_safe),
        )

    @classmethod
    def unknown(
        cls,
        error_code: str = "message_ack_unknown",
    ) -> "AiAutoReplySendResult":
        return cls(
            status="unknown",
            error_code=_safe_code(error_code, "message_ack_unknown"),
            retry_safe=False,
        )


@dataclass(frozen=True)
class AiAutoReplyOutcome:
    attempt_id: int
    event_key: str
    status: AttemptState | Literal["in_progress"]
    retry_safe: bool
    repeated: bool
    error_code: str | None = None
    local_message_id: int | None = None


class AiAutoReplyAttemptError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = _safe_code(code, "ai_auto_reply_attempt_error")


class AiAutoReplyQuotaExceeded(AiAutoReplyAttemptError):
    """Raised before model generation when the local-day limit is occupied."""

    def __init__(self) -> None:
        super().__init__(
            "daily_quota_exhausted",
            "AI 自动回复已达到配置时区内的每日上限，本次未调用模型或发送消息",
        )


class AiAutoReplyGenerationError(RuntimeError):
    """Safe, non-provider-specific generation failure for the orchestrator."""

    def __init__(self, code: str = "model_generation_failed") -> None:
        self.code = _safe_code(code, "model_generation_failed")
        super().__init__(_error_message(self.code))


class AiAutoReplyAttemptStore(Protocol):
    async def claim(self, command: AiAutoReplyCommand) -> AiAutoReplyAttemptLease: ...

    async def prepare_message(
        self,
        lease: AiAutoReplyAttemptLease,
        reply_text: str,
    ) -> AiAutoReplyAttemptLease: ...

    async def mark_generation_failed(
        self,
        lease: AiAutoReplyAttemptLease,
        *,
        error_code: str,
    ) -> AiAutoReplyAttemptLease: ...

    async def mark_send_failed(
        self,
        lease: AiAutoReplyAttemptLease,
        result: AiAutoReplySendResult,
    ) -> AiAutoReplyAttemptLease: ...

    async def mark_unknown(
        self,
        lease: AiAutoReplyAttemptLease,
        result: AiAutoReplySendResult,
    ) -> AiAutoReplyAttemptLease: ...

    async def mark_message_confirmed(
        self,
        lease: AiAutoReplyAttemptLease,
    ) -> AiAutoReplyAttemptLease: ...

    async def mark_local_confirmed(
        self,
        lease: AiAutoReplyAttemptLease,
        *,
        local_message_id: int | None,
    ) -> AiAutoReplyAttemptLease: ...

    async def mark_local_failed(
        self,
        lease: AiAutoReplyAttemptLease,
        *,
        error_code: str,
    ) -> AiAutoReplyAttemptLease: ...


GenerateReply = Callable[[], Awaitable[str]]
SendReply = Callable[[str], Awaitable[AiAutoReplySendResult]]
SaveReply = Callable[[str, str], Awaitable[int | None]]


class AiAutoReplyRuntime:
    """Execute one durable AI reply attempt through its public callbacks."""

    def __init__(self, store: AiAutoReplyAttemptStore) -> None:
        self._store = store

    async def execute(
        self,
        command: AiAutoReplyCommand,
        generate_reply: GenerateReply,
        send_reply: SendReply,
        save_reply: SaveReply,
    ) -> AiAutoReplyOutcome:
        command.validate()
        lease = await self._store.claim(command)

        if lease.action in {"return", "in_progress"}:
            return self._outcome(lease)
        if lease.action == "finalize_local":
            return await self._finalize_local(lease, save_reply)
        if lease.action != "generate":
            raise AiAutoReplyAttemptError(
                "attempt_action_invalid",
                "AI 自动回复状态无效，系统未执行外部发送",
            )

        try:
            reply_text = str(await generate_reply() or "").strip()
        except AiAutoReplyGenerationError as exc:
            lease = await self._store.mark_generation_failed(
                lease,
                error_code=exc.code,
            )
            return self._outcome(lease)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AI reply generation failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            lease = await self._store.mark_generation_failed(
                lease,
                error_code="model_generation_failed",
            )
            return self._outcome(lease)

        if not reply_text:
            lease = await self._store.mark_generation_failed(
                lease,
                error_code="model_reply_empty",
            )
            return self._outcome(lease)
        if len(reply_text) > MAX_AI_REPLY_CHARS:
            lease = await self._store.mark_generation_failed(
                lease,
                error_code="model_reply_too_long",
            )
            return self._outcome(lease)

        try:
            lease = await self._store.prepare_message(lease, reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "AI reply prepare failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            try:
                lease = await self._store.mark_generation_failed(
                    lease,
                    error_code="reply_persist_failed",
                )
            except Exception:  # noqa: BLE001
                logger.error(
                    "AI reply prepare recovery failed attemptId=%d",
                    lease.attempt_id,
                )
            return self._outcome(lease)

        try:
            send_result = await send_reply(reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "AI reply send result unknown attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            send_result = AiAutoReplySendResult.unknown("message_result_unknown")

        if not isinstance(send_result, AiAutoReplySendResult):
            send_result = AiAutoReplySendResult.unknown("message_result_unknown")
        if send_result.status == "unknown":
            lease = await self._store.mark_unknown(lease, send_result)
            return self._outcome(lease)
        if send_result.status == "failed":
            lease = await self._store.mark_send_failed(lease, send_result)
            return self._outcome(lease)

        try:
            lease = await self._store.mark_message_confirmed(lease)
        except Exception as exc:  # noqa: BLE001
            # The external platform acknowledged the message but the durable
            # confirmation write failed.  Never attempt another send: the
            # persisted message_sending state is quarantined on lease expiry.
            logger.critical(
                "AI reply ACK persistence uncertain attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            return AiAutoReplyOutcome(
                attempt_id=lease.attempt_id,
                event_key=lease.event_key,
                status="unknown",
                retry_safe=False,
                repeated=lease.repeated,
                error_code="message_confirmation_persist_unknown",
            )
        return await self._finalize_local(lease, save_reply)

    async def _finalize_local(
        self,
        lease: AiAutoReplyAttemptLease,
        save_reply: SaveReply,
    ) -> AiAutoReplyOutcome:
        if not lease.reply_text:
            lease = await self._store.mark_local_failed(
                lease,
                error_code="reply_decryption_failed",
            )
            return self._outcome(lease)
        local_key = f"ai-auto-reply:{lease.event_key}"
        try:
            local_message_id = await save_reply(lease.reply_text, local_key)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "AI reply local finalize failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            lease = await self._store.mark_local_failed(
                lease,
                error_code="local_message_persist_failed",
            )
            return self._outcome(lease)
        lease = await self._store.mark_local_confirmed(
            lease,
            local_message_id=local_message_id,
        )
        return self._outcome(lease)

    @staticmethod
    def _outcome(lease: AiAutoReplyAttemptLease) -> AiAutoReplyOutcome:
        status: AttemptState | Literal["in_progress"] = (
            "in_progress" if lease.action == "in_progress" else lease.state
        )
        return AiAutoReplyOutcome(
            attempt_id=lease.attempt_id,
            event_key=lease.event_key,
            status=status,
            retry_safe=lease.retry_safe,
            repeated=lease.repeated,
            error_code=lease.error_code,
            local_message_id=lease.local_message_id,
        )


class SqlAiAutoReplyAttemptStore:
    """MySQL-backed attempt store with finite leases and fail-closed recovery."""

    def __init__(self, db: AsyncSession, *, lease_seconds: int = 120) -> None:
        self._db = db
        self._lease_seconds = max(30, min(int(lease_seconds), 600))

    async def claim(self, command: AiAutoReplyCommand) -> AiAutoReplyAttemptLease:
        command.validate()
        attempt = await self._find(command.event_key)
        if attempt is None:
            # End the non-locking discovery transaction before reserving the
            # account/day counter. This avoids a missing-key next-key lock from
            # deadlocking two concurrent deliveries of the same event.
            await self._db.rollback()
            return await self._create(command)
        attempt = await self._find_locked(command.event_key)
        if attempt is None:
            await self._db.rollback()
            return await self._create(command)
        self._validate_payload(attempt, command)
        return await self._claim_existing(attempt, command)

    async def _create(self, command: AiAutoReplyCommand) -> AiAutoReplyAttemptLease:
        now = _now()
        if command.quota_date is not None:
            try:
                await self._reserve_quota(command)
            except AiAutoReplyQuotaExceeded:
                await self._db.rollback()
                # A competing replay of this exact event may have consumed the
                # only slot while creating the single-flight attempt. Return
                # that attempt instead of misreporting a quota denial.
                existing = await self._find_locked(command.event_key)
                if existing is not None:
                    self._validate_payload(existing, command)
                    return await self._claim_existing(existing, command)
                await self._db.rollback()
                raise
            except Exception:
                await self._db.rollback()
                raise
        attempt = AiAutoReplyAttempt(
            event_key=command.event_key,
            account_id=command.account_id,
            source_message_digest=command.source_message_digest,
            request_digest=command.request_digest,
            session_id=command.session_id[:200],
            peer_id=command.peer_id[:200],
            goods_id=command.goods_id[:200] or None,
            seller_external_uid=command.seller_external_uid[:200] or None,
            state="generating",
            retry_scope="generation",
            retry_safe=1,
            attempt_count=1,
            lease_token=uuid.uuid4().hex,
            lease_until=now + dt.timedelta(seconds=self._lease_seconds),
            generation_started_at=now,
            quota_date=command.quota_date,
            quota_status="reserved" if command.quota_date is not None else None,
            policy_timezone=(command.policy_timezone[:64] or None),
        )
        self._db.add(attempt)
        try:
            await self._db.flush()
            await self._db.commit()
            return self._lease(attempt, action="generate")
        except IntegrityError:
            await self._db.rollback()
            existing = await self._find_locked(command.event_key)
            if existing is None:
                raise
            self._validate_payload(existing, command)
            return await self._claim_existing(existing, command)

    async def _claim_existing(
        self,
        attempt: AiAutoReplyAttempt,
        command: AiAutoReplyCommand,
    ) -> AiAutoReplyAttemptLease:
        state = str(attempt.state or "pending")
        now = _now()
        lease_active = bool(attempt.lease_until and attempt.lease_until > now)

        if state in {"confirmed", "unknown"}:
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)
        if state == "message_sending":
            if lease_active:
                await self._db.commit()
                return self._lease(attempt, action="in_progress", repeated=True)
            attempt.state = "unknown"
            attempt.retry_scope = "message"
            attempt.retry_safe = 0
            attempt.last_error_code = "message_result_unknown_after_recovery"
            attempt.error_message = _error_message("message_ack_unknown")
            await self._consume_quota(attempt)
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)
        if state == "message_sent":
            if not bool(attempt.retry_safe):
                await self._db.commit()
                return self._lease(attempt, action="return", repeated=True)
            if lease_active:
                await self._db.commit()
                return self._lease(attempt, action="in_progress", repeated=True)
            self._acquire(attempt, retry_scope="local")
            await self._db.commit()
            return self._lease(
                attempt,
                action="finalize_local",
                repeated=True,
                decrypt_reply=True,
            )
        if state == "generating" and lease_active:
            await self._db.commit()
            return self._lease(attempt, action="in_progress", repeated=True)
        if state == "failed" and not bool(attempt.retry_safe):
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)

        # pending, retry-safe failed, or expired generation: no external send
        # has started, so another finite lease may safely regenerate.
        if str(attempt.quota_status or "") not in {"reserved", "consumed"}:
            if command.quota_date is not None:
                try:
                    await self._reserve_quota(command)
                except Exception:
                    await self._db.rollback()
                    raise
                attempt.quota_date = command.quota_date
                attempt.quota_status = "reserved"
                attempt.policy_timezone = command.policy_timezone[:64]
        attempt.state = "generating"
        attempt.retry_scope = "generation"
        attempt.retry_safe = 1
        attempt.attempt_count = int(attempt.attempt_count or 0) + 1
        attempt.generation_started_at = now
        attempt.last_error_code = None
        attempt.error_message = None
        attempt.reply_digest = None
        attempt.encrypted_reply = None
        self._acquire(attempt, retry_scope="generation")
        await self._db.commit()
        return self._lease(attempt, action="generate", repeated=True)

    async def prepare_message(
        self,
        lease: AiAutoReplyAttemptLease,
        reply_text: str,
    ) -> AiAutoReplyAttemptLease:
        attempt = await self._locked_attempt(lease)
        if str(attempt.state) != "generating":
            raise AiAutoReplyAttemptError(
                "attempt_state_conflict",
                "AI 自动回复生成租约状态已变化，系统未执行外部发送",
            )
        ciphertext = encrypt_secret(reply_text, purpose=AI_REPLY_SECRET_PURPOSE)
        if not ciphertext:
            raise AiAutoReplyAttemptError(
                "reply_encryption_failed",
                "AI 回复无法安全持久化，系统未执行外部发送",
            )
        now = _now()
        attempt.encrypted_reply = ciphertext
        attempt.reply_digest = hashlib.sha256(reply_text.encode("utf-8")).hexdigest()
        attempt.state = "message_sending"
        attempt.retry_scope = "message"
        attempt.retry_safe = 0
        attempt.message_started_at = now
        attempt.last_error_code = None
        attempt.error_message = None
        await self._db.commit()
        return self._lease(attempt, action="send_message", reply_text=reply_text)

    async def mark_generation_failed(
        self,
        lease: AiAutoReplyAttemptLease,
        *,
        error_code: str,
    ) -> AiAutoReplyAttemptLease:
        attempt = await self._locked_attempt(lease)
        code = _safe_code(error_code, "model_generation_failed")
        attempt.state = "failed"
        non_retryable_policy_denials = {
            "manual_mode",
            "human_intervention_active",
            "handoff_keyword_matched",
            "blacklist_keyword_matched",
        }
        attempt.retry_scope = (
            None if code in non_retryable_policy_denials else "generation"
        )
        attempt.retry_safe = 0 if code in non_retryable_policy_denials else 1
        attempt.last_error_code = code
        attempt.error_message = _error_message(code)
        attempt.encrypted_reply = None
        attempt.reply_digest = None
        await self._release_quota_reservation(attempt)
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_send_failed(
        self,
        lease: AiAutoReplyAttemptLease,
        result: AiAutoReplySendResult,
    ) -> AiAutoReplyAttemptLease:
        attempt = await self._locked_attempt(lease)
        code = _safe_code(result.error_code, "message_rejected")
        attempt.state = "failed"
        attempt.retry_scope = "message" if result.retry_safe else None
        attempt.retry_safe = 1 if result.retry_safe else 0
        attempt.last_error_code = code
        attempt.error_message = _error_message(code)
        attempt.encrypted_reply = None
        attempt.reply_digest = None
        # A ``failed`` send result is reserved for an explicit pre-delivery
        # rejection. Ambiguous transport/ACK outcomes use ``unknown`` and are
        # deliberately not released.
        await self._release_quota_reservation(attempt)
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_unknown(
        self,
        lease: AiAutoReplyAttemptLease,
        result: AiAutoReplySendResult,
    ) -> AiAutoReplyAttemptLease:
        attempt = await self._locked_attempt(lease)
        code = _safe_code(result.error_code, "message_ack_unknown")
        attempt.state = "unknown"
        attempt.retry_scope = "message"
        attempt.retry_safe = 0
        attempt.last_error_code = code
        attempt.error_message = _error_message(code)
        # Unknown attempts are never locally replayed, so retaining the buyer
        # message body would add privacy risk without recovery value.
        attempt.encrypted_reply = None
        await self._consume_quota(attempt)
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_message_confirmed(
        self,
        lease: AiAutoReplyAttemptLease,
    ) -> AiAutoReplyAttemptLease:
        attempt = await self._locked_attempt(lease)
        if str(attempt.state) != "message_sending":
            raise AiAutoReplyAttemptError(
                "attempt_state_conflict",
                "AI 自动回复发送状态已变化，系统不会重复发送",
            )
        attempt.state = "message_sent"
        attempt.retry_scope = "local"
        attempt.retry_safe = 1
        attempt.message_confirmed_at = attempt.message_confirmed_at or _now()
        attempt.last_error_code = None
        attempt.error_message = None
        await self._consume_quota(attempt)
        await self._db.commit()
        return self._lease(
            attempt,
            action="finalize_local",
            reply_text=lease.reply_text,
        )

    async def mark_local_confirmed(
        self,
        lease: AiAutoReplyAttemptLease,
        *,
        local_message_id: int | None,
    ) -> AiAutoReplyAttemptLease:
        attempt = await self._locked_attempt(lease)
        if str(attempt.state) != "message_sent":
            raise AiAutoReplyAttemptError(
                "attempt_state_conflict",
                "AI 自动回复本地确认状态已变化",
            )
        attempt.state = "confirmed"
        attempt.retry_scope = None
        attempt.retry_safe = 0
        attempt.local_message_id = local_message_id
        attempt.local_confirmed_at = attempt.local_confirmed_at or _now()
        attempt.last_error_code = None
        attempt.error_message = None
        attempt.encrypted_reply = None
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_local_failed(
        self,
        lease: AiAutoReplyAttemptLease,
        *,
        error_code: str,
    ) -> AiAutoReplyAttemptLease:
        attempt = await self._locked_attempt(lease)
        code = _safe_code(error_code, "local_message_persist_failed")
        attempt.state = "message_sent"
        irrecoverable = code == "reply_decryption_failed"
        attempt.retry_scope = None if irrecoverable else "local"
        attempt.retry_safe = 0 if irrecoverable else 1
        attempt.last_error_code = code
        attempt.error_message = _error_message(code)
        if irrecoverable:
            attempt.encrypted_reply = None
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def _find_locked(self, event_key: str) -> AiAutoReplyAttempt | None:
        return (
            await self._db.execute(
                select(AiAutoReplyAttempt)
                .where(AiAutoReplyAttempt.event_key == event_key)
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _find(self, event_key: str) -> AiAutoReplyAttempt | None:
        return (
            await self._db.execute(
                select(AiAutoReplyAttempt).where(
                    AiAutoReplyAttempt.event_key == event_key
                )
            )
        ).scalar_one_or_none()

    async def _ensure_quota_row(self, command: AiAutoReplyCommand) -> None:
        if command.quota_date is None:
            return
        dialect = str(self._db.get_bind().dialect.name)
        params = {
            "account_id": int(command.account_id),
            "quota_date": command.quota_date,
        }
        if dialect == "mysql":
            statement = text(
                """
                INSERT INTO ai_auto_reply_daily_quota (
                    account_id, quota_date, occupied_count, consumed_count,
                    released_count, created_time, updated_time
                ) VALUES (
                    :account_id, :quota_date, 0, 0, 0, NOW(), NOW()
                )
                ON DUPLICATE KEY UPDATE account_id = account_id
                """
            )
        elif dialect == "sqlite":
            statement = text(
                """
                INSERT OR IGNORE INTO ai_auto_reply_daily_quota (
                    account_id, quota_date, occupied_count, consumed_count,
                    released_count, created_time, updated_time
                ) VALUES (
                    :account_id, :quota_date, 0, 0, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        else:
            raise AiAutoReplyAttemptError(
                "quota_database_unsupported",
                "当前数据库不支持 AI 自动回复持久额度",
            )
        await self._db.execute(statement, params)

    async def _reserve_quota(self, command: AiAutoReplyCommand) -> None:
        if command.quota_date is None:
            return
        await self._ensure_quota_row(command)
        result = await self._db.execute(
            update(AiAutoReplyDailyQuota)
            .where(
                AiAutoReplyDailyQuota.account_id == int(command.account_id),
                AiAutoReplyDailyQuota.quota_date == command.quota_date,
                AiAutoReplyDailyQuota.occupied_count < int(command.quota_limit),
            )
            .values(
                occupied_count=AiAutoReplyDailyQuota.occupied_count + 1,
                updated_time=_now(),
            )
        )
        if int(result.rowcount or 0) != 1:
            raise AiAutoReplyQuotaExceeded()

    async def _release_quota_reservation(
        self,
        attempt: AiAutoReplyAttempt,
    ) -> None:
        if (
            attempt.quota_date is None
            or str(attempt.quota_status or "") not in {"reserved", "consumed"}
        ):
            return
        result = await self._db.execute(
            update(AiAutoReplyDailyQuota)
            .where(
                AiAutoReplyDailyQuota.account_id == int(attempt.account_id),
                AiAutoReplyDailyQuota.quota_date == attempt.quota_date,
                AiAutoReplyDailyQuota.occupied_count > 0,
            )
            .values(
                occupied_count=AiAutoReplyDailyQuota.occupied_count - 1,
                released_count=AiAutoReplyDailyQuota.released_count + 1,
                updated_time=_now(),
            )
        )
        if int(result.rowcount or 0) != 1:
            raise AiAutoReplyAttemptError(
                "quota_counter_inconsistent",
                "AI 自动回复额度状态不一致，系统已停止本次状态变更",
            )
        attempt.quota_status = "released"

    async def _consume_quota(self, attempt: AiAutoReplyAttempt) -> None:
        if (
            attempt.quota_date is None
            or str(attempt.quota_status or "") != "reserved"
        ):
            return
        result = await self._db.execute(
            update(AiAutoReplyDailyQuota)
            .where(
                AiAutoReplyDailyQuota.account_id == int(attempt.account_id),
                AiAutoReplyDailyQuota.quota_date == attempt.quota_date,
            )
            .values(
                consumed_count=AiAutoReplyDailyQuota.consumed_count + 1,
                updated_time=_now(),
            )
        )
        if int(result.rowcount or 0) != 1:
            raise AiAutoReplyAttemptError(
                "quota_counter_inconsistent",
                "AI 自动回复额度状态不一致，系统已停止本次状态变更",
            )
        attempt.quota_status = "consumed"

    async def _locked_attempt(
        self,
        lease: AiAutoReplyAttemptLease,
    ) -> AiAutoReplyAttempt:
        attempt = (
            await self._db.execute(
                select(AiAutoReplyAttempt)
                .where(AiAutoReplyAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise AiAutoReplyAttemptError(
                "attempt_not_found",
                "AI 自动回复尝试不存在，系统未执行外部发送",
            )
        if not lease.lease_token or attempt.lease_token != lease.lease_token:
            await self._db.rollback()
            raise AiAutoReplyAttemptError(
                "attempt_lease_lost",
                "AI 自动回复执行权已变化，系统不会重复发送",
            )
        return attempt

    @staticmethod
    def _validate_payload(
        attempt: AiAutoReplyAttempt,
        command: AiAutoReplyCommand,
    ) -> None:
        expected = (
            int(attempt.account_id),
            str(attempt.source_message_digest),
            str(attempt.request_digest),
            str(attempt.session_id),
            str(attempt.peer_id),
            str(attempt.goods_id or ""),
            str(attempt.seller_external_uid or ""),
        )
        incoming = (
            int(command.account_id),
            str(command.source_message_digest),
            str(command.request_digest),
            str(command.session_id)[:200],
            str(command.peer_id)[:200],
            str(command.goods_id)[:200],
            str(command.seller_external_uid)[:200],
        )
        if expected != incoming:
            raise AiAutoReplyAttemptError(
                "event_payload_conflict",
                "同一买家消息对应的账号、会话或上下文已变化，系统已拒绝重复发送",
            )

    def _acquire(self, attempt: AiAutoReplyAttempt, *, retry_scope: str) -> None:
        attempt.lease_token = uuid.uuid4().hex
        attempt.lease_until = _now() + dt.timedelta(seconds=self._lease_seconds)
        attempt.retry_scope = retry_scope

    @staticmethod
    def _release(attempt: AiAutoReplyAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _lease(
        attempt: AiAutoReplyAttempt,
        *,
        action: AttemptAction,
        repeated: bool = False,
        decrypt_reply: bool = False,
        reply_text: str = "",
    ) -> AiAutoReplyAttemptLease:
        if decrypt_reply and attempt.encrypted_reply:
            try:
                reply_text = str(
                    decrypt_secret(
                        str(attempt.encrypted_reply),
                        purpose=AI_REPLY_SECRET_PURPOSE,
                    )
                    or ""
                )
            except Exception:  # noqa: BLE001
                logger.error(
                    "AI reply recovery decryption failed attemptId=%d",
                    int(attempt.id),
                )
                reply_text = ""
        return AiAutoReplyAttemptLease(
            attempt_id=int(attempt.id),
            event_key=str(attempt.event_key),
            state=str(attempt.state),
            action=action,
            lease_token=str(attempt.lease_token) if attempt.lease_token else None,
            retry_safe=bool(attempt.retry_safe),
            repeated=repeated,
            error_code=str(attempt.last_error_code) if attempt.last_error_code else None,
            local_message_id=int(attempt.local_message_id) if attempt.local_message_id else None,
            reply_text=reply_text,
        )
