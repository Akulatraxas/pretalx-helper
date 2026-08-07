#!/usr/bin/env python3
"""
Pretalx Submission Tag Automation CLI Utility
Mass sets or removes tags on submissions depending on answers to specific event questions.
"""

import os
import sys
import argparse
from pretalx_client import PretalxClient, PretalxAPIError

# --- ANSI Color Helpers ---

def _c(code, text):
    """Wrap text in ANSI color codes."""
    return f"\033[{code}m{text}\033[0m"

def purple(text):  
    """Wrap text in purple ANSI color."""
    return _c("38;5;141", text)

def green(text):   
    """Wrap text in green ANSI color."""
    return _c("38;5;114", text)

def cyan(text):    
    """Wrap text in cyan ANSI color."""
    return _c("38;5;117", text)

def red(text):     
    """Wrap text in red ANSI color."""
    return _c("38;5;203", text)

def yellow(text):  
    """Wrap text in yellow ANSI color."""
    return _c("38;5;221", text)

def dim(text):     
    """Wrap text in dimmed grey ANSI color."""
    return _c("38;5;245", text)

def bold(text):    
    """Wrap text in bold ANSI formatting."""
    return _c("1", text)


# --- Predefined Mappings ---

DEFAULT_MAPPINGS = {
    "ef_feedback": {
        "name": "ef_feedback",
        "description": "Sets ef_feedback tag for submissions opting into feedback collection (defaults to yes).",
        "question": 4,  # Question ID or title ("Feedback Collection")
        "tag": 41,      # Tag ID or name ("ef_feedback")
        "add_on_answers": ["Yes", "yes", "true", "True", "1"],
        "remove_on_answers": ["No", "no", "false", "False", "2"],
        "on_missing": "add",  # "add", "remove", or "skip" (Help text: "If not specified we assume yes")
    }
}


def extract_i18n_text(val):
    """Extract human-readable string from localized dict or string."""
    if val is None:
        return ""
    if isinstance(val, dict):
        return val.get("en") or next(iter(val.values()), "")
    return str(val)


def resolve_question_answer(sub, question_obj):
    """
    Retrieves the answer object and normalized answer string/option IDs for a submission and question.
    Returns (answer_record, answer_str, option_ids_list)
    """
    q_id = question_obj.get("id")
    q_identifier = str(question_obj.get("identifier", "")).lower()
    q_text = extract_i18n_text(question_obj.get("question")).lower()

    for ans in sub.get("answers", []):
        ans_q = ans.get("question")
        ans_q_id = ans_q.get("id") if isinstance(ans_q, dict) else ans_q
        ans_q_text = extract_i18n_text(ans_q.get("question") if isinstance(ans_q, dict) else None).lower()

        if ans_q_id == q_id or (ans_q_text and ans_q_text == q_text):
            answer_str = str(ans.get("answer") or "").strip()
            options = ans.get("options") or []
            return ans, answer_str, options
    return None, None, []


