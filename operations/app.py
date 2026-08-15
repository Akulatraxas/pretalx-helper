"""
app.py — Flask backend for Operations Resource Manager.

Multi-page application: each of the four main sections is a full HTML page
rendered by Jinja2. JSON API endpoints power the per-page JS interactions.
"""

import os
import sys
import logging
import io
import csv
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, Response, g,
)

import db
import auth
import pretalx_cache
import announcements
from db import DEPARTMENTS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PRETALX_URL    = os.environ.get("PRETALX_URL", "")
PRETALX_APIKEY = os.environ.get("PRETALX_APIKEY", "")
PRETALX_EVENT  = os.environ.get("PRETALX_EVENT_SLUG", "")
BASE_PATH       = os.environ.get("BASE_PATH", "/ef-operations")
EVENT_TIMEZONE  = os.environ.get("EVENT_TIMEZONE", "Europe/Berlin")

if not PRETALX_URL or not PRETALX_APIKEY:
    sys.stderr.write("Error: PRETALX_URL and PRETALX_APIKEY are required.\n")
    sys.exit(1)
if not PRETALX_EVENT:
    sys.stderr.write("Error: PRETALX_EVENT_SLUG is required.\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_event_timezone() -> ZoneInfo | timezone:
    """
    Resolve the configured EVENT_TIMEZONE into a tzinfo object.
    
    Falls back to UTC if the timezone is invalid or unknown.
    """
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

# Make BASE_PATH, DEPARTMENTS, and pretalx orga link base available in all templates
@app.context_processor
def inject_globals():
    return {
        "base_path":          BASE_PATH,
        "departments":        DEPARTMENTS,
        "user":               getattr(g, "user", None),
        "pretalx_orga_base":  f"{PRETALX_URL}/orga/event/{PRETALX_EVENT}",
    }

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

db.init_db()
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
@auth.require_read_any
def page_index():
    """Render the landing / index overview page."""
    return render_template("index.html", page="index")


@app.route(f"{BASE_PATH}/resources")
@auth.require_read_events
def page_resources():
    """Render the resources page."""
    return render_template("resources.html", page="resources")


@app.route(f"{BASE_PATH}/events")
@auth.require_read_events
def page_events():
    """
    Render the events page.
    
    Returns:
    	str: The rendered events HTML response.
    """
    return render_template("events.html", page="events")


@app.route(f"{BASE_PATH}/output")
@auth.require_read_events
def page_output():
    """
    Render the output page.
    """
    return render_template("output.html", page="output")


@app.route(f"{BASE_PATH}/operations")
@auth.require_read_operations
def page_operations():
    """Render the operations page."""
    return render_template("operations.html", page="operations")


@app.route(f"{BASE_PATH}/occupancy")
@auth.require_read_operations
def page_occupancy():
    """Render the occupancy page."""
    return render_template("occupancy.html", page="occupancy")


@app.route(f"{BASE_PATH}/delays")
@auth.require_read_announcements
def page_delays():
    """Render the delays page."""
    return render_template("delays.html", page="delays")

# ---------------------------------------------------------------------------
# API — Health & debug
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/health")
def api_health():
    status = pretalx_cache.get_cache_status()
    return jsonify({"status": "ok" if status["has_data"] else "loading", **status})


@app.route(f"{BASE_PATH}/api/debug/headers")
def api_debug_headers():
    lines = [f"{k}: {v}" for k, v in sorted(request.headers)]
    return Response("\n".join(lines), content_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# API — Pretalx cache
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/refresh", methods=["POST","GET"])
@auth.require_admin
def api_refresh():
    """Start refreshing the Pretalx cache.
    
    Returns:
        Response: A JSON response confirming that the refresh started.
    """
    pretalx_cache.trigger_refresh()
    return jsonify({"status": "refresh started"})


@app.route(f"{BASE_PATH}/api/submissions")
@auth.require_read_events
def api_submissions():
    """
    List cached submissions, optionally filtered by a search query.
    
    Returns:
        JSON response containing the matching submissions and their total count.
        Each submission includes assignment and conflict indicators. Returns HTTP
        503 when the cache is unavailable.
    """
    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    q = (request.args.get("q") or "").strip().lower()

    # Load which codes have assignments (one cheap DB query)
    codes_with_data = db.get_codes_with_assignments()

    # Load conflict codes (for badges)
    conflict_codes = _get_conflict_codes(cache)

    result = []
    for sub in cache["submissions_list"]:
        code = sub["code"]

        # Filter by search query
        if q:
            hay = f"{sub['title']} {sub['code']} {' '.join(s['name'] for s in sub['speakers'])}".lower()
            if q not in hay:
                continue

        result.append({
            "code":            code,
            "title":           sub["title"],
            "track":           sub["track"],
            "submission_type": sub["submission_type"],
            "speakers":        [{"name": s["name"], "code": s["code"]} for s in sub["speakers"]],
            "slots":           sub["slots"],
            "has_data":        code in codes_with_data,
            "has_conflict":    code in conflict_codes,
        })

    return jsonify({"submissions": result, "total": len(result)})


@app.route(f"{BASE_PATH}/api/submission/<code>")
@auth.require_read_events
def api_submission_detail(code):
    """
    Retrieve detailed submission data, including its resource assignments and conflict status.
    
    Parameters:
        code (str): The unique submission code.
    
    Returns:
        Response: A JSON response containing the submission details, assignments, and conflict status.
            Returns HTTP 503 when the cache is unavailable or HTTP 404 when the submission is missing.
    """
    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    sub = cache["submissions_map"].get(code)
    if sub is None:
        return jsonify({"error": "Submission not found"}), 404

    assignments = db.get_submission_assignments(code)
    conflict_codes = _get_conflict_codes(cache)

    return jsonify({
        **sub,
        "assignments":   assignments,
        "has_conflict":  code in conflict_codes,
    })


# ---------------------------------------------------------------------------
# API — Resources CRUD
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/resources", methods=["GET"])
@auth.require_read_events
def api_resources_list():
    """List resources, optionally filtered by a case-insensitive name search.
    
    Parameters:
        q (str): Optional search text matched against resource names.
    
    Returns:
        Response: A JSON response containing the matching resources.
    """
    q = (request.args.get("q") or "").strip().lower()
    resources = db.list_resources()
    if q:
        resources = [r for r in resources if q in r["name"].lower()]
    return jsonify({"resources": resources})


@app.route(f"{BASE_PATH}/api/resources", methods=["POST"])
@auth.require_write_events
def api_resources_create():
    """Create a resource from the request JSON payload.
    
    Returns:
        A JSON response containing the created resource ID with status 201.
        Invalid names return status 400, and duplicate names return status 409.
    """
    data = request.get_json(force=True) or {}
    name  = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    amount = int(data.get("amount") or 0)
    depts  = [d for d in (data.get("departments") or []) if d in DEPARTMENTS]
    try:
        rid = db.create_resource(name, amount, depts, user_email=g.user.get("email"))
    except Exception as exc:
        if "UNIQUE" in str(exc):
            return jsonify({"error": "A resource with that name already exists"}), 409
        raise
    return jsonify({"id": rid}), 201


@app.route(f"{BASE_PATH}/api/resources/<int:rid>", methods=["PATCH"])
@auth.require_write_events
def api_resources_update(rid):
    """
    Update a resource's name, amount, and department assignments.
    
    Parameters:
        rid: The identifier of the resource to update.
    
    Returns:
        A JSON response indicating whether the update succeeded.
    """
    data = request.get_json(force=True) or {}
    name   = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    amount = int(data.get("amount") or 0)
    depts  = [d for d in (data.get("departments") or []) if d in DEPARTMENTS]
    db.update_resource(rid, name, amount, depts, user_email=g.user.get("email"))
    return jsonify({"ok": True})


@app.route(f"{BASE_PATH}/api/resources/<int:rid>", methods=["DELETE"])
@auth.require_write_events
def api_resources_delete(rid):
    """Delete a resource by its identifier."""
    db.delete_resource(rid, user_email=g.user.get("email"))
    return jsonify({"ok": True})


@app.route(f"{BASE_PATH}/api/resources/<int:rid>/usages")
@auth.require_read_events
def api_resource_usages(rid):
    """
    Return all submissions that have this resource assigned, enriched with
    slot/title data from the Pretalx cache.
    """
    resource = db.get_resource(rid)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404

    usages = db.get_resource_usage(rid)

    cache = pretalx_cache.get_cache()
    sub_map = cache.get("submissions_map", {}) if cache else {}

    result = []
    for u in usages:
        code = u["submission_code"]
        sub  = sub_map.get(code)
        result.append({
            "submission_code":  code,
            "note":             u.get("note"),
            "department_override": u.get("department_override"),
            "title":            sub["title"]    if sub else code,
            "submission_type":  sub["submission_type"] if sub else None,
            "slots":            sub["slots"]    if sub else [],
            "speakers":         sub["speakers"] if sub else [],
        })

    return jsonify({"resource": resource, "usages": result, "total": len(result)})


# ---------------------------------------------------------------------------
# API — Submission resource assignments
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/submission/<code>/assignments", methods=["GET"])
@auth.require_read_events
def api_get_assignments(code):
    """Retrieve resource assignments for a submission.
    
    Parameters:
    	code (str): The submission code.
    
    Returns:
    	assignments (JSON response): The submission's resource assignments.
    """
    return jsonify(db.get_submission_assignments(code))


@app.route(f"{BASE_PATH}/api/submission/<code>/resources", methods=["POST"])
@auth.require_write_events
def api_add_resource(code):
    """
    Assigns a resource to a submission.
    
    Parameters:
        code (str): The submission code to associate with the resource.
    
    Returns:
        dict: A success response when the assignment is created, or an error response if the submission or resource is unavailable or the request is invalid.
    """
    cache = pretalx_cache.get_cache()
    if cache and code not in cache["submissions_map"]:
        return jsonify({"error": "Submission not found in cache"}), 404

    data          = request.get_json(force=True) or {}
    resource_id   = data.get("resource_id")
    note          = (data.get("note") or "").strip() or None
    dept_override = data.get("department_override") or None
    if dept_override and dept_override not in DEPARTMENTS:
        dept_override = None

    if not resource_id:
        return jsonify({"error": "resource_id is required"}), 400

    resource = db.get_resource(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found"}), 404

    db.add_submission_resource(
        code, resource_id, note, dept_override,
        user_email=g.user.get("email"),
    )
    return jsonify({"ok": True}), 201


@app.route(f"{BASE_PATH}/api/submission/<code>/resources/<int:assignment_id>", methods=["DELETE"])
@auth.require_write_events
def api_remove_resource(code, assignment_id):
    """Remove a resource assignment from a submission.
    
    Parameters:
    	code (str): Submission code associated with the assignment.
    	assignment_id (int): Identifier of the resource assignment to remove.
    
    Returns:
    	Response: A JSON response indicating whether the removal succeeded.
    """
    db.remove_submission_resource(assignment_id, user_email=g.user.get("email"))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Submission comments
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/submission/<code>/comments", methods=["POST"])
@auth.require_write_events
def api_add_comment(code):
    """Add a department-specific comment to a submission.
    
    Parameters:
        code (str): Submission code identifying the submission.
    
    Returns:
        Response: JSON containing the created comment ID with HTTP status 201.
    """
    cache = pretalx_cache.get_cache()
    if cache and code not in cache["submissions_map"]:
        return jsonify({"error": "Submission not found in cache"}), 404

    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    dept = data.get("department") or ""

    if not text:
        return jsonify({"error": "text is required"}), 400
    if dept not in DEPARTMENTS:
        return jsonify({"error": f"department must be one of {DEPARTMENTS}"}), 400

    comment_id = db.add_submission_comment(
        code, text, dept, user_email=g.user.get("email")
    )
    return jsonify({"id": comment_id}), 201


@app.route(f"{BASE_PATH}/api/submission/<code>/comments/<int:comment_id>", methods=["DELETE"])
@auth.require_write_events
def api_remove_comment(code, comment_id):
    """Remove a comment from a submission."""
    db.remove_submission_comment(comment_id, user_email=g.user.get("email"))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Output
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/output")
@auth.require_read_events
def api_output():
    """
    Builds slot-level rows for the output table, optionally filtered by department.
    
    The ``dept`` query parameter accepts ``all`` or a specific department name.
    
    Returns:
        JSON response containing the output rows and selected department, or an
        HTTP 503 response when the Pretalx cache is unavailable.
    """
    dept  = request.args.get("dept") or "all"
    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    conflict_codes = _get_conflict_codes(cache)
    by_code        = db.get_output_by_department(dept if dept != "all" else None)
    rows           = _build_output_rows(cache, by_code, conflict_codes)

    return jsonify({"rows": rows, "department": dept})


@app.route(f"{BASE_PATH}/api/output/csv")
@auth.require_read_events
def api_output_csv():
    """Export department-filtered operation assignments as a downloadable CSV file.
    
    Returns:
        Response: A CSV response containing scheduled submissions, speakers, resources,
            comments, and conflict indicators. Returns HTTP 503 if the Pretalx cache
            is unavailable.
    """
    dept  = request.args.get("dept") or "all"
    cache = pretalx_cache.get_cache()
    if cache is None:
        return Response("Cache not ready", status=503)

    conflict_codes = _get_conflict_codes(cache)
    by_code        = db.get_output_by_department(dept if dept != "all" else None)
    rows           = _build_output_rows(cache, by_code, conflict_codes)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Day", "Date", "Start", "End", "Room",
        "Code", "Title", "Submission Type", "Track",
        "Speakers", "Telegram Handles",
        "Resources", "Comments", "Conflict",
    ])

    for row in rows:
        speakers_str  = "; ".join(s["name"] for s in row.get("speakers", []))
        telegram_str  = "; ".join(
            f"@{s['telegram']}" for s in row.get("speakers", []) if s.get("telegram")
        )
        def _fmt_res(r):
            note = f" ({r['note']})" if r.get("note") else ""
            return f"{r['resource_name']}{note}"
        resources_str = "; ".join(_fmt_res(r) for r in row.get("resources", []))
        comments_str  = "; ".join(
            f"[{c['department']}] {c['text']}" for c in row.get("comments", [])
        )
        writer.writerow([
            row.get("day_label", ""),
            row.get("date", ""),
            row.get("start_time", ""),
            row.get("end_time", ""),
            row.get("room_name", ""),
            row.get("code", ""),
            row.get("title", ""),
            row.get("submission_type", ""),
            row.get("track_name", ""),
            speakers_str,
            telegram_str,
            resources_str,
            comments_str,
            "YES" if row.get("has_conflict") else "",
        ])

    safe_dept = dept.replace(" ", "_").replace("/", "-")
    filename  = f"operations_output_{safe_dept}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# API — Conflicts
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/conflicts")
@auth.require_read_events
def api_conflicts():
    """
    List resource assignment conflicts enriched with submission details.
    
    Returns:
        A JSON response containing the conflicts and their total count, or an
        error response with status 503 when the Pretalx cache is unavailable.
    """
    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    assignments = db.get_all_resource_assignments_for_conflict()
    conflicts   = pretalx_cache.find_conflicts(cache, assignments)

    # Enrich with submission titles
    sub_map = cache.get("submissions_map", {})
    for c in conflicts:
        c["conflicting_submissions"] = [
            {
                "code":  code,
                "title": sub_map.get(code, {}).get("title", code),
                "slots": sub_map.get(code, {}).get("slots", []),
            }
            for code in c["conflicting_codes"]
        ]

    return jsonify({"conflicts": conflicts, "total": len(conflicts)})


# ---------------------------------------------------------------------------
# API — Operations (upcoming events)
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/upcoming")
@auth.require_read_operations
def api_upcoming():
    """
    List upcoming submission slots within a configurable time window.
    
    Query parameters:
        hours (float): Number of hours to include, limited to 1–48 and defaulting to 4.
        all (str): Set to ``"1"`` to include submissions without resources or comments.
        at (str): ISO-formatted reference time in the event timezone for testing.
        mine (str): Set to ``"1"`` to include only slots assigned to the current user.
    
    Returns:
        JSON response containing matching slots, the effective time window, reference
        time, and whether test mode is active. Returns HTTP 503 if the Pretalx cache
        is unavailable.
    """
    from datetime import datetime, timedelta

    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    try:
        hours = float(request.args.get("hours") or 4)
        hours = max(1, min(hours, 48))
    except ValueError:
        hours = 4

    include_all = request.args.get("all") == "1"

    # Event local timezone (used to interpret naive ?at= values)
    event_tz = EVENT_TZ

    # ?at= override: lets you test against a specific point in time.
    # The browser datetime-local input always sends a naive string (no offset),
    # which represents a wall-clock time in the event's local timezone.
    # Attach event_tz so the comparison is done against the correct instant.
    at_str = (request.args.get("at") or "").strip()
    if at_str:
        try:
            now = datetime.fromisoformat(at_str)
            if now.tzinfo is None:
                now = now.replace(tzinfo=event_tz)
            logger.info("Upcoming: using test reference time %s", now.isoformat())
        except ValueError:
            logger.warning("Upcoming: invalid ?at= value %r, using real now", at_str)
            now = datetime.now(tz=event_tz)
    else:
        # Real mode: use current wall-clock time in event timezone so that
        # the displayed reference time is human-readable and consistent with
        # the slot timestamps from Pretalx (which carry the event's offset).
        now = datetime.now(tz=event_tz)

    deadline = now + timedelta(hours=hours)

    codes_with_data = db.get_codes_with_assignments() if not include_all else None
    conflict_codes  = _get_conflict_codes(cache)

    result = []
    for slot in cache["slots_flat"]:
        code  = slot["submission_code"]
        start = slot.get("start", "")
        if not start:
            continue

        # Parse slot start time
        try:
            slot_start = datetime.fromisoformat(start)
            if slot_start.tzinfo is None:
                slot_start = slot_start.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if not (now <= slot_start <= deadline):
            continue

        if codes_with_data is not None and code not in codes_with_data:
            continue

        sub  = cache["submissions_map"].get(code)
        if not sub:
            continue

        assignments = db.get_submission_assignments(code)

        result.append({
            "code":            code,
            "title":           sub["title"],
            "track":           sub["track"],
            "submission_type": sub["submission_type"],
            "speakers":        sub["speakers"],
            "slot_index":      slot.get("slot_index", 0),
            "start":           slot.get("start", ""),
            "end":             slot.get("end", ""),
            "room_name":       slot.get("room_name", ""),
            "resources":       assignments["resources"],
            "comments":        assignments["comments"],
            "has_conflict":    code in conflict_codes,
        })

    # Enrich with operation_events state (bulk query)
    codes_in_result = list({s["code"] for s in result})
    op_events = db.get_operation_events_for_codes(codes_in_result)
    for s in result:
        ev = op_events.get((s["code"], s["slot_index"]))
        s["assigned_to"]  = ev["assigned_to"]  if ev else None
        s["is_completed"] = bool(ev["is_completed"]) if ev else False

    # ?mine=1 — filter to slots assigned to the current user
    mine = request.args.get("mine") == "1"
    if mine:
        user_email = g.user.get("email", "") if g.user else ""
        result = [s for s in result if s.get("assigned_to") == user_email]

    result.sort(key=lambda x: x["start"])
    return jsonify({
        "slots":          result,
        "hours":          hours,
        "reference_time": now.isoformat(),
        "is_test_mode":   bool(at_str),
    })


# ---------------------------------------------------------------------------
# API — Operation event actions (take / complete / unassign)
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/slots/<code>/<int:slot_index>/take", methods=["POST"])
@auth.require_write_operations
def api_slot_take(code, slot_index):
    """
    Assign an operation slot to the current user.
    
    Parameters:
        code (str): Submission code associated with the operation slot.
        slot_index (int): Index of the slot to assign.
    
    Returns:
        Response: JSON response containing the assignment status, assigned user email, and incomplete state.
    """
    db.take_operation_event(code, slot_index, g.user.get("email"))
    return jsonify({"ok": True, "assigned_to": g.user.get("email"), "is_completed": False})


@app.route(f"{BASE_PATH}/api/slots/<code>/<int:slot_index>/complete", methods=["POST"])
@auth.require_write_operations
def api_slot_complete(code, slot_index):
    """
    Mark an operation slot as completed.
    
    Returns:
    	dict: A JSON response indicating success, the assignee's email, and the completed status.
    """
    db.complete_operation_event(code, slot_index, g.user.get("email"))
    ev = db.get_operation_event(code, slot_index)
    return jsonify({"ok": True, "assigned_to": ev["assigned_to"] if ev else None, "is_completed": True})


@app.route(f"{BASE_PATH}/api/slots/<code>/<int:slot_index>/unassign", methods=["POST"])
@auth.require_write_operations
def api_slot_unassign(code, slot_index):
    """Remove the assignee and reset completion for this slot."""
    db.unassign_operation_event(code, slot_index, g.user.get("email"))
    return jsonify({"ok": True, "assigned_to": None, "is_completed": False})


# ---------------------------------------------------------------------------
# API — Occupancy feed + rating
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/occupancy")
@auth.require_read_operations
def api_occupancy():
    """
    Return currently running or upcoming submissions with their occupancy ratings.
    
    Query parameters:
        at (str): Optional ISO 8601 reference time for test mode.
        rooms (str): Optional comma-separated list of room names to include.
        show_rated (str): Set to ``"1"`` to include slots that already have ratings.
    
    Returns:
        JSON response containing matching slots, occupancy rating options, available
        room names, and the reference time. Returns HTTP 503 if the Pretalx cache
        is unavailable.
    """
    from datetime import datetime, timedelta

    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    event_tz = EVENT_TZ

    # ?at= override for test mode
    at_str = (request.args.get("at") or "").strip()
    if at_str:
        try:
            now = datetime.fromisoformat(at_str)
            if now.tzinfo is None:
                now = now.replace(tzinfo=event_tz)
        except ValueError:
            now = datetime.now(tz=event_tz)
    else:
        now = datetime.now(tz=event_tz)

    # Window: currently running OR starting within the next 1 hour
    window_end = now + timedelta(hours=1)

    # Room filter
    rooms_raw = (request.args.get("rooms") or "").strip()
    room_filter = {r.strip() for r in rooms_raw.split(",") if r.strip()} if rooms_raw else None

    show_rated = request.args.get("show_rated") == "1"

    result = []
    for slot in cache["slots_flat"]:
        code  = slot["submission_code"]
        start_raw = slot.get("start", "")
        end_raw   = slot.get("end", "")
        if not start_raw:
            continue

        try:
            slot_start = datetime.fromisoformat(start_raw)
            if slot_start.tzinfo is None:
                slot_start = slot_start.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        try:
            slot_end = datetime.fromisoformat(end_raw) if end_raw else slot_start
            if slot_end.tzinfo is None:
                slot_end = slot_end.replace(tzinfo=timezone.utc)
        except ValueError:
            slot_end = slot_start

        # Include: currently running (started ≤ now ≤ ended) OR starting ≤ window_end
        is_running = slot_start <= now <= slot_end
        starting_soon = now <= slot_start <= window_end
        if not (is_running or starting_soon):
            continue

        # Room filter
        room_name = slot.get("room_name", "")
        if room_filter and room_name not in room_filter:
            continue

        sub = cache["submissions_map"].get(code)
        if not sub:
            continue

        result.append({
            "code":            code,
            "title":           sub["title"],
            "track":           sub["track"],
            "submission_type": sub["submission_type"],
            "speakers":        sub["speakers"],
            "slot_index":      slot.get("slot_index", 0),
            "start":           start_raw,
            "end":             end_raw,
            "room_name":       room_name,
            "is_running":      is_running,
        })

    # Enrich with occupancy ratings (bulk query)
    codes_in_result = list({s["code"] for s in result})
    occupancy_map = db.get_occupancy_for_codes(codes_in_result)
    for s in result:
        occ = occupancy_map.get((s["code"], s["slot_index"]))
        s["rating"]     = occ["rating"]     if occ else None
        s["rated_by"]   = occ["rated_by"]   if occ else None
        s["rated_at"]   = occ["updated_at"] if occ else None

    # Filter out already-rated unless show_rated=1
    if not show_rated:
        result = [s for s in result if s["rating"] is None]

    # Collect all unique room names from ALL current+soon slots (for filter dropdown)
    all_rooms = sorted({
        sl.get("room_name", "") for sl in cache["slots_flat"]
        if sl.get("room_name")
    })

    result.sort(key=lambda x: (x["room_name"], x["start"]))
    return jsonify({
        "slots":          result,
        "reference_time": now.isoformat(),
        "is_test_mode":   bool(at_str),
        "all_rooms":      all_rooms,
        "ratings":        db.OCCUPANCY_RATINGS,
    })


@app.route(f"{BASE_PATH}/api/slots/<code>/<int:slot_index>/rate", methods=["POST"])
@auth.require_write_operations
def api_slot_rate(code, slot_index):
    """
    Set or update the occupancy rating for a scheduled slot.
    
    Parameters:
        code (str): The submission code associated with the slot.
        slot_index (int): The slot's index within the submission.
    
    Returns:
        A JSON response containing the saved rating, or an error response when the rating is invalid.
    """
    data   = request.get_json(force=True) or {}
    rating = (data.get("rating") or "").strip()
    if rating not in db.OCCUPANCY_RATINGS:
        return jsonify({"error": f"rating must be one of {db.OCCUPANCY_RATINGS}"}), 400

    db.upsert_occupancy(code, slot_index, rating, user_email=g.user.get("email"))
    return jsonify({"ok": True, "rating": rating})



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_conflict_codes(cache):
    """Return a set of submission codes that are currently in conflict."""
    if cache is None:
        return set()
    assignments = db.get_all_resource_assignments_for_conflict()
    conflicts   = pretalx_cache.find_conflicts(cache, assignments)
    codes = set()
    for c in conflicts:
        codes.update(c.get("conflicting_codes", []))
    return codes


def _build_output_rows(cache, by_code, conflict_codes):
    """
    Expand assigned submissions into one row per schedule slot and sort the rows chronologically.
    
    Parameters:
    	cache (dict): Cached submission data.
    	by_code (dict): Submission assignments keyed by submission code.
    	conflict_codes (set): Submission codes with scheduling conflicts.
    
    Returns:
    	list: Slot-level rows containing submission, schedule, assignment, comment, and conflict details.
    """
    from datetime import datetime

    sub_map = cache.get("submissions_map", {})
    rows    = []

    for code, data in by_code.items():
        sub = sub_map.get(code)
        if not sub:
            continue

        for slot in sub["slots"]:
            start_raw = slot.get("start", "")
            end_raw   = slot.get("end", "")
            date_str  = start_raw[:10] if start_raw else ""

            # Format human-readable times (strip TZ, keep HH:MM)
            start_time = start_raw[11:16] if len(start_raw) > 15 else start_raw
            end_time   = end_raw[11:16]   if len(end_raw) > 15   else end_raw

            # Day label
            try:
                dt        = datetime.fromisoformat(start_raw)
                day_label = dt.strftime("%A, %B %d")
            except Exception:
                day_label = date_str

            rows.append({
                "code":            code,
                "title":           sub["title"],
                "track":           sub.get("track"),
                "track_name":      (sub.get("track") or {}).get("name", ""),
                "submission_type": sub["submission_type"],
                "speakers":        sub["speakers"],
                "slot_index":      slot["slot_index"],
                "date":            date_str,
                "day_label":       day_label,
                "start":           start_raw,
                "start_time":      start_time,
                "end_time":        end_time,
                "room_name":       slot.get("room_name", ""),
                "resources":       data.get("resources", []),
                "comments":        data.get("comments", []),
                "has_conflict":    code in conflict_codes,
            })

    rows.sort(key=lambda r: (r["date"], r["start"]))
    return rows


# ---------------------------------------------------------------------------
# API — Delays
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/delays")
@auth.require_read_announcements
def api_delays():
    """
    List currently running or upcoming schedule slots with their active delay details.
    
    Query parameters:
        hours: Lookahead window in hours, clamped to 1-24; defaults to 4.
        at: Optional ISO-formatted reference time for test mode.
    
    Returns:
        A JSON response containing matching slots, their delay details, reference time,
        and whether test mode is enabled.
    """
    from datetime import datetime, timedelta

    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    event_tz = EVENT_TZ

    at_str = (request.args.get("at") or "").strip()
    if at_str:
        try:
            now = datetime.fromisoformat(at_str)
            if now.tzinfo is None:
                now = now.replace(tzinfo=event_tz)
        except ValueError:
            now = datetime.now(tz=event_tz)
    else:
        now = datetime.now(tz=event_tz)

    try:
        hours = max(1, min(24, int(request.args.get("hours", 4))))
    except (ValueError, TypeError):
        hours = 4
    window_end = now + timedelta(hours=hours)

    result = []
    for slot in cache["slots_flat"]:
        code      = slot["submission_code"]
        start_raw = slot.get("start", "")
        end_raw   = slot.get("end", "")
        if not start_raw:
            continue

        try:
            slot_start = datetime.fromisoformat(start_raw)
            if slot_start.tzinfo is None:
                slot_start = slot_start.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        try:
            slot_end = datetime.fromisoformat(end_raw) if end_raw else slot_start
            if slot_end.tzinfo is None:
                slot_end = slot_end.replace(tzinfo=timezone.utc)
        except ValueError:
            slot_end = slot_start

        is_running   = slot_start <= now <= slot_end
        starting_soon = now <= slot_start <= window_end
        if not (is_running or starting_soon):
            continue

        sub = cache["submissions_map"].get(code)
        if not sub:
            continue

        result.append({
            "code":            code,
            "title":           sub["title"],
            "track":           sub["track"],
            "submission_type": sub["submission_type"],
            "speakers":        sub["speakers"],
            "slot_index":      slot.get("slot_index", 0),
            "start":           start_raw,
            "end":             end_raw,
            "room_name":       slot.get("room_name", ""),
            "is_running":      is_running,
        })

    # Enrich with delay data (bulk query)
    codes_in_result = list({s["code"] for s in result})
    delay_map = db.get_delays_for_codes(codes_in_result)
    for s in result:
        d = delay_map.get((s["code"], s["slot_index"]))
        s["delay_minutes"] = d["delay_minutes"] if d else None
        s["delay_comment"] = d["comment"]       if d else None
        s["delay_set_by"]  = d["set_by"]        if d else None
        s["delay_set_at"]  = d["updated_at"]    if d else None

    result.sort(key=lambda x: (x["start"], x["room_name"]))
    return jsonify({
        "slots":          result,
        "reference_time": now.isoformat(),
        "is_test_mode":   bool(at_str),
    })


@app.route(
    f"{BASE_PATH}/api/slots/<code>/<int:slot_index>/delay",
    methods=["POST"],
)
@auth.require_write_announcements
def api_slot_set_delay(code, slot_index):
    """
    Set or update the delay for a submission slot and dispatch a delay announcement.
    
    Parameters:
        code: Submission code identifying the slot.
        slot_index: Zero-based index of the slot within the submission.
    
    Returns:
        A JSON response containing the delay duration, comment, and announcement result.
    """
    data = request.get_json(force=True) or {}
    try:
        minutes = int(data.get("minutes", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "minutes must be an integer"}), 400
    if minutes < 1 or minutes > 1440:
        return jsonify({"error": "minutes must be between 1 and 1440"}), 400

    comment = (data.get("comment") or "").strip() or None
    if comment and len(comment) > 500:
        return jsonify({"error": "comment must be 500 characters or fewer"}), 400
    db.upsert_delay(code, slot_index, minutes, comment,
                    user_email=g.user.get("email"))

    # Dispatch announcement — enrich with slot data from cache
    event_tz = EVENT_TZ

    cache = pretalx_cache.get_cache()
    slot_info = {}
    if cache:
        sub = cache.get("submissions_map", {}).get(code, {})
        slot_info["title"] = sub.get("title", code)
        for sl in cache.get("slots_flat", []):
            if sl.get("submission_code") == code and sl.get("slot_index", 0) == slot_index:
                slot_info["start"] = sl.get("start")
                slot_info["end"]   = sl.get("end")
                slot_info["room"]  = sl.get("room_name")
                break
    else:
        slot_info["title"] = code

    dispatch_result = announcements.dispatch_delay(
        title=slot_info.get("title", code),
        minutes=minutes,
        comment=comment,
        start=slot_info.get("start"),
        end=slot_info.get("end"),
        room=slot_info.get("room"),
        tz=event_tz,
        reference=f"{code}-{slot_index}",
    )

    return jsonify({
        "ok": True,
        "delay_minutes": minutes,
        "comment": comment,
        "announce": dispatch_result.to_dict(),
    })


@app.route(
    f"{BASE_PATH}/api/slots/<code>/<int:slot_index>/delay",
    methods=["DELETE"],
)
@auth.require_write_announcements
def api_slot_clear_delay(code, slot_index):
    """Remove a delay record for a slot."""
    db.clear_delay(code, slot_index, user_email=g.user.get("email"))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Schedule Changes
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/changes")
@auth.require_read_announcements
def api_changes():
    """
    List pending schedule changes enriched with cached submission details.
    
    Returns:
        A JSON response containing the pending changes and their submission titles,
        tracks, and speakers.
    """
    rows = db.get_pending_changes()

    cache = pretalx_cache.get_cache()
    sub_map = (cache or {}).get("submissions_map", {})

    result = []
    for r in rows:
        sub = sub_map.get(r["submission_code"]) or {}
        r["title"]   = sub.get("title", r["submission_code"])
        r["track"]   = sub.get("track")
        r["speakers"] = sub.get("speakers", [])
        result.append(r)

    return jsonify({"changes": result})


@app.route(f"{BASE_PATH}/api/changes/<int:change_id>/send", methods=["POST"])
@auth.require_write_announcements
def api_change_send(change_id):
    """
    Mark a pending schedule change as sent and dispatch its announcement.
    
    Parameters:
        change_id: Identifier of the schedule change.
    
    Returns:
        A JSON response containing the sent status and announcement dispatch result.
    """
    # Fetch the change row first so we can format the announcement
    change = db.get_change_by_id(change_id)
    if change is None or change.get("status") != "pending":
        return jsonify({"error": "Change not found or already actioned"}), 404

    ok = db.action_change(change_id, "sent", user_email=g.user.get("email"))
    if not ok:
        return jsonify({"error": "Change not found or already actioned"}), 404

    # Enrich with submission title from cache
    cache = pretalx_cache.get_cache()
    sub = (cache or {}).get("submissions_map", {}).get(change["submission_code"], {})
    title = sub.get("title", change["submission_code"])

    event_tz = EVENT_TZ

    dispatch_result = announcements.dispatch_change(
        title=title,
        change_types=change["change_types"],
        old_start=change.get("old_start"),
        old_end=change.get("old_end"),
        old_room=change.get("old_room"),
        new_start=change.get("new_start"),
        new_end=change.get("new_end"),
        new_room=change.get("new_room"),
        tz=event_tz,
        reference=f"{change['submission_code']}-{change['slot_index']}",
    )

    return jsonify({
        "ok": True,
        "status": "sent",
        "announce": dispatch_result.to_dict(),
    })


@app.route(f"{BASE_PATH}/api/changes/<int:change_id>/discard", methods=["POST"])
@auth.require_write_announcements
def api_change_discard(change_id):
    """Discard a pending change (suppress it from the UI)."""
    ok = db.action_change(change_id, "discarded", user_email=g.user.get("email"))
    if not ok:
        return jsonify({"error": "Change not found or already actioned"}), 404
    return jsonify({"ok": True, "status": "discarded"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting Operations server on 0.0.0.0:8090 with base path '%s'", BASE_PATH)
    app.run(host="0.0.0.0", port=8090, debug=False)
