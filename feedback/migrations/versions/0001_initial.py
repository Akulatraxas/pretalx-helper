"""Initial schema — audit log.

Revision ID: 0001
Revises:
Create Date: 2026-09-04
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email  TEXT,
            action      TEXT NOT NULL,
            detail      TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))


def downgrade() -> None:
    op.drop_table("audit_log")
