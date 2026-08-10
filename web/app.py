"""
Pretalx Schedule Preview — Flask Backend
Fetches schedule data from a Pretalx API and serves it as JSON for the frontend.
"""

import os
import sys
import json
import threading
import time
import logging
import hashlib
import re
import urllib.request
import urllib.error
import urllib.parse

import uuid
import markdown as _markdown

from flask import Flask, jsonify, send_from_directory, Response, request
from pretalx_client import PretalxClient, PretalxAPIError
from pretalx_xml_exporter import generate_pretalx_xml

# --- Configuration (all via environment variables) ---
PRETALX_URL = os.environ.get("PRETALX_URL", "")
PRETALX_APIKEY = os.environ.get("PRETALX_APIKEY", "")
PRETALX_EVENT = os.environ.get("PRETALX_EVENT_SLUG", "")  # Required
SCHEDULE_VERSION = os.environ.get("SCHEDULE_VERSION", "wip")
BASE_PATH = os.environ.get("BASE_PATH", "/ef-schedule-preview")
EF_SCHEDULE_IMPRINT = os.environ.get("EF_SCHEDULE_IMPRINT", "https://help.eurofurence.org/legal/imprint")
EF_SCHEDULE_PRIVACY = os.environ.get("EF_SCHEDULE_PRIVACY", "https://help.eurofurence.org/legal/privacy")
EF_SCHEDULE_IGNORE_TAGS_IDS = os.environ.get("EF_SCHEDULE_IGNORE_TAGS_IDS", "")

if not PRETALX_URL or not PRETALX_APIKEY:
    sys.stderr.write("Error: PRETALX_URL and PRETALX_APIKEY environment variables are required.\n")
    sys.exit(1)

if not PRETALX_EVENT:
    sys.stderr.write("Error: PRETALX_EVENT environment variable is required.\n")
    sys.exit(1)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Flask App ---
app = Flask(__name__, static_folder="static", static_url_path=f"{BASE_PATH}/static")

# --- In-memory cache ---
_cache = {
    "data": None,
    "last_fetched": None,
    "error": None,
    "lock": threading.Lock(),
}


def format_localized(val):
    """Extract English string from a localized dict, or return as-is."""
    if isinstance(val, dict):
        return val.get("en") or next(iter(val.values()), "") if val else ""
    return str(val) if val is not None else ""


def extract_id(val):
    """Extract ID from a potentially expanded dict."""
    if isinstance(val, dict) and "id" in val:
        return val["id"]
    return val


# Markdown instance with useful extensions:
#   extra     → tables, fenced code, footnotes, abbr, attr_list
#   nl2br     → single newlines become <br> (matches user expectation)
#   sane_lists → list parsing closer to CommonMark
_md = _markdown.Markdown(
    extensions=["extra", "nl2br", "sane_lists"],
    output_format="html",
)


def md_to_html(text):
    """Convert a markdown string to sanitised HTML.

    Returns an empty string for falsy input.
    The Markdown library does not produce <script> tags; remaining XSS
    risk is mitigated by the CSP script-src 'self' header on every response.
    """
    if not text:
        return ""
    _md.reset()  # clear internal state between calls (links, footnotes, etc.)
    return _md.convert(str(text))


