"""
Async SQLAlchemy engine + session factory.

Usage (FastAPI dependency):
    async with get_db() as db:
        result = await db.execute(select(Scheme))
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # SQLite needs check_same_thread=False; Postgres ignores it
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

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
    """Create all tables (useful for SQLite dev; production uses Alembic)."""
    from backend.db.models import Base  # noqa: F401 — import ensures models are registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
