"""
Copy Event Configuration Data
Copies configuration resources (rooms, tags, tracks, mail templates,
submission types, questions, speaker information) from one pretalx event
to another. Designed for recurring events that share the same structure
year after year.

Prerequisites:
  - The target event must already exist (create it via the organiser dashboard).
  - PRETALX_URL and PRETALX_APIKEY must be set in the environment or .env file.

Usage:
  python copy_event.py <source_event> <target_event> [options]

Examples:
  python copy_event.py ef28 ef29 --dry-run
  python copy_event.py ef28 ef29
  python copy_event.py ef28 ef29 --skip questions speaker-info
  python copy_event.py ef28 ef29 --only rooms tags tracks
"""

import argparse
import sys
import os

# Add parent directory to path so we can import the client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pretalx_client import PretalxClient, PretalxAPIError


# --- ANSI Color Helpers ---

def _c(code, text):
    """Wrap text in ANSI color codes."""
    return f"\033[{code}m{text}\033[0m"

def purple(text):   return _c("38;5;141", text)
def green(text):    return _c("38;5;114", text)
def cyan(text):     return _c("38;5;117", text)
def red(text):      return _c("38;5;203", text)
def yellow(text):   return _c("38;5;221", text)
def dim(text):      return _c("38;5;245", text)
def bold(text):     return _c("1", text)


# --- i18n Name Helpers ---

def _i18n_label(obj, field="name"):
    """Extract a human-readable label from an i18n field."""
    val = obj.get(field)
    if val is None:
        return dim("(unnamed)")
    if isinstance(val, dict):
        # Prefer English, then first available
        return val.get("en") or next(iter(val.values()), "(unnamed)")
    return str(val)


def _i18n_match(a, b):
    """Check if two i18n fields refer to the same thing (match on any shared locale)."""
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        for locale in a:
            if locale in b and a[locale] and b[locale] and a[locale] == b[locale]:
                return True
    return False


# --- Resource Copy Functions ---
# Each returns a dict mapping old_id -> new_id for downstream remapping.

def copy_submission_types(client, source, target, dry_run=False):
    """Copy submission types from source to target event."""
    print(f"\n{purple('━━━ Submission Types ━━━')}")
    
    source_types = list(client.list_submission_types(source))
    target_types = list(client.list_submission_types(target))
    id_map = {}
    
    if not source_types:
        print(f"  {dim('No submission types found in source event.')}")
        return id_map
    
    # Build name-based map of existing target types for dedup
    target_by_name = {}
    for t in target_types:
        name = t.get("name")
        if name:
            target_by_name[id(name)] = t  # placeholder
            for existing in target_types:
                if _i18n_match(existing.get("name"), t.get("name")):
                    target_by_name[t["id"]] = existing
    
    created = 0
    skipped = 0
    for st in source_types:
        label = _i18n_label(st)
        
        # Check if already exists in target by name match
        existing = None
        for tt in target_types:
            if _i18n_match(st.get("name"), tt.get("name")):
                existing = tt
                break
        
        if existing:
            id_map[st["id"]] = existing["id"]
            print(f"  {dim('skip')} {cyan(label)} {dim('(already exists)')}")
            skipped += 1
            continue
        
        payload = {}
        for field in ("name", "default_duration", "requires_access_code", "attendee_signup_required"):
            if field in st and st[field] is not None:
                payload[field] = st[field]
        # Skip deadline — it's date-specific
        
        if dry_run:
            print(f"  {yellow('would create')} {cyan(label)}")
            created += 1
        else:
            new = client.create_submission_type(target, payload)
            id_map[st["id"]] = new["id"]
            print(f"  {green('✓ created')} {cyan(label)}")
            created += 1
    
    _print_summary("Submission types", created, skipped, dry_run)
    return id_map