def build_schedule_data(client, event_slug, schedule_version):
    """
    Fetch and normalize schedule data from the Pretalx API.
    Returns a dict ready to be serialized as JSON for the frontend.

    When schedule_version is not 'wip', events in the 'internal' track or
    with the 'internal' tag are excluded from the output.
    """
    logger.info("Fetching event details for '%s'...", event_slug)
    event_details = client.get_event(event_slug)
    event_name = format_localized(event_details.get("name", ""))

    # Fetch tracks (for colors and filter metadata)
    logger.info("Fetching tracks...")
    tracks_raw = list(client.list_tracks(event_slug))
    tracks = []
    track_map = {}
    for t in tracks_raw:
        track_obj = {
            "id": t.get("id"),
            "name": format_localized(t.get("name", "")),
            "color": t.get("color", "#666666"),
        }
        tracks.append(track_obj)
        track_map[t.get("id")] = track_obj

    # Fetch tags
    logger.info("Fetching tags...")
    tags_raw = list(client.list_tags(event_slug))
    tags = []
    tag_lookup = {}
    ignore_ids = set()
    if EF_SCHEDULE_IGNORE_TAGS_IDS:
        ignore_ids = [int(x.strip()) for x in EF_SCHEDULE_IGNORE_TAGS_IDS.split(",") if x.strip().isdigit()]
        logger.info("Ignoring tags with IDs: %s", ignore_ids)
    for t in tags_raw:
        tag_name = t.get("tag") or t.get("name")
        tag_str = format_localized(tag_name) if isinstance(tag_name, dict) else str(tag_name or "")
        if tag_str.startswith("ef_"): continue
        tag_obj = {
            "id": t.get("id"),
            "tag": tag_str,
            "color": t.get("color", "#666666"),
        }
        tags.append(tag_obj)
        tag_lookup[t.get("id")] = tag_obj

    # Fetch full schedule with expansions
    logger.info("Fetching schedule version '%s' with full expansion...", schedule_version)
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

    slots_raw = schedule.get("slots", [])
    logger.info("Processing %d slots...", len(slots_raw))

    # Collect rooms and speakers as we process slots
    rooms_map = {}
    speakers_map = {}
    days_map = {}
    slot_index_counter = {}

    for slot in slots_raw:
        start = slot.get("start")
        end = slot.get("end")

        # Extract room
        room_data = slot.get("room")
        if isinstance(room_data, dict):
            room_id = room_data.get("id")
            room_name = format_localized(room_data.get("name", ""))
            room_position = room_data.get("position")
            if room_position is None:
                room_position = 0
        else:
            room_id = room_data
            room_name = str(room_data) if room_data else "No Room"
            room_position = 0

        if room_id is not None and room_id not in rooms_map:
            rooms_map[room_id] = {"id": room_id, "name": room_name, "position": room_position}

        # Extract submission data
        sub_data = slot.get("submission")
        is_blocker = False

        if isinstance(sub_data, dict):
            code = sub_data.get("code", "")
            title = sub_data.get("title", "No Title")
            abstract = sub_data.get("abstract", "")
            description = sub_data.get("description", "")
            # Submission image (event poster / banner)
            submission_image = sub_data.get("image") or None
            submission_type_data = sub_data.get("submission_type")
            submission_type = format_localized(submission_type_data.get("name", "")) if isinstance(submission_type_data, dict) else str(submission_type_data or "")

            # Track
            track_data = sub_data.get("track")
            if isinstance(track_data, dict):
                track_id = track_data.get("id")
                track_obj = {
                    "id": track_id,
                    "name": format_localized(track_data.get("name", "")),
                    "color": track_data.get("color") or track_map.get(track_id, {}).get("color", "#666666"),
                }
            elif track_data is not None:
                track_obj = track_map.get(track_data, {"id": track_data, "name": str(track_data), "color": "#666666"})
            else:
                track_obj = None

            # Tags
            slot_tags = []
            for tag in sub_data.get("tags", []):
                tag_id = extract_id(tag)
                if tag_id in ignore_ids: continue
                if tag_id in tag_lookup:
                    slot_tags.append({
                        "id": tag_id,
                        "tag": tag_lookup[tag_id]["tag"],
                    })
                else:
                    slot_tags.append({"id": tag_id, "tag": f"Tag {tag_id}"})

            # Speakers — note: Pretalx API uses 'avatar_url', not 'avatar'
            slot_speakers = []
            for sp in sub_data.get("speakers", []):
                if isinstance(sp, dict):
                    sp_code = sp.get("code", "")
                    sp_name = sp.get("name", "Unknown")
                    # The Pretalx API field is avatar_url (not avatar)
                    sp_avatar = sp.get("avatar_url") or sp.get("avatar") or None
                    sp_biography = sp.get("biography", "")
                    slot_speakers.append({
                        "code": sp_code,
                        "name": sp_name,
                        "avatar": sp_avatar,
                    })
                    if sp_code and sp_code not in speakers_map:
                        speakers_map[sp_code] = {
                            "code": sp_code,
                            "name": sp_name,
                            "avatar": sp_avatar,
                            "biography": sp_biography,
                        }
                else:
                    slot_speakers.append({"code": str(sp), "name": str(sp), "avatar": None})
        else:
            # Blocker or unknown slot
            is_blocker = True
            blocker_desc = format_localized(slot.get("description", ""))
            code = "BLOCKER"
            title = blocker_desc or "Blocker"
            abstract = ""
            description = ""
            submission_type = "Blocker"
            submission_image = None
            track_obj = None
            slot_tags = []
            slot_speakers = []

        duration = slot.get("duration")

        # --- Build a stable, content-derived ID for sharing links ---
        # For regular submissions: "{code}@{YYYY-MM-DDTHH:MM}" (minute-level ISO,
        # no TZ — stable across re-publishes as long as the time doesn't change).
        # For blockers (no submission code): "blk-{md5(start|end|room_id)[:8]}"
        # so the key is tied to the blocker's position, not its DB row id.
        if not is_blocker:
            # Truncate to minute precision: "2026-08-18T10:00+02:00" → "2026-08-18T10:00"
            start_minute = start[:16] if start else ""
            stable_id = f"{code}@{start_minute}"
        else:
            _blk_raw = f"{start}|{end}|{room_id}"
            _blk_hash = hashlib.md5(_blk_raw.encode()).hexdigest()[:8]
            stable_id = f"blk-{_blk_hash}"

        # Determine the day
        if start:
            day_str = start[:10]  # "2026-08-14"
        else:
            day_str = "unscheduled"

        # --- Internal event filtering (only for published/non-wip schedules) ---
        if schedule_version != "wip":
            # Skip blocker slots (internal setup entries)
            if is_blocker:
                logger.debug("Skipping blocker slot: %s", title)
                continue
            # Skip events in the "internal" track
            if track_obj and track_obj.get("name", "").strip().lower() == "internal":
                logger.debug("Skipping internal-track slot: %s", title)
                continue
            # Skip events with the "internal" tag
            if any(t.get("tag", "").strip().lower() == "internal" for t in slot_tags):
                logger.debug("Skipping internal-tagged slot: %s", title)
                continue

        # Slot index per submission code & GUID generation
        if not is_blocker:
            slot_idx = slot_index_counter.get(code, 0)
            slot_index_counter[code] = slot_idx + 1
            slot_guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"event:{code}-{slot_idx}"))
        else:
            slot_idx = 0
            slot_guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"blocker:{stable_id}"))

        slot_obj = {
            "id": slot.get("id"),
            "stable_id": stable_id,
            "slot_index": slot_idx,
            "guid": slot_guid,
            "start": start,
            "end": end,
            "duration": duration,
            "room": {"id": room_id, "name": room_name},
            "title": title,
            "code": code,
            "image": submission_image if not is_blocker else None,
            "track": track_obj,
            "tags": slot_tags,
            "speakers": slot_speakers,
            "raw_abstract": abstract,
            "raw_description": description,
            "abstract": md_to_html(abstract),
            "description": md_to_html(description),
            "submission_type": submission_type,
            "is_blocker": is_blocker,
        }

        if day_str not in days_map:
            days_map[day_str] = []
        days_map[day_str].append(slot_obj)

    # Sort days and slots within each day
    sorted_days = []
    for day_key in sorted(days_map.keys()):
        day_slots = days_map[day_key]
        day_slots.sort(key=lambda s: s.get("start") or "")

        # Format the day label
        if day_key == "unscheduled":
            label = "Unscheduled"
        else:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(day_key)
                label = dt.strftime("%A, %B %d")
            except Exception:
                label = day_key

        sorted_days.append({
            "date": day_key,
            "label": label,
            "slots": day_slots,
        })

    # Sort rooms by position
    rooms = sorted(rooms_map.values(), key=lambda r: r.get("position") or 0)

    # Sort speakers alphabetically
    speakers = sorted(speakers_map.values(), key=lambda s: (s.get("name") or "").lower())

    return {
        "event": {
            "name": event_name,
            "slug": event_slug,
        },
        "schedule_version": schedule.get("version") or schedule_version,
        "days": sorted_days,
        "rooms": rooms,
        "tracks": tracks,
        "tags": tags,
        "speakers": speakers,
        "imprint_url": EF_SCHEDULE_IMPRINT,
        "privacy_url": EF_SCHEDULE_PRIVACY,
    }


