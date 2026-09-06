"""
auth.py — Header-based ACL for Feedback Viewer.

In production the app sits behind an oauth2-proxy that injects:
  X-Auth-Email   — user's email address
  X-Auth-User    — username / display name
  X-Auth-Groups  — comma-separated group IDs

Groups are matched against the following env vars (all comma-separated lists
of IDP group IDs):

  READ_GROUPS   / WRITE_GROUPS
      Global access groups.
      READ_GROUPS grants read access across all domains.
      WRITE_GROUPS grants write and read access across all domains.

  READ_GROUPS_FEEDBACK   / WRITE_GROUPS_FEEDBACK
      Read/write access for the Feedback viewer.

  Note: WRITE_* always implies read for the same domain.
        Admin (READ_GROUPS / WRITE_GROUPS) always implies access to every domain.

In development (no proxy), explicitly enable development authentication and
set DEV_AUTH_* env vars to inject fake headers:
  DEV_AUTH_ENABLED=true
  DEV_AUTH_EMAIL=dev@example.com
  DEV_AUTH_USER=Developer
  DEV_AUTH_GROUPS=group-programming-id
"""

import os
import logging
from functools import wraps
from flask import request, g, jsonify

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _parse_group_env(var):
    """Parse a comma-separated environment variable into a set of trimmed group identifiers."""
    raw = os.environ.get(var, "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def _parse_bool_env(var):
    """Return whether an environment variable is explicitly enabled."""
    return os.environ.get(var, "").strip().lower() in {"1", "true", "yes", "on"}


# Admin groups (full access)
READ_GROUPS  = _parse_group_env("READ_GROUPS")
WRITE_GROUPS = _parse_group_env("WRITE_GROUPS")

# Feedback-scoped groups
READ_GROUPS_FEEDBACK  = _parse_group_env("READ_GROUPS_FEEDBACK")
WRITE_GROUPS_FEEDBACK = _parse_group_env("WRITE_GROUPS_FEEDBACK")

DEV_AUTH_ENABLED = _parse_bool_env("DEV_AUTH_ENABLED")
DEV_AUTH_EMAIL  = os.environ.get("DEV_AUTH_EMAIL", "")
DEV_AUTH_USER   = os.environ.get("DEV_AUTH_USER", "")
DEV_AUTH_GROUPS = os.environ.get("DEV_AUTH_GROUPS", "")

_ALL_GROUP_ENVS = (
    READ_GROUPS, WRITE_GROUPS,
    READ_GROUPS_FEEDBACK, WRITE_GROUPS_FEEDBACK,
)
_ACL_CONFIGURED = any(_ALL_GROUP_ENVS)
_DEV_AUTH_ACTIVE = DEV_AUTH_ENABLED and bool(DEV_AUTH_EMAIL)


def validate_config():
    """Reject startup unless production ACLs or explicit development auth are configured."""
    if DEV_AUTH_ENABLED and not DEV_AUTH_EMAIL:
        raise RuntimeError("DEV_AUTH_ENABLED requires DEV_AUTH_EMAIL")
    if not _ACL_CONFIGURED and not _DEV_AUTH_ACTIVE:
        raise RuntimeError(
            "No ACL groups configured; set READ_GROUPS/WRITE_GROUPS (or their "
            "feedback variants), or explicitly enable development auth with "
            "DEV_AUTH_ENABLED=true and DEV_AUTH_EMAIL"
        )
    if DEV_AUTH_EMAIL and not DEV_AUTH_ENABLED:
        logger.warning("DEV_AUTH_EMAIL is ignored unless DEV_AUTH_ENABLED is true")


# ---------------------------------------------------------------------------
# User resolution
# ---------------------------------------------------------------------------

def get_current_user():
    """
    Resolve the current user's identity, groups, and authorization flags.
    """
    if _DEV_AUTH_ACTIVE:
        email      = DEV_AUTH_EMAIL
        username   = DEV_AUTH_USER or DEV_AUTH_EMAIL
        groups_raw = DEV_AUTH_GROUPS
    else:
        email      = request.headers.get("X-Auth-Email", "")
        username   = request.headers.get("X-Auth-User", email)
        groups_raw = request.headers.get("X-Auth-Groups", "")

    groups = {x.strip() for x in groups_raw.split(",") if x.strip()}

    if not _ACL_CONFIGURED and _DEV_AUTH_ACTIVE:
        # Explicit local development mode without production ACL groups.
        return {
            "email":               email,
            "username":            username or email or "anonymous",
            "groups":              sorted(groups),
            "can_read":            True,
            "can_write":           True,
            "can_admin":           True,
            "can_read_any":        True,
            "can_write_any":       True,
            "can_read_feedback":   True,
            "can_write_feedback":  True,
        }

    # Admin groups grant full access everywhere
    is_admin_write = bool(WRITE_GROUPS & groups)
    is_admin_read  = bool(READ_GROUPS & groups) or is_admin_write

    # Feedback flags (write implies read for the same domain; admin implies all)
    can_write_feedback = is_admin_write or bool(WRITE_GROUPS_FEEDBACK & groups)
    can_read_feedback  = is_admin_read  or bool(READ_GROUPS_FEEDBACK & groups) or can_write_feedback

    can_read_any  = is_admin_read or can_read_feedback
    can_write_any = is_admin_write or can_write_feedback

    return {
        "email":               email,
        "username":            username or email or "anonymous",
        "groups":              sorted(groups),
        # Legacy / admin flags
        "can_read":            is_admin_read or can_read_feedback,
        "can_write":           is_admin_write or can_write_feedback,
        "can_admin":           is_admin_write,
        "can_read_any":        can_read_any,
        "can_write_any":       can_write_any,
        # Feedback flags
        "can_read_feedback":   can_read_feedback,
        "can_write_feedback":  can_write_feedback,
    }


# ---------------------------------------------------------------------------
# Internal decorator factory
# ---------------------------------------------------------------------------

def _make_decorator(flag, label):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            g.user = user
            if not user[flag]:
                logger.warning("403 %s denied: %s", label, user.get("email"))
                if request.path.startswith("/api/") or request.is_json:
                    return jsonify({"error": "Access denied"}), 403
                return "403 Access Denied — insufficient permissions", 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# Public decorators
# ---------------------------------------------------------------------------

require_admin = _make_decorator("can_admin", "admin")

require_read_feedback  = _make_decorator("can_read_feedback",  "read:feedback")
require_write_feedback = _make_decorator("can_write_feedback", "write:feedback")

require_read_any  = _make_decorator("can_read_any",  "read:any")
require_write_any = _make_decorator("can_write_any", "write:any")

require_read  = require_read_feedback
require_write = require_write_feedback