def copy_tracks(client, source, target, dry_run=False):
    """Copy tracks from source to target event."""
    print(f"\n{purple('━━━ Tracks ━━━')}")
    
    source_tracks = list(client.list_tracks(source))
    target_tracks = list(client.list_tracks(target))
    id_map = {}
    
    if not source_tracks:
        print(f"  {dim('No tracks found in source event.')}")
        return id_map
    
    created = 0
    skipped = 0
    for track in source_tracks:
        label = _i18n_label(track)
        
        # Check if already exists
        existing = None
        for tt in target_tracks:
            if _i18n_match(track.get("name"), tt.get("name")):
                existing = tt
                break
        
        if existing:
            id_map[track["id"]] = existing["id"]
            print(f"  {dim('skip')} {cyan(label)} {dim('(already exists)')}")
            skipped += 1
            continue
        
        payload = {}
        for field in ("name", "description", "color", "position", "requires_access_code", "attendee_signup_required"):
            if field in track and track[field] is not None:
                payload[field] = track[field]
        
        if dry_run:
            print(f"  {yellow('would create')} {cyan(label)}")
            created += 1
        else:
            new = client.create_track(target, payload)
            id_map[track["id"]] = new["id"]
            print(f"  {green('✓ created')} {cyan(label)}")
            created += 1
    
    _print_summary("Tracks", created, skipped, dry_run)
    return id_map


def copy_rooms(client, source, target, dry_run=False):
    """Copy rooms from source to target event."""
    print(f"\n{purple('━━━ Rooms ━━━')}")
    
    source_rooms = list(client.list_rooms(source))
    target_rooms = list(client.list_rooms(target))
    
    if not source_rooms:
        print(f"  {dim('No rooms found in source event.')}")
        return
    
    created = 0
    skipped = 0
    for room in source_rooms:
        label = _i18n_label(room)
        
        # Check if already exists
        existing = None
        for tr in target_rooms:
            if _i18n_match(room.get("name"), tr.get("name")):
                existing = tr
                break
        
        if existing:
            print(f"  {dim('skip')} {cyan(label)} {dim('(already exists)')}")
            skipped += 1
            continue
        
        payload = {}
        for field in ("name", "description", "capacity", "position", "speaker_info"):
            if field in room and room[field] is not None:
                payload[field] = room[field]
        # Skip guid — let target generate its own unique IDs
        # Skip availabilities — date-specific to each event
        
        if dry_run:
            print(f"  {yellow('would create')} {cyan(label)}")
            if room.get("capacity"):
                cap = room["capacity"]
                print(f"    {dim(f'capacity: {cap}')}")
            created += 1
        else:
            client.create_room(target, payload)
            print(f"  {green('✓ created')} {cyan(label)}")
            created += 1
    
    _print_summary("Rooms", created, skipped, dry_run)


def copy_tags(client, source, target, dry_run=False):
    """Copy tags from source to target event."""
    print(f"\n{purple('━━━ Tags ━━━')}")
    
    source_tags = list(client.list_tags(source))
    target_tags = list(client.list_tags(target))
    
    if not source_tags:
        print(f"  {dim('No tags found in source event.')}")
        return
    
    created = 0
    skipped = 0
    for tag in source_tags:
        label = tag.get("tag", "(unnamed)")
        
        # Check if already exists (tags use a simple string, not i18n)
        existing = None
        for tt in target_tags:
            if tag.get("tag") == tt.get("tag"):
                existing = tt
                break
        
        if existing:
            print(f"  {dim('skip')} {cyan(label)} {dim('(already exists)')}")
            skipped += 1
            continue
        
        payload = {}
        for field in ("tag", "description", "color", "is_public"):
            if field in tag and tag[field] is not None:
                payload[field] = tag[field]
        
        if dry_run:
            color_swatch = tag.get("color", "")
            print(f"  {yellow('would create')} {cyan(label)} {dim(color_swatch)}")
            created += 1
        else:
            client.create_tag(target, payload)
            print(f"  {green('✓ created')} {cyan(label)}")
            created += 1
    
    _print_summary("Tags", created, skipped, dry_run)