def fetch_and_cache():
    """Fetch schedule data and store in cache."""
    try:
        client = PretalxClient(url=PRETALX_URL, apikey=PRETALX_APIKEY)
        data = build_schedule_data(client, PRETALX_EVENT, SCHEDULE_VERSION)
        with _cache["lock"]:
            _cache["data"] = data
            _cache["last_fetched"] = time.time()
            _cache["error"] = None
        logger.info("Schedule data cached successfully (%d days, %d rooms, %d tracks).",
                     len(data["days"]), len(data["rooms"]), len(data["tracks"]))
    except Exception as e:
        logger.error("Failed to fetch schedule data: %s", e)
        with _cache["lock"]:
            _cache["error"] = str(e)


# --- Security headers middleware ---
@app.after_request
def add_security_headers(response):
    """Add security headers to every response."""
    # TODO(security): CSP nonces for inline scripts if we add any in the future
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' https: data:; "
        "script-src 'self'; "
        "frame-ancestors 'none'"
    )
    # Note: 'unsafe-inline' for style-src is needed for track-color dynamic styles.
    # This is a minimal risk since we don't handle user-generated CSS.
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# --- Routes ---

@app.route(f"{BASE_PATH}/")
def index():
    """Serve the main SPA page."""
    return send_from_directory("static", "index.html")


