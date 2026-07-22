"""
migrations/env.py — Alembic runtime environment.

Key settings for SQLite:
  • render_as_batch=True  — emulates ALTER TABLE via table-copy (SQLite limitation)
  • DB URL read from DB_PATH env var so it matches the running app exactly
  • metadata imported from models.py for autogenerate support
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Make sure the app package is importable when running alembic from the CLI.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import metadata as target_metadata  # noqa: E402

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to the .ini file values.
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the sqlalchemy.url with the value from the environment.
DB_PATH = os.environ.get("DB_PATH", "/data/operations.db")
config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")


# ---------------------------------------------------------------------------
# Offline mode (generate SQL without connecting)
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,           # Required for SQLite ALTER TABLE
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode (connect and migrate)
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,        # No pool needed for migration runs
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,       # Required for SQLite ALTER TABLE
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
