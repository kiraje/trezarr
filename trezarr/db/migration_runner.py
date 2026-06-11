"""Alembic migration runner — async-aware startup bridge (D-31, D-38).

Design decisions honoured:
  D-31  The baseline Alembic migration (0001_baseline_bible_schema.py) is the
        single source of truth for the full long-term Bible schema. run_migrations_to_head()
        ensures every startup applies all pending migrations idempotently.
  D-37  migrate_json_ledger_if_needed() — one-shot JSON→SQLite migration on first
        SQLite startup — is implemented here and called AFTER run_migrations_to_head().
        Pitfall 5: commit the SQLite transaction FIRST, rename the JSON file SECOND.
        Corrupt JSON → .corrupt.bak. Success → .migrated.bak.
        Idempotency: short-circuits on EITHER .migrated.bak OR .corrupt.bak presence.
        Caveat: if the DB is deleted but .migrated.bak exists, auto-recovery is lost
        (accepted v1 trade-off — documented in migrate_json_ledger_if_needed docstring).

Pitfall 1 (04-RESEARCH.md): Alembic's command.upgrade() is synchronous and MUST
be invoked via connection.run_sync(_do_upgrade) to avoid blocking the event loop
and bypassing the engine's PRAGMA-configured connection.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)

# Path to alembic.ini at the project root (two parents up from this file:
# trezarr/db/migration_runner.py → trezarr/db → trezarr → project-root).
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _do_upgrade(connection, cfg: Config) -> None:
    """Sync callback invoked via connection.run_sync().

    Injects the live connection into the Alembic config so env.py's
    run_migrations_online() uses OUR connection (and therefore our PRAGMAs)
    rather than creating a new engine internally.

    Args:
        connection: Synchronous SQLAlchemy connection from run_sync().
        cfg:        Alembic Config with script_location set.
    """
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def run_migrations_to_head(engine: AsyncEngine) -> None:
    """Run all pending Alembic migrations up to the 'head' revision.

    Uses the connection.run_sync(_do_upgrade) bridge to invoke synchronous
    Alembic from an async context without blocking the event loop (Pitfall 1).
    Idempotent — Alembic skips already-applied revisions.

    Args:
        engine: An AsyncEngine from build_engine() with PRAGMAs already registered.

    Raises:
        Exception: Re-raises any Alembic error; caller (cli.py) should sys.exit(1).
    """
    cfg = Config(str(ALEMBIC_INI))
    # In-app migrations must NOT let env.py's fileConfig(alembic.ini) replace
    # the daemon's logging setup (alembic.ini root is WARNING — it silently
    # drops all app INFO records, including the per-pass instrumentation).
    cfg.attributes["configure_logger"] = False
    logger.info("Running Alembic migrations to head (alembic.ini: %s)", ALEMBIC_INI)
    async with engine.begin() as conn:
        await conn.run_sync(_do_upgrade, cfg)
    logger.info("Alembic migrations complete")


async def migrate_json_ledger_if_needed(
    session_factory: async_sessionmaker[AsyncSession],
    settings: "TrezarrSettings",
) -> None:
    """One-shot JSON→SQLite migration for the idempotency ledger (D-37).

    Reads any pre-existing JSON ledger at ``settings.translate_ledger_path``,
    inserts all its entries into the processed_file SQLite table in a single
    transaction, then renames the JSON file to ``<path>.migrated.bak``.

    Idempotency contract (D-37):
      - If ``<path>.migrated.bak`` already exists → no-op (migration already ran).
      - If ``<path>.corrupt.bak`` already exists → no-op (corrupt JSON logged and
        parked on a prior run; SQLite starts empty from that point).
      - If ``json_ledger_path`` does not exist → no-op (fresh install, nothing to migrate).

    Pitfall 5 ordering (COMMIT FIRST, RENAME SECOND):
      The SQLite transaction commits before os.replace renames the JSON file.
      If the process crashes between commit and rename, the JSON file survives on
      the next run: the migration check finds it (no .bak), re-reads it, and
      tries to INSERT each row. Rows already in the DB are skipped via the
      collision-skip logic (SELECT-then-skip on existing source_path). The net
      result is idempotent.

    Collision handling (D-37 — DB is newer truth):
      If a source_path from the JSON ledger already exists in the SQLite table,
      the JSON entry is logged-and-skipped. The existing SQLite row is not
      overwritten.

    Corrupt/unreadable JSON handling:
      - JSONDecodeError / OSError / unexpected top-level type → log warning,
        rename to ``<path>.corrupt.bak``, return. SQLite starts empty (no rows
        inserted). Mirrors the never-raises (Pitfall 4) contract of Ledger._load.

    Accepted v1 trade-off (.migrated.bak idempotency caveat):
      If the SQLite database is deleted but ``.migrated.bak`` exists, this
      function short-circuits and returns without re-populating SQLite. In
      Phase 3 the operator must manually restore the DB from the .bak file or
      accept that prior entries are lost. Phase 5+ should add a ``--force-reimport``
      CLI flag if this becomes an operational pain point.

    Args:
        session_factory: async_sessionmaker for the migrated AsyncEngine.
                         MUST use expire_on_commit=False (Pitfall 2).
        settings:        TrezarrSettings instance; ``settings.translate_ledger_path``
                         is the path to the JSON ledger file (e.g. /config/processed_files.json).
    """
    from trezarr.bible.models import ProcessedFile
    from trezarr.output.ledger import Ledger, LedgerEntry

    json_path = Path(settings.translate_ledger_path)
    migrated_bak = json_path.with_suffix(json_path.suffix + ".migrated.bak")
    corrupt_bak = json_path.with_suffix(json_path.suffix + ".corrupt.bak")

    # WR-09: a sentinel sibling file produced when the post-COMMIT rename
    # FAILED on a prior run. Its presence lets us short-circuit BEFORE we
    # parse the JSON ledger and re-execute all the per-entry idempotent
    # collision-skip SELECTs on every subsequent startup — wasted work that
    # would otherwise compound forever until an operator manually clears
    # the situation. The sentinel is informational: it points the operator
    # at the failed rename so they can resolve it once and remove BOTH the
    # sentinel and the leftover JSON file.
    rename_blocked = json_path.with_suffix(json_path.suffix + ".rename_blocked")

    # Idempotency: short-circuit on either .bak suffix present (D-37 cross-AI MEDIUM).
    if migrated_bak.exists():
        logger.info(
            "JSON ledger already migrated (%s exists) — skipping migration",
            migrated_bak,
        )
        return
    if corrupt_bak.exists():
        logger.info(
            "JSON ledger previously flagged corrupt (%s exists) — skipping migration",
            corrupt_bak,
        )
        return
    if rename_blocked.exists():
        # WR-09: a prior run committed rows but could not rename the JSON
        # file. The SQLite rows are already present; re-reading the JSON file
        # would do N collision-skip SELECTs for zero new inserts. Short-
        # circuit at startup, log at error level (operator action required),
        # and stop.
        logger.error(
            "JSON ledger migration: post-COMMIT rename was blocked on a prior run "
            "(sentinel %s exists). SQLite rows are already present (idempotent). "
            "OPERATOR ACTION: resolve the underlying rename failure (cross-device, "
            "permissions, EXDEV), manually move %s to %s, then delete %s.",
            rename_blocked, json_path, migrated_bak, rename_blocked,
        )
        return

    # Fresh install — nothing to migrate.
    if not json_path.exists():
        logger.debug("No JSON ledger found at %s — nothing to migrate", json_path)
        return

    # Load JSON ledger (Pitfall 4 — never raises; mirrors Ledger._load forgiveness).
    try:
        raw_text = json_path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "JSON ledger at %s is unreadable/corrupt (%s) — "
            "renaming to %s and starting SQLite empty",
            json_path, exc, corrupt_bak,
        )
        os.replace(json_path, corrupt_bak)
        return

    if not isinstance(raw, dict):
        logger.warning(
            "JSON ledger at %s is not a JSON object (got %s) — "
            "renaming to %s and starting SQLite empty",
            json_path, type(raw).__name__, corrupt_bak,
        )
        os.replace(json_path, corrupt_bak)
        return

    # Parse entries (same per-entry forgiveness as Ledger._load).
    import dataclasses

    valid_keys = {f.name for f in dataclasses.fields(LedgerEntry)}
    # WR-03: validate the status enum BEFORE opening the transaction so a
    # single bad row (e.g. status="weird-status" introduced by a hand-edit or
    # an upstream schema-drift bug) cannot roll back ALL the good rows that
    # were already inserted earlier in the loop. SQLite enforces this CHECK
    # constraint at INSERT time; once a single INSERT raises IntegrityError
    # inside a non-savepointed transaction, the only recovery is rollback of
    # the whole txn — and the `inserted` counter would lie about what made
    # it into the DB. Validating up front guarantees the txn either commits
    # cleanly or never enters the loop.
    VALID_STATUSES = {"done", "quarantined", "in_progress"}
    entries: list[LedgerEntry] = []
    pre_skipped = 0
    for k, v in raw.items():
        if not isinstance(v, dict):
            logger.warning("JSON ledger entry %r is not an object — skipping", k)
            pre_skipped += 1
            continue
        try:
            entry = LedgerEntry(**{kk: vv for kk, vv in v.items() if kk in valid_keys})
        except (TypeError, KeyError, AttributeError, ValueError):
            logger.warning("JSON ledger entry %r is malformed — skipping", k)
            pre_skipped += 1
            continue
        # WR-03 defensive enum gate — keeps the transaction guaranteed-safe.
        if entry.status not in VALID_STATUSES:
            logger.warning(
                "JSON ledger entry %r has invalid status %r — skipping (must be one of %s)",
                k, entry.status, sorted(VALID_STATUSES),
            )
            pre_skipped += 1
            continue
        entries.append(entry)

    if not entries:
        logger.info(
            "JSON ledger at %s has no valid entries — renaming to %s",
            json_path, migrated_bak,
        )
        os.replace(json_path, migrated_bak)
        return

    # COMMIT FIRST (Pitfall 5): insert all rows in a single transaction.
    # WR-03: pre-validated entries above guarantee no row inside this loop can
    # raise IntegrityError on the status CHECK; the only legitimate skip path
    # is the collision check (DB-already-has-this-source_path).
    skipped = pre_skipped
    inserted = 0
    async with session_factory() as session:
        async with session.begin():
            for entry in entries:
                # Collision check: DB is newer truth (D-37) — skip if already present.
                result = await session.execute(
                    select(ProcessedFile).where(
                        ProcessedFile.source_path == entry.source_path
                    )
                )
                if result.scalar_one_or_none() is not None:
                    logger.warning(
                        "JSON ledger migration: collision — %s already in SQLite, "
                        "DB entry kept (JSON entry skipped, D-37 newer-truth rule)",
                        entry.source_path,
                    )
                    skipped += 1
                    continue
                session.add(ProcessedFile(
                    source_path=entry.source_path,
                    output_path=entry.output_path,
                    status=entry.status,
                    content_hash=entry.content_hash,
                    series_id=entry.series_id,
                    source_lang=entry.source_lang,
                    episode_key=entry.episode_key,
                    translated_at=entry.translated_at,
                    quarantine_path=entry.quarantine_path,
                ))
                inserted += 1
        # session.begin().__aexit__ commits here — Pitfall 5: commit happened.

    logger.info(
        "JSON ledger migration complete: inserted=%d, skipped=%d; "
        "renaming %s → %s",
        inserted, skipped, json_path, migrated_bak,
    )

    # RENAME SECOND (Pitfall 5): only rename AFTER the SQLite commit.
    # If the rename fails (e.g. cross-device, permissions), log at ERROR
    # level (this is an operator-action condition, NOT a recurring transient)
    # and drop a sentinel sibling file so subsequent startups short-circuit
    # before re-parsing the JSON ledger.
    try:
        os.replace(json_path, migrated_bak)
    except OSError as exc:
        # WR-09: promote warning → error. This is a one-time unrecoverable
        # operator-action condition (cross-device, permissions, EXDEV); on
        # every subsequent startup the SAME warning would fire forever
        # because the JSON file remains in place. error level + sentinel
        # makes the condition both visible and self-suppressing on re-runs.
        logger.error(
            "JSON ledger migration: SQLite commit succeeded but renaming %s → %s "
            "failed (%s). Rows are committed; subsequent runs will short-circuit "
            "via the sentinel at %s. OPERATOR ACTION: resolve the underlying "
            "rename failure, then manually move the JSON file and delete the "
            "sentinel.",
            json_path, migrated_bak, exc, rename_blocked,
        )
        # Drop a sentinel so the next startup short-circuits before re-
        # parsing N entries and emitting N collision-skip SELECTs.
        try:
            rename_blocked.write_text(
                f"JSON ledger rename failed at {json_path}\n"
                f"target: {migrated_bak}\n"
                f"error: {exc}\n"
                f"Resolve manually, then delete this file.\n",
                encoding="utf-8",
            )
        except OSError as sentinel_exc:
            # If even the sentinel write fails (truly broken filesystem),
            # log it but do NOT raise — the SQLite commit succeeded and the
            # CLI should still complete the run.
            logger.error(
                "JSON ledger migration: failed to write sentinel %s (%s). "
                "Subsequent startups will re-attempt the migration and likely "
                "log this same error each time.",
                rename_blocked, sentinel_exc,
            )
