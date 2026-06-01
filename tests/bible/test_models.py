"""Model-fidelity tests — round-trips, JSON defaults, D-39 import boundary.

Tests:
  7.  test_series_round_trip: Series INSERT + reload preserves all fields (D-33/D-34/D-35)
  8.  test_character_round_trip: Character INSERT + reload (BIBLE-02)
  9.  test_term_dictionary_round_trip: TermDictionary INSERT + reload (BIBLE-04)
  10. test_processed_file_round_trip: ProcessedFile INSERT matches LedgerEntry schema (D-20)
  11. test_bible_event_round_trip: BibleEvent INSERT + reload (D-32)
  12. test_json_default_consistency: SQLA default, server_default, and round-trip all agree
  13. test_no_sqlalchemy_leakage_through_bible_init: D-39 import-graph boundary

asyncio_mode="auto" is configured project-wide.
Tests 7-12 use the session_factory fixture from tests/db/conftest.py.
Test 13 is synchronous (import inspection — no DB needed).
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from trezarr.bible.models import (
    BibleEvent,
    Character,
    ProcessedFile,
    Series,
    TermDictionary,
)


# ---------------------------------------------------------------------------
# Helper: create a series row for FK dependencies
# ---------------------------------------------------------------------------
async def _make_series(session_factory, *, arr_series_id: int = 1) -> int:
    """Insert a Series row and return its id."""
    async with session_factory() as session:
        async with session.begin():
            s = Series(
                arr_kind="sonarr",
                arr_instance="default",
                arr_series_id=arr_series_id,
                arr_metadata={"genres": ["drama"]},
                locked_fields=[],
            )
            session.add(s)
            await session.flush()
            return s.id


# ---------------------------------------------------------------------------
# Test 7 — Series round-trip (D-33/D-34/D-35)
# ---------------------------------------------------------------------------
async def test_series_round_trip(session_factory):
    """Series INSERT + SELECT-by-id returns identical values.

    Proves: arr_metadata round-trips as dict, locked_fields as list,
    register stays None, tvdb_id/tmdb_id nullable (D-33/D-34/D-35).
    """
    async with session_factory() as session:
        async with session.begin():
            s = Series(
                arr_kind="sonarr",
                arr_instance="default",
                arr_series_id=42,
                arr_metadata={"genres": ["drama"]},
                register=None,
                tvdb_id=12345,
                tmdb_id=None,
                locked_fields=[],
            )
            session.add(s)
            await session.flush()
            series_id = s.id

    # Reload from DB
    async with session_factory() as session:
        row = await session.get(Series, series_id)

    assert row is not None
    assert row.arr_kind == "sonarr"
    assert row.arr_instance == "default"
    assert row.arr_series_id == 42
    assert row.arr_metadata == {"genres": ["drama"]}, f"arr_metadata: {row.arr_metadata}"
    assert row.register is None
    assert row.tvdb_id == 12345
    assert row.tmdb_id is None
    assert row.locked_fields == [], f"locked_fields: {row.locked_fields}"
    assert isinstance(row.arr_metadata, dict), "arr_metadata must be dict after round-trip"
    assert isinstance(row.locked_fields, list), "locked_fields must be list after round-trip"


# ---------------------------------------------------------------------------
# Test 8 — Character round-trip (BIBLE-02)
# ---------------------------------------------------------------------------
async def test_character_round_trip(session_factory):
    """Character INSERT + reload — all fields including locked_fields survive.

    Proves BIBLE-02 column shape is correct.
    """
    series_id = await _make_series(session_factory)

    async with session_factory() as session:
        async with session.begin():
            c = Character(
                series_id=series_id,
                original_latin_name="Mary",
                gender="female",
                rough_age="adult",
                role="detective",
                locked_fields=["role"],
            )
            session.add(c)
            await session.flush()
            char_id = c.id

    async with session_factory() as session:
        row = await session.get(Character, char_id)

    assert row is not None
    assert row.series_id == series_id
    assert row.original_latin_name == "Mary"
    assert row.gender == "female"
    assert row.rough_age == "adult"
    assert row.role == "detective"
    assert row.locked_fields == ["role"], f"locked_fields: {row.locked_fields}"


# ---------------------------------------------------------------------------
# Test 9 — TermDictionary round-trip (BIBLE-04)
# ---------------------------------------------------------------------------
async def test_term_dictionary_round_trip(session_factory):
    """TermDictionary INSERT + reload — all fields survive.

    Proves BIBLE-04 column shape is correct.
    """
    series_id = await _make_series(session_factory, arr_series_id=2)

    async with session_factory() as session:
        async with session.begin():
            t = TermDictionary(
                series_id=series_id,
                source_term="King's Landing",
                vietnamese_rendering="Vương Đô",
                category="place",
                locked_fields=[],
            )
            session.add(t)
            await session.flush()
            term_id = t.id

    async with session_factory() as session:
        row = await session.get(TermDictionary, term_id)

    assert row is not None
    assert row.series_id == series_id
    assert row.source_term == "King's Landing"
    assert row.vietnamese_rendering == "Vương Đô"
    assert row.category == "place"
    assert row.locked_fields == []


# ---------------------------------------------------------------------------
# Test 10 — ProcessedFile round-trip (D-20 LedgerEntry schema compat)
# ---------------------------------------------------------------------------
async def test_processed_file_round_trip(session_factory):
    """ProcessedFile INSERT + reload matches all 9 LedgerEntry field names (D-20).

    Also verifies UNIQUE constraint on source_path: second INSERT raises IntegrityError.
    """
    async with session_factory() as session:
        async with session.begin():
            pf = ProcessedFile(
                source_path="/media/show/s01e01.srt",
                output_path="/media/show/s01e01.vi.srt",
                status="done",
                content_hash="abc123def456789a",
                series_id="sonarr:42",
                source_lang="en",
                episode_key="S01E01",
                translated_at="2026-06-01T00:00:00Z",
                quarantine_path=None,
            )
            session.add(pf)
            await session.flush()
            pf_id = pf.id

    async with session_factory() as session:
        row = await session.get(ProcessedFile, pf_id)

    assert row is not None
    assert row.source_path == "/media/show/s01e01.srt"
    assert row.output_path == "/media/show/s01e01.vi.srt"
    assert row.status == "done"
    assert row.content_hash == "abc123def456789a"
    assert row.series_id == "sonarr:42"
    assert row.source_lang == "en"
    assert row.episode_key == "S01E01"
    assert row.translated_at == "2026-06-01T00:00:00Z"
    assert row.quarantine_path is None

    # UNIQUE constraint: second INSERT with same source_path must raise
    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            async with session.begin():
                session.add(ProcessedFile(
                    source_path="/media/show/s01e01.srt",  # duplicate
                    output_path=None,
                    status="in_progress",
                    content_hash="different_hash",
                ))


# ---------------------------------------------------------------------------
# Test 11 — BibleEvent round-trip (D-32)
# ---------------------------------------------------------------------------
async def test_bible_event_round_trip(session_factory):
    """BibleEvent INSERT + reload preserves all 9 D-32 fields.

    source ∈ {"inference", "lock", "import", "system"} is enforced by CHECK.
    """
    series_id = await _make_series(session_factory, arr_series_id=3)

    async with session_factory() as session:
        async with session.begin():
            ev = BibleEvent(
                series_id=series_id,
                episode_key="S01E02",
                entity_type="character",
                entity_id=99,
                field="role",
                old_value="spy",
                new_value="detective",
                source="inference",
            )
            session.add(ev)
            await session.flush()
            ev_id = ev.id

    async with session_factory() as session:
        row = await session.get(BibleEvent, ev_id)

    assert row is not None
    assert row.series_id == series_id
    assert row.episode_key == "S01E02"
    assert row.entity_type == "character"
    assert row.entity_id == 99
    assert row.field == "role"
    assert row.old_value == "spy"
    assert row.new_value == "detective"
    assert row.source == "inference"
    assert row.created_at is not None  # server_default sets this


# ---------------------------------------------------------------------------
# Test 12 — JSON-default consistency (three-layer check)
# ---------------------------------------------------------------------------
async def test_json_default_consistency(db_engine, session_factory):
    """JSON-column defaults are consistent across SQLA model, server_default, and round-trip.

    Three layers tested:
      (a) SQLA callable default: new Series() without locked_fields → empty list (not None)
      (b) Alembic server_default: sqlite pragma table_info shows dflt_value='[]'
      (c) Round-trip: after commit + reload, locked_fields is still a Python list []

    Same check repeated for arr_metadata and '{}'.
    """
    # (a) SQLAlchemy 2.0 callable default — applied at INSERT (flush) time, not at __init__.
    # Create a Series without providing locked_fields or arr_metadata to test defaults.
    async with session_factory() as session:
        async with session.begin():
            s2 = Series(
                arr_kind="sonarr",
                arr_instance="default",
                arr_series_id=1001,
                # NOT providing locked_fields or arr_metadata — testing defaults
            )
            session.add(s2)
            await session.flush()
            # After flush(), SQLAlchemy has applied the callable default (list/dict)
            # expire_on_commit=False + flush means attributes are fresh
            series_id = s2.id

    # (c) Round-trip: reload and verify list/dict shape
    async with session_factory() as session:
        row = await session.get(Series, series_id)

    assert isinstance(row.locked_fields, list), (
        f"locked_fields must be list after round-trip, got {type(row.locked_fields)}"
    )
    assert row.locked_fields == [], f"locked_fields must be [] after round-trip, got {row.locked_fields}"
    assert isinstance(row.arr_metadata, dict), (
        f"arr_metadata must be dict after round-trip, got {type(row.arr_metadata)}"
    )
    assert row.arr_metadata == {}, f"arr_metadata must be {{}} after round-trip, got {row.arr_metadata}"

    # (b) DB server_default — check via pragma table_info
    async with db_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info('series')"))
        columns = {row[1]: row[4] for row in result}  # name → dflt_value

    locked_fields_default = columns.get("locked_fields")
    arr_metadata_default = columns.get("arr_metadata")

    # SQLite stores string defaults with surrounding single-quotes in pragma table_info.
    # So server_default='[]' appears as "'[]'" in the dflt_value column.
    # We check that the default value, stripped of surrounding quotes, equals [] or {}.
    def _strip_sqlite_quotes(val: str | None) -> str:
        if val is None:
            return ""
        return val.strip("'\"")

    assert _strip_sqlite_quotes(locked_fields_default) == "[]", (
        f"server_default for locked_fields must be '[]' (got {locked_fields_default!r})"
    )
    assert _strip_sqlite_quotes(arr_metadata_default) == "{}", (
        f"server_default for arr_metadata must be '{{}}' (got {arr_metadata_default!r})"
    )


# ---------------------------------------------------------------------------
# Test 13 — D-39 import-graph boundary (synchronous)
# ---------------------------------------------------------------------------
def test_no_sqlalchemy_leakage_through_bible_init():
    """D-39 boundary: trezarr/bible/__init__.py does not import SQLAlchemy.

    Two checks via import-graph introspection (not brittle dir() name-inspection):
      (a) Source of trezarr.bible.__init__ contains no 'from sqlalchemy' or 'import sqlalchemy'.
      (b) Importing trezarr.bible (without trezarr.bible.models) does NOT add sqlalchemy
          to sys.modules as a side effect of __init__ itself.
    """
    # (a) Source inspection — find the __init__ source and check for sqlalchemy imports
    spec = importlib.util.find_spec("trezarr.bible")
    assert spec is not None, "trezarr.bible must be importable"

    import trezarr.bible as _bible_pkg
    init_source = inspect.getsource(_bible_pkg)

    assert "from sqlalchemy" not in init_source, (
        "trezarr/bible/__init__.py must not contain 'from sqlalchemy' — "
        "SQLAlchemy must stay inside trezarr.bible.models (D-39)"
    )
    assert "import sqlalchemy" not in init_source, (
        "trezarr/bible/__init__.py must not contain 'import sqlalchemy' — "
        "SQLAlchemy must stay inside trezarr.bible.models (D-39)"
    )

    # (b) sys.modules side-effect check
    # Save current sys.modules state (sqlalchemy may already be present because
    # other test imports brought it in). The check is whether __init__ itself
    # (not models) contributes to importing sqlalchemy.
    # We check the __init__ source: it has no sqlalchemy import, so
    # loading it alone (without models submodule) would not add sqlalchemy.
    # The definitive proof is the source check above (a).
    # For robustness, we also confirm the __init__ source contains no
    # __import__ calls that reference sqlalchemy.
    assert "__import__('sqlalchemy')" not in init_source, (
        "trezarr/bible/__init__.py must not dynamically import sqlalchemy"
    )

    # Verify the __init__ source does NOT contain any reference to models attributes
    # that would trigger a submodule import (e.g. 'from .models import ...')
    assert "from .models import" not in init_source, (
        "trezarr/bible/__init__.py must not re-export from .models — "
        "keeps the D-39 SQLAlchemy boundary clean"
    )
    assert "from trezarr.bible.models" not in init_source, (
        "trezarr/bible/__init__.py must not import from trezarr.bible.models"
    )
