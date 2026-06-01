"""Tests for migrate_json_ledger_if_needed — one-shot JSON→SQLite migration (D-37).

Tests validate:
  - Happy-path: 5-entry JSON ledger → 5 SQLite rows; .migrated.bak created
  - Idempotency when .migrated.bak exists (no-op, both coverage paths)
  - Idempotency when .corrupt.bak exists (cross-AI review MEDIUM finding)
  - Collision: existing SQLite row wins over JSON entry (DB is the newer truth)
  - Corrupt JSON: renamed to .corrupt.bak, NOT .migrated.bak; no exception raised
  - Missing JSON file: complete no-op
  - Pitfall 5 ordering: commit FIRST, rename SECOND — verified by patching os.replace
  - Corrupt-JSON backup path is logged (operators know where it went)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from trezarr.bible.models import ProcessedFile
from trezarr.config import TrezarrSettings


def _make_settings(tmp_path: Path) -> TrezarrSettings:
    """Build a TrezarrSettings stub with ledger and DB pointed at tmp_path."""
    db_path = tmp_path / "trezarr.db"
    json_path = tmp_path / "processed_files.json"
    return TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        translate_ledger_path=str(json_path),
        llm_api_key="test-key",
    )


def _make_json_entries(paths: list[str], statuses: list[str] | None = None) -> dict:
    """Build a dict suitable for JSON serialisation as a ledger file."""
    if statuses is None:
        statuses = ["done"] * len(paths)
    data = {}
    for path, status in zip(paths, statuses):
        data[path] = {
            "source_path": path,
            "output_path": path.replace(".en.srt", ".vi.srt"),
            "status": status,
            "content_hash": "abcd1234abcd1234",
            "series_id": None,
            "source_lang": "en",
            "episode_key": None,
            "translated_at": None,
            "quarantine_path": None,
        }
    return data


async def test_one_shot_migration_happy_path(tmp_path, session_factory):
    """5-entry JSON ledger → 5 SQLite rows; JSON renamed to .migrated.bak (D-37)."""
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)
    migrated_bak = Path(str(json_path) + ".migrated.bak")

    # Arrange: 5 entries covering all three status values
    paths = [
        "/data/Show.S01E01.en.srt",
        "/data/Show.S01E02.en.srt",
        "/data/Show.S01E03.en.srt",
        "/data/Show.S01E04.en.srt",
        "/data/Show.S01E05.en.srt",
    ]
    statuses = ["done", "done", "quarantined", "in_progress", "done"]
    data = _make_json_entries(paths, statuses)
    json_path.write_text(json.dumps(data), encoding="utf-8")

    # Act
    await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: 5 rows in SQLite
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProcessedFile))
    assert count == 5, f"Expected 5 rows in processed_file, got {count}"

    # Assert: rows have correct data
    async with session_factory() as session:
        row = await session.scalar(
            select(ProcessedFile).where(ProcessedFile.source_path == paths[2])
        )
    assert row is not None
    assert row.status == "quarantined"
    assert row.source_lang == "en"

    # Assert: original JSON gone, .migrated.bak exists
    assert not json_path.exists(), "Original JSON should be renamed away"
    assert migrated_bak.exists(), ".migrated.bak should exist after successful migration"


async def test_idempotent_when_migrated_bak_present(tmp_path, session_factory):
    """When .migrated.bak already exists, migration is a no-op (D-37 idempotency)."""
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)
    migrated_bak = Path(str(json_path) + ".migrated.bak")

    # Arrange: pre-create .migrated.bak (a prior successful migration)
    migrated_bak.write_text("{}", encoding="utf-8")

    # Also write the JSON so we can confirm it wasn't touched
    json_path.write_text(json.dumps(_make_json_entries(["/data/Show.S01E01.en.srt"])), encoding="utf-8")

    # Act
    await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: no rows inserted (short-circuit fired)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProcessedFile))
    assert count == 0, f"Expected 0 rows (idempotent no-op), got {count}"

    # JSON file still in place (short-circuit returns before touching it)
    assert json_path.exists(), "JSON should be untouched when .migrated.bak already exists"


async def test_idempotent_when_corrupt_bak_present(tmp_path, session_factory):
    """When .corrupt.bak already exists, migration is a no-op (cross-AI MEDIUM finding).

    Proves the idempotency check covers BOTH .migrated.bak and .corrupt.bak.
    """
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)
    corrupt_bak = Path(str(json_path) + ".corrupt.bak")

    # Arrange: pre-create .corrupt.bak (a prior corrupt-JSON run)
    corrupt_bak.write_text("", encoding="utf-8")

    # Also write a valid JSON to confirm it was NOT processed
    json_path.write_text(json.dumps(_make_json_entries(["/data/Show.S01E01.en.srt"])), encoding="utf-8")

    # Act
    await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: no rows inserted
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProcessedFile))
    assert count == 0, f"Expected 0 rows (corrupt.bak idempotency no-op), got {count}"


async def test_collision_logged_and_skipped(tmp_path, session_factory, caplog):
    """A JSON entry whose source_path already exists in SQLite is skipped; existing row wins (D-37)."""
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)

    existing_path = "/data/Show.S01E01.en.srt"

    # Arrange: pre-populate SQLite with one row
    async with session_factory() as session:
        async with session.begin():
            session.add(ProcessedFile(
                source_path=existing_path,
                output_path="/data/Show.S01E01.vi.srt",
                status="done",
                content_hash="existing_hash___",
            ))

    # Arrange: JSON has the SAME source_path with a STALE hash
    data = {
        existing_path: {
            "source_path": existing_path,
            "output_path": "/data/Show.S01E01.vi.srt",
            "status": "in_progress",         # stale status
            "content_hash": "stale_hash_____",
            "series_id": None,
            "source_lang": None,
            "episode_key": None,
            "translated_at": None,
            "quarantine_path": None,
        }
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")

    # Act
    with caplog.at_level(logging.WARNING, logger="trezarr.db.migration_runner"):
        await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: existing row is UNCHANGED (DB is the newer truth)
    async with session_factory() as session:
        row = await session.scalar(
            select(ProcessedFile).where(ProcessedFile.source_path == existing_path)
        )
    assert row is not None
    assert row.content_hash == "existing_hash___", "Existing row must not be overwritten by JSON entry"
    assert row.status == "done", "Existing row status must not be overwritten"

    # Assert: count is still 1 (collision skipped, not inserted twice)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProcessedFile))
    assert count == 1, f"Expected 1 row (collision-skip), got {count}"

    # Assert: warning was logged naming the source_path
    collision_logs = [r for r in caplog.records if "collision" in r.getMessage().lower() or existing_path in r.getMessage()]
    assert collision_logs, f"Expected a warning log mentioning the collision for {existing_path}"

    # Assert: .migrated.bak was created (rename still happens)
    migrated_bak = Path(str(json_path) + ".migrated.bak")
    assert migrated_bak.exists(), ".migrated.bak should exist even when there were collision-skips"


async def test_corrupt_json_renames_to_corrupt_bak_no_raise(tmp_path, session_factory, caplog):
    """Corrupt JSON → .corrupt.bak (not .migrated.bak); no exception; empty SQLite; warning logged.

    Cross-AI review MEDIUM finding: corrupt files get a DISTINCT suffix.
    """
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)

    # Arrange: corrupt JSON
    json_path.write_text("not valid {{ json", encoding="utf-8")

    # Act — must not raise
    with caplog.at_level(logging.WARNING, logger="trezarr.db.migration_runner"):
        await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: no rows
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProcessedFile))
    assert count == 0, f"Expected 0 rows on corrupt JSON, got {count}"

    # Assert: .corrupt.bak exists, NOT .migrated.bak
    corrupt_bak = Path(str(json_path) + ".corrupt.bak")
    migrated_bak = Path(str(json_path) + ".migrated.bak")
    assert corrupt_bak.exists(), ".corrupt.bak must exist for corrupt JSON"
    assert not migrated_bak.exists(), ".migrated.bak must NOT exist for corrupt JSON"

    # Assert: warning was logged
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "Expected a warning log for corrupt JSON"


async def test_missing_json_is_noop(tmp_path, session_factory, caplog):
    """No JSON ledger file present → complete no-op; no bak files; no noise in logs."""
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)

    # Arrange: json_path does NOT exist
    assert not json_path.exists()

    # Act
    with caplog.at_level(logging.WARNING, logger="trezarr.db.migration_runner"):
        await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: no rows
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProcessedFile))
    assert count == 0, f"Expected 0 rows on missing JSON, got {count}"

    # Assert: no bak files created
    assert not Path(str(json_path) + ".migrated.bak").exists()
    assert not Path(str(json_path) + ".corrupt.bak").exists()

    # Assert: no WARNING-level noise
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warnings, f"Expected no warning logs on missing JSON, got: {warnings}"


async def test_commit_before_rename_pitfall5(tmp_path, session_factory):
    """Pitfall 5: monkeypatch os.replace to raise; rows ARE in SQLite; JSON file still present.

    Proves commit-FIRST, rename-SECOND ordering: the migration rows survive
    even when the rename step fails.
    """
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)

    # Arrange: one-entry JSON
    data = _make_json_entries(["/data/Show.S01E01.en.srt"])
    json_path.write_text(json.dumps(data), encoding="utf-8")

    # Patch os.replace to raise OSError on the FIRST call only
    original_replace = os.replace
    call_count = {"n": 0}

    def _failing_replace(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("simulated rename failure for Pitfall 5 test")
        return original_replace(src, dst)

    with patch("trezarr.db.migration_runner.os.replace", side_effect=_failing_replace):
        # Should not raise — OSError on rename is logged and handled
        await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: SQLite rows ARE persisted (commit happened FIRST)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(ProcessedFile))
    assert count == 1, f"Expected 1 row after commit (Pitfall 5 — commit before rename); got {count}"

    # Assert: JSON file is STILL in place (rename failed AFTER commit)
    assert json_path.exists(), "JSON file should still exist when rename failed (Pitfall 5)"


async def test_corrupt_bak_path_is_logged(tmp_path, session_factory, caplog):
    """Corrupt JSON migration: the exact .corrupt.bak path is logged.

    Ensures operators know where the corrupt file was moved.
    """
    from trezarr.db.migration_runner import migrate_json_ledger_if_needed

    settings = _make_settings(tmp_path)
    json_path = Path(settings.translate_ledger_path)
    corrupt_bak = Path(str(json_path) + ".corrupt.bak")

    # Arrange: corrupt JSON
    json_path.write_text("{{{invalid", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="trezarr.db.migration_runner"):
        await migrate_json_ledger_if_needed(session_factory, settings)

    # Assert: the .corrupt.bak path string appears in at least one log message
    all_messages = " ".join(r.getMessage() for r in caplog.records)
    assert str(corrupt_bak) in all_messages, (
        f"Expected .corrupt.bak path {corrupt_bak} in log output; got:\n{all_messages}"
    )
