"""
app.py — Flask backend for Feedback Viewer.

A web service for viewing attendee feedback collected during Eurofurence conventions.
"""

import os
import sys
import logging
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (
    Flask, render_template, jsonify, request, g,
)

import db
import auth
import pretalx_cache
from data_loader import list_conventions, load_convention_data, load_occupancies_data

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PRETALX_URL    = os.environ.get("PRETALX_URL", "")
PRETALX_APIKEY = os.environ.get("PRETALX_APIKEY", "")
PRETALX_EVENT  = os.environ.get("PRETALX_EVENT_SLUG", "")
BASE_PATH       = os.environ.get("BASE_PATH", "/ef-feedback")
EVENT_TIMEZONE  = os.environ.get("EVENT_TIMEZONE", "Europe/Berlin")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

if not PRETALX_URL or not PRETALX_APIKEY or not PRETALX_EVENT:
    logger.info("Pretalx live credentials not fully set; operating in file-based data mode.")


def _resolve_event_timezone() -> ZoneInfo | timezone:
    """Resolve the configured EVENT_TIMEZONE into a tzinfo object."""
    try:
        return ZoneInfo(EVENT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown EVENT_TIMEZONE %r, falling back to UTC", EVENT_TIMEZONE)
        return timezone.utc


EVENT_TZ = _resolve_event_timezone()

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"{BASE_PATH}/static",
)
app.config["BASE_PATH"] = BASE_PATH


@app.context_processor
def inject_globals():
    return {
        "base_path":         BASE_PATH,
        "user":              getattr(g, "user", None),
        "pretalx_orga_base": f"{PRETALX_URL}/orga/event/{PRETALX_EVENT}" if PRETALX_URL and PRETALX_EVENT else "",
    }


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

db.init_db()

if PRETALX_URL and PRETALX_APIKEY and PRETALX_EVENT:
    pretalx_cache.start_background_fetch()


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]     = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data: https:; "
        "script-src 'self';"
    )
    return response


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/")
@app.route(f"{BASE_PATH}")
@auth.require_read_feedback
def page_index():
    """Render the Feedback viewer page."""
    return render_template("feedback.html", page="feedback")


@app.route(f"{BASE_PATH}/feedback")
@auth.require_read_feedback
def page_feedback():
    """Render the Feedback viewer page."""
    return render_template("feedback.html", page="feedback")


@app.route(f"{BASE_PATH}/occupancies")
@app.route(f"{BASE_PATH}/occupancy")
@auth.require_read_feedback
def page_occupancies():
    """Render the Occupancies viewer page."""
    return render_template("occupancies.html", page="occupancies")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/health")
def api_health():
    """Cache and DB status check."""
    status = pretalx_cache.get_cache_status()
    conventions = list_conventions()
    status["conventions_count"] = len(conventions)
    status["conventions"] = [c["id"] for c in conventions]
    return jsonify(status)


@app.route(f"{BASE_PATH}/api/debug/headers")
def api_debug_headers():
    """Dev helper: return all request headers + resolved user."""
    return jsonify({
        "headers": dict(request.headers),
        "user":    auth.get_current_user(),
    })


@app.route(f"{BASE_PATH}/api/conventions")
@auth.require_read_feedback
def api_conventions():
    """List available conventions determined from data/feedback files."""
    conventions = list_conventions()
    return jsonify({"conventions": conventions})


@app.route(f"{BASE_PATH}/api/convention/<con_id>")
@auth.require_read_feedback
def api_convention_detail(con_id):
    """Retrieve grouped feedback, occupancy, and event details for a convention."""
    data = load_convention_data(con_id)
    if data is None:
        return jsonify({"error": f"Convention '{con_id}' not found"}), 404
    return jsonify(data)


@app.route(f"{BASE_PATH}/api/occupancies/<con_id>")
@auth.require_read_feedback
def api_occupancies(con_id):
    """Retrieve all occupancy ratings for a convention."""
    data = load_occupancies_data(con_id)
    if data is None:
        return jsonify({"error": f"Convention '{con_id}' not found"}), 404
    return jsonify(data)


@app.route(f"{BASE_PATH}/api/refresh", methods=["POST", "GET"])
@auth.require_admin
def api_refresh():
    """Trigger a background refresh of the Pretalx cache if configured."""
    if PRETALX_URL and PRETALX_APIKEY and PRETALX_EVENT:
        pretalx_cache.trigger_refresh()
        return jsonify({"status": "refresh_triggered"})
    return jsonify({"status": "pretalx_not_configured"}), 400


@app.route(f"{BASE_PATH}/api/submissions")
@auth.require_read_feedback
def api_submissions():
    """List cached submissions from live Pretalx cache if available."""
    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    q = (request.args.get("q") or "").strip().lower()

    result = []
    for sub in cache["submissions_list"]:
        if q:
            hay = f"{sub['title']} {sub['code']} {' '.join(s['name'] for s in sub['speakers'])}".lower()
            if q not in hay:
                continue

        result.append({
            "code":            sub["code"],
            "title":           sub["title"],
            "track":           sub["track"],
            "submission_type": sub["submission_type"],
            "speakers":        [{"name": s["name"], "code": s["code"]} for s in sub["speakers"]],
            "slots":           sub["slots"],
        })

    return jsonify({"submissions": result, "total": len(result)})
