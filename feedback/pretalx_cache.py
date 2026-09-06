"""
pretalx_cache.py — Pretalx data fetching and in-memory cache for Feedback Viewer.

Fetches schedule + speaker data, normalises it into submission-centric structures,
and keeps an in-memory cache refreshed in the background.
"""

import os
import time
import threading
import logging

from pretalx_client import PretalxClient

logger = logging.getLogger(__name__)

PRETALX_URL    = os.environ.get("PRETALX_URL", "")
PRETALX_APIKEY = os.environ.get("PRETALX_APIKEY", "")
PRETALX_EVENT  = os.environ.get("PRETALX_EVENT_SLUG", "")
SCHEDULE_VERSION = os.environ.get("SCHEDULE_VERSION", "latest")

CACHE_REFRESH_INTERVAL = int(os.environ.get("CACHE_REFRESH_INTERVAL", "3600"))

# ---------------------------------------------------------------------------
# In-memory cache state
# ---------------------------------------------------------------------------

_cache = {
    "data":         None,   # normalised cache dict (see build_cache)
    "last_fetched": None,   # Unix timestamp
    "error":        None,   # last error message
    "lock":         threading.Lock(),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _localized(val, lang="en"):
    """Extract a string from a potentially localised dict."""
    if isinstance(val, dict):
        return val.get(lang) or next(iter(val.values()), "") or ""
    return str(val) if val is not None else ""


def _find_telegram(answers):
    """
    Scan a list of Pretalx answer dicts for the first one whose question text
    contains 'telegram' (case-insensitive). Returns the answer string or ''.
    """
    for answer in (answers or []):
        q = answer.get("question") or {}
        if isinstance(q, dict):
            q_text = _localized(q.get("question", ""))
        else:
            q_text = str(q)
        if "telegram" in q_text.lower():
            val = answer.get("answer") or answer.get("answer_file") or ""
            val = str(val).strip()
            if val and not val.startswith("@"):
                val = f"@{val}"
            return val
    return ""


# ---------------------------------------------------------------------------
# Cache builder
# ---------------------------------------------------------------------------

def build_cache(client, event_slug, schedule_version):
    """
    Fetch and normalise all schedule data into:

      submissions_map  : { code → submission_dict }
        submission_dict: {
          code, title, abstract, track, submission_type, image,
          speakers: [{code, name, avatar, telegram}],
          slots: [{slot_index, start, end, room_id, room_name}]
        }

      slots_flat       : [ {submission_code, slot_index, start, end, room_id, room_name} ]
      submissions_list : [ submission_dict, ... ] (sorted by first start time, then title)
      event            : { name, slug }
      schedule_version : str  (resolved version name)
    """
    logger.info("Fetching schedule '%s' for event '%s'…", schedule_version, event_slug)

    # -- Event details --
    event_details = client.get_event(event_slug)
    event_name = _localized(event_details.get("name", ""))

    # -- Schedule --
    schedule = client.get_schedule(
        event_slug,
        schedule_version,
        expand=[
            "slots",
            "slots.room",
            "slots.submission",
            "slots.submission.speakers",
            "slots.submission.track",
            "slots.submission.submission_type",
        ],
    )
    resolved_version = schedule.get("version") or schedule_version
    slots_raw = schedule.get("slots", [])
    logger.info("Processing %d raw slots…", len(slots_raw))

    # -- Speaker telegram handles --
    logger.info("Fetching speakers with answers for telegram handles…")
    telegram_by_speaker = {}
    try:
        for sp in client.list_speakers(
            event_slug,
            expand=["answers", "answers.question"],
        ):
            sp_code = sp.get("code", "")
            if sp_code:
                telegram_by_speaker[sp_code] = _find_telegram(sp.get("answers", []))
    except Exception as exc:
        logger.warning("Could not fetch speaker answers: %s", exc)

    slot_index_counter = {}
    submissions_map = {}
    slots_flat = []

    is_wip = (schedule_version == "wip")

    for slot in slots_raw:
        sub_data = slot.get("submission")
        start    = slot.get("start") or ""
        end      = slot.get("end") or ""

        room_raw   = slot.get("room") or {}
        room_id    = room_raw.get("id") if isinstance(room_raw, dict) else room_raw
        room_name  = _localized(room_raw.get("name", "")) if isinstance(room_raw, dict) else str(room_raw or "")

        if not isinstance(sub_data, dict):
            continue

        code = sub_data.get("code", "")
        if not code:
            continue

        if not is_wip:
            track_data = sub_data.get("track") or {}
            track_name = _localized(track_data.get("name", "")) if isinstance(track_data, dict) else ""
            if track_name.strip().lower() == "internal":
                continue
            tags = sub_data.get("tags", [])
            if any(
                (isinstance(t, dict) and t.get("tag", "").strip().lower() == "internal")
                for t in tags
            ):
                continue

        if code not in submissions_map:
            track_raw  = sub_data.get("track")
            if isinstance(track_raw, dict):
                track_obj = {
                    "id":    track_raw.get("id"),
                    "name":  _localized(track_raw.get("name", "")),
                    "color": track_raw.get("color") or "#666666",
                }
            else:
                track_obj = None

            stype_raw = sub_data.get("submission_type")
            stype = _localized(stype_raw.get("name", "")) if isinstance(stype_raw, dict) else str(stype_raw or "")

            speakers = []
            for sp in sub_data.get("speakers", []):
                if not isinstance(sp, dict):
                    continue
                sp_code   = sp.get("code", "")
                sp_avatar = sp.get("avatar_url") or sp.get("avatar") or None
                speakers.append({
                    "code":     sp_code,
                    "name":     sp.get("name", ""),
                    "avatar":   sp_avatar,
                    "telegram": telegram_by_speaker.get(sp_code, ""),
                })

            submissions_map[code] = {
                "code":            code,
                "title":           sub_data.get("title", ""),
                "abstract":        sub_data.get("abstract", ""),
                "notes":           sub_data.get("notes") or "",
                "internal_notes":  sub_data.get("internal_notes") or "",
                "track":           track_obj,
                "submission_type": stype,
                "image":           sub_data.get("image") or None,
                "speakers":        speakers,
                "slots":           [],
            }

        idx = slot_index_counter.get(code, 0)
        slot_index_counter[code] = idx + 1

        slot_entry = {
            "slot_index": idx,
            "start":      start,
            "end":        end,
            "room_id":    room_id,
            "room_name":  room_name,
        }
        submissions_map[code]["slots"].append(slot_entry)
        slots_flat.append({
            "submission_code": code,
            "slot_index":      idx,
            "start":           start,
            "end":             end,
            "room_id":         room_id,
            "room_name":       room_name,
        })

    for sub in submissions_map.values():
        sub["slots"].sort(key=lambda s: s["start"])

    submissions_list = sorted(
        submissions_map.values(),
        key=lambda s: (
            s["slots"][0]["start"] if s["slots"] else "9999",
            s["title"].lower(),
        ),
    )

    logger.info(
        "Cache built: %d submissions, %d slots, %d speakers with telegram",
        len(submissions_map),
        len(slots_flat),
        sum(1 for t in telegram_by_speaker.values() if t),
    )

    return {
        "event":            {"name": event_name, "slug": event_slug},
        "schedule_version": resolved_version,
        "submissions_map":  submissions_map,
        "submissions_list": submissions_list,
        "slots_flat":       slots_flat,
    }


# ---------------------------------------------------------------------------
# Background fetch + public accessors
# ---------------------------------------------------------------------------

def _do_fetch():
    try:
        client = PretalxClient(url=PRETALX_URL, apikey=PRETALX_APIKEY)
        data   = build_cache(client, PRETALX_EVENT, SCHEDULE_VERSION)

        with _cache["lock"]:
            _cache["data"]         = data
            _cache["last_fetched"] = time.time()
            _cache["error"]        = None

        logger.info("Pretalx cache refreshed successfully.")
    except Exception as exc:
        logger.error("Pretalx cache fetch failed: %s", exc)
        with _cache["lock"]:
            _cache["error"] = str(exc)


def _periodic_refresh():
    while True:
        time.sleep(CACHE_REFRESH_INTERVAL)
        logger.info("Scheduled Pretalx cache refresh…")
        _do_fetch()


def start_background_fetch():
    """Kick off initial fetch + periodic refresh. Call once at app startup."""
    t1 = threading.Thread(target=_do_fetch, daemon=True)
    t1.start()
    t2 = threading.Thread(target=_periodic_refresh, daemon=True)
    t2.start()


def trigger_refresh():
    """Manually trigger a non-blocking refresh (e.g. from /api/refresh)."""
    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()


def get_cache():
    """Return the current cache dict (may be None if still loading)."""
    with _cache["lock"]:
        return _cache["data"]


def get_cache_status():
    with _cache["lock"]:
        return {
            "has_data":         _cache["data"] is not None,
            "last_fetched":     _cache["last_fetched"],
            "error":            _cache["error"],
            "event":            (_cache["data"] or {}).get("event"),
            "schedule_version": (_cache["data"] or {}).get("schedule_version"),
        }
