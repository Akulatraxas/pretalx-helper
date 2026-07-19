"""
db.py — SQLite database layer for Operations Resource Manager.

All event data lives in the Pretalx cache (never stored here).
This module stores only the operational overlay: resources, assignments, comments.
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/data/operations.db")

DEPARTMENTS = ["Conops", "FS-Support", "CCH"]

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS resources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    amount      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resource_departments (
    resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    department  TEXT NOT NULL,
    PRIMARY KEY (resource_id, department)
);

-- One assignment record per (submission_code, resource) pair.
-- note shows up in parentheses on output lists.
-- department_override redirects the assignment to a different dept list than the resource default.
CREATE TABLE IF NOT EXISTS submission_resources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_code     TEXT NOT NULL,
    resource_id         INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    note                TEXT,
    department_override TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (submission_code, resource_id)
);

CREATE TABLE IF NOT EXISTS submission_comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_code TEXT NOT NULL,
    text            TEXT NOT NULL,
    department      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email  TEXT,
    action      TEXT NOT NULL,
    detail      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sub_resources_code ON submission_resources(submission_code);
CREATE INDEX IF NOT EXISTS idx_sub_comments_code  ON submission_comments(submission_code);
"""


def _connect():
    """Open a WAL-mode, foreign-key-enabled SQLite connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = _connect()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    logger.info("Database ready at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_resource(row):
    r = dict(row)
    raw = r.get("departments") or ""
    r["departments"] = [d for d in raw.split(",") if d] if raw else []
    return r


def _audit(conn, user_email, action, detail=""):
    conn.execute(
        "INSERT INTO audit_log (user_email, action, detail) VALUES (?, ?, ?)",
        (user_email or "", action, detail),
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

def list_resources():
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT r.id, r.name, r.amount, r.created_at,
                   GROUP_CONCAT(rd.department) AS departments
            FROM resources r
            LEFT JOIN resource_departments rd ON rd.resource_id = r.id
            GROUP BY r.id
            ORDER BY lower(r.name)
        """).fetchall()
        return [_row_to_resource(row) for row in rows]
    finally:
        conn.close()


def get_resource(resource_id):
    conn = _connect()
    try:
        row = conn.execute("""
            SELECT r.id, r.name, r.amount, r.created_at,
                   GROUP_CONCAT(rd.department) AS departments
            FROM resources r
            LEFT JOIN resource_departments rd ON rd.resource_id = r.id
            WHERE r.id = ?
            GROUP BY r.id
        """, (resource_id,)).fetchone()
        return _row_to_resource(row) if row else None
    finally:
        conn.close()


def create_resource(name, amount, departments, user_email=None):
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO resources (name, amount) VALUES (?, ?)", (name, int(amount))
        )
        rid = cur.lastrowid
        for dept in departments:
            if dept in DEPARTMENTS:
                conn.execute(
                    "INSERT INTO resource_departments (resource_id, department) VALUES (?, ?)",
                    (rid, dept),
                )
        _audit(conn, user_email, "create_resource", f"id={rid} name={name!r}")
        conn.commit()
        return rid
    finally:
        conn.close()


def update_resource(resource_id, name, amount, departments, user_email=None):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE resources SET name=?, amount=? WHERE id=?",
            (name, int(amount), resource_id),
        )
        conn.execute(
            "DELETE FROM resource_departments WHERE resource_id=?", (resource_id,)
        )
        for dept in departments:
            if dept in DEPARTMENTS:
                conn.execute(
                    "INSERT INTO resource_departments (resource_id, department) VALUES (?, ?)",
                    (resource_id, dept),
                )
        _audit(conn, user_email, "update_resource", f"id={resource_id} name={name!r}")
        conn.commit()
    finally:
        conn.close()


def delete_resource(resource_id, user_email=None):
    conn = _connect()
    try:
        conn.execute("DELETE FROM resources WHERE id=?", (resource_id,))
        _audit(conn, user_email, "delete_resource", f"id={resource_id}")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Submission assignments (resources + comments)
# ---------------------------------------------------------------------------

def get_submission_assignments(submission_code):
    """Return all resources and comments attached to a submission code."""
    conn = _connect()
    try:
        resource_rows = conn.execute("""
            SELECT sr.id, sr.resource_id, r.name AS resource_name, r.amount,
                   sr.note, sr.department_override, sr.created_at,
                   GROUP_CONCAT(rd.department) AS resource_departments
            FROM submission_resources sr
            JOIN resources r ON r.id = sr.resource_id
            LEFT JOIN resource_departments rd ON rd.resource_id = sr.resource_id
            WHERE sr.submission_code = ?
            GROUP BY sr.id
            ORDER BY lower(r.name)
        """, (submission_code,)).fetchall()

        comment_rows = conn.execute("""
            SELECT id, text, department, created_at
            FROM submission_comments
            WHERE submission_code = ?
            ORDER BY created_at
        """, (submission_code,)).fetchall()

        resources = []
        for row in resource_rows:
            r = dict(row)
            raw = r.get("resource_departments") or ""
            r["resource_departments"] = [d for d in raw.split(",") if d]
            resources.append(r)

        return {
            "resources": resources,
            "comments": [dict(r) for r in comment_rows],
        }
    finally:
        conn.close()


