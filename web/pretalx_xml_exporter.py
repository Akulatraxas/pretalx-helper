"""
xml_exporter.py - Pretalx frab-like XML schedule exporter
Converts our cached schedule data dictionary into frab-ish XML format.

Pretalx provides an XML exporter too, but that does not suit our need to 
select only certain tracks and talks. So this is a custom script for that.

Inspired by https://github.com/jendrikw/ef-sched/blob/main/ef-sched.py

"""

import re
import uuid
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET


def slugify(text):
    """Convert text to lowercase kebab-case slug."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text


def format_duration(duration_minutes):
    """Format duration integer minutes as HH:MM string."""
    if not duration_minutes or not isinstance(duration_minutes, int):
        return "00:00"
    hours = duration_minutes // 60
    minutes = duration_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def extract_tz_offset(iso_str):
    """Extract timezone offset (e.g. +02:00 or Z) from ISO datetime string."""
    if not iso_str:
        return "+02:00"
    if iso_str.endswith("Z"):
        return "+00:00"
    match = re.search(r'([+-]\d{2}:\d{2})$', iso_str)
    if match:
        return match.group(1)
    return "+02:00"


def generate_pretalx_xml(data, pretalx_url="https://cfp.eurofurence.org"):
    """
    Generate frab-compatible Pretalx XML string from normalized schedule data dict.
    """
    event_info = data.get("event", {})
    event_name = event_info.get("name", "Schedule")
    event_slug = event_info.get("slug", "event")
    schedule_version = data.get("schedule_version", "1.0")
    base_url = (pretalx_url or "https://cfp.eurofurence.org").rstrip("/")

    days = data.get("days", [])
    first_day = days[0]["date"] if days else ""
    last_day = days[-1]["date"] if days else ""

    # Detect timezone offset from first available slot
    tz_offset = "+02:00"
    for d in days:
        for s in d.get("slots", []):
            if s.get("start"):
                tz_offset = extract_tz_offset(s["start"])
                break
        if tz_offset != "+02:00":
            break

    root = ET.Element("schedule")

    # Generator element ;  pretending to be pretalx for now.
    # I am not sure if the reading tools will check for this, but maybe a hint is good.
    ET.SubElement(root, "generator", attrib={"name": "pretalx", "version": "2026.1.2"})

    # Version tag
    version_elem = ET.SubElement(root, "version")
    version_elem.text = str(schedule_version)

    # Conference metadata
    conf = ET.SubElement(root, "conference")
    ET.SubElement(conf, "title").text = event_name
    ET.SubElement(conf, "acronym").text = event_slug
    ET.SubElement(conf, "start").text = first_day
    ET.SubElement(conf, "end").text = last_day
    ET.SubElement(conf, "days").text = str(len(days))
    ET.SubElement(conf, "timeslot_duration").text = "00:05"
    ET.SubElement(conf, "base_url").text = base_url
    ET.SubElement(conf, "time_zone_name").text = "Europe/Berlin"

    # Tracks
    for track in data.get("tracks", []):
        t_name = track.get("name", "")
        t_id = track.get("id", "")
        t_slug = f"{t_id}-{slugify(t_name)}" if t_id else slugify(t_name)
        t_color = track.get("color", "")
        ET.SubElement(conf, "track", attrib={
            "name": t_name,
            "slug": t_slug,
            "color": t_color,
        })

    # Have Days
    for idx, day_data in enumerate(days, start=1):
        day_date = day_data.get("date", "")
        if day_date == "unscheduled":
            continue

        try:
            dt = datetime.strptime(day_date, "%Y-%m-%d")
            next_dt = dt + timedelta(days=1)
            next_date = next_dt.strftime("%Y-%m-%d")
        except ValueError:
            next_date = day_date

        day_start = f"{day_date}T04:00:00{tz_offset}"
        day_end = f"{next_date}T03:59:00{tz_offset}"

        day_elem = ET.SubElement(root, "day", attrib={
            "index": str(idx),
            "date": day_date,
            "start": day_start,
            "end": day_end,
        })

        # Group non-blocker, non-internal slots on this day by room
        slots_by_room = {}
        for slot in day_data.get("slots", []):
            # Exclude blockers and internal-tagged/tracked sloties
            # We probably won't see them here as they are not in the 'wip' schedule, but just in case they are.
            if slot.get("is_blocker"):
                continue
            track_obj = slot.get("track")
            if track_obj and isinstance(track_obj, dict) and track_obj.get("name", "").strip().lower() == "internal":
                continue
            if any(t.get("tag", "").strip().lower() == "internal" for t in slot.get("tags", [])):
                continue

            r_info = slot.get("room") or {}
            r_id = r_info.get("id") if isinstance(r_info, dict) else r_info
            r_name = r_info.get("name", "") if isinstance(r_info, dict) else str(r_info)

            if r_id not in slots_by_room:
                slots_by_room[r_id] = {"name": r_name, "id": r_id, "slots": []}
            slots_by_room[r_id]["slots"].append(slot)

        # Sort rooms by data["rooms"] position order if available
        room_order_map = {r["id"]: i for i, r in enumerate(data.get("rooms", []))}
        sorted_room_ids = sorted(slots_by_room.keys(), key=lambda rid: room_order_map.get(rid, 9999))

        for rid in sorted_room_ids:
            room_group = slots_by_room[rid]
            r_name = room_group["name"]
            r_guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"room:{rid}"))

            room_elem = ET.SubElement(day_elem, "room", attrib={
                "name": r_name,
                "guid": r_guid,
            })

            for slot in room_group["slots"]:
                slot_id = str(slot.get("id", ""))
                slot_code = slot.get("code", "")
                slot_index = slot.get("slot_index", 0)
                slot_guid = slot.get("guid") or str(uuid.uuid5(uuid.NAMESPACE_URL, f"event:{slot_code}-{slot_index}"))

                event_elem = ET.SubElement(room_elem, "event", attrib={
                    "guid": slot_guid,
                    "id": slot_id,
                    "code": slot_code,
                })

                ET.SubElement(event_elem, "room").text = r_name
                ET.SubElement(event_elem, "title").text = slot.get("title", "")
                ET.SubElement(event_elem, "subtitle").text = ""
                ET.SubElement(event_elem, "type").text = slot.get("submission_type", "")

                start_iso = slot.get("start", "")
                ET.SubElement(event_elem, "date").text = start_iso

                # Extract HH:MM start time
                start_time_str = ""
                if start_iso and "T" in start_iso:
                    start_time_str = start_iso.split("T")[1][:5]
                ET.SubElement(event_elem, "start").text = start_time_str

                duration_min = slot.get("duration", 0)
                ET.SubElement(event_elem, "duration").text = format_duration(duration_min)

                # Abstract (plain text without HTML tags)
                abs_text = slot.get("raw_abstract") or slot.get("abstract") or ""
                ET.SubElement(event_elem, "abstract").text = abs_text

                # Slug: {event_slug}-{slot_id}-{slot_index}-{slugified_title} (or without slot_index if 0)
                title_slug = slugify(slot.get("title", ""))
                if slot_index > 0:
                    event_slug_val = f"{event_slug}-{slot_id}-{slot_index}-{title_slug}"
                else:
                    event_slug_val = f"{event_slug}-{slot_id}-{title_slug}"
                ET.SubElement(event_elem, "slug").text = event_slug_val

                # Track
                t_obj = slot.get("track")
                if t_obj and isinstance(t_obj, dict):
                    ET.SubElement(event_elem, "track").text = t_obj.get("name", "")

                # Tags
                tags_elem = ET.SubElement(event_elem, "tags")
                for tag_obj in slot.get("tags", []):
                    if isinstance(tag_obj, dict):
                        t_str = tag_obj.get("tag") or tag_obj.get("name") or ""
                    else:
                        t_str = str(tag_obj or "")
                    if t_str:
                        ET.SubElement(tags_elem, "tag").text = t_str

                # Logo image
                img = slot.get("image")
                if img:
                    ET.SubElement(event_elem, "logo").text = img

                # Fursonas (speakers)
                persons_elem = ET.SubElement(event_elem, "persons")
                for sp in slot.get("speakers", []):
                    sp_code = sp.get("code", "")
                    sp_name = sp.get("name", "")
                    person_item = ET.SubElement(persons_elem, "person", attrib={"id": str(sp_code)})
                    person_item.text = sp_name

                ET.SubElement(event_elem, "language").text = "en"

                # Description
                desc_text = slot.get("raw_description") or slot.get("description") or ""
                ET.SubElement(event_elem, "description").text = desc_text

                # Recording; in case we ever do that. 
                rec_elem = ET.SubElement(event_elem, "recording")
                ET.SubElement(rec_elem, "license").text = ""
                ET.SubElement(rec_elem, "optout").text = "false"

                ET.SubElement(event_elem, "links")
                ET.SubElement(event_elem, "attachments")

                # URLs
                talk_url = f"{base_url}/{event_slug}/talk/{slot_code}/"
                ET.SubElement(event_elem, "url").text = talk_url
                ET.SubElement(event_elem, "feedback_url").text = f"{talk_url}feedback/"

    ET.indent(root, space="    ")
    xml_body = ET.tostring(root, encoding="utf-8").decode("utf-8")

    xml_header = "<?xml version='1.0' encoding='utf-8' ?>\n<!-- Made with love by pretalx schedule preview. -->\n"
    return xml_header + xml_body
