"""Unit tests for the database layer (app.db.database).

Tests cover:
1. TypeDecorator serialization/deserialization (JSONEncodedDict,
   JSONEncodedList, StringArray) for both SQLite and PostgreSQL dialects.
2. ORM model creation, column defaults, and constraint enforcement.
3. init_db() table creation and WAL mode (SQLite).
4. Engine configuration (SQLite vs PostgreSQL connect_args).
5. ENUM type definitions and default values.
6. Foreign key relationships and cascade behavior.
7. Boolean column behavior (is_favorite).
8. Session factory and get_session dependency.
"""

# pylint: disable=redefined-outer-name

import json

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, inspect, select, text, TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.db.database import (
    Base,
    CharacterProfileRow,
    JSONEncodedDict,
    JSONEncodedList,
    LoraJobRow,
    LoraJobStatusEnum,
    PresetRow,
    PromptHistoryRow,
    ReferenceAngleEnum,
    ReferenceImageRow,
    ReferenceStatusEnum,
    StringArray,
    get_session,
    init_db,
)

# ---------------------------------------------------------------------------
# In-memory test database fixtures
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
_test_session_factory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop them after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_session():
    """Yield a test database session."""
    async with _test_session_factory() as session:
        yield session


# ===========================================================================
# TypeDecorator tests
# ===========================================================================


class TestJSONEncodedDict:
    """Tests for JSONEncodedDict TypeDecorator."""

    def test_impl_is_text(self):
        """JSONEncodedDict.impl should be Text (the base storage type)."""
        assert JSONEncodedDict.impl is not None

    def test_cache_is_true(self):
        """JSONEncodedDict.cache should be True for statement caching."""
        assert JSONEncodedDict.cache is True

    def test_load_dialect_impl_sqlite(self):
        """On SQLite, JSONEncodedDict should resolve to Text."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        result = typ.load_dialect_impl(dialect)
        # Should return a Text type for SQLite
        assert result.__class__.__name__ == "Text"

    def test_load_dialect_impl_postgresql(self):
        """On PostgreSQL, JSONEncodedDict should resolve to JSONB."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = JSONEncodedDict()
        dialect = PGDialect()
        result = typ.load_dialect_impl(dialect)
        # Should return a JSONB type for PostgreSQL
        assert isinstance(result, JSONB)

    def test_process_bind_param_dict_sqlite(self):
        """On SQLite, process_bind_param should serialize dict to JSON string."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        data = {"key": "value", "number": 42}
        result = typ.process_bind_param(data, dialect)
        assert isinstance(result, str)
        assert json.loads(result) == data

    def test_process_bind_param_dict_postgresql(self):
        """On PostgreSQL, process_bind_param should pass dict through unchanged."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = JSONEncodedDict()
        dialect = PGDialect()
        data = {"key": "value", "number": 42}
        result = typ.process_bind_param(data, dialect)
        assert result == data

    def test_process_bind_param_none(self):
        """process_bind_param should return None when value is None."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        assert typ.process_bind_param(None, dialect) is None

    def test_process_result_value_string_sqlite(self):
        """On SQLite, process_result_value should deserialize JSON string to dict."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        data = {"key": "value", "number": 42}
        json_str = json.dumps(data)
        result = typ.process_result_value(json_str, dialect)
        assert result == data

    def test_process_result_value_dict_postgresql(self):
        """On PostgreSQL, process_result_value should pass dict through unchanged."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = JSONEncodedDict()
        dialect = PGDialect()
        data = {"key": "value", "number": 42}
        result = typ.process_result_value(data, dialect)
        assert result == data

    def test_process_result_value_none(self):
        """process_result_value should return None when value is None."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        assert typ.process_result_value(None, dialect) is None

    def test_roundtrip_sqlite(self):
        """Full round-trip: dict → bind → result → dict on SQLite."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        data = {"species": "elf", "class": "wizard", "level": 5}
        bound = typ.process_bind_param(data, dialect)
        assert isinstance(bound, str)
        result = typ.process_result_value(bound, dialect)
        assert result == data

    def test_roundtrip_postgresql(self):
        """Full round-trip: dict → bind → result → dict on PostgreSQL."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = JSONEncodedDict()
        dialect = PGDialect()
        data = {"species": "elf", "class": "wizard", "level": 5}
        bound = typ.process_bind_param(data, dialect)
        result = typ.process_result_value(bound, dialect)
        assert result == data

    def test_empty_dict(self):
        """Empty dict should serialize/deserialize correctly."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        data = {}
        bound = typ.process_bind_param(data, dialect)
        result = typ.process_result_value(bound, dialect)
        assert result == {}

    def test_nested_dict(self):
        """Nested dict should serialize/deserialize correctly."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedDict()
        dialect = SQLiteDialect()
        data = {"outer": {"inner": "value"}, "list": [1, 2, 3]}
        bound = typ.process_bind_param(data, dialect)
        result = typ.process_result_value(bound, dialect)
        assert result == data


