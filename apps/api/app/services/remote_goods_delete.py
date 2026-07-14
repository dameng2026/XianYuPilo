from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, replace
from typing import Literal, Protocol

import requests
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.cookie_crypto import decrypt_cookie_if_needed
from ..core.logging_security import redact_sensitive_text
from ..models.entities import (
    RemoteGoodsDeleteAttempt,
    XianyuAccount,
    XianyuAccountAuth,
    XianyuGoods,
    XianyuSysSetting,
)
from .xianyu_goods_sync import XianyuItemOperator


logger = logging.getLogger(__name__)

_DELETE_SWITCH_KEY = "goods_delete_enabled"
_ENABLED_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_SAFE_ERROR_CODE_RE = re.compile(r"[^a-z0-9_]+")


RemoteDeleteState = Literal[
    "pending",
    "in_progress",
    "remote_confirmed",
    "confirmed",
    "failed",
    "unknown",
]
RemoteDeleteAction = Literal["call_remote", "finalize_local", "return", "in_progress"]


@dataclass(frozen=True)
class RemoteDeleteContext:
    goods_id: int
    account_id: int
    external_goods_id: str


@dataclass(frozen=True)
class ExternalDeleteResult:
    status: Literal["confirmed", "failed", "unknown"]
    error_code: str | None = None
    message: str = ""
    retry_safe: bool = False

    @classmethod
    def confirmed(cls) -> "ExternalDeleteResult":
        return cls(status="confirmed")

    @classmethod
    def failed(
        cls,
        error_code: str,
        message: str,
        *,
        retry_safe: bool,
    ) -> "ExternalDeleteResult":
        return cls(
            status="failed",
            error_code=error_code,
            message=message,
            retry_safe=retry_safe,
        )

    @classmethod
    def unknown(cls, error_code: str, message: str) -> "ExternalDeleteResult":
        return cls(
            status="unknown",
            error_code=error_code,
            message=message,
            retry_safe=False,
        )


@dataclass(frozen=True)
class RemoteDeleteLease:
    attempt_id: int
    idempotency_key: str
    state: RemoteDeleteState
    action: RemoteDeleteAction
    context: RemoteDeleteContext
    retry_safe: bool
    lease_token: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    repeated: bool = False
    remote_confirmed: bool = False
    local_deleted: bool = False


@dataclass(frozen=True)
class RemoteDeleteOutcome:
    status: RemoteDeleteState | Literal["in_progress"]
    message: str
    attempt_id: int
    goods_id: int
    idempotency_key: str
    retry_safe: bool
    recovery: str | None
    error_code: str | None
    remote_confirmed: bool
    local_deleted: bool
    repeated: bool = False

    def to_data(self) -> dict[str, object]:
        # Platform identifiers are deliberately excluded from browser-visible
        # attempt state and logs. The local goods ID is sufficient for recovery.
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
            "localDeleted": self.local_deleted,
            "repeated": self.repeated,
        }


class RemoteDeleteError(Exception):
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


class RemoteDeletePersistenceError(RuntimeError):
    """A durable transition could not be confirmed."""


class RemoteDeleteStore(Protocol):
    async def ensure_feature_enabled(self) -> None: ...

    async def acquire(
        self,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str,
    ) -> RemoteDeleteLease: ...

    async def mark_remote_confirmed(
        self,
        lease: RemoteDeleteLease,
    ) -> RemoteDeleteLease: ...

    async def mark_confirmed(self, lease: RemoteDeleteLease) -> RemoteDeleteLease: ...

    async def mark_failed(
        self,
        lease: RemoteDeleteLease,
        result: ExternalDeleteResult,
    ) -> RemoteDeleteLease: ...

    async def mark_unknown(
        self,
        lease: RemoteDeleteLease,
        result: ExternalDeleteResult,
    ) -> RemoteDeleteLease: ...


class RemoteDeleteGateway(Protocol):
    async def delete(self, context: RemoteDeleteContext) -> ExternalDeleteResult: ...


