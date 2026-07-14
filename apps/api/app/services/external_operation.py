from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_security import redact_sensitive_text
from ..models.entities import ExternalOperationAttempt, XianyuGoods

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExternalOperationCommand:
    operation_type: Literal["publish", "update_price"]
    account_id: int
    idempotency_key: str
    request_digest: str
    target_local_id: int | None = None


@dataclass(frozen=True)
class RemoteOperationResult:
    status: Literal["confirmed", "failed", "unknown"]
    reference_id: str | None = None
    reference_url: str | None = None
    error_code: str | None = None
    message: str = ""
    retry_safe: bool = False

    @classmethod
    def confirmed(cls, reference_id: str | None = None, reference_url: str | None = None):
        return cls("confirmed", reference_id=reference_id, reference_url=reference_url)

    @classmethod
    def failed(cls, code: str, message: str, *, retry_safe: bool = True):
        return cls("failed", error_code=code, message=message, retry_safe=retry_safe)

    @classmethod
    def unknown(cls, code: str, message: str):
        return cls("unknown", error_code=code, message=message, retry_safe=False)


@dataclass(frozen=True)
class OperationLease:
    attempt_id: int
    idempotency_key: str
    state: str
    action: Literal["remote", "local", "return", "in_progress"]
    lease_token: str | None
    retry_safe: bool
    retry_scope: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    remote_reference_id: str | None = None
    remote_reference_url: str | None = None
    repeated: bool = False


@dataclass(frozen=True)
class ExternalOperationOutcome:
    status: str
    message: str
    attempt_id: int
    idempotency_key: str
    retry_safe: bool
    retry_scope: str | None
    remote_confirmed: bool
    local_confirmed: bool
    remote_reference_id: str | None
    remote_reference_url: str | None
    repeated: bool

    def to_data(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "attemptId": self.attempt_id,
            "idempotencyKey": self.idempotency_key,
            "retrySafe": self.retry_safe,
            "retryScope": self.retry_scope,
            "remoteConfirmed": self.remote_confirmed,
            "localConfirmed": self.local_confirmed,
            "remoteReferenceId": self.remote_reference_id,
            "remoteReferenceUrl": self.remote_reference_url,
            "repeated": self.repeated,
        }


class ExternalOperationError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.public_message = message


class OperationStore(Protocol):
    async def acquire(self, command: ExternalOperationCommand) -> OperationLease: ...
    async def mark_remote_started(self, lease: OperationLease) -> None: ...
    async def mark_remote_confirmed(self, lease: OperationLease, result: RemoteOperationResult) -> OperationLease: ...
    async def mark_failed(self, lease: OperationLease, result: RemoteOperationResult) -> OperationLease: ...
    async def mark_unknown(self, lease: OperationLease, result: RemoteOperationResult) -> OperationLease: ...
    async def mark_local_failed(self, lease: OperationLease) -> OperationLease: ...
    async def mark_confirmed(self, lease: OperationLease, local_result_id: int | None = None) -> OperationLease: ...


