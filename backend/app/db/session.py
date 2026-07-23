"""
Async database engine, session factory, and the FastAPI dependency.

Usage in a router::

    from app.db.session import get_db

    @router.get("/things")
    async def list_things(db: AsyncSession = Depends(get_db)):
        ...

The engine is created once per process. Sessions are per-request and always
closed (and rolled back on error) by the dependency's context manager.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import settings

# pool_pre_ping avoids handing out a dead connection after Postgres restarts.
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_sec,
    future=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
