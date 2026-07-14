"""Durable, fail-closed audit intents for authenticated API mutations."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from typing import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import async_session
from .response import ResultObject
from .security import request_client_ip

logger = logging.getLogger(__name__)
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SENSITIVE_PATH_SEGMENTS = (
    re.compile(r"(?i)(/(?:internal/)?qrlogin/(?:status|cookies)/)[^/]+"),
    re.compile(r"(?i)(/ads/payment/orders/)[^/]+"),
)


def _client_hash(request: Request) -> str:
    # Resolve proxy headers only when the immediate peer is trusted, then use a
    # keyed digest so a leaked audit export cannot be used as a cheap IPv4
    # dictionary. The domain prefix prevents cross-protocol use of the JWT key.
    source = request_client_ip(request)
    digest = hmac.new(
        str(settings.jwt_secret).encode("utf-8"),
        f"audit-client\0{source}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest[:24]}"


def _audit_outcome(status_code: int) -> tuple[str, str]:
    """Return an honest operation type and description state for one response."""

    if 200 <= status_code < 300:
        return "HTTP_MUTATION_COMPLETED", "completed"
    if 400 <= status_code < 500:
        return "HTTP_MUTATION_REJECTED", "rejected"
    # Redirects are not proof that the intended handler ran, and 5xx responses
    # may follow an irreversible side effect. Both require reconciliation.
    return "HTTP_MUTATION_RESULT_UNKNOWN", "result_unknown"


def _audit_path(path: str) -> str:
    """Remove bearer-like or payment identifiers embedded in known API paths."""

    sanitized = str(path or "")
    for pattern in _SENSITIVE_PATH_SEGMENTS:
        sanitized = pattern.sub(r"\1<redacted>", sanitized)
    return sanitized[:1000]


def _audit_description(request: Request, status: str, http_status: int | None = None) -> str:
    payload: dict[str, object] = {
        "requestId": str(getattr(request.state, "request_id", ""))[:100],
        "method": request.method,
        "path": _audit_path(request.url.path),
        "status": status,
    }
    if http_status is not None:
        payload["httpStatus"] = int(http_status)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


async def _create_audit_intent(request: Request) -> int:
    user = getattr(request.state, "current_user", None) or {}
    operator = str(user.get("username") or "authenticated-admin")[:64]
    request_id = str(getattr(request.state, "request_id", ""))[:100]
    async with async_session() as db:
        result = await db.execute(
            text(
                """
                INSERT INTO operation_log(
                    operator, operation_type, operation_desc, target_type,
                    target_id, ip_address, created_time
                ) VALUES(
                    :operator, 'HTTP_MUTATION_STARTED', :description,
                    'api_mutation', :request_id, :ip_address, NOW()
                )
                """
            ),
            {
                "operator": operator,
                "description": _audit_description(request, "started"),
                "request_id": request_id,
                "ip_address": _client_hash(request),
            },
        )
        await db.commit()
        return int(result.lastrowid)


async def _finish_audit_intent(request: Request, audit_id: int, status_code: int) -> None:
    operation_type, outcome = _audit_outcome(status_code)
    async with async_session() as db:
        result = await db.execute(
            text(
                """
                UPDATE operation_log
                SET operation_type = :operation_type,
                    operation_desc = :description
                WHERE id = :audit_id
                """
            ),
            {
                "audit_id": audit_id,
                "operation_type": operation_type,
                "description": _audit_description(
                    request,
                    outcome,
                    status_code,
                ),
            },
        )
        if int(result.rowcount or 0) != 1:
            raise RuntimeError("mutation audit intent disappeared before completion")
        await db.commit()


def _unavailable(request: Request) -> JSONResponse:
    request_id = str(getattr(request.state, "request_id", ""))
    payload = ResultObject.failed(
        "审计存储暂不可用，写操作未执行",
        code=503,
    ).model_dump(by_alias=True)
    payload["requestId"] = request_id
    return JSONResponse(
        status_code=503,
        content=payload,
        headers={"X-Request-ID": request_id},
    )


class MutationAuditMiddleware(BaseHTTPMiddleware):
    """Persist an intent before every authenticated mutation.

    A completion update is best-effort because the durable ``STARTED`` row is
    already sufficient to flag a crash window as requiring reconciliation.
    The business handler never runs if the initial audit insert cannot commit.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        should_audit = (
            settings.audit_mutation_intent_required
            and request.method.upper() in _MUTATING_METHODS
            and request.url.path.startswith("/api/")
            # These authenticated compatibility paths are retired lookups that
            # always return 410 and can no longer mutate state. Writing an
            # audit intent for them would create a misleading mutation record.
            and not request.url.path.startswith("/api/internal/qrlogin/")
            and getattr(request.state, "current_user", None) is not None
        )
        if not should_audit:
            return await call_next(request)

        try:
            audit_id = await _create_audit_intent(request)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "mutation audit intent unavailable request_id=%s errorType=%s",
                getattr(request.state, "request_id", ""),
                type(exc).__name__,
            )
            return _unavailable(request)

        try:
            response = await call_next(request)
        except BaseException:
            try:
                await _finish_audit_intent(request, audit_id, 500)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "mutation audit completion unavailable audit_id=%s errorType=%s",
                    audit_id,
                    type(exc).__name__,
                )
            raise

        try:
            await _finish_audit_intent(request, audit_id, response.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "mutation audit completion unavailable audit_id=%s errorType=%s",
                audit_id,
                type(exc).__name__,
            )
        return response
