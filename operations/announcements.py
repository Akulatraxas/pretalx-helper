"""
announcements.py — Multi-channel announcement dispatcher.

Formats human-readable messages for schedule delays and changes, then
dispatches them through all registered output channels.

Output channels (each implements `send(title, body, area) -> ChannelResult`):
  - LoggerChannel  — logs via Python's logging module
  - EFAppChannel   — posts to the EF App push-notification API

Usage (from app.py):
  import announcements
  results = announcements.dispatch_delay(title=title, minutes=minutes, comment=comment, start=start, end=end, room=room, tz=tz, reference=reference)
  results = announcements.dispatch_change(title=title, change_types=change_types, old_start=old_start, old_end=old_end, old_room=old_room, new_start=new_start, new_end=new_end, new_room=new_room, tz=tz, reference=reference)
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ChannelResult:
    channel: str
    ok: bool
    error: Optional[str] = None
    detail: Optional[str] = None   # e.g. returned ID from remote API


@dataclass
class DispatchResult:
    results: list[ChannelResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        """Indicates whether every channel dispatch succeeded.
        
        Returns:
        	bool: `true` if all channel results are successful, `false` otherwise.
        """
        return all(r.ok for r in self.results)

    def to_dict(self) -> dict:
        """
        Serialize the dispatch outcome and individual channel results.
        
        Returns:
        	dict: A mapping containing the overall success status and serialized channel results.
        """
        return {
            "all_ok": self.all_ok,
            "channels": [
                {
                    "channel": r.channel,
                    "ok": r.ok,
                    "error": r.error,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Message formatters
# ---------------------------------------------------------------------------

def _fmt_time(iso_str, tz=None) -> str:
    """
    Format an ISO timestamp as a local time in `HH:MM` format.
    
    Parameters:
    	iso_str (str): ISO timestamp to format.
    	tz: Optional timezone for conversion; naive timestamps are interpreted as UTC when provided.
    
    Returns:
    	str: Formatted time, `"unknown time"` for missing input, or the original value if parsing fails.
    """
    if not iso_str:
        return "unknown time"
    try:
        dt = datetime.fromisoformat(iso_str)
        if tz and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if tz:
            dt = dt.astimezone(tz)
        return dt.strftime("%H:%M")
    except ValueError:
        return iso_str


def _fmt_day(iso_str, tz=None) -> str:
    """
    Format an ISO timestamp as a weekday and date.
    
    Parameters:
        iso_str (str): ISO-formatted timestamp to format.
        tz: Optional timezone for converting the timestamp.
    
    Returns:
        str: Formatted weekday and date, ``"unknown day"`` for missing input, or the original value when parsing fails.
    """
    if not iso_str:
        return "unknown day"
    try:
        dt = datetime.fromisoformat(iso_str)
        if tz and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if tz:
            dt = dt.astimezone(tz)
        return dt.strftime("%A, %d %B")   # e.g. "Wednesday, 20 August"
    except ValueError:
        return iso_str


def _parse_dt_utc(iso_str):
    """Parse an ISO datetime string and return a UTC-aware datetime, or None."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


_MD_ESCAPE_RE = re.compile(r"([\\*_{}[\]()#+\-.!~`|<>])")


def _md(text: str | None) -> str:
    """
    Escape Markdown-special characters in text.

    Parameters:
        text: Text to escape.

    Returns:
        str: Escaped text, or empty string if input is None.
    """
    if text is None:
        return ""
    return _MD_ESCAPE_RE.sub(r"\\\1", str(text))


def format_delay_announcement(
    title: str,
    minutes: int,
    comment=None,
    start=None,
    room=None,
    tz=None,
):
    """
    Build the subject and body for a delay announcement.
    
    Parameters:
        comment (str, optional): Additional context included in the body.
        start (str, optional): Event start timestamp included in the body.
        room (str, optional): Event room included in the body.
        tz (optional): Time zone used to format the start timestamp.
    
    Returns:
        tuple: The announcement subject and body.
    """
    subject = f"Delay: {title}"

    comment_part = f" *({_md(comment)})*" if comment else ""
    room_part = f" in **{_md(room)}**" if room else ""
    time_part = f" starting at {_fmt_time(start, tz)}" if start else ""

    body = (
        f"**{_md(title)}**{room_part}{time_part} will be delayed by about "
        f"**{minutes} minute{'s' if minutes != 1 else ''}**{comment_part}"
    )
    return subject, body


