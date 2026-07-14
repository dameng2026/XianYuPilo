from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import uuid
from dataclasses import dataclass, replace
from typing import Literal, Protocol

import requests
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.cookie_crypto import decrypt_cookie_if_needed
from ..core.logging_security import redact_sensitive_text
from ..models.entities import (
    GoodsOffShelfAttempt,
    XianyuAccount,
    XianyuAccountAuth,
    XianyuGoods,
)
from .xianyu_goods_sync import XianyuItemOperator


logger = logging.getLogger(__name__)

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_SAFE_ERROR_CODE_RE = re.compile(r"[^a-z0-9_]+")

GoodsOffShelfState = Literal[
    "pending",
    "in_progress",
    "remote_confirmed",
    "confirmed",
    "failed",
    "unknown",
]
GoodsOffShelfAction = Literal["call_remote", "finalize_local", "return", "in_progress"]


@dataclass(frozen=True)
class GoodsOffShelfContext:
    goods_id: int
    account_id: int
    external_goods_id: str


@dataclass(frozen=True)
class OffShelfResult:
    status: Literal["confirmed", "failed", "unknown"]
    error_code: str | None = None
    message: str = ""
    retry_safe: bool = False

    @classmethod
    def confirmed(cls) -> "OffShelfResult":
        return cls(status="confirmed")

    @classmethod
    def failed(
        cls,
        error_code: str,
        message: str,
        *,
        retry_safe: bool,
    ) -> "OffShelfResult":
        return cls(
            status="failed",
            error_code=error_code,
            message=message,
            retry_safe=retry_safe,
        )

    @classmethod
    def unknown(cls, error_code: str, message: str) -> "OffShelfResult":
        return cls(
            status="unknown",
            error_code=error_code,
            message=message,
            retry_safe=False,
        )


@dataclass(frozen=True)
class GoodsOffShelfLease:
    attempt_id: int
    idempotency_key: str
    state: GoodsOffShelfState
    action: GoodsOffShelfAction
    context: GoodsOffShelfContext
    retry_safe: bool
    lease_token: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    repeated: bool = False
    remote_confirmed: bool = False
    local_confirmed: bool = False


@dataclass(frozen=True)
class GoodsOffShelfOutcome:
    status: GoodsOffShelfState | Literal["in_progress"]
    message: str
    attempt_id: int
    goods_id: int
    idempotency_key: str
    retry_safe: bool
    recovery: str | None
    error_code: str | None
    remote_confirmed: bool
    local_confirmed: bool
    repeated: bool = False

    def to_data(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "attemptId": self.attempt_id,
            "goodsId": self.goods_id,
            "idempotencyKey": self.idempotency_key,
            "retrySafe": self.retry_safe,
            "recovery": self.recovery,
            "errorCode": self.error_code,
            "remoteConfirmed": self.remote_confirmed,
            "localConfirmed": self.local_confirmed,
            "repeated": self.repeated,
        }


class GoodsOffShelfError(Exception):
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


class GoodsOffShelfPersistenceError(RuntimeError):
    """A durable off-shelf transition could not be confirmed."""


class GoodsOffShelfStore(Protocol):
    async def acquire(
        self,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str,
    ) -> GoodsOffShelfLease: ...

    async def mark_remote_confirmed(
        self,
        lease: GoodsOffShelfLease,
    ) -> GoodsOffShelfLease: ...

    async def mark_confirmed(self, lease: GoodsOffShelfLease) -> GoodsOffShelfLease: ...

    async def mark_failed(
        self,
        lease: GoodsOffShelfLease,
        result: OffShelfResult,
    ) -> GoodsOffShelfLease: ...

    async def mark_unknown(
        self,
        lease: GoodsOffShelfLease,
        result: OffShelfResult,
    ) -> GoodsOffShelfLease: ...


class GoodsOffShelfGateway(Protocol):
    async def off_shelf(self, context: GoodsOffShelfContext) -> OffShelfResult: ...


