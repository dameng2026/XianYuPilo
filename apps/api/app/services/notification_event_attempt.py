"""Durable at-most-once coordination for automatic notification events.

The public seam is deliberately small: callers execute one metadata-only event
intent or explicitly resolve the latest generation after verified recovery.
Payloads and channel credentials never cross this module boundary.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import uuid
from dataclasses import dataclass, replace
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import NotificationEventAttempt, NotificationEventTargetMutex

logger = logging.getLogger(__name__)

_EVENT_TYPE_PATTERN = re.compile(r"^[a-z0-9_.:-]{1,64}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class NotificationEventAttemptError(RuntimeError):
    """A bounded state-machine or persistence error."""


@dataclass(frozen=True, slots=True)
class NotificationDispatchOutcome:
    """What is known about one dispatcher invocation."""

    called: bool
    delivered: bool
    outcome_known: bool

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, bool)
            for value in (self.called, self.delivered, self.outcome_known)
        ):
            raise ValueError("dispatch outcome fields must be booleans")
        if self.delivered and (not self.called or not self.outcome_known):
            raise ValueError("delivered requires a called, known outcome")
        if not self.called and not self.outcome_known:
            raise ValueError("a non-call is always a known local outcome")

    @property
    def outcomeKnown(self) -> bool:
        """Camel-case compatibility for dispatcher result consumers."""

        return self.outcome_known


@dataclass(frozen=True, slots=True)
class NotificationEventCommand:
    event_type: str
    account_id: int
    target_digest: str
    generation_ttl_seconds: int | None = None

    def __post_init__(self) -> None:
        event_type = str(self.event_type or "").strip().casefold()
        target_digest = str(self.target_digest or "").strip().casefold()
        account_id = int(self.account_id)
        if not _EVENT_TYPE_PATTERN.fullmatch(event_type):
            raise ValueError("event_type is invalid")
        if account_id <= 0:
            raise ValueError("account_id must be positive")
        if not _DIGEST_PATTERN.fullmatch(target_digest):
            raise ValueError("target_digest must be a SHA-256 hex digest")
        ttl = self.generation_ttl_seconds
        if ttl is not None and not 1 <= int(ttl) <= 7 * 24 * 60 * 60:
            raise ValueError("generation_ttl_seconds is invalid")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "target_digest", target_digest)
        object.__setattr__(
            self,
            "generation_ttl_seconds",
            None if ttl is None else int(ttl),
        )


@dataclass(frozen=True, slots=True)
class NotificationEventLease:
    attempt_id: int
    event_type: str
    account_id: int
    target_digest: str
    generation: int
    generation_ttl_seconds: int | None
    state: str
    action: str
    lease_token: str | None
    attempt_count: int
    called: bool
    delivered: bool
    outcome_known: bool
    error_code: str | None = None
    repeated: bool = False


@dataclass(frozen=True, slots=True)
class NotificationEventOutcome:
    status: str
    attempt_id: int
    generation: int
    attempt_count: int
    called: bool
    delivered: bool
    outcome_known: bool
    error_code: str | None = None
    repeated: bool = False


SessionFactory = Callable[[], AsyncSession]
Clock = Callable[[], dt.datetime]
RemoteSend = Callable[[], Awaitable[NotificationDispatchOutcome]]


class SqlNotificationEventAttemptStore:
    """SQL-backed event generation state machine.

    Every method owns a short transaction. In particular, ``acquire`` commits
    the pending lease and ``mark_send_started`` commits the irreversible send
    boundary before the caller may touch a remote transport.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        now: Clock | None = None,
        lease_seconds: int = 60,
        retry_backoff_seconds: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or dt.datetime.utcnow
        self.lease_seconds = max(5, min(int(lease_seconds), 300))
        self.retry_backoff_seconds = max(
            5, min(int(retry_backoff_seconds), 60 * 60)
        )

    async def acquire(self, command: NotificationEventCommand) -> NotificationEventLease:
        for retry in range(4):
            try:
                return await self._acquire_once(command)
            except IntegrityError:
                if retry == 3:
                    raise
            except OperationalError as exc:
                if retry == 3 or not self._retryable_operational_error(exc):
                    raise
            await asyncio.sleep(0.01 * (retry + 1))
        raise RuntimeError("unreachable")

    async def _acquire_once(
        self, command: NotificationEventCommand
    ) -> NotificationEventLease:
        async with self._session_factory() as db:
            try:
                target = (
                    await db.execute(
                        select(NotificationEventTargetMutex)
                        .where(
                            NotificationEventTargetMutex.event_type
                            == command.event_type,
                            NotificationEventTargetMutex.account_id
                            == command.account_id,
                            NotificationEventTargetMutex.target_digest
                            == command.target_digest,
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if target is None:
                    target = NotificationEventTargetMutex(
                        event_type=command.event_type,
                        account_id=command.account_id,
                        target_digest=command.target_digest,
                    )
                    db.add(target)
                    await db.flush()

                latest = await self._latest_locked(db, target, command)
                if latest is None:
                    return await self._create_generation(db, target, command, None)

                state = str(latest.state or "pending")
                now = self._now()
                if state == "confirmed":
                    if latest.generation_expires_at and latest.generation_expires_at <= now:
                        latest.state = "expired"
                        latest.last_error_code = None
                        self._release(latest)
                        return await self._create_generation(db, target, command, latest)
                    await db.commit()
                    return self._lease(latest, command, "return", repeated=True)

                if state == "unknown":
                    await db.commit()
                    return self._lease(latest, command, "return", repeated=True)

                if state in {"resolved", "expired"}:
                    return await self._create_generation(db, target, command, latest)

                if state == "send_started":
                    if self._lease_active(latest, now):
                        await db.commit()
                        return self._lease(
                            latest, command, "in_progress", repeated=True
                        )
                    latest.state = "unknown"
                    latest.provider_called = 1
                    latest.delivered = 0
                    latest.outcome_known = 0
                    latest.last_error_code = "send_result_unknown_after_lease"
                    self._release(latest)
                    await db.commit()
                    return self._lease(latest, command, "return", repeated=True)

                if state == "pending":
                    if self._lease_active(latest, now):
                        await db.commit()
                        return self._lease(
                            latest, command, "in_progress", repeated=True
                        )
                    if latest.send_started_at is not None:
                        latest.state = "unknown"
                        latest.provider_called = 1
                        latest.delivered = 0
                        latest.outcome_known = 0
                        latest.last_error_code = "pending_send_boundary_inconsistent"
                        self._release(latest)
                        await db.commit()
                        return self._lease(latest, command, "return", repeated=True)
                    return await self._reclaim(db, latest, command)

                if state == "failed":
                    if latest.next_retry_at and latest.next_retry_at > now:
                        await db.commit()
                        return self._lease(latest, command, "backoff", repeated=True)
                    return await self._reclaim(db, latest, command)

                latest.state = "unknown"
                latest.provider_called = 1 if latest.send_started_at else 0
                latest.delivered = 0
                latest.outcome_known = 0
                latest.last_error_code = "invalid_notification_event_state"
                self._release(latest)
                await db.commit()
                return self._lease(latest, command, "return", repeated=True)
            except BaseException:
                await db.rollback()
                raise

    async def _latest_locked(
        self,
        db: AsyncSession,
        target: NotificationEventTargetMutex,
        command: NotificationEventCommand,
    ) -> NotificationEventAttempt | None:
        latest = None
        if target.latest_attempt_id is not None:
            latest = (
                await db.execute(
                    select(NotificationEventAttempt)
                    .where(NotificationEventAttempt.id == target.latest_attempt_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        if latest is None:
            latest = (
                await db.execute(
                    select(NotificationEventAttempt)
                    .where(
                        NotificationEventAttempt.event_type == command.event_type,
                        NotificationEventAttempt.account_id == command.account_id,
                        NotificationEventAttempt.target_digest == command.target_digest,
                    )
                    .order_by(
                        NotificationEventAttempt.generation.desc(),
                        NotificationEventAttempt.id.desc(),
                    )
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            target.latest_attempt_id = None if latest is None else int(latest.id)
        if latest is not None and (
            str(latest.event_type) != command.event_type
            or int(latest.account_id) != command.account_id
            or str(latest.target_digest) != command.target_digest
        ):
            raise NotificationEventAttemptError(
                "notification event target pointer is inconsistent"
            )
        return latest

    async def _create_generation(
        self,
        db: AsyncSession,
        target: NotificationEventTargetMutex,
        command: NotificationEventCommand,
        previous: NotificationEventAttempt | None,
    ) -> NotificationEventLease:
        now = self._now()
        attempt = NotificationEventAttempt(
            event_type=command.event_type,
            account_id=command.account_id,
            target_digest=command.target_digest,
            generation=1 if previous is None else int(previous.generation) + 1,
            state="pending",
            attempt_count=1,
            lease_token=uuid.uuid4().hex,
            lease_until=now + dt.timedelta(seconds=self.lease_seconds),
            provider_called=0,
            delivered=0,
            outcome_known=1,
        )
        db.add(attempt)
        await db.flush()
        target.latest_attempt_id = int(attempt.id)
        await db.commit()
        return self._lease(attempt, command, "send")

    async def _reclaim(
        self,
        db: AsyncSession,
        attempt: NotificationEventAttempt,
        command: NotificationEventCommand,
    ) -> NotificationEventLease:
        now = self._now()
        attempt.state = "pending"
        attempt.attempt_count = int(attempt.attempt_count or 0) + 1
        attempt.lease_token = uuid.uuid4().hex
        attempt.lease_until = now + dt.timedelta(seconds=self.lease_seconds)
        attempt.send_started_at = None
        attempt.confirmed_at = None
        attempt.generation_expires_at = None
        attempt.next_retry_at = None
        attempt.provider_called = 0
        attempt.delivered = 0
        attempt.outcome_known = 1
        attempt.last_error_code = None
        await db.commit()
        return self._lease(attempt, command, "send", repeated=True)

    async def mark_send_started(
        self, lease: NotificationEventLease
    ) -> NotificationEventLease:
        async with self._session_factory() as db:
            attempt = await self._locked(db, lease, require_active=True)
            attempt.state = "send_started"
            attempt.send_started_at = self._now()
            attempt.provider_called = 1
            attempt.delivered = 0
            attempt.outcome_known = 0
            attempt.last_error_code = None
            await db.commit()
            return self._lease_from_lease(attempt, lease, "send")

    async def mark_confirmed(
        self, lease: NotificationEventLease
    ) -> NotificationEventLease:
        async with self._session_factory() as db:
            attempt = await self._locked(db, lease, require_active=True)
            now = self._now()
            attempt.state = "confirmed"
            attempt.confirmed_at = now
            attempt.generation_expires_at = (
                None
                if lease.generation_ttl_seconds is None
                else now + dt.timedelta(seconds=lease.generation_ttl_seconds)
            )
            attempt.next_retry_at = None
            attempt.provider_called = 1
            attempt.delivered = 1
            attempt.outcome_known = 1
            attempt.last_error_code = None
            self._release(attempt)
            await db.commit()
            return self._lease_from_lease(attempt, lease, "return")

    async def mark_failed(
        self,
        lease: NotificationEventLease,
        *,
        called: bool,
        code: str,
    ) -> NotificationEventLease:
        async with self._session_factory() as db:
            attempt = await self._locked(db, lease, require_active=False)
            attempt.state = "failed"
            attempt.next_retry_at = self._now() + dt.timedelta(
                seconds=self.retry_backoff_seconds
            )
            attempt.provider_called = 1 if called else 0
            attempt.delivered = 0
            attempt.outcome_known = 1
            attempt.last_error_code = self._safe_code(code)
            self._release(attempt)
            await db.commit()
            return self._lease_from_lease(attempt, lease, "return")

    async def mark_unknown(
        self, lease: NotificationEventLease, *, code: str
    ) -> NotificationEventLease:
        async with self._session_factory() as db:
            attempt = await self._locked(db, lease, require_active=False)
            attempt.state = "unknown"
            attempt.next_retry_at = None
            attempt.provider_called = 1
            attempt.delivered = 0
            attempt.outcome_known = 0
            attempt.last_error_code = self._safe_code(code)
            self._release(attempt)
            await db.commit()
            return self._lease_from_lease(attempt, lease, "return")

    async def resolve(
        self,
        event_type: str,
        account_id: int,
        target_digest: str | None = None,
        *,
        resolution_code: str = "explicit_clear",
    ) -> int:
        normalized_event = str(event_type or "").strip().casefold()
        normalized_digest = (
            None if target_digest is None else str(target_digest).strip().casefold()
        )
        if not _EVENT_TYPE_PATTERN.fullmatch(normalized_event):
            raise ValueError("event_type is invalid")
        if int(account_id) <= 0:
            raise ValueError("account_id must be positive")
        if normalized_digest is not None and not _DIGEST_PATTERN.fullmatch(
            normalized_digest
        ):
            raise ValueError("target_digest must be a SHA-256 hex digest")

        async with self._session_factory() as db:
            query = select(NotificationEventTargetMutex).where(
                NotificationEventTargetMutex.event_type == normalized_event,
                NotificationEventTargetMutex.account_id == int(account_id),
            )
            if normalized_digest is not None:
                query = query.where(
                    NotificationEventTargetMutex.target_digest == normalized_digest
                )
            query = query.order_by(NotificationEventTargetMutex.target_digest)
            targets = (await db.execute(query.with_for_update())).scalars().all()
            resolved = 0
            for target in targets:
                if target.latest_attempt_id is None:
                    continue
                attempt = (
                    await db.execute(
                        select(NotificationEventAttempt)
                        .where(
                            NotificationEventAttempt.id == target.latest_attempt_id
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if attempt is None or str(attempt.state) == "resolved":
                    continue
                state = str(attempt.state or "pending")
                now = self._now()
                if state in {"pending", "send_started"}:
                    if self._lease_active(attempt, now):
                        # A live owner may still cross (or may already have
                        # crossed) the remote send boundary. Resolution cannot
                        # revoke its lease or open a concurrent generation.
                        continue
                    crossed_send_boundary = bool(
                        state == "send_started"
                        or attempt.send_started_at is not None
                        or attempt.provider_called
                    )
                    if crossed_send_boundary:
                        # Persist ambiguity first. This call deliberately does
                        # not also resolve the unknown state, so a fresh
                        # generation cannot open behind a late remote result.
                        attempt.state = "unknown"
                        attempt.next_retry_at = None
                        attempt.provider_called = 1
                        attempt.delivered = 0
                        attempt.outcome_known = 0
                        attempt.last_error_code = (
                            "send_result_unknown_before_resolution"
                        )
                        self._release(attempt)
                        continue
                    # An expired pending lease with no send boundary is safe
                    # to resolve: the provider was never called.
                attempt.state = "resolved"
                attempt.resolved_at = now
                attempt.resolution_code = self._safe_code(resolution_code)
                attempt.next_retry_at = None
                self._release(attempt)
                resolved += 1
            await db.commit()
            return resolved

    async def _locked(
        self,
        db: AsyncSession,
        lease: NotificationEventLease,
        *,
        require_active: bool,
    ) -> NotificationEventAttempt:
        attempt = (
            await db.execute(
                select(NotificationEventAttempt)
                .where(NotificationEventAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise NotificationEventAttemptError("notification event attempt is missing")
        if not lease.lease_token or attempt.lease_token != lease.lease_token:
            raise NotificationEventAttemptError("notification event lease was lost")
        if require_active and not self._lease_active(attempt, self._now()):
            raise NotificationEventAttemptError("notification event lease expired")
        return attempt

    @staticmethod
    def _lease_active(
        attempt: NotificationEventAttempt, now: dt.datetime
    ) -> bool:
        return bool(
            attempt.lease_token
            and attempt.lease_until
            and attempt.lease_until > now
        )

    @staticmethod
    def _release(attempt: NotificationEventAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _safe_code(value: str) -> str:
        normalized = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in str(value or "").casefold()
        )
        return (normalized.strip("_") or "notification_event_failure")[:64]

    @staticmethod
    def _retryable_operational_error(exc: OperationalError) -> bool:
        detail = str(exc).casefold()
        return any(
            marker in detail
            for marker in (
                "database is locked",
                "deadlock",
                "lock wait timeout",
                "1213",
                "1205",
            )
        )

    @staticmethod
    def _lease(
        attempt: NotificationEventAttempt,
        command: NotificationEventCommand,
        action: str,
        *,
        repeated: bool = False,
    ) -> NotificationEventLease:
        return NotificationEventLease(
            attempt_id=int(attempt.id),
            event_type=str(attempt.event_type),
            account_id=int(attempt.account_id),
            target_digest=str(attempt.target_digest),
            generation=int(attempt.generation),
            generation_ttl_seconds=command.generation_ttl_seconds,
            state=str(attempt.state or "pending"),
            action=action,
            lease_token=attempt.lease_token,
            attempt_count=int(attempt.attempt_count or 0),
            called=bool(attempt.provider_called),
            delivered=bool(attempt.delivered),
            outcome_known=bool(attempt.outcome_known),
            error_code=attempt.last_error_code,
            repeated=repeated,
        )

    @staticmethod
    def _lease_from_lease(
        attempt: NotificationEventAttempt,
        lease: NotificationEventLease,
        action: str,
    ) -> NotificationEventLease:
        return replace(
            lease,
            state=str(attempt.state),
            action=action,
            lease_token=attempt.lease_token,
            attempt_count=int(attempt.attempt_count or 0),
            called=bool(attempt.provider_called),
            delivered=bool(attempt.delivered),
            outcome_known=bool(attempt.outcome_known),
            error_code=attempt.last_error_code,
        )


class NotificationEventCoordinator:
    """Execute or explicitly resolve one durable notification event target."""

    def __init__(self, store: SqlNotificationEventAttemptStore) -> None:
        self._store = store

    async def execute(
        self,
        command: NotificationEventCommand,
        sender: RemoteSend,
    ) -> NotificationEventOutcome:
        lease = await self._store.acquire(command)
        if lease.action != "send":
            return self._outcome(lease)

        try:
            lease = await self._store.mark_send_started(lease)
        except Exception as exc:
            logger.error(
                "Notification event pre-send persistence failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            try:
                failed = await self._store.mark_failed(
                    lease,
                    called=False,
                    code="pre_send_persistence_failed",
                )
            except Exception:
                failed = replace(
                    lease,
                    state="failed",
                    action="return",
                    lease_token=None,
                    called=False,
                    delivered=False,
                    outcome_known=True,
                    error_code="pre_send_persistence_failed",
                )
            return self._outcome(failed)

        try:
            dispatch = await sender()
            if not isinstance(dispatch, NotificationDispatchOutcome):
                raise TypeError("sender returned an invalid delivery outcome")
        except Exception as exc:
            logger.warning(
                "Notification event delivery outcome unknown attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            unknown = await self._mark_unknown_safely(
                lease, "transport_result_unknown"
            )
            return self._outcome(unknown)

        try:
            if not dispatch.called:
                terminal = await self._store.mark_failed(
                    lease, called=False, code="delivery_not_called"
                )
            elif dispatch.delivered:
                terminal = await self._store.mark_confirmed(lease)
            elif dispatch.outcome_known:
                terminal = await self._store.mark_failed(
                    lease, called=True, code="delivery_rejected"
                )
            else:
                terminal = await self._store.mark_unknown(
                    lease, code="transport_result_unknown"
                )
        except Exception as exc:
            logger.error(
                "Notification event terminal persistence failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            terminal = await self._mark_unknown_safely(
                lease, "terminal_persistence_unknown"
            )
        return self._outcome(terminal)

    async def resolve(
        self,
        event_type: str,
        account_id: int,
        target_digest: str | None = None,
        *,
        resolution_code: str = "explicit_clear",
    ) -> int:
        return await self._store.resolve(
            event_type,
            account_id,
            target_digest,
            resolution_code=resolution_code,
        )

    async def _mark_unknown_safely(
        self, lease: NotificationEventLease, code: str
    ) -> NotificationEventLease:
        try:
            return await self._store.mark_unknown(lease, code=code)
        except Exception as exc:
            logger.error(
                "Notification event unknown-state persistence failed attemptId=%d errorType=%s",
                lease.attempt_id,
                type(exc).__name__,
            )
            return replace(
                lease,
                state="unknown",
                action="return",
                lease_token=None,
                called=True,
                delivered=False,
                outcome_known=False,
                error_code=code,
            )

    @staticmethod
    def _outcome(lease: NotificationEventLease) -> NotificationEventOutcome:
        status = {
            "in_progress": "in_progress",
            "backoff": "backoff",
        }.get(lease.action, lease.state)
        return NotificationEventOutcome(
            status=status,
            attempt_id=lease.attempt_id,
            generation=lease.generation,
            attempt_count=lease.attempt_count,
            called=lease.called,
            delivered=lease.delivered,
            outcome_known=lease.outcome_known,
            error_code=lease.error_code,
            repeated=lease.repeated,
        )