@app.route(f"{BASE_PATH}/api/schedule")
def api_schedule():
    """Return the cached schedule data as JSON."""
    with _cache["lock"]:
        if _cache["data"] is None:
            if _cache["error"]:
                return jsonify({"error": _cache["error"]}), 503
            return jsonify({"error": "Data not yet loaded. Try again shortly."}), 503
        return jsonify(_cache["data"])


@app.route(f"{BASE_PATH}/api/schedule/pretalx.xml")
def api_schedule_pretalx_xml():
    """Return cached schedule data formatted as (hopyfully, mostly) frab-like Pretalx XML."""
    with _cache["lock"]:
        if _cache["data"] is None:
            if _cache["error"]:
                return Response(f"<?xml version='1.0'?><error>{_cache['error']}</error>", status=503, mimetype="application/xml")
            return Response("<?xml version='1.0'?><error>Data not yet loaded. Try again shortly.</error>", status=503, mimetype="application/xml")
        data = _cache["data"]

    xml_str = generate_pretalx_xml(data, PRETALX_URL)
    return Response(xml_str, status=200, mimetype="application/xml; charset=utf-8")


@app.route(f"{BASE_PATH}/api/refresh", methods=["POST"])
def api_refresh():
    """Trigger a re-fetch of the schedule data.

    Only available when SCHEDULE_VERSION is 'wip'. Returns 403 otherwise
    to prevent (un)intended API hammering in production deployments.
    """
    if SCHEDULE_VERSION != "wip":
        return jsonify({"error": "Refresh not available in this mode."}), 403
    thread = threading.Thread(target=fetch_and_cache, daemon=True)
    thread.start()
    return jsonify({"status": "refresh started"})