class GoodsOffShelfCoordinator:
    """Own the cross-system off-shelf workflow behind one small interface."""

    def __init__(self, *, store: GoodsOffShelfStore, gateway: GoodsOffShelfGateway) -> None:
        self._store = store
        self._gateway = gateway

    async def execute(
        self,
        *,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str | None,
    ) -> GoodsOffShelfOutcome:
        if int(account_id or 0) <= 0 or not str(external_goods_id or "").strip():
            raise GoodsOffShelfError(422, "off_shelf_target_invalid", "缺少有效的账号或商品信息")

        resolved_key = self._idempotency_key(idempotency_key)
        lease = await self._store.acquire(
            int(account_id),
            str(external_goods_id).strip(),
            resolved_key,
        )
        if lease.action == "in_progress":
            return self._outcome(lease, status="in_progress")
        if lease.action == "return":
            return self._outcome(lease)

        if lease.action == "call_remote":
            try:
                result = await self._gateway.off_shelf(lease.context)
            except Exception:
                logger.error(
                    "Goods off-shelf call ended unexpectedly attemptId=%d",
                    lease.attempt_id,
                )
                result = OffShelfResult.unknown(
                    "remote_result_unknown",
                    "平台下架结果无法确认，请先在闲鱼 App 核对；系统不会自动重试",
                )

            if result.status == "unknown":
                return self._outcome(await self._store.mark_unknown(lease, result))
            if result.status != "confirmed":
                return self._outcome(await self._store.mark_failed(lease, result))

            try:
                lease = await self._store.mark_remote_confirmed(lease)
            except Exception:
                logger.error(
                    "Could not persist off-shelf remote confirmation attemptId=%d",
                    lease.attempt_id,
                )
                unknown = OffShelfResult.unknown(
                    "remote_confirmation_persist_unknown",
                    "平台可能已下架商品，但确认状态未能保存；请在闲鱼 App 核对，禁止重复下架",
                )
                try:
                    lease = await self._store.mark_unknown(lease, unknown)
                except Exception:
                    lease = replace(
                        lease,
                        state="unknown",
                        action="return",
                        retry_safe=False,
                        error_code=unknown.error_code,
                        error_message=unknown.message,
                    )
                return self._outcome(lease)

        if lease.action == "finalize_local":
            try:
                lease = await self._store.mark_confirmed(lease)
            except Exception:
                logger.error(
                    "Off-shelf remote confirmed but local finalization failed attemptId=%d",
                    lease.attempt_id,
                )
                lease = replace(
                    lease,
                    state="remote_confirmed",
                    action="return",
                    retry_safe=True,
                    remote_confirmed=True,
                    local_confirmed=False,
                    error_code="local_finalize_failed",
                    error_message="平台下架已确认，但本地状态未完成；可安全重试本地收尾",
                )
        return self._outcome(lease)

    @staticmethod
    def _idempotency_key(supplied: str | None) -> str:
        normalized = str(supplied or "").strip()
        if not normalized:
            raise GoodsOffShelfError(
                422,
                "idempotency_key_required",
                "下架操作必须提供幂等键，请刷新页面后重试",
            )
        if not _IDEMPOTENCY_KEY_RE.fullmatch(normalized):
            raise GoodsOffShelfError(
                422,
                "idempotency_key_invalid",
                "幂等键格式无效，应为 8-128 位字母、数字或 . _ : -",
            )
        return normalized

    @staticmethod
    def _outcome(
        lease: GoodsOffShelfLease,
        *,
        status: GoodsOffShelfState | Literal["in_progress"] | None = None,
    ) -> GoodsOffShelfOutcome:
        resolved = status or lease.state
        messages = {
            "pending": "下架请求已登记，等待执行",
            "in_progress": "该商品正在平台下架，请勿重复操作",
            "remote_confirmed": lease.error_message
            or "平台下架已确认，但本地状态尚未完成；再次操作只会重试本地收尾",
            "confirmed": "平台与本地下架状态均已确认",
            "failed": lease.error_message or "平台明确未执行下架；排除问题后可手动重试",
            "unknown": lease.error_message
            or "平台下架结果未知，请先在闲鱼 App 核对；系统已禁止自动重试",
        }
        recovery = {
            "remote_confirmed": "retry_local_finalize",
            "failed": "resolve_and_retry" if lease.retry_safe else "verify_in_xianyu_app",
            "unknown": "verify_in_xianyu_app",
        }.get(resolved)
        return GoodsOffShelfOutcome(
            status=resolved,
            message=messages[resolved],
            attempt_id=lease.attempt_id,
            goods_id=lease.context.goods_id,
            idempotency_key=lease.idempotency_key,
            retry_safe=lease.retry_safe if resolved != "in_progress" else False,
            recovery=recovery,
            error_code=lease.error_code,
            remote_confirmed=lease.remote_confirmed
            or resolved in {"remote_confirmed", "confirmed"},
            local_confirmed=lease.local_confirmed or resolved == "confirmed",
            repeated=lease.repeated,
        )


