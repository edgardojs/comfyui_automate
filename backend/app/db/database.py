"""PostgreSQL database setup with SQLAlchemy async engine and session management.

Uses PostgreSQL as the default database backend. SQLite is supported for
local testing/development by setting DATABASE_URL to an sqlite+aiosqlite URL.
PostgreSQL offers native support for ENUM, BOOLEAN, JSONB, and ARRAY types
with proper constraints and indexing.

Environment variables:
    DATABASE_URL: SQLAlchemy async connection string.
        Default: postgresql+asyncpg://sprite_user:sprite_pass@localhost:5432/sprite_prompt_generator
        For local testing: sqlite+aiosqlite:///:memory:

Column type notes:
    - ENUM types (reference_status, reference_angle, lora_job_status) are
      created as PostgreSQL ENUM types with CHECK constraints. On SQLite they
      fall back to VARCHAR with no constraint enforcement.
    - BOOLEAN replaces the previous Integer(0/1) pattern for is_favorite.
    - JSONB replaces Text columns storing JSON strings for attributes,
      locked_fields, target_perspective, and animations.
    - ARRAY(String) is used for target_perspective and animations on PostgreSQL,
      with JSONB fallback on SQLite.
"""

import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Database URL — configurable via DATABASE_URL env var
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://sprite_user:sprite_pass@localhost:5432/sprite_prompt_generator",
)

# Detect if we're using SQLite (for test/development compatibility)
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

# ---------------------------------------------------------------------------
# PostgreSQL ENUM types
# ---------------------------------------------------------------------------

ReferenceStatusEnum = Enum(
    "pending",
    "accepted",
    "rejected",
    "maybe",
    name="reference_status",
    create_constraint=True,
)

ReferenceAngleEnum = Enum(
    "front",
    "side",
    "back",
    "three-quarter",
    name="reference_angle",
    create_constraint=True,
)

LoraJobStatusEnum = Enum(
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="lora_job_status",
    create_constraint=True,
)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class."""


# ---------------------------------------------------------------------------
# Helper: dialect-aware column types
# ---------------------------------------------------------------------------


class JSONEncodedDict(TypeDecorator):
    """Represents a JSON dict stored as JSONB on PostgreSQL or Text on SQLite."""

    impl = Text
    cache = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is not None and dialect.name != "postgresql":
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and dialect.name != "postgresql":
            return json.loads(value)
        return value


class JSONEncodedList(TypeDecorator):
    """Represents a JSON list stored as JSONB on PostgreSQL or Text on SQLite."""

    impl = Text
    cache = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is not None and dialect.name != "postgresql":
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and dialect.name != "postgresql":
            return json.loads(value)
        return value


class StringArray(TypeDecorator):
    """Represents a list of strings stored as ARRAY(String) on PostgreSQL
    or as JSON-encoded Text on SQLite."""

    impl = Text
    cache = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is not None and dialect.name != "postgresql":
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and dialect.name != "postgresql":
            return json.loads(value)
        return value


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class PresetRow(Base):
    """SQLAlchemy model for the presets table."""

    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    preset_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    attributes = Column(JSONEncodedDict, nullable=False, default=dict)
    locked_fields = Column(JSONEncodedList, nullable=False, default=list)
    positive_template_id = Column(String, nullable=False, default="front_view_sprite")
    negative_profile_id = Column(
        String, nullable=False, default="general_sprite_cleanup"
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PromptHistoryRow(Base):
    """SQLAlchemy model for the prompt_history table."""

    __tablename__ = "prompt_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    generation_id = Column(String, nullable=False, index=True)
    positive_prompt = Column(Text, nullable=False)
    negative_prompt = Column(Text, nullable=False)
    attributes = Column(JSONEncodedDict, nullable=False, default=dict)
    template_id = Column(String, nullable=True)
    negative_profile_id = Column(String, nullable=True)
    is_favorite = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    comfyui_prompt_id = Column(String, nullable=True, index=True)
    comfyui_images = Column(JSONEncodedDict, nullable=True, default=list)


class CharacterProfileRow(Base):
    """SQLAlchemy model for the character_profiles table."""

    __tablename__ = "character_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(String, unique=True, nullable=False, index=True)
    project_name = Column(String, nullable=False)
    character_name = Column(String, nullable=False)
    species = Column(String, nullable=True)
    character_class = Column(String, nullable=True)
    weapon = Column(String, nullable=True)
    armor = Column(String, nullable=True)
    color_palette = Column(String, nullable=True)
    art_style = Column(String, nullable=True)
    target_sprite_size = Column(String, nullable=True)
    target_perspective = Column(
        StringArray, nullable=False, default=lambda: ["front", "side", "back", "three-quarter"]
    )
    animations = Column(
        StringArray, nullable=False, default=lambda: ["idle", "walk", "attack", "hurt"]
    )
    trigger_token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ReferenceImageRow(Base):
    """SQLAlchemy model for the reference_images table."""

    __tablename__ = "reference_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(String, unique=True, nullable=False, index=True)
    character_id = Column(
        String, ForeignKey("character_profiles.character_id"), nullable=False
    )
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    status = Column(
        ReferenceStatusEnum,
        nullable=False,
        default="pending",
    )
    angle = Column(ReferenceAngleEnum, nullable=True)
    caption = Column(String, nullable=True)
    rejection_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LoraJobRow(Base):
    """SQLAlchemy model for the lora_jobs table (Milestone 8)."""

    __tablename__ = "lora_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, unique=True, nullable=False, index=True)
    character_id = Column(
        String, ForeignKey("character_profiles.character_id"), nullable=False
    )
    preset_id = Column(String, nullable=True)
    base_model = Column(String(512), nullable=False, default="stabilityai/stable-diffusion-xl-base-1.0")
    learning_rate = Column(Float, nullable=False, default=0.0002)
    epochs = Column(Integer, nullable=False, default=18)
    preview_interval = Column(Integer, nullable=False, default=2)
    output_format = Column(String(50), nullable=False, default="safetensors")
    lora_strength = Column(Float, nullable=False, default=1.0)
    custom_args = Column(JSONEncodedDict, nullable=True)
    status = Column(
        LoraJobStatusEnum,
        nullable=False,
        default="pending",
    )
    output_lora_path = Column(String, nullable=True)
    log_output = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AuditLogRow(Base):
    """SQLAlchemy model for the audit_log table.

    Records sensitive operations for security and compliance auditing.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    action = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    details = Column(JSONEncodedDict, nullable=True, default=dict)
    client_ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    request_id = Column(String, nullable=True)


# ---------------------------------------------------------------------------
# Async engine and session factory
# ---------------------------------------------------------------------------

_engine_kwargs: dict = {"echo": False}
if _IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all database tables if they don't exist.

    On PostgreSQL, this also creates ENUM types.
    On SQLite, this enables WAL mode for better concurrent write performance.

    Schema migrations are now managed by Alembic. For existing databases
    that were created before Alembic was adopted, use:
        alembic stamp head
    to mark the current schema as the baseline without running migrations.

    For new databases, this function uses create_all() as a fallback to
    create all tables, then stamps the Alembic version to head.
    """
    async with engine.begin() as conn:
        if _IS_SQLITE:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)

    # Stamp Alembic to head for new databases (tables already created by create_all)
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command
        import os

        alembic_cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "alembic.ini",
        )
        if os.path.exists(alembic_cfg_path):
            alembic_cfg = AlembicConfig(alembic_cfg_path)
            command.stamp(alembic_cfg, "head")
    except Exception:
        # If Alembic stamping fails (e.g., already stamped), that's fine
        pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional database session."""
    async with async_session() as session:
        yield session