class ExternalOperationCoordinator:
    def __init__(
        self,
        store: OperationStore,
        remote_call: Callable[[], Awaitable[RemoteOperationResult]],
        local_call: Callable[[RemoteOperationResult], Awaitable[int | None]],
    ) -> None:
        self._store = store
        self._remote_call = remote_call
        self._local_call = local_call

    async def execute(self, command: ExternalOperationCommand) -> ExternalOperationOutcome:
        lease = await self._store.acquire(command)
        if lease.action == "in_progress":
            return self._outcome(lease, "in_progress")
        if lease.action == "return":
            return self._outcome(lease)

        remote_result: RemoteOperationResult
        if lease.action == "remote":
            await self._store.mark_remote_started(lease)
            try:
                remote_result = await self._remote_call()
            except Exception:
                logger.error("External operation remote result unknown attemptId=%d", lease.attempt_id)
                remote_result = RemoteOperationResult.unknown(
                    "remote_result_unknown",
                    "平台操作结果未知，请先同步核对，系统已禁止自动重试",
                )
            if remote_result.status == "unknown":
                return self._outcome(await self._store.mark_unknown(lease, remote_result))
            if remote_result.status != "confirmed":
                return self._outcome(await self._store.mark_failed(lease, remote_result))
            lease = await self._store.mark_remote_confirmed(lease, remote_result)
        else:
            remote_result = RemoteOperationResult.confirmed(
                lease.remote_reference_id,
                lease.remote_reference_url,
            )

        try:
            local_result_id = await self._local_call(remote_result)
        except Exception:
            logger.error("External operation local persistence failed attemptId=%d", lease.attempt_id)
            return self._outcome(await self._store.mark_local_failed(lease))
        return self._outcome(await self._store.mark_confirmed(lease, local_result_id))

    @staticmethod
    def _outcome(lease: OperationLease, status: str | None = None) -> ExternalOperationOutcome:
        resolved = status or lease.state
        messages = {
            "pending": "操作待执行",
            "in_progress": "同一操作正在执行，请勿重复提交",
            "remote_confirmed": "平台已确认，但本地状态尚未完成；重试只会修复本地状态",
            "confirmed": "平台与本地状态均已确认",
            "failed": lease.error_message or "平台明确拒绝操作，可排除问题后安全重试",
            "unknown": lease.error_message or "平台结果未知，请先同步核对，禁止自动重试",
        }
        return ExternalOperationOutcome(
            status=resolved,
            message=messages[resolved],
            attempt_id=lease.attempt_id,
            idempotency_key=lease.idempotency_key,
            retry_safe=False if resolved == "in_progress" else lease.retry_safe,
            retry_scope=lease.retry_scope,
            remote_confirmed=resolved in {"remote_confirmed", "confirmed"},
            local_confirmed=resolved == "confirmed",
            remote_reference_id=lease.remote_reference_id,
            remote_reference_url=lease.remote_reference_url,
            repeated=lease.repeated,
        )


