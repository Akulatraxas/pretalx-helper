"""
auth.py — Header-based ACL for Operations Resource Manager.

In production the app sits behind an oauth2-proxy that injects:
  X-Auth-Email   — user's email address
  X-Auth-User    — username / display name
  X-Auth-Groups  — comma-separated group IDs

Groups are matched against the following env vars (all comma-separated lists
of IDP group IDs):

  READ_GROUPS   / WRITE_GROUPS
      Legacy global-access groups.
      READ_GROUPS grants read access across all domains.
      WRITE_GROUPS grants write and read access across all domains.

  READ_GROUPS_EVENTS   / WRITE_GROUPS_EVENTS
      Read/write access for the Events, Resources, and Output pages/tabs.
      Covers: resource inventory, submission assignments/comments, output views.

  READ_GROUPS_OPERATIONS   / WRITE_GROUPS_OPERATIONS
      Read/write access for the Operations and Occupancy pages/tabs.
      Covers: upcoming-events feed, take/complete/unassign, occupancy ratings.

  READ_GROUPS_ANNOUNCEMENTS   / WRITE_GROUPS_ANNOUNCEMENTS
      Read/write access for the Delays (Announcements) page/tab.
      Covers: delay feed, set/clear delays, schedule-change send/discard.
      Named ANNOUNCEMENTS rather than DELAYS because the page will eventually
      host a generic announcement feature alongside delays.

  Note: WRITE_* always implies read for the same domain.
        Admin (READ_GROUPS / WRITE_GROUPS) always implies access to every domain.

In development (no proxy), set DEV_AUTH_* env vars to inject fake headers:
  DEV_AUTH_EMAIL=dev@example.com
  DEV_AUTH_USER=Developer
  DEV_AUTH_GROUPS=group-programming-id

If none of the group env vars are configured, all access is allowed
(convenient for local development without DEV_AUTH vars).
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
    """Parse a comma-separated environment variable into a set of trimmed group identifiers.
    
    Parameters:
    	var (str): The environment variable name.
    
    Returns:
    	set[str]: The non-empty group identifiers defined by the environment variable.
    """
    raw = os.environ.get(var, "")
    return {x.strip() for x in raw.split(",") if x.strip()}


# Admin / legacy groups (full access to all domains)
READ_GROUPS  = _parse_group_env("READ_GROUPS")
WRITE_GROUPS = _parse_group_env("WRITE_GROUPS")

# Domain-scoped groups
READ_GROUPS_EVENTS         = _parse_group_env("READ_GROUPS_EVENTS")
WRITE_GROUPS_EVENTS        = _parse_group_env("WRITE_GROUPS_EVENTS")
READ_GROUPS_OPERATIONS     = _parse_group_env("READ_GROUPS_OPERATIONS")
WRITE_GROUPS_OPERATIONS    = _parse_group_env("WRITE_GROUPS_OPERATIONS")
READ_GROUPS_ANNOUNCEMENTS  = _parse_group_env("READ_GROUPS_ANNOUNCEMENTS")
WRITE_GROUPS_ANNOUNCEMENTS = _parse_group_env("WRITE_GROUPS_ANNOUNCEMENTS")

DEV_AUTH_EMAIL  = os.environ.get("DEV_AUTH_EMAIL", "")
DEV_AUTH_USER   = os.environ.get("DEV_AUTH_USER", "")
DEV_AUTH_GROUPS = os.environ.get("DEV_AUTH_GROUPS", "")

_ALL_GROUP_ENVS = (
    READ_GROUPS, WRITE_GROUPS,
    READ_GROUPS_EVENTS, WRITE_GROUPS_EVENTS,
    READ_GROUPS_OPERATIONS, WRITE_GROUPS_OPERATIONS,
    READ_GROUPS_ANNOUNCEMENTS, WRITE_GROUPS_ANNOUNCEMENTS,
)
_ACL_CONFIGURED = any(_ALL_GROUP_ENVS)


# ---------------------------------------------------------------------------
# User resolution
# ---------------------------------------------------------------------------

def get_current_user():
    """
    Resolve the current user's identity, groups, and authorization flags.
    
    Identity and groups come from development authentication settings when configured;
    otherwise, they are read from the request headers. When no ACL groups are
    configured, all permissions are enabled.
    
    Returns:
        dict: User metadata and authorization flags, including ``email``,
        ``username``, sorted ``groups``, legacy admin-level permissions, and
        read/write permissions for Events, Operations, and Announcements.
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
        return {
            "email":                   email,
            "username":                username or email or "anonymous",
            "groups":                  sorted(groups),
            "can_read":                True,
            "can_write":               True,
            "can_admin":               True,
            "can_read_events":         True,
            "can_write_events":        True,
            "can_read_operations":     True,
            "can_write_operations":    True,
            "can_read_announcements":  True,
            "can_write_announcements": True,
        }

    # Admin groups grant full access everywhere
    is_admin_write = bool(WRITE_GROUPS & groups)
    is_admin_read  = bool(READ_GROUPS & groups) or is_admin_write

    # Per-domain flags (write implies read for the same domain; admin implies all)
    can_write_events        = is_admin_write or bool(WRITE_GROUPS_EVENTS & groups)
    can_read_events         = is_admin_read  or bool(READ_GROUPS_EVENTS & groups) or can_write_events

    can_write_operations    = is_admin_write or bool(WRITE_GROUPS_OPERATIONS & groups)
    can_read_operations     = is_admin_read  or bool(READ_GROUPS_OPERATIONS & groups) or can_write_operations

    can_write_announcements = is_admin_write or bool(WRITE_GROUPS_ANNOUNCEMENTS & groups)
    can_read_announcements  = is_admin_read  or bool(READ_GROUPS_ANNOUNCEMENTS & groups) or can_write_announcements

    return {
        "email":                   email,
        "username":                username or email or "anonymous",
        "groups":                  sorted(groups),
        # Legacy / admin flags
        "can_read":                is_admin_read,
        "can_write":               is_admin_write,
        "can_admin":               is_admin_write,
        # Domain-scoped flags
        "can_read_events":         can_read_events,
        "can_write_events":        can_write_events,
        "can_read_operations":     can_read_operations,
        "can_write_operations":    can_write_operations,
        "can_read_announcements":  can_read_announcements,
        "can_write_announcements": can_write_announcements,
    }