def copy_questions(client, source, target, track_map, type_map, dry_run=False):
    """Copy questions from source to target event, remapping track/type IDs."""
    print(f"\n{purple('━━━ Questions ━━━')}")
    
    # Expand options so we get the full answer option objects
    source_questions = list(client.list_questions(source, expand=["options"]))
    target_questions = list(client.list_questions(target))
    
    if not source_questions:
        print(f"  {dim('No questions found in source event.')}")
        return
    
    # Date fields to null out
    date_fields = ("deadline", "freeze_after", "min_date", "max_date", "min_datetime", "max_datetime")
    
    created = 0
    skipped = 0
    for q in source_questions:
        label = _i18n_label(q, field="question")
        variant = q.get("variant", "")
        target_type = q.get("target", "")
        
        # Check if already exists by question text match
        existing = None
        for tq in target_questions:
            if _i18n_match(q.get("question"), tq.get("question")):
                existing = tq
                break
        
        if existing:
            print(f"  {dim('skip')} {cyan(label)} {dim(f'[{variant}] (already exists)')}")
            skipped += 1
            continue
        
        payload = {}
        
        # Copy standard fields
        standard_fields = (
            "question", "help_text", "default_answer", "variant", "target",
            "question_required", "position", "min_length", "max_length",
            "min_number", "max_number", "icon", "active", "is_public",
            "contains_personal_data", "is_visible_to_reviewers",
        )
        for field in standard_fields:
            if field in q and q[field] is not None:
                payload[field] = q[field]
        
        # Null out date-specific fields
        for field in date_fields:
            if field in q and q[field] is not None:
                payload[field] = None
        
        # Remap track IDs
        if q.get("tracks"):
            remapped = []
            for old_id in q["tracks"]:
                tid = old_id
                if isinstance(old_id, dict) and "id" in old_id:
                    tid = old_id["id"]
                new_id = track_map.get(tid)
                if new_id is not None:
                    remapped.append(new_id)
            payload["tracks"] = remapped
        
        # Remap submission type IDs
        if q.get("submission_types"):
            remapped = []
            for old_id in q["submission_types"]:
                tid = old_id
                if isinstance(old_id, dict) and "id" in old_id:
                    tid = old_id["id"]
                new_id = type_map.get(tid)
                if new_id is not None:
                    remapped.append(new_id)
            payload["submission_types"] = remapped
        
        # Copy answer options (for choices / multiple_choice questions)
        if q.get("options") and isinstance(q["options"], list) and len(q["options"]) > 0:
            options_payload = []
            for opt in q["options"]:
                if isinstance(opt, dict):
                    opt_data = {}
                    if "answer" in opt:
                        opt_data["answer"] = opt["answer"]
                    if "position" in opt:
                        opt_data["position"] = opt["position"]
                    if opt_data:
                        options_payload.append(opt_data)
            if options_payload:
                payload["options"] = options_payload
        
        if dry_run:
            extra = ""
            if q.get("options") and isinstance(q["options"], list):
                extra = f" ({len(q['options'])} options)"
            print(f"  {yellow('would create')} {cyan(label)} {dim(f'[{variant}/{target_type}]{extra}')}")
            created += 1
        else:
            client.create_question(target, payload)
            print(f"  {green('✓ created')} {cyan(label)} {dim(f'[{variant}/{target_type}]')}")
            created += 1
    
    _print_summary("Questions", created, skipped, dry_run)


def copy_speaker_information(client, source, target, track_map, type_map, dry_run=False):
    """Copy speaker information from source to target event."""
    print(f"\n{purple('━━━ Speaker Information ━━━')}")
    
    source_info = list(client.list_speaker_information(source))
    target_info = list(client.list_speaker_information(target))
    
    if not source_info:
        print(f"  {dim('No speaker information found in source event.')}")
        return
    
    created = 0
    skipped = 0
    for info in source_info:
        label = _i18n_label(info, field="title")
        
        # Check if already exists
        existing = None
        for ti in target_info:
            if _i18n_match(info.get("title"), ti.get("title")):
                existing = ti
                break
        
        if existing:
            print(f"  {dim('skip')} {cyan(label)} {dim('(already exists)')}")
            skipped += 1
            continue
        
        payload = {}
        for field in ("target_group", "title", "text"):
            if field in info and info[field] is not None:
                payload[field] = info[field]
        # Skip 'resource' (file attachment) — per user decision
        
        # Remap limit_tracks
        if info.get("limit_tracks"):
            remapped = []
            for old_id in info["limit_tracks"]:
                tid = old_id
                if isinstance(old_id, dict) and "id" in old_id:
                    tid = old_id["id"]
                new_id = track_map.get(tid)
                if new_id is not None:
                    remapped.append(new_id)
            payload["limit_tracks"] = remapped
        
        # Remap limit_types
        if info.get("limit_types"):
            remapped = []
            for old_id in info["limit_types"]:
                tid = old_id
                if isinstance(old_id, dict) and "id" in old_id:
                    tid = old_id["id"]
                new_id = type_map.get(tid)
                if new_id is not None:
                    remapped.append(new_id)
            payload["limit_types"] = remapped
        
        if dry_run:
            print(f"  {yellow('would create')} {cyan(label)}")
            created += 1
        else:
            client.create_speaker_information(target, payload)
            print(f"  {green('✓ created')} {cyan(label)}")
            created += 1
    
    _print_summary("Speaker information", created, skipped, dry_run)