def process_mapping(client, event_slug, mapping, target_submission=None, dry_run=False, verbose=False):
    """
    Executes a single question -> tag mapping rule across submissions in the event.
    Optionally limits processing to a specific submission code.
    """
    rule_name = mapping.get("name", "custom")
    q_spec = mapping["question"]
    t_spec = mapping["tag"]
    add_answers = [str(a).strip().lower() for a in mapping.get("add_on_answers", [])]
    remove_answers = [str(a).strip().lower() for a in mapping.get("remove_on_answers", [])]
    on_missing = mapping.get("on_missing", "skip").lower()

    print(f"\n{purple(bold('=== Rule Execution: ' + rule_name + ' ==='))}")
    print(f"Resolving tag and question resources for event {cyan(bold(event_slug))}...")

    # 1. Fetch tags first to locate target tag ID and metadata
    all_tags = list(client.list_tags(event_slug))
    tag_obj = None
    if isinstance(t_spec, int) or (isinstance(t_spec, str) and t_spec.isdigit()):
        tag_obj = next((t for t in all_tags if t.get("id") == int(t_spec)), None)
    if not tag_obj:
        target_str = str(t_spec).strip().lower()
        for t in all_tags:
            t_name = str(t.get("tag") or "").strip().lower()
            if t_name == target_str or str(t.get("id")) == target_str:
                tag_obj = t
                break

    if not tag_obj:
        print(f"{red(bold('Error:'))} Could not find tag {cyan(str(t_spec))} in event {cyan(event_slug)}.")
        return False

    tag_id = tag_obj["id"]
    tag_name = tag_obj.get("tag") or str(tag_id)
    print(f"✓ Target Tag resolved: {cyan(bold(tag_name))} (ID: {bold(str(tag_id))})")

    # 2. Fetch question to locate metadata and option mappings
    all_questions = list(client.list_questions(event_slug, expand=["options"]))
    q_obj = None
    if isinstance(q_spec, int) or (isinstance(q_spec, str) and q_spec.isdigit()):
        q_obj = next((q for q in all_questions if q.get("id") == int(q_spec)), None)
    if not q_obj:
        target_str = str(q_spec).strip().lower()
        for q in all_questions:
            q_title = extract_i18n_text(q.get("question")).strip().lower()
            if q_title == target_str or str(q.get("identifier", "")).lower() == target_str:
                q_obj = q
                break

    if not q_obj:
        print(f"{red(bold('Error:'))} Could not find question {cyan(str(q_spec))} in event {cyan(event_slug)}.")
        return False

    q_id = q_obj["id"]
    q_title = extract_i18n_text(q_obj.get("question"))
    print(f"✓ Target Question resolved: {cyan(bold(q_title))} (ID: {bold(str(q_id))})")
    print(f"  Add tag on answers:    {green(', '.join(add_answers))}")
    print(f"  Remove tag on answers: {yellow(', '.join(remove_answers))}")
    print(f"  On missing answer:     {cyan(on_missing.upper())}")

    # 3. Fetch submission(s) with expanded answers & tags
    if target_submission:
        print(f"\nFetching specific submission {cyan(bold(target_submission))} for event {cyan(bold(event_slug))}...")
        try:
            sub = client.get_submission(event_slug, target_submission, expand=["answers", "tags"])
            submissions = [sub]
        except PretalxAPIError as e:
            print(f"{red(bold('Error:'))} Failed to fetch submission {cyan(target_submission)}: {e}")
            return False
    else:
        print(f"\nFetching submissions for event {cyan(bold(event_slug))}...")
        submissions = list(client.list_submissions(event_slug, expand=["answers", "tags"]))
        print(f"Loaded {bold(str(len(submissions)))} submissions.")

    stats = {
        "added": 0,
        "removed": 0,
        "already_correct": 0,
        "errors": 0,
    }

    print(f"\n{bold('Evaluating submissions...')}")
    for sub in submissions:
        code = sub["code"]
        title = sub.get("title") or "(Untitled)"

        # Normalize existing submission tag IDs
        existing_tags = sub.get("tags", [])
        existing_tag_ids = [t["id"] if isinstance(t, dict) and "id" in t else t for t in existing_tags]
        has_tag = tag_id in existing_tag_ids

        # Retrieve answer for this question
        ans_record, ans_str, opt_ids = resolve_question_answer(sub, q_obj)

        desired_action = "keep"  # "add", "remove", or "keep"

        if ans_str is not None:
            ans_clean = ans_str.strip().lower()
            opt_strs = [str(o) for o in opt_ids]

            # Check if answer matches add criteria
            if ans_clean in add_answers or any(o in add_answers for o in opt_strs):
                desired_action = "add"
            elif ans_clean in remove_answers or any(o in remove_answers for o in opt_strs):
                desired_action = "remove"
            else:
                # Unrecognized specific answer, default to missing policy or keep
                desired_action = "add" if on_missing == "add" else ("remove" if on_missing == "remove" else "keep")
        else:
            # Submission has no explicit answer for this question
            if on_missing == "add":
                desired_action = "add"
            elif on_missing == "remove":
                desired_action = "remove"
            else:
                desired_action = "keep"

        # Determine required state change
        needs_add = (desired_action == "add" and not has_tag)
        needs_remove = (desired_action == "remove" and has_tag)

        if needs_add:
            target_tag_ids = existing_tag_ids + [tag_id]
            msg = f"Adding tag '{tag_name}'"
        elif needs_remove:
            target_tag_ids = [t for t in existing_tag_ids if t != tag_id]
            msg = f"Removing tag '{tag_name}'"
        else:
            target_tag_ids = existing_tag_ids
            stats["already_correct"] += 1
            if verbose or target_submission:
                ans_display = f"'{ans_str}'" if ans_str is not None else "<NO_ANSWER>"
                print(f"  {dim(code)}: Tag status OK (has_tag={has_tag}, ans={ans_display})")
            continue

        ans_display = f"'{ans_str}'" if ans_str is not None else "<NO_ANSWER>"
        prefix = "[DRY-RUN] " if dry_run else ""

        if needs_add:
            color_fn = green
            action_label = "+ ADD"
        else:
            color_fn = yellow
            action_label = "- REMOVE"

        print(f"  {bold(code)}: {color_fn(action_label)} tag '{tag_name}' ({prefix}ans={ans_display}) - Title: {dim(title[:50])}")

        if not dry_run:
            try:
                client.update_submission_tags(event_slug, code, target_tag_ids)
                if needs_add:
                    stats["added"] += 1
                if needs_remove:
                    stats["removed"] += 1
            except PretalxAPIError as e:
                stats["errors"] += 1
                print(f"    {red('ERROR updating submission')} {code}: {e}")
        else:
            if needs_add:
                stats["added"] += 1
            if needs_remove:
                stats["removed"] += 1

    # Output rule summary
    dry_prefix = f" {yellow('[DRY-RUN mode - no changes saved]')}" if dry_run else ""
    print(f"\n{bold('--- Rule Summary ---')}{dry_prefix}")
    print(f"  Total Submissions: {len(submissions)}")
    print(f"  Tags Added:        {green(bold(str(stats['added'])))}")
    print(f"  Tags Removed:      {yellow(bold(str(stats['removed'])))}")
    print(f"  Unchanged / OK:    {dim(str(stats['already_correct']))}")
    if stats["errors"] > 0:
        print(f"  Errors:            {red(bold(str(stats['errors'])))}")

    return stats["errors"] == 0


