from __future__ import annotations

import hashlib
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from ....core.logging_security import redact_sensitive_text
from ....core.response import ResultObject
from ..deps import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(tags=["client-observability"])

MAX_EVENTS_PER_REQUEST = 30
MAX_MESSAGE_LENGTH = 1000
MAX_STACK_LENGTH = 4000


def _bounded_text(value: Any, limit: int) -> str:
    return redact_sensitive_text(value if value is not None else "", max_length=limit)


def normalize_client_error_event(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    message = _bounded_text(value.get("message") or "Unknown client error", MAX_MESSAGE_LENGTH)
    if not message.strip():
        return None

    def bounded_int(name: str) -> int | None:
        raw = value.get(name)
        if raw in (None, ""):
            return None
        try:
            return max(0, min(int(raw), 10_000_000))
        except (TypeError, ValueError):
            return None

    return {
        "message": message,
        "stack": _bounded_text(value.get("stack"), MAX_STACK_LENGTH),
        "type": _bounded_text(value.get("type") or "client_error", 64),
        "source": _bounded_text(value.get("source"), 512),
        "route": _bounded_text(value.get("route"), 512),
        "userAgent": _bounded_text(value.get("userAgent"), 512),
        "time": _bounded_text(value.get("time"), 64),
        "line": bounded_int("line"),
        "column": bounded_int("column"),
    }


@router.post("/client-errors", response_model=ResultObject[dict])
async def ingest_client_errors(
    request: Request,
    payload: dict = Body(default={}),
    _current_user: dict = Depends(get_current_user),
):
    events = payload.get("events")
    if not isinstance(events, list):
        return ResultObject.validate_failed("events 必须是数组")

    accepted = 0
    dropped = max(0, len(events) - MAX_EVENTS_PER_REQUEST)
    for raw_event in events[:MAX_EVENTS_PER_REQUEST]:
        event = normalize_client_error_event(raw_event)
        if event is None:
            dropped += 1
            continue
        accepted += 1
        message = str(event.get("message") or "")
        stack = str(event.get("stack") or "")
        route = str(event.get("route") or "")
        event_type = str(event.get("type") or "client_error")
        safe_type = "".join(
            character for character in event_type if character.isalnum() or character in "_-"
        )[:64] or "client_error"
        logger.error(
            "client_error request_id=%s type=%s message_hash=%s stack_hash=%s route_hash=%s message_len=%d stack_len=%d",
            getattr(request.state, "request_id", ""),
            safe_type,
            hashlib.sha256(message.encode("utf-8")).hexdigest()[:16],
            hashlib.sha256(stack.encode("utf-8")).hexdigest()[:16],
            hashlib.sha256(route.encode("utf-8")).hexdigest()[:16],
            len(message),
            len(stack),
        )

    return ResultObject.success({"accepted": accepted, "dropped": dropped})
