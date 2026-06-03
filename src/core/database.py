"""Async SQLAlchemy database engine and session factory.

All database access uses async sessions via asyncpg.
The `get_db` dependency yields a session that is automatically committed
on success and rolled back on any exception — no caller needs to manage
transactions manually for the common case.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings

# ── Engine ────────────────────────────────────────────────────────────────────
# Created lazily so tests can patch get_settings() before the module is used.
_engine: Any = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> Any:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            # asyncpg pool settings — reasonable defaults for Railway (512 MB RAM)
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # recycle stale connections
            pool_recycle=1800,   # recycle connections older than 30 min
            echo=settings.is_development,
        )
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (or initialize) the session factory."""
    _get_engine()  # ensures _session_factory is set
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a database session.

    Commits the transaction on normal exit.
    Rolls back and re-raises on any exception so no partial writes leak.

    Handles the case where an endpoint handler internally catches a DB exception
    and returns an error response (e.g. 503).  In that scenario the session is
    left in DEACTIVE state after a rolled-back flush, and calling commit() would
    raise PendingRollbackError.  We detect that case and perform a clean rollback
    rather than letting the error propagate through the ASGI transport.

    Usage::

        @router.post("/")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    from sqlalchemy.exc import PendingRollbackError

    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except PendingRollbackError:
            # The session was internally invalidated by a prior DB error that the
            # endpoint handler caught and converted to an HTTP error response.
            # Roll back to clean state; no data should be committed in this case.
            try:
                await session.rollback()
            except Exception:
                pass  # Best-effort; session pool will discard the connection.
        except Exception:
            await session.rollback()
            raise


async def close_engine() -> None:
    """Dispose of the engine connection pool.

    Called in the FastAPI lifespan shutdown handler.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
