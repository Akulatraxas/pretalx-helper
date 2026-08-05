"""Add operation_events table for Operations tab slot tracking.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

Adds a new table that tracks per-slot operational state for the Operations
tab: who has taken an event (assigned_to email) and whether it has been
marked as completed.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS operation_events (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_code  TEXT    NOT NULL,
            slot_index       INTEGER NOT NULL DEFAULT 0,
            assigned_to      TEXT,
            is_completed     INTEGER NOT NULL DEFAULT 0,
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (submission_code, slot_index)
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_op_events_code
        ON operation_events(submission_code)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_op_events_code"))
    op.execute(sa.text("DROP TABLE IF EXISTS operation_events"))
