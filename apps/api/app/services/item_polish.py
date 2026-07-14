from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import re
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..core.background_tasks import spawn_background_task
from ..core.cookie_crypto import decrypt_cookie_if_needed
from ..core.logging_security import redact_sensitive_text
from ..models.entities import (
    ItemPolishTask,
    ItemPolishTaskItem,
    XianyuAccount,
    XianyuAccountAuth,
    XianyuGoods,
)
from .xianyu_goods_sync import XianyuItemOperator, extract_token_from_cookie


logger = logging.getLogger(__name__)

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_SAFE_ERROR_CODE_RE = re.compile(r"[^a-z0-9_]+")
_MAX_ITEMS_PER_TASK = 100
_MAX_RECONCILE_ITEMS = 200
_BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")
_MANUAL_CONFIRMED_CODE = "polish_manual_reconciled_confirmed"
_MANUAL_NOT_POLISHED_CODE = "polish_manual_reconciled_not_polished"
_MANUAL_RETRY_QUIESCENCE_SECONDS = 300
_BLOCKING_TASK_STATUSES = frozenset(
    {"pending", "running", "needs_verification", "unknown"}
)

TaskStatus = Literal[
    "pending",
    "running",
    "completed",
    "partial",
    "failed",
    "needs_verification",
    "unknown",
]
ItemStatus = Literal[
    "pending",
    "in_progress",
    "confirmed",
    "already_done",
    "failed",
    "needs_verification",
    "unknown",
]


@dataclass(frozen=True)
class ItemPolishResult:
    status: Literal[
        "confirmed",
        "already_done",
        "failed",
        "needs_verification",
        "unknown",
    ]
    error_code: str | None = None
    message: str = ""
    retry_safe: bool = False

    @classmethod
    def confirmed(cls, *, already_done: bool = False) -> "ItemPolishResult":
        return cls(status="already_done" if already_done else "confirmed")

    @classmethod
    def failed(
        cls,
        error_code: str,
        message: str,
        *,
        retry_safe: bool = True,
    ) -> "ItemPolishResult":
        return cls("failed", error_code, message, retry_safe)

    @classmethod
    def verification_required(cls) -> "ItemPolishResult":
        return cls(
            "needs_verification",
            "polish_verification_required",
            "闲鱼要求完成安全验证；请在闲鱼 App 完成验证后使用原任务继续",
            True,
        )

    @classmethod
    def unknown(cls, error_code: str, message: str) -> "ItemPolishResult":
        return cls("unknown", error_code, message, False)


@dataclass(frozen=True)
class ItemPolishContext:
    task_id: str
    item_attempt_id: int
    goods_id: int
    account_id: int
    external_goods_id: str
    lease_token: str


@dataclass(frozen=True)
class ItemPolishRunLease:
    task_id: str
    lease_token: str


@dataclass(frozen=True)
class ItemPolishReconcileDecision:
    goods_id: int
    outcome: Literal["confirmed_polished", "confirmed_not_polished"]


@dataclass(frozen=True)
class ItemPolishTaskView:
    task_id: str
    account_id: int
    idempotency_key: str
    status: TaskStatus
    total: int
    processed: int
    polished: int
    already_done: int
    failed: int
    unknown: int
    progress: int
    message: str
    retry_safe: bool
    recovery: str | None
    results: tuple[dict[str, object], ...] = ()
    retry_after: str | None = None

    def to_data(self) -> dict[str, object]:
        return {
            "taskId": self.task_id,
            "accountId": self.account_id,
            "idempotencyKey": self.idempotency_key,
            "status": self.status,
            "running": self.status == "running",
            "total": self.total,
            "processed": self.processed,
            "polished": self.polished,
            "alreadyDone": self.already_done,
            "failed": self.failed,
            "unknown": self.unknown,
            "progress": self.progress,
            "needManual": self.status == "needs_verification",
            "message": self.message,
            "retrySafe": self.retry_safe,
            "recovery": self.recovery,
            "retryAfter": self.retry_after,
            "results": list(self.results),
        }


@dataclass(frozen=True)
class ItemPolishSubmission:
    task: ItemPolishTaskView
    should_start: bool


