"""数据库连接和会话管理"""

import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite+aiosqlite:///{DATA_DIR / 'trips.db'}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.url.get_backend_name() == "sqlite":
            await _ensure_sqlite_columns(conn)


async def _ensure_sqlite_columns(conn):
    """Add lightweight SQLite columns that create_all cannot backfill."""
    result = await conn.execute(text("PRAGMA table_info(attractions_cache)"))
    existing = {row[1] for row in result.fetchall()}
    if "open_hours" not in existing:
        await conn.execute(text("ALTER TABLE attractions_cache ADD COLUMN open_hours VARCHAR(500)"))
    if "tel" not in existing:
        await conn.execute(text("ALTER TABLE attractions_cache ADD COLUMN tel VARCHAR(100)"))


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