def format_change_announcement(
    title: str,
    change_types: list,
    old_start=None,
    old_end=None,
    old_room=None,
    new_start=None,
    new_end=None,
    new_room=None,
    tz=None,
):
    """
    Format a new-event, cancellation, or schedule-change announcement.
    
    Parameters:
        title (str): Event title.
        change_types (list): Change categories, such as ``"new"``, ``"cancelled"``,
            ``"time"``, ``"day"``, or ``"room"``.
        old_start: Previous event start timestamp.
        old_room: Previous event room.
        new_start: Updated event start timestamp.
        new_room: Updated event room.
        tz: Time zone used to format timestamps.
    
    Returns:
        tuple: The announcement subject and body.
    """
    types = set(change_types)

    if "new" in types:
        subject = f"New Event: {title}"
        day = _fmt_day(new_start, tz)
        time = _fmt_time(new_start, tz)
        room_part = f" in **{_md(new_room)}**" if new_room else ""
        body = (
            f"✨ **New Event:** **{_md(title)}** will take place{room_part} "
            f"starting at **{time}** on **{day}**"
        )
        return subject, body

    if "cancelled" in types:
        subject = f"CANCELLED: {title}"
        day = _fmt_day(old_start, tz)
        time = _fmt_time(old_start, tz)
        body = (
            f"❌ **CANCELLED:** We are sorry to announce that **{_md(title)}** "
            f"planned for **{time}** on **{day}** will **NOT** take place."
        )
        return subject, body

    # Reschedule — build a diff summary
    subject = f"Schedule Change: {title}"
    parts = []

    if "day" in types or "time" in types:
        old_t = f"{_fmt_day(old_start, tz)} at {_fmt_time(old_start, tz)}"
        new_t = f"{_fmt_day(new_start, tz)} at {_fmt_time(new_start, tz)}"
        parts.append(f"~~{old_t}~~ \u2192 **{new_t}**")

    if "room" in types:
        old_r = _md(old_room) if old_room else "unknown room"
        new_r = _md(new_room) if new_room else "unknown room"
        parts.append(f"~~{old_r}~~ \u2192 **{new_r}**")

    if parts:
        changes_text = " | ".join(parts)
        body = f"📅 **Schedule Change:** **{_md(title)}** has been updated: {changes_text}"
    else:
        body = f"📅 **Schedule Change:** **{_md(title)}** has been updated."

    return subject, body


# ---------------------------------------------------------------------------
# Base channel
# ---------------------------------------------------------------------------

