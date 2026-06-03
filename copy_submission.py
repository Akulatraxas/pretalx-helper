#!/usr/bin/env python3
"""
Pretalx Submission Copy CLI Utility
"""

import sys
import argparse
from pretalx_client import PretalxClient, PretalxAPIError

# ANSI Colors for premium terminal output
C_HEADER = "\033[95m"
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"

def main():
    parser = argparse.ArgumentParser(
        description="Clones/Copies a Pretalx submission within an event and outputs the new submission details."
    )
    parser.add_argument("--event", required=True, help="The slug of the target event (e.g. eurofurence-30-2026)")
    parser.add_argument("--code", required=True, help="The code of the source submission to copy (e.g. MJRE78)")
    parser.add_argument("--title", help="Optional override for the new submission title")
    parser.add_argument("--duration", type=int, help="Optional override for the new submission duration in minutes")
    parser.add_argument("--slots", type=int, help="Optional override for the new submission slot count")

    args = parser.parse_args()

    print(f"{C_GREEN}{C_BOLD}Pretalx Submission Cloner{C_RESET}")
    print(f"Connecting to Pretalx instance and loading API credentials...")

    try:
        client = PretalxClient()
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Initialization Error:{C_RESET} {e}")
        print("Make sure PRETALX_URL and PRETALX_APIKEY are defined in your .env file.")
        sys.exit(1)

    print(f"✓ Connected to base site URL: {C_BOLD}{client.site_url}{C_RESET}")
    print(f"Cloning submission {C_BLUE}{C_BOLD}{args.code}{C_RESET} in event {C_BLUE}{C_BOLD}{args.event}{C_RESET}...")

    try:
        new_sub, orga_url = client.copy_submission(
            event_slug=args.event,
            code=args.code,
            title=args.title,
            duration=args.duration,
            slot_count=args.slots
        )

        print(f"\n{C_GREEN}{C_BOLD}✓ Submission Copied Successfully!{C_RESET}")
        print(f"  {C_BOLD}New Code:{C_RESET}        {C_GREEN}{C_BOLD}{new_sub.get('code')}{C_RESET}")
        print(f"  {C_BOLD}New Title:{C_RESET}       {new_sub.get('title')}")
        print(f"  {C_BOLD}Duration:{C_RESET}        {new_sub.get('duration')} minutes")
        print(f"  {C_BOLD}Slot Count:{C_RESET}      {new_sub.get('slot_count')}")
        print(f"  {C_BOLD}Track ID:{C_RESET}        {new_sub.get('track')}")
        print(f"  {C_BOLD}Sub Type ID:{C_RESET}     {new_sub.get('submission_type')}")
        print(f"  {C_BOLD}Organizer URL:{C_RESET}   {C_BLUE}{C_BOLD}{orga_url}{C_RESET}")
        print()

    except PretalxAPIError as e:
        print(f"\n{C_RED}{C_BOLD}API Error occurred during copy:{C_RESET} {e}")
        if e.response_body:
            print(f"Response details: {e.response_body}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{C_RED}{C_BOLD}Unexpected error occurred:{C_RESET} {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