def copy_mail_templates(client, source, target, dry_run=False):
    """Copy mail templates from source to target event.
    
    Built-in role templates (accept, reject, etc.) are updated rather than
    created, since pretalx auto-creates them for new events.
    Custom templates (role=null) are created fresh.
    """
    print(f"\n{purple('━━━ Mail Templates ━━━')}")
    
    source_templates = list(client.list_mail_templates(source))
    target_templates = list(client.list_mail_templates(target))
    
    if not source_templates:
        print(f"  {dim('No mail templates found in source event.')}")
        return
    
    # Index target templates by role for matching built-ins
    target_by_role = {}
    for tt in target_templates:
        role = tt.get("role")
        if role:
            target_by_role[role] = tt
    
    created = 0
    updated = 0
    skipped = 0
    for tmpl in source_templates:
        role = tmpl.get("role")
        subject_label = _i18n_label(tmpl, field="subject")
        
        payload = {}
        for field in ("subject", "text", "reply_to", "bcc"):
            if field in tmpl and tmpl[field] is not None:
                payload[field] = tmpl[field]
        
        if role and role in target_by_role:
            # Built-in template: update existing in target
            target_tmpl = target_by_role[role]
            if dry_run:
                print(f"  {yellow('would update')} {cyan(role)} → {dim(subject_label)}")
                updated += 1
            else:
                client.update_mail_template(target, target_tmpl["id"], payload, partial=True)
                print(f"  {green('✓ updated')} {cyan(role)} → {dim(subject_label)}")
                updated += 1
        elif role is None:
            # Custom template: check for subject match, then create
            existing = None
            for tt in target_templates:
                if tt.get("role") is None and _i18n_match(tmpl.get("subject"), tt.get("subject")):
                    existing = tt
                    break
            
            if existing:
                print(f"  {dim('skip')} {cyan(subject_label)} {dim('(already exists)')}")
                skipped += 1
                continue
            
            if dry_run:
                print(f"  {yellow('would create')} {cyan(subject_label)} {dim('(custom)')}")
                created += 1
            else:
                client.create_mail_template(target, payload)
                print(f"  {green('✓ created')} {cyan(subject_label)} {dim('(custom)')}")
                created += 1
        else:
            # Role-based but not found in target — unusual, try creating
            if dry_run:
                print(f"  {yellow('would create')} {cyan(subject_label)} {dim(f'(role: {role})')}")
                created += 1
            else:
                try:
                    client.create_mail_template(target, payload)
                    print(f"  {green('✓ created')} {cyan(subject_label)} {dim(f'(role: {role})')}")
                    created += 1
                except PretalxAPIError as e:
                    print(f"  {red('✗ failed')} {cyan(subject_label)}: {e}")
    
    _print_summary("Mail templates", created, skipped, dry_run, updated=updated)


# --- Helpers ---

def _print_summary(resource_name, created, skipped, dry_run, updated=0):
    """Print a summary line for a resource type."""
    parts = []
    if created > 0:
        verb = "would create" if dry_run else "created"
        parts.append(f"{created} {verb}")
    if updated > 0:
        verb = "would update" if dry_run else "updated"
        parts.append(f"{updated} {verb}")
    if skipped > 0:
        parts.append(f"{skipped} skipped")
    if not parts:
        parts.append("nothing to do")
    summary = ", ".join(parts)
    print(f"  {dim('─')} {resource_name}: {bold(summary)}")


# --- Available resource types in copy order ---

RESOURCE_ORDER = [
    "submission-types",
    "tracks",
    "rooms",
    "tags",
    "questions",
    "speaker-info",
    "mail-templates",
]

RESOURCE_LABELS = {
    "submission-types": "Submission Types",
    "tracks":           "Tracks",
    "rooms":            "Rooms",
    "tags":             "Tags",
    "questions":        "Questions",
    "speaker-info":     "Speaker Information",
    "mail-templates":   "Mail Templates",
}


