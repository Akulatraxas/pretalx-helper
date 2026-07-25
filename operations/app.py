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

from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, Response, g,
)

import db
import auth
import pretalx_cache
from db import DEPARTMENTS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PRETALX_URL    = os.environ.get("PRETALX_URL", "")
PRETALX_APIKEY = os.environ.get("PRETALX_APIKEY", "")
PRETALX_EVENT  = os.environ.get("PRETALX_EVENT_SLUG", "")
BASE_PATH      = os.environ.get("BASE_PATH", "/ef-operations")

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

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"{BASE_PATH}/static",
)
app.config["BASE_PATH"] = BASE_PATH

# Make BASE_PATH and DEPARTMENTS available in all templates
@app.context_processor
def inject_globals():
    return {
        "base_path":   BASE_PATH,
        "departments": DEPARTMENTS,
        "user":        getattr(g, "user", None),
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
@auth.require_read
def index():
    return redirect(url_for("page_events"))


@app.route(f"{BASE_PATH}/resources")
@auth.require_read
def page_resources():
    return render_template("resources.html", page="resources")


@app.route(f"{BASE_PATH}/events")
@auth.require_read
def page_events():
    return render_template("events.html", page="events")


@app.route(f"{BASE_PATH}/output")
@auth.require_read
def page_output():
    return render_template("output.html", page="output")


@app.route(f"{BASE_PATH}/operations")
@auth.require_read
def page_operations():
    return render_template("operations.html", page="operations")

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

@app.route(f"{BASE_PATH}/api/refresh", methods=["POST"])
@auth.require_write
def api_refresh():
    pretalx_cache.trigger_refresh()
    return jsonify({"status": "refresh started"})


@app.route(f"{BASE_PATH}/api/submissions")
@auth.require_read
def api_submissions():
    """
    List submissions from cache, optionally filtered by ?q=search.
    Also annotates each submission with has_resources / has_comments / has_conflict
    from the DB (expensive-ish but submissions list is typically < 500 entries).
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
@auth.require_read
def api_submission_detail(code):
    """Full detail for one submission: pretalx data + DB assignments."""
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
@auth.require_read
def api_resources_list():
    q = (request.args.get("q") or "").strip().lower()
    resources = db.list_resources()
    if q:
        resources = [r for r in resources if q in r["name"].lower()]
    return jsonify({"resources": resources})


@app.route(f"{BASE_PATH}/api/resources", methods=["POST"])
@auth.require_write
def api_resources_create():
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
@auth.require_write
def api_resources_update(rid):
    data = request.get_json(force=True) or {}
    name   = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    amount = int(data.get("amount") or 0)
    depts  = [d for d in (data.get("departments") or []) if d in DEPARTMENTS]
    db.update_resource(rid, name, amount, depts, user_email=g.user.get("email"))
    return jsonify({"ok": True})


@app.route(f"{BASE_PATH}/api/resources/<int:rid>", methods=["DELETE"])
@auth.require_write
def api_resources_delete(rid):
    db.delete_resource(rid, user_email=g.user.get("email"))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Submission resource assignments
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/submission/<code>/assignments", methods=["GET"])
@auth.require_read
def api_get_assignments(code):
    return jsonify(db.get_submission_assignments(code))


@app.route(f"{BASE_PATH}/api/submission/<code>/resources", methods=["POST"])
@auth.require_write
def api_add_resource(code):
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
@auth.require_write
def api_remove_resource(code, assignment_id):
    db.remove_submission_resource(assignment_id, user_email=g.user.get("email"))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Submission comments
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/submission/<code>/comments", methods=["POST"])
@auth.require_write
def api_add_comment(code):
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
@auth.require_write
def api_remove_comment(code, comment_id):
    db.remove_submission_comment(comment_id, user_email=g.user.get("email"))
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API — Output
# ---------------------------------------------------------------------------

@app.route(f"{BASE_PATH}/api/output")
@auth.require_read
def api_output():
    """
    Returns a list of slot rows suitable for the output table.
    Each row = one slot occurrence of a submission that has data for the dept.
    ?dept=all|Conops|FS-Support|CCH|CODA
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
@auth.require_read
def api_output_csv():
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
@auth.require_read
def api_conflicts():
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
@auth.require_read
def api_upcoming():
    """
    Return submissions whose slots start within the next ?hours=N hours.
    Only submissions that have resources or comments are included by default
    unless ?all=1 is passed.

    For testing before the con, pass ?at=YYYY-MM-DDTHH:MM to override "now".
    Example: ?at=2026-08-19T10:00&hours=4
    """
    from datetime import datetime, timezone, timedelta

    cache = pretalx_cache.get_cache()
    if cache is None:
        return jsonify({"error": "Cache not ready"}), 503

    try:
        hours = float(request.args.get("hours") or 4)
        hours = max(1, min(hours, 48))
    except ValueError:
        hours = 4

    include_all = request.args.get("all") == "1"

    # ?at= override: lets you test against a specific point in time
    at_str = (request.args.get("at") or "").strip()
    if at_str:
        try:
            now = datetime.fromisoformat(at_str)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            logger.info("Upcoming: using test reference time %s", now.isoformat())
        except ValueError:
            logger.warning("Upcoming: invalid ?at= value %r, using real now", at_str)
            now = datetime.now(tz=timezone.utc)
    else:
        now = datetime.now(tz=timezone.utc)

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

    result.sort(key=lambda x: x["start"])
    return jsonify({
        "slots":          result,
        "hours":          hours,
        "reference_time": now.isoformat(),
        "is_test_mode":   bool(at_str),
    })


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
    Expand submission assignments into one row per slot, sorted by start time.
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting Operations server on 0.0.0.0:8090 with base path '%s'", BASE_PATH)
    app.run(host="0.0.0.0", port=8090, debug=False)