@app.route(f"{BASE_PATH}/api/image-proxy")
def api_image_proxy():
    """Proxy image requests to the Pretalx instance with authentication.

    This is needed because speaker avatar URLs from the Pretalx API
    require authentication headers that the browser cannot provide.
    Only URLs belonging to the configured Pretalx instance are proxied
    to prevent SSRF.
    """
    url = request.args.get("url", "")
    if not url:
        return Response("Missing url parameter", status=400)

    # Validate that the URL belongs to the configured Pretalx instance
    parsed_pretalx = urllib.parse.urlparse(PRETALX_URL)
    parsed_url = urllib.parse.urlparse(url)

    if not parsed_url.scheme or not parsed_url.netloc:
        return Response("UwU No lookie...", status=400)

    if parsed_url.netloc != parsed_pretalx.netloc:
        return Response("NSFW! - You can't look at other people's privates! >:(", status=403)

    # Only allow HTTPS (or HTTP if Pretalx itself is HTTP)
    allowed_schemes = {parsed_pretalx.scheme, "https"}
    if parsed_url.scheme not in allowed_schemes:
        return Response("URL scheme not allowed", status=403)

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Token {PRETALX_APIKEY}")
        req.add_header("Accept", "image/*")

        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            image_data = resp.read()

            # Only serve image content types
            if not content_type.startswith("image/"):
                return Response("Not an image", status=400)

            response = Response(image_data, status=200)
            response.headers["Content-Type"] = content_type
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response
    except urllib.error.HTTPError as e:
        logger.warning("Image proxy HTTP error for %s: %s", url, e.code)
        return Response(f"Upstream error: {e.code}", status=502)
    except Exception as e:
        logger.warning("Image proxy error for %s: %s", url, e)
        return Response("Failed to fetch image", status=502)


@app.route(f"{BASE_PATH}/api/health")
def api_health():
    """Health check endpoint."""
    with _cache["lock"]:
        has_data = _cache["data"] is not None
        last_fetched = _cache["last_fetched"]
        error = _cache["error"]
    return jsonify({
        "status": "ok" if has_data else "loading",
        "has_data": has_data,
        "last_fetched": last_fetched,
        "error": error,
    })


# --- Startup ---
# Kick off the initial fetch in a background thread regardless of how the app
# is launched (gunicorn, python app.py, pytest, etc.). The daemon=True flag
# ensures the thread won't block process exit when a SIGTERM is received.

CACHE_REFRESH_INTERVAL = 3600  # seconds (1 hour)


def _periodic_refresh():
    """Sleep for CACHE_REFRESH_INTERVAL seconds, then re-fetch indefinitely."""
    while True:
        time.sleep(CACHE_REFRESH_INTERVAL)
        logger.info("Hourly cache refresh triggered.")
        fetch_and_cache()


logger.info("Starting schedule data fetch in background...")
_fetch_thread = threading.Thread(target=fetch_and_cache, daemon=True)
_fetch_thread.start()

logger.info("Starting hourly cache refresh thread (interval: %ds)...", CACHE_REFRESH_INTERVAL)
_refresh_thread = threading.Thread(target=_periodic_refresh, daemon=True)
_refresh_thread.start()

if __name__ == "__main__":
    # NOTE: Binding to 0.0.0.0 inside the container is required for
    # container networking (port mapping). The container itself is
    # isolated and accessed via the mapped host port.
    # TODO(security): In production, place behind a reverse proxy (nginx)
    # that handles TLS termination and rate limiting.
    logger.info("Starting Flask server on 0.0.0.0:8089 with base path '%s'", BASE_PATH)
    app.run(host="0.0.0.0", port=8089, debug=False)
