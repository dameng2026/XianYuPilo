"""Durable exactly-once coordination for operator-triggered chat messages.

Only digests and delivery metadata cross the attempt-store seam.  The message
body remains in the route callback and is never persisted in this module.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Awaitable, Callable, Literal, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import ManualMessageAttempt


logger = logging.getLogger(__name__)

AttemptState = Literal["pending", "sending", "confirmed", "failed", "unknown"]
AttemptAction = Literal["prepare", "send", "return", "in_progress"]
MessageType = Literal["text", "image"]
SendStatus = Literal["confirmed", "failed", "unknown"]

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SAFE_ERROR_CODE_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _safe_error_code(value: object, fallback: str) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if _SAFE_ERROR_CODE_RE.fullmatch(normalized) else fallback


def _now() -> dt.datetime:
    return dt.datetime.now()


def _identity_digest(value: object) -> str:
    return hashlib.sha256(str(value or "").strip().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ManualMessageCommand:
    idempotency_key: str
    account_id: int
    session_id: str = field(repr=False)
    peer_id: str = field(repr=False)
    message_type: MessageType = "text"
    payload_digest: str = ""

    def validate(self) -> None:
        if not _IDEMPOTENCY_KEY_RE.fullmatch(str(self.idempotency_key or "")):
            raise ValueError("idempotency_key is invalid")
        if int(self.account_id or 0) <= 0:
            raise ValueError("account_id is required")
        if not str(self.session_id or "").strip():
            raise ValueError("session_id is required")
        if not str(self.peer_id or "").strip():
            raise ValueError("peer_id is required")
        if self.message_type not in {"text", "image"}:
            raise ValueError("message_type is invalid")
        if not _SHA256_RE.fullmatch(str(self.payload_digest or "")):
            raise ValueError("payload_digest must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class ManualMessageAttemptLease:
    attempt_id: int
    idempotency_key: str
    state: AttemptState
    action: AttemptAction
    lease_token: str | None
    retry_safe: bool
    repeated: bool = False
    error_code: str | None = None
    local_message_id: int | None = None
    platform_message_id: str | None = None


@dataclass(frozen=True)
class ManualMessageSendResult:
    status: SendStatus
    error_code: str | None = None
    retry_safe: bool = False
    platform_message_id: str | None = None

    @classmethod
    def confirmed(cls, platform_message_id: object = None) -> "ManualMessageSendResult":
        value = str(platform_message_id or "").strip()
        return cls(
            status="confirmed",
            retry_safe=False,
            platform_message_id=value[:200] or None,
        )

    @classmethod
    def failed(
        cls,
        error_code: str = "message_rejected",
        *,
        retry_safe: bool = True,
    ) -> "ManualMessageSendResult":
        return cls(
            status="failed",
            error_code=_safe_error_code(error_code, "message_rejected"),
            retry_safe=bool(retry_safe),
        )

    @classmethod
    def unknown(
        cls,
        error_code: str = "message_ack_unknown",
    ) -> "ManualMessageSendResult":
        return cls(
            status="unknown",
            error_code=_safe_error_code(error_code, "message_ack_unknown"),
            retry_safe=False,
        )


@dataclass(frozen=True)
class ManualMessageOutcome:
    attempt_id: int
    idempotency_key: str
    status: AttemptState | Literal["in_progress"]
    retry_safe: bool
    repeated: bool
    error_code: str | None = None
    local_message_id: int | None = None
    platform_message_id: str | None = None

    def to_data(self) -> dict[str, object]:
        state_messages = {
            "pending": "消息尚未发送，可稍后重试",
            "sending": "消息正在发送，请勿重复操作",
            "in_progress": "同一消息正在发送，请勿重复操作",
            "confirmed": "平台已确认消息发送",
            "failed": "平台明确未接收消息，排查后可安全重试",
            "unknown": "发送结果未确认，请先在闲鱼 App 核对；系统已禁止直接重试",
        }
        error_messages = {
            "websocket_credentials_unavailable": "账号登录凭据不可用，消息尚未发送；请重新登录后重试",
            "websocket_auth_failed": "账号登录状态失效，消息尚未发送；请重新登录后重试",
            "websocket_unavailable": "账号消息连接不可用，消息尚未发送；连接恢复后可安全重试",
            "conversation_context_missing": "无法确认会话上下文，消息尚未发送；请刷新会话后重试",
            "conversation_peer_missing": "无法确认消息接收方，消息尚未发送；请刷新会话后重试",
            "conversation_missing": "平台明确拒绝已失效会话，消息未发送；请刷新会话列表",
            "message_rejected": "平台明确拒绝消息，本次未送达；排查后可安全重试",
            "message_ack_unknown": "平台确认超时，发送结果未知；请先在闲鱼 App 核对，系统已禁止直接重试",
            "message_result_unknown": "发送边界发生异常，结果未知；请先在闲鱼 App 核对，系统已禁止直接重试",
            "message_result_unknown_after_recovery": "上次发送在确认前中断，结果未知；请先在闲鱼 App 核对，系统不会重发",
            "local_message_persist_failed": "平台已确认接收，但本地记录失败；请先核对会话，系统已禁止重发",
        }
        return {
            "attemptId": self.attempt_id,
            "idempotencyKey": self.idempotency_key,
            "status": self.status,
            "retrySafe": self.retry_safe,
            "repeated": self.repeated,
            "errorCode": self.error_code,
            "message": error_messages.get(
                str(self.error_code or ""),
                state_messages[self.status],
            ),
            "uuid": self.platform_message_id,
        }


class ManualMessagePreflightError(RuntimeError):
    """A known failure before the external message boundary is crossed."""

    def __init__(self, error_code: str) -> None:
        self.error_code = _safe_error_code(error_code, "message_preflight_failed")
        super().__init__(self.error_code)


class ManualMessageAttemptError(RuntimeError):
    """Stable attempt-store error that never contains message content."""

    def __init__(self, error_code: str) -> None:
        self.error_code = _safe_error_code(error_code, "manual_message_attempt_error")
        super().__init__(self.error_code)


class AttemptStore(Protocol):
    async def claim(self, command: ManualMessageCommand) -> ManualMessageAttemptLease: ...

    async def mark_sending(
        self,
        lease: ManualMessageAttemptLease,
    ) -> ManualMessageAttemptLease: ...

    async def mark_failed(
        self,
        lease: ManualMessageAttemptLease,
        result: ManualMessageSendResult,
    ) -> ManualMessageAttemptLease: ...

    async def mark_unknown(
        self,
        lease: ManualMessageAttemptLease,
        result: ManualMessageSendResult,
        *,
        rollback_first: bool = False,
    ) -> ManualMessageAttemptLease: ...

    async def mark_confirmed(
        self,
        lease: ManualMessageAttemptLease,
        *,
        local_message_id: int | None,
        platform_message_id: str | None,
    ) -> ManualMessageAttemptLease: ...


Prepared = TypeVar("Prepared")
PrepareMessage = Callable[[], Awaitable[Prepared]]
SendMessage = Callable[[Prepared], Awaitable[ManualMessageSendResult]]
PersistMessage = Callable[[Prepared, str | None], Awaitable[int | None]]


class ManualMessageRuntime:
    """Execute one buyer-facing message behind a small, durable interface."""

    def __init__(self, store: AttemptStore) -> None:
        self._store = store

    async def execute(
        self,
        command: ManualMessageCommand,
        prepare: PrepareMessage[Prepared],
        send: SendMessage[Prepared],
        persist: PersistMessage[Prepared],
    ) -> ManualMessageOutcome:
        command.validate()
        lease = await self._store.claim(command)
        if lease.action in {"return", "in_progress"}:
            return self._outcome(lease)

        try:
            prepared = await prepare()
        except ManualMessagePreflightError as exc:
            lease = await self._store.mark_failed(
                lease,
                ManualMessageSendResult.failed(exc.error_code, retry_safe=True),
            )
            return self._outcome(lease)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Manual message preflight failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            lease = await self._store.mark_failed(
                lease,
                ManualMessageSendResult.failed(
                    "message_preflight_failed",
                    retry_safe=True,
                ),
            )
            return self._outcome(lease)

        lease = await self._store.mark_sending(lease)
        try:
            send_result = await send(prepared)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Manual message send result unknown attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            send_result = ManualMessageSendResult.unknown("message_result_unknown")

        if send_result.status == "failed":
            lease = await self._store.mark_failed(lease, send_result)
            return self._outcome(lease)
        if send_result.status == "unknown":
            lease = await self._store.mark_unknown(lease, send_result)
            return self._outcome(lease)

        try:
            local_message_id = await persist(
                prepared,
                send_result.platform_message_id,
            )
            lease = await self._store.mark_confirmed(
                lease,
                local_message_id=local_message_id,
                platform_message_id=send_result.platform_message_id,
            )
            return self._outcome(lease)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Manual message local confirmation failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            try:
                lease = await self._store.mark_unknown(
                    lease,
                    ManualMessageSendResult.unknown("local_message_persist_failed"),
                    rollback_first=True,
                )
            except Exception as mark_exc:  # noqa: BLE001
                logger.error(
                    "Manual message unknown state persistence failed attemptId=%d errorType=%s",
                    lease.attempt_id,
                    type(mark_exc).__name__,
                )
                lease = replace(
                    lease,
                    state="unknown",
                    action="return",
                    lease_token=None,
                    retry_safe=False,
                    error_code="local_message_persist_failed",
                )
            return self._outcome(lease)

    @staticmethod
    def _outcome(lease: ManualMessageAttemptLease) -> ManualMessageOutcome:
        return ManualMessageOutcome(
            attempt_id=lease.attempt_id,
            idempotency_key=lease.idempotency_key,
            status="in_progress" if lease.action == "in_progress" else lease.state,
            retry_safe=False if lease.action == "in_progress" else lease.retry_safe,
            repeated=lease.repeated,
            error_code=lease.error_code,
            local_message_id=lease.local_message_id,
            platform_message_id=lease.platform_message_id,
        )


class SqlManualMessageAttemptStore:
    """SQL adapter for finite leases and fail-closed crash recovery."""

    def __init__(self, db: AsyncSession, *, lease_seconds: int = 90) -> None:
        self._db = db
        self._lease_seconds = max(30, min(int(lease_seconds), 300))

    async def claim(
        self,
        command: ManualMessageCommand,
    ) -> ManualMessageAttemptLease:
        command.validate()
        existing = await self._find_locked(command.idempotency_key)
        if existing is not None:
            self._validate_payload(existing, command)
            return await self._claim_existing(existing)

        now = _now()
        attempt = ManualMessageAttempt(
            idempotency_key=command.idempotency_key,
            account_id=command.account_id,
            session_digest=_identity_digest(command.session_id),
            peer_digest=_identity_digest(command.peer_id),
            payload_digest=command.payload_digest,
            message_type=command.message_type,
            state="pending",
            retry_safe=1,
            attempt_count=1,
            lease_token=uuid.uuid4().hex,
            lease_until=now + dt.timedelta(seconds=self._lease_seconds),
        )
        self._db.add(attempt)
        try:
            await self._db.flush()
            await self._db.commit()
            return self._lease(attempt, action="prepare")
        except IntegrityError:
            await self._db.rollback()
            existing = await self._find_locked(command.idempotency_key)
            if existing is None:
                raise
            self._validate_payload(existing, command)
            return await self._claim_existing(existing)

    async def _claim_existing(
        self,
        attempt: ManualMessageAttempt,
    ) -> ManualMessageAttemptLease:
        state = str(attempt.state or "pending")
        now = _now()
        lease_active = bool(attempt.lease_until and attempt.lease_until > now)

        if state in {"confirmed", "unknown"} or (
            state == "failed" and not bool(attempt.retry_safe)
        ):
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)
        if state in {"pending", "sending"} and lease_active:
            await self._db.commit()
            return self._lease(attempt, action="in_progress", repeated=True)
        if state == "sending":
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = "message_result_unknown_after_recovery"
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)

        # Expired preflight work or an explicit retry-safe rejection did not
        # leave an ambiguous delivery behind, so it may take a fresh lease.
        attempt.state = "pending"
        attempt.retry_safe = 1
        attempt.attempt_count = int(attempt.attempt_count or 0) + 1
        attempt.lease_token = uuid.uuid4().hex
        attempt.lease_until = now + dt.timedelta(seconds=self._lease_seconds)
        attempt.send_started_at = None
        attempt.last_error_code = None
        await self._db.commit()
        return self._lease(attempt, action="prepare", repeated=True)

    async def mark_sending(
        self,
        lease: ManualMessageAttemptLease,
    ) -> ManualMessageAttemptLease:
        attempt = await self._locked_attempt(lease)
        if str(attempt.state) != "pending":
            raise ManualMessageAttemptError("attempt_state_conflict")
        attempt.state = "sending"
        attempt.retry_safe = 0
        attempt.send_started_at = attempt.send_started_at or _now()
        attempt.last_error_code = None
        await self._db.commit()
        return self._lease(attempt, action="send")

    async def mark_failed(
        self,
        lease: ManualMessageAttemptLease,
        result: ManualMessageSendResult,
    ) -> ManualMessageAttemptLease:
        attempt = await self._locked_attempt(lease)
        attempt.state = "failed"
        attempt.retry_safe = 1 if result.retry_safe else 0
        attempt.last_error_code = _safe_error_code(
            result.error_code,
            "message_rejected",
        )
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_unknown(
        self,
        lease: ManualMessageAttemptLease,
        result: ManualMessageSendResult,
        *,
        rollback_first: bool = False,
    ) -> ManualMessageAttemptLease:
        if rollback_first:
            await self._db.rollback()
        attempt = await self._find_locked_by_id(lease.attempt_id)
        if attempt is None:
            raise ManualMessageAttemptError("attempt_not_found")
        if str(attempt.state) == "confirmed":
            await self._db.commit()
            return self._lease(attempt, action="return")
        if not lease.lease_token or str(attempt.lease_token or "") != lease.lease_token:
            await self._db.rollback()
            raise ManualMessageAttemptError("attempt_lease_lost")
        attempt.state = "unknown"
        attempt.retry_safe = 0
        attempt.last_error_code = _safe_error_code(
            result.error_code,
            "message_ack_unknown",
        )
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_confirmed(
        self,
        lease: ManualMessageAttemptLease,
        *,
        local_message_id: int | None,
        platform_message_id: str | None,
    ) -> ManualMessageAttemptLease:
        attempt = await self._locked_attempt(lease)
        if str(attempt.state) != "sending":
            raise ManualMessageAttemptError("attempt_state_conflict")
        attempt.state = "confirmed"
        attempt.retry_safe = 0
        attempt.confirmed_at = attempt.confirmed_at or _now()
        attempt.local_message_id = local_message_id
        attempt.platform_message_digest = (
            _identity_digest(platform_message_id) if platform_message_id else None
        )
        attempt.last_error_code = None
        self._release(attempt)
        await self._db.commit()
        return replace(
            self._lease(attempt, action="return"),
            platform_message_id=platform_message_id,
        )

    async def _find_locked(
        self,
        idempotency_key: str,
    ) -> ManualMessageAttempt | None:
        return (
            await self._db.execute(
                select(ManualMessageAttempt)
                .where(ManualMessageAttempt.idempotency_key == idempotency_key)
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _find_locked_by_id(
        self,
        attempt_id: int,
    ) -> ManualMessageAttempt | None:
        return (
            await self._db.execute(
                select(ManualMessageAttempt)
                .where(ManualMessageAttempt.id == attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _locked_attempt(
        self,
        lease: ManualMessageAttemptLease,
    ) -> ManualMessageAttempt:
        attempt = await self._find_locked_by_id(lease.attempt_id)
        if attempt is None:
            raise ManualMessageAttemptError("attempt_not_found")
        if not lease.lease_token or str(attempt.lease_token or "") != lease.lease_token:
            await self._db.rollback()
            raise ManualMessageAttemptError("attempt_lease_lost")
        return attempt

    @staticmethod
    def _validate_payload(
        attempt: ManualMessageAttempt,
        command: ManualMessageCommand,
    ) -> None:
        expected = (
            int(attempt.account_id),
            str(attempt.session_digest),
            str(attempt.peer_digest),
            str(attempt.payload_digest),
            str(attempt.message_type),
        )
        incoming = (
            int(command.account_id),
            _identity_digest(command.session_id),
            _identity_digest(command.peer_id),
            str(command.payload_digest),
            str(command.message_type),
        )
        if expected != incoming:
            raise ManualMessageAttemptError("idempotency_payload_conflict")

    @staticmethod
    def _release(attempt: ManualMessageAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _lease(
        attempt: ManualMessageAttempt,
        *,
        action: AttemptAction,
        repeated: bool = False,
    ) -> ManualMessageAttemptLease:
        return ManualMessageAttemptLease(
            attempt_id=int(attempt.id),
            idempotency_key=str(attempt.idempotency_key),
            state=str(attempt.state),
            action=action,
            lease_token=str(attempt.lease_token) if attempt.lease_token else None,
            retry_safe=bool(attempt.retry_safe),
            repeated=repeated,
            error_code=(
                str(attempt.last_error_code) if attempt.last_error_code else None
            ),
            local_message_id=(
                int(attempt.local_message_id) if attempt.local_message_id else None
            ),
        )
