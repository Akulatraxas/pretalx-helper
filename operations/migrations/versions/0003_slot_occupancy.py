"""Add slot_occupancy table for Occupancy tab room rating.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06

Tracks per-slot occupancy ratings (Empty/Low/Medium/High/Full) entered by
Conops staff when they visit rooms during events. Only one measurement is
stored per (submission_code, slot_index) — newer ratings overwrite old ones.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS slot_occupancy (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_code  TEXT    NOT NULL,
            slot_index       INTEGER NOT NULL DEFAULT 0,
            rating           TEXT    NOT NULL,
            rated_by         TEXT,
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (submission_code, slot_index)
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_slot_occupancy_code
        ON slot_occupancy(submission_code)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_slot_occupancy_code"))
    op.execute(sa.text("DROP TABLE IF EXISTS slot_occupancy"))
