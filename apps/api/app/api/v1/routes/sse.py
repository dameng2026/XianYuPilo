import asyncio
import hmac
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ....core.config import settings
from ....core.response import ResultObject
from ....services.ws_sse import broadcaster
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sse")

SSE_TICKET_TTL_SECONDS = 60
_sse_tickets: dict[str, float] = {}


def _cleanup_expired_tickets() -> None:
    now = time.time()
    expired = [ticket for ticket, expires_at in _sse_tickets.items() if expires_at <= now]
    for ticket in expired:
        _sse_tickets.pop(ticket, None)


def _issue_ticket() -> str:
    _cleanup_expired_tickets()
    ticket = uuid.uuid4().hex
    _sse_tickets[ticket] = time.time() + SSE_TICKET_TTL_SECONDS
    return ticket


def _consume_ticket(ticket: str) -> bool:
    _cleanup_expired_tickets()
    expires_at = _sse_tickets.pop(ticket, None)
    return bool(expires_at and expires_at > time.time())


def _sse_response(generator):
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ticket", response_model=ResultObject[dict])
async def create_sse_ticket(
    current_user: dict = Depends(get_current_user),
):
    return ResultObject.success({
        "ticket": _issue_ticket(),
        "expiresIn": SSE_TICKET_TTL_SECONDS,
    })


@router.get("/subscribe")
async def subscribe_sse(
    request: Request,
    ticket: str | None = Query(default=None),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    ticket_ok = bool(ticket and _consume_ticket(ticket))
    internal_token = (settings.internal_api_token or "").strip()
    internal_ok = bool(
        internal_token
        and x_internal_token
        and hmac.compare_digest(str(x_internal_token), internal_token)
    )
    if not ticket_ok and not internal_ok:
        raise HTTPException(status_code=403, detail="invalid sse ticket")
    if broadcaster.subscriber_count >= 100:
        raise HTTPException(status_code=503, detail="SSE 连接数已达上限，请稍后重试")

    subscriber_id = f"sse_{uuid.uuid4().hex[:8]}"

    async def event_generator():
        queue = None
        try:
            queue = await broadcaster.subscribe(subscriber_id)
            yield f"data: {json.dumps({'type': 'connected', 'message': 'connected'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield message
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'message': 'connected'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE client disconnected subId=%s", subscriber_id)
        except Exception:
            logger.error("SSE stream error", exc_info=True)
        finally:
            if queue is not None:
                await broadcaster.unsubscribe(subscriber_id)

    return _sse_response(event_generator())
