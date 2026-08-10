"""Add schedule_changes table for Changes column on Delays/Changes page.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-11

Stores per-slot schedule changes detected when a new schedule version is
published. Each row captures the old/new start, end, and room for a given
(submission_code, slot_index) pair. Status lifecycle: pending → sent | discarded.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS schedule_changes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_code  TEXT    NOT NULL,
            slot_index       INTEGER NOT NULL DEFAULT 0,
            from_version     TEXT    NOT NULL,
            to_version       TEXT    NOT NULL,
            change_types     TEXT    NOT NULL,
            old_start        TEXT,
            old_end          TEXT,
            old_room         TEXT,
            new_start        TEXT,
            new_end          TEXT,
            new_room         TEXT,
            status           TEXT    NOT NULL DEFAULT 'pending',
            actioned_by      TEXT,
            detected_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            actioned_at      TEXT
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_schedule_changes_code
        ON schedule_changes(submission_code)
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_schedule_changes_status
        ON schedule_changes(status)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_schedule_changes_status"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_schedule_changes_code"))
    op.execute(sa.text("DROP TABLE IF EXISTS schedule_changes"))
