"""
db.py — SQLite database layer for Feedback Viewer.

Uses SQLAlchemy Core for the connection engine (pooling, pragma events) and
Alembic for schema migrations. Query functions use raw SQL via text().
"""

import os
import logging

from sqlalchemy import create_engine, event, text, inspect as sa_inspect

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = (
    "/data/feedback.db"
    if os.path.isdir("/data") and os.access("/data", os.W_OK)
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "feedback.db")
)
DB_PATH = os.environ.get("DB_PATH", DEFAULT_DB_PATH)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
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

    Handles fresh DB, pre-existing DB, and pending migrations.
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
        insp = sa_inspect(engine)
        if "audit_log" in insp.get_table_names():
            logger.info("Existing pre-Alembic database detected — stamping at head")
            command.stamp(alembic_cfg, "head")
            return

    command.upgrade(alembic_cfg, "head")
    logger.info("Database ready at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_dict(row):
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)


def _audit(conn, user_email, action, detail=""):
    conn.execute(
        text(
            "INSERT INTO audit_log (user_email, action, detail) "
            "VALUES (:email, :action, :detail)"
        ),
        {"email": user_email or "", "action": action, "detail": detail},
    )


def log_audit(user_email, action, detail=""):
    """Public helper to write to the audit log."""
    with engine.begin() as conn:
        _audit(conn, user_email, action, detail)


def get_recent_audit_logs(limit=100):
    """Retrieve the most recent audit log records."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, user_email, action, detail, created_at FROM audit_log ORDER BY id DESC LIMIT :limit"),
            {"limit": limit},
        ).fetchall()
        return [_to_dict(r) for r in rows]
