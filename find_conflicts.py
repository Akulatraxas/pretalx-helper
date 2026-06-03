#!/usr/bin/env python3
"""
Pretalx Submission Conflict Finder CLI Utility
Scans submissions of an event to find various validation and scheduling conflicts.
"""

import sys
import argparse
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
    print(f"\n{C_HEADER}{C_BOLD}{'=' * 60}{C_RESET}")
    print(f"{C_BLUE}{C_BOLD}>>> {title}{C_RESET}")
    print(f"{C_HEADER}{C_BOLD}{'=' * 60}{C_RESET}")

def is_empty_or_todo(text):
    if text is None:
        return True
    if isinstance(text, str):
        cleaned = text.strip()
        return len(cleaned) == 0 or "todo" in cleaned.lower()
    if isinstance(text, dict):
        all_empty = all(val is None or (isinstance(val, str) and len(val.strip()) == 0) for val in text.values())
        if all_empty:
            return True
        any_todo = any(isinstance(val, str) and "todo" in val.lower() for val in text.values())
        if any_todo:
            return True
        return False
    return True

def format_speakers(speakers):
    if not speakers:
        return f"{C_RED}None{C_RESET}"
    return ", ".join(speakers)

def main():
    parser = argparse.ArgumentParser(
        description="Finds conflicts in submissions of a Pretalx event."
    )
    parser.add_argument(
        "--event", 
        help="The slug of the event to check. If omitted, uses the first available event."
    )
    
    args = parser.parse_args()
    
    print(f"{C_GREEN}{C_BOLD}Pretalx Submission Conflict Finder{C_RESET}")
    print("Connecting to Pretalx instance and loading API credentials...")
    
    try:
        client = PretalxClient()
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Initialization Error:{C_RESET} {e}")
        print("Make sure PRETALX_URL and PRETALX_APIKEY are defined in your .env file.")
        sys.exit(1)
        
    print(f"✓ Connected to base site URL: {C_BOLD}{client.site_url}{C_RESET}")
    
    # 1. Determine Event
    event_slug = args.event
    if not event_slug:
        print("No event slug provided. Querying available events...")
        try:
            events = list(client.list_events())
            if not events:
                print(f"{C_RED}No events found on this Pretalx instance.{C_RESET}")
                sys.exit(1)
            elif len(events) == 1:
                event_slug = events[0].get("slug")
                print(f"Automatically selected the only available event: {C_BLUE}{C_BOLD}{event_slug}{C_RESET}")
            else:
                print(f"{C_YELLOW}Multiple events found. Please specify one with --event:{C_RESET}")
                for e in events:
                    print(f"  - {C_BOLD}{e.get('slug')}{C_RESET} ({e.get('name', {}).get('en') or e.get('name')})")
                sys.exit(1)
        except PretalxAPIError as e:
            print(f"{C_RED}Failed to query events: {e}{C_RESET}")
            sys.exit(1)

    print(f"Scanning event: {C_BLUE}{C_BOLD}{event_slug}{C_RESET}...\n")
    
    # 2. Fetch Submissions and WIP schedule (to check rooms in current draft)
    wip_slots = {}
    try:
        wip_schedule = client.get_schedule(event_slug, "wip", expand=["slots", "slots.room"])
        slots_list = wip_schedule.get("slots", [])
        for slot in slots_list:
            sub_val = slot.get("submission")
            sub_code = sub_val.get("code") if isinstance(sub_val, dict) else sub_val
            if sub_code:
                if sub_code not in wip_slots:
                    wip_slots[sub_code] = []
                wip_slots[sub_code].append(slot)
        print("✓ Loaded current working (WIP) schedule for room assignment checks.")
    except Exception as e:
        print(f"⚠ Could not retrieve WIP schedule ({e}). Falling back to latest published slots.")
        wip_slots = None

    try:
        submissions = list(client.list_submissions(event_slug, expand=["slots"]))
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to fetch submissions: {e}{C_RESET}")
        sys.exit(1)
        
    print(f"Retrieved {C_BOLD}{len(submissions)}{C_RESET} submissions.")
    
    # 3. Categorize conflicts
    empty_abstract = []
    empty_description = []
    confirmed_no_speaker = []
    confirmed_no_room = []
    
    for sub in submissions:
        code = sub.get("code")
        title = sub.get("title")
        abstract = sub.get("abstract")
        description = sub.get("description")
        state = sub.get("state")
        speakers = sub.get("speakers", [])
        slots = sub.get("slots", [])
        
        # Check empty or TODO abstract
        if is_empty_or_todo(abstract):
            empty_abstract.append(sub)
            
        # Check empty or TODO description
        if is_empty_or_todo(description):
            empty_description.append(sub)
            
        # Check confirmed with no speaker
        if state == "confirmed" and not speakers:
            confirmed_no_speaker.append(sub)
            
        # Check confirmed with no room
        if state == "confirmed":
            has_room = False
            # Use WIP schedule slots if available, otherwise fallback to submission-level slots
            sub_slots = wip_slots.get(code, []) if wip_slots is not None else slots
            for slot in sub_slots:
                if isinstance(slot, dict):
                    if slot.get("room") is not None:
                        has_room = True
                        break
                elif slot is not None:
                    # Fallback if slot is ID
                    has_room = True
                    break
            if not has_room:
                confirmed_no_room.append(sub)
                
    # 4. Print Results
    total_conflicts = len(empty_abstract) + len(empty_description) + len(confirmed_no_speaker) + len(confirmed_no_room)
    
    # Empty/TODO Abstract
    print_section("Category 1: Submissions with Empty or TODO Abstract")
    if empty_abstract:
        for sub in empty_abstract:
            print(f"  [{C_CYAN}{sub.get('code')}{C_RESET}] {C_BOLD}{sub.get('title')}{C_RESET}")
            print(f"      State:    {sub.get('state')}")
            print(f"      Speakers: {format_speakers(sub.get('speakers'))}")
            print()
    else:
        print(f"  {C_GREEN}✓ No submissions with empty or TODO abstract.{C_RESET}")
        
    # Empty/TODO Description
    print_section("Category 2: Submissions with Empty or TODO Description")
    if empty_description:
        for sub in empty_description:
            print(f"  [{C_CYAN}{sub.get('code')}{C_RESET}] {C_BOLD}{sub.get('title')}{C_RESET}")
            print(f"      State:    {sub.get('state')}")
            print(f"      Speakers: {format_speakers(sub.get('speakers'))}")
            print()
    else:
        print(f"  {C_GREEN}✓ No submissions with empty or TODO description.{C_RESET}")
        
    # Confirmed but no speaker
    print_section("Category 3: Confirmed Submissions with No Speaker")
    if confirmed_no_speaker:
        for sub in confirmed_no_speaker:
            print(f"  [{C_CYAN}{sub.get('code')}{C_RESET}] {C_BOLD}{sub.get('title')}{C_RESET}")
            print(f"      State:    {C_YELLOW}{sub.get('state')}{C_RESET}")
            print()
    else:
        print(f"  {C_GREEN}✓ No confirmed submissions missing speakers.{C_RESET}")
        
    # Confirmed but no room
    print_section("Category 4: Confirmed Submissions with No Room Assigned")
    if confirmed_no_room:
        for sub in confirmed_no_room:
            print(f"  [{C_CYAN}{sub.get('code')}{C_RESET}] {C_BOLD}{sub.get('title')}{C_RESET}")
            print(f"      State:    {C_YELLOW}{sub.get('state')}{C_RESET}")
            print(f"      Speakers: {format_speakers(sub.get('speakers'))}")
            print()
    else:
        print(f"  {C_GREEN}✓ No confirmed submissions missing rooms.{C_RESET}")
        
    # Summary
    print(f"\n{C_BOLD}{'=' * 60}{C_RESET}")
    if total_conflicts == 0:
        print(f"{C_GREEN}{C_BOLD}★ All checks passed! No conflicts found in event '{event_slug}'.{C_RESET}")
    else:
        print(f"{C_RED}{C_BOLD}⚠ Found {total_conflicts} conflict(s) in event '{event_slug}'.{C_RESET}")
        print(f"  - Empty/TODO Abstract:    {len(empty_abstract)}")
        print(f"  - Empty/TODO Description: {len(empty_description)}")
        print(f"  - Confirmed, No Speaker:   {len(confirmed_no_speaker)}")
        print(f"  - Confirmed, No Room:      {len(confirmed_no_room)}")
    print(f"{C_BOLD}{'=' * 60}{C_RESET}\n")

if __name__ == "__main__":
    main()