def _now() -> dt.datetime:
    return dt.datetime.now()


def _safe_error_code(value: object, default: str) -> str:
    normalized = _SAFE_ERROR_CODE_RE.sub("_", str(value or "").strip().lower()).strip("_")
    return (normalized or default)[:64]


def _safe_error_message(value: object, default: str) -> str:
    normalized = redact_sensitive_text(str(value or "").strip())
    return (normalized or default)[:500]


class SqlGoodsOffShelfStore:
    """MySQL adapter with durable single-flight and atomic local finalization."""

    def __init__(self, db: AsyncSession, *, lease_seconds: int = 90) -> None:
        self._db = db
        self._lease_seconds = max(30, min(int(lease_seconds), 300))

    async def acquire(
        self,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str,
    ) -> GoodsOffShelfLease:
        for race_attempt in range(2):
            try:
                return await self._acquire_once(
                    account_id,
                    external_goods_id,
                    idempotency_key,
                )
            except IntegrityError:
                await self._safe_rollback()
                if race_attempt:
                    raise GoodsOffShelfError(
                        409,
                        "off_shelf_attempt_conflict",
                        "该商品已有下架请求正在处理，请刷新状态",
                    )
        raise RuntimeError("unreachable")

    async def _acquire_once(
        self,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str,
    ) -> GoodsOffShelfLease:
        # Goods is always locked first. This serializes different idempotency
        # keys for the same target and keeps lock order identical to finalize.
        goods = (
            await self._db.execute(
                select(XianyuGoods)
                .where(
                    XianyuGoods.account_id == account_id,
                    XianyuGoods.external_goods_id == external_goods_id,
                    XianyuGoods.deleted == 0,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if goods is None:
            await self._safe_rollback()
            raise GoodsOffShelfError(404, "goods_not_found", "商品不存在或已被清理")

        existing = (
            await self._db.execute(
                select(GoodsOffShelfAttempt)
                .where(GoodsOffShelfAttempt.idempotency_key == idempotency_key)
                .with_for_update()
            )
        ).scalar_one_or_none()
        latest = (
            await self._db.execute(
                select(GoodsOffShelfAttempt)
                .where(GoodsOffShelfAttempt.goods_id == goods.id)
                .order_by(
                    GoodsOffShelfAttempt.created_time.desc(),
                    GoodsOffShelfAttempt.id.desc(),
                )
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            if (
                int(existing.goods_id) != int(goods.id)
                or int(existing.account_id) != int(account_id)
                or str(existing.external_goods_id) != str(external_goods_id)
            ):
                await self._safe_rollback()
                raise GoodsOffShelfError(
                    409,
                    "idempotency_key_conflict",
                    "幂等键已用于其他商品或账号，请刷新页面后重试",
                )
            if latest is not None and int(latest.id) != int(existing.id):
                await self._db.commit()
                raise GoodsOffShelfError(
                    409,
                    "off_shelf_intent_superseded",
                    "该幂等键对应的下架意图已被更新意图取代；请刷新商品状态，旧意图不会再次执行",
                )
            existing_state = str(existing.state or "pending")
            if int(goods.status if goods.status is not None else 1) == 0 and (
                existing_state == "pending"
                or (existing_state == "failed" and bool(existing.retry_safe))
            ):
                await self._db.commit()
                raise GoodsOffShelfError(
                    409,
                    "goods_already_off_shelf",
                    "本地商品已是下架状态；旧意图不会再次调用平台，请先同步核对",
                )
            return await self._claim_existing(existing, repeated=True)
        if latest is not None and self._blocks_new_intent(latest):
            # A second key must never bypass an active or ambiguous intent.
            return await self._claim_existing(latest, repeated=True)

        if int(goods.status if goods.status is not None else 1) == 0:
            await self._db.commit()
            raise GoodsOffShelfError(
                409,
                "goods_already_off_shelf",
                "本地商品已是下架状态；请先同步核对平台，无需重复下架",
            )

        attempt = GoodsOffShelfAttempt(
            goods_id=int(goods.id),
            account_id=int(account_id),
            external_goods_id=external_goods_id,
            idempotency_key=idempotency_key,
            state="pending",
            retry_safe=1,
            attempt_count=0,
        )
        self._db.add(attempt)
        await self._db.flush()
        attempt_id = int(attempt.id)
        # The intent exists durably before this method can authorize a call.
        await self._db.commit()

        attempt = (
            await self._db.execute(
                select(GoodsOffShelfAttempt)
                .where(GoodsOffShelfAttempt.id == attempt_id)
                .with_for_update()
            )
        ).scalar_one()
        return await self._claim_existing(attempt, repeated=False)

    @staticmethod
    def _blocks_new_intent(attempt: GoodsOffShelfAttempt) -> bool:
        state = str(attempt.state or "pending")
        return state in {"pending", "in_progress", "remote_confirmed", "unknown"} or (
            state == "failed" and not bool(attempt.retry_safe)
        )

    async def _claim_existing(
        self,
        attempt: GoodsOffShelfAttempt,
        *,
        repeated: bool,
    ) -> GoodsOffShelfLease:
        now = _now()
        state = str(attempt.state or "pending")
        if state == "confirmed":
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)
        if state == "remote_confirmed":
            await self._db.commit()
            return self._lease(attempt, action="finalize_local", repeated=True)
        if state == "unknown" or (state == "failed" and not bool(attempt.retry_safe)):
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)
        if (
            state in {"pending", "in_progress"}
            and attempt.lease_until
            and attempt.lease_until > now
        ):
            await self._db.commit()
            return self._lease(attempt, action="in_progress", repeated=True)
        if state == "in_progress":
            # The worker may have died after the outbound request started.
            # Lease expiry is not evidence that the platform did nothing.
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = "remote_result_unknown_after_recovery"
            attempt.error_message = (
                "上次下架在平台确认前中断；请在闲鱼 App 核对，系统已禁止自动重试"
            )
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)

        attempt.state = "in_progress"
        # From this persisted transition onward, retry can no longer be called
        # safe until the platform gives an explicit non-execution response.
        attempt.retry_safe = 0
        attempt.attempt_count = int(attempt.attempt_count or 0) + 1
        attempt.lease_token = uuid.uuid4().hex
        attempt.lease_until = now + dt.timedelta(seconds=self._lease_seconds)
        attempt.remote_started_at = now
        attempt.last_error_code = None
        attempt.error_message = None
        await self._db.commit()
        return self._lease(attempt, action="call_remote", repeated=repeated)

    async def mark_remote_confirmed(
        self,
        lease: GoodsOffShelfLease,
    ) -> GoodsOffShelfLease:
        try:
            attempt = await self._locked_attempt(lease)
            if str(attempt.state) != "in_progress":
                raise GoodsOffShelfError(
                    409,
                    "off_shelf_attempt_state_conflict",
                    "下架状态已变化，请刷新商品列表",
                )
            attempt.state = "remote_confirmed"
            attempt.retry_safe = 1
            attempt.remote_confirmed_at = attempt.remote_confirmed_at or _now()
            attempt.last_error_code = None
            attempt.error_message = None
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="finalize_local")
        except GoodsOffShelfError:
            await self._safe_rollback()
            raise
        except Exception as exc:
            await self._safe_rollback()
            raise GoodsOffShelfPersistenceError(
                "remote confirmation was not persisted"
            ) from exc

    async def mark_confirmed(self, lease: GoodsOffShelfLease) -> GoodsOffShelfLease:
        try:
            goods = (
                await self._db.execute(
                    select(XianyuGoods)
                    .where(XianyuGoods.id == lease.context.goods_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            attempt = (
                await self._db.execute(
                    select(GoodsOffShelfAttempt)
                    .where(GoodsOffShelfAttempt.id == lease.attempt_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is None:
                raise GoodsOffShelfError(
                    404,
                    "off_shelf_attempt_not_found",
                    "下架尝试不存在，请刷新商品列表",
                )
            if str(attempt.state) == "confirmed":
                await self._db.commit()
                return self._lease(attempt, action="return", repeated=True)
            if str(attempt.state) != "remote_confirmed":
                raise GoodsOffShelfError(
                    409,
                    "remote_off_shelf_not_confirmed",
                    "平台下架尚未确认，本地商品状态不会改变",
                )
            if goods is None:
                raise GoodsOffShelfPersistenceError("local goods row is unavailable")

            now = _now()
            # DB contract: 1=on sale, 0=off shelf, 2=sold.
            goods.status = 0
            goods.updated_time = now
            attempt.state = "confirmed"
            attempt.retry_safe = 0
            attempt.local_confirmed_at = attempt.local_confirmed_at or now
            attempt.last_error_code = None
            attempt.error_message = None
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return")
        except GoodsOffShelfError:
            await self._safe_rollback()
            raise
        except Exception as exc:
            await self._safe_rollback()
            if isinstance(exc, GoodsOffShelfPersistenceError):
                raise
            raise GoodsOffShelfPersistenceError("local off-shelf finalization failed") from exc

    async def mark_failed(
        self,
        lease: GoodsOffShelfLease,
        result: OffShelfResult,
    ) -> GoodsOffShelfLease:
        attempt = await self._locked_attempt(lease)
        attempt.state = "failed"
        attempt.retry_safe = 1 if result.retry_safe else 0
        attempt.last_error_code = _safe_error_code(result.error_code, "remote_off_shelf_failed")
        attempt.error_message = _safe_error_message(
            result.message,
            "平台明确未执行下架",
        )
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_unknown(
        self,
        lease: GoodsOffShelfLease,
        result: OffShelfResult,
    ) -> GoodsOffShelfLease:
        try:
            attempt = await self._locked_attempt(lease)
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = _safe_error_code(
                result.error_code,
                "remote_off_shelf_result_unknown",
            )
            attempt.error_message = _safe_error_message(
                result.message,
                "平台下架结果未知，请先在闲鱼 App 核对，系统不会自动重试",
            )
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return")
        except Exception:
            await self._safe_rollback()
            raise

    async def _locked_attempt(self, lease: GoodsOffShelfLease) -> GoodsOffShelfAttempt:
        attempt = (
            await self._db.execute(
                select(GoodsOffShelfAttempt)
                .where(GoodsOffShelfAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise GoodsOffShelfError(
                404,
                "off_shelf_attempt_not_found",
                "下架尝试不存在，请刷新商品列表",
            )
        if not lease.lease_token or attempt.lease_token != lease.lease_token:
            raise GoodsOffShelfError(
                409,
                "off_shelf_attempt_lease_lost",
                "下架执行权已变化，请刷新商品状态",
            )
        return attempt

    @staticmethod
    def _release(attempt: GoodsOffShelfAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _lease(
        attempt: GoodsOffShelfAttempt,
        *,
        action: GoodsOffShelfAction,
        repeated: bool = False,
    ) -> GoodsOffShelfLease:
        state = str(attempt.state or "pending")
        return GoodsOffShelfLease(
            attempt_id=int(attempt.id),
            idempotency_key=str(attempt.idempotency_key),
            state=state,  # type: ignore[arg-type]
            action=action,
            context=GoodsOffShelfContext(
                goods_id=int(attempt.goods_id),
                account_id=int(attempt.account_id),
                external_goods_id=str(attempt.external_goods_id),
            ),
            retry_safe=bool(attempt.retry_safe),
            lease_token=attempt.lease_token,
            error_code=attempt.last_error_code,
            error_message=attempt.error_message,
            repeated=repeated,
            remote_confirmed=attempt.remote_confirmed_at is not None
            or state in {"remote_confirmed", "confirmed"},
            local_confirmed=attempt.local_confirmed_at is not None or state == "confirmed",
        )

    async def _safe_rollback(self) -> None:
        try:
            await self._db.rollback()
        except Exception:
            pass


class XianyuGoodsOffShelfGateway:
    """Platform adapter that never labels an ambiguous outbound call retry-safe."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def off_shelf(self, context: GoodsOffShelfContext) -> OffShelfResult:
        try:
            auth = (
                await self._db.execute(
                    select(XianyuAccountAuth).where(
                        XianyuAccountAuth.account_id == context.account_id,
                        XianyuAccountAuth.deleted == 0,
                    )
                )
            ).scalar_one_or_none()
            account = (
                await self._db.execute(
                    select(XianyuAccount).where(
                        XianyuAccount.id == context.account_id,
                        XianyuAccount.deleted == 0,
                        XianyuAccount.status == 1,
                    )
                )
            ).scalar_one_or_none()
            await self._db.rollback()
        except Exception:
            await self._safe_rollback()
            return OffShelfResult.failed(
                "account_context_unavailable",
                "无法读取账号认证状态，平台下架未执行",
                retry_safe=True,
            )

        if auth is None or not auth.encrypted_cookie or account is None:
            return OffShelfResult.failed(
                "account_auth_missing",
                "账号未登录、已禁用或 Cookie 已失效，平台下架未执行",
                retry_safe=True,
            )

        try:
            cookie = decrypt_cookie_if_needed(auth.encrypted_cookie)
            operator = XianyuItemOperator(
                cookie,
                is_fish_shop=bool(getattr(account, "fish_shop", False)),
            )
        except Exception:
            # No outbound call has happened yet, so retry after repairing auth is safe.
            return OffShelfResult.failed(
                "account_auth_invalid",
                "账号认证信息无效，平台下架未执行；请重新登录后重试",
                retry_safe=True,
            )

        try:
            confirmed = await asyncio.to_thread(
                operator.off_shelf,
                context.external_goods_id,
            )
            if confirmed is not True:
                return OffShelfResult.unknown(
                    "platform_confirmation_missing",
                    "平台未返回可确认的下架结果；请先在闲鱼 App 核对",
                )
            return OffShelfResult.confirmed()
        except requests.exceptions.Timeout:
            return OffShelfResult.unknown(
                "platform_timeout_unknown",
                "平台请求超时，下架结果未知；请先在闲鱼 App 核对，系统不会自动重试",
            )
        except requests.exceptions.ConnectionError:
            return OffShelfResult.unknown(
                "platform_connection_unknown",
                "平台连接中断，下架结果未知；请先在闲鱼 App 核对，系统不会自动重试",
            )
        except requests.exceptions.HTTPError as exc:
            status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
            if 400 <= status < 500:
                return OffShelfResult.failed(
                    "platform_http_rejected",
                    "平台明确拒绝且未执行下架；请检查登录、权限或商品状态后重试",
                    retry_safe=True,
                )
            return OffShelfResult.unknown(
                "platform_http_result_unknown",
                "平台服务异常，下架结果未知；请先在闲鱼 App 核对",
            )
        except RuntimeError:
            # XianyuItemOperator raises RuntimeError only after parsing an
            # explicit non-success platform response.
            return OffShelfResult.failed(
                "platform_rejected_not_executed",
                "平台明确拒绝且未执行下架；请检查登录、风控或商品状态后重试",
                retry_safe=True,
            )
        except Exception:
            return OffShelfResult.unknown(
                "platform_result_unknown",
                "平台下架结果无法确认；请先在闲鱼 App 核对，系统不会自动重试",
            )

    async def _safe_rollback(self) -> None:
        try:
            await self._db.rollback()
        except Exception:
            pass
