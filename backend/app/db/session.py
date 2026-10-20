"""Async SQLAlchemy session for request-scoped database work.

The engine uses ``DATABASE_URL`` and the asyncpg driver. ``get_db`` yields
one session per call and commits only when the caller finishes without an
error.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the shared async engine, creating it on first use.

    Returns:
        The process-wide async engine.

    Raises:
        ValueError: ``DATABASE_URL`` is empty. The URL must use the
            ``postgresql+asyncpg`` driver.
    """
    global _engine
    if _engine is None:
        database_url = get_settings().DATABASE_URL.strip()
        if database_url == "":
            raise ValueError("DATABASE_URL is not configured.")
        _engine = create_async_engine(database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory bound to :func:`get_engine`."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session, then commit, roll back on failure, and close.

    Yields:
        An open :class:`AsyncSession` for the current unit of work.

    The session is committed after the caller finishes successfully. Any
    exception rolls the transaction back. The session is closed in either
    case.
    """
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_optional_db() -> AsyncGenerator[AsyncSession | None, None]:
    """Yield a session when ``DATABASE_URL`` is set, otherwise ``None``.

    Recommendation logging uses this so a missing database does not block
    the clothing response. When a session is yielded, it follows the same
    commit, rollback, and close rules as :func:`get_db`.
    """
    if get_settings().DATABASE_URL.strip() == "":
        yield None
        return
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
