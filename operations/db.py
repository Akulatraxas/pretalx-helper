"""
db.py — SQLite database layer for Operations Resource Manager.

Uses SQLAlchemy Core for the connection engine (pooling, pragma events) and
Alembic for schema migrations. Query functions use raw SQL via text() so the
SQL stays readable and the diff from the sqlite3 version is minimal.

Schema changes workflow
-----------------------
  1. Edit models.py with the new column / table.
  2. alembic revision --autogenerate -m "describe_change"
  3. Review migrations/versions/<rev>_describe_change.py
  4. Rebuild container — alembic upgrade head runs automatically at startup.
"""

import os
import logging

from sqlalchemy import create_engine, event, text, inspect as sa_inspect

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/data/operations.db")

DEPARTMENTS = ["Conops", "FS-Support", "CCH", "CODA"]

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    # SQLite needs pool_pre_ping disabled (it doesn't support it meaningfully)
    pool_pre_ping=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    """Apply WAL mode and foreign-key enforcement to every new connection."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


# ---------------------------------------------------------------------------
# Startup — run Alembic migrations
# ---------------------------------------------------------------------------

def init_db():
    """
    Ensure the database directory exists and apply any pending Alembic
    migrations.

    Handles three cases automatically:
      • Fresh DB: creates full schema via 0001_initial migration.
      • Pre-Alembic DB (tables exist, no alembic_version): stamps at head.
      • Existing managed DB: runs any pending migrations to reach head.
    """
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    from alembic.config import Config
    from alembic import command
    from alembic.runtime.migration import MigrationContext

    alembic_cfg_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "alembic.ini"
    )
    alembic_cfg = Config(alembic_cfg_path)

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current_rev = ctx.get_current_revision()

    if current_rev is None:
        # No alembic_version row — check whether the schema already exists
        insp = sa_inspect(engine)
        if "resources" in insp.get_table_names():
            # Pre-Alembic deployment: tables are already there, just stamp.
            logger.info(
                "Existing pre-Alembic database detected — stamping at head"
            )
            command.stamp(alembic_cfg, "head")
            return

    # Fresh DB or DB with pending migrations: run upgrade.
    command.upgrade(alembic_cfg, "head")
    logger.info("Database ready at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_dict(row):
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)


def _row_to_resource(row):
    r = _to_dict(row)
    raw = r.get("departments") or ""
    r["departments"] = [d for d in raw.split(",") if d] if raw else []
    return r


def _audit(conn, user_email, action, detail=""):
    conn.execute(
        text(
            "INSERT INTO audit_log (user_email, action, detail) "
            "VALUES (:email, :action, :detail)"
        ),
        {"email": user_email or "", "action": action, "detail": detail},
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

def list_resources():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.id, r.name, r.amount, r.created_at,
                   GROUP_CONCAT(rd.department) AS departments
            FROM resources r
            LEFT JOIN resource_departments rd ON rd.resource_id = r.id
            GROUP BY r.id
            ORDER BY lower(r.name)
        """)).fetchall()
        return [_row_to_resource(row) for row in rows]


def get_resource(resource_id):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT r.id, r.name, r.amount, r.created_at,
                   GROUP_CONCAT(rd.department) AS departments
            FROM resources r
            LEFT JOIN resource_departments rd ON rd.resource_id = r.id
            WHERE r.id = :id
            GROUP BY r.id
        """), {"id": resource_id}).fetchone()
        return _row_to_resource(row) if row else None


def create_resource(name, amount, departments, user_email=None):
    with engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO resources (name, amount) VALUES (:name, :amount)"),
            {"name": name, "amount": int(amount)},
        )
        rid = result.lastrowid
        for dept in departments:
            if dept in DEPARTMENTS:
                conn.execute(
                    text(
                        "INSERT INTO resource_departments (resource_id, department) "
                        "VALUES (:rid, :dept)"
                    ),
                    {"rid": rid, "dept": dept},
                )
        _audit(conn, user_email, "create_resource", f"id={rid} name={name!r}")
        return rid


def update_resource(resource_id, name, amount, departments, user_email=None):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE resources SET name=:name, amount=:amount WHERE id=:id"),
            {"name": name, "amount": int(amount), "id": resource_id},
        )
        conn.execute(
            text("DELETE FROM resource_departments WHERE resource_id=:id"),
            {"id": resource_id},
        )
        for dept in departments:
            if dept in DEPARTMENTS:
                conn.execute(
                    text(
                        "INSERT INTO resource_departments (resource_id, department) "
                        "VALUES (:rid, :dept)"
                    ),
                    {"rid": resource_id, "dept": dept},
                )
        _audit(conn, user_email, "update_resource",
               f"id={resource_id} name={name!r}")


def delete_resource(resource_id, user_email=None):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM resources WHERE id=:id"), {"id": resource_id}
        )
        _audit(conn, user_email, "delete_resource", f"id={resource_id}")


def get_resource_usage(resource_id):
    """Return all submission codes assigned this resource, with assignment metadata."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT sr.submission_code, sr.note, sr.department_override
            FROM submission_resources sr
            WHERE sr.resource_id = :rid
            ORDER BY sr.submission_code
        """), {"rid": resource_id}).fetchall()
        return [_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Submission assignments (resources + comments)
# ---------------------------------------------------------------------------

def get_submission_assignments(submission_code):
    """Return all resources and comments attached to a submission code."""
    with engine.connect() as conn:
        resource_rows = conn.execute(text("""
            SELECT sr.id, sr.resource_id, r.name AS resource_name, r.amount,
                   sr.note, sr.department_override, sr.created_at,
                   GROUP_CONCAT(rd.department) AS resource_departments
            FROM submission_resources sr
            JOIN resources r ON r.id = sr.resource_id
            LEFT JOIN resource_departments rd ON rd.resource_id = sr.resource_id
            WHERE sr.submission_code = :code
            GROUP BY sr.id
            ORDER BY lower(r.name)
        """), {"code": submission_code}).fetchall()

        comment_rows = conn.execute(text("""
            SELECT id, text, department, created_at
            FROM submission_comments
            WHERE submission_code = :code
            ORDER BY created_at
        """), {"code": submission_code}).fetchall()

    resources = []
    for row in resource_rows:
        r = _to_dict(row)
        raw = r.get("resource_departments") or ""
        r["resource_departments"] = [d for d in raw.split(",") if d]
        resources.append(r)

    return {
        "resources": resources,
        "comments":  [_to_dict(r) for r in comment_rows],
    }


def add_submission_resource(
    submission_code, resource_id, note, department_override, user_email=None
):
    """Upsert a resource assignment (UNIQUE on code + resource_id)."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO submission_resources
                (submission_code, resource_id, note, department_override)
            VALUES (:code, :rid, :note, :dept)
            ON CONFLICT(submission_code, resource_id) DO UPDATE SET
                note=excluded.note,
                department_override=excluded.department_override
        """), {
            "code": submission_code,
            "rid":  resource_id,
            "note": note or None,
            "dept": department_override or None,
        })
        _audit(conn, user_email, "add_resource",
               f"code={submission_code} resource_id={resource_id}")


def remove_submission_resource(assignment_id, user_email=None):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM submission_resources WHERE id=:id"),
            {"id": assignment_id},
        )
        _audit(conn, user_email, "remove_resource",
               f"assignment_id={assignment_id}")


def add_submission_comment(submission_code, text_body, department, user_email=None):
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO submission_comments (submission_code, text, department)
            VALUES (:code, :text, :dept)
        """), {"code": submission_code, "text": text_body, "dept": department})
        comment_id = result.lastrowid
        _audit(conn, user_email, "add_comment",
               f"code={submission_code} dept={department}")
        return comment_id


def remove_submission_comment(comment_id, user_email=None):
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM submission_comments WHERE id=:id"),
            {"id": comment_id},
        )
        _audit(conn, user_email, "remove_comment", f"comment_id={comment_id}")


# ---------------------------------------------------------------------------
# Output queries (used by /api/output)
# ---------------------------------------------------------------------------

def get_output_by_department(department=None):
    """
    Return a dict keyed by submission_code with resources + comments.
    If department is None, returns everything; otherwise filters to that dept.
    """
    with engine.connect() as conn:
        if department and department != "all":
            resource_rows = conn.execute(text("""
                SELECT sr.submission_code, sr.id AS assignment_id,
                       sr.resource_id, r.name AS resource_name,
                       sr.note, sr.department_override,
                       GROUP_CONCAT(rd.department) AS resource_departments
                FROM submission_resources sr
                JOIN resources r ON r.id = sr.resource_id
                LEFT JOIN resource_departments rd ON rd.resource_id = sr.resource_id
                WHERE sr.department_override = :dept
                   OR (sr.department_override IS NULL AND EXISTS (
                        SELECT 1 FROM resource_departments rd2
                        WHERE rd2.resource_id = sr.resource_id
                          AND rd2.department = :dept
                   ))
                GROUP BY sr.id
            """), {"dept": department}).fetchall()

            comment_rows = conn.execute(text("""
                SELECT submission_code, id, text, department, created_at
                FROM submission_comments
                WHERE department = :dept
                ORDER BY submission_code, created_at
            """), {"dept": department}).fetchall()
        else:
            resource_rows = conn.execute(text("""
                SELECT sr.submission_code, sr.id AS assignment_id,
                       sr.resource_id, r.name AS resource_name,
                       sr.note, sr.department_override,
                       GROUP_CONCAT(rd.department) AS resource_departments
                FROM submission_resources sr
                JOIN resources r ON r.id = sr.resource_id
                LEFT JOIN resource_departments rd ON rd.resource_id = sr.resource_id
                GROUP BY sr.id
            """)).fetchall()

            comment_rows = conn.execute(text("""
                SELECT submission_code, id, text, department, created_at
                FROM submission_comments
                ORDER BY submission_code, created_at
            """)).fetchall()

    by_code = {}
    for row in resource_rows:
        code = row._mapping["submission_code"]
        if code not in by_code:
            by_code[code] = {"resources": [], "comments": []}
        r = _to_dict(row)
        raw = r.get("resource_departments") or ""
        r["resource_departments"] = [d for d in raw.split(",") if d]
        by_code[code]["resources"].append(r)

    for row in comment_rows:
        code = row._mapping["submission_code"]
        if code not in by_code:
            by_code[code] = {"resources": [], "comments": []}
        by_code[code]["comments"].append(_to_dict(row))

    return by_code


# ---------------------------------------------------------------------------
# Conflict detection helpers
# ---------------------------------------------------------------------------

def get_all_resource_assignments_for_conflict():
    """Return (submission_code, resource_id, resource_name, amount) for finite resources."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT sr.submission_code, sr.resource_id,
                   r.name AS resource_name, r.amount
            FROM submission_resources sr
            JOIN resources r ON r.id = sr.resource_id
            WHERE r.amount > 0
        """)).fetchall()
        return [_to_dict(r) for r in rows]


def get_codes_with_assignments():
    """Return set of submission codes that have any resource or comment."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT submission_code FROM submission_resources
            UNION
            SELECT DISTINCT submission_code FROM submission_comments
        """)).fetchall()
        return {row._mapping["submission_code"] for row in rows}