def add_submission_resource(submission_code, resource_id, note, department_override, user_email=None):
    """Upsert a resource assignment (UNIQUE on code+resource_id)."""
    conn = _connect()
    try:
        conn.execute("""
            INSERT INTO submission_resources
                (submission_code, resource_id, note, department_override)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(submission_code, resource_id) DO UPDATE SET
                note=excluded.note,
                department_override=excluded.department_override
        """, (submission_code, resource_id,
               note or None,
               department_override or None))
        _audit(conn, user_email, "add_resource",
               f"code={submission_code} resource_id={resource_id}")
        conn.commit()
    finally:
        conn.close()


def remove_submission_resource(assignment_id, user_email=None):
    conn = _connect()
    try:
        conn.execute("DELETE FROM submission_resources WHERE id=?", (assignment_id,))
        _audit(conn, user_email, "remove_resource", f"assignment_id={assignment_id}")
        conn.commit()
    finally:
        conn.close()


def add_submission_comment(submission_code, text, department, user_email=None):
    conn = _connect()
    try:
        cur = conn.execute("""
            INSERT INTO submission_comments (submission_code, text, department)
            VALUES (?, ?, ?)
        """, (submission_code, text, department))
        comment_id = cur.lastrowid
        _audit(conn, user_email, "add_comment",
               f"code={submission_code} dept={department}")
        conn.commit()
        return comment_id
    finally:
        conn.close()


def remove_submission_comment(comment_id, user_email=None):
    conn = _connect()
    try:
        conn.execute("DELETE FROM submission_comments WHERE id=?", (comment_id,))
        _audit(conn, user_email, "remove_comment", f"comment_id={comment_id}")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Output queries (used by /api/output)
# ---------------------------------------------------------------------------

def get_output_by_department(department=None):
    """
    Return a dict keyed by submission_code with resources + comments.
    If department is None or "all", return everything.
    Otherwise filter to resources/comments relevant to that department.
    """
    conn = _connect()
    try:
        if department and department != "all":
            resource_rows = conn.execute("""
                SELECT sr.submission_code, sr.id AS assignment_id,
                       sr.resource_id, r.name AS resource_name,
                       sr.note, sr.department_override,
                       GROUP_CONCAT(rd.department) AS resource_departments
                FROM submission_resources sr
                JOIN resources r ON r.id = sr.resource_id
                LEFT JOIN resource_departments rd ON rd.resource_id = sr.resource_id
                WHERE sr.department_override = ?
                   OR (sr.department_override IS NULL AND EXISTS (
                        SELECT 1 FROM resource_departments rd2
                        WHERE rd2.resource_id = sr.resource_id AND rd2.department = ?
                   ))
                GROUP BY sr.id
            """, (department, department)).fetchall()

            comment_rows = conn.execute("""
                SELECT submission_code, id, text, department, created_at
                FROM submission_comments
                WHERE department = ?
                ORDER BY submission_code, created_at
            """, (department,)).fetchall()
        else:
            resource_rows = conn.execute("""
                SELECT sr.submission_code, sr.id AS assignment_id,
                       sr.resource_id, r.name AS resource_name,
                       sr.note, sr.department_override,
                       GROUP_CONCAT(rd.department) AS resource_departments
                FROM submission_resources sr
                JOIN resources r ON r.id = sr.resource_id
                LEFT JOIN resource_departments rd ON rd.resource_id = sr.resource_id
                GROUP BY sr.id
            """).fetchall()

            comment_rows = conn.execute("""
                SELECT submission_code, id, text, department, created_at
                FROM submission_comments
                ORDER BY submission_code, created_at
            """).fetchall()

        # Group by submission code
        by_code = {}
        for row in resource_rows:
            code = row["submission_code"]
            if code not in by_code:
                by_code[code] = {"resources": [], "comments": []}
            r = dict(row)
            raw = r.get("resource_departments") or ""
            r["resource_departments"] = [d for d in raw.split(",") if d]
            by_code[code]["resources"].append(r)

        for row in comment_rows:
            code = row["submission_code"]
            if code not in by_code:
                by_code[code] = {"resources": [], "comments": []}
            by_code[code]["comments"].append(dict(row))

        return by_code
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Conflict detection helpers
# ---------------------------------------------------------------------------

def get_all_resource_assignments_for_conflict():
    """Return (submission_code, resource_id, resource_name, amount) for all finite resources."""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT sr.submission_code, sr.resource_id,
                   r.name AS resource_name, r.amount
            FROM submission_resources sr
            JOIN resources r ON r.id = sr.resource_id
            WHERE r.amount > 0
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_codes_with_assignments():
    """Return set of submission codes that have any resource or comment."""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT DISTINCT submission_code FROM submission_resources
            UNION
            SELECT DISTINCT submission_code FROM submission_comments
        """).fetchall()
        return {r["submission_code"] for r in rows}
    finally:
        conn.close()
