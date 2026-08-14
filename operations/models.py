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
    Integer, Text, ForeignKey, Index, Boolean, UniqueConstraint,
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

# Tracks per-slot occupancy rating (Empty/Low/Medium/High/Full) for the Occupancy tab.
# Keyed by (submission_code, slot_index) — one row per slot, newer rating overwrites.
slot_occupancy = Table(
    "slot_occupancy", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("submission_code",  Text,    nullable=False),
    Column("slot_index",       Integer, nullable=False, server_default="0"),
    Column("rating",           Text,    nullable=False),   # Empty|Low|Medium|High|Full
    Column("rated_by",         Text,    nullable=True),    # email of the rater
    Column("updated_at",       Text,    nullable=False,
           server_default="(datetime('now'))"),
    UniqueConstraint("submission_code", "slot_index", name="uq_slot_occupancy_code_slot"),
)

Index("idx_slot_occupancy_code", slot_occupancy.c.submission_code)

# Tracks per-slot delay information (minutes + optional comment) for the Delays tab.
# Keyed by (submission_code, slot_index) — one row per slot; NULL minutes = no active delay.
slot_delays = Table(
    "slot_delays", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("submission_code",  Text,    nullable=False),
    Column("slot_index",       Integer, nullable=False, server_default="0"),
    Column("delay_minutes",    Integer, nullable=False),   # delay in minutes (positive = late start)
    Column("comment",          Text,    nullable=True),    # optional free-text comment
    Column("set_by",           Text,    nullable=True),    # email of staff who set it
    Column("updated_at",       Text,    nullable=False,
           server_default="(datetime('now'))"),
    UniqueConstraint("submission_code", "slot_index", name="uq_slot_delays_code_slot"),
)

Index("idx_slot_delays_code", slot_delays.c.submission_code)

# Tracks schedule changes detected between consecutive published versions.
# Each row is one changed slot (time/room diff). Status: pending → sent | discarded.
schedule_changes = Table(
    "schedule_changes", metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("submission_code",  Text,    nullable=False),
    Column("slot_index",       Integer, nullable=False, server_default="0"),
    Column("from_version",     Text,    nullable=False),   # previous schedule version
    Column("to_version",       Text,    nullable=False),   # new schedule version
    Column("change_types",     Text,    nullable=False),   # comma-separated: time,room,day
    # "before" snapshot
    Column("old_start",        Text,    nullable=True),
    Column("old_end",          Text,    nullable=True),
    Column("old_room",         Text,    nullable=True),
    # "after" snapshot
    Column("new_start",        Text,    nullable=True),
    Column("new_end",          Text,    nullable=True),
    Column("new_room",         Text,    nullable=True),
    # lifecycle
    Column("status",           Text,    nullable=False, server_default="'pending'"),  # pending|sent|discarded
    Column("actioned_by",      Text,    nullable=True),
    Column("detected_at",      Text,    nullable=False,
           server_default="(datetime('now'))"),
    Column("actioned_at",      Text,    nullable=True),
)

Index("idx_schedule_changes_code",   schedule_changes.c.submission_code)
Index("idx_schedule_changes_status", schedule_changes.c.status)

