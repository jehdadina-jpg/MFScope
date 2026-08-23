"""
Async SQLAlchemy engine + session factory.

SQLite tuning
-------------
The development database is a 380 MB file with a 3M-row NAV table, and the
ingestion pipeline writes to it from many coroutines at once.  Out of the box
that produces ``database is locked`` the moment a bulk insert overlaps
anything else, because SQLite defaults to rollback-journal mode with a
five-second busy timeout.  The pragmas below fix that properly:

* ``journal_mode=WAL`` lets readers continue while a writer commits, which is
  exactly the API-serving-while-refreshing case.
* ``busy_timeout`` makes a contended writer wait instead of failing.
* ``synchronous=NORMAL`` is the standard, safe-under-WAL durability setting.

They are applied per connection, so pooled connections all get them.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

IS_SQLITE = settings.database_url.startswith("sqlite")

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 60} if IS_SQLITE else {},
)

if IS_SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _apply_sqlite_pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=60000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA cache_size=-65536")   # 64 MB page cache
            cursor.execute("PRAGMA temp_store=MEMORY")
        finally:
            cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables and reconcile additive schema changes."""
    from backend.db.migrate import reconcile_schema

    await reconcile_schema()
