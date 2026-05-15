"""SQLite database setup with SQLAlchemy async engine and session management."""

import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# SQLite database file path — configurable via DATABASE_URL env var
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///./sprite_prompt_generator.db"
)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class."""


class PresetRow(Base):
    """SQLAlchemy model for the presets table."""

    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    preset_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    attributes_json = Column(Text, nullable=False, default="{}")
    locked_fields_json = Column(Text, nullable=False, default="[]")
    positive_template_id = Column(String, nullable=False, default="front_view_sprite")
    negative_profile_id = Column(
        String, nullable=False, default="general_sprite_cleanup"
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PromptHistoryRow(Base):
    """SQLAlchemy model for the prompt_history table."""

    __tablename__ = "prompt_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    generation_id = Column(String, unique=True, nullable=False, index=True)
    positive_prompt = Column(Text, nullable=False)
    negative_prompt = Column(Text, nullable=False)
    attributes_json = Column(Text, nullable=False, default="{}")
    template_id = Column(String, nullable=True)
    negative_profile_id = Column(String, nullable=True)
    is_favorite = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# Async engine and session factory
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all database tables if they don't exist and enable WAL mode."""
    async with engine.begin() as conn:
        # Enable WAL mode for better concurrent write performance with SQLite
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional database session."""
    async with async_session() as session:
        yield session
