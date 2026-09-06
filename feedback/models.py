"""
models.py — SQLAlchemy Core table metadata for Feedback Viewer.

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
    Integer, Text,
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

audit_log = Table(
    "audit_log", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("user_email", Text,    nullable=True),
    Column("action",     Text,    nullable=False),
    Column("detail",     Text,    nullable=True),
    Column("created_at", Text,    nullable=False,
           server_default="(datetime('now'))"),
)
