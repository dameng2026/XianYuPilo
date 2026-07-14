from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import AdPaymentOrderAttempt, AdPaymentOrderTargetMutex

logger = logging.getLogger(__name__)

_ORDER_NO_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{16,128}$")
_PAYMENT_METHOD_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_REMOTE_STATUS_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")


class AdPaymentOrderAttemptError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class AdPaymentRemoteNotExecuted(RuntimeError):
    """The bridge rejected the call before any remote write could start."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AdPaymentOrderCommand:
    application_id: int
    payment_method: str
    idempotency_key: str

    def __post_init__(self) -> None:
        method = str(self.payment_method).strip().lower()
        key = str(self.idempotency_key).strip()
        if int(self.application_id) <= 0:
            raise ValueError("application_id must be positive")
        if not _PAYMENT_METHOD_PATTERN.fullmatch(method):
            raise ValueError("payment_method is invalid")
        if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
            raise ValueError("idempotency_key is invalid")
        object.__setattr__(self, "payment_method", method)
        object.__setattr__(self, "idempotency_key", key)

    @property
    def payload_digest(self) -> str:
        return payment_order_request_digest(self.application_id, self.payment_method)


@dataclass(frozen=True, slots=True)
class AdPaymentOrderLease:
    attempt_id: int
    application_id: int
    payment_method: str
    idempotency_key: str
    payload_digest: str
    state: str
    action: str
    lease_token: str | None
    retry_safe: bool
    attempt_count: int
    remote_order_no: str | None = None
    remote_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    repeated: bool = False
    replay_allowed: bool = True


@dataclass(frozen=True, slots=True)
class AdPaymentOrderOutcome:
    status: str
    message: str
    attempt_id: int
    retry_safe: bool
    replay_safe: bool
    repeated: bool
    order_data: dict[str, Any] | None = None
    error_code: str | None = None

    def response_data(self) -> dict[str, Any]:
        result = dict(self.order_data or {})
        result.update(
            {
                "attemptId": self.attempt_id,
                "attemptStatus": self.status,
                "retrySafe": self.retry_safe,
                "replaySafe": self.replay_safe,
                "repeated": self.repeated,
            }
        )
        if self.error_code:
            result["reason"] = self.error_code
        return result


RemoteCreate = Callable[[AdPaymentOrderCommand], Awaitable[dict[str, Any]]]


def payment_order_request_digest(application_id: int, payment_method: str) -> str:
    canonical = json.dumps(
        {
            "applicationId": int(application_id),
            "paymentMethod": str(payment_method).strip().lower(),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def payment_order_terminal_state(data: dict[str, Any]) -> str | None:
    """Return only terminal states explicitly proven by a bridge read result."""

    if not isinstance(data, dict):
        return None
    raw_status = data.get("status")
    if isinstance(raw_status, int) and not isinstance(raw_status, bool):
        # The current commercial bridge contract defines 2 as closed. Do not
        # guess that any other numeric failure means the order cannot settle.
        if raw_status == 2:
            return "closed"
    status_token = str(raw_status or "").strip().lower()
    if status_token in {"2", "closed", "cancelled", "canceled"}:
        return "closed"
    if status_token == "expired":
        return "expired"
    status_text = str(data.get("statusText") or "").strip().lower()
    if status_text in {
        "closed",
        "cancelled",
        "canceled",
        "已关闭",
        "订单已关闭",
        "支付已关闭",
        "已取消",
        "订单已取消",
        "支付已取消",
    }:
        return "closed"
    if status_text in {
        "expired",
        "已过期",
        "订单已过期",
        "支付已过期",
        "已失效",
        "订单已失效",
        "支付已失效",
    }:
        return "expired"
    return None


class AdPaymentOrderCoordinator:
    """Create or recover one remote order behind a durable application mutex."""

    def __init__(
        self,
        store: "SqlAdPaymentOrderAttemptStore",
        remote_create: RemoteCreate,
    ) -> None:
        self._store = store
        self._remote_create = remote_create

    async def execute(self, command: AdPaymentOrderCommand) -> AdPaymentOrderOutcome:
        lease = await self._store.acquire(command)
        if lease.action in {"return", "in_progress"}:
            return self._outcome(lease)

        await self._store.mark_remote_started(lease)
        try:
            remote_data = await self._remote_create(command)
            order_no, remote_status = self._validated_remote_result(remote_data)
        except AdPaymentRemoteNotExecuted as exc:
            lease = await self._store.mark_failed(
                lease,
                code=exc.code,
                retry_safe=True,
            )
            return self._outcome(lease)
        except Exception as exc:
            logger.warning(
                "Commercial payment-order result is unknown attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            lease = await self._store.mark_unknown(
                lease,
                code="commercial_bridge_result_unknown",
            )
            return self._outcome(lease)

        try:
            confirmed = await self._store.mark_confirmed(
                lease,
                order_no=order_no,
                remote_status=remote_status,
            )
        except Exception as exc:
            logger.error(
                "Payment order confirmation persistence failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            confirmed = await self._store.reconcile_after_confirmation_failure(
                lease,
                order_no=order_no,
            )
            if confirmed.state != "confirmed":
                return self._outcome(confirmed)
        return self._outcome(confirmed, remote_data=remote_data)

    @staticmethod
    def _validated_remote_result(data: dict[str, Any]) -> tuple[str, str | None]:
        if not isinstance(data, dict):
            raise ValueError("commercial bridge returned a non-object payment result")
        order_no = str(data.get("orderNo") or "").strip()
        if not _ORDER_NO_PATTERN.fullmatch(order_no):
            raise ValueError("commercial bridge did not return a valid order number")
        raw_status = data.get("status")
        remote_status = str(raw_status).strip() if raw_status is not None else ""
        return (
            order_no,
            remote_status if _REMOTE_STATUS_PATTERN.fullmatch(remote_status) else None,
        )

    @staticmethod
    def _outcome(
        lease: AdPaymentOrderLease,
        *,
        remote_data: dict[str, Any] | None = None,
    ) -> AdPaymentOrderOutcome:
        status = "in_progress" if lease.action == "in_progress" else lease.state
        messages = {
            "pending": "支付订单创建请求待执行",
            "in_progress": "同一广告申请的支付订单正在创建，请勿重复提交",
            "confirmed": "支付订单已由商业服务明确确认",
            "failed": lease.error_message or "商业服务明确未执行支付订单创建，可复用原意图重试",
            "unknown": lease.error_message or "支付订单创建结果未知，请先核对并复用原支付意图恢复",
            "closed": "该支付订单已由商业服务明确关闭，可创建新的支付意图",
            "expired": "该支付订单已由商业服务明确过期，可创建新的支付意图",
        }
        safe_replay = {
            "orderNo": lease.remote_order_no,
            "status": lease.remote_status,
        }
        safe_replay = {key: value for key, value in safe_replay.items() if value is not None}
        return AdPaymentOrderOutcome(
            status=status,
            message=messages[status],
            attempt_id=lease.attempt_id,
            retry_safe=lease.retry_safe if status != "in_progress" else False,
            replay_safe=(
                lease.replay_allowed
                and status
                in {
                    "in_progress",
                    "unknown",
                    "failed",
                    "confirmed",
                    "closed",
                    "expired",
                }
            ),
            repeated=lease.repeated,
            order_data=dict(remote_data) if remote_data is not None else safe_replay or None,
            error_code=lease.error_code,
        )


class SqlAdPaymentOrderAttemptStore:
    def __init__(self, db: AsyncSession, *, lease_seconds: int = 120) -> None:
        self.db = db
        self.lease_seconds = max(30, min(int(lease_seconds), 300))

    async def acquire(self, command: AdPaymentOrderCommand) -> AdPaymentOrderLease:
        for retry in range(2):
            try:
                return await self._acquire_once(command)
            except IntegrityError:
                await self.db.rollback()
                if retry:
                    raise
        raise RuntimeError("unreachable")

    async def _acquire_once(self, command: AdPaymentOrderCommand) -> AdPaymentOrderLease:
        target_mutex = (
            await self.db.execute(
                select(AdPaymentOrderTargetMutex)
                .where(
                    AdPaymentOrderTargetMutex.application_id == command.application_id
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if target_mutex is None:
            target_mutex = AdPaymentOrderTargetMutex(
                application_id=command.application_id,
            )
            self.db.add(target_mutex)
            # A concurrent first generation is resolved by acquire()'s unique
            # constraint retry, after which this row is locked and authoritative.
            await self.db.flush()

        keyed = (
            await self.db.execute(
                select(AdPaymentOrderAttempt)
                .where(AdPaymentOrderAttempt.idempotency_key == command.idempotency_key)
                .with_for_update()
            )
        ).scalar_one_or_none()
        latest = None
        if target_mutex.latest_attempt_id is not None:
            latest = (
                await self.db.execute(
                    select(AdPaymentOrderAttempt)
                    .where(AdPaymentOrderAttempt.id == target_mutex.latest_attempt_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        if latest is None:
            # Fail closed if a previous interrupted/manual repair left the
            # pointer empty or stale: recover the newest retained generation
            # under the target lock instead of creating a parallel order.
            latest = (
                await self.db.execute(
                    select(AdPaymentOrderAttempt)
                    .where(
                        AdPaymentOrderAttempt.application_id
                        == command.application_id
                    )
                    .order_by(
                        AdPaymentOrderAttempt.created_time.desc(),
                        AdPaymentOrderAttempt.id.desc(),
                    )
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if latest is not None:
                target_mutex.latest_attempt_id = int(latest.id)

        if keyed is not None and (
            int(keyed.application_id) != int(command.application_id)
            or str(keyed.payload_digest) != command.payload_digest
            or str(keyed.payment_method) != command.payment_method
        ):
            await self.db.rollback()
            raise AdPaymentOrderAttemptError(
                409,
                "idempotency_conflict",
                "支付意图幂等键已用于不同申请或支付方式",
            )

        if keyed is not None:
            if latest is not None and int(keyed.id) != int(latest.id):
                await self.db.commit()
                return self._lease(keyed, "return", repeated=True)
            return await self._claim_existing(keyed)

        if latest is not None:
            latest_state = str(latest.state or "pending")
            if latest_state not in {"closed", "expired"} and (
                str(latest.payload_digest) != command.payload_digest
            ):
                await self.db.rollback()
                raise AdPaymentOrderAttemptError(
                    409,
                    "application_payment_intent_conflict",
                    "同一广告申请已有不同支付方式的订单意图，请先核对原订单",
                )
            if latest_state not in {"closed", "expired"}:
                return await self._observe_with_different_key(latest)

        now = dt.datetime.now()
        attempt = AdPaymentOrderAttempt(
            application_id=command.application_id,
            idempotency_key=command.idempotency_key,
            payload_digest=command.payload_digest,
            payment_method=command.payment_method,
            state="pending",
            retry_safe=1,
            attempt_count=1,
            lease_token=uuid.uuid4().hex,
            lease_until=now + dt.timedelta(seconds=self.lease_seconds),
        )
        self.db.add(attempt)
        await self.db.flush()
        target_mutex.latest_attempt_id = int(attempt.id)
        await self.db.commit()
        return self._lease(attempt, "remote")

    async def _claim_existing(
        self,
        attempt: AdPaymentOrderAttempt,
    ) -> AdPaymentOrderLease:
        state = str(attempt.state or "pending")
        if state in {"confirmed", "closed", "expired"} or (
            state == "failed" and not bool(attempt.retry_safe)
        ):
            await self.db.commit()
            return self._lease(attempt, "return", repeated=True)
        if self._lease_active(attempt):
            await self.db.commit()
            return self._lease(attempt, "in_progress", repeated=True)

        now = dt.datetime.now()
        if state in {"in_progress", "pending"} and attempt.remote_started_at:
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = "remote_result_unknown_after_recovery"
            attempt.error_message = (
                "上次支付订单请求在确认前中断；仅允许复用原支付意图向幂等商业桥恢复"
            )
        elif state == "failed" and bool(attempt.retry_safe):
            attempt.state = "pending"
            attempt.last_error_code = None
            attempt.error_message = None
        attempt.attempt_count = int(attempt.attempt_count or 0) + 1
        attempt.lease_token = uuid.uuid4().hex
        attempt.lease_until = now + dt.timedelta(seconds=self.lease_seconds)
        await self.db.commit()
        return self._lease(attempt, "remote", repeated=True)

    async def _observe_with_different_key(
        self,
        attempt: AdPaymentOrderAttempt,
    ) -> AdPaymentOrderLease:
        if self._lease_active(attempt):
            await self.db.commit()
            return self._lease(
                attempt,
                "in_progress",
                repeated=True,
                replay_allowed=False,
            )
        state = str(attempt.state or "pending")
        if state in {"pending", "in_progress"}:
            if attempt.remote_started_at:
                attempt.state = "unknown"
                attempt.retry_safe = 0
                attempt.last_error_code = "remote_result_unknown_after_recovery"
                attempt.error_message = (
                    "上次支付订单请求在确认前中断；仅原支付意图键可向幂等商业桥恢复"
                )
            else:
                attempt.state = "failed"
                attempt.retry_safe = 1
                attempt.last_error_code = "request_not_started_after_recovery"
                attempt.error_message = (
                    "上次支付订单请求确定未发出；仅可回到保存原支付意图键的页面恢复"
                )
            self._release(attempt)
        await self.db.commit()
        return self._lease(
            attempt,
            "return",
            repeated=True,
            replay_allowed=False,
        )

    async def mark_remote_started(self, lease: AdPaymentOrderLease) -> None:
        attempt = await self._locked(lease)
        attempt.state = "in_progress"
        attempt.retry_safe = 0
        attempt.remote_started_at = attempt.remote_started_at or dt.datetime.now()
        await self.db.commit()

    async def mark_confirmed(
        self,
        lease: AdPaymentOrderLease,
        *,
        order_no: str,
        remote_status: str | None,
    ) -> AdPaymentOrderLease:
        attempt = await self._locked(lease)
        attempt.state = "confirmed"
        attempt.retry_safe = 0
        attempt.remote_confirmed_at = attempt.remote_confirmed_at or dt.datetime.now()
        attempt.remote_order_no = order_no
        attempt.remote_status = remote_status
        attempt.last_error_code = None
        attempt.error_message = None
        self._release(attempt)
        await self.db.commit()
        return self._lease(
            attempt,
            "return",
            repeated=lease.repeated,
            replay_allowed=lease.replay_allowed,
        )

    async def mark_failed(
        self,
        lease: AdPaymentOrderLease,
        *,
        code: str,
        retry_safe: bool,
    ) -> AdPaymentOrderLease:
        attempt = await self._locked(lease)
        attempt.state = "failed"
        attempt.retry_safe = 1 if retry_safe else 0
        attempt.last_error_code = self._safe_code(code)
        attempt.error_message = (
            "商业桥明确未发出支付订单请求；仅可复用原支付意图重试"
            if retry_safe
            else "支付订单请求失败且无法确认未执行；请先人工核对"
        )
        self._release(attempt)
        await self.db.commit()
        return self._lease(
            attempt,
            "return",
            repeated=lease.repeated,
            replay_allowed=lease.replay_allowed,
        )

    async def mark_unknown(
        self,
        lease: AdPaymentOrderLease,
        *,
        code: str,
    ) -> AdPaymentOrderLease:
        try:
            attempt = await self._locked(lease)
        except Exception:
            await self.db.rollback()
            raise
        attempt.state = "unknown"
        attempt.retry_safe = 0
        attempt.last_error_code = self._safe_code(code)
        attempt.error_message = "支付订单创建结果未知，请先核对商业服务；恢复时必须复用原支付意图"
        self._release(attempt)
        await self.db.commit()
        return self._lease(
            attempt,
            "return",
            repeated=lease.repeated,
            replay_allowed=lease.replay_allowed,
        )

    async def reconcile_after_confirmation_failure(
        self,
        lease: AdPaymentOrderLease,
        *,
        order_no: str,
    ) -> AdPaymentOrderLease:
        await self.db.rollback()
        attempt = (
            await self.db.execute(
                select(AdPaymentOrderAttempt)
                .where(AdPaymentOrderAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise AdPaymentOrderAttemptError(
                503,
                "attempt_persistence_unavailable",
                "支付订单结果已返回，但本地核对记录不可用",
            )
        if str(attempt.state) == "confirmed":
            await self.db.commit()
            return self._lease(attempt, "return", repeated=True)
        attempt.state = "unknown"
        attempt.retry_safe = 0
        attempt.remote_order_no = order_no
        attempt.last_error_code = "confirmation_persistence_failed"
        attempt.error_message = "商业桥已返回订单，但本地确认提交失败；请按订单号核对并复用原意图恢复"
        self._release(attempt)
        await self.db.commit()
        return self._lease(
            attempt,
            "return",
            repeated=lease.repeated,
            replay_allowed=lease.replay_allowed,
        )

    async def mark_terminal_by_order_no(
        self,
        order_no: str,
        *,
        terminal_state: str,
    ) -> bool:
        normalized_state = str(terminal_state).strip().lower()
        if normalized_state not in {"closed", "expired"}:
            raise ValueError("terminal_state must be closed or expired")
        normalized_order_no = str(order_no).strip()
        if not _ORDER_NO_PATTERN.fullmatch(normalized_order_no):
            raise ValueError("order_no is invalid")
        attempt = (
            await self.db.execute(
                select(AdPaymentOrderAttempt)
                .where(AdPaymentOrderAttempt.remote_order_no == normalized_order_no)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            await self.db.commit()
            return False
        attempt.state = normalized_state
        attempt.remote_status = normalized_state
        attempt.retry_safe = 0
        attempt.last_error_code = None
        attempt.error_message = None
        self._release(attempt)
        await self.db.commit()
        return True

    async def _locked(self, lease: AdPaymentOrderLease) -> AdPaymentOrderAttempt:
        attempt = (
            await self.db.execute(
                select(AdPaymentOrderAttempt)
                .where(AdPaymentOrderAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise AdPaymentOrderAttemptError(404, "attempt_not_found", "支付订单尝试不存在")
        if not lease.lease_token or attempt.lease_token != lease.lease_token:
            raise AdPaymentOrderAttemptError(
                409,
                "attempt_lease_lost",
                "支付订单执行权已变化，请刷新后核对",
            )
        return attempt

    @staticmethod
    def _lease_active(attempt: AdPaymentOrderAttempt) -> bool:
        return bool(
            attempt.lease_token
            and attempt.lease_until
            and attempt.lease_until > dt.datetime.now()
        )

    @staticmethod
    def _release(attempt: AdPaymentOrderAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _safe_code(value: str) -> str:
        normalized = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in str(value or "").lower()
        )
        return (normalized.strip("_") or "payment_order_failed")[:64]

    @staticmethod
    def _lease(
        attempt: AdPaymentOrderAttempt,
        action: str,
        *,
        repeated: bool = False,
        replay_allowed: bool = True,
    ) -> AdPaymentOrderLease:
        return AdPaymentOrderLease(
            attempt_id=int(attempt.id),
            application_id=int(attempt.application_id),
            payment_method=str(attempt.payment_method),
            idempotency_key=str(attempt.idempotency_key),
            payload_digest=str(attempt.payload_digest),
            state=str(attempt.state or "pending"),
            action=action,
            lease_token=attempt.lease_token,
            retry_safe=bool(attempt.retry_safe),
            attempt_count=int(attempt.attempt_count or 0),
            remote_order_no=attempt.remote_order_no,
            remote_status=attempt.remote_status,
            error_code=attempt.last_error_code,
            error_message=attempt.error_message,
            repeated=repeated,
            replay_allowed=replay_allowed,
        )