# ---------------------------------------------------------------------------
# Internal decorator factory
# ---------------------------------------------------------------------------

def _make_decorator(flag, label):
    """Create a Flask decorator that enforces a user's authorization flag.
    
    Parameters:
        flag: The user permission key to check.
        label: The authorization label used when logging denied requests.
    
    Returns:
        A decorator that permits authorized requests and returns a 403 response for denied requests.
    """
    def decorator(f):
        """
        Create an authorization decorator for a Flask view.
        
        Parameters:
        	f (callable): The view function to protect.
        
        Returns:
        	callable: A wrapped view that executes for authorized users and returns a 403 response otherwise.
        """
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

# Admin (full access / cache refresh)
require_admin = _make_decorator("can_admin", "admin")

# Events domain — Events, Resources, Output pages
require_read_events  = _make_decorator("can_read_events",  "read:events")
require_write_events = _make_decorator("can_write_events", "write:events")

# Operations domain — Operations, Occupancy pages
require_read_operations  = _make_decorator("can_read_operations",  "read:operations")
require_write_operations = _make_decorator("can_write_operations", "write:operations")

# Announcements domain — Delays (+ future generic announcements) page
require_read_announcements  = _make_decorator("can_read_announcements",  "read:announcements")
require_write_announcements = _make_decorator("can_write_announcements", "write:announcements")

# ---------------------------------------------------------------------------
# Legacy aliases (kept for any callers not yet migrated)
# ---------------------------------------------------------------------------

def require_read(f):
    """
    Deprecated legacy decorator that grants access to users with read permission in any domain or administrative read permission.
    
    Parameters:
        f (callable): View function to protect.
    
    Returns:
        callable: Decorated view function that denies unauthorized requests with a 403 response.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        """
        Authorize access to views requiring read permission in any supported domain.
        
        Returns:
            The wrapped view response when access is granted; otherwise, a 403 response.
        """
        user = get_current_user()
        g.user = user
        has_any_read = (
            user["can_read"]
            or user["can_read_events"]
            or user["can_read_operations"]
            or user["can_read_announcements"]
        )
        if not has_any_read:
            logger.warning("403 read denied (legacy): %s", user.get("email"))
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Access denied"}), 403
            return "403 Access Denied — insufficient permissions", 403
        return f(*args, **kwargs)
    return decorated


def require_write(f):
    """
    Require write access in at least one supported domain.
    
    Parameters:
        f (callable): The function to protect.
    
    Returns:
        callable: A wrapped function that returns a JSON 403 response when access is denied.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        """
        Authorize access for users with write permission in any supported domain.
        
        Returns:
            The wrapped view result when authorized, or a JSON 403 response when access is denied.
        """
        user = get_current_user()
        g.user = user
        has_any_write = (
            user["can_write"]
            or user["can_write_events"]
            or user["can_write_operations"]
            or user["can_write_announcements"]
        )
        if not has_any_write:
            logger.warning("403 write denied (legacy): %s", user.get("email"))
            return jsonify({"error": "Write access denied"}), 403
        return f(*args, **kwargs)
    return decorated