class ItemPolishError(Exception):
    def __init__(
        self,
        http_status: int,
        error_code: str,
        message: str,
        *,
        data: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.error_code = error_code
        self.public_message = message
        self.data = data or {}


class ItemPolishStore(Protocol):
    async def submit(
        self,
        *,
        account_id: int,
        idempotency_key: str,
        goods_ids: tuple[int, ...],
        request_digest: str,
    ) -> ItemPolishSubmission: ...

    async def progress(self, task_id: str) -> ItemPolishTaskView: ...

    async def reconcile_unknown(
        self,
        *,
        task_id: str,
        decisions: tuple[ItemPolishReconcileDecision, ...],
    ) -> ItemPolishTaskView: ...

    async def recoverable_task_ids(self, *, limit: int = 100) -> tuple[str, ...]: ...

    async def acquire_run(self, task_id: str) -> ItemPolishRunLease | None: ...

    async def claim_next(
        self,
        lease: ItemPolishRunLease,
    ) -> ItemPolishContext | None: ...

    async def record_result(
        self,
        lease: ItemPolishRunLease,
        item: ItemPolishContext,
        result: ItemPolishResult,
    ) -> None: ...

    async def mark_unknown(
        self,
        lease: ItemPolishRunLease,
        item: ItemPolishContext,
        result: ItemPolishResult,
    ) -> None: ...

    async def finish(self, lease: ItemPolishRunLease) -> None: ...


class ItemPolishGateway(Protocol):
    async def polish(self, context: ItemPolishContext) -> ItemPolishResult: ...


Scheduler = Callable[[Coroutine[Any, Any, None], str], None]


class ItemPolishModule:
    """Deep module: callers only submit an intent and read truthful progress."""

    def __init__(
        self,
        *,
        store: ItemPolishStore,
        gateway: ItemPolishGateway,
        scheduler: Scheduler,
        inter_item_delay_seconds: float = 1.0,
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._scheduler = scheduler
        self._delay = max(0.0, float(inter_item_delay_seconds))

    async def submit(
        self,
        *,
        account_id: int,
        idempotency_key: str | None,
        goods_ids: list[int] | tuple[int, ...] | None = None,
    ) -> ItemPolishTaskView:
        normalized_account_id = int(account_id or 0)
        if normalized_account_id <= 0:
            raise ItemPolishError(422, "polish_account_invalid", "请选择有效的闲鱼账号")
        normalized_key = str(idempotency_key or "").strip()
        if not _IDEMPOTENCY_KEY_RE.fullmatch(normalized_key):
            raise ItemPolishError(
                422,
                "idempotency_key_invalid",
                "擦亮操作必须提供 8-128 位幂等键",
            )
        normalized_goods = tuple(sorted({int(value) for value in goods_ids or () if int(value) > 0}))
        if len(normalized_goods) > _MAX_ITEMS_PER_TASK:
            raise ItemPolishError(
                422,
                "polish_scope_too_large",
                f"单次最多擦亮 {_MAX_ITEMS_PER_TASK} 件商品，请缩小选择范围",
            )
        request_digest = self._request_digest(normalized_account_id, normalized_goods)
        submission = await self._store.submit(
            account_id=normalized_account_id,
            idempotency_key=normalized_key,
            goods_ids=normalized_goods,
            request_digest=request_digest,
        )
        if submission.should_start:
            self._schedule(submission.task.task_id)
        return submission.task

    async def progress(self, task_id: str) -> ItemPolishTaskView:
        normalized = str(task_id or "").strip()
        if not normalized or len(normalized) > 64:
            raise ItemPolishError(404, "polish_task_not_found", "擦亮任务不存在")
        return await self._store.progress(normalized)

    async def reconcile_unknown(
        self,
        *,
        task_id: str,
        verified_in_xianyu_app: bool,
        decisions: list[ItemPolishReconcileDecision]
        | tuple[ItemPolishReconcileDecision, ...],
    ) -> ItemPolishTaskView:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id or len(normalized_task_id) > 64:
            raise ItemPolishError(404, "polish_task_not_found", "擦亮任务不存在")
        if verified_in_xianyu_app is not True:
            raise ItemPolishError(
                422,
                "polish_reconcile_verification_required",
                "请先在闲鱼 App 逐项核对结果，并明确确认已完成核对",
            )
        if not 1 <= len(decisions) <= _MAX_RECONCILE_ITEMS:
            raise ItemPolishError(
                422,
                "polish_reconcile_items_invalid",
                f"人工对账必须包含 1-{_MAX_RECONCILE_ITEMS} 个商品结论",
            )

        normalized: dict[int, ItemPolishReconcileDecision] = {}
        for decision in decisions:
            goods_id = int(decision.goods_id or 0)
            outcome = str(decision.outcome or "").strip()
            if goods_id <= 0 or outcome not in {
                "confirmed_polished",
                "confirmed_not_polished",
            }:
                raise ItemPolishError(
                    422,
                    "polish_reconcile_decision_invalid",
                    "商品对账结论无效；只能确认已擦亮或确认未擦亮",
                )
            previous = normalized.get(goods_id)
            if previous is not None and previous.outcome != outcome:
                raise ItemPolishError(
                    422,
                    "polish_reconcile_decision_conflict",
                    f"商品 {goods_id} 存在相互冲突的对账结论，请修正后重试",
                )
            normalized[goods_id] = ItemPolishReconcileDecision(
                goods_id=goods_id,
                outcome=outcome,  # type: ignore[arg-type]
            )
        return await self._store.reconcile_unknown(
            task_id=normalized_task_id,
            decisions=tuple(normalized.values()),
        )

    async def recover_due_tasks(self, *, limit: int = 100) -> int:
        """Schedule durable pending work after startup or an expired lease."""

        task_ids = await self._store.recoverable_task_ids(limit=limit)
        return sum(self._schedule(task_id) for task_id in task_ids)

    def _schedule(self, task_id: str) -> bool:
        coroutine = self._run(task_id)
        try:
            self._scheduler(coroutine, f"item-polish:{task_id}")
            return True
        except Exception:
            coroutine.close()
            logger.error(
                "Item polish task could not be scheduled taskId=%s",
                task_id,
            )
            return False

    async def _run(self, task_id: str) -> None:
        lease = await self._store.acquire_run(task_id)
        if lease is None:
            return
        while True:
            item = await self._store.claim_next(lease)
            if item is None:
                await self._store.finish(lease)
                return
            remote_task = asyncio.create_task(
                self._gateway.polish(item),
                name=f"item-polish-remote:{lease.task_id}:{item.item_attempt_id}",
            )
            try:
                # asyncio.to_thread cannot stop its worker when the awaiting
                # coroutine is cancelled. Shield the complete gateway call so
                # a graceful shutdown cannot release the durable lease while
                # an older platform mutation is still running in a thread.
                result = await asyncio.shield(remote_task)
            except asyncio.CancelledError:
                current_task = asyncio.current_task()
                if current_task is not None and current_task.cancelling():
                    current_task.uncancel()
                # Shutdown registries may cancel the runner more than once.
                # Consume repeated cancellation requests and keep shielding
                # until the real gateway task (including any to_thread worker)
                # has actually stopped. The explicit raise below still makes
                # the runner finish as cancelled after durable reconciliation.
                while not remote_task.done():
                    try:
                        await asyncio.shield(remote_task)
                    except asyncio.CancelledError:
                        if current_task is not None and current_task.cancelling():
                            current_task.uncancel()
                    except BaseException:
                        break
                if remote_task.done():
                    try:
                        remote_task.result()
                    except BaseException:
                        pass
                await self._best_effort_unknown(
                    lease,
                    item,
                    ItemPolishResult.unknown(
                        "platform_result_unknown_shutdown",
                        "服务停止时平台结果尚未确认；请先在闲鱼 App 核对，系统不会自动重试",
                    ),
                )
                raise
            except Exception:
                result = ItemPolishResult.unknown(
                    "platform_result_unknown",
                    "平台擦亮结果无法确认；请先在闲鱼 App 核对，系统不会自动重试",
                )

            try:
                await self._store.record_result(lease, item, result)
            except Exception:
                await self._best_effort_unknown(
                    lease,
                    item,
                    ItemPolishResult.unknown(
                        "polish_confirmation_persist_unknown",
                        "平台可能已擦亮商品，但结果未能保存；请先在闲鱼 App 核对，禁止自动重试",
                    ),
                )
                return

            if result.status in {"unknown", "needs_verification"}:
                return
            if self._delay:
                await asyncio.sleep(self._delay)

    async def _best_effort_unknown(
        self,
        lease: ItemPolishRunLease,
        item: ItemPolishContext,
        result: ItemPolishResult,
    ) -> None:
        try:
            await self._store.mark_unknown(lease, item, result)
        except Exception:
            logger.error(
                "Item polish unknown outcome could not be persisted taskId=%s",
                lease.task_id,
            )

    @staticmethod
    def _request_digest(account_id: int, goods_ids: tuple[int, ...]) -> str:
        payload = {
            "accountId": account_id,
            "goodsIds": list(goods_ids) if goods_ids else "all-active",
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> dt.datetime:
    # Persistence columns are currently naive DATETIME values. Always write
    # naive Asia/Shanghai wall time so Docker/host timezone cannot move the
    # product's definition of "today" or lease expiry by eight hours.
    return dt.datetime.now(tz=_BUSINESS_TIMEZONE).replace(tzinfo=None)


def _business_day_bounds(
    reference: dt.datetime | None = None,
) -> tuple[dt.datetime, dt.datetime]:
    current = reference if reference is not None else _now()
    if current.tzinfo is not None:
        current = current.astimezone(_BUSINESS_TIMEZONE).replace(tzinfo=None)
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + dt.timedelta(days=1)


def _manual_retry_after(
    item: ItemPolishTaskItem,
    *,
    fallback: dt.datetime | None = None,
) -> dt.datetime:
    reconciliation_anchor = item.updated_time or fallback
    timestamps = [
        value
        for value in (
            reconciliation_anchor,
            item.remote_started_at,
            item.created_time,
        )
        if value is not None
    ]
    reconciled_at = max(timestamps) if timestamps else _now()
    _, next_business_day = _business_day_bounds(reconciled_at)
    quiescent_at = reconciled_at + dt.timedelta(
        seconds=_MANUAL_RETRY_QUIESCENCE_SECONDS
    )
    return max(next_business_day, quiescent_at)


def _safe_error_code(value: object, default: str) -> str:
    normalized = _SAFE_ERROR_CODE_RE.sub("_", str(value or "").lower()).strip("_")
    return (normalized or default)[:64]


def _safe_error_message(value: object, default: str) -> str:
    normalized = redact_sensitive_text(str(value or "").strip())
    return (normalized or default)[:500]


class SqlItemPolishStore:
    """MySQL adapter for durable task snapshots and per-item leases."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_seconds: int = 90,
    ) -> None:
        self._sessions = session_factory
        self._lease_seconds = max(45, min(int(lease_seconds), 300))

    async def submit(
        self,
        *,
        account_id: int,
        idempotency_key: str,
        goods_ids: tuple[int, ...],
        request_digest: str,
    ) -> ItemPolishSubmission:
        for race_attempt in range(2):
            async with self._sessions() as db:
                try:
                    return await self._submit_once(
                        db,
                        account_id=account_id,
                        idempotency_key=idempotency_key,
                        goods_ids=goods_ids,
                        request_digest=request_digest,
                    )
                except IntegrityError:
                    await db.rollback()
                    if race_attempt:
                        raise ItemPolishError(
                            409,
                            "polish_submission_conflict",
                            "该账号的擦亮请求正在登记，请稍后刷新",
                        )
        raise RuntimeError("unreachable")

    async def _submit_once(
        self,
        db: AsyncSession,
        *,
        account_id: int,
        idempotency_key: str,
        goods_ids: tuple[int, ...],
        request_digest: str,
    ) -> ItemPolishSubmission:
        account = (
            await db.execute(
                select(XianyuAccount)
                .where(
                    XianyuAccount.id == account_id,
                    XianyuAccount.deleted == 0,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if account is None:
            await db.rollback()
            raise ItemPolishError(404, "polish_account_not_found", "闲鱼账号不存在或已删除")
        if int(account.status or 0) != 1:
            await db.rollback()
            raise ItemPolishError(409, "polish_account_disabled", "账号已禁用，不能执行商品擦亮")

        existing = (
            await db.execute(
                select(ItemPolishTask)
                .where(ItemPolishTask.idempotency_key == idempotency_key)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            if (
                int(existing.account_id) != account_id
                or str(existing.request_digest) != request_digest
            ):
                await db.rollback()
                raise ItemPolishError(
                    409,
                    "polish_idempotency_conflict",
                    "该幂等键已用于其他账号或商品范围，请刷新后重试",
                )

        day_start, _ = _business_day_bounds()
        candidates = list(
            (
                await db.execute(
                    select(ItemPolishTask)
                    .where(
                        ItemPolishTask.account_id == account_id,
                        or_(
                            ItemPolishTask.status.in_(_BLOCKING_TASK_STATUSES),
                            (
                                (ItemPolishTask.request_digest == request_digest)
                                & (ItemPolishTask.created_time >= day_start)
                            ),
                        ),
                    )
                    .order_by(ItemPolishTask.id.asc())
                    .with_for_update()
                )
            ).scalars().all()
        )
        for candidate in candidates:
            await self._reconcile_expired_locked(db, candidate)

        blocking_tasks = [
            candidate
            for candidate in candidates
            if str(candidate.status or "pending") in _BLOCKING_TASK_STATUSES
        ]
        same_scope_blockers = [
            candidate
            for candidate in blocking_tasks
            if str(candidate.request_digest) == request_digest
        ]
        if len(blocking_tasks) == 1 and same_scope_blockers:
            submission = await self._prepare_existing(db, same_scope_blockers[0])
            await db.commit()
            return submission
        if blocking_tasks:
            priority = {"unknown": 0, "needs_verification": 1, "running": 2, "pending": 3}
            blocker = min(
                blocking_tasks,
                key=lambda task: (priority.get(str(task.status), 9), int(task.id)),
            )
            view = await self._view(db, blocker)
            await db.commit()
            raise ItemPolishError(
                409,
                "polish_account_task_conflict",
                view.message,
                data={"existingTask": view.to_data()},
            )

        if existing is not None:
            submission = await self._prepare_existing(db, existing)
            await db.commit()
            return submission

        same_scope = next(
            (
                candidate
                for candidate in reversed(candidates)
                if str(candidate.request_digest) == request_digest
                and str(candidate.status) != "completed"
            ),
            None,
        )
        if same_scope is not None:
            submission = await self._prepare_existing(db, same_scope)
            await db.commit()
            return submission

        await self._validate_auth(db, account_id)
        goods = await self._eligible_goods(db, account_id, goods_ids)
        retry_blocker = await self._manual_retry_blocker(
            db,
            account_id=account_id,
            external_goods_ids=tuple(
                str(goods_row.external_goods_id) for goods_row in goods
            ),
        )
        if retry_blocker is not None:
            view = await self._view(db, retry_blocker)
            await db.commit()
            raise ItemPolishError(
                409,
                "polish_same_day_unknown_retry_blocked",
                "该范围包含今天曾出现未知结果且人工确认未擦亮的商品；为防止迟到请求造成重复操作，今天不再自动擦亮，请次日创建新任务",
                data={"existingTask": view.to_data()},
            )
        confirmed_today = await self._confirmed_targets_today(
            db,
            account_id=account_id,
            external_goods_ids=tuple(
                str(goods_row.external_goods_id) for goods_row in goods
            ),
        )
        pending_goods_count = sum(
            str(goods_row.external_goods_id) not in confirmed_today
            for goods_row in goods
        )
        already_confirmed_count = len(goods) - pending_goods_count
        created_at = _now()
        task = ItemPolishTask(
            task_id=f"polish-{uuid.uuid4().hex}",
            account_id=account_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            status="pending" if pending_goods_count else "completed",
            retry_safe=1 if pending_goods_count else 0,
            total_count=len(goods),
            processed_count=already_confirmed_count,
            polished_count=0,
            already_done_count=already_confirmed_count,
            failed_count=0,
            unknown_count=0,
            finished_time=None if pending_goods_count else _now(),
            created_time=created_at,
            updated_time=created_at,
        )
        db.add(task)
        await db.flush()
        for goods_row in goods:
            external_goods_id = str(goods_row.external_goods_id)
            previous_confirmation = confirmed_today.get(external_goods_id)
            db.add(
                ItemPolishTaskItem(
                    task_db_id=int(task.id),
                    goods_id=int(goods_row.id),
                    account_id=account_id,
                    external_goods_id=external_goods_id,
                    title_snapshot=str(goods_row.title or "")[:500],
                    status="already_done" if previous_confirmation else "pending",
                    retry_safe=0 if previous_confirmation else 1,
                    remote_confirmed_at=previous_confirmation,
                    last_error_code=(
                        "polish_already_confirmed_today"
                        if previous_confirmation
                        else None
                    ),
                    error_message=(
                        "该平台商品今日已有已确认擦亮记录，本任务未重复调用平台"
                        if previous_confirmation
                        else None
                    ),
                    created_time=created_at,
                    updated_time=created_at,
                )
            )
        await db.commit()
        async with self._sessions() as read_db:
            stored = await self._task_by_public_id(read_db, task.task_id)
            return ItemPolishSubmission(
                task=await self._view(read_db, stored),
                should_start=bool(pending_goods_count),
            )

    async def _prepare_existing(
        self,
        db: AsyncSession,
        task: ItemPolishTask,
    ) -> ItemPolishSubmission:
        await self._reconcile_expired_locked(db, task)
        status = str(task.status or "pending")
        if status in {"completed", "unknown", "running"}:
            return ItemPolishSubmission(await self._view(db, task), False)
        if status in {"partial", "failed", "needs_verification"}:
            items = list(
                (
                    await db.execute(
                        select(ItemPolishTaskItem)
                        .where(ItemPolishTaskItem.task_db_id == task.id)
                        .with_for_update()
                    )
                ).scalars().all()
            )
            # Heal rows written by the earlier implementation, which allowed
            # an unknown platform call that was manually observed as "not
            # polished" to be retried immediately. Such a row is quarantined
            # for the rest of the Shanghai business day.
            for item in items:
                if str(item.last_error_code or "") == _MANUAL_NOT_POLISHED_CODE:
                    item.status = "failed"
                    item.retry_safe = 0
                    item.lease_token = None
                    item.error_message = (
                        "已在闲鱼 App 人工确认未擦亮；为防止迟到请求重复操作，"
                        "本日不再自动重试，请次日创建新任务"
                    )
            retryable_items = [
                item
                for item in items
                if str(item.status) in {"failed", "needs_verification"}
                and bool(item.retry_safe)
            ]
            if not retryable_items:
                task.retry_safe = 0
                return ItemPolishSubmission(await self._view(db, task), False)
            other_tasks = list(
                (
                    await db.execute(
                        select(ItemPolishTask)
                        .where(
                            ItemPolishTask.account_id == task.account_id,
                            ItemPolishTask.id != task.id,
                            ItemPolishTask.status.in_(
                                ["pending", "running", "needs_verification", "unknown"]
                            ),
                        )
                        .order_by(ItemPolishTask.created_time.desc(), ItemPolishTask.id.desc())
                        .with_for_update()
                    )
                ).scalars().all()
            )
            blocking_task = None
            for candidate in other_tasks:
                await self._reconcile_expired_locked(db, candidate)
                if str(candidate.status) in {
                    "pending",
                    "running",
                    "needs_verification",
                    "unknown",
                }:
                    blocking_task = candidate
                    break
            if blocking_task is not None:
                view = await self._view(db, blocking_task)
                await db.commit()
                raise ItemPolishError(
                    409,
                    "polish_account_task_conflict",
                    view.message,
                    data={"existingTask": view.to_data()},
                )
            await self._validate_auth(db, int(task.account_id))
            for item in items:
                if str(item.status) in {"failed", "needs_verification"} and bool(item.retry_safe):
                    item.status = "pending"
                    item.last_error_code = None
                    item.error_message = None
                    item.lease_token = None
            pending_items = [item for item in items if str(item.status) == "pending"]
            confirmed_today = await self._confirmed_targets_today(
                db,
                account_id=int(task.account_id),
                external_goods_ids=tuple(
                    str(item.external_goods_id) for item in pending_items
                ),
            )
            for item in pending_items:
                previous_confirmation = confirmed_today.get(str(item.external_goods_id))
                if previous_confirmation is None:
                    continue
                item.status = "already_done"
                item.retry_safe = 0
                item.remote_confirmed_at = previous_confirmation
                item.last_error_code = "polish_already_confirmed_today"
                item.error_message = (
                    "该平台商品今日已有已确认擦亮记录，本任务未重复调用平台"
                )
            await self._sync_counts(db, task)
            if any(str(item.status) == "pending" for item in items):
                task.status = "pending"
                task.retry_safe = 1
                task.finished_time = None
                task.last_error_code = None
                task.error_message = None
                should_start = True
            else:
                task.status = (
                    "completed"
                    if int(task.failed_count or 0) == 0
                    else (
                        "partial"
                        if int(task.polished_count or 0) + int(task.already_done_count or 0) > 0
                        else "failed"
                    )
                )
                task.retry_safe = 0
                task.finished_time = _now()
                self._release_task(task)
                should_start = False
            return ItemPolishSubmission(await self._view(db, task), should_start)
        return ItemPolishSubmission(await self._view(db, task), status == "pending")

    async def progress(self, task_id: str) -> ItemPolishTaskView:
        async with self._sessions() as db:
            task = (
                await db.execute(
                    select(ItemPolishTask)
                    .where(ItemPolishTask.task_id == task_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if task is None:
                await db.rollback()
                raise ItemPolishError(404, "polish_task_not_found", "擦亮任务不存在或已清理")
            await self._reconcile_expired_locked(db, task)
            await db.commit()
        async with self._sessions() as read_db:
            stored = await self._task_by_public_id(read_db, task_id)
            return await self._view(read_db, stored)

    async def reconcile_unknown(
        self,
        *,
        task_id: str,
        decisions: tuple[ItemPolishReconcileDecision, ...],
    ) -> ItemPolishTaskView:
        async with self._sessions() as db:
            account_id = (
                await db.execute(
                    select(ItemPolishTask.account_id).where(
                        ItemPolishTask.task_id == task_id
                    )
                )
            ).scalar_one_or_none()
            if account_id is None:
                await db.rollback()
                raise ItemPolishError(404, "polish_task_not_found", "擦亮任务不存在")

            account = (
                await db.execute(
                    select(XianyuAccount)
                    .where(XianyuAccount.id == int(account_id))
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                await db.rollback()
                raise ItemPolishError(404, "polish_account_not_found", "闲鱼账号不存在或已删除")
            task = (
                await db.execute(
                    select(ItemPolishTask)
                    .where(
                        ItemPolishTask.task_id == task_id,
                        ItemPolishTask.account_id == int(account_id),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if task is None:
                await db.rollback()
                raise ItemPolishError(404, "polish_task_not_found", "擦亮任务不存在")
            await self._reconcile_expired_locked(db, task)
            now = _now()
            if (
                str(task.status) == "running"
                or (task.lease_until is not None and task.lease_until > now)
            ):
                await db.rollback()
                raise ItemPolishError(
                    409,
                    "polish_reconcile_lease_active",
                    "擦亮任务仍由执行器处理，请等待当前租约结束后再人工对账",
                )

            items = list(
                (
                    await db.execute(
                        select(ItemPolishTaskItem)
                        .where(ItemPolishTaskItem.task_db_id == task.id)
                        .order_by(ItemPolishTaskItem.id.asc())
                        .with_for_update()
                    )
                ).scalars().all()
            )
            if any(str(item.status) == "in_progress" for item in items):
                await db.rollback()
                raise ItemPolishError(
                    409,
                    "polish_reconcile_item_in_progress",
                    "仍有商品正在等待平台确认，请等待租约结束后刷新任务状态",
                )
            items_by_goods_id = {int(item.goods_id): item for item in items}
            requested_ids = {int(decision.goods_id) for decision in decisions}
            if not requested_ids.issubset(items_by_goods_id):
                await db.rollback()
                raise ItemPolishError(
                    409,
                    "polish_reconcile_goods_mismatch",
                    "部分商品不属于该擦亮任务，请刷新任务详情后逐项核对",
                )

            has_new_decision = False
            for decision in decisions:
                item = items_by_goods_id[int(decision.goods_id)]
                status = str(item.status)
                error_code = str(item.last_error_code or "")
                expected_status = (
                    "confirmed"
                    if decision.outcome == "confirmed_polished"
                    else "failed"
                )
                expected_code = (
                    _MANUAL_CONFIRMED_CODE
                    if decision.outcome == "confirmed_polished"
                    else _MANUAL_NOT_POLISHED_CODE
                )
                if status == expected_status and error_code == expected_code:
                    if decision.outcome == "confirmed_not_polished":
                        # Normalize idempotent replays of rows written by the
                        # previous unsafe immediate-retry behavior.
                        changed = bool(item.retry_safe) or item.error_message != (
                            "已在闲鱼 App 人工确认未擦亮；为防止迟到请求重复操作，"
                            "本日不再自动重试，请次日创建新任务"
                        )
                        item.retry_safe = 0
                        item.lease_token = None
                        item.error_message = (
                            "已在闲鱼 App 人工确认未擦亮；为防止迟到请求重复操作，"
                            "本日不再自动重试，请次日创建新任务"
                        )
                        if changed:
                            item.updated_time = now
                    continue
                if error_code in {
                    _MANUAL_CONFIRMED_CODE,
                    _MANUAL_NOT_POLISHED_CODE,
                }:
                    await db.rollback()
                    raise ItemPolishError(
                        409,
                        "polish_reconcile_outcome_conflict",
                        f"商品 {decision.goods_id} 已记录相反的人工对账结论，不能覆盖",
                    )
                if status != "unknown":
                    await db.rollback()
                    raise ItemPolishError(
                        409,
                        "polish_reconcile_item_not_unknown",
                        f"商品 {decision.goods_id} 当前不是未知结果，不能人工覆盖平台状态",
                    )
                if str(task.status) != "unknown":
                    await db.rollback()
                    raise ItemPolishError(
                        409,
                        "polish_reconcile_task_not_unknown",
                        "仅结果未知的擦亮任务可执行人工对账",
                    )
                if (
                    decision.outcome == "confirmed_not_polished"
                    and item.remote_confirmed_at is not None
                ):
                    await db.rollback()
                    raise ItemPolishError(
                        409,
                        "polish_reconcile_confirmation_conflict",
                        f"商品 {decision.goods_id} 已有平台确认时间，不能标记为未擦亮",
                    )
                has_new_decision = True

            if has_new_decision:
                for decision in decisions:
                    item = items_by_goods_id[int(decision.goods_id)]
                    if str(item.status) != "unknown":
                        continue
                    item.lease_token = None
                    if decision.outcome == "confirmed_polished":
                        item.status = "confirmed"
                        item.retry_safe = 0
                        item.remote_confirmed_at = now
                        item.updated_time = now
                        item.last_error_code = _MANUAL_CONFIRMED_CODE
                        item.error_message = "已在闲鱼 App 人工核对并确认商品已擦亮"
                    else:
                        item.status = "failed"
                        item.retry_safe = 0
                        item.updated_time = now
                        item.last_error_code = _MANUAL_NOT_POLISHED_CODE
                        item.error_message = (
                            "已在闲鱼 App 人工确认未擦亮；为防止迟到请求重复操作，"
                            "本日不再自动重试，请次日创建新任务"
                        )

            await self._sync_counts(db, task)
            remaining_unknown = any(
                str(item.status) in {"unknown", "in_progress"} for item in items
            )
            if remaining_unknown:
                task.status = "unknown"
                task.retry_safe = 0
                task.last_error_code = "polish_manual_reconciliation_pending"
                task.error_message = (
                    f"仍有 {int(task.unknown_count or 0)} 件商品结果未知；"
                    "请继续在闲鱼 App 逐项核对，系统不会重试未知项"
                )
            else:
                retry_safe = any(
                    str(item.status) == "pending"
                    or (
                        str(item.status) in {"failed", "needs_verification"}
                        and bool(item.retry_safe)
                    )
                    for item in items
                )
                confirmed_count = int(task.polished_count or 0) + int(
                    task.already_done_count or 0
                )
                if int(task.failed_count or 0) == 0 and not retry_safe:
                    task.status = "completed"
                elif confirmed_count > 0:
                    task.status = "partial"
                else:
                    task.status = "failed"
                task.retry_safe = 1 if retry_safe else 0
                task.last_error_code = (
                    "polish_manual_reconciliation_retryable"
                    if retry_safe
                    else "polish_manual_reconciliation_completed"
                )
                task.error_message = (
                    "人工对账完成；请仅复用原任务和原幂等键继续安全项"
                    if retry_safe
                    else None
                )
            task.finished_time = now
            self._release_task(task)
            await db.commit()
            return await self._view(db, task)

    async def recoverable_task_ids(
        self,
        *,
        limit: int = 100,
    ) -> tuple[str, ...]:
        """Reconcile crash state and return only tasks safe to execute."""

        bounded_limit = max(1, min(int(limit), 500))
        async with self._sessions() as db:
            tasks = list(
                (
                    await db.execute(
                        select(ItemPolishTask)
                        .where(ItemPolishTask.status.in_(["pending", "running"]))
                        .order_by(ItemPolishTask.id.asc())
                        .limit(bounded_limit)
                        .with_for_update(skip_locked=True)
                    )
                ).scalars().all()
            )
            recoverable: list[str] = []
            for task in tasks:
                await self._reconcile_expired_locked(db, task)
                if str(task.status) == "pending":
                    recoverable.append(str(task.task_id))
            await db.commit()
            return tuple(recoverable)

    async def acquire_run(self, task_id: str) -> ItemPolishRunLease | None:
        async with self._sessions() as db:
            account_id = (
                await db.execute(
                    select(ItemPolishTask.account_id).where(
                        ItemPolishTask.task_id == task_id
                    )
                )
            ).scalar_one_or_none()
            if account_id is None:
                await db.rollback()
                return None
            # Keep the same account -> task lock order used by submit. The
            # account row is the durable cross-replica execution mutex; task
            # leases remain the per-task crash-recovery ownership token.
            account = (
                await db.execute(
                    select(XianyuAccount)
                    .where(XianyuAccount.id == int(account_id))
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                await db.rollback()
                return None
            task = (
                await db.execute(
                    select(ItemPolishTask)
                    .where(
                        ItemPolishTask.task_id == task_id,
                        ItemPolishTask.account_id == int(account_id),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if task is None:
                await db.rollback()
                return None
            await self._reconcile_expired_locked(db, task)
            if str(task.status) != "pending":
                await db.commit()
                return None
            other_tasks = list(
                (
                    await db.execute(
                        select(ItemPolishTask)
                        .where(
                            ItemPolishTask.account_id == int(account_id),
                            ItemPolishTask.id != task.id,
                            ItemPolishTask.status.in_(_BLOCKING_TASK_STATUSES),
                        )
                        .order_by(ItemPolishTask.id.asc())
                        .with_for_update()
                    )
                ).scalars().all()
            )
            for other_task in other_tasks:
                await self._reconcile_expired_locked(db, other_task)
            if any(
                str(other_task.status) in {"running", "needs_verification", "unknown"}
                for other_task in other_tasks
            ):
                await db.commit()
                return None
            # Legacy races can leave more than one pending task. Deterministic
            # oldest-first ownership avoids both overlap and mutual starvation:
            # newer pending tasks wait, while the oldest may safely acquire.
            if any(
                str(other_task.status) == "pending" and int(other_task.id) < int(task.id)
                for other_task in other_tasks
            ):
                await db.commit()
                return None

            pending_external_ids = tuple(
                str(value)
                for value in (
                    await db.execute(
                        select(ItemPolishTaskItem.external_goods_id).where(
                            ItemPolishTaskItem.task_db_id == task.id,
                            ItemPolishTaskItem.status == "pending",
                        )
                    )
                ).scalars().all()
            )
            retry_blocker = await self._manual_retry_blocker(
                db,
                account_id=int(account_id),
                external_goods_ids=pending_external_ids,
            )
            if retry_blocker is not None and int(retry_blocker.id) != int(task.id):
                await db.commit()
                return None

            items = list(
                (
                    await db.execute(
                        select(ItemPolishTaskItem)
                        .where(ItemPolishTaskItem.task_db_id == task.id)
                        .order_by(ItemPolishTaskItem.id.asc())
                        .with_for_update()
                    )
                ).scalars().all()
            )
            pending_items = [item for item in items if str(item.status) == "pending"]
            confirmed_today = await self._confirmed_targets_today(
                db,
                account_id=int(account_id),
                external_goods_ids=tuple(
                    str(item.external_goods_id) for item in pending_items
                ),
            )
            for item in pending_items:
                previous_confirmation = confirmed_today.get(str(item.external_goods_id))
                if previous_confirmation is None:
                    continue
                item.status = "already_done"
                item.retry_safe = 0
                item.remote_confirmed_at = previous_confirmation
                item.last_error_code = "polish_already_confirmed_today"
                item.error_message = (
                    "该平台商品今日已有已确认擦亮记录，本任务未重复调用平台"
                )
            await self._sync_counts(db, task)
            if not any(str(item.status) == "pending" for item in items):
                task.status = (
                    "completed"
                    if int(task.failed_count or 0) == 0
                    else (
                        "partial"
                        if int(task.polished_count or 0) + int(task.already_done_count or 0) > 0
                        else "failed"
                    )
                )
                task.retry_safe = 0
                task.finished_time = _now()
                self._release_task(task)
                await db.commit()
                return None
            token = uuid.uuid4().hex
            now = _now()
            task.status = "running"
            task.retry_safe = 0
            task.lease_token = token
            task.lease_until = now + dt.timedelta(seconds=self._lease_seconds)
            task.started_time = task.started_time or now
            task.finished_time = None
            await db.commit()
            return ItemPolishRunLease(task_id=task_id, lease_token=token)

    async def claim_next(
        self,
        lease: ItemPolishRunLease,
    ) -> ItemPolishContext | None:
        async with self._sessions() as db:
            task = await self._locked_task_for_lease(db, lease)
            item = (
                await db.execute(
                    select(ItemPolishTaskItem)
                    .where(
                        ItemPolishTaskItem.task_db_id == task.id,
                        ItemPolishTaskItem.status == "pending",
                    )
                    .order_by(ItemPolishTaskItem.id.asc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if item is None:
                await db.commit()
                return None
            now = _now()
            item.status = "in_progress"
            item.retry_safe = 0
            item.attempt_count = int(item.attempt_count or 0) + 1
            item.lease_token = lease.lease_token
            item.remote_started_at = now
            item.last_error_code = None
            item.error_message = None
            task.lease_until = now + dt.timedelta(seconds=self._lease_seconds)
            await db.commit()
            return ItemPolishContext(
                task_id=lease.task_id,
                item_attempt_id=int(item.id),
                goods_id=int(item.goods_id),
                account_id=int(item.account_id),
                external_goods_id=str(item.external_goods_id),
                lease_token=lease.lease_token,
            )

    async def record_result(
        self,
        lease: ItemPolishRunLease,
        item: ItemPolishContext,
        result: ItemPolishResult,
    ) -> None:
        async with self._sessions() as db:
            task = await self._locked_task_for_lease(db, lease)
            stored_item = await self._locked_item(db, task, item)
            now = _now()
            stored_item.status = result.status
            stored_item.retry_safe = 1 if result.retry_safe else 0
            stored_item.lease_token = None
            stored_item.last_error_code = (
                _safe_error_code(result.error_code, "polish_failed")
                if result.error_code
                else None
            )
            stored_item.error_message = (
                _safe_error_message(result.message, "商品擦亮未完成")
                if result.message
                else None
            )
            if result.status in {"confirmed", "already_done"}:
                stored_item.remote_confirmed_at = now
            if result.status == "unknown":
                task.status = "unknown"
                task.retry_safe = 0
                task.last_error_code = stored_item.last_error_code
                task.error_message = stored_item.error_message
                task.finished_time = now
                self._release_task(task)
            elif result.status == "needs_verification":
                task.status = "needs_verification"
                task.retry_safe = 1
                task.last_error_code = stored_item.last_error_code
                task.error_message = stored_item.error_message
                task.finished_time = now
                self._release_task(task)
            await self._sync_counts(db, task)
            await db.commit()

    async def mark_unknown(
        self,
        lease: ItemPolishRunLease,
        item: ItemPolishContext,
        result: ItemPolishResult,
    ) -> None:
        async with self._sessions() as db:
            task = (
                await db.execute(
                    select(ItemPolishTask)
                    .where(ItemPolishTask.task_id == lease.task_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if task is None:
                await db.rollback()
                raise ItemPolishError(404, "polish_attempt_not_found", "擦亮尝试不存在")
            stored_item = (
                await db.execute(
                    select(ItemPolishTaskItem)
                    .where(
                        ItemPolishTaskItem.id == item.item_attempt_id,
                        ItemPolishTaskItem.task_db_id == task.id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if stored_item is None:
                await db.rollback()
                raise ItemPolishError(404, "polish_attempt_not_found", "擦亮尝试不存在")
            if (
                str(task.status) != "running"
                or task.lease_token != lease.lease_token
                or str(stored_item.status) != "in_progress"
                or stored_item.lease_token != lease.lease_token
                or item.lease_token != lease.lease_token
            ):
                # A late runner may arrive after a confirmed result, manual
                # reconciliation, lease recovery, or a newer runner. Every
                # such state is monotonic: the stale lease is a no-op and may
                # never clear or overwrite the current owner/result.
                await db.commit()
                return
            stored_item.status = "unknown"
            stored_item.retry_safe = 0
            stored_item.lease_token = None
            stored_item.last_error_code = _safe_error_code(
                result.error_code,
                "polish_result_unknown",
            )
            stored_item.error_message = _safe_error_message(
                result.message,
                "平台擦亮结果未知，请先在闲鱼 App 核对",
            )
            task.status = "unknown"
            task.retry_safe = 0
            task.last_error_code = stored_item.last_error_code
            task.error_message = stored_item.error_message
            task.finished_time = _now()
            self._release_task(task)
            await self._sync_counts(db, task)
            await db.commit()

    async def finish(self, lease: ItemPolishRunLease) -> None:
        async with self._sessions() as db:
            task = (
                await db.execute(
                    select(ItemPolishTask)
                    .where(ItemPolishTask.task_id == lease.task_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if task is None:
                await db.rollback()
                raise ItemPolishError(404, "polish_task_not_found", "擦亮任务不存在")
            if str(task.status) in {"unknown", "needs_verification"}:
                await db.commit()
                return
            if task.lease_token != lease.lease_token:
                await db.rollback()
                raise ItemPolishError(409, "polish_task_lease_lost", "擦亮任务执行权已变化")
            await self._sync_counts(db, task)
            has_retryable_failure = (
                await db.execute(
                    select(ItemPolishTaskItem.id)
                    .where(
                        ItemPolishTaskItem.task_db_id == task.id,
                        ItemPolishTaskItem.status.in_(["failed", "needs_verification"]),
                        ItemPolishTaskItem.retry_safe == 1,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none() is not None
            if int(task.failed_count or 0) == 0:
                task.status = "completed"
                task.retry_safe = 0
            elif int(task.polished_count or 0) + int(task.already_done_count or 0) > 0:
                task.status = "partial"
                task.retry_safe = 1 if has_retryable_failure else 0
            else:
                task.status = "failed"
                task.retry_safe = 1 if has_retryable_failure else 0
            task.finished_time = _now()
            self._release_task(task)
            await db.commit()

    async def _eligible_goods(
        self,
        db: AsyncSession,
        account_id: int,
        goods_ids: tuple[int, ...],
    ) -> list[XianyuGoods]:
        query = select(XianyuGoods).where(
            XianyuGoods.account_id == account_id,
            XianyuGoods.deleted == 0,
            XianyuGoods.status == 1,
            XianyuGoods.external_goods_id.is_not(None),
            XianyuGoods.external_goods_id != "",
        )
        if goods_ids:
            query = query.where(XianyuGoods.id.in_(goods_ids))
        matched_goods = list(
            (await db.execute(query.order_by(XianyuGoods.id.asc()))).scalars().all()
        )
        if goods_ids and len(matched_goods) != len(goods_ids):
            await db.rollback()
            raise ItemPolishError(
                409,
                "polish_goods_not_eligible",
                "部分商品不存在、非在售或不属于该账号，请刷新商品列表后重试",
            )
        # The platform identity, not a local snapshot row, is the mutation
        # target. Legacy imports can leave multiple local rows for one Xianyu
        # item; keep the oldest eligible row as the representative and never
        # issue duplicate outbound calls for the shared external id.
        unique_by_external_id: dict[str, XianyuGoods] = {}
        for goods_row in matched_goods:
            external_id = str(goods_row.external_goods_id or "").strip()
            if external_id and external_id not in unique_by_external_id:
                unique_by_external_id[external_id] = goods_row
        goods = list(unique_by_external_id.values())
        if len(goods) > _MAX_ITEMS_PER_TASK:
            await db.rollback()
            raise ItemPolishError(
                422,
                "polish_scope_too_large",
                f"该账号有超过 {_MAX_ITEMS_PER_TASK} 件在售商品，请到商品管理页分批擦亮",
            )
        return list(goods)

    async def _confirmed_targets_today(
        self,
        db: AsyncSession,
        *,
        account_id: int,
        external_goods_ids: tuple[str, ...],
    ) -> dict[str, dt.datetime]:
        if not external_goods_ids:
            return {}
        day_start, day_end = _business_day_bounds()
        rows = (
            await db.execute(
                select(
                    ItemPolishTaskItem.external_goods_id,
                    ItemPolishTaskItem.remote_confirmed_at,
                )
                .where(
                    ItemPolishTaskItem.account_id == account_id,
                    ItemPolishTaskItem.external_goods_id.in_(external_goods_ids),
                    ItemPolishTaskItem.status.in_(["confirmed", "already_done"]),
                    ItemPolishTaskItem.remote_confirmed_at >= day_start,
                    ItemPolishTaskItem.remote_confirmed_at < day_end,
                )
                .order_by(ItemPolishTaskItem.remote_confirmed_at.desc())
            )
        ).all()
        confirmed: dict[str, dt.datetime] = {}
        for external_goods_id, confirmed_at in rows:
            normalized = str(external_goods_id or "").strip()
            if normalized and confirmed_at is not None and normalized not in confirmed:
                confirmed[normalized] = confirmed_at
        return confirmed

    async def _manual_retry_blocker(
        self,
        db: AsyncSession,
        *,
        account_id: int,
        external_goods_ids: tuple[str, ...],
    ) -> ItemPolishTask | None:
        """Return an unresolved unknown-call quarantine that overlaps the scope."""

        if not external_goods_ids:
            return None
        now = _now()
        day_start, _ = _business_day_bounds(now)
        lookback_start = day_start - dt.timedelta(
            seconds=_MANUAL_RETRY_QUIESCENCE_SECONDS
        )
        recent_window = or_(
            ItemPolishTaskItem.updated_time >= lookback_start,
            (
                ItemPolishTaskItem.updated_time.is_(None)
                & (ItemPolishTaskItem.remote_started_at >= lookback_start)
            ),
            (
                ItemPolishTaskItem.updated_time.is_(None)
                & ItemPolishTaskItem.remote_started_at.is_(None)
                & (ItemPolishTaskItem.created_time >= lookback_start)
            ),
        )
        candidates = list(
            (
                await db.execute(
                    select(ItemPolishTaskItem)
                    .where(
                        ItemPolishTaskItem.account_id == account_id,
                        ItemPolishTaskItem.external_goods_id.in_(external_goods_ids),
                        ItemPolishTaskItem.last_error_code == _MANUAL_NOT_POLISHED_CODE,
                        recent_window,
                    )
                    .order_by(
                        ItemPolishTaskItem.updated_time.desc(),
                        ItemPolishTaskItem.id.desc(),
                    )
                )
            ).scalars().all()
        )
        candidate = next(
            (
                item
                for item in candidates
                if now < _manual_retry_after(item)
            ),
            None,
        )
        if candidate is None:
            return None
        task = (
            await db.execute(
                select(ItemPolishTask)
                .where(ItemPolishTask.id == int(candidate.task_db_id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if task is None:
            return None
        locked_item = (
            await db.execute(
                select(ItemPolishTaskItem)
                .where(
                    ItemPolishTaskItem.id == int(candidate.id),
                    ItemPolishTaskItem.task_db_id == task.id,
                    ItemPolishTaskItem.account_id == account_id,
                    ItemPolishTaskItem.external_goods_id.in_(external_goods_ids),
                    ItemPolishTaskItem.last_error_code == _MANUAL_NOT_POLISHED_CODE,
                    recent_window,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if locked_item is None:
            return None
        return task if now < _manual_retry_after(
            locked_item,
            fallback=task.finished_time,
        ) else None

    async def _validate_auth(self, db: AsyncSession, account_id: int) -> None:
        auth = (
            await db.execute(
                select(XianyuAccountAuth).where(
                    XianyuAccountAuth.account_id == account_id,
                    XianyuAccountAuth.deleted == 0,
                )
            )
        ).scalar_one_or_none()
        if (
            auth is None
            or not auth.encrypted_cookie
            or int(auth.cookie_status or 0) != 1
        ):
            await db.rollback()
            raise ItemPolishError(
                409,
                "polish_account_auth_unavailable",
                "账号登录状态未确认可用，请先执行登录验证或重新扫码",
            )
        try:
            cookie = decrypt_cookie_if_needed(auth.encrypted_cookie)
            token = extract_token_from_cookie(cookie)
        except Exception:
            token = None
        if not token:
            await db.rollback()
            raise ItemPolishError(
                409,
                "polish_account_auth_invalid",
                "账号 Cookie 缺少有效签名令牌，请重新扫码登录",
            )

    async def _reconcile_expired_locked(
        self,
        db: AsyncSession,
        task: ItemPolishTask,
    ) -> None:
        if (
            str(task.status) != "running"
            or not task.lease_until
            or task.lease_until > _now()
        ):
            return
        items = (
            await db.execute(
                select(ItemPolishTaskItem)
                .where(ItemPolishTaskItem.task_db_id == task.id)
                .with_for_update()
            )
        ).scalars().all()
        in_progress = [item for item in items if str(item.status) == "in_progress"]
        if in_progress:
            for item in in_progress:
                item.status = "unknown"
                item.retry_safe = 0
                item.lease_token = None
                item.last_error_code = "polish_result_unknown_after_recovery"
                item.error_message = (
                    "服务中断前平台结果未确认；请先在闲鱼 App 核对，系统不会自动重试"
                )
            task.status = "unknown"
            task.retry_safe = 0
            task.last_error_code = "polish_result_unknown_after_recovery"
            task.error_message = in_progress[0].error_message
            task.finished_time = _now()
        else:
            task.status = "pending"
            task.retry_safe = 1
            task.last_error_code = "polish_worker_interrupted_before_remote"
            task.error_message = "执行器在下一件商品调用前中断，可使用原任务安全继续"
        self._release_task(task)
        await self._sync_counts(db, task)

    async def _sync_counts(self, db: AsyncSession, task: ItemPolishTask) -> None:
        statuses = list(
            (
                await db.execute(
                    select(ItemPolishTaskItem.status).where(
                        ItemPolishTaskItem.task_db_id == task.id
                    )
                )
            ).scalars().all()
        )
        task.total_count = len(statuses)
        task.processed_count = sum(status != "pending" for status in statuses)
        task.polished_count = statuses.count("confirmed")
        task.already_done_count = statuses.count("already_done")
        task.failed_count = statuses.count("failed") + statuses.count("needs_verification")
        task.unknown_count = statuses.count("unknown") + statuses.count("in_progress")

    async def _locked_task_for_lease(
        self,
        db: AsyncSession,
        lease: ItemPolishRunLease,
    ) -> ItemPolishTask:
        task = (
            await db.execute(
                select(ItemPolishTask)
                .where(ItemPolishTask.task_id == lease.task_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            task is None
            or str(task.status) != "running"
            or task.lease_token != lease.lease_token
        ):
            await db.rollback()
            raise ItemPolishError(409, "polish_task_lease_lost", "擦亮任务执行权已变化")
        return task

    async def _locked_item(
        self,
        db: AsyncSession,
        task: ItemPolishTask,
        context: ItemPolishContext,
    ) -> ItemPolishTaskItem:
        item = (
            await db.execute(
                select(ItemPolishTaskItem)
                .where(
                    ItemPolishTaskItem.id == context.item_attempt_id,
                    ItemPolishTaskItem.task_db_id == task.id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            item is None
            or str(item.status) != "in_progress"
            or item.lease_token != context.lease_token
        ):
            await db.rollback()
            raise ItemPolishError(409, "polish_item_lease_lost", "商品擦亮执行权已变化")
        return item

    async def _task_by_public_id(
        self,
        db: AsyncSession,
        task_id: str,
    ) -> ItemPolishTask:
        task = (
            await db.execute(
                select(ItemPolishTask).where(ItemPolishTask.task_id == task_id)
            )
        ).scalar_one_or_none()
        if task is None:
            raise ItemPolishError(404, "polish_task_not_found", "擦亮任务不存在")
        return task

    async def _view(
        self,
        db: AsyncSession,
        task: ItemPolishTask,
    ) -> ItemPolishTaskView:
        items = list(
            (
                await db.execute(
                    select(ItemPolishTaskItem)
                    .where(ItemPolishTaskItem.task_db_id == task.id)
                    .order_by(ItemPolishTaskItem.id.asc())
                )
            ).scalars().all()
        )
        status = str(task.status or "pending")
        total = int(task.total_count or 0)
        processed = int(task.processed_count or 0)
        progress = 100 if status == "completed" or total == 0 else min(99, int(processed * 100 / total))
        manual_not_polished_items = [
            item
            for item in items
            if str(item.last_error_code or "") == _MANUAL_NOT_POLISHED_CODE
        ]
        retry_after = None
        retry_quarantine_active = False
        if manual_not_polished_items:
            retry_deadlines = [
                _manual_retry_after(item, fallback=task.finished_time)
                for item in manual_not_polished_items
            ]
            retry_deadline = max(retry_deadlines)
            retry_after = retry_deadline.replace(tzinfo=_BUSINESS_TIMEZONE).isoformat()
            retry_quarantine_active = _now() < retry_deadline
        messages = {
            "pending": task.error_message or "擦亮请求已持久化，等待执行",
            "running": "正在逐件调用闲鱼擦亮接口，请勿重复提交",
            "completed": (
                f"擦亮完成：成功 {int(task.polished_count or 0)} 件，"
                f"今日已擦亮 {int(task.already_done_count or 0)} 件"
            ),
            "partial": (
                f"擦亮部分完成：已确认 {int(task.polished_count or 0) + int(task.already_done_count or 0)} 件，"
                f"明确失败 {int(task.failed_count or 0)} 件；可使用原任务重试失败项"
            ),
            "failed": task.error_message or "平台明确未完成擦亮；排除问题后可使用原任务重试",
            "needs_verification": task.error_message or "闲鱼要求安全验证；验证后使用原任务继续",
            "unknown": task.error_message or "平台擦亮结果未知，请先在闲鱼 App 核对；禁止自动重试",
        }
        if manual_not_polished_items and status in {"partial", "failed"}:
            if bool(task.retry_safe):
                messages[status] = (
                    "人工对账已确认部分未知项未擦亮；这些商品本日不再自动重试。"
                    "其他明确可重试项仍只能复用原任务处理"
                )
            elif retry_quarantine_active:
                messages[status] = (
                    "已人工确认未擦亮；为防止迟到的平台请求造成重复操作，"
                    "本日不再自动重试，请在下一个上海自然日创建新任务"
                )
            else:
                messages[status] = (
                    "旧任务已安全隔离且不可恢复；如需再次擦亮，请创建新任务和新幂等键"
                )
        recovery = {
            "pending": "resume_task",
            "partial": "retry_failed_items",
            "failed": "resolve_and_retry",
            "needs_verification": "complete_verification_then_resume",
            "unknown": "verify_in_xianyu_app",
        }.get(status)
        if manual_not_polished_items and status in {"partial", "failed"} and not bool(task.retry_safe):
            recovery = "retry_next_business_day"
        results = tuple(
            {
                "goodsId": int(item.goods_id),
                "title": str(item.title_snapshot or ""),
                "status": str(item.status),
                "message": item.error_message,
                "errorCode": item.last_error_code,
                "retrySafe": bool(item.retry_safe),
            }
            for item in items
        )
        return ItemPolishTaskView(
            task_id=str(task.task_id),
            account_id=int(task.account_id),
            idempotency_key=str(task.idempotency_key),
            status=status,  # type: ignore[arg-type]
            total=total,
            processed=processed,
            polished=int(task.polished_count or 0),
            already_done=int(task.already_done_count or 0),
            failed=int(task.failed_count or 0),
            unknown=int(task.unknown_count or 0),
            progress=progress,
            message=messages.get(status, "擦亮任务状态未知"),
            retry_safe=bool(task.retry_safe),
            recovery=recovery,
            results=results,
            retry_after=retry_after,
        )

    @staticmethod
    def _release_task(task: ItemPolishTask) -> None:
        task.lease_token = None
        task.lease_until = None


class XianyuItemPolishGateway:
    """True external adapter with explicit known/unknown outcome semantics."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def polish(self, context: ItemPolishContext) -> ItemPolishResult:
        async with self._sessions() as db:
            try:
                account = (
                    await db.execute(
                        select(XianyuAccount).where(
                            XianyuAccount.id == context.account_id,
                            XianyuAccount.deleted == 0,
                            XianyuAccount.status == 1,
                        )
                    )
                ).scalar_one_or_none()
                auth = (
                    await db.execute(
                        select(XianyuAccountAuth).where(
                            XianyuAccountAuth.account_id == context.account_id,
                            XianyuAccountAuth.deleted == 0,
                        )
                    )
                ).scalar_one_or_none()
                goods = (
                    await db.execute(
                        select(XianyuGoods).where(
                            XianyuGoods.id == context.goods_id,
                            XianyuGoods.account_id == context.account_id,
                            XianyuGoods.deleted == 0,
                            XianyuGoods.status == 1,
                            XianyuGoods.external_goods_id == context.external_goods_id,
                        )
                    )
                ).scalar_one_or_none()
                # SQLAlchemy expires every ORM instance on rollback, even
                # when the session factory uses expire_on_commit=False. Take
                # an explicit immutable snapshot while the session is still
                # active; the outbound adapter must never depend on detached
                # ORM state.
                account_eligible = account is not None
                goods_eligible = goods is not None
                encrypted_cookie = str(auth.encrypted_cookie or "") if auth is not None else ""
                cookie_status = int(auth.cookie_status or 0) if auth is not None else 0
                is_fish_shop = bool(getattr(account, "fish_shop", False)) if account is not None else False
                await db.rollback()
            except Exception:
                await db.rollback()
                return ItemPolishResult.failed(
                    "polish_context_unavailable",
                    "无法读取账号或商品状态，平台擦亮未执行",
                )

        if not account_eligible or not goods_eligible:
            return ItemPolishResult.failed(
                "polish_target_not_eligible",
                "账号已禁用或商品已非在售状态，平台擦亮未执行",
            )
        if (
            not encrypted_cookie
            or cookie_status != 1
        ):
            return ItemPolishResult.failed(
                "polish_account_auth_unavailable",
                "账号登录状态未确认可用，平台擦亮未执行；请重新登录",
            )
        try:
            cookie = decrypt_cookie_if_needed(encrypted_cookie)
            operator = XianyuItemOperator(
                cookie,
                is_fish_shop=is_fish_shop,
            )
        except Exception:
            return ItemPolishResult.failed(
                "polish_account_auth_invalid",
                "账号认证信息无效，平台擦亮未执行；请重新登录",
            )

        try:
            result = await asyncio.to_thread(operator.polish, context.external_goods_id)
        except requests.exceptions.Timeout:
            return ItemPolishResult.unknown(
                "polish_platform_timeout_unknown",
                "平台请求超时，擦亮结果未知；请先在闲鱼 App 核对，系统不会自动重试",
            )
        except requests.exceptions.ConnectionError:
            return ItemPolishResult.unknown(
                "polish_platform_connection_unknown",
                "平台连接中断，擦亮结果未知；请先在闲鱼 App 核对，系统不会自动重试",
            )
        except requests.exceptions.HTTPError as exc:
            status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
            return ItemPolishResult.unknown(
                f"polish_platform_http_{status}_unknown"
                if status
                else "polish_platform_http_unknown",
                "平台 HTTP 响应无法证明擦亮未执行；请先在闲鱼 App 核对，系统不会自动重试",
            )
        except Exception:
            return ItemPolishResult.unknown(
                "polish_platform_result_unknown",
                "平台擦亮结果无法确认；请先在闲鱼 App 核对，系统不会自动重试",
            )

        if result.get("success") is True:
            return ItemPolishResult.confirmed(already_done=bool(result.get("already_done")))
        if result.get("need_manual") is True:
            return ItemPolishResult.verification_required()
        error_code = str(result.get("error_code") or result.get("errorCode") or "").strip()
        if error_code:
            return ItemPolishResult.failed(
                _safe_error_code(error_code, "polish_platform_rejected"),
                str(result.get("error") or "平台明确未完成擦亮；请检查账号与商品状态"),
            )
        return ItemPolishResult.unknown(
            "polish_platform_confirmation_missing",
            "平台未返回可确认的擦亮结果；请先在闲鱼 App 核对",
        )


def _production_scheduler(coroutine: Coroutine[Any, Any, None], name: str) -> None:
    spawn_background_task(coroutine, name=name)


def build_item_polish_module(
    session_factory: async_sessionmaker[AsyncSession],
) -> ItemPolishModule:
    return ItemPolishModule(
        store=SqlItemPolishStore(session_factory),
        gateway=XianyuItemPolishGateway(session_factory),
        scheduler=_production_scheduler,
    )


_item_polish_recovery_task: asyncio.Task[None] | None = None
_item_polish_recovery_stop: asyncio.Event | None = None


async def _item_polish_recovery_loop(
    module: ItemPolishModule,
    stop: asyncio.Event,
    *,
    poll_seconds: float,
) -> None:
    logger.info("Item polish recovery worker started")
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
                continue
            except TimeoutError:
                pass
            try:
                await module.recover_due_tasks()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Durable pending rows remain recoverable. A transient scan
                # failure must not terminate the worker or cause a blind retry
                # of an in-progress platform call.
                logger.error("Item polish recovery scan failed", exc_info=True)
    finally:
        logger.info("Item polish recovery worker stopped")


async def start_item_polish_recovery_worker(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    poll_seconds: float = 15.0,
) -> int:
    """Run startup catch-up, then continuously recover durable safe work."""

    global _item_polish_recovery_task, _item_polish_recovery_stop
    if (
        _item_polish_recovery_task is not None
        and not _item_polish_recovery_task.done()
    ):
        return 0

    module = build_item_polish_module(session_factory)
    recovered = 0
    try:
        # Await the first scan so startup does not depend on a browser tab or a
        # later API request to rediscover committed pending rows.
        recovered = await module.recover_due_tasks()
    except Exception:
        logger.error("Item polish startup recovery scan failed", exc_info=True)

    stop = asyncio.Event()
    _item_polish_recovery_stop = stop
    _item_polish_recovery_task = asyncio.create_task(
        _item_polish_recovery_loop(
            module,
            stop,
            poll_seconds=max(0.1, float(poll_seconds)),
        ),
        name="item-polish-recovery",
    )
    return recovered


async def stop_item_polish_recovery_worker() -> None:
    """Stop and drain the explicitly owned long-running recovery poller."""

    global _item_polish_recovery_task, _item_polish_recovery_stop
    task = _item_polish_recovery_task
    if task is None:
        return
    if _item_polish_recovery_stop is not None:
        _item_polish_recovery_stop.set()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=10)
    except TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    finally:
        _item_polish_recovery_task = None
        _item_polish_recovery_stop = None
