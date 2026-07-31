#!/usr/bin/env python3
"""
Pretalx Schedule Export Utility
Exports schedule slot data to CSV with optional filters and group-by support.

Output fields: name, time_start, time_end, runtime, speaker, room
Sorted by day and then time_start within each file.

Usage examples:
  # Export all slots to output/slots.csv
  python export_slots.py --schedule wip

  # Export only slots in the "Main Hall" room
  python export_slots.py --schedule wip --room "Main Hall"

  # Export slots for multiple speakers
  python export_slots.py --schedule wip --speaker "Alice" --speaker "Bob"

  # Export slots filtered by track, grouped into one file per room
  python export_slots.py --schedule wip --track "Art" --group-by room

  # Export a room-usage overview (earliest start / latest end per room per day)
  python export_slots.py --schedule wip --room-usage
"""

import sys
import os
import csv
import argparse
import re
from datetime import datetime

from pretalx_client import PretalxClient, PretalxAPIError

# ---------------------------------------------------------------------------
# ANSI colour constants (consistent with the rest of the project)
# ---------------------------------------------------------------------------
C_HEADER = "\033[95m"
C_BLUE   = "\033[94m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"

OUTPUT_DIR = "output"

# ---------------------------------------------------------------------------
# Room group mappings – extend or move to a config file as needed
# ---------------------------------------------------------------------------
ROOM_GROUPS = {
    "panelrooms": [
        "CCH Hall 4",
        "CCH X 5-8",
        "CCH X 9-11",
        "CCH X 1-2",
        "CCH X 3-4",
        "CCH Y 7-8",
        "CCH Y 9-10",
        "CCH X 12",
        "CCH Y 4"
    ],
    "stages": [
        "Theater Stage – CCH Hall 3",
        "Arena Stage – CCH Hall H Section 1-2",
        "Auditorium – CCH Hall Z",
    ],
}

# ---------------------------------------------------------------------------
# Shared helpers (mirroring schedule.py conventions)
# ---------------------------------------------------------------------------

def format_localized(val):
    """Return the English string from a localized dict, or the value itself."""
    if isinstance(val, dict):
        return val.get("en") or next(iter(val.values()), "") if val else ""
    return str(val) if val is not None else ""


def parse_slot_datetime(iso_str):
    """Parse an ISO 8601 datetime string; return a datetime or None."""
    if not iso_str:
        return None
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def safe_filename(name):
    """Sanitize a string so it can be used as a file-system name component."""
    name = re.sub(r"[^\w\s\-]", "", name, flags=re.UNICODE)
    name = re.sub(r"[\s]+", "_", name.strip())
    return name or "unnamed"


# ---------------------------------------------------------------------------
# Slot data extraction
# ---------------------------------------------------------------------------

def _get_track_name(sub_data):
    """Return the track name string for a submission dict."""
    track = sub_data.get("track")
    if isinstance(track, dict):
        return format_localized(track.get("name", ""))
    return str(track) if track else ""


def _get_tag_names(sub_data, tag_map):
    """
    Return a list of tag name strings for a submission dict.

    Because of a pretalx bug that causes a 500 error when expanding tags
    inline, tags are NOT expanded on the slot endpoint.  Instead the caller
    pre-fetches all tags and passes a {tag_id: tag_name} lookup dict.
    The submission's `tags` field therefore contains raw integer IDs.
    """
    tags = sub_data.get("tags", [])
    result = []
    for tag in tags:
        if isinstance(tag, dict):
            # Defensive: handle partially-expanded objects if the bug is ever fixed
            raw = tag.get("tag") or tag.get("name")
            name = format_localized(raw) if isinstance(raw, dict) else str(raw or "")
            if not name and tag.get("id") is not None:
                name = tag_map.get(tag["id"], str(tag["id"]))
            result.append(name)
        else:
            # Raw ID — look up in the pre-fetched map
            tag_id = tag
            result.append(tag_map.get(tag_id, str(tag_id)))
    return [t for t in result if t]