def main():
    """Main CLI entry point for Pretalx mass submission tag manager."""
    parser = argparse.ArgumentParser(
        description="Mass set or remove submission tags in Pretalx based on question answers."
    )
    parser.add_argument(
        "--event",
        help="Target event slug (e.g. eurofurence-30-2026). Defaults to PRETALX_EVENT_SLUG in environment/.env."
    )
    parser.add_argument(
        "-s", "--submission", "--code",
        dest="submission",
        help="Optional submission code to target a single submission (e.g. 38QWND). Default: process all submissions."
    )
    parser.add_argument(
        "-q", "--question",
        default="4",
        help="Question ID or title text (default: 4 / 'Feedback Collection')."
    )
    parser.add_argument(
        "-t", "--tag",
        default="41",
        help="Tag ID or tag name (default: 41 / 'ef_feedback')."
    )
    parser.add_argument(
        "--add-on-answers",
        nargs="+",
        default=["Yes", "yes", "true", "True", "1"],
        help="Answer values or option IDs that trigger ADDING the tag (default: Yes yes true True 1)."
    )
    parser.add_argument(
        "--remove-on-answers",
        nargs="+",
        default=["No", "no", "false", "False", "2"],
        help="Answer values or option IDs that trigger REMOVING the tag (default: No no false False 2)."
    )
    parser.add_argument(
        "--on-missing",
        choices=["add", "remove", "skip"],
        default="add",
        help="Action when a submission has no explicit answer for the question (default: add, matching Q4 policy)."
    )
    parser.add_argument(
        "--mapping-name",
        choices=list(DEFAULT_MAPPINGS.keys()),
        help="Select a predefined mapping by name."
    )
    parser.add_argument(
        "--all-mappings",
        action="store_true",
        help="Execute all predefined question -> tag mappings."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview tag changes without writing updates to Pretalx."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed evaluation status for all submissions."
    )

    args = parser.parse_args()

    print(f"{green(bold('Pretalx Mass Tag Manager'))}")
    print("Connecting to Pretalx API...")

    try:
        client = PretalxClient()
    except Exception as e:
        print(f"{red(bold('Initialization Error:'))} {e}")
        print("Ensure PRETALX_URL and PRETALX_APIKEY are defined in your .env file or environment.")
        sys.exit(1)

    event_slug = args.event or os.environ.get("PRETALX_EVENT_SLUG")
    if not event_slug:
        print(f"{red(bold('Error:'))} Event slug not specified. Pass --event or set PRETALX_EVENT_SLUG in .env.")
        sys.exit(1)

    print(f"✓ Connected to API site: {bold(client.site_url)}")

    mappings_to_run = []

    if args.all_mappings:
        mappings_to_run = list(DEFAULT_MAPPINGS.values())
    elif args.mapping_name:
        mappings_to_run = [DEFAULT_MAPPINGS[args.mapping_name]]
    else:
        # Custom mapping built from CLI parameters
        custom_mapping = {
            "name": f"q_{args.question}_tag_{args.tag}",
            "question": int(args.question) if args.question.isdigit() else args.question,
            "tag": int(args.tag) if args.tag.isdigit() else args.tag,
            "add_on_answers": args.add_on_answers,
            "remove_on_answers": args.remove_on_answers,
            "on_missing": args.on_missing,
        }
        mappings_to_run = [custom_mapping]

    success = True
    for mapping in mappings_to_run:
        ok = process_mapping(
            client,
            event_slug,
            mapping,
            target_submission=args.submission,
            dry_run=args.dry_run,
            verbose=args.verbose
        )
        if not ok:
            success = False

    if success:
        print(f"\n{green(bold('✓ All tag updates processed successfully!'))}\n")
    else:
        print(f"\n{red(bold('✖ Completed with errors.'))}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