def main():
    parser = argparse.ArgumentParser(
        description="Copy configuration data from one pretalx event to another.",
        epilog="The target event must already exist in pretalx (create it via the dashboard first).",
    )
    parser.add_argument("source", help="Source event slug to copy FROM")
    parser.add_argument("target", help="Target event slug to copy TO")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be copied without making any changes"
    )
    parser.add_argument(
        "--skip", nargs="+", metavar="RESOURCE",
        choices=RESOURCE_ORDER,
        help=f"Skip specific resources. Choices: {', '.join(RESOURCE_ORDER)}"
    )
    parser.add_argument(
        "--only", nargs="+", metavar="RESOURCE",
        choices=RESOURCE_ORDER,
        help=f"Copy only specific resources. Choices: {', '.join(RESOURCE_ORDER)}"
    )
    
    args = parser.parse_args()
    
    if args.skip and args.only:
        parser.error("Cannot use --skip and --only together.")
    
    # Determine which resources to copy
    if args.only:
        resources = [r for r in RESOURCE_ORDER if r in args.only]
    elif args.skip:
        resources = [r for r in RESOURCE_ORDER if r not in args.skip]
    else:
        resources = list(RESOURCE_ORDER)
    
    # Initialize client
    try:
        client = PretalxClient()
    except ValueError as e:
        print(f"{red('Error:')} {e}", file=sys.stderr)
        sys.exit(1)
    
    # Validate both events exist
    try:
        source_event = client.get_event(args.source)
        source_name = _i18n_label(source_event)
    except PretalxAPIError as e:
        print(f"{red('Error:')} Source event '{args.source}' not accessible: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        target_event = client.get_event(args.target)
        target_name = _i18n_label(target_event)
    except PretalxAPIError as e:
        print(f"{red('Error:')} Target event '{args.target}' not accessible: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Header
    mode = f" {yellow('[DRY RUN]')}" if args.dry_run else ""
    print(f"\n{bold(purple('╔══════════════════════════════════════╗'))}")
    print(f"{bold(purple('║'))}  {bold('Copy Event Configuration')}{mode}  {bold(purple('║'))}")
    print(f"{bold(purple('╚══════════════════════════════════════╝'))}")
    print(f"\n  {dim('Source:')} {cyan(source_name)} {dim(f'({args.source})')}")
    print(f"  {dim('Target:')} {cyan(target_name)} {dim(f'({args.target})')}")
    print(f"  {dim('Resources:')} {', '.join(RESOURCE_LABELS.get(r, r) for r in resources)}")
    
    if args.dry_run:
        print(f"\n  {yellow('⚠ Dry run mode — no changes will be made')}")
    
    # ID remapping tables (populated by early phases, consumed by later ones)
    type_map = {}   # old submission_type_id -> new
    track_map = {}  # old track_id -> new
    
    # Execute copy in dependency order
    errors = []
    try:
        for resource in resources:
            try:
                if resource == "submission-types":
                    type_map = copy_submission_types(client, args.source, args.target, args.dry_run)
                elif resource == "tracks":
                    track_map = copy_tracks(client, args.source, args.target, args.dry_run)
                elif resource == "rooms":
                    copy_rooms(client, args.source, args.target, args.dry_run)
                elif resource == "tags":
                    copy_tags(client, args.source, args.target, args.dry_run)
                elif resource == "questions":
                    copy_questions(client, args.source, args.target, track_map, type_map, args.dry_run)
                elif resource == "speaker-info":
                    copy_speaker_information(client, args.source, args.target, track_map, type_map, args.dry_run)
                elif resource == "mail-templates":
                    copy_mail_templates(client, args.source, args.target, args.dry_run)
            except PretalxAPIError as e:
                label = RESOURCE_LABELS.get(resource, resource)
                print(f"\n  {red(f'✗ {label}:')} {e}")
                errors.append(resource)
    except KeyboardInterrupt:
        print(f"\n{yellow('Cancelled by user.')}")
        sys.exit(130)
    
    # Footer
    if errors:
        failed = ", ".join(RESOURCE_LABELS.get(r, r) for r in errors)
        print(f"\n{yellow('Completed with errors.')} Failed: {red(failed)}")
    elif args.dry_run:
        print(f"\n{yellow('Dry run complete — no changes were made.')}")
    else:
        print(f"\n{green('Done!')}")
    if not args.dry_run and not errors:
        orga_url = f"{client.site_url}/orga/event/{args.target}/"
        print(f"  {dim('Review at:')} {cyan(orga_url)}")
    print()
    
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