def extract_slot_row(slot, tag_map):
    """
    Convert a fully-expanded slot dict into a flat row dict for CSV output.

    Returns None for slots without a start time.

    tag_map: pre-fetched {tag_id: tag_name} dict (workaround for pretalx
             bug that 500s when slots.submission.tags is in the expand list).
    """
    start_str = slot.get("start")
    end_str   = slot.get("end")

    if not start_str:
        return None  # skip unscheduled slots

    dt_start = parse_slot_datetime(start_str)
    dt_end   = parse_slot_datetime(end_str)

    day_str = dt_start.strftime("%Y-%m-%d") if dt_start else ""
    start_time_str = dt_start.strftime("%H:%M") if dt_start else start_str
    end_time_str = dt_end.strftime("%H:%M") if dt_end else (end_str or "")

    sub_data = slot.get("submission")
    if isinstance(sub_data, dict):
        name = sub_data.get("title") or ""
        code = sub_data.get("code") or ""

        # Speakers: may be a list of dicts or codes
        speakers = sub_data.get("speakers", [])
        speaker_names = []
        for sp in speakers:
            if isinstance(sp, dict):
                speaker_names.append(sp.get("name") or sp.get("code") or "")
            else:
                speaker_names.append(str(sp))
        valid_speaker_names = list(filter(None, speaker_names))
        if valid_speaker_names:
            speaker_str = valid_speaker_names[0]
            if len(valid_speaker_names) > 1:
                speaker_str += f" (+ {len(valid_speaker_names) - 1})"
        else:
            speaker_str = ""

        track_name = _get_track_name(sub_data)
        tag_names = _get_tag_names(sub_data, tag_map)
    else:
        # Blocker slot
        name = format_localized(slot.get("description")) or "Blocker"
        code = "BLOCKER"
        speaker_str = ""
        valid_speaker_names = []
        track_name = ""
        tag_names = []

    if len(name) > 30:
        name = name[:30] + "..."

    # Room
    room_data = slot.get("room")
    if isinstance(room_data, dict):
        room_name     = format_localized(room_data.get("name")) or str(room_data.get("id", ""))
        room_capacity = room_data.get("capacity")  # may be int or None
    else:
        room_name     = str(room_data) if room_data else ""
        room_capacity = None

    # Runtime in minutes
    runtime = slot.get("duration")
    if runtime is None and dt_start and dt_end:
        runtime = int((dt_end - dt_start).total_seconds() // 60)

    return {
        "code":       code,
        "name":       name,
        "day":        day_str,
        "time_start": start_time_str,
        "time_end":   end_time_str,
        "runtime":    str(runtime) if runtime is not None else "",
        "speaker":    speaker_str,
        "room":       room_name,
        # Internal helpers for filtering / grouping (not written to CSV)
        "_speakers":       valid_speaker_names,
        "_track":          track_name,
        "_tags":           tag_names,
        "_sort_key":       start_str,   # ISO string sorts lexicographically
        "_end_key":        end_str,     # ISO end string for accurate end-time comparisons
        "_room_capacity":  room_capacity,
    }


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def normalize_filter_values(values):
    """Lower-case and strip a list of filter strings for case-insensitive matching."""
    return [v.strip().lower() for v in (values or [])]


def row_matches_filters(row, rooms, speakers, tracks, tags):
    """
    Return True if the row satisfies ALL active filters.
    Each filter list uses OR logic (any value matches → passes that filter).
    """
    if rooms:
        if row["room"].strip().lower() not in rooms:
            return False
    if speakers:
        row_speakers_lower = [s.strip().lower() for s in row.get("_speakers", [])]
        if not any(sp in row_speakers_lower for sp in speakers):
            return False
    if tracks:
        if row["_track"].strip().lower() not in tracks:
            return False
    if tags:
        row_tags_lower = [t.strip().lower() for t in row["_tags"]]
        if not any(tag in row_tags_lower for tag in tags):
            return False
    return True


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------

CSV_FIELDS = ["code", "name", "day", "time_start", "time_end", "runtime", "speaker", "room"]

ROOM_USAGE_FIELDS_BASE = ["Day", "Room Group", "Room", "Earliest Slot Start", "Latest Slot End"]


def write_csv(rows, filepath):
    """Write a list of row dicts to a CSV file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_room_usage_csv(usage_rows, filepath, fieldnames):
    """Write room-usage summary rows to a CSV file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(usage_rows)
    return len(usage_rows)


def build_room_usage_rows(rows, include_capacity=False):
    """
    Build a list of room-usage summary dicts from extracted slot rows.

    For every room defined in ROOM_GROUPS, compute – per calendar day –
    the earliest slot start time and the latest slot end time.
    Rooms with no scheduled slots on a given day are omitted.

    include_capacity: if True, a 'Capacity' key is added to each result row.

    Returns a list of dicts sorted by Day then Earliest Slot Start.
    """
    # Build an inverse map: room_name_lower -> group_name
    room_to_group = {}
    for group_name, room_list in ROOM_GROUPS.items():
        for room in room_list:
            room_to_group[room.strip().lower()] = (group_name, room)

    # Accumulate (earliest_start, latest_end, capacity) keyed by (day, group, canonical_room)
    usage = {}  # key -> {"earliest": datetime, "latest": datetime, "capacity": int|None}

    for row in rows:
        room_lower = row["room"].strip().lower()
        if room_lower not in room_to_group:
            continue  # ignore rooms not in any group

        group_name, canonical_room = room_to_group[room_lower]
        day = row["day"]

        # Parse start/end directly from the stored ISO strings
        dt_start = parse_slot_datetime(row.get("_sort_key") or "")
        dt_end   = parse_slot_datetime(row.get("_end_key") or "")

        if dt_start is None:
            continue

        capacity = row.get("_room_capacity")  # int or None

        key = (day, group_name, canonical_room)
        if key not in usage:
            usage[key] = {"earliest": dt_start, "latest": dt_end, "capacity": capacity}
        else:
            if dt_start < usage[key]["earliest"]:
                usage[key]["earliest"] = dt_start
            if dt_end is not None and (
                usage[key]["latest"] is None or dt_end > usage[key]["latest"]
            ):
                usage[key]["latest"] = dt_end
            # Keep whichever capacity value is not None (should be stable per room)
            if usage[key]["capacity"] is None and capacity is not None:
                usage[key]["capacity"] = capacity

    # Convert to output rows and sort by day then earliest start
    result = []
    for (day, group_name, canonical_room), times in usage.items():
        earliest = times["earliest"]
        latest   = times["latest"]
        row_out = {
            "Day":                 day,
            "Room Group":          group_name,
            "Room":                canonical_room,
            "Earliest Slot Start": earliest.strftime("%H:%M") if earliest else "",
            "Latest Slot End":     latest.strftime("%H:%M") if latest else "",
            # Internal sort key
            "_sort": (day, earliest or datetime.min),
        }
        if include_capacity:
            cap = times["capacity"]
            row_out["Capacity"] = str(cap) if cap is not None else ""
        result.append(row_out)

    result.sort(key=lambda r: r["_sort"])
    # Remove internal sort key before returning
    for r in result:
        del r["_sort"]
    return result


def sort_rows(rows):
    """Sort rows by time_start (ISO string lexicographic order = chronological)."""
    return sorted(rows, key=lambda r: r.get("_sort_key") or "")


# ---------------------------------------------------------------------------
# Group-by helpers
# ---------------------------------------------------------------------------

def group_keys_for_row(row, group_by):
    """
    Return a list of grouping keys for a row given the group-by dimension.
    A row with multiple speakers/tags can appear in multiple output files.
    """
    if group_by == "room":
        return [row["room"] or "No Room"]
    if group_by == "speaker":
        names = [s.strip() for s in row.get("_speakers", []) if s.strip()]
        return names if names else ["No Speaker"]
    if group_by == "track":
        return [row["_track"] or "No Track"]
    if group_by == "tag":
        tags = [t.strip() for t in row["_tags"] if t.strip()]
        return tags if tags else ["No Tag"]
    return ["all"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export Pretalx schedule slots to CSV with optional filters and group-by."
    )

    # Event / schedule selection
    parser.add_argument(
        "--event",
        help="Event slug. If omitted, auto-detects when only one event is available."
    )
    parser.add_argument(
        "--schedule", "-s",
        default="wip",
        help="Schedule version to export ('wip', 'latest', or a version name). Default: wip"
    )

    # Filters (each may be repeated for multiple values)
    parser.add_argument("--room",    action="append", metavar="ROOM",
                        help="Filter by room name (case-insensitive) or room group (e.g., 'panelrooms', 'stages'). Repeatable.")
    parser.add_argument("--speaker", action="append", metavar="SPEAKER",
                        help="Filter by speaker name (case-insensitive). Repeatable.")
    parser.add_argument("--track",   action="append", metavar="TRACK",
                        help="Filter by track name (case-insensitive). Repeatable.")
    parser.add_argument("--tag",     action="append", metavar="TAG",
                        help="Filter by tag name (case-insensitive). Repeatable.")

    # Group-by
    parser.add_argument(
        "--group-by",
        choices=["room", "speaker", "track", "tag"],
        metavar="DIMENSION",
        help="Group output into one file per distinct value of DIMENSION "
             "(room | speaker | track | tag)."
    )

    # Room-usage overview
    parser.add_argument(
        "--room-usage",
        action="store_true",
        help="Export a room-usage overview: earliest slot start and latest slot end "
             "per room (from ROOM_GROUPS) per day. Output: output/room_usage.csv"
    )
    parser.add_argument(
        "--room-capacity",
        action="store_true",
        help="(Used with --room-usage) Include a Capacity column in the room-usage CSV."
    )

    args = parser.parse_args()

    # --- Client init ---
    try:
        client = PretalxClient()
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Initialization Error:{C_RESET} {e}")
        print("Make sure PRETALX_URL and PRETALX_APIKEY are set in .env or environment.")
        sys.exit(1)

    # --- Resolve event ---
    event_slug = args.event
    if not event_slug:
        try:
            events = list(client.list_events())
            if not events:
                print(f"{C_RED}No events found on this Pretalx instance.{C_RESET}")
                sys.exit(1)
            elif len(events) == 1:
                event_slug = events[0].get("slug")
            else:
                print(f"{C_YELLOW}Multiple events found. Please specify one with --event:{C_RESET}")
                for ev in events:
                    slug = ev.get("slug")
                    name = format_localized(ev.get("name", {}))
                    print(f"  - {C_BOLD}{slug}{C_RESET} ({name})")
                sys.exit(1)
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to query events: {e}{C_RESET}")
            sys.exit(1)

    # --- Resolve schedule ---
    schedule_input = args.schedule.strip()
    schedule_id = None
    if schedule_input.lower() in ("wip", "latest"):
        schedule_id = schedule_input.lower()
    else:
        try:
            schedules = list(client.list_schedules(event_slug))
            for sched in schedules:
                if sched.get("version") == schedule_input or str(sched.get("id")) == schedule_input:
                    schedule_id = sched.get("id")
                    break
            if schedule_id is None:
                try:
                    schedule_id = int(schedule_input)
                except ValueError:
                    pass
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to query schedules: {e}{C_RESET}")
            sys.exit(1)

    if schedule_id is None:
        print(f"{C_RED}Schedule '{schedule_input}' not found.{C_RESET}")
        sys.exit(1)

    # --- Fetch schedule with expanded slots ---
    print(f"{C_BLUE}Fetching schedule '{schedule_input}' for event '{event_slug}'…{C_RESET}")
    # Fetch all tags upfront to work around a pretalx bug: including
    # 'slots.submission.tags' in the expand list causes a 500 error.
    # We instead resolve tag names manually using raw tag IDs.
    print(f"{C_BLUE}Fetching tag list for event '{event_slug}'…{C_RESET}")
    try:
        all_tags = list(client.list_tags(event_slug))
        # Build {id: name} lookup; tag objects have a 'tag' field (the name string)
        tag_map = {}
        for t in all_tags:
            tid  = t.get("id")
            name = t.get("tag") or format_localized(t.get("name", ""))
            if tid is not None:
                tag_map[tid] = name
        print(f"{C_CYAN}  {len(tag_map)} tags loaded.{C_RESET}")
    except PretalxAPIError as e:
        print(f"{C_YELLOW}Warning: Could not fetch tags ({e}). Tag filters/grouping will use raw IDs.{C_RESET}")
        tag_map = {}

    try:
        schedule_detail = client.get_schedule(
            event_slug,
            schedule_id,
            expand=[
                "slots",
                "slots.room",
                "slots.submission",
                "slots.submission.speakers",
                "slots.submission.track",
                # NOTE: 'slots.submission.tags' intentionally omitted — pretalx
                # bug causes a 500 error when this expand key is included.
                # Tags are resolved via the separately-fetched tag_map instead.
            ]
        )
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to fetch schedule: {e}{C_RESET}")
        sys.exit(1)

    raw_slots = schedule_detail.get("slots", [])
    print(f"{C_CYAN}  {len(raw_slots)} raw slots found.{C_RESET}")

    # --- Extract rows ---
    rows = []
    for slot in raw_slots:
        row = extract_slot_row(slot, tag_map)
        if row is not None:
            rows.append(row)

    # --- Apply filters ---
    f_rooms = []
    for r in (args.room or []):
        r_lower = r.strip().lower()
        if r_lower in ROOM_GROUPS:
            f_rooms.extend([x.strip().lower() for x in ROOM_GROUPS[r_lower]])
        else:
            f_rooms.extend([x.strip().lower() for x in r.split(",") if x.strip()])
    f_speakers = normalize_filter_values(args.speaker)
    f_tracks   = normalize_filter_values(args.track)
    f_tags     = normalize_filter_values(args.tag)

    if any([f_rooms, f_speakers, f_tracks, f_tags]):
        before = len(rows)
        rows = [r for r in rows if row_matches_filters(r, f_rooms, f_speakers, f_tracks, f_tags)]
        print(f"{C_CYAN}  {len(rows)} slots after filtering (was {before}).{C_RESET}")

    if not rows:
        print(f"{C_YELLOW}No slots match the given filters. Nothing to export.{C_RESET}")
        sys.exit(0)

    # --- Room-usage overview (early exit) ---
    if args.room_usage:
        include_capacity = args.room_capacity
        usage_rows = build_room_usage_rows(rows, include_capacity=include_capacity)
        if not usage_rows:
            print(f"{C_YELLOW}No slots found in any configured room group. Nothing to export.{C_RESET}")
            sys.exit(0)
        fieldnames = ROOM_USAGE_FIELDS_BASE + (["Room-Capacity"] if include_capacity else [])
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(OUTPUT_DIR, "room_usage.csv")
        count = write_room_usage_csv(usage_rows, filepath, fieldnames)
        print(f"\n{C_GREEN}{C_BOLD}Done.{C_RESET} {count} rows written to {C_CYAN}{filepath}{C_RESET}.")
        sys.exit(0)

    # --- Ensure output directory ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Write output ---
    group_by = args.group_by

    if group_by:
        # Bucket rows by group value(s); a row can land in multiple buckets
        # (e.g. a slot with two speakers → appears in both speaker files)
        buckets = {}
        for row in rows:
            for key in group_keys_for_row(row, group_by):
                buckets.setdefault(key, []).append(row)

        print(f"\n{C_HEADER}{C_BOLD}Exporting {len(buckets)} file(s) grouped by {group_by}:{C_RESET}")
        total_written = 0
        for group_name in sorted(buckets.keys()):
            group_rows = sort_rows(buckets[group_name])
            filename   = f"{safe_filename(group_name)}.csv"
            filepath   = os.path.join(OUTPUT_DIR, filename)
            count      = write_csv(group_rows, filepath)
            total_written += count
            print(f"  {C_GREEN}✓{C_RESET} {C_BOLD}{filepath}{C_RESET}  ({count} rows)")

        print(f"\n{C_GREEN}{C_BOLD}Done.{C_RESET} {total_written} total rows written across {len(buckets)} file(s).")

    else:
        # Single output file
        rows = sort_rows(rows)
        filepath = os.path.join(OUTPUT_DIR, "slots.csv")
        count = write_csv(rows, filepath)
        print(f"\n{C_GREEN}{C_BOLD}Done.{C_RESET} {count} rows written to {C_CYAN}{filepath}{C_RESET}.")


if __name__ == "__main__":
    main()
