#!/usr/bin/env python3

"""
push_feedback.py - Import app-collected feedback into Pretalx.

Reads a JSON file produced by the feedback app and POSTs each entry to the
Pretalx feedback endpoint.  Duplicate prevention works by embedding the
source feedback UUID in the review text; any existing feedback for the same
submission is scanned first and entries whose review already contains the
UUID are skipped.

Usage:
    python3 push_feedback.py <feedback_file.json> [--dry-run]

Environment variables (or .env):
    PRETALX_URL        - Base URL of the Pretalx instance
    PRETALX_APIKEY     - API token
    PRETALX_EVENT_SLUG - Event slug to submit feedback against
"""

import sys
import json
import os
import argparse
from collections.abc import Mapping

from pretalx_client import PretalxClient, PretalxNotFoundError, PretalxAPIError, load_env

# ---------------------------------------------------------------------------
# ANSI colours (matches project conventions: purple/green/cyan/red)
# ---------------------------------------------------------------------------
_C = {
    "reset":  "\033[0m",
    "purple": "\033[95m",
    "green":  "\033[92m",
    "cyan":   "\033[96m",
    "yellow": "\033[93m",
    "red":    "\033[91m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
}

# Unicode symbols extracted as constants to avoid backslash-in-f-string issues
_SYM_BAR     = "\u2501" * 60   # ━━━━...
_SYM_OK      = "\u2714"         # ✔
_SYM_ERR     = "\u2717"         # ✗
_SYM_WARN    = "\u26a0"         # ⚠
_SYM_SKIP    = "\u2298"         # ⊘
_SYM_ARROW   = "\u2192"         # →
_SYM_ELLIP   = "\u2026"         # …
_SYM_DASH    = "\u2013"         # –


def _c(color, text):
    return f"{_C.get(color, '')}{text}{_C['reset']}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rating_stars(rating):
    """Convert a 0-5 integer rating to an emoji star string."""
    try:
        n = int(round(float(rating)))
        n = max(0, min(5, n))
    except (TypeError, ValueError):
        return ""
    filled = "\u2b50" * n        # ⭐
    empty  = "\u2606" * (5 - n)  # ☆
    return filled + empty + "  (" + str(n) + "/5)"


def build_review(entry):
    """
    Compose the full review text that will be sent to Pretalx.

    Format:
        ⭐⭐⭐⭐⭐  (5/5)

        <original message>

        ---
        Source ID: <uuid>
    """
    parts = []

    rating = entry.get("Rating")
    if rating is not None:
        parts.append(rating_stars(rating))
        parts.append("")  # blank line after stars

    message = entry.get("Message") or ""
    if message:
        parts.append(message)

    parts.append("")
    parts.append("---")
    parts.append("Source ID: " + entry["Id"])

    return "\n".join(parts)


def _remove_trailing_commas(raw):
    """Remove trailing JSON commas without changing quoted string content."""
    cleaned = []
    in_string = False
    escaped = False

    for index, char in enumerate(raw):
        if in_string:
            cleaned.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == ",":
            next_index = index + 1
            while next_index < len(raw) and raw[next_index].isspace():
                next_index += 1
            if next_index < len(raw) and raw[next_index] in "}]":
                continue
        cleaned.append(char)

    return "".join(cleaned)


