"""
auth.py — Header-based ACL for Operations Resource Manager.

In production the app sits behind an oauth2-proxy that injects:
  X-Auth-Email   — user's email address
  X-Auth-User    — username / display name
  X-Auth-Groups  — comma-separated group IDs

Groups are matched against READ_GROUPS and WRITE_GROUPS env vars
(also comma-separated lists of group IDs).

In development (no proxy), set DEV_AUTH_* env vars to inject fake headers:
  DEV_AUTH_EMAIL=dev@example.com
  DEV_AUTH_USER=Developer
  DEV_AUTH_GROUPS=group-programming-id

If neither READ_GROUPS nor WRITE_GROUPS are configured, all access is allowed
(convenient for local development without DEV_AUTH vars).
"""

import os
import logging
from functools import wraps
from flask import request, g, jsonify

logger = logging.getLogger(__name__)

# --- Configuration ---

def _parse_group_env(var):
    raw = os.environ.get(var, "")
    return {x.strip() for x in raw.split(",") if x.strip()}

READ_GROUPS  = _parse_group_env("READ_GROUPS")
WRITE_GROUPS = _parse_group_env("WRITE_GROUPS")

DEV_AUTH_EMAIL  = os.environ.get("DEV_AUTH_EMAIL", "")
DEV_AUTH_USER   = os.environ.get("DEV_AUTH_USER", "")
DEV_AUTH_GROUPS = os.environ.get("DEV_AUTH_GROUPS", "")

_ACL_CONFIGURED = bool(READ_GROUPS or WRITE_GROUPS)


def get_current_user():
    """
    Build the current user dict from request headers (or dev env vars).
    Returns:
        {email, username, groups: list, can_read: bool, can_write: bool}
    """
    if DEV_AUTH_EMAIL:
        email      = DEV_AUTH_EMAIL
        username   = DEV_AUTH_USER or DEV_AUTH_EMAIL
        groups_raw = DEV_AUTH_GROUPS
    else:
        email      = request.headers.get("X-Auth-Email", "")
        username   = request.headers.get("X-Auth-User", email)
        groups_raw = request.headers.get("X-Auth-Groups", "")

    groups = {x.strip() for x in groups_raw.split(",") if x.strip()}

    if not _ACL_CONFIGURED:
        # No groups configured — allow everything (local dev mode)
        can_read = can_write = True
    else:
        can_write = bool(WRITE_GROUPS & groups)
        can_read  = bool(READ_GROUPS & groups) or can_write  # write implies read

    return {
        "email":     email,
        "username":  username or email or "anonymous",
        "groups":    sorted(groups),
        "can_read":  can_read,
        "can_write": can_write,
    }


# ---------------------------------------------------------------------------
# Flask decorators
# ---------------------------------------------------------------------------

def require_read(f):
    """Decorator: reject with 403 if the user does not have read access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        g.user = user
        if not user["can_read"]:
            logger.warning("403 read denied: %s", user.get("email"))
            # Return JSON for API routes, plain text for page routes
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Access denied"}), 403
            return "403 Access Denied — insufficient permissions", 403
        return f(*args, **kwargs)
    return decorated


def require_write(f):
    """Decorator: reject with 403 if the user does not have write access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        g.user = user
        if not user["can_write"]:
            logger.warning("403 write denied: %s", user.get("email"))
            return jsonify({"error": "Write access denied"}), 403
        return f(*args, **kwargs)
    return decorated
