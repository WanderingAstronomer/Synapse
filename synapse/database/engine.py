"""
synapse.database.engine — Database Connection & Async Helper
=============================================================

**Why this file exists:**
Discord bots run on an ``asyncio`` event loop.  SQLAlchemy + psycopg2 is
**synchronous** — if we call the DB directly from an async context, the
entire bot freezes until the query returns.

The solution is the **Synapse Bridge Pattern**:

    1. An event fires in Discord  (async world).
    2. The Cog calls ``await run_db(some_function, arg1, arg2)``.
    3. ``run_db`` ships the synchronous function to a **thread pool** via
       ``asyncio.to_thread()``.
    4. The DB work happens on a background thread — the event loop stays free.
    5. The result is awaited back in the Cog, which can then reply to the user.

This keeps the code simple (no async engine, no asyncpg) while remaining
fully non-blocking.  It's the best trade-off for a project where readability
matters as much as performance.

Usage::

    from synapse.database.engine import create_db_engine, init_db, run_db

    engine = create_db_engine()          # reads DATABASE_URL from .env
    init_db(engine)                      # CREATE TABLE IF NOT EXISTS …

    # Inside an async Cog method:
    user = await run_db(get_or_create_user, engine, user_id, display_name)
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import contextmanager
from typing import ParamSpec, TypeVar

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from synapse.database.models import Base

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# ---------------------------------------------------------------------------
# Engine creation
# ---------------------------------------------------------------------------
def create_db_engine() -> Engine:
    """Build a SQLAlchemy :class:`Engine` from the ``DATABASE_URL`` env var.

    The connection pool is sized for a small-to-medium community bot:
    * ``pool_size=5`` — five persistent connections.
    * ``max_overflow=10`` — up to 10 extra connections under load.
    * ``pool_timeout=10`` — fail after 10 s if no connection is available.
    * ``pool_recycle=3600`` — recycle connections after 1 hour.

    Returns
    -------
    Engine
        A configured SQLAlchemy engine instance.

    Raises
    ------
    RuntimeError
        If ``DATABASE_URL`` is not set.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set.  "
            "Copy .env.example → .env and set a valid PostgreSQL URL."
        )

    engine = create_engine(
        url,
        echo=False,        # Set True for SQL debugging
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,   # Reconnect stale connections automatically
        pool_timeout=10,      # Fail after 10s instead of hanging forever
        pool_recycle=3600,    # Recycle connections after 1 hour
    )
    logger.info("Database engine created → %s", engine.url.host)
    return engine


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------
def init_db(engine: Engine) -> None:
    """Create all tables defined in :mod:`synapse.database.models`.

    This is safe to call on every startup — ``CREATE TABLE IF NOT EXISTS``
    under the hood.  After creating tables, seeds default settings so the
    dashboard is immediately usable (economy, anti-gaming, quality, display,
    announcements).  Seeding is idempotent — only inserts keys that don't
    already exist.

    .. note::

        In production the schema is managed by Alembic (``alembic upgrade
        head``).  ``create_all`` is retained as a safety net for dev/test
        environments where Alembic may not have run.
    """
    Base.metadata.create_all(engine)
    logger.info("Database tables verified / created.")

    from synapse.database.seed import seed_default_settings

    seed_default_settings(engine)


# ---------------------------------------------------------------------------
# Session helper
# ---------------------------------------------------------------------------
@contextmanager
def get_session(engine: Engine):
    """Yield a :class:`Session` that auto-commits on success and rolls back
    on exception.

    Usage::

        with get_session(engine) as session:
            session.add(User(id=123, discord_name="drew"))
            # commit happens automatically on block exit
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Async bridge — THE key pattern in Synapse
# ---------------------------------------------------------------------------
async def run_db(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Run a **synchronous** database function on a background thread.

    This is the "Neural Bridge" between Discord's async world and
    SQLAlchemy's synchronous world.  Every DB call in a Cog should go
    through this wrapper::

        result = await run_db(my_sync_db_function, engine, user_id)

    Under the hood it calls :func:`asyncio.to_thread`, which schedules
    *func* on the default ``ThreadPoolExecutor`` so the bot's event loop
    is never blocked.

    Parameters
    ----------
    func:
        Any sync callable (typically a function that opens a session and
        runs queries).
    *args, **kwargs:
        Forwarded to *func*.

    Returns
    -------
    T
        Whatever *func* returns.
    """
    return await asyncio.to_thread(func, *args, **kwargs)
