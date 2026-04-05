"""
Alembic migration environment for Garage Radar.

Key design decisions:
  - DB URL is read from environment via Settings (never hardcoded in alembic.ini)
  - Migrations use the sync psycopg2 driver; the app uses asyncpg
  - Base.metadata is imported from db.models for autogenerate support
  - compare_type=True detects column type changes
  - SQLAlchemy enums are rendered as native Postgres ENUM types
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Path setup ────────────────────────────────────────────────────────────────
# Ensure the backend package is importable regardless of cwd
_BACKEND_DIR = Path(__file__).parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ── Import models and settings ────────────────────────────────────────────────
from garage_radar.config import get_settings  # noqa: E402
from garage_radar.db.models import Base       # noqa: E402

# ── Alembic config object ─────────────────────────────────────────────────────
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata — gives autogenerate the full model state to diff against
target_metadata = Base.metadata


# ── URL helpers ───────────────────────────────────────────────────────────────

def _sync_db_url() -> str:
    """
    Return a sync (psycopg2) database URL for Alembic.

    The app uses asyncpg (postgresql+asyncpg://...). Alembic needs the sync
    driver. We normalise both formats to postgresql://...
    """
    settings = get_settings()
    url = settings.database_url
    # Strip async driver suffix if present
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


# ── Migration modes ───────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Offline mode: emit SQL to stdout without connecting to the DB.

    Useful for reviewing migration SQL before applying it, or for
    environments where you can't connect at migration-generation time.

    Usage: alembic upgrade head --sql
    """
    url = _sync_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online mode: connect to the DB and apply migrations directly.

    Usage: alembic upgrade head
    """
    # Override the sqlalchemy.url in the ini config with our env-sourced URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _sync_db_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pooling for migration runs
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,       # Detect column type changes
            compare_server_default=True,  # Detect server default changes
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