class BaseChannel:
    name = "base"

    def send(
        self,
        title: str,
        body: str,
        area: str,
        expires_at=None,
        reference: Optional[str] = None,
    ) -> ChannelResult:
        """Send an announcement through the channel.
        
        Parameters:
        	title (str): Announcement title.
        	body (str): Announcement content.
        	area (str): Announcement area.
        	expires_at: Optional expiration timestamp.
        	reference: Optional reference identifier (e.g. "{code}-{slot}").
        
        Returns:
        	ChannelResult: The result of sending the announcement.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Channel: Logger (always-on debug/test channel)
# ---------------------------------------------------------------------------

class LoggerChannel(BaseChannel):
    name = "logger"

    def send(
        self,
        title: str,
        body: str,
        area: str,
        expires_at=None,
        reference: Optional[str] = None,
    ) -> ChannelResult:
        """
        Record an announcement as successfully sent through the logger channel.
        
        Parameters:
            expires_at: Optional expiration time for the announcement.
            reference: Optional reference identifier (e.g. "{code}-{slot}").
        
        Returns:
            A successful channel result.
        """
        ref_part = f" (ref: {reference})" if reference else ""
        expires_part = f" (expires: {expires_at.strftime('%Y-%m-%dT%H:%M:%SZ')})" if expires_at else ""
        logger.info(
            "[ANNOUNCE:%s] %s | %s%s%s",
            area.upper(),
            title,
            body,
            ref_part,
            expires_part,
        )
        return ChannelResult(channel=self.name, ok=True)


# ---------------------------------------------------------------------------
# Channel: EF App push notifications
# ---------------------------------------------------------------------------

class EFAppChannel(BaseChannel):
    name = "ef-app"

    # Maps our internal area names to the EF App API area strings
    AREA_MAP = {
        "delay":      "delay",
        "new":        "new",
        "cancelled":  "deleted",
        "reschedule": "reschedule",
        "general":    "announcement", # unused in this path
    }

    def __init__(self, api_base: str, token: str, author: str = "EF Operations"):
        """Initialize an EF App channel with its API endpoint, authentication token, and author name.
        
        Parameters:
            api_base (str): Base URL for the EF App API.
            token (str): Authentication token used for API requests.
            author (str): Name attributed to announcements.
        """
        self.api_base = api_base.rstrip("/")
        self.token = token
        self.author = author

    def send(
        self,
        title: str,
        body: str,
        area: str,
        expires_at=None,
        reference: Optional[str] = None,
    ) -> ChannelResult:
        """
        Post an announcement to the EF App.
        
        Parameters:
            title (str): Announcement title.
            body (str): Announcement content.
            area (str): Internal announcement area name.
            expires_at: Optional expiration timestamp for the announcement.
            reference: Optional reference identifier (unused by EF App).
        
        Returns:
            ChannelResult: The posting outcome, including the remote announcement ID on success.
        """
        try:
            import requests as _requests
        except ImportError:
            return ChannelResult(
                channel=self.name,
                ok=False,
                error="requests library not installed",
            )

        ef_area = self.AREA_MAP.get(area, "announcement")
        now_utc = datetime.now(timezone.utc)

        # Use slot expiry when available; fall back to end of current UTC day
        if expires_at is not None:
            valid_until = expires_at
        else:
            from datetime import timedelta
            valid_until = now_utc.replace(hour=23, minute=59, second=59, microsecond=0)
            if valid_until <= now_utc:
                valid_until = valid_until + timedelta(days=1)

        payload = {
            "ValidFromDateTimeUtc":  now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ValidUntilDateTimeUtc": valid_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Area":    ef_area,
            "Author":  self.author,
            "Title":   title,
            "Content": body,
        }

        url = f"{self.api_base}/Api/Announcements"
        headers = {
            "X-API-Key":    self.token,
            "Content-Type": "application/json",
        }

        try:
            resp = _requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                announcement_id = resp.text.strip().strip('"')
                logger.info(
                    "[ef-app] Announcement posted (id=%s area=%s): %s",
                    announcement_id, ef_area, title,
                )
                return ChannelResult(
                    channel=self.name,
                    ok=True,
                    detail=announcement_id,
                )
            else:
                error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error("[ef-app] Announcement failed: %s", error_msg)
                return ChannelResult(channel=self.name, ok=False, error=error_msg)

        except Exception as exc:
            error_msg = str(exc)
            logger.error("[ef-app] Announcement exception: %s", error_msg)
            return ChannelResult(channel=self.name, ok=False, error=error_msg)


# ---------------------------------------------------------------------------
# Channel: EFSched Notification Bot
# ---------------------------------------------------------------------------

class EFSchedBotChannel(BaseChannel):
    """
    Sends notifications via the EFSched Notification Bot API.

    POST {api_base}/v1/notifications
    Auth: X-API-Key header

    Fixed parameters (per ops requirements):
      output_channels: ["local", "telegram"]
      type:            "delay"   (covers all our announcement types)
      status:          "pending" (bot dispatches immediately)
      team:            "ef-operations"
    """
    name = "efsched-bot"

    def __init__(self, api_base: str, token: str):
        self.api_base = api_base.rstrip("/")
        self.token = token

    def send(
        self,
        title: str,
        body: str,
        area: str,
        expires_at=None,
        reference: Optional[str] = None,
    ) -> ChannelResult:
        """
        Send a pending notification through the EFSched Bot API.
        
        Parameters:
            expires_at: Optional timestamp at which the notification expires.
            reference: Optional reference identifier (e.g. "{code}-{slot}").
        
        Returns:
            ChannelResult: The notification result, including its remote ID on success or an error message on failure.
        """
        try:
            import requests as _requests
        except ImportError:
            return ChannelResult(
                channel=self.name,
                ok=False,
                error="requests library not installed",
            )

        now_utc = datetime.now(timezone.utc)

        # short_text is capped at 255 chars — combine title + body into one concise string
        # If they fit together, use "Title: body"; otherwise just body (already descriptive)
        #combined = f"{title}: {body}" if len(f"{title}: {body}") <= 255 else body[:255]
        combined = f"{body}" if len(f"{body}") <= 255 else body[:255]

        payload = {
            "short_text":      combined,
            "type":            "delay",
            "team":            "ef-operations",
            "output_channels": ["local", "telegram"],
            "status":          "pending",
            "scheduled_at":    now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if expires_at is not None:
            payload["expires_at"] = expires_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if reference:
            payload["reference"] = reference

        url = f"{self.api_base}/v1/notifications"
        headers = {
            "X-API-Key":    self.token,
            "Content-Type": "application/json",
        }

        try:
            resp = _requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 201:
                notification_id = resp.json().get("id", "")
                logger.info(
                    "[efsched-bot] Notification posted (id=%s area=%s): %s",
                    notification_id, area, title,
                )
                return ChannelResult(
                    channel=self.name,
                    ok=True,
                    detail=notification_id,
                )
            else:
                error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error("[efsched-bot] Notification failed: %s", error_msg)
                return ChannelResult(channel=self.name, ok=False, error=error_msg)

        except Exception as exc:
            error_msg = str(exc)
            logger.error("[efsched-bot] Notification exception: %s", error_msg)
            return ChannelResult(channel=self.name, ok=False, error=error_msg)



_channels = []


def _build_channels():
    """
    Build the configured announcement channels.
    
    Returns:
    	list: The logger channel and any external channels configured through environment variables.
    """
    channels = [LoggerChannel()]

    ef_api = os.environ.get("EF_APP_API", "").strip()
    ef_token = os.environ.get("EF_APP_ANNOUNCE_TOKEN", "").strip()
    if ef_api and ef_token:
        channels.append(EFAppChannel(api_base=ef_api, token=ef_token))
        logger.info("[announcements] EF App channel enabled (%s)", ef_api)
    else:
        logger.warning(
            "[announcements] EF App channel disabled "
            "(EF_APP_API or EF_APP_ANNOUNCE_TOKEN not set)"
        )

    bot_url = os.environ.get("EF_EFSCHED_BOT", "").strip()
    bot_token = os.environ.get("EF_EFSCHED_BOT_TOKEN", "").strip()
    if bot_url and bot_token:
        channels.append(EFSchedBotChannel(api_base=bot_url, token=bot_token))
        logger.info("[announcements] EFSched Bot channel enabled (%s)", bot_url)
    else:
        logger.warning(
            "[announcements] EFSched Bot channel disabled "
            "(EF_EFSCHED_BOT or EF_EFSCHED_BOT_TOKEN not set)"
        )

    return channels


def _get_channels():
    """Return the configured announcement channels, building and caching them when needed."""
    global _channels
    if not _channels:
        _channels = _build_channels()
    return _channels


# ---------------------------------------------------------------------------
# Public dispatch functions
# ---------------------------------------------------------------------------

def dispatch_delay(
    title: str,
    minutes: int,
    comment=None,
    start=None,
    end=None,
    room=None,
    tz=None,
    reference: Optional[str] = None,
) -> DispatchResult:
    """
    Format and dispatch a delay announcement through all configured channels.
    
    Parameters:
        title (str): Event title.
        minutes (int): Delay duration in minutes.
        comment: Optional staff comment.
        start: Optional ISO start timestamp used in the announcement.
        end: Optional ISO end timestamp used to calculate expiration.
        room: Optional room name.
        tz: Optional timezone used to format the start time.
        reference: Optional reference identifier (e.g. "{code}-{slot}").
    
    Returns:
        DispatchResult: Results from each configured channel.
    """
    from datetime import timedelta
    subject, body = format_delay_announcement(title, minutes, comment, start, room, tz)

    # Expiry: slot end time + the delay itself (the event finishes that much later)
    expires_at = None
    end_dt = _parse_dt_utc(end)
    if end_dt is not None:
        expires_at = end_dt + timedelta(minutes=minutes)

    result = DispatchResult()
    for channel in _get_channels():
        result.results.append(
            channel.send(
                subject,
                body,
                area="delay",
                expires_at=expires_at,
                reference=reference,
            )
        )
    return result


def dispatch_change(
    title: str,
    change_types: list,
    old_start=None,
    old_end=None,
    old_room=None,
    new_start=None,
    new_end=None,
    new_room=None,
    tz=None,
    reference: Optional[str] = None,
) -> DispatchResult:
    """
    Format and dispatch an announcement for a new, cancelled, or rescheduled event.
    
    Parameters:
        title (str): Event title.
        change_types (list): Changes to announce, such as ``new``, ``cancelled``,
            ``time``, ``day``, or ``room``.
        old_start: Previous event start timestamp.
        old_end: Previous event end timestamp.
        old_room: Previous event room.
        new_start: Updated event start timestamp.
        new_end: Updated event end timestamp.
        new_room: Updated event room.
        tz: Time zone used to format timestamps.
        reference: Optional reference identifier (e.g. "{code}-{slot}").
    
    Returns:
        DispatchResult: Results from sending the announcement through all configured
            channels.
    """
    types = set(change_types)
    if "new" in types:
        area = "new"
    elif "cancelled" in types:
        area = "cancelled"
    else:
        area = "reschedule"

    subject, body = format_change_announcement(
        title, change_types,
        old_start, old_end, old_room,
        new_start, new_end, new_room,
        tz,
    )

    # Expiry: the later of old_end / new_end (cover both the old and new slot window)
    candidates = [dt for dt in (_parse_dt_utc(old_end), _parse_dt_utc(new_end)) if dt]
    expires_at = max(candidates) if candidates else None

    result = DispatchResult()
    for channel in _get_channels():
        result.results.append(
            channel.send(
                subject,
                body,
                area=area,
                expires_at=expires_at,
                reference=reference,
            )
        )
    return result