class SqlExternalOperationStore:
    def __init__(self, db: AsyncSession, *, lease_seconds: int = 120) -> None:
        self.db = db
        self.lease_seconds = max(30, min(lease_seconds, 300))

    async def acquire(self, command: ExternalOperationCommand) -> OperationLease:
        for retry in range(2):
            try:
                return await self._acquire_once(command)
            except IntegrityError:
                await self.db.rollback()
                if retry:
                    raise
        raise RuntimeError("unreachable")

    async def _acquire_once(self, command: ExternalOperationCommand) -> OperationLease:
        # The target row is the business-identity mutex.  Idempotency keys are
        # client intent identifiers and can legitimately differ across tabs or
        # after lost browser storage, so locking only the key is insufficient.
        if command.target_local_id is not None:
            await self._lock_target(command)

        attempt = (
            await self.db.execute(
                select(ExternalOperationAttempt)
                .where(ExternalOperationAttempt.idempotency_key == command.idempotency_key)
                .with_for_update()
            )
        ).scalar_one_or_none()
        latest = await self._latest_target_attempt(command)
        now = dt.datetime.now()

        if attempt is not None:
            if (
                attempt.operation_type != command.operation_type
                or int(attempt.account_id) != int(command.account_id)
                or attempt.request_digest != command.request_digest
                or (attempt.target_local_id or None) != (command.target_local_id or None)
            ):
                await self.db.rollback()
                raise ExternalOperationError(
                    409,
                    "idempotency_conflict",
                    "幂等键已用于不同操作，请刷新后重试",
                )

            # A final result is always replayable by its original key, even if
            # later update-price intents exist for the same goods row.
            if self._is_final(attempt):
                await self.db.commit()
                return self._lease(attempt, "return", repeated=True)

            if latest is not None and int(latest.id) != int(attempt.id):
                await self.db.rollback()
                raise ExternalOperationError(
                    409,
                    "target_intent_superseded",
                    "该操作意图已被同一商品的更新意图取代；旧意图不会再次执行",
                )
            return await self._claim_existing(attempt, now=now, repeated=True)

        if latest is not None:
            resolved = await self._resolve_new_key_against_latest(
                command,
                latest,
                now=now,
            )
            if resolved is not None:
                return resolved

        attempt = ExternalOperationAttempt(
            operation_type=command.operation_type,
            account_id=command.account_id,
            idempotency_key=command.idempotency_key,
            request_digest=command.request_digest,
            target_local_id=command.target_local_id,
            state="pending",
            retry_scope="remote",
            retry_safe=1,
            attempt_count=1,
            lease_token=uuid.uuid4().hex,
            lease_until=now + dt.timedelta(seconds=self.lease_seconds),
        )
        self.db.add(attempt)
        await self.db.flush()
        await self.db.commit()
        return self._lease(attempt, "remote")

    async def _claim_existing(
        self,
        attempt: ExternalOperationAttempt,
        *,
        now: dt.datetime,
        repeated: bool,
    ) -> OperationLease:
        if self._is_final(attempt):
            await self.db.commit()
            return self._lease(attempt, "return", repeated=repeated)
        if attempt.lease_until and attempt.lease_until > now and attempt.state in {
            "pending",
            "in_progress",
            "remote_confirmed",
        }:
            await self.db.commit()
            return self._lease(attempt, "in_progress", repeated=repeated)
        if (
            attempt.state in {"pending", "in_progress"}
            and attempt.remote_started_at
            and not attempt.remote_confirmed_at
        ):
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.retry_scope = "remote"
            attempt.last_error_code = "remote_result_unknown_after_recovery"
            attempt.error_message = "上次平台请求在确认前中断，请先同步核对，系统已禁止自动重试"
            self._release(attempt)
            await self.db.commit()
            return self._lease(attempt, "return", repeated=repeated)

        action = "local" if attempt.state == "remote_confirmed" or attempt.remote_confirmed_at else "remote"
        attempt.state = "remote_confirmed" if action == "local" else "pending"
        attempt.retry_scope = "local_persist" if action == "local" else "remote"
        attempt.retry_safe = 1
        attempt.attempt_count = int(attempt.attempt_count or 0) + 1
        attempt.lease_token = uuid.uuid4().hex
        attempt.lease_until = now + dt.timedelta(seconds=self.lease_seconds)
        attempt.last_error_code = None
        attempt.error_message = None
        await self.db.commit()
        return self._lease(attempt, action, repeated=repeated)

    async def _resolve_new_key_against_latest(
        self,
        command: ExternalOperationCommand,
        latest: ExternalOperationAttempt,
        *,
        now: dt.datetime,
    ) -> OperationLease | None:
        same_request = (
            int(latest.account_id) == int(command.account_id)
            and str(latest.request_digest) == str(command.request_digest)
        )
        state = str(latest.state or "pending")

        if state == "confirmed":
            if same_request:
                await self.db.commit()
                return self._lease(latest, "return", repeated=True)
            if command.operation_type == "publish":
                await self.db.rollback()
                raise ExternalOperationError(
                    409,
                    "target_already_published",
                    "该本地草稿已经完成发布；系统已阻止使用新意图重复发布",
                )
            # A confirmed price change does not permanently lock the product;
            # a later key with a different digest represents a new price.
            return None

        blocks_new_intent = state in {
            "pending",
            "in_progress",
            "remote_confirmed",
            "unknown",
        } or (state == "failed" and not bool(latest.retry_safe))
        if blocks_new_intent:
            if same_request:
                return await self._claim_existing(
                    latest,
                    now=now,
                    repeated=True,
                )
            await self.db.rollback()
            raise ExternalOperationError(
                409,
                "target_intent_conflict",
                "同一商品已有执行中或结果待核对的操作意图；请恢复原意图或先核对平台状态",
            )

        # Only an explicit retry-safe failure may be replaced by a new key.
        return None

    async def _lock_target(self, command: ExternalOperationCommand) -> None:
        target = (
            await self.db.execute(
                select(XianyuGoods.id, XianyuGoods.account_id)
                .where(
                    XianyuGoods.id == command.target_local_id,
                    XianyuGoods.deleted == 0,
                )
                .with_for_update()
            )
        ).one_or_none()
        if target is None:
            await self.db.rollback()
            raise ExternalOperationError(
                404,
                "target_not_found",
                "操作目标不存在或已被清理，请刷新商品列表",
            )
        target_account_id = target[1]
        if target_account_id is not None and int(target_account_id) != int(command.account_id):
            await self.db.rollback()
            raise ExternalOperationError(
                409,
                "target_account_conflict",
                "操作目标与当前账号不匹配，请刷新商品列表",
            )

    async def _latest_target_attempt(
        self,
        command: ExternalOperationCommand,
    ) -> ExternalOperationAttempt | None:
        if command.target_local_id is None:
            return None
        return (
            await self.db.execute(
                select(ExternalOperationAttempt)
                .where(
                    ExternalOperationAttempt.operation_type == command.operation_type,
                    ExternalOperationAttempt.target_local_id == command.target_local_id,
                )
                .order_by(
                    ExternalOperationAttempt.created_time.desc(),
                    ExternalOperationAttempt.id.desc(),
                )
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    def _is_final(attempt: ExternalOperationAttempt) -> bool:
        state = str(attempt.state or "pending")
        return state in {"confirmed", "unknown"} or (
            state == "failed" and not bool(attempt.retry_safe)
        )

    async def mark_remote_started(self, lease: OperationLease) -> None:
        attempt = await self._locked(lease)
        attempt.state = "in_progress"
        attempt.remote_started_at = attempt.remote_started_at or dt.datetime.now()
        await self.db.commit()

    async def mark_remote_confirmed(self, lease: OperationLease, result: RemoteOperationResult) -> OperationLease:
        attempt = await self._locked(lease)
        attempt.state = "remote_confirmed"
        attempt.retry_scope = "local_persist"
        attempt.retry_safe = 1
        attempt.remote_confirmed_at = attempt.remote_confirmed_at or dt.datetime.now()
        attempt.remote_reference_id = (result.reference_id or "")[:200] or None
        attempt.remote_reference_url = (result.reference_url or "")[:1000] or None
        attempt.last_error_code = None
        attempt.error_message = None
        await self.db.commit()
        return self._lease(attempt, "local")

    async def mark_failed(self, lease: OperationLease, result: RemoteOperationResult) -> OperationLease:
        attempt = await self._locked(lease)
        attempt.state = "failed"
        attempt.retry_scope = "remote"
        attempt.retry_safe = 1 if result.retry_safe else 0
        attempt.last_error_code = self._safe_code(result.error_code, "remote_rejected")
        attempt.error_message = self._safe_message(result.message, "平台明确拒绝操作")
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return")

    async def mark_unknown(self, lease: OperationLease, result: RemoteOperationResult) -> OperationLease:
        attempt = await self._locked(lease)
        attempt.state = "unknown"
        attempt.retry_scope = "remote"
        attempt.retry_safe = 0
        attempt.last_error_code = self._safe_code(result.error_code, "remote_result_unknown")
        attempt.error_message = self._safe_message(result.message, "平台结果未知，请先同步核对")
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return")

    async def mark_local_failed(self, lease: OperationLease) -> OperationLease:
        await self.db.rollback()
        attempt = await self._locked(lease)
        attempt.state = "remote_confirmed"
        attempt.retry_scope = "local_persist"
        attempt.retry_safe = 1
        attempt.last_error_code = "local_persistence_failed"
        attempt.error_message = "平台已确认，但本地状态保存失败；重试只会修复本地状态"
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return")

    async def mark_confirmed(self, lease: OperationLease, local_result_id: int | None = None) -> OperationLease:
        attempt = await self._locked(lease)
        attempt.state = "confirmed"
        attempt.retry_scope = None
        attempt.retry_safe = 0
        attempt.local_confirmed_at = attempt.local_confirmed_at or dt.datetime.now()
        attempt.local_result_id = local_result_id
        attempt.last_error_code = None
        attempt.error_message = None
        self._release(attempt)
        await self.db.commit()
        return self._lease(attempt, "return")

    async def _locked(self, lease: OperationLease) -> ExternalOperationAttempt:
        attempt = (
            await self.db.execute(
                select(ExternalOperationAttempt)
                .where(ExternalOperationAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise ExternalOperationError(404, "attempt_not_found", "操作记录不存在")
        if not lease.lease_token or attempt.lease_token != lease.lease_token:
            raise ExternalOperationError(409, "attempt_lease_lost", "操作执行权已变化，请刷新状态")
        return attempt

    @staticmethod
    def _release(attempt: ExternalOperationAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _safe_code(value: str | None, default: str) -> str:
        normalized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(value or "").lower())
        return (normalized.strip("_") or default)[:64]

    @staticmethod
    def _safe_message(value: str, default: str) -> str:
        return (redact_sensitive_text(str(value or "").strip()) or default)[:500]

    @staticmethod
    def _lease(attempt: ExternalOperationAttempt, action, repeated: bool = False) -> OperationLease:
        return OperationLease(
            int(attempt.id),
            str(attempt.idempotency_key),
            str(attempt.state),
            action,
            attempt.lease_token,
            bool(attempt.retry_safe),
            attempt.retry_scope,
            attempt.last_error_code,
            attempt.error_message,
            attempt.remote_reference_id,
            attempt.remote_reference_url,
            repeated,
        )
