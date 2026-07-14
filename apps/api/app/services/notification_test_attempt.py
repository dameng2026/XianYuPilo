from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import re
import uuid
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import NotificationTestAttempt, NotificationTestTargetMutex

logger = logging.getLogger(__name__)

_CHANNEL_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{16,128}$")


class NotificationTestAttemptError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NotificationTestCommand:
    user_id: int
    channel_key: str
    idempotency_key: str
    title: str
    content: str

    def __post_init__(self) -> None:
        channel_key = str(self.channel_key or "").strip()
        idempotency_key = str(self.idempotency_key or "").strip()
        title = str(self.title or "").strip()
        content = str(self.content or "").strip()
        if int(self.user_id) <= 0:
            raise ValueError("user_id must be positive")
        if not _CHANNEL_KEY_PATTERN.fullmatch(channel_key):
            raise ValueError("channel_key is invalid")
        if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
            raise ValueError("idempotency_key is invalid")
        if not title or len(title) > 300:
            raise ValueError("title is invalid")
        if not content or len(content) > 2_000:
            raise ValueError("content is invalid")
        object.__setattr__(self, "channel_key", channel_key)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "content", content)

    @property
    def payload_digest(self) -> str:
        canonical = json.dumps(
            {
                "channelKey": self.channel_key,
                "content": self.content,
                "title": self.title,
                "userId": int(self.user_id),
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NotificationTestLease:
    attempt_id: int
    user_id: int
    channel_key: str
    idempotency_key: str
    payload_digest: str
    state: str
    action: str
    lease_token: str | None
    retry_safe: bool
    attempt_count: int
    provider_success: bool | None = None
    provider_status_code: int | None = None
    cost_ms: int | None = None
    result_code: str | None = None
    log_persisted: bool = False
    error_code: str | None = None
    repeated: bool = False
    replay_allowed: bool = True


@dataclass(frozen=True, slots=True)
class NotificationTestOutcome:
    status: str
    message: str
    attempt_id: int
    retry_safe: bool
    replay_safe: bool
    repeated: bool
    success: bool | None = None
    status_code: int | None = None
    cost_ms: int | None = None
    log_persisted: bool = False
    error_code: str | None = None

    def response_data(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "attemptId": self.attempt_id,
            "attemptStatus": self.status,
            "retrySafe": self.retry_safe,
            "replaySafe": self.replay_safe,
            "repeated": self.repeated,
            "logPersisted": self.log_persisted,
        }
        if self.success is not None:
            result["success"] = self.success
        if self.status_code is not None:
            result["statusCode"] = self.status_code
        if self.cost_ms is not None:
            result["costMs"] = self.cost_ms
        if self.error_code:
            result["reason"] = self.error_code
        return result


RemoteSend = Callable[[NotificationTestCommand], Awaitable[dict[str, Any]]]
LogWriter = Callable[[AsyncSession, NotificationTestLease], Awaitable[None]]


class NotificationTestCoordinator:
    def __init__(
        self,
        store: "SqlNotificationTestAttemptStore",
        remote_send: RemoteSend,
        log_writer: LogWriter | None = None,
    ) -> None:
        self._store = store
        self._remote_send = remote_send
        self._log_writer = log_writer

    async def execute(self, command: NotificationTestCommand) -> NotificationTestOutcome:
        lease = await self._store.acquire(command)
        if lease.action in {"return", "in_progress"}:
            if (
                lease.state == "confirmed"
                and not lease.log_persisted
                and lease.replay_allowed
            ):
                lease = await self._persist_log_best_effort(lease)
            return self._outcome(lease)

        try:
            await self._store.mark_send_started(lease)
        except Exception as exc:
            logger.error(
                "Notification test pre-send state persistence failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            try:
                failed = await self._store.reconcile_pre_send_failure(lease)
            except Exception as recovery_exc:
                logger.error(
                    "Notification test pre-send recovery failed attemptId=%d errorType=%s",
                    lease.attempt_id,
                    type(recovery_exc).__name__,
                )
                failed = replace(
                    lease,
                    state="unknown",
                    action="return",
                    lease_token=None,
                    retry_safe=False,
                    error_code="notification_test_pre_send_persistence_unknown",
                )
            return self._outcome(failed)
        try:
            remote_result = await self._remote_send(command)
            success = bool(remote_result["success"])
            status_code = int(remote_result.get("statusCode") or 0)
            cost_ms = max(0, int(remote_result.get("costMs") or 0))
        except Exception as exc:
            logger.warning(
                "Notification test result unknown attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            try:
                unknown = await self._store.mark_unknown(
                    lease, code="notification_test_result_unknown"
                )
            except Exception as persistence_exc:
                logger.error(
                    "Notification test unknown-state persistence failed attemptId=%d errorType=%s",
                    lease.attempt_id,
                    type(persistence_exc).__name__,
                )
                try:
                    unknown = await self._store.reconcile_unknown_failure(
                        lease,
                        code="notification_test_result_unknown",
                    )
                except Exception as recovery_exc:
                    logger.error(
                        "Notification test unknown-state recovery failed attemptId=%d errorType=%s",
                        lease.attempt_id,
                        type(recovery_exc).__name__,
                    )
                    unknown = replace(
                        lease,
                        state="unknown",
                        action="return",
                        lease_token=None,
                        retry_safe=False,
                        error_code="notification_test_result_unknown",
                    )
            return self._outcome(unknown)

        try:
            confirmed = await self._store.mark_confirmed(
                lease,
                success=success,
                status_code=status_code,
                cost_ms=cost_ms,
            )
        except Exception as exc:
            logger.error(
                "Notification test confirmation persistence failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            try:
                confirmed = await self._store.reconcile_confirmation_failure(lease)
            except Exception as recovery_exc:
                logger.error(
                    "Notification test unknown-state persistence failed attemptId=%d errorType=%s",
                    lease.attempt_id,
                    type(recovery_exc).__name__,
                )
                confirmed = replace(
                    lease,
                    state="unknown",
                    action="return",
                    lease_token=None,
                    retry_safe=False,
                    error_code="notification_test_confirmation_persistence_unknown",
                )
            return self._outcome(confirmed)
        confirmed = await self._persist_log_best_effort(confirmed)
        return self._outcome(confirmed)

    async def _persist_log_best_effort(
        self, lease: NotificationTestLease
    ) -> NotificationTestLease:
        if self._log_writer is None or lease.log_persisted:
            return lease
        try:
            return await self._store.persist_log(lease, self._log_writer)
        except Exception as exc:
            logger.error(
                "Notification test delivery-log persistence failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            try:
                await self._store.db.rollback()
            except Exception:
                logger.error(
                    "Notification test delivery-log rollback failed attemptId=%d",
                    lease.attempt_id,
                )
            return replace(lease, log_persisted=False)

    @staticmethod
    def _outcome(lease: NotificationTestLease) -> NotificationTestOutcome:
        status = "in_progress" if lease.action == "in_progress" else lease.state
        if lease.error_code == "notification_test_log_repair_required":
            status = "blocked"
        messages = {
            "pending": "通知测试等待发送",
            "in_progress": "当前渠道已有测试发送正在执行，请勿重复提交",
            "confirmed": (
                "通知渠道明确返回发送成功"
                if lease.provider_success
                else "通知渠道明确返回发送失败"
            ),
            "failed": "上次通知测试确定未调用渠道；仅原测试意图可安全恢复",
            "unknown": "通知测试发送结果未知；系统不会自动重发，请使用原意图核对",
            "blocked": "上一通知结果已确认，但审计日志待修复；仅原意图可补写日志",
            "resolved": "未知通知测试已由操作员人工核对并关闭；系统未自动重发",
        }
        return NotificationTestOutcome(
            status=status,
            message=messages[status],
            attempt_id=lease.attempt_id,
            retry_safe=(
                bool(lease.retry_safe)
                if lease.replay_allowed and status == "failed"
                else False
            ),
            replay_safe=lease.replay_allowed and status in {"confirmed", "failed", "unknown", "in_progress", "resolved"},
            repeated=lease.repeated,
            success=None if status == "blocked" else lease.provider_success,
            status_code=None if status == "blocked" else lease.provider_status_code,
            cost_ms=None if status == "blocked" else lease.cost_ms,
            log_persisted=lease.log_persisted,
            error_code=lease.error_code,
        )


class SqlNotificationTestAttemptStore:
    def __init__(self, db: AsyncSession, *, lease_seconds: int = 120) -> None:
        self.db = db
        self.lease_seconds = max(30, min(int(lease_seconds), 300))

    async def acquire(self, command: NotificationTestCommand) -> NotificationTestLease:
        for retry in range(2):
            try:
                return await self._acquire_once(command)
            except IntegrityError:
                await self.db.rollback()
                if retry:
                    raise
        raise RuntimeError("unreachable")

    async def _acquire_once(self, command: NotificationTestCommand) -> NotificationTestLease:
        target = (
            await self.db.execute(
                select(NotificationTestTargetMutex)
                .where(
                    NotificationTestTargetMutex.user_id == command.user_id,
                    NotificationTestTargetMutex.channel_key == command.channel_key,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if target is None:
            target = NotificationTestTargetMutex(
                user_id=command.user_id,
                channel_key=command.channel_key,
            )
            self.db.add(target)
            await self.db.flush()

        keyed = (
            await self.db.execute(
                select(NotificationTestAttempt)
                .where(NotificationTestAttempt.idempotency_key == command.idempotency_key)
                .with_for_update()
            )
        ).scalar_one_or_none()
        latest = None
        if target.latest_attempt_id is not None:
            latest = (
                await self.db.execute(
                    select(NotificationTestAttempt)
                    .where(NotificationTestAttempt.id == target.latest_attempt_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        if latest is None:
            latest = (
                await self.db.execute(
                    select(NotificationTestAttempt)
                    .where(
                        NotificationTestAttempt.user_id == command.user_id,
                        NotificationTestAttempt.channel_key == command.channel_key,
                    )
                    .order_by(
                        NotificationTestAttempt.created_time.desc(),
                        NotificationTestAttempt.id.desc(),
                    )
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if latest is not None:
                target.latest_attempt_id = int(latest.id)

        if keyed is not None and (
            int(keyed.user_id) != command.user_id
            or str(keyed.channel_key) != command.channel_key
            or str(keyed.payload_digest) != command.payload_digest
        ):
            await self.db.rollback()
            raise NotificationTestAttemptError(
                409,
                "idempotency_conflict",
                "通知测试幂等键已用于不同用户、渠道或消息",
            )

        if keyed is not None:
            return await self._claim_existing(keyed)

        latest_state = str(latest.state or "pending") if latest is not None else ""
        latest_terminal = bool(
            latest is not None
            and (
                latest_state == "resolved"
                or (latest_state == "confirmed" and bool(latest.log_persisted))
            )
        )
        if latest is not None and not latest_terminal:
            if self._lease_active(latest):
                await self.db.commit()
                return self._lease(
                    latest,
                    "in_progress",
                    repeated=True,
                    replay_allowed=False,
                )
            if latest_state == "confirmed":
                # The provider result is durable, but the audit log is not.
                # A new key must not advance the target until the original key
                # repairs that local-only transaction.
                await self.db.commit()
                return replace(
                    self._lease(
                        latest,
                        "return",
                        repeated=True,
                        replay_allowed=False,
                    ),
                    error_code="notification_test_log_repair_required",
                )
            if latest_state in {"pending", "failed"} and not latest.send_started_at:
                latest.state = "failed"
                latest.retry_safe = 1
                latest.last_error_code = "notification_test_not_started"
            else:
                latest.state = "unknown"
                latest.retry_safe = 0
                latest.last_error_code = "notification_test_lease_expired"
            self._release(latest)
            await self.db.commit()
            return self._lease(
                latest,
                "return",
                repeated=True,
                replay_allowed=False,
            )

        now = dt.datetime.now()
        attempt = NotificationTestAttempt(
            user_id=command.user_id,
            channel_key=command.channel_key,
            idempotency_key=command.idempotency_key,
            payload_digest=command.payload_digest,
            state="pending",
            retry_safe=1,
            attempt_count=1,
            lease_token=uuid.uuid4().hex,
            lease_until=now + dt.timedelta(seconds=self.lease_seconds),
        )
        self.db.add(attempt)
        await self.db.flush()
        target.latest_attempt_id = int(attempt.id)
        await self.db.commit()
        return self._lease(attempt, "remote")

    async def _claim_existing(
        self, attempt: NotificationTestAttempt
    ) -> NotificationTestLease:
        state = str(attempt.state or "pending")
        if state in {"confirmed", "unknown", "resolved"}:
            await self.db.commit()
            return self._lease(attempt, "return", repeated=True)
        if self._lease_active(attempt):
            await self.db.commit()
            return self._lease(attempt, "in_progress", repeated=True)
        if state in {"pending", "failed"} and not attempt.send_started_at:
            now = dt.datetime.now()
            attempt.state = "pending"
            attempt.retry_safe = 1
            attempt.attempt_count = int(attempt.attempt_count or 0) + 1
            attempt.lease_token = uuid.uuid4().hex
            attempt.lease_until = now + dt.timedelta(seconds=self.lease_seconds)
            attempt.last_error_code = None
            await self.db.commit()
            return self._lease(attempt, "remote", repeated=True)
        attempt.state = "unknown"
        attempt.retry_safe = 0
        attempt.last_error_code = "notification_test_lease_expired"
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return", repeated=True)

    async def mark_send_started(self, lease: NotificationTestLease) -> None:
        attempt = await self._locked(lease)
        attempt.state = "in_progress"
        attempt.retry_safe = 0
        attempt.send_started_at = attempt.send_started_at or dt.datetime.now()
        await self.db.commit()

    async def mark_confirmed(
        self,
        lease: NotificationTestLease,
        *,
        success: bool,
        status_code: int,
        cost_ms: int,
    ) -> NotificationTestLease:
        attempt = await self._locked(lease)
        attempt.state = "confirmed"
        attempt.retry_safe = 0
        attempt.confirmed_at = attempt.confirmed_at or dt.datetime.now()
        attempt.provider_success = 1 if success else 0
        attempt.provider_status_code = max(0, min(int(status_code), 999))
        attempt.cost_ms = max(0, min(int(cost_ms), 3_600_000))
        attempt.result_code = "delivered" if success else "rejected"
        attempt.last_error_code = None
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return", repeated=lease.repeated)

    async def mark_unknown(
        self, lease: NotificationTestLease, *, code: str
    ) -> NotificationTestLease:
        attempt = await self._locked(lease)
        attempt.state = "unknown"
        attempt.retry_safe = 0
        attempt.last_error_code = re.sub(r"[^A-Za-z0-9_.:-]", "_", code)[:64]
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return", repeated=lease.repeated)

    async def reconcile_confirmation_failure(
        self, lease: NotificationTestLease
    ) -> NotificationTestLease:
        await self.db.rollback()
        attempt = (
            await self.db.execute(
                select(NotificationTestAttempt)
                .where(NotificationTestAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise NotificationTestAttemptError(
                503,
                "notification_test_attempt_missing",
                "通知发送结果已返回，但本地安全状态不可用",
            )
        if str(attempt.state or "") != "confirmed":
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = "notification_test_confirmation_persistence_unknown"
            self._release(attempt)
            await self.db.commit()
        return self._lease(attempt, "return", repeated=lease.repeated)

    async def reconcile_pre_send_failure(
        self, lease: NotificationTestLease
    ) -> NotificationTestLease:
        """Recover only before the coordinator has invoked the provider."""

        await self.db.rollback()
        attempt = (
            await self.db.execute(
                select(NotificationTestAttempt)
                .where(NotificationTestAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise NotificationTestAttemptError(
                503,
                "notification_test_attempt_missing",
                "通知测试发送前安全状态不可用",
            )
        if str(attempt.state or "") not in {"confirmed", "unknown", "resolved"}:
            attempt.state = "failed"
            attempt.retry_safe = 1
            attempt.send_started_at = None
            attempt.last_error_code = "notification_test_pre_send_not_executed"
            self._release(attempt)
            await self.db.commit()
        return self._lease(attempt, "return", repeated=lease.repeated)

    async def reconcile_unknown_failure(
        self,
        lease: NotificationTestLease,
        *,
        code: str,
    ) -> NotificationTestLease:
        await self.db.rollback()
        attempt = (
            await self.db.execute(
                select(NotificationTestAttempt)
                .where(NotificationTestAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise NotificationTestAttemptError(
                503,
                "notification_test_attempt_missing",
                "通知测试未知状态不可用",
            )
        if str(attempt.state or "") not in {"confirmed", "resolved"}:
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = re.sub(r"[^A-Za-z0-9_.:-]", "_", code)[:64]
            self._release(attempt)
            await self.db.commit()
        return self._lease(attempt, "return", repeated=lease.repeated)

    async def persist_log(
        self,
        lease: NotificationTestLease,
        writer: LogWriter,
    ) -> NotificationTestLease:
        attempt = (
            await self.db.execute(
                select(NotificationTestAttempt)
                .where(NotificationTestAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None or str(attempt.state or "") != "confirmed":
            await self.db.rollback()
            raise NotificationTestAttemptError(
                409,
                "notification_test_not_confirmed",
                "通知测试尚未确认，不能写入投递日志",
            )
        if bool(attempt.log_persisted):
            await self.db.commit()
            return self._lease(attempt, "return", repeated=True)
        safe_lease = self._lease(attempt, "return", repeated=lease.repeated)
        await writer(self.db, safe_lease)
        attempt.log_persisted = 1
        await self.db.commit()
        return self._lease(attempt, "return", repeated=lease.repeated)

    async def resolve_unknown(
        self,
        *,
        user_id: int,
        channel_key: str,
        attempt_id: int,
        idempotency_key: str,
    ) -> NotificationTestLease:
        normalized_channel = str(channel_key or "").strip()
        normalized_key = str(idempotency_key or "").strip()
        if (
            int(user_id) <= 0
            or int(attempt_id) <= 0
            or not _CHANNEL_KEY_PATTERN.fullmatch(normalized_channel)
            or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized_key)
        ):
            raise NotificationTestAttemptError(
                400,
                "notification_test_resolution_invalid",
                "未知通知测试关闭参数不合法",
            )

        target = (
            await self.db.execute(
                select(NotificationTestTargetMutex)
                .where(
                    NotificationTestTargetMutex.user_id == int(user_id),
                    NotificationTestTargetMutex.channel_key == normalized_channel,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        attempt = (
            await self.db.execute(
                select(NotificationTestAttempt)
                .where(NotificationTestAttempt.id == int(attempt_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        identity_matches = bool(
            target is not None
            and attempt is not None
            and int(attempt.user_id) == int(user_id)
            and str(attempt.channel_key) == normalized_channel
            and hmac.compare_digest(str(attempt.idempotency_key), normalized_key)
            and int(target.latest_attempt_id or 0) == int(attempt_id)
        )
        if not identity_matches:
            await self.db.rollback()
            raise NotificationTestAttemptError(
                409,
                "notification_test_resolution_conflict",
                "只能使用当前用户、渠道与原始幂等键关闭最新未知测试",
            )

        state = str(attempt.state or "")
        if state == "resolved" and attempt.resolution_code == "manual_reconciled":
            await self.db.commit()
            return self._lease(attempt, "return", repeated=True)
        if state != "unknown":
            await self.db.rollback()
            raise NotificationTestAttemptError(
                409,
                "notification_test_not_unknown",
                "只有结果未知的最新通知测试可以人工关闭",
            )

        attempt.state = "resolved"
        attempt.retry_safe = 0
        attempt.resolved_at = attempt.resolved_at or dt.datetime.now()
        attempt.resolution_code = "manual_reconciled"
        attempt.last_error_code = None
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return")

    async def _locked(self, lease: NotificationTestLease) -> NotificationTestAttempt:
        attempt = (
            await self.db.execute(
                select(NotificationTestAttempt)
                .where(
                    NotificationTestAttempt.id == lease.attempt_id,
                    NotificationTestAttempt.lease_token == lease.lease_token,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            attempt is None
            or not attempt.lease_until
            or attempt.lease_until <= dt.datetime.now()
        ):
            await self.db.rollback()
            raise NotificationTestAttemptError(
                409,
                "notification_test_lease_lost",
                "通知测试执行租约已失效，禁止重复发送",
            )
        return attempt

    @staticmethod
    def _lease_active(attempt: NotificationTestAttempt) -> bool:
        return bool(
            attempt.lease_token
            and attempt.lease_until
            and attempt.lease_until > dt.datetime.now()
        )

    @staticmethod
    def _release(attempt: NotificationTestAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _lease(
        attempt: NotificationTestAttempt,
        action: str,
        *,
        repeated: bool = False,
        replay_allowed: bool = True,
    ) -> NotificationTestLease:
        provider_success = (
            None
            if attempt.provider_success is None
            else bool(attempt.provider_success)
        )
        return NotificationTestLease(
            attempt_id=int(attempt.id),
            user_id=int(attempt.user_id),
            channel_key=str(attempt.channel_key),
            idempotency_key=str(attempt.idempotency_key),
            payload_digest=str(attempt.payload_digest),
            state=str(attempt.state or "pending"),
            action=action,
            lease_token=str(attempt.lease_token) if attempt.lease_token else None,
            retry_safe=bool(attempt.retry_safe),
            attempt_count=int(attempt.attempt_count or 0),
            provider_success=provider_success,
            provider_status_code=(
                int(attempt.provider_status_code)
                if attempt.provider_status_code is not None
                else None
            ),
            cost_ms=int(attempt.cost_ms) if attempt.cost_ms is not None else None,
            result_code=str(attempt.result_code) if attempt.result_code else None,
            log_persisted=bool(attempt.log_persisted),
            error_code=str(attempt.last_error_code) if attempt.last_error_code else None,
            repeated=repeated,
            replay_allowed=replay_allowed,
        )