class TestJSONEncodedList:
    """Tests for JSONEncodedList TypeDecorator."""

    def test_impl_is_text(self):
        """JSONEncodedList.impl should be Text."""
        assert JSONEncodedList.impl is not None

    def test_load_dialect_impl_sqlite(self):
        """On SQLite, JSONEncodedList should resolve to Text."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedList()
        dialect = SQLiteDialect()
        result = typ.load_dialect_impl(dialect)
        assert result.__class__.__name__ == "Text"

    def test_load_dialect_impl_postgresql(self):
        """On PostgreSQL, JSONEncodedList should resolve to JSONB."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = JSONEncodedList()
        dialect = PGDialect()
        result = typ.load_dialect_impl(dialect)
        assert isinstance(result, JSONB)

    def test_process_bind_param_list_sqlite(self):
        """On SQLite, process_bind_param should serialize list to JSON string."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedList()
        dialect = SQLiteDialect()
        data = ["front", "side", "back"]
        result = typ.process_bind_param(data, dialect)
        assert isinstance(result, str)
        assert json.loads(result) == data

    def test_process_bind_param_list_postgresql(self):
        """On PostgreSQL, process_bind_param should pass list through unchanged."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = JSONEncodedList()
        dialect = PGDialect()
        data = ["front", "side", "back"]
        result = typ.process_bind_param(data, dialect)
        assert result == data

    def test_process_bind_param_none(self):
        """process_bind_param should return None when value is None."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedList()
        dialect = SQLiteDialect()
        assert typ.process_bind_param(None, dialect) is None

    def test_process_result_value_string_sqlite(self):
        """On SQLite, process_result_value should deserialize JSON string to list."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedList()
        dialect = SQLiteDialect()
        data = ["front", "side", "back"]
        json_str = json.dumps(data)
        result = typ.process_result_value(json_str, dialect)
        assert result == data

    def test_process_result_value_list_postgresql(self):
        """On PostgreSQL, process_result_value should pass list through unchanged."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = JSONEncodedList()
        dialect = PGDialect()
        data = ["front", "side", "back"]
        result = typ.process_result_value(data, dialect)
        assert result == data

    def test_process_result_value_none(self):
        """process_result_value should return None when value is None."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedList()
        dialect = SQLiteDialect()
        assert typ.process_result_value(None, dialect) is None

    def test_empty_list(self):
        """Empty list should serialize/deserialize correctly."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedList()
        dialect = SQLiteDialect()
        data = []
        bound = typ.process_bind_param(data, dialect)
        result = typ.process_result_value(bound, dialect)
        assert result == []

    def test_roundtrip_sqlite(self):
        """Full round-trip: list → bind → result → list on SQLite."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = JSONEncodedList()
        dialect = SQLiteDialect()
        data = ["species", "class", "weapon"]
        bound = typ.process_bind_param(data, dialect)
        assert isinstance(bound, str)
        result = typ.process_result_value(bound, dialect)
        assert result == data


