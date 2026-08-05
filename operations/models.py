"""
models.py — SQLAlchemy Core table metadata for Operations Resource Manager.

This module is intentionally ONLY used by Alembic (env.py imports `metadata`
for autogenerate). The query layer in db.py uses raw SQL via text() and does
NOT import from here — keeping a clean separation between schema definition
and query logic.

When you add a new column or table:
  1. Add it here in the appropriate Table() definition.
  2. Run: alembic revision --autogenerate -m "describe_change"
  3. Review the generated file in migrations/versions/.
"""

from sqlalchemy import (
    MetaData, Table, Column,
    Integer, Text, ForeignKey, Index, Boolean,
)

# Naming conventions let Alembic generate stable constraint names for batch
# operations (required for SQLite ALTER TABLE emulation).
metadata = MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

resources = Table(
    "resources", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("name",       Text,    nullable=False, unique=True),
    Column("amount",     Integer, nullable=False, default=0),
    Column("created_at", Text,    nullable=False,
           server_default="(datetime('now'))"),
)

resource_departments = Table(
    "resource_departments", metadata,
    Column("resource_id", Integer,
           ForeignKey("resources.id", ondelete="CASCADE"), nullable=False),
    Column("department",  Text, nullable=False),
)

submission_resources = Table(
    "submission_resources", metadata,
    Column("id",                  Integer, primary_key=True, autoincrement=True),
    Column("submission_code",     Text,    nullable=False),
    Column("resource_id",         Integer,
           ForeignKey("resources.id", ondelete="CASCADE"), nullable=False),
    Column("note",                Text,    nullable=True),
    Column("department_override", Text,    nullable=True),
    Column("created_at",          Text,    nullable=False,
           server_default="(datetime('now'))"),
)

submission_comments = Table(
    "submission_comments", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("submission_code", Text,    nullable=False),
    Column("text",            Text,    nullable=False),
    Column("department",      Text,    nullable=False),
    Column("created_at",      Text,    nullable=False,
           server_default="(datetime('now'))"),
)

audit_log = Table(
    "audit_log", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_email", Text,    nullable=True),
    Column("action",     Text,    nullable=False),
    Column("detail",     Text,    nullable=True),
    Column("created_at", Text,    nullable=False,
           server_default="(datetime('now'))"),
)

# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

Index("idx_sub_resources_code", submission_resources.c.submission_code)
Index("idx_sub_comments_code",  submission_comments.c.submission_code)

# Tracks per-slot operational state (taken by / completed) for the Operations tab.
# Keyed by (submission_code, slot_index) — one row per slot per submission.
operation_events = Table(
    "operation_events", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("submission_code",  Text,    nullable=False),
    Column("slot_index",       Integer, nullable=False, server_default="0"),
    Column("assigned_to",      Text,    nullable=True),   # email of the conops member who took it
    Column("is_completed",     Boolean, nullable=False, server_default="0"),
    Column("updated_at",       Text,    nullable=False,
           server_default="(datetime('now'))"),
)

Index("idx_op_events_code", operation_events.c.submission_code)
