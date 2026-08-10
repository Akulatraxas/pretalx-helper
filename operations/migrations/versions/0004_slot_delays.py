"""Add slot_delays table for Delays/Changes tab.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-10

Tracks per-slot delay information (minutes + optional comment) set by
Conops staff when an event starts late or its schedule changes.
One row per (submission_code, slot_index) — newer delays overwrite old ones.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS slot_delays (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_code  TEXT    NOT NULL,
            slot_index       INTEGER NOT NULL DEFAULT 0,
            delay_minutes    INTEGER NOT NULL,
            comment          TEXT,
            set_by           TEXT,
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (submission_code, slot_index)
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_slot_delays_code
        ON slot_delays(submission_code)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_slot_delays_code"))
    op.execute(sa.text("DROP TABLE IF EXISTS slot_delays"))
