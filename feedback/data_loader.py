"""
data_loader.py — Load, parse, and aggregate convention feedback, occupancy, and event details.
"""

import os
import json
import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def get_data_dir() -> str:
    """Resolve the directory containing feedback/, occupancy/, and events/ subfolders."""
    if os.environ.get("DATA_DIR"):
        return os.environ["DATA_DIR"]
    # Check if running in container with /data mounted
    if os.path.isdir("/data/feedback"):
        return "/data"
    # Local path relative to feedback package
    local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    if os.path.isdir(local_dir):
        return local_dir
    parent_data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    if os.path.isdir(parent_data):
        return parent_data
    return "data"


def list_conventions() -> List[Dict[str, Any]]:
    """
    List all available conventions based on files in data/feedback/*.json.
    
    Returns list of convention metadata dicts sorted with newest first.
    """
    data_dir = get_data_dir()
    feedback_dir = os.path.join(data_dir, "feedback")
    if not os.path.isdir(feedback_dir):
        logger.warning("Feedback directory not found: %s", feedback_dir)
        return []

    conventions = []
    for fname in os.listdir(feedback_dir):
        if not fname.endswith(".json") or fname.startswith("."):
            continue
        con_id = fname[:-5]  # e.g. "ef_30"

        m = re.match(r"^ef_?(\d+)$", con_id, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            display_name = f"EF {num}"
            sort_key = (num, con_id)
        else:
            display_name = con_id.replace("_", " ").upper()
            sort_key = (-1, con_id)

        events_path = os.path.join(data_dir, "events", f"{con_id}.json")
        occ_path = os.path.join(data_dir, "occupancy", f"{con_id}.json")

        has_events = os.path.isfile(events_path)
        has_occ = os.path.isfile(occ_path)

        event_title = None
        if has_events:
            try:
                with open(events_path, "r", encoding="utf-8") as f:
                    ev_info = json.load(f).get("event", {})
                    event_title = ev_info.get("name")
            except Exception as e:
                logger.warning("Could not read event metadata from %s: %s", events_path, e)

        conventions.append({
            "id": con_id,
            "name": display_name,
            "title": event_title or display_name,
            "has_events": has_events,
            "has_occupancy": has_occ,
            "_sort_key": sort_key,
        })

    # Sort descending by convention number (e.g. EF 30, EF 29, EF 28)
    conventions.sort(key=lambda c: c["_sort_key"], reverse=True)
    for c in conventions:
        del c["_sort_key"]

    return conventions


def load_convention_data(con_id: str) -> Optional[Dict[str, Any]]:
    """
    Load feedback, occupancy, and event details for a given convention ID.
    Groups feedback items by EventSlug and enriches with title, track, slots, and occupancy.
    """
    data_dir = get_data_dir()
    feedback_path = os.path.join(data_dir, "feedback", f"{con_id}.json")
    if not os.path.isfile(feedback_path):
        return None

    try:
        with open(feedback_path, "r", encoding="utf-8") as f:
            feedback_raw = json.load(f)
    except Exception as e:
        logger.error("Error reading feedback file %s: %s", feedback_path, e)
        return None

    events_path = os.path.join(data_dir, "events", f"{con_id}.json")
    events_data = {}
    if os.path.isfile(events_path):
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                events_data = json.load(f).get("submissions", {})
        except Exception as e:
            logger.error("Error reading events file %s: %s", events_path, e)

    occ_path = os.path.join(data_dir, "occupancy", f"{con_id}.json")
    occ_data = {}
    if os.path.isfile(occ_path):
        try:
            with open(occ_path, "r", encoding="utf-8") as f:
                occ_data = json.load(f)
        except Exception as e:
            logger.error("Error reading occupancy file %s: %s", occ_path, e)

    # Group feedback by EventSlug
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in feedback_raw:
        slug = str(item.get("EventSlug") or "").strip()
        if not slug:
            continue
        if slug not in grouped:
            grouped[slug] = []

        rating = item.get("Rating")
        if rating is not None:
            try:
                rating = int(round(float(rating)))
            except (ValueError, TypeError):
                rating = None

        raw_msg = item.get("Message")
        if raw_msg is None or str(raw_msg).strip() in ("", "NULL"):
            msg = None
        else:
            msg = str(raw_msg).strip()

        grouped[slug].append({
            "id": item.get("Id") or "",
            "rating": rating,
            "message": msg,
            "date": item.get("LastChangeDateTimeUtc") or "",
            "source_id": item.get("EventSourceId") or "",
        })

    tracks_map = {}
    event_list = []
    total_feedbacks = 0
    total_comments = 0
    all_ratings = []

    for slug, fb_items in grouped.items():
        # Sort feedback items: most recent date first
        fb_items.sort(key=lambda x: x.get("date") or "", reverse=True)

        # Submission metadata (if available)
        sub = events_data.get(slug)
        title = None
        track = None
        submission_type = None
        abstract = None
        slots = []

        if sub:
            title = sub.get("title")
            sub_track = sub.get("track")
            if isinstance(sub_track, dict) and sub_track.get("name"):
                track = {
                    "name": sub_track.get("name"),
                    "color": sub_track.get("color") or "#666666",
                }
                tracks_map[track["name"]] = track
            submission_type = sub.get("submission_type")
            abstract = sub.get("abstract")
            slots = sub.get("slots", [])

        # Fallback title if events details not available (EF 28, EF 29)
        if not title:
            if "_" in slug:
                title = slug.replace("_", " ").title()
            else:
                title = slug

        # Occupancy matching
        occupancy_info = None
        if occ_data:
            # 1. Match against source_ids from feedback items
            for it in fb_items:
                sid = it.get("source_id")
                if sid and sid in occ_data:
                    occupancy_info = occ_data[sid]
                    break
            # 2. Match against any slot
            if not occupancy_info and slots:
                for slot in slots:
                    idx = slot.get("slot_index", 0)
                    key = f"{slug}-{idx}"
                    if key in occ_data:
                        occupancy_info = occ_data[key]
                        break
            # 3. Match against default "{slug}-0"
            if not occupancy_info and f"{slug}-0" in occ_data:
                occupancy_info = occ_data[f"{slug}-0"]

        occ_obj = None
        if occupancy_info:
            occ_obj = {
                "rating": occupancy_info.get("rating"),
                "level": occupancy_info.get("level"),
                "room": occupancy_info.get("conference_room"),
                "day": occupancy_info.get("day"),
                "start_time": occupancy_info.get("start_time"),
            }

        # Compute stats for this event
        ratings = [it["rating"] for it in fb_items if it["rating"] is not None]
        all_ratings.extend(ratings)
        comments = [it for it in fb_items if it["message"]]
        total_feedbacks += len(fb_items)
        total_comments += len(comments)

        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
        rating_dist = {str(i): ratings.count(i) for i in range(1, 6)}

        event_list.append({
            "event_slug": slug,
            "title": title,
            "track": track,
            "submission_type": submission_type,
            "abstract": abstract,
            "slots": [
                {
                    "slot_index": s.get("slot_index", 0),
                    "start": s.get("start"),
                    "end": s.get("end"),
                    "room_name": s.get("room_name"),
                }
                for s in slots
            ],
            "occupancy": occ_obj,
            "feedback_count": len(fb_items),
            "comments_count": len(comments),
            "avg_rating": avg_rating,
            "rating_dist": rating_dist,
            "feedbacks": fb_items,
        })

    # Default sort: highest feedback count first, then highest rating, then title
    event_list.sort(key=lambda e: (
        -e["feedback_count"],
        -(e["avg_rating"] or 0),
        e["title"].lower(),
    ))

    overall_avg = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else None

    m = re.match(r"^ef_?(\d+)$", con_id, re.IGNORECASE)
    con_name = f"EF {m.group(1)}" if m else con_id.replace("_", " ").upper()

    return {
        "convention": {
            "id": con_id,
            "name": con_name,
            "has_events": bool(events_data),
            "has_occupancy": bool(occ_data),
            "tracks": sorted(list(tracks_map.values()), key=lambda t: t["name"]),
        },
        "stats": {
            "total_events": len(event_list),
            "total_feedbacks": total_feedbacks,
            "total_comments": total_comments,
            "avg_rating": overall_avg,
        },
        "events": event_list,
    }


def load_occupancies_data(con_id: str) -> Optional[Dict[str, Any]]:
    """
    Load all occupancy ratings for a convention, enriched with event details
    (title, track, room) and feedback summary if available.
    """
    data_dir = get_data_dir()
    occ_path = os.path.join(data_dir, "occupancy", f"{con_id}.json")
    feedback_path = os.path.join(data_dir, "feedback", f"{con_id}.json")
    events_path = os.path.join(data_dir, "events", f"{con_id}.json")

    # Verify if convention exists anywhere
    if not os.path.isfile(occ_path) and not os.path.isfile(feedback_path) and not os.path.isfile(events_path):
        return None

    m = re.match(r"^ef_?(\d+)$", con_id, re.IGNORECASE)
    con_name = f"EF {m.group(1)}" if m else con_id.replace("_", " ").upper()

    if not os.path.isfile(occ_path):
        return {
            "convention": {
                "id": con_id,
                "name": con_name,
                "has_occupancy": False,
                "has_events": os.path.isfile(events_path),
                "tracks": [],
                "rooms": [],
                "days": [],
            },
            "stats": {
                "total_rated": 0,
                "avg_level": None,
                "distribution": {"Empty": 0, "Low": 0, "Medium": 0, "High": 0, "Full": 0},
                "high_full_count": 0,
                "total_rooms": 0,
            },
            "items": [],
        }

    try:
        with open(occ_path, "r", encoding="utf-8") as f:
            occ_data = json.load(f)
    except Exception as e:
        logger.error("Error reading occupancy file %s: %s", occ_path, e)
        return None

    # Load events for metadata enrichment
    events_data = {}
    if os.path.isfile(events_path):
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                events_data = json.load(f).get("submissions", {})
        except Exception as e:
            logger.error("Error reading events file %s: %s", events_path, e)

    # Load feedback for cross-reference stats
    feedback_by_code: Dict[str, List[int]] = {}
    if os.path.isfile(feedback_path):
        try:
            with open(feedback_path, "r", encoding="utf-8") as f:
                fb_raw = json.load(f)
                for it in fb_raw:
                    s = it.get("EventSlug")
                    if s:
                        r = it.get("Rating")
                        if r is not None:
                            try:
                                r = int(round(float(r)))
                            except (ValueError, TypeError):
                                r = None
                        feedback_by_code.setdefault(s, []).append(r)
        except Exception as e:
            logger.error("Error reading feedback file %s: %s", feedback_path, e)

    # Process items
    items = []
    distribution = {"Empty": 0, "Low": 0, "Medium": 0, "High": 0, "Full": 0}
    unique_rooms = set()
    unique_days = set()
    tracks_map = {}
    total_levels = 0

    for key, val in occ_data.items():
        parts = key.split("-")
        code = parts[0]
        slot_idx = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

        rating_raw = str(val.get("rating") or "Unknown").capitalize()
        level = val.get("level")
        if level is not None:
            try:
                level = int(level)
            except (ValueError, TypeError):
                level = 0
        else:
            level_map = {"Empty": 0, "Low": 1, "Medium": 2, "High": 3, "Full": 4}
            level = level_map.get(rating_raw, 0)

        # Normalize rating label
        if rating_raw in distribution:
            rating_label = rating_raw
        else:
            if level == 0:
                rating_label = "Empty"
            elif level == 1:
                rating_label = "Low"
            elif level == 2:
                rating_label = "Medium"
            elif level == 3:
                rating_label = "High"
            else:
                rating_label = "Full"

        distribution[rating_label] = distribution.get(rating_label, 0) + 1
        total_levels += level

        room = val.get("conference_room") or ""
        if room:
            unique_rooms.add(room)

        day = val.get("day") or ""
        if day:
            unique_days.add(day)

        start_time = val.get("start_time") or ""

        # Enrich with events metadata
        sub = events_data.get(code, {})
        title = val.get("title") or sub.get("title") or code
        abstract = sub.get("abstract")
        submission_type = sub.get("submission_type")
        track_obj = None
        sub_track = sub.get("track")
        if isinstance(sub_track, dict) and sub_track.get("name"):
            track_obj = {
                "name": sub_track.get("name"),
                "color": sub_track.get("color") or "#666666",
            }
            tracks_map[track_obj["name"]] = track_obj

        # Feedback summary
        fb_ratings = feedback_by_code.get(code, [])
        valid_ratings = [r for r in fb_ratings if r is not None]
        avg_fb = round(sum(valid_ratings) / len(valid_ratings), 1) if valid_ratings else None

        items.append({
            "key": key,
            "code": code,
            "slot_index": slot_idx,
            "title": title,
            "rating": rating_label,
            "level": level,
            "room": room,
            "day": day,
            "start_time": start_time,
            "track": track_obj,
            "abstract": abstract,
            "submission_type": submission_type,
            "feedback_count": len(fb_ratings),
            "feedback_avg_rating": avg_fb,
        })

    # Sort items: by level descending (Full/High first), then day, time, title
    items.sort(key=lambda x: (
        -x["level"],
        x["day"] or "9999",
        x["start_time"] or "9999",
        x["title"].lower(),
    ))

    avg_level = round(total_levels / len(items), 2) if items else None
    high_full_count = distribution.get("High", 0) + distribution.get("Full", 0)

    return {
        "convention": {
            "id": con_id,
            "name": con_name,
            "has_occupancy": True,
            "has_events": bool(events_data),
            "tracks": sorted(list(tracks_map.values()), key=lambda t: t["name"]),
            "rooms": sorted(list(unique_rooms)),
            "days": sorted(list(unique_days)),
        },
        "stats": {
            "total_rated": len(items),
            "avg_level": avg_level,
            "distribution": distribution,
            "high_full_count": high_full_count,
            "total_rooms": len(unique_rooms),
        },
        "items": items,
    }
