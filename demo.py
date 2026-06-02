#!/usr/bin/env python3
"""
Pretalx API Client Demo
An interactive and beautifully formatted demonstration of the zero-dependency Pretalx Client.
"""

import sys
from pretalx_client import PretalxClient, PretalxAPIError, PretalxNotFoundError, PretalxAuthError

# ANSI Colors for a premium terminal appearance
C_HEADER = "\033[95m"
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"

def print_section(title):
    print(f"\n{C_HEADER}{C_BOLD}{'=' * 60}{C_RESET}")
    print(f"{C_BLUE}{C_BOLD}>>> {title}{C_RESET}")
    print(f"{C_HEADER}{C_BOLD}{'=' * 60}{C_RESET}")

def main():
    print(f"{C_GREEN}{C_BOLD}Pretalx API Python Client Demo{C_RESET}")
    print("Loading credentials and initializing client...\n")
    
    try:
        # Client automatically loads from .env if url/apikey are omitted
        client = PretalxClient()
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Initialization Error:{C_RESET} {e}")
        print(f"Please verify that your {C_BOLD}.env{C_RESET} file exists and contains:")
        print("  PRETALX_URL=\"<your_pretalx_instance_url>\"")
        print("  PRETALX_APIKEY=\"<your_api_token>\"")
        sys.exit(1)
        
    print(f"{C_GREEN}✓ Client initialized successfully!{C_RESET}")
    print(f"  URL: {C_BOLD}{client.base_url}{C_RESET}")
    
    # 1. ROOT ENDPOINT
    print_section("1. API Root Endpoint (/api/)")
    try:
        root_data = client.get_root()
        print(f"  {C_BOLD}Instance Name:{C_RESET}  {root_data.get('name')}")
        print(f"  {C_BOLD}Pretalx Version:{C_RESET} {root_data.get('version')}")
        print(f"  {C_BOLD}API Version:{C_RESET}     {root_data.get('api_version')}")
        print(f"  {C_BOLD}Available URLs:{C_RESET}")
        for key, val in root_data.get("urls", {}).items():
            print(f"    - {C_BOLD}{key}:{C_RESET} {val}")
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to retrieve API root: {e}{C_RESET}")
        
    # 2. EVENTS
    print_section("2. Events List (/api/events/)")
    events = []
    try:
        # list_events returns a generator; we convert to list to check size
        events = list(client.list_events())
        print(f"Found {C_BOLD}{len(events)}{C_RESET} accessible event(s):\n")
        for i, event in enumerate(events, 1):
            name = event.get("name", {}).get("en") or event.get("name")
            slug = event.get("slug")
            is_public = event.get("is_public")
            tz = event.get("timezone")
            pub_status = f"{C_GREEN}Public{C_RESET}" if is_public else f"{C_RED}Private{C_RESET}"
            
            print(f"  [{i}] {C_GREEN}{C_BOLD}{name}{C_RESET} ({pub_status})")
            print(f"      Slug:     {C_BOLD}{slug}{C_RESET}")
            print(f"      Timezone: {tz}")
            print(f"      Duration: {event.get('date_from')} to {event.get('date_to')}")
            print()
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to list events: {e}{C_RESET}")
        
    # Let's target the first event if available for detail inspection
    if not events:
        print(f"{C_YELLOW}No events found to showcase schedules, speakers, or slots.{C_RESET}")
        sys.exit(0)
        
    target_event_slug = events[0].get("slug")
    
    # 3. ORGANISER TEAMS (Demonstrating grace handles)
    print_section("3. Organiser Teams (/api/organisers/{organiser}/teams/)")
    # Since organizer slug is not part of standard event detail, we guess the slug or ask the user
    # Pretalx organizers are usually slugs representing groups. Let's try event slug prefix or common name
    guess_organiser = target_event_slug.split("-")[0] if "-" in target_event_slug else target_event_slug
    print(f"Attempting to query teams for organiser: {C_BOLD}{guess_organiser}{C_RESET}...")
    try:
        teams = list(client.list_teams(guess_organiser))
        print(f"{C_GREEN}✓ Successfully retrieved teams!{C_RESET}")
        for team in teams:
            print(f"  - {C_BOLD}{team.get('name')}{C_RESET} (ID: {team.get('id')})")
    except PretalxNotFoundError:
        print(f"{C_YELLOW}ℹ Teams not found for organiser '{guess_organiser}'.{C_RESET}")
        print("  Note: Teams exist outside event hierarchy and require a correct organiser slug.")
        print("  You can query teams by calling:")
        print(f"  {C_BOLD}client.list_teams(organiser_slug=\"your-organiser-slug\"){C_RESET}")
    except PretalxAuthError:
        print(f"{C_YELLOW}ℹ Permission Denied to access organiser teams.{C_RESET}")
        print("  Your API token may not have organizer-level scoping.")
        
    # 4. SCHEDULES
    print_section(f"4. Schedules for '{target_event_slug}' (/api/events/{{event}}/schedules/)")
    try:
        schedules = list(client.list_schedules(target_event_slug))
        print(f"Found {C_BOLD}{len(schedules)}{C_RESET} schedule version(s):\n")
        for sched in schedules:
            ver = sched.get("version") or "wip (Work In Progress)"
            published = sched.get("published") or "Not Published"
            print(f"  - Version: {C_GREEN}{C_BOLD}{ver:<10}{C_RESET} | ID: {sched.get('id'):<3} | Published: {published}")
            
        print(f"\nRetrieving {C_BOLD}latest{C_RESET} schedule detail (expanded room and slots)...")
        # Fetch detailed latest schedule
        latest_sched = client.get_schedule(
            target_event_slug, 
            "latest", 
            expand=["slots", "slots.room", "slots.submission"]
        )
        print(f"  {C_GREEN}✓ Retrieved Detailed Schedule (Version: {latest_sched.get('version')}){C_RESET}")
        print(f"  Total Schedule Slots: {len(latest_sched.get('slots', []))}")
    except PretalxNotFoundError:
        print(f"{C_YELLOW}ℹ Latest schedule details not available (event might not be published yet).{C_RESET}")
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to retrieve schedules: {e}{C_RESET}")
        
    # 5. SPEAKERS
    print_section(f"5. Speakers for '{target_event_slug}' (/api/events/{{event}}/speakers/)")
    try:
        speakers = list(client.list_speakers(target_event_slug))
        print(f"Found {C_BOLD}{len(speakers)}{C_RESET} speaker(s):\n")
        for i, speaker in enumerate(speakers[:5], 1):  # Limit display to 5
            name = speaker.get("name")
            code = speaker.get("code")
            subs = ", ".join(speaker.get("submissions", []))
            print(f"  [{i}] {C_GREEN}{C_BOLD}{name:<20}{C_RESET} (Code: {code})")
            print(f"      Submissions: {subs}")
            print(f"      Timezone:    {speaker.get('timezone')} | Locale: {speaker.get('locale')}")
        if len(speakers) > 5:
            print(f"  ... and {C_BOLD}{len(speakers) - 5}{C_RESET} more speakers.")
            
        # Detail inspection of the first speaker
        if speakers:
            first_code = speakers[0].get("code")
            print(f"\nRetrieving detailed info for speaker code {C_BOLD}{first_code}{C_RESET}...")
            sp_detail = client.get_speaker(target_event_slug, first_code)
            print(f"  Name:      {C_GREEN}{C_BOLD}{sp_detail.get('name')}{C_RESET}")
            print(f"  Biography: {sp_detail.get('biography') or 'No biography provided'}")
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to list/get speakers: {e}{C_RESET}")
        
    # 6. TALK SLOTS
    print_section(f"6. Talk Slots for '{target_event_slug}' (/api/events/{{event}}/slots/)")
    try:
        # List slots expanded with room and submission details
        slots = list(client.list_slots(target_event_slug, expand=["room", "submission"]))
        print(f"Found {C_BOLD}{len(slots)}{C_RESET} slots scheduled in the latest version:\n")
        for i, slot in enumerate(slots, 1):
            sub_title = "No Submission Info"
            if isinstance(slot.get("submission"), dict):
                sub_title = slot.get("submission", {}).get("title")
            elif slot.get("submission"):
                sub_title = f"Submission ID: {slot.get('submission')}"
                
            room_name = "Unknown Room"
            if isinstance(slot.get("room"), dict):
                room_name = slot.get("room", {}).get("name", {}).get("en") or slot.get("room", {}).get("name")
            elif slot.get("room"):
                room_name = f"Room ID: {slot.get('room')}"
                
            start = slot.get("start") or "N/A"
            end = slot.get("end") or "N/A"
            
            print(f"  [{i}] {C_GREEN}{C_BOLD}{sub_title}{C_RESET}")
            print(f"      Room:     {room_name}")
            print(f"      Time:     {start} to {end} ({slot.get('duration')} mins)")
            print()
    except PretalxAPIError as e:
        print(f"{C_RED}Failed to list talk slots: {e}{C_RESET}")

    print(f"\n{C_GREEN}{C_BOLD}Demo Finished! Enjoy playing with the Pretalx API!{C_RESET}\n")

if __name__ == "__main__":
    main()
