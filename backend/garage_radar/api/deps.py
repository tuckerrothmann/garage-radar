"""
FastAPI dependency injection helpers.

Usage:
    @router.get("/foo")
    async def foo(session: DBSession):
        ...
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.db import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for the duration of a request."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# Annotated shorthand for router signatures
from typing import Annotated
from fastapi import Depends

DBSession = Annotated[AsyncSession, Depends(get_db)]
