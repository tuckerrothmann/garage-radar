"""
Garage Radar — Database layer.

Async engine + session factory using SQLAlchemy 2.0 async API.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from garage_radar.config import get_settings
from garage_radar.db.models import Base

_engine = None
_session_factory = None

_SCHEMA_READINESS_QUERY = text(
    """
    SELECT current_bid, auction_end_at, time_remaining_text, cluster_insufficient_data
    FROM active_listings_with_delta
    LIMIT 0
    """
)


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        # Convert sync postgres:// to async postgresql+asyncpg://
        url = settings.database_url.replace(
            "postgresql://", "postgresql+asyncpg://"
        ).replace("postgres://", "postgresql+asyncpg://")
        _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def create_all_tables():
    """Create all tables. Dev convenience — use Alembic for production."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_schema_ready() -> None:
    """
    Fail fast if the migration-managed schema is not present.

    In particular, this verifies the latest `active_listings_with_delta` view
    shape exists, which catches the partial-schema case where tables exist but
    Alembic-managed views have not been applied yet.
    """
    async with get_engine().connect() as conn:
        try:
            await conn.execute(_SCHEMA_READINESS_QUERY)
        except Exception as exc:  # pragma: no cover - exercised via caller tests
            raise RuntimeError(
                "Database schema is not ready. Run `python scripts/dev.py migrate` "
                "or `alembic upgrade head` before running ingestion."
            ) from exc