def load_feedback_file(path):
    """Load and parse the JSON feedback file.

    The feedback app may emit trailing commas (e.g. the last element of the
    array is followed by a comma before the closing bracket).  Python's
    json module is strict about this, so we strip trailing commas from
    objects and arrays before parsing.
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    cleaned = _remove_trailing_commas(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("JSON parse error: " + str(exc)) from exc
    if not isinstance(data, list):
        raise ValueError(
            "Expected a JSON array at the top level, got " + type(data).__name__ + "."
        )
    for index, entry in enumerate(data):
        if not isinstance(entry, Mapping):
            raise ValueError(
                "Feedback entry " + str(index) + " must be a JSON object."
            )
        for field in ("Id", "EventSlug"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    "Feedback entry " + str(index) + " must have a non-empty string " + field + "."
                )
    return data


def already_submitted(existing_reviews, source_id):
    """Return True if any existing review text contains the source UUID."""
    marker = "Source ID: " + source_id
    return any(marker in (fb.get("review") or "") for fb in existing_reviews)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_env()

    parser = argparse.ArgumentParser(
        description="Push app-collected feedback into Pretalx.",
    )
    parser.add_argument(
        "file",
        metavar="FILE",
        help="Path to the JSON feedback file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the file but do not push anything to Pretalx.",
    )
    args = parser.parse_args()

    # -- Validate file -------------------------------------------------------
    if not os.path.isfile(args.file):
        print(_c("red", _SYM_ERR + " File not found: " + args.file))
        sys.exit(1)

    try:
        entries = load_feedback_file(args.file)
    except (json.JSONDecodeError, ValueError) as exc:
        print(_c("red", _SYM_ERR + " Failed to parse feedback file: " + str(exc)))
        sys.exit(1)

    if not entries:
        print(_c("yellow", _SYM_WARN + " Feedback file contains no entries."))
        sys.exit(0)

    # -- Resolve event slug --------------------------------------------------
    event_slug = os.environ.get("PRETALX_EVENT_SLUG", "").strip()
    if not event_slug:
        print(_c("red", _SYM_ERR + " PRETALX_EVENT_SLUG is not set in environment/.env."))
        sys.exit(1)

    # -- Banner --------------------------------------------------------------
    print()
    print(_c("purple", _SYM_BAR))
    print(_c("purple", "  Push Feedback " + _SYM_ARROW + " Pretalx"))
    print(_c("purple", _SYM_BAR))
    print("  " + _c("dim", "Event   :") + " " + _c("cyan", event_slug))
    print("  " + _c("dim", "File    :") + " " + _c("cyan", args.file))
    print("  " + _c("dim", "Entries :") + " " + _c("cyan", str(len(entries))))
    if args.dry_run:
        print("  " + _c("yellow", _SYM_WARN + " DRY-RUN mode " + _SYM_DASH + " nothing will be written to Pretalx"))
    print(_c("purple", _SYM_BAR))
    print()

    if args.dry_run:
        for entry in entries:
            sub_code = entry.get("EventSlug", "").strip()
            review   = build_review(entry)
            rating   = entry.get("Rating")
            src_id   = entry.get("Id")
            print(_c("cyan", "  [" + sub_code + "]") + "  Id=" + str(src_id) + "  Rating=" + str(rating))
            print(_c("dim", "  " + review.replace("\n", "\n  ")))
            print()
        count = len(entries)
        noun  = "entry" if count == 1 else "entries"
        print(_c("green", _SYM_OK + " Dry-run complete. " + str(count) + " " + noun + " would be processed."))
        return

    # -- Initialise client ---------------------------------------------------
    try:
        client = PretalxClient()
    except ValueError as exc:
        print(_c("red", _SYM_ERR + " Configuration error: " + str(exc)))
        sys.exit(1)

    # -- Fetch existing feedback per submission for deduplication ------------
    # Lazily populated: submission_code -> [feedback_dict, ...] or None on failure
    existing_cache = {}

    def get_existing(sub_code):
        if sub_code not in existing_cache:
            try:
                existing_cache[sub_code] = list(
                    client.list_feedback(event_slug, submission=sub_code)
                )
            except PretalxAPIError as exc:
                print("  " + _c("yellow", _SYM_WARN + " Could not fetch existing feedback for " + sub_code + ": " + str(exc)))
                existing_cache[sub_code] = None
        return existing_cache[sub_code]

    # -- Process entries -----------------------------------------------------
    stats = {"pushed": 0, "skipped_duplicate": 0, "skipped_error": 0}

    for entry in entries:
        source_id = entry.get("Id", "")
        sub_code  = (entry.get("EventSlug") or "").strip()

        prefix = "  [" + _c("cyan", sub_code) + "]"

        if not sub_code:
            print(prefix + " " + _c("yellow", _SYM_WARN + " Missing EventSlug " + _SYM_DASH + " skipping."))
            stats["skipped_error"] += 1
            continue

        if not source_id:
            print(prefix + " " + _c("yellow", _SYM_WARN + " Missing Id " + _SYM_DASH + " skipping (cannot guarantee idempotency)."))
            stats["skipped_error"] += 1
            continue

        # Deduplication check
        existing = get_existing(sub_code)
        if existing is None:
            print(prefix + " " + _c("red", _SYM_ERR + " Duplicate check failed " + _SYM_DASH + " skipping."))
            stats["skipped_error"] += 1
            continue
        if already_submitted(existing, source_id):
            short_id = source_id[:8] + _SYM_ELLIP
            print(prefix + " " + _c("dim", "already imported (" + short_id + ") " + _SYM_DASH + " skip"))
            stats["skipped_duplicate"] += 1
            continue

        review = build_review(entry)

        try:
            result = client.create_feedback(
                event_slug=event_slug,
                submission=sub_code,
                review=review,
            )
            fb_id     = result.get("id", "?")
            short_id  = source_id[:8] + _SYM_ELLIP
            print(prefix + " " + _c("green", _SYM_OK) + " pushed  (pretalx id=" + str(fb_id) + ", source=" + short_id + ")")
            # Cache newly created entry so duplicates within the same file
            # are caught without an additional API round-trip
            existing_cache[sub_code].append(result)
            stats["pushed"] += 1
        except PretalxNotFoundError:
            print(prefix + " " + _c("red", _SYM_ERR) + " submission not found in event " + _SYM_DASH + " skipping.")
            stats["skipped_error"] += 1
        except PretalxAPIError as exc:
            print(prefix + " " + _c("red", _SYM_ERR) + " API error: " + str(exc))
            stats["skipped_error"] += 1

    # -- Summary -------------------------------------------------------------
    print()
    print(_c("purple", _SYM_BAR))
    print("  " + _c("green",  _SYM_OK + " Pushed   :") + " " + str(stats["pushed"]))
    print("  " + _c("dim",    _SYM_SKIP + " Skipped  :") + " " + str(stats["skipped_duplicate"]) + "  (already imported)")
    if stats["skipped_error"]:
        print("  " + _c("red", _SYM_ERR + " Errors   :") + " " + str(stats["skipped_error"]))
    print(_c("purple", _SYM_BAR))
    print()

    if stats["skipped_error"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