class RemoteGoodsDeleteCoordinator:
    """Own the irreversible remote-delete workflow behind one small interface."""

    def __init__(self, *, store: RemoteDeleteStore, gateway: RemoteDeleteGateway) -> None:
        self._store = store
        self._gateway = gateway

    async def execute(
        self,
        *,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str | None = None,
    ) -> RemoteDeleteOutcome:
        if int(account_id or 0) <= 0 or not str(external_goods_id or "").strip():
            raise RemoteDeleteError(422, "delete_target_invalid", "缺少有效的账号或商品信息")

        resolved_key = self._idempotency_key(
            int(account_id),
            str(external_goods_id).strip(),
            idempotency_key,
        )
        await self._store.ensure_feature_enabled()
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
                result = await self._gateway.delete(lease.context)
            except Exception:
                logger.error(
                    "Remote goods delete call ended unexpectedly attemptId=%d",
                    lease.attempt_id,
                )
                result = ExternalDeleteResult.unknown(
                    "remote_result_unknown",
                    "平台删除结果无法确认，请先在闲鱼 App 核对；系统不会自动重试",
                )

            if result.status == "unknown":
                lease = await self._store.mark_unknown(lease, result)
                return self._outcome(lease)
            if result.status != "confirmed":
                lease = await self._store.mark_failed(lease, result)
                return self._outcome(lease)

            try:
                # This commit is intentionally separate from local deletion.
                # A crash after the remote call can therefore never cause the
                # platform delete to be repeated automatically.
                lease = await self._store.mark_remote_confirmed(lease)
            except Exception:
                logger.error(
                    "Could not persist remote delete confirmation attemptId=%d",
                    lease.attempt_id,
                )
                result = ExternalDeleteResult.unknown(
                    "remote_confirmation_persist_unknown",
                    "平台可能已删除商品，但确认状态未能保存；请在闲鱼 App 核对，禁止重复删除",
                )
                try:
                    lease = await self._store.mark_unknown(lease, result)
                except Exception:
                    lease = replace(
                        lease,
                        state="unknown",
                        action="return",
                        retry_safe=False,
                        error_code=result.error_code,
                        error_message=result.message,
                    )
                return self._outcome(lease)

        if lease.action == "finalize_local":
            try:
                lease = await self._store.mark_confirmed(lease)
            except Exception:
                logger.error(
                    "Remote delete confirmed but local finalization failed attemptId=%d",
                    lease.attempt_id,
                )
                # Remote deletion is already durable. Expose a partial state;
                # never claim success and never call the platform again.
                lease = replace(
                    lease,
                    state="remote_confirmed",
                    action="return",
                    retry_safe=True,
                    remote_confirmed=True,
                    local_deleted=False,
                    error_code="local_finalize_failed",
                    error_message="平台删除已确认，但本地软删除未完成；可安全重试本地收尾",
                )

        return self._outcome(lease)

    @staticmethod
    def _idempotency_key(
        account_id: int,
        external_goods_id: str,
        supplied: str | None,
    ) -> str:
        if supplied is None or not str(supplied).strip():
            return hashlib.sha256(
                f"remote-goods-delete:v1:{account_id}:{external_goods_id}".encode("utf-8")
            ).hexdigest()
        normalized = str(supplied).strip()
        if not _IDEMPOTENCY_KEY_RE.fullmatch(normalized):
            raise RemoteDeleteError(
                422,
                "idempotency_key_invalid",
                "幂等键格式无效，应为 8-128 位字母、数字或 . _ : -",
            )
        return normalized

    @staticmethod
    def _outcome(
        lease: RemoteDeleteLease,
        *,
        status: RemoteDeleteState | Literal["in_progress"] | None = None,
    ) -> RemoteDeleteOutcome:
        resolved_status = status or lease.state
        messages = {
            "pending": "删除请求已登记，等待执行",
            "in_progress": "该商品的远程删除正在执行，请勿重复操作",
            "remote_confirmed": lease.error_message
            or "平台删除已确认，但本地软删除尚未完成；再次操作只会重试本地收尾",
            "confirmed": "平台删除与本地软删除均已确认完成",
            "failed": lease.error_message or "平台明确拒绝删除；排除问题后可手动重试",
            "unknown": lease.error_message
            or "平台删除结果未知，请先在闲鱼 App 核对；系统已禁止自动重试",
        }
        recovery = {
            "remote_confirmed": "retry_local_finalize",
            "failed": "resolve_and_retry",
            "unknown": "verify_in_xianyu_app",
        }.get(resolved_status)
        return RemoteDeleteOutcome(
            status=resolved_status,
            message=messages[resolved_status],
            attempt_id=lease.attempt_id,
            goods_id=lease.context.goods_id,
            idempotency_key=lease.idempotency_key,
            retry_safe=lease.retry_safe if resolved_status != "in_progress" else False,
            recovery=recovery,
            error_code=lease.error_code,
            remote_confirmed=lease.remote_confirmed
            or resolved_status in {"remote_confirmed", "confirmed"},
            local_deleted=lease.local_deleted or resolved_status == "confirmed",
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


class SqlRemoteGoodsDeleteStore:
    """MySQL adapter with durable single-flight and atomic local finalization."""

    def __init__(self, db: AsyncSession, *, lease_seconds: int = 90) -> None:
        self._db = db
        self._lease_seconds = max(30, min(int(lease_seconds), 300))

    async def ensure_feature_enabled(self) -> None:
        try:
            setting = (
                await self._db.execute(
                    select(XianyuSysSetting).where(
                        XianyuSysSetting.setting_key == _DELETE_SWITCH_KEY
                    )
                )
            ).scalar_one_or_none()
            # Read the value BEFORE rollback: rollback expires the ORM object,
            # and a later attribute access would trigger a sync lazy-load that
            # fails with MissingGreenlet in the async driver.
            value = str(getattr(setting, "setting_value", "") or "").strip().lower()
            await self._db.rollback()
        except Exception:
            await self._safe_rollback()
            logger.warning("Remote goods delete switch could not be read; operation denied")
            raise RemoteDeleteError(
                503,
                "remote_delete_switch_unavailable",
                "无法确认远程删除功能开关，操作已安全阻止；请检查数据库后重试",
            )

        if value not in _ENABLED_VALUES:
            raise RemoteDeleteError(
                403,
                "remote_delete_disabled",
                "远程删除功能未明确启用；请由管理员确认风险后将 goods_delete_enabled 设置为 true",
            )

    async def acquire(
        self,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str,
    ) -> RemoteDeleteLease:
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
                    raise RemoteDeleteError(
                        409,
                        "delete_attempt_conflict",
                        "该商品已有删除请求正在处理，请刷新状态",
                    )
        raise RuntimeError("unreachable")

    async def _acquire_once(
        self,
        account_id: int,
        external_goods_id: str,
        idempotency_key: str,
    ) -> RemoteDeleteLease:
        goods = (
            await self._db.execute(
                select(XianyuGoods)
                .where(
                    XianyuGoods.account_id == account_id,
                    XianyuGoods.external_goods_id == external_goods_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if goods is None:
            await self._db.rollback()
            raise RemoteDeleteError(404, "goods_not_found", "商品不存在或已被清理")

        existing = (
            await self._db.execute(
                select(RemoteGoodsDeleteAttempt)
                .where(
                    or_(
                        RemoteGoodsDeleteAttempt.goods_id == goods.id,
                        RemoteGoodsDeleteAttempt.idempotency_key == idempotency_key,
                    )
                )
                .with_for_update()
            )
        ).scalars().first()
        if existing is not None:
            if int(existing.goods_id) != int(goods.id):
                await self._db.rollback()
                raise RemoteDeleteError(
                    409,
                    "idempotency_key_conflict",
                    "幂等键已用于其他商品，请刷新页面后重试",
                )
            return await self._claim_existing(existing, repeated=True)

        if int(goods.deleted or 0) == 1 or int(goods.status or 0) == 3:
            await self._db.rollback()
            raise RemoteDeleteError(
                409,
                "goods_already_locally_deleted",
                "商品已被本地标记删除；请同步商品并核对平台状态，系统不会重复远程删除",
            )

        attempt = RemoteGoodsDeleteAttempt(
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
        # Persist pending before any transition can invoke the platform.
        await self._db.commit()

        attempt = (
            await self._db.execute(
                select(RemoteGoodsDeleteAttempt)
                .where(RemoteGoodsDeleteAttempt.id == attempt_id)
                .with_for_update()
            )
        ).scalar_one()
        return await self._claim_existing(attempt, repeated=False)

    async def _claim_existing(
        self,
        attempt: RemoteGoodsDeleteAttempt,
        *,
        repeated: bool,
    ) -> RemoteDeleteLease:
        now = _now()
        if attempt.state == "confirmed":
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)
        if attempt.state == "remote_confirmed":
            await self._db.commit()
            return self._lease(attempt, action="finalize_local", repeated=True)
        if attempt.state == "unknown" or (
            attempt.state == "failed" and not bool(attempt.retry_safe)
        ):
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)
        if (
            attempt.state in {"pending", "in_progress"}
            and attempt.lease_until
            and attempt.lease_until > now
        ):
            await self._db.commit()
            return self._lease(attempt, action="in_progress", repeated=True)
        if attempt.state == "in_progress":
            # The process may have died after writing the outbound request.
            # Expiry is therefore unknown, never an automatic platform retry.
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = "remote_result_unknown_after_recovery"
            attempt.error_message = "上次删除在平台确认前中断；请在闲鱼 App 核对，系统已禁止自动重试"
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return", repeated=True)

        attempt.state = "in_progress"
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
        lease: RemoteDeleteLease,
    ) -> RemoteDeleteLease:
        try:
            attempt = await self._locked_attempt(lease)
            if attempt.state != "in_progress":
                raise RemoteDeleteError(
                    409,
                    "delete_attempt_state_conflict",
                    "删除状态已变化，请刷新商品列表",
                )
            attempt.state = "remote_confirmed"
            attempt.retry_safe = 1
            attempt.remote_confirmed_at = attempt.remote_confirmed_at or _now()
            attempt.last_error_code = None
            attempt.error_message = None
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="finalize_local")
        except RemoteDeleteError:
            await self._safe_rollback()
            raise
        except Exception as exc:
            await self._safe_rollback()
            raise RemoteDeletePersistenceError("remote confirmation was not persisted") from exc

    async def mark_confirmed(self, lease: RemoteDeleteLease) -> RemoteDeleteLease:
        try:
            # Keep the same lock order as acquire: goods, then attempt.
            goods = (
                await self._db.execute(
                    select(XianyuGoods)
                    .where(XianyuGoods.id == lease.context.goods_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            attempt = (
                await self._db.execute(
                    select(RemoteGoodsDeleteAttempt)
                    .where(RemoteGoodsDeleteAttempt.id == lease.attempt_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is None:
                raise RemoteDeleteError(404, "delete_attempt_not_found", "删除尝试不存在，请刷新商品列表")
            if attempt.state == "confirmed":
                await self._db.commit()
                return self._lease(attempt, action="return", repeated=True)
            if attempt.state != "remote_confirmed":
                raise RemoteDeleteError(
                    409,
                    "remote_delete_not_confirmed",
                    "平台删除尚未确认，本地商品不会被删除",
                )
            if goods is None:
                raise RemoteDeletePersistenceError("local goods row is unavailable")

            now = _now()
            goods.status = 3
            goods.deleted = 1
            goods.updated_time = now
            attempt.state = "confirmed"
            attempt.retry_safe = 0
            attempt.local_deleted_at = attempt.local_deleted_at or now
            attempt.last_error_code = None
            attempt.error_message = None
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return")
        except RemoteDeleteError:
            await self._safe_rollback()
            raise
        except Exception as exc:
            await self._safe_rollback()
            if isinstance(exc, RemoteDeletePersistenceError):
                raise
            raise RemoteDeletePersistenceError("local delete finalization failed") from exc

    async def mark_failed(
        self,
        lease: RemoteDeleteLease,
        result: ExternalDeleteResult,
    ) -> RemoteDeleteLease:
        attempt = await self._locked_attempt(lease)
        attempt.state = "failed"
        attempt.retry_safe = 1 if result.retry_safe else 0
        attempt.last_error_code = _safe_error_code(result.error_code, "remote_delete_failed")
        attempt.error_message = _safe_error_message(result.message, "平台明确拒绝删除")
        self._release(attempt)
        await self._db.commit()
        return self._lease(attempt, action="return")

    async def mark_unknown(
        self,
        lease: RemoteDeleteLease,
        result: ExternalDeleteResult,
    ) -> RemoteDeleteLease:
        try:
            attempt = await self._locked_attempt(lease)
            attempt.state = "unknown"
            attempt.retry_safe = 0
            attempt.last_error_code = _safe_error_code(
                result.error_code,
                "remote_delete_result_unknown",
            )
            attempt.error_message = _safe_error_message(
                result.message,
                "平台删除结果未知，请先在闲鱼 App 核对，系统不会自动重试",
            )
            self._release(attempt)
            await self._db.commit()
            return self._lease(attempt, action="return")
        except Exception:
            await self._safe_rollback()
            raise

    async def _locked_attempt(self, lease: RemoteDeleteLease) -> RemoteGoodsDeleteAttempt:
        attempt = (
            await self._db.execute(
                select(RemoteGoodsDeleteAttempt)
                .where(RemoteGoodsDeleteAttempt.id == lease.attempt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise RemoteDeleteError(404, "delete_attempt_not_found", "删除尝试不存在，请刷新商品列表")
        if not lease.lease_token or attempt.lease_token != lease.lease_token:
            raise RemoteDeleteError(409, "delete_attempt_lease_lost", "删除执行权已变化，请刷新商品状态")
        return attempt

    @staticmethod
    def _release(attempt: RemoteGoodsDeleteAttempt) -> None:
        attempt.lease_token = None
        attempt.lease_until = None

    @staticmethod
    def _lease(
        attempt: RemoteGoodsDeleteAttempt,
        *,
        action: RemoteDeleteAction,
        repeated: bool = False,
    ) -> RemoteDeleteLease:
        state = str(attempt.state)
        return RemoteDeleteLease(
            attempt_id=int(attempt.id),
            idempotency_key=str(attempt.idempotency_key),
            state=state,  # type: ignore[arg-type]
            action=action,
            context=RemoteDeleteContext(
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
            local_deleted=attempt.local_deleted_at is not None or state == "confirmed",
        )

    async def _safe_rollback(self) -> None:
        try:
            await self._db.rollback()
        except Exception:
            pass


class XianyuRemoteDeleteGateway:
    """Adapter that classifies platform outcomes without exposing raw responses."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def delete(self, context: RemoteDeleteContext) -> ExternalDeleteResult:
        try:
            auth = (
                await self._db.execute(
                    select(XianyuAccountAuth).where(
                        XianyuAccountAuth.account_id == context.account_id
                    )
                )
            ).scalar_one_or_none()
            account = (
                await self._db.execute(
                    select(XianyuAccount).where(
                        XianyuAccount.id == context.account_id,
                        XianyuAccount.deleted == 0,
                    )
                )
            ).scalar_one_or_none()
            # Read ORM attributes BEFORE rollback: rollback expires ORM
            # objects, and later attribute access would trigger a sync lazy-load
            # that fails with MissingGreenlet in the async driver.
            encrypted_cookie = getattr(auth, "encrypted_cookie", "") if auth else ""
            fish_shop = bool(getattr(account, "fish_shop", False)) if account else False
            await self._db.rollback()
        except Exception:
            try:
                await self._db.rollback()
            except Exception:
                pass
            return ExternalDeleteResult.failed(
                "account_context_unavailable",
                "无法读取账号认证状态，平台删除未执行",
                retry_safe=True,
            )

        if auth is None or not encrypted_cookie or account is None:
            return ExternalDeleteResult.failed(
                "account_auth_missing",
                "账号未登录或 Cookie 已失效，平台删除未执行",
                retry_safe=True,
            )

        try:
            cookie = decrypt_cookie_if_needed(encrypted_cookie)
            operator = XianyuItemOperator(
                cookie,
                is_fish_shop=fish_shop,
            )
            confirmed = await asyncio.to_thread(operator.delete, context.external_goods_id)
            if confirmed is not True:
                return ExternalDeleteResult.failed(
                    "platform_rejected",
                    "平台明确拒绝删除；请同步商品状态后再处理",
                    retry_safe=True,
                )
            return ExternalDeleteResult.confirmed()
        except requests.exceptions.Timeout:
            return ExternalDeleteResult.unknown(
                "platform_timeout_unknown",
                "平台请求超时，删除结果未知；请先在闲鱼 App 核对，系统不会自动重试",
            )
        except requests.exceptions.ConnectionError:
            return ExternalDeleteResult.unknown(
                "platform_connection_unknown",
                "平台连接中断，删除结果未知；请先在闲鱼 App 核对，系统不会自动重试",
            )
        except requests.exceptions.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", 0) or 0
            if 400 <= int(status) < 500:
                return ExternalDeleteResult.failed(
                    "platform_http_rejected",
                    "平台明确拒绝删除；请检查登录状态、权限或商品状态",
                    retry_safe=True,
                )
            return ExternalDeleteResult.unknown(
                "platform_http_result_unknown",
                "平台服务异常，删除结果未知；请先在闲鱼 App 核对",
            )
        except RuntimeError as exc:
            normalized = str(exc).lower()
            if any(marker in normalized for marker in ("cookie", "token", "登录", "session")):
                code = "account_auth_expired"
                message = "账号登录已失效，平台明确未完成删除；请重新登录后手动重试"
            else:
                code = "platform_rejected"
                message = "平台明确拒绝删除；请检查商品状态或稍后手动重试"
            return ExternalDeleteResult.failed(code, message, retry_safe=True)
        except Exception:
            return ExternalDeleteResult.unknown(
                "platform_result_unknown",
                "平台删除结果无法确认；请先在闲鱼 App 核对，系统不会自动重试",
            )
