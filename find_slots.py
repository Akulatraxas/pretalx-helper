#!/usr/bin/env python3
"""
Pretalx Empty Slot Finder CLI Utility
Scans the WIP schedule to find gaps in rooms large enough to fit a new slot,
considering buffer time before and after each event.
"""

import sys
import argparse
from datetime import datetime, timedelta
from pretalx_client import PretalxClient, PretalxAPIError

# ANSI Colors for premium terminal output
C_HEADER = "\033[95m"
C_BLUE   = "\033[94m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"
C_DIM    = "\033[2m"

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
    ],
    "stages": [
        "Theater Stage – CCH Hall 3",
        "Arena Stage – CCH Hall H Section 1-2",
        "Auditorium – CCH Hall Z",
    ],
}

# ---------------------------------------------------------------------------
# Slot parameters
# ---------------------------------------------------------------------------
DEFAULT_SLOT_DURATION = 90   # minutes – the actual talk runtime
DEFAULT_BUFFER        = 30   # minutes on each side of the slot
EARLIEST_START_HOUR   = 11   # first allowed begin time (no buffer before this)
LATEST_START_HOUR     = 21   # last allowed begin time for a new slot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_section(title):
    print(f"\n{C_HEADER}{C_BOLD}{'=' * 70}{C_RESET}")
    print(f"{C_BLUE}{C_BOLD}>>> {title}{C_RESET}")
    print(f"{C_HEADER}{C_BOLD}{'=' * 70}{C_RESET}")


def format_localized(val):
    """Return English text from a localized dict, or the raw string."""
    if isinstance(val, dict):
        return val.get("en") or next(iter(val.values()), "") if val else ""
    return str(val) if val is not None else ""


def parse_dt(iso_str):
    """Parse an ISO 8601 datetime string into an aware datetime object."""
    if not iso_str:
        return None
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def fmt_time(dt):
    return dt.strftime("%H:%M") if dt else "?"


def local_naive(dt):
    """Strip timezone info to produce a naive local-ish datetime for display."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_free_slots(slots_by_room, slot_duration, buffer, earliest_hour, latest_hour,
                    all_conference_days=None):
    """
    Given a mapping of room_name -> list of (start, end) datetime tuples,
    return a mapping of room_name -> list of available (window_start, window_end)
    tuples within the allowed time range.

    all_conference_days: a sorted list of date objects covering every conference
    day. When provided, every room is scanned against ALL conference days, so
    rooms that have no events on a given day still produce free windows for that
    day. Without it, only days that already have events in a room are checked.

    Rules:
    - There must be `buffer` minutes of clear time BEFORE the new slot starts.
      No leading buffer is required if the slot starts exactly at earliest_hour
      (the opening of the allowed window).
    - There must be `buffer` minutes of clear time AFTER the new slot ends.
    - The new slot start must be >= earliest_hour and <= latest_hour.
    - The buffer between two adjacent events is shared: 30 min after one slot
      and 30 min before the next slot are the SAME 30 minutes – not 60.
    """
    free_windows = {}

    for room, events in slots_by_room.items():
        windows = []
        sorted_events = sorted(events, key=lambda e: e[0])

        # Use globally known conference days so that days without any events in
        # this room are still scanned (they will be completely free).
        if all_conference_days:
            days = all_conference_days
        else:
            days = sorted({e[0].date() for e in sorted_events})

        for day in days:
            day_events = [e for e in sorted_events if e[0].date() == day]

            day_start  = datetime(day.year, day.month, day.day, earliest_hour, 0, 0)
            day_latest = datetime(day.year, day.month, day.day, latest_hour,   0, 0)

            def candidate_is_free(candidate_start, _day_events=day_events, _day_start=day_start):
                required_clear_start = candidate_start - timedelta(minutes=buffer)
                required_clear_end   = candidate_start + timedelta(minutes=slot_duration + buffer)

                # No leading buffer required before the allowed window opens.
                effective_clear_start = max(required_clear_start, _day_start)

                for ev_start, ev_end in _day_events:
                    # An existing event blocks the candidate if it overlaps with
                    # [effective_clear_start, required_clear_end).  The boundary
                    # is exclusive on both sides so that an event ending exactly
                    # at the buffer boundary (or starting exactly at the trailing
                    # buffer boundary) is NOT considered a conflict – this
                    # correctly models the "one shared buffer between slots" rule.
                    if ev_start < required_clear_end and ev_end > effective_clear_start:
                        return False
                return True

            # Scan every 5 minutes within the allowed window
            step = timedelta(minutes=5)
            candidate = day_start
            in_window = False
            window_open_at = None

            while candidate <= day_latest:
                if candidate_is_free(candidate):
                    if not in_window:
                        in_window = True
                        window_open_at = candidate
                else:
                    if in_window:
                        windows.append((window_open_at, candidate - step))
                        in_window = False
                        window_open_at = None
                candidate += step

            # Close any trailing open window at day_latest
            if in_window:
                windows.append((window_open_at, day_latest))

        if windows:
            free_windows[room] = windows

    return free_windows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Find empty slots in the WIP schedule where a new panel or talk "
            "can fit, respecting buffer times on each side."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Room groups available (use with --rooms):
  stages      : Theater Stage, Arena Stage, Auditorium
  panelrooms  : CCH Hall 4, CCH X 5-8, CCH X 9-11, CCH X 1-2,
                CCH X 3-4, CCH Y 7-8, CCH Y 9-10

Example usage:
  python find_slots.py
  python find_slots.py --rooms panelrooms
  python find_slots.py --rooms stages --length 60
  python find_slots.py --rooms "CCH Hall 4,CCH X 5-8" --event my-event
        """,
    )
    parser.add_argument(
        "--event",
        help="The slug of the event to scan. Defaults to the only available event.",
    )
    parser.add_argument(
        "--schedule", "-s",
        default="wip",
        help="Schedule version to analyse (default: wip).",
    )
    parser.add_argument(
        "--rooms", "-r",
        default=None,
        help=(
            "Filter rooms to search. Accepts a group name ('stages', 'panelrooms'), "
            "or a comma-separated list of exact room names. "
            "Omit to search all rooms."
        ),
    )
    parser.add_argument(
        "--length", "-l",
        type=int,
        default=DEFAULT_SLOT_DURATION,
        metavar="MINUTES",
        help=f"Duration of the slot to fit in minutes (default: {DEFAULT_SLOT_DURATION}).",
    )
    parser.add_argument(
        "--buffer", "-b",
        type=int,
        default=DEFAULT_BUFFER,
        metavar="MINUTES",
        help=f"Buffer time required before and after each slot in minutes (default: {DEFAULT_BUFFER}).",
    )

    args = parser.parse_args()

    print(f"{C_GREEN}{C_BOLD}Pretalx Empty Slot Finder{C_RESET}")
    print("Connecting to Pretalx instance...")

    try:
        client = PretalxClient()
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Initialization Error:{C_RESET} {e}")
        print("Make sure PRETALX_URL and PRETALX_APIKEY are defined in your .env file.")
        sys.exit(1)

    print(f"✓ Connected: {C_BOLD}{client.site_url}{C_RESET}")

    # 1. Resolve event slug
    event_slug = args.event
    if not event_slug:
        try:
            events = list(client.list_events())
            if not events:
                print(f"{C_RED}No events found.{C_RESET}")
                sys.exit(1)
            elif len(events) == 1:
                event_slug = events[0].get("slug")
                print(f"Auto-selected event: {C_BLUE}{C_BOLD}{event_slug}{C_RESET}")
            else:
                print(f"{C_YELLOW}Multiple events found. Please specify one with --event:{C_RESET}")
                for e in events:
                    print(f"  - {C_BOLD}{e.get('slug')}{C_RESET}")
                sys.exit(1)
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to query events: {e}{C_RESET}")
            sys.exit(1)

    # 2. Resolve room filter
    room_filter = None
    if args.rooms:
        group_key = args.rooms.strip().lower()
        if group_key in ROOM_GROUPS:
            room_filter = ROOM_GROUPS[group_key]
            print(f"Room filter: group {C_CYAN}{C_BOLD}{group_key}{C_RESET} "
                  f"({len(room_filter)} rooms)")
        else:
            room_filter = [r.strip() for r in args.rooms.split(",") if r.strip()]
            print(f"Room filter: {C_CYAN}{', '.join(room_filter)}{C_RESET}")
    else:
        print("Room filter: all rooms")

    slot_duration = args.length
    buffer        = args.buffer
    total_block   = slot_duration + 2 * buffer

    print(
        f"Slot params: {C_BOLD}{slot_duration}min{C_RESET} slot + "
        f"{C_BOLD}{buffer}min{C_RESET} buffer each side "
        f"= {C_BOLD}{total_block}min{C_RESET} total block required"
    )
    print(
        f"Search window: {C_BOLD}{EARLIEST_START_HOUR:02d}:00{C_RESET} – "
        f"{C_BOLD}{LATEST_START_HOUR:02d}:00{C_RESET} (latest slot start time)"
    )

    # 3. Fetch schedule
    schedule_id = args.schedule.lower() if args.schedule else "wip"
    print(f"\nFetching schedule '{C_BOLD}{schedule_id}{C_RESET}' for event '{event_slug}'...")

    try:
        schedule_detail = client.get_schedule(
            event_slug,
            schedule_id,
            expand=["slots", "slots.room"],
        )
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to fetch schedule: {e}{C_RESET}")
        sys.exit(1)

    slots = schedule_detail.get("slots", [])
    print(f"✓ Loaded {C_BOLD}{len(slots)}{C_RESET} slots from schedule.")

    # 4. Build per-room timelines + collect ALL conference days (globally, before
    #    applying room filter) so that we can scan every room on every day even
    #    when a room has no events on a particular day.
    all_conference_days_set = set()
    slots_by_room = {}

    for slot in slots:
        start_raw = slot.get("start")
        end_raw   = slot.get("end")
        if not start_raw or not end_raw:
            continue

        start_dt = parse_dt(start_raw)
        end_dt   = parse_dt(end_raw)
        if not start_dt or not end_dt:
            continue

        # Use naive wall-clock datetimes for comparison
        start_naive = local_naive(start_dt)
        end_naive   = local_naive(end_dt)

        # Track conference day regardless of room filter
        all_conference_days_set.add(start_naive.date())

        room_data = slot.get("room")
        if room_data is None:
            continue
        room_name = (
            format_localized(room_data.get("name"))
            if isinstance(room_data, dict)
            else str(room_data)
        )
        if not room_name:
            continue

        # Apply room filter
        if room_filter is not None and room_name not in room_filter:
            continue

        if room_name not in slots_by_room:
            slots_by_room[room_name] = []
        slots_by_room[room_name].append((start_naive, end_naive))

    all_conference_days = sorted(all_conference_days_set)

    # Ensure every room from the filter appears in slots_by_room, even if it
    # has zero scheduled events (it will be treated as fully free on all days).
    if room_filter:
        for room in room_filter:
            if room not in slots_by_room:
                slots_by_room[room] = []

    if not slots_by_room:
        print(f"\n{C_YELLOW}No rooms found to scan.{C_RESET}")
        if room_filter:
            print(f"{C_DIM}Hint: check that room names match exactly what Pretalx returns.{C_RESET}")
        sys.exit(0)

    rooms_with_slots = sum(1 for v in slots_by_room.values() if v)
    print(f"Rooms to scan: {C_BOLD}{len(slots_by_room)}{C_RESET} "
          f"({rooms_with_slots} with existing slots, "
          f"{len(slots_by_room) - rooms_with_slots} empty)")    
    print(f"Conference days detected: {C_BOLD}{len(all_conference_days)}{C_RESET}")

    # 5. Find free windows
    free_windows = find_free_slots(
        slots_by_room=slots_by_room,
        slot_duration=slot_duration,
        buffer=buffer,
        earliest_hour=EARLIEST_START_HOUR,
        latest_hour=LATEST_START_HOUR,
        all_conference_days=all_conference_days,
    )

    # 6. Print results
    print_section(
        f"Available Slots ({slot_duration}min) in '{event_slug}' — Schedule: {schedule_id}"
    )

    if not free_windows:
        print(f"\n  {C_RED}{C_BOLD}No free windows found for the requested slot size.{C_RESET}")
        print(f"  {C_DIM}Try a shorter --length or smaller --buffer.{C_RESET}")
        sys.exit(0)

    # Flatten and sort all windows globally by date + time
    all_windows_flat = []
    for room, windows in free_windows.items():
        for (ws, we) in windows:
            all_windows_flat.append((ws.date(), ws, we, room))
    all_windows_flat.sort(key=lambda x: (x[0], x[1]))

    # Group by day for clean output
    days_seen = sorted({x[0] for x in all_windows_flat})

    total_windows = 0
    for day in days_seen:
        day_windows = [x for x in all_windows_flat if x[0] == day]
        day_label   = day_windows[0][1].strftime("%A, %Y-%m-%d")

        print(f"\n  {C_GREEN}{C_BOLD}{day_label}{C_RESET}")
        print(f"  {C_GREEN}{'-' * 66}{C_RESET}")

        for _, ws, we, room in day_windows:
            # window_len is the range of valid START positions (in minutes).
            # Even a 0-length window (single valid start) means one slot fits.
            window_len = int((we - ws).total_seconds() / 60)
            slots_fitting = 1 + window_len // (slot_duration + buffer)

            # Show the actual slot time (first available: ws → ws+slot_duration)
            slot_end = ws + timedelta(minutes=slot_duration)
            if window_len == 0:
                # Exactly one valid start time
                time_str = f"{fmt_time(ws)} – {fmt_time(slot_end)}"
                extra    = ""
            else:
                # Range of valid starts; show first slot and last possible start
                last_slot_end = we + timedelta(minutes=slot_duration)
                time_str = f"{fmt_time(ws)} – {fmt_time(slot_end)}"
                extra    = f"  {C_DIM}(or start any 5min step up to {fmt_time(we)}, ends {fmt_time(last_slot_end)}){C_RESET}"

            slots_str = f"~{slots_fitting} slot(s)" if slots_fitting > 1 else "1 slot"
            print(
                f"    {C_YELLOW}{time_str}{C_RESET}"
                f"  {C_BOLD}{room}{C_RESET}"
                f"  {C_DIM}[{slots_str} fit]{C_RESET}"
                f"{extra}"
            )
            total_windows += 1

    # Summary
    print(f"\n{C_BOLD}{'=' * 70}{C_RESET}")
    print(
        f"{C_GREEN}{C_BOLD}★ Found {total_windows} free window(s) "
        f"across {len(free_windows)} room(s).{C_RESET}"
    )
    print(f"{C_BOLD}{'=' * 70}{C_RESET}\n")


if __name__ == "__main__":
    main()
