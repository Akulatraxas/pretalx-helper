"""Initial schema — resources, assignments, comments, audit log.

Revision ID: 0001
Revises:
Create Date: 2026-07-21

All CREATE TABLE statements use IF NOT EXISTS so this migration is safe to
run against a pre-Alembic database that already has the tables. In that case
db.py's init_db() will detect the existing tables and stamp the DB at head
instead of running this migration, but the guard is here for robustness.
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
        CREATE TABLE IF NOT EXISTS resources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            amount      INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS resource_departments (
            resource_id INTEGER NOT NULL
                REFERENCES resources(id) ON DELETE CASCADE,
            department  TEXT NOT NULL,
            PRIMARY KEY (resource_id, department)
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS submission_resources (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_code     TEXT NOT NULL,
            resource_id         INTEGER NOT NULL
                REFERENCES resources(id) ON DELETE CASCADE,
            note                TEXT,
            department_override TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (submission_code, resource_id)
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS submission_comments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_code TEXT NOT NULL,
            text            TEXT NOT NULL,
            department      TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email  TEXT,
            action      TEXT NOT NULL,
            detail      TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_sub_resources_code
        ON submission_resources(submission_code)
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_sub_comments_code
        ON submission_comments(submission_code)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_sub_comments_code"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_sub_resources_code"))
    op.drop_table("audit_log")
    op.drop_table("submission_comments")
    op.drop_table("submission_resources")
    op.drop_table("resource_departments")
    op.drop_table("resources")