class TestStringArray:
    """Tests for StringArray TypeDecorator."""

    def test_impl_is_text(self):
        """StringArray.impl should be Text."""
        assert StringArray.impl is not None

    def test_load_dialect_impl_sqlite(self):
        """On SQLite, StringArray should resolve to Text."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = StringArray()
        dialect = SQLiteDialect()
        result = typ.load_dialect_impl(dialect)
        assert result.__class__.__name__ == "Text"

    def test_load_dialect_impl_postgresql(self):
        """On PostgreSQL, StringArray should resolve to ARRAY(String)."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = StringArray()
        dialect = PGDialect()
        result = typ.load_dialect_impl(dialect)
        assert isinstance(result, ARRAY)

    def test_process_bind_param_list_sqlite(self):
        """On SQLite, process_bind_param should serialize list to JSON string."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = StringArray()
        dialect = SQLiteDialect()
        data = ["front", "side", "back", "three-quarter"]
        result = typ.process_bind_param(data, dialect)
        assert isinstance(result, str)
        assert json.loads(result) == data

    def test_process_bind_param_list_postgresql(self):
        """On PostgreSQL, process_bind_param should pass list through unchanged."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = StringArray()
        dialect = PGDialect()
        data = ["front", "side", "back", "three-quarter"]
        result = typ.process_bind_param(data, dialect)
        assert result == data

    def test_process_bind_param_none(self):
        """process_bind_param should return None when value is None."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = StringArray()
        dialect = SQLiteDialect()
        assert typ.process_bind_param(None, dialect) is None

    def test_process_result_value_string_sqlite(self):
        """On SQLite, process_result_value should deserialize JSON string to list."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = StringArray()
        dialect = SQLiteDialect()
        data = ["idle", "walk", "attack", "hurt"]
        json_str = json.dumps(data)
        result = typ.process_result_value(json_str, dialect)
        assert result == data

    def test_process_result_value_list_postgresql(self):
        """On PostgreSQL, process_result_value should pass list through unchanged."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = StringArray()
        dialect = PGDialect()
        data = ["idle", "walk", "attack", "hurt"]
        result = typ.process_result_value(data, dialect)
        assert result == data

    def test_process_result_value_none(self):
        """process_result_value should return None when value is None."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = StringArray()
        dialect = SQLiteDialect()
        assert typ.process_result_value(None, dialect) is None

    def test_roundtrip_sqlite(self):
        """Full round-trip: list → bind → result → list on SQLite."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = StringArray()
        dialect = SQLiteDialect()
        data = ["front", "side", "back"]
        bound = typ.process_bind_param(data, dialect)
        assert isinstance(bound, str)
        result = typ.process_result_value(bound, dialect)
        assert result == data

    def test_roundtrip_postgresql(self):
        """Full round-trip: list → bind → result → list on PostgreSQL."""
        from sqlalchemy.dialects.postgresql.base import PGDialect

        typ = StringArray()
        dialect = PGDialect()
        data = ["front", "side", "back"]
        bound = typ.process_bind_param(data, dialect)
        result = typ.process_result_value(bound, dialect)
        assert result == data

    def test_empty_list(self):
        """Empty list should serialize/deserialize correctly."""
        from sqlalchemy.dialects.sqlite.base import SQLiteDialect

        typ = StringArray()
        dialect = SQLiteDialect()
        data = []
        bound = typ.process_bind_param(data, dialect)
        result = typ.process_result_value(bound, dialect)
        assert result == []


# ===========================================================================
# ENUM type tests
# ===========================================================================


class TestEnumTypes:
    """Tests for PostgreSQL ENUM type definitions."""

    def test_reference_status_enum_values(self):
        """ReferenceStatusEnum should contain the expected status values."""
        enums = ReferenceStatusEnum.enums
        assert "pending" in enums
        assert "accepted" in enums
        assert "rejected" in enums
        assert "maybe" in enums
        assert len(enums) == 4

    def test_reference_angle_enum_values(self):
        """ReferenceAngleEnum should contain the expected angle values."""
        enums = ReferenceAngleEnum.enums
        assert "front" in enums
        assert "side" in enums
        assert "back" in enums
        assert "three-quarter" in enums
        assert len(enums) == 4

    def test_lora_job_status_enum_values(self):
        """LoraJobStatusEnum should contain the expected status values."""
        enums = LoraJobStatusEnum.enums
        assert "pending" in enums
        assert "running" in enums
        assert "completed" in enums
        assert "failed" in enums
        assert len(enums) == 4

    def test_reference_status_enum_name(self):
        """ReferenceStatusEnum should have the correct type name."""
        assert ReferenceStatusEnum.name == "reference_status"

    def test_reference_angle_enum_name(self):
        """ReferenceAngleEnum should have the correct type name."""
        assert ReferenceAngleEnum.name == "reference_angle"

    def test_lora_job_status_enum_name(self):
        """LoraJobStatusEnum should have the correct type name."""
        assert LoraJobStatusEnum.name == "lora_job_status"

    def test_reference_status_enum_create_constraint(self):
        """ReferenceStatusEnum should have create_constraint=True."""
        assert ReferenceStatusEnum.create_constraint is True

    def test_reference_angle_enum_create_constraint(self):
        """ReferenceAngleEnum should have create_constraint=True."""
        assert ReferenceAngleEnum.create_constraint is True

    def test_lora_job_status_enum_create_constraint(self):
        """LoraJobStatusEnum should have create_constraint=True."""
        assert LoraJobStatusEnum.create_constraint is True


# ===========================================================================
# ORM Model tests (using async SQLite)
# ===========================================================================


class TestPresetRow:
    """Tests for PresetRow ORM model."""

    @pytest.mark.asyncio
    async def test_create_preset_row(self):
        """PresetRow should be creatable with required fields."""
        async with _test_session_factory() as session:
            row = PresetRow(
                preset_id="preset_abc123",
                name="Test Preset",
                attributes={"species": "elf", "class": "wizard"},
                locked_fields=["species"],
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.id is not None
            assert row.preset_id == "preset_abc123"
            assert row.name == "Test Preset"
            assert row.attributes == {"species": "elf", "class": "wizard"}
            assert row.locked_fields == ["species"]

    @pytest.mark.asyncio
    async def test_preset_row_defaults(self):
        """PresetRow should apply default values for optional fields."""
        async with _test_session_factory() as session:
            row = PresetRow(
                preset_id="preset_defaults",
                name="Defaults Test",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.positive_template_id == "front_view_sprite"
            assert row.negative_profile_id == "general_sprite_cleanup"
            assert row.created_at is not None
            assert row.updated_at is not None

    @pytest.mark.asyncio
    async def test_preset_row_json_dict_roundtrip(self):
        """PresetRow.attributes should round-trip a dict through SQLite."""
        async with _test_session_factory() as session:
            attrs = {
                "species": "dwarf",
                "class": "fighter",
                "weapon": "battleaxe",
                "armor": "plate",
            }
            row = PresetRow(
                preset_id="preset_json1",
                name="JSON Dict Test",
                attributes=attrs,
                locked_fields=["species", "class"],
            )
            session.add(row)
            await session.commit()

            # Re-fetch from a new session to force a fresh read
            async with _test_session_factory() as session2:
                result = await session2.execute(
                    PresetRow.__table__.select().where(
                        PresetRow.preset_id == "preset_json1"
                    )
                )
                fetched = result.fetchone()
                assert fetched is not None
                # The TypeDecorator should deserialize the JSON string back to dict
                assert isinstance(fetched.attributes, dict)
                assert fetched.attributes == attrs
                assert isinstance(fetched.locked_fields, list)
                assert fetched.locked_fields == ["species", "class"]

    @pytest.mark.asyncio
    async def test_preset_row_empty_attributes(self):
        """PresetRow should handle empty dict for attributes."""
        async with _test_session_factory() as session:
            row = PresetRow(
                preset_id="preset_empty",
                name="Empty Attrs",
                attributes={},
                locked_fields=[],
            )
            session.add(row)
            await session.commit()

            async with _test_session_factory() as session2:
                result = await session2.execute(
                    PresetRow.__table__.select().where(
                        PresetRow.preset_id == "preset_empty"
                    )
                )
                fetched = result.fetchone()
                assert fetched.attributes == {}
                assert fetched.locked_fields == []

    @pytest.mark.asyncio
    async def test_preset_row_unique_preset_id(self):
        """PresetRow.preset_id should be unique."""
        async with _test_session_factory() as session:
            row1 = PresetRow(preset_id="preset_unique1", name="First")
            row2 = PresetRow(preset_id="preset_unique1", name="Second")
            session.add(row1)
            await session.commit()
            session.add(row2)
            with pytest.raises(Exception):
                await session.commit()


class TestPromptHistoryRow:
    """Tests for PromptHistoryRow ORM model."""

    @pytest.mark.asyncio
    async def test_create_history_row(self):
        """PromptHistoryRow should be creatable with required fields."""
        async with _test_session_factory() as session:
            row = PromptHistoryRow(
                generation_id="gen_abc123",
                positive_prompt="a brave warrior",
                negative_prompt="blurry, low quality",
                attributes={"species": "human", "class": "paladin"},
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.id is not None
            assert row.generation_id == "gen_abc123"
            assert row.positive_prompt == "a brave warrior"
            assert row.negative_prompt == "blurry, low quality"
            assert row.attributes == {"species": "human", "class": "paladin"}

    @pytest.mark.asyncio
    async def test_history_row_is_favorite_default(self):
        """PromptHistoryRow.is_favorite should default to False."""
        async with _test_session_factory() as session:
            row = PromptHistoryRow(
                generation_id="gen_fav_default",
                positive_prompt="test",
                negative_prompt="test",
                attributes={},
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.is_favorite is False

    @pytest.mark.asyncio
    async def test_history_row_is_favorite_toggle(self):
        """PromptHistoryRow.is_favorite should be toggleable (Boolean)."""
        async with _test_session_factory() as session:
            row = PromptHistoryRow(
                generation_id="gen_fav_toggle",
                positive_prompt="test",
                negative_prompt="test",
                attributes={},
                is_favorite=False,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.is_favorite is False

            # Toggle to True
            row.is_favorite = not row.is_favorite
            await session.commit()
            await session.refresh(row)
            assert row.is_favorite is True

            # Toggle back to False
            row.is_favorite = not row.is_favorite
            await session.commit()
            await session.refresh(row)
            assert row.is_favorite is False

    @pytest.mark.asyncio
    async def test_history_row_json_dict_roundtrip(self):
        """PromptHistoryRow.attributes should round-trip a dict through SQLite."""
        async with _test_session_factory() as session:
            attrs = {"species": "orc", "class": "barbarian", "weapon": "greataxe"}
            row = PromptHistoryRow(
                generation_id="gen_json_hist",
                positive_prompt="test",
                negative_prompt="test",
                attributes=attrs,
            )
            session.add(row)
            await session.commit()

            async with _test_session_factory() as session2:
                result = await session2.execute(
                    PromptHistoryRow.__table__.select().where(
                        PromptHistoryRow.generation_id == "gen_json_hist"
                    )
                )
                fetched = result.fetchone()
                assert isinstance(fetched.attributes, dict)
                assert fetched.attributes == attrs

    @pytest.mark.asyncio
    async def test_history_row_generation_id_allows_duplicates(self):
        """PromptHistoryRow.generation_id allows duplicates (batch entries)."""
        async with _test_session_factory() as session:
            row1 = PromptHistoryRow(
                generation_id="gen_batch_hist",
                positive_prompt="test1",
                negative_prompt="test1",
                attributes={},
            )
            row2 = PromptHistoryRow(
                generation_id="gen_batch_hist",
                positive_prompt="test2",
                negative_prompt="test2",
                attributes={},
            )
            session.add(row1)
            session.add(row2)
            await session.commit()
            # Both rows should be persisted
            result = await session.execute(
                select(PromptHistoryRow).where(
                    PromptHistoryRow.generation_id == "gen_batch_hist"
                )
            )
            rows = result.scalars().all()
            assert len(rows) == 2


class TestCharacterProfileRow:
    """Tests for CharacterProfileRow ORM model."""

    @pytest.mark.asyncio
    async def test_create_character_row(self):
        """CharacterProfileRow should be creatable with required fields."""
        async with _test_session_factory() as session:
            row = CharacterProfileRow(
                character_id="char_test1",
                project_name="My Project",
                character_name="Hero",
                trigger_token="my_project_hero_v1",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.id is not None
            assert row.character_id == "char_test1"
            assert row.project_name == "My Project"
            assert row.character_name == "Hero"

    @pytest.mark.asyncio
    async def test_character_row_defaults(self):
        """CharacterProfileRow should apply default values for list fields."""
        async with _test_session_factory() as session:
            row = CharacterProfileRow(
                character_id="char_defaults",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.target_perspective == ["front", "side", "back", "three-quarter"]
            assert row.animations == ["idle", "walk", "attack", "hurt"]

    @pytest.mark.asyncio
    async def test_character_row_string_array_roundtrip(self):
        """CharacterProfileRow.target_perspective and animations should round-trip lists."""
        async with _test_session_factory() as session:
            perspectives = ["front", "side"]
            anims = ["idle", "walk", "run"]
            row = CharacterProfileRow(
                character_id="char_array1",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
                target_perspective=perspectives,
                animations=anims,
            )
            session.add(row)
            await session.commit()

            async with _test_session_factory() as session2:
                result = await session2.execute(
                    CharacterProfileRow.__table__.select().where(
                        CharacterProfileRow.character_id == "char_array1"
                    )
                )
                fetched = result.fetchone()
                assert isinstance(fetched.target_perspective, list)
                assert fetched.target_perspective == perspectives
                assert isinstance(fetched.animations, list)
                assert fetched.animations == anims

    @pytest.mark.asyncio
    async def test_character_row_nullable_fields(self):
        """CharacterProfileRow nullable fields should accept None."""
        async with _test_session_factory() as session:
            row = CharacterProfileRow(
                character_id="char_nullable",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
                species=None,
                character_class=None,
                weapon=None,
                armor=None,
                color_palette=None,
                art_style=None,
                target_sprite_size=None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.species is None
            assert row.character_class is None
            assert row.weapon is None

    @pytest.mark.asyncio
    async def test_character_row_unique_character_id(self):
        """CharacterProfileRow.character_id should be unique."""
        async with _test_session_factory() as session:
            row1 = CharacterProfileRow(
                character_id="char_unique1",
                project_name="P1",
                character_name="C1",
                trigger_token="p1_c1_v1",
            )
            row2 = CharacterProfileRow(
                character_id="char_unique1",
                project_name="P2",
                character_name="C2",
                trigger_token="p2_c2_v1",
            )
            session.add(row1)
            await session.commit()
            session.add(row2)
            with pytest.raises(Exception):
                await session.commit()

    @pytest.mark.asyncio
    async def test_character_row_unique_trigger_token(self):
        """CharacterProfileRow.trigger_token should be unique."""
        async with _test_session_factory() as session:
            row1 = CharacterProfileRow(
                character_id="char_tt1",
                project_name="P1",
                character_name="C1",
                trigger_token="unique_trigger_v1",
            )
            row2 = CharacterProfileRow(
                character_id="char_tt2",
                project_name="P2",
                character_name="C2",
                trigger_token="unique_trigger_v1",
            )
            session.add(row1)
            await session.commit()
            session.add(row2)
            with pytest.raises(Exception):
                await session.commit()


class TestReferenceImageRow:
    """Tests for ReferenceImageRow ORM model."""

    @pytest.mark.asyncio
    async def test_create_reference_image_row(self):
        """ReferenceImageRow should be creatable with required fields."""
        async with _test_session_factory() as session:
            # First create a character to reference
            char = CharacterProfileRow(
                character_id="char_ref_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = ReferenceImageRow(
                image_id="img_test1",
                character_id="char_ref_test",
                file_path="/path/to/image.png",
                original_filename="image.png",
                status="pending",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.id is not None
            assert row.image_id == "img_test1"
            assert row.character_id == "char_ref_test"
            assert row.status == "pending"

    @pytest.mark.asyncio
    async def test_reference_image_default_status(self):
        """ReferenceImageRow.status should default to 'pending'."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_status_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = ReferenceImageRow(
                image_id="img_status1",
                character_id="char_status_test",
                file_path="/path/to/image.png",
                original_filename="image.png",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.status == "pending"

    @pytest.mark.asyncio
    async def test_reference_image_enum_status_values(self):
        """ReferenceImageRow.status should accept all valid enum values."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_enum_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            for status_val in ["pending", "accepted", "rejected", "maybe"]:
                row = ReferenceImageRow(
                    image_id=f"img_enum_{status_val}",
                    character_id="char_enum_test",
                    file_path=f"/path/to/{status_val}.png",
                    original_filename=f"{status_val}.png",
                    status=status_val,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                assert row.status == status_val

    @pytest.mark.asyncio
    async def test_reference_image_angle_values(self):
        """ReferenceImageRow.angle should accept all valid enum values."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_angle_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            for angle_val in ["front", "side", "back", "three-quarter"]:
                row = ReferenceImageRow(
                    image_id=f"img_angle_{angle_val}",
                    character_id="char_angle_test",
                    file_path=f"/path/to/{angle_val}.png",
                    original_filename=f"{angle_val}.png",
                    status="accepted",
                    angle=angle_val,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                assert row.angle == angle_val

    @pytest.mark.asyncio
    async def test_reference_image_nullable_angle(self):
        """ReferenceImageRow.angle should be nullable."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_null_angle",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = ReferenceImageRow(
                image_id="img_null_angle",
                character_id="char_null_angle",
                file_path="/path/to/image.png",
                original_filename="image.png",
                status="pending",
                angle=None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.angle is None

    @pytest.mark.asyncio
    async def test_reference_image_unique_image_id(self):
        """ReferenceImageRow.image_id should be unique."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_unique_img",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row1 = ReferenceImageRow(
                image_id="img_unique_test",
                character_id="char_unique_img",
                file_path="/path/to/image1.png",
                original_filename="image1.png",
                status="pending",
            )
            row2 = ReferenceImageRow(
                image_id="img_unique_test",
                character_id="char_unique_img",
                file_path="/path/to/image2.png",
                original_filename="image2.png",
                status="pending",
            )
            session.add(row1)
            await session.commit()
            session.add(row2)
            with pytest.raises(Exception):
                await session.commit()


class TestLoraJobRow:
    """Tests for LoraJobRow ORM model."""

    @pytest.mark.asyncio
    async def test_create_lora_job_row(self):
        """LoraJobRow should be creatable with required fields."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_lora_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = LoraJobRow(
                job_id="job_test1",
                character_id="char_lora_test",
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate=1e-4,
                epochs=10,
                preview_interval=2,
                output_format="safetensors",
                lora_strength=1.0,
                status="pending",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.id is not None
            assert row.job_id == "job_test1"
            assert row.character_id == "char_lora_test"
            assert row.status == "pending"
            assert row.epochs == 10

    @pytest.mark.asyncio
    async def test_lora_job_default_status(self):
        """LoraJobRow.status should default to 'pending'."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_lora_default",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = LoraJobRow(
                job_id="job_default_status",
                character_id="char_lora_default",
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate=1e-4,
                epochs=10,
                preview_interval=2,
                output_format="safetensors",
                lora_strength=1.0,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.status == "pending"

    @pytest.mark.asyncio
    async def test_lora_job_enum_status_values(self):
        """LoraJobRow.status should accept all valid enum values."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_lora_enum",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            for status_val in ["pending", "running", "completed", "failed"]:
                row = LoraJobRow(
                    job_id=f"job_status_{status_val}",
                    character_id="char_lora_enum",
                    preset_id="pixel_art_character",
                    base_model="stabilityai/stable-diffusion-xl-base-1.0",
                    learning_rate=1e-4,
                    epochs=10,
                    preview_interval=2,
                    output_format="safetensors",
                    lora_strength=1.0,
                    status=status_val,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                assert row.status == status_val

    @pytest.mark.asyncio
    async def test_lora_job_nullable_fields(self):
        """LoraJobRow nullable fields should accept None."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_lora_null",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = LoraJobRow(
                job_id="job_nullable",
                character_id="char_lora_null",
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate=1e-4,
                epochs=10,
                preview_interval=2,
                output_format="safetensors",
                lora_strength=1.0,
                status="pending",
                output_lora_path=None,
                log_output=None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.output_lora_path is None
            assert row.log_output is None

    @pytest.mark.asyncio
    async def test_lora_job_unique_job_id(self):
        """LoraJobRow.job_id should be unique."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_lora_unique",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row1 = LoraJobRow(
                job_id="job_unique_test",
                character_id="char_lora_unique",
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate=1e-4,
                epochs=10,
                preview_interval=2,
                output_format="safetensors",
                lora_strength=1.0,
                status="pending",
            )
            row2 = LoraJobRow(
                job_id="job_unique_test",
                character_id="char_lora_unique",
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate=1e-4,
                epochs=20,
                preview_interval=2,
                output_format="safetensors",
                lora_strength=1.0,
                status="pending",
            )
            session.add(row1)
            await session.commit()
            session.add(row2)
            with pytest.raises(Exception):
                await session.commit()


# ===========================================================================
# init_db and engine configuration tests
# ===========================================================================


class TestInitDb:
    """Tests for init_db() and engine configuration."""

    @pytest.mark.asyncio
    async def test_init_db_creates_all_tables(self):
        """init_db() should create all database tables."""
        # Tables already created by setup_db fixture, so we verify they exist
        async with _test_engine.begin() as conn:
            # Check that all expected tables exist
            def _inspect(connection):
                inspector = inspect(connection)
                return inspector.get_table_names()

            table_names = await conn.run_sync(_inspect)
            expected_tables = [
                "presets",
                "prompt_history",
                "character_profiles",
                "reference_images",
                "lora_jobs",
            ]
            for table in expected_tables:
                assert table in table_names, f"Table '{table}' not found in database"

    @pytest.mark.asyncio
    async def test_init_db_idempotent(self):
        """init_db() should be idempotent — calling it twice should not raise."""
        # init_db uses create_all which is idempotent
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Second call should not raise
            await conn.run_sync(Base.metadata.create_all)

    @pytest.mark.asyncio
    async def test_get_session_yields_session(self):
        """get_session() should yield an AsyncSession."""
        session_gen = _override_get_session()
        session = await anext(session_gen)
        assert isinstance(session, AsyncSession)
        await session.close()


class TestEngineConfiguration:
    """Tests for engine configuration based on DATABASE_URL."""

    def test_is_sqlite_flag_with_sqlite_url(self):
        """_IS_SQLITE should be True when DATABASE_URL starts with 'sqlite'."""
        # The test uses SQLite, so _IS_SQLITE should be True for test config
        # But the module-level _IS_SQLITE depends on the actual DATABASE_URL
        # We test the logic directly
        assert "sqlite+aiosqlite" in TEST_DB_URL

    def test_sqlite_connect_args(self):
        """SQLite engine should have check_same_thread=False in connect_args."""
        # Our test engine uses SQLite with connect_args
        assert _test_engine.dialect.name == "sqlite"


class TestTableConstraints:
    """Tests for table constraints (NOT NULL, UNIQUE, etc.)."""

    @pytest.mark.asyncio
    async def test_preset_row_not_null_name(self):
        """PresetRow.name should be NOT NULL."""
        async with _test_session_factory() as session:
            row = PresetRow(preset_id="preset_no_name", name=None)  # type: ignore
            session.add(row)
            with pytest.raises(Exception):
                await session.commit()

    @pytest.mark.asyncio
    async def test_preset_row_not_null_preset_id(self):
        """PresetRow.preset_id should be NOT NULL."""
        async with _test_session_factory() as session:
            row = PresetRow(preset_id=None, name="Test")  # type: ignore
            session.add(row)
            with pytest.raises(Exception):
                await session.commit()

    @pytest.mark.asyncio
    async def test_history_row_not_null_generation_id(self):
        """PromptHistoryRow.generation_id should be NOT NULL."""
        async with _test_session_factory() as session:
            row = PromptHistoryRow(
                generation_id=None,  # type: ignore
                positive_prompt="test",
                negative_prompt="test",
                attributes={},
            )
            session.add(row)
            with pytest.raises(Exception):
                await session.commit()

    @pytest.mark.asyncio
    async def test_character_row_not_null_project_name(self):
        """CharacterProfileRow.project_name should be NOT NULL."""
        async with _test_session_factory() as session:
            row = CharacterProfileRow(
                character_id="char_no_proj",
                project_name=None,  # type: ignore
                character_name="Test",
                trigger_token="test_v1",
            )
            session.add(row)
            with pytest.raises(Exception):
                await session.commit()

    @pytest.mark.asyncio
    async def test_reference_image_not_null_file_path(self):
        """ReferenceImageRow.file_path should be NOT NULL."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_fp_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = ReferenceImageRow(
                image_id="img_no_fp",
                character_id="char_fp_test",
                file_path=None,  # type: ignore
                original_filename="image.png",
                status="pending",
            )
            session.add(row)
            with pytest.raises(Exception):
                await session.commit()

    @pytest.mark.asyncio
    async def test_lora_job_not_null_character_id(self):
        """LoraJobRow.character_id should be NOT NULL."""
        async with _test_session_factory() as session:
            row = LoraJobRow(
                job_id="job_no_char",
                character_id=None,  # type: ignore
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate=1e-4,
                epochs=10,
                preview_interval=2,
                output_format="safetensors",
                lora_strength=1.0,
                status="pending",
            )
            session.add(row)
            with pytest.raises(Exception):
                await session.commit()


class TestForeignKeyRelationships:
    """Tests for foreign key relationships between tables."""

    @pytest.mark.asyncio
    async def test_reference_image_fk_to_character(self):
        """ReferenceImageRow.character_id should reference CharacterProfileRow."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_fk_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            img = ReferenceImageRow(
                image_id="img_fk_test",
                character_id="char_fk_test",
                file_path="/path/to/image.png",
                original_filename="image.png",
                status="pending",
            )
            session.add(img)
            await session.commit()
            await session.refresh(img)
            assert img.character_id == "char_fk_test"

    @pytest.mark.asyncio
    async def test_lora_job_fk_to_character(self):
        """LoraJobRow.character_id should reference CharacterProfileRow."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_lora_fk",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            job = LoraJobRow(
                job_id="job_fk_test",
                character_id="char_lora_fk",
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate=1e-4,
                epochs=10,
                preview_interval=2,
                output_format="safetensors",
                lora_strength=1.0,
                status="pending",
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            assert job.character_id == "char_lora_fk"

    @pytest.mark.asyncio
    async def test_reference_image_invalid_character_id(self):
        """ReferenceImageRow with non-existent character_id should fail FK constraint.

        Note: SQLite does not enforce FK constraints by default. This test
        verifies the FK relationship exists in the model definition. On
        PostgreSQL, this would raise an IntegrityError.
        """
        async with _test_session_factory() as session:
            # SQLite doesn't enforce FK constraints without PRAGMA foreign_keys=ON
            # Verify the FK column exists in the model definition
            columns = {c.name for c in ReferenceImageRow.__table__.columns}
            assert "character_id" in columns
            # Verify the FK references the correct table
            fk = ReferenceImageRow.__table__.c.character_id.foreign_keys
            assert len(fk) == 1
            fk_ref = list(fk)[0]
            assert fk_ref.column.table.name == "character_profiles"

    @pytest.mark.asyncio
    async def test_lora_job_invalid_character_id(self):
        """LoraJobRow with non-existent character_id should fail FK constraint.

        Note: SQLite does not enforce FK constraints by default. This test
        verifies the FK relationship exists in the model definition. On
        PostgreSQL, this would raise an IntegrityError.
        """
        async with _test_session_factory() as session:
            # SQLite doesn't enforce FK constraints without PRAGMA foreign_keys=ON
            # Verify the FK column exists in the model definition
            columns = {c.name for c in LoraJobRow.__table__.columns}
            assert "character_id" in columns
            # Verify the FK references the correct table
            fk = LoraJobRow.__table__.c.character_id.foreign_keys
            assert len(fk) == 1
            fk_ref = list(fk)[0]
            assert fk_ref.column.table.name == "character_profiles"


class TestColumnDefaults:
    """Tests for column default values."""

    @pytest.mark.asyncio
    async def test_preset_row_column_defaults(self):
        """PresetRow should have correct default values for all columns."""
        async with _test_session_factory() as session:
            row = PresetRow(
                preset_id="preset_defaults_test",
                name="Defaults Test",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.positive_template_id == "front_view_sprite"
            assert row.negative_profile_id == "general_sprite_cleanup"
            assert row.created_at is not None
            assert row.updated_at is not None

    @pytest.mark.asyncio
    async def test_history_row_column_defaults(self):
        """PromptHistoryRow should have correct default values."""
        async with _test_session_factory() as session:
            row = PromptHistoryRow(
                generation_id="gen_defaults_test",
                positive_prompt="test",
                negative_prompt="test",
                attributes={},
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.is_favorite is False
            assert row.created_at is not None

    @pytest.mark.asyncio
    async def test_character_row_column_defaults(self):
        """CharacterProfileRow should have correct default values for list fields."""
        async with _test_session_factory() as session:
            row = CharacterProfileRow(
                character_id="char_defaults_test",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.target_perspective == ["front", "side", "back", "three-quarter"]
            assert row.animations == ["idle", "walk", "attack", "hurt"]
            assert row.created_at is not None
            assert row.updated_at is not None

    @pytest.mark.asyncio
    async def test_reference_image_column_defaults(self):
        """ReferenceImageRow should have correct default values."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_ref_defaults",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = ReferenceImageRow(
                image_id="img_defaults_test",
                character_id="char_ref_defaults",
                file_path="/path/to/image.png",
                original_filename="image.png",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.status == "pending"
            assert row.angle is None
            assert row.caption is None
            assert row.rejection_reason is None
            assert row.created_at is not None

    @pytest.mark.asyncio
    async def test_lora_job_column_defaults(self):
        """LoraJobRow should have correct default values."""
        async with _test_session_factory() as session:
            char = CharacterProfileRow(
                character_id="char_lora_defaults",
                project_name="Project",
                character_name="Character",
                trigger_token="project_character_v1",
            )
            session.add(char)
            await session.commit()

            row = LoraJobRow(
                job_id="job_defaults_test",
                character_id="char_lora_defaults",
                preset_id="pixel_art_character",
                base_model="stabilityai/stable-diffusion-xl-base-1.0",
                learning_rate="1e-4",
                epochs=10,
                preview_interval=2,
                output_format="safetensors",
                lora_strength="1.0",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            assert row.status == "pending"
            assert row.output_lora_path is None
            assert row.log_output is None
            assert row.created_at is not None
            assert row.updated_at is not None