#!/usr/bin/env python3
"""
Pretalx Schedule Drill-Down CLI Utility
Allows drilling down into pretalx data: schedules -> slots -> submissions.
"""

import sys
import argparse
from datetime import datetime
from pretalx_client import PretalxClient, PretalxAPIError

# ANSI Colors for premium terminal output
C_HEADER = "\033[95m"
C_BLUE = "\033[94m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"

def print_section(title):
    print(f"\n{C_HEADER}{C_BOLD}{'=' * 70}{C_RESET}")
    print(f"{C_BLUE}{C_BOLD}>>> {title}{C_RESET}")
    print(f"{C_HEADER}{C_BOLD}{'=' * 70}{C_RESET}")

def format_localized(val):
    """Formats localized strings (e.g., {'en': 'Room Name'}) to standard English or first key."""
    if isinstance(val, dict):
        return val.get("en") or next(iter(val.values())) if val else ""
    return str(val) if val is not None else ""

def format_expanded_field(field_val):
    """Formats an expanded ID/Name dictionary field (like track or submission_type)."""
    if isinstance(field_val, dict):
        name_val = field_val.get("name")
        name = format_localized(name_val)
        fid = field_val.get("id")
        if name:
            return f"{name} (ID: {fid})"
        return f"ID: {fid}"
    return str(field_val) if field_val is not None else ""

def format_tags(tags_list):
    """Formats a list of tag objects or IDs."""
    if not tags_list:
        return ""
    formatted = []
    for tag in tags_list:
        if isinstance(tag, dict):
            tag_name = tag.get("tag") or tag.get("name")
            tag_str = format_localized(tag_name)
            if tag_str:
                formatted.append(tag_str)
            else:
                formatted.append(str(tag.get("id", tag)))
        else:
            formatted.append(str(tag))
    return ", ".join(formatted)

def parse_slot_datetime(iso_str):
    """Parses an ISO 8601 datetime string safely."""
    if not iso_str:
        return None
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None

def format_day(iso_str):
    """Returns a formatted day representation (e.g., 'Friday, 2026-06-05')."""
    dt = parse_slot_datetime(iso_str)
    if dt:
        return dt.strftime("%A, %Y-%m-%d")
    if len(iso_str) >= 10:
        return iso_str[:10]
    return "Unknown Day"

def format_time(iso_str):
    """Returns a formatted time representation (e.g., '09:00')."""
    dt = parse_slot_datetime(iso_str)
    if dt:
        return dt.strftime("%H:%M")
    if "T" in iso_str:
        return iso_str.split("T")[1][:5]
    return iso_str

def format_schedule_version(sched):
    """Returns a clean schedule version string from a schedule object or ID."""
    if not sched:
        return "Unknown"
    if isinstance(sched, dict):
        version = sched.get("version")
        if version is None:
            return "wip (Work In Progress)"
        return version
    return f"Schedule ID: {sched}"

def main():
    parser = argparse.ArgumentParser(
        description="Drill down into Pretalx data: schedules -> slots -> submissions"
    )
    parser.add_argument(
        "--event",
        help="The slug of the event to check. If omitted, uses the first/only available event."
    )
    parser.add_argument(
        "--schedule", "-s",
        help="The schedule version or ID to view slots for. (e.g., 'wip', 'latest', 'v1.0')"
    )
    parser.add_argument(
        "--submission", "-c",
        help="The alphanumeric submission code to view details for (e.g., 'ABC123')."
    )

    args = parser.parse_args()

    # Initialize client
    try:
        client = PretalxClient()
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Initialization Error:{C_RESET} {e}")
        print("Make sure PRETALX_URL and PRETALX_APIKEY are defined in your .env file.")
        sys.exit(1)

    # 1. Determine Event
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
                for e in events:
                    print(f"  - {C_BOLD}{e.get('slug')}{C_RESET} ({e.get('name', {}).get('en') or e.get('name')})")
                sys.exit(1)
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to query events: {e}{C_RESET}")
            sys.exit(1)

    # Fetch event details to show name
    try:
        event_details = client.get_event(event_slug)
        event_name = format_localized(event_details.get("name"))
    except Exception:
        event_name = "Pretalx Event"

    # --- Flow 3: Submission Details (if --submission is specified) ---
    if args.submission:
        sub_code = args.submission
        print_section(f"Submission Details: {sub_code} in Event '{event_name}' ({event_slug})")
        
        try:
            # Get detailed submission data
            sub = client.get_submission(
                event_slug, 
                sub_code, 
                expand=["speakers", "track", "submission_type", "tags"]
            )
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to retrieve submission details for '{sub_code}': {e}{C_RESET}")
            sys.exit(1)

        # 3.1 Logical Grouping of Fields
        # Group 1: Basic Info
        print(f"\n{C_BLUE}{C_BOLD}[BASIC INFO]{C_RESET}")
        basic_fields = [
            ("Code", sub.get("code")),
            ("Title", sub.get("title")),
            ("State", sub.get("state")),
            ("Language", sub.get("content_locale")),
            ("Duration", f"{sub.get('duration')} mins" if sub.get("duration") is not None else None),
            ("Slot Count", sub.get("slot_count")),
            ("Created", sub.get("created")),
            ("Modified", sub.get("modified")),
        ]
        for label, val in basic_fields:
            if val is not None and str(val).strip() != "":
                # Color code state if applicable
                if label == "State":
                    state_color = C_GREEN if val == "confirmed" else (C_YELLOW if val == "accepted" else C_CYAN)
                    val = f"{state_color}{val}{C_RESET}"
                print(f"  {C_BOLD}{label:<15}:{C_RESET} {val}")

        # Group 2: Content
        content_fields = [
            ("Abstract", sub.get("abstract")),
            ("Description", sub.get("description")),
            ("Submitter Notes", sub.get("notes")),
            ("Internal Notes", sub.get("internal_notes")),
        ]
        has_content = any(val is not None and str(val).strip() != "" for _, val in content_fields)
        if has_content:
            print(f"\n{C_BLUE}{C_BOLD}[CONTENT]{C_RESET}")
            for label, val in content_fields:
                if val is not None and str(val).strip() != "":
                    # Print multi-line strings indented nicely
                    lines = val.strip().split("\n")
                    print(f"  {C_BOLD}{label}:{C_RESET}")
                    for line in lines:
                        print(f"    {line}")

        # Group 3: Metadata
        metadata_fields = [
            ("Track", format_expanded_field(sub.get("track"))),
            ("Submission Type", format_expanded_field(sub.get("submission_type"))),
            ("Tags", format_tags(sub.get("tags"))),
        ]
        has_metadata = any(val is not None and str(val).strip() != "" for _, val in metadata_fields)
        if has_metadata:
            print(f"\n{C_BLUE}{C_BOLD}[METADATA]{C_RESET}")
            for label, val in metadata_fields:
                if val is not None and str(val).strip() != "":
                    print(f"  {C_BOLD}{label:<15}:{C_RESET} {val}")

        # Group 4: Speakers
        speakers = sub.get("speakers", [])
        if speakers:
            print(f"\n{C_BLUE}{C_BOLD}[SPEAKERS]{C_RESET}")
            for sp in speakers:
                name = sp.get("name") if isinstance(sp, dict) else str(sp)
                code = sp.get("code") if isinstance(sp, dict) else None
                bio = sp.get("biography") if isinstance(sp, dict) else None
                
                code_str = f" (Code: {code})" if code else ""
                print(f"  - {C_GREEN}{C_BOLD}{name}{C_RESET}{code_str}")
                if bio and bio.strip():
                    # Format biography indented
                    bio_lines = bio.strip().split("\n")
                    print(f"    {C_BOLD}Bio:{C_RESET}")
                    for line in bio_lines:
                        print(f"      {line}")

        # Group 5: Associated Slots
        print(f"\n{C_BLUE}{C_BOLD}[SCHEDULED SLOTS]{C_RESET}")
        try:
            slots = list(client.list_slots(event_slug, submission=sub_code, expand=["room", "schedule"]))
            if not slots:
                print(f"  {C_YELLOW}Not scheduled in any version.{C_RESET}")
            else:
                for slot in slots:
                    sched_ver = format_schedule_version(slot.get("schedule"))
                    room_data = slot.get("room")
                    room_name = format_localized(room_data.get("name")) if isinstance(room_data, dict) else str(room_data)
                    start = slot.get("start")
                    end = slot.get("end")
                    
                    if start and end:
                        day = format_day(start)
                        time_range = f"{format_time(start)} - {format_time(end)}"
                        print(f"  - {C_BOLD}{sched_ver:<10}:{C_RESET} {day} {C_YELLOW}{time_range}{C_RESET} @ {C_CYAN}{room_name}{C_RESET}")
                    else:
                        print(f"  - {C_BOLD}{sched_ver:<10}:{C_RESET} {C_YELLOW}Unscheduled{C_RESET} @ {C_CYAN}{room_name or 'No Room'}{C_RESET}")
        except Exception as e:
            print(f"  {C_RED}Failed to query slot associations: {e}{C_RESET}")
        print()

    # --- Flow 2: Schedule Slots (if --schedule is specified) ---
    elif args.schedule:
        schedule_input = args.schedule.strip()
        print_section(f"Schedule Slots: Version '{schedule_input}' in '{event_name}' ({event_slug})")

        schedule_id = None
        # Handle "latest" and "wip" directly
        if schedule_input.lower() in ("latest", "wip"):
            schedule_id = schedule_input.lower()
        else:
            # Query versions list to resolve version name/id
            try:
                schedules = list(client.list_schedules(event_slug))
                for sched in schedules:
                    if sched.get("version") == schedule_input or str(sched.get("id")) == schedule_input:
                        schedule_id = sched.get("id")
                        break
                
                # Fallback to integer ID direct check
                if schedule_id is None:
                    try:
                        schedule_id = int(schedule_input)
                    except ValueError:
                        pass
            except PretalxAPIError as e:
                print(f"{C_RED}Failed to query schedules list: {e}{C_RESET}")
                sys.exit(1)

        if schedule_id is None:
            print(f"{C_RED}Error: Schedule version or ID '{schedule_input}' not found.{C_RESET}")
            sys.exit(1)

        try:
            # Fetch complete schedule detail
            schedule_detail = client.get_schedule(
                event_slug,
                schedule_id,
                expand=["slots", "slots.room", "slots.submission", "slots.submission.speakers"]
            )
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to fetch schedule details: {e}{C_RESET}")
            sys.exit(1)

        slots = schedule_detail.get("slots", [])
        if not slots:
            print(f"{C_YELLOW}No slots found in this schedule.{C_RESET}")
            sys.exit(0)

        # Sort and Group slots
        grouped_slots = {}
        unscheduled_slots = []

        for slot in slots:
            start = slot.get("start")
            if not start:
                unscheduled_slots.append(slot)
            else:
                day_str = format_day(start)
                if day_str not in grouped_slots:
                    grouped_slots[day_str] = []
                grouped_slots[day_str].append(slot)

        # Sort days chronologically using the YYYY-MM-DD from the string
        sorted_days = sorted(grouped_slots.keys(), key=lambda d: d.split(", ")[-1] if ", " in d else d)

        # Print scheduled slots grouped by day
        for day in sorted_days:
            # Sort slots within day by start time
            day_slots = grouped_slots[day]
            day_slots.sort(key=lambda s: s.get("start") or "")

            print(f"\n{C_GREEN}{C_BOLD}{day}{C_RESET}")
            print(f"{C_GREEN}{'-' * 70}{C_RESET}")
            
            for slot in day_slots:
                start = slot.get("start")
                end = slot.get("end")
                time_range = f"{format_time(start)} - {format_time(end)}" if start and end else "N/A"
                
                room_data = slot.get("room")
                room_name = format_localized(room_data.get("name")) if isinstance(room_data, dict) else str(room_data or "No Room")
                
                sub_data = slot.get("submission")
                if isinstance(sub_data, dict):
                    sub_code = sub_data.get("code") or "N/A"
                    sub_title = sub_data.get("title") or "No Title"
                    speakers = sub_data.get("speakers", [])
                    if speakers:
                        speaker_names = [sp.get("name") if isinstance(sp, dict) else str(sp) for sp in speakers]
                        speakers_str = f" (Speakers: {', '.join(speaker_names)})"
                    else:
                        speakers_str = ""
                else:
                    blocker_desc = format_localized(slot.get("description"))
                    if blocker_desc:
                        sub_code = "BLOCKER"
                        sub_title = blocker_desc
                    else:
                        sub_code = str(sub_data) if sub_data else "N/A"
                        sub_title = "Unknown Submission"
                    speakers_str = ""

                duration = slot.get("duration")
                duration_str = f" [{duration}m]" if duration is not None else ""

                print(f"  {C_BLUE}{time_range:<13}{C_RESET} | {C_YELLOW}{room_name:<16}{C_RESET} | [{C_CYAN}{sub_code}{C_RESET}] {C_BOLD}{sub_title}{C_RESET}{speakers_str}{duration_str}")

        # Print unscheduled slots if any
        if unscheduled_slots:
            print(f"\n{C_RED}{C_BOLD}Unscheduled Slots{C_RESET}")
            print(f"{C_RED}{'-' * 70}{C_RESET}")
            for slot in unscheduled_slots:
                room_data = slot.get("room")
                room_name = format_localized(room_data.get("name")) if isinstance(room_data, dict) else str(room_data or "No Room")
                
                sub_data = slot.get("submission")
                if isinstance(sub_data, dict):
                    sub_code = sub_data.get("code") or "N/A"
                    sub_title = sub_data.get("title") or "No Title"
                else:
                    blocker_desc = format_localized(slot.get("description"))
                    if blocker_desc:
                        sub_code = "BLOCKER"
                        sub_title = blocker_desc
                    else:
                        sub_code = str(sub_data) if sub_data else "N/A"
                        sub_title = "Unknown Submission"
                
                print(f"  {C_YELLOW}{'Unscheduled':<13}{C_RESET} | {C_YELLOW}{room_name:<16}{C_RESET} | [{C_CYAN}{sub_code}{C_RESET}] {C_BOLD}{sub_title}{C_RESET}")
        print()

    # --- Flow 1: List Schedules (default) ---
    else:
        print_section(f"Available Schedules for '{event_name}' ({event_slug})")
        
        try:
            schedules = list(client.list_schedules(event_slug))
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to query schedules: {e}{C_RESET}")
            sys.exit(1)

        print(f"Injecting special quick-access selectors:")
        print(f"  - Version: {C_GREEN}{C_BOLD}{'wip':<10}{C_RESET} | {C_BLUE}Work In Progress / Draft Schedule{C_RESET}")
        print(f"  - Version: {C_GREEN}{C_BOLD}{'latest':<10}{C_RESET} | {C_BLUE}Latest Published Schedule{C_RESET}")
        
        # Display other schedules returned by the API
        versioned_schedules = [s for s in schedules if s.get("version") is not None]
        if versioned_schedules:
            print(f"\nPublished Versions:")
            for sched in versioned_schedules:
                ver = sched.get("version")
                published = sched.get("published") or "Not Published"
                print(f"  - Version: {C_GREEN}{C_BOLD}{ver:<10}{C_RESET} | ID: {sched.get('id'):<3} | Published: {published}")
        print()

if __name__ == "__main__":
    main()
