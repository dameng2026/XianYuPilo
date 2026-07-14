"""Runtime admission policy for buyer-facing AI auto replies.

The public interface returns one deterministic decision containing both the
operator-visible denial reason and the local calendar day used by the durable
daily quota.  Time-zone, cross-midnight and human-takeover details stay inside
this module so the external-send state machine only needs an allow/deny result.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


DEFAULT_POLICY_TIMEZONE = "Asia/Shanghai"
SUPPORTED_POLICY_TIMEZONES: dict[str, dt.tzinfo] = {
    "Asia/Shanghai": dt.timezone(dt.timedelta(hours=8), name="Asia/Shanghai"),
    "UTC": dt.timezone.utc,
}
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_KEYWORD_SEPARATOR_RE = re.compile(r"[,，、;；|/\r\n]+")


@dataclass(frozen=True)
class AiAutoReplyPolicyDecision:
    allowed: bool
    reason: str
    local_date: dt.date
    timezone_name: str
    max_daily_replies: int


def _coerce_now(value: dt.datetime | None) -> dt.datetime:
    now = value or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now


def _parse_clock(value: Any) -> dt.time | None:
    normalized = str(value or "").strip()
    if not _TIME_RE.fullmatch(normalized):
        return None
    hour, minute = normalized.split(":", 1)
    return dt.time(hour=int(hour), minute=int(minute))


def _inside_work_window(
    local_time: dt.time,
    *,
    work_start: dt.time,
    work_end: dt.time,
) -> bool:
    # Half-open intervals make the hand-over instant deterministic.  A start
    # after the end is an intentional cross-midnight window.
    if work_start < work_end:
        return work_start <= local_time < work_end
    if work_start > work_end:
        return local_time >= work_start or local_time < work_end
    return False


def _keyword_matches(content: str, configured: Any) -> bool:
    normalized_content = str(content or "")[:12_000].casefold()
    if not normalized_content:
        return False
    keywords = [
        item.strip().casefold()[:100]
        for item in _KEYWORD_SEPARATOR_RE.split(str(configured or "")[:10_000])
        if item.strip()
    ][:100]
    return any(keyword in normalized_content for keyword in keywords)


async def evaluate_ai_auto_reply_policy(
    db: AsyncSession,
    *,
    config: dict[str, Any],
    account_id: int,
    session_id: str,
    message_content: str = "",
    now: dt.datetime | None = None,
) -> AiAutoReplyPolicyDecision:
    """Evaluate work-hours and human-takeover policy for one conversation.

    The daily quota is returned as policy context and is enforced atomically by
    ``SqlAiAutoReplyAttemptStore`` when it creates or retries an attempt.
    """
    current = _coerce_now(now)
    timezone_name = str(
        config.get("timeZone") or DEFAULT_POLICY_TIMEZONE
    ).strip()
    policy_timezone = SUPPORTED_POLICY_TIMEZONES.get(timezone_name)
    if policy_timezone is None:
        local_date = current.astimezone(dt.timezone.utc).date()
        return AiAutoReplyPolicyDecision(
            allowed=False,
            reason="invalid_policy_timezone",
            local_date=local_date,
            timezone_name=timezone_name,
            max_daily_replies=0,
        )

    local_now = current.astimezone(policy_timezone)
    raw_daily_limit = config.get("maxDailyReplies", 200)
    try:
        max_daily_replies = (
            0 if isinstance(raw_daily_limit, bool) else int(raw_daily_limit)
        )
    except (TypeError, ValueError):
        max_daily_replies = 0
    if not 1 <= max_daily_replies <= 10_000:
        return AiAutoReplyPolicyDecision(
            allowed=False,
            reason="invalid_daily_reply_limit",
            local_date=local_now.date(),
            timezone_name=timezone_name,
            max_daily_replies=0,
        )

    mode = str(config.get("mode") or "hybrid").strip().casefold()
    if mode == "manual":
        return AiAutoReplyPolicyDecision(
            allowed=False,
            reason="manual_mode",
            local_date=local_now.date(),
            timezone_name=timezone_name,
            max_daily_replies=max_daily_replies,
        )
    if mode not in {"auto", "hybrid"}:
        return AiAutoReplyPolicyDecision(
            allowed=False,
            reason="invalid_reply_mode",
            local_date=local_now.date(),
            timezone_name=timezone_name,
            max_daily_replies=max_daily_replies,
        )

    work_hours_24 = config.get("workHours24", True)
    pause_on_human = config.get("pauseOnHumanIntervene", True)
    safe_mode = config.get("safeMode", True)
    if not all(
        isinstance(value, bool)
        for value in (work_hours_24, pause_on_human, safe_mode)
    ):
        return AiAutoReplyPolicyDecision(
            allowed=False,
            reason="invalid_policy_boolean",
            local_date=local_now.date(),
            timezone_name=timezone_name,
            max_daily_replies=max_daily_replies,
        )

    # Hybrid mode always keeps configured high-risk conversations for a human.
    # Auto mode applies the same deterministic list when safe mode is enabled.
    keyword_guard_enabled = mode == "hybrid" or safe_mode
    if keyword_guard_enabled:
        if _keyword_matches(message_content, config.get("handoffKeywords")):
            return AiAutoReplyPolicyDecision(
                allowed=False,
                reason="handoff_keyword_matched",
                local_date=local_now.date(),
                timezone_name=timezone_name,
                max_daily_replies=max_daily_replies,
            )
        if _keyword_matches(message_content, config.get("blacklistKeywords")):
            return AiAutoReplyPolicyDecision(
                allowed=False,
                reason="blacklist_keyword_matched",
                local_date=local_now.date(),
                timezone_name=timezone_name,
                max_daily_replies=max_daily_replies,
            )

    if not work_hours_24:
        work_start = _parse_clock(config.get("workStart"))
        work_end = _parse_clock(config.get("workEnd"))
        if work_start is None or work_end is None or work_start == work_end:
            return AiAutoReplyPolicyDecision(
                allowed=False,
                reason="invalid_work_hours",
                local_date=local_now.date(),
                timezone_name=timezone_name,
                max_daily_replies=max_daily_replies,
            )
        if not _inside_work_window(
            local_now.time().replace(tzinfo=None),
            work_start=work_start,
            work_end=work_end,
        ):
            return AiAutoReplyPolicyDecision(
                allowed=False,
                reason="outside_work_hours",
                local_date=local_now.date(),
                timezone_name=timezone_name,
                max_daily_replies=max_daily_replies,
            )

    if pause_on_human:
        raw_pause_minutes = config.get("humanInterventionPauseMinutes", 30)
        try:
            pause_minutes = (
                0 if isinstance(raw_pause_minutes, bool) else int(raw_pause_minutes)
            )
        except (TypeError, ValueError):
            pause_minutes = 0
        if not 1 <= pause_minutes <= 1_440:
            return AiAutoReplyPolicyDecision(
                allowed=False,
                reason="invalid_human_pause_window",
                local_date=local_now.date(),
                timezone_name=timezone_name,
                max_daily_replies=max_daily_replies,
            )

        normalized_sid = (
            str(session_id or "")
            .strip()
            .removeprefix("sid:")
            .removesuffix("@goofish")
        )
        if not account_id or not normalized_sid:
            return AiAutoReplyPolicyDecision(
                allowed=False,
                reason="invalid_conversation_identity",
                local_date=local_now.date(),
                timezone_name=timezone_name,
                max_daily_replies=max_daily_replies,
            )
        threshold_ms = int(
            (current - dt.timedelta(minutes=pause_minutes)).timestamp() * 1_000
        )
        human_message_id = (
            await db.execute(
                text(
                    """
                    SELECT message.id
                    FROM xianyu_chat_message AS message
                    WHERE message.account_id = :account_id
                      AND message.deleted = 0
                      AND message.direction = 'OUT'
                      AND message.s_id IN (:sid_plain, :sid_goofish)
                      AND message.message_time >= :threshold_ms
                      AND COALESCE(message.pnm_id, '') NOT LIKE 'ai-auto-reply:%'
                      AND NOT EXISTS (
                        SELECT 1
                        FROM ai_auto_reply_attempt AS attempt
                        WHERE attempt.local_message_id = message.id
                      )
                    ORDER BY message.message_time DESC, message.id DESC
                    LIMIT 1
                    """
                ),
                {
                    "account_id": int(account_id),
                    "sid_plain": normalized_sid,
                    "sid_goofish": f"{normalized_sid}@goofish",
                    "threshold_ms": threshold_ms,
                },
            )
        ).scalar_one_or_none()
        if human_message_id is not None:
            return AiAutoReplyPolicyDecision(
                allowed=False,
                reason="human_intervention_active",
                local_date=local_now.date(),
                timezone_name=timezone_name,
                max_daily_replies=max_daily_replies,
            )

    return AiAutoReplyPolicyDecision(
        allowed=True,
        reason="allowed",
        local_date=local_now.date(),
        timezone_name=timezone_name,
        max_daily_replies=max_daily_replies,
    )
