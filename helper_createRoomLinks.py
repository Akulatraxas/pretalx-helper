#!/usr/bin/env python3
"""
helper_createRoomLinks.py

Generates a CSV file listing all rooms for the configured Pretalx event,
including a public schedule URL with the room filter pre-applied and a
QR code image (PNG) for each room URL.

Output:
  output/room_links.csv         — CSV with Room ID, Room Name, Room URL, QR-Code
  output/qr_room_{id}.png       — QR code images for each room

2026 - Akulatraxas - Eurofurence e.V.

"""

import os
import sys
import csv

import qrcode

from pretalx_client import PretalxClient, PretalxAPIError, load_env

# ---------------------------------------------------------------------------
# ANSI colours (consistent with other helper scripts in this project)
# ---------------------------------------------------------------------------
C_PURPLE = "\033[95m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_output_dir(path: str) -> None:
    """Create the output directory if it does not already exist."""
    os.makedirs(path, exist_ok=True)


def load_config() -> dict:
    """
    Load required configuration from environment / .env file.
    Returns a dict with keys: event_slug, schedule_url_public.
    """
    load_env()

    event_slug = os.environ.get("PRETALX_EVENT_SLUG", "").strip()
    if not event_slug:
        print(f"{C_RED}{C_BOLD}Error:{C_RESET} PRETALX_EVENT_SLUG is not set in .env")
        sys.exit(1)

    schedule_url_public = os.environ.get("EF_SCHEDULE_URL_PUBLIC", "").strip().rstrip("/")
    if not schedule_url_public:
        print(f"{C_RED}{C_BOLD}Error:{C_RESET} EF_SCHEDULE_URL_PUBLIC is not set in .env")
        print(f"  Add a line like: EF_SCHEDULE_URL_PUBLIC=\"http://shell01.nest:8089/ef-schedule-preview\"")
        sys.exit(1)

    return {
        "event_slug": event_slug,
        "schedule_url_public": schedule_url_public,
    }


def build_room_url(schedule_url_public: str, room_id: int) -> str:
    """Build the public schedule URL with the room filter pre-applied."""
    return f"{schedule_url_public}/?rooms={room_id}"


def generate_qr(url: str, output_path: str) -> None:
    """Generate a QR code PNG for *url* and save it to *output_path*."""
    qr = qrcode.QRCode(
        version=None,           # auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n{C_PURPLE}{C_BOLD}╔══════════════════════════════════════════╗{C_RESET}")
    print(f"{C_PURPLE}{C_BOLD}║   Pretalx — Room Link & QR Generator    ║{C_RESET}")
    print(f"{C_PURPLE}{C_BOLD}╚══════════════════════════════════════════╝{C_RESET}\n")

    config = load_config()
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    ensure_output_dir(output_dir)

    # ------------------------------------------------------------------
    # Connect to Pretalx
    # ------------------------------------------------------------------
    print(f"  Connecting to Pretalx API…")
    try:
        client = PretalxClient()
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Initialization Error:{C_RESET} {e}")
        print("  Make sure PRETALX_URL and PRETALX_APIKEY are set in your .env file.")
        sys.exit(1)

    print(f"  {C_GREEN}✓{C_RESET} Connected to {C_BOLD}{client.site_url}{C_RESET}")
    print(f"  Event slug  : {C_CYAN}{C_BOLD}{config['event_slug']}{C_RESET}")
    print(f"  Schedule URL: {C_CYAN}{config['schedule_url_public']}{C_RESET}\n")

    # ------------------------------------------------------------------
    # Fetch rooms
    # ------------------------------------------------------------------
    print(f"  Fetching rooms for event {C_BOLD}{config['event_slug']}{C_RESET}…")
    try:
        rooms = list(client.list_rooms(config["event_slug"]))
    except PretalxAPIError as e:
        print(f"{C_RED}{C_BOLD}API Error:{C_RESET} {e}")
        sys.exit(1)
    except Exception as e:
        print(f"{C_RED}{C_BOLD}Unexpected error:{C_RESET} {e}")
        sys.exit(1)

    if not rooms:
        print(f"{C_YELLOW}Warning:{C_RESET} No rooms found for this event.")
        sys.exit(0)

    print(f"  {C_GREEN}✓{C_RESET} Found {C_BOLD}{len(rooms)}{C_RESET} room(s).\n")

    # ------------------------------------------------------------------
    # Build rows, generate QR codes
    # ------------------------------------------------------------------
    csv_path = os.path.join(output_dir, "room_links.csv")
    rows = []

    print(f"  {'Room ID':<10} {'Room Name':<35} {'QR File'}")
    print(f"  {'─'*10} {'─'*35} {'─'*30}")

    for room in rooms:
        room_id   = room["id"]
        room_name = room.get("name", "")
        # Pretalx may return localized name dicts; extract "en" if so
        if isinstance(room_name, dict):
            room_name = room_name.get("en") or next(iter(room_name.values()), str(room_id))

        room_url  = build_room_url(config["schedule_url_public"], room_id)
        qr_file   = f"qr_room_{room_id}.png"
        qr_path   = os.path.join(output_dir, qr_file)

        generate_qr(room_url, qr_path)

        rows.append({
            "Room ID":   room_id,
            "Room Name": room_name,
            "Room URL":  room_url,
            "QR-Code":   qr_file,
        })

        print(f"  {str(room_id):<10} {room_name:<35} {qr_file}  {C_GREEN}✓{C_RESET}")

    # ------------------------------------------------------------------
    # Write CSV
    # ------------------------------------------------------------------
    print()
    fieldnames = ["Room ID", "Room Name", "Room URL", "QR-Code"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  {C_GREEN}{C_BOLD}✓ CSV written:{C_RESET}  {C_CYAN}{csv_path}{C_RESET}")
    print(f"  {C_GREEN}{C_BOLD}✓ QR images:{C_RESET}   {C_CYAN}{output_dir}/{C_RESET}\n")


if __name__ == "__main__":
    main()
