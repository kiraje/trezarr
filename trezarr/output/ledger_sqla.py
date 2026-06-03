"""SQLAlchemy-backed idempotency ledger — LedgerSQLA (D-37, D-20, D-38).

Design decisions honoured:
  D-20  LedgerEntry field names map 1:1 to ProcessedFile column names (frozen
        contract from Phase 2). check() and record() use those same field names
        so call sites are unmodified when Ledger is swapped for LedgerSQLA.
  D-37  One-shot JSON→SQLite migration. LedgerSQLA is the authoritative backend
        once migrate_json_ledger_if_needed() runs. The JSON Ledger class is kept
        for the migration function and any legacy tests.
  D-38  Async everywhere: check() and record() are async coroutines. LedgerSQLA
        implements LedgerProtocol structurally via @runtime_checkable Protocol.

UPSERT semantics for record():
  SELECT-then-INSERT/UPDATE (no dialect-specific INSERT OR REPLACE) so the
  implementation stays portable and SQLAlchemy-version-agnostic. The ProcessedFile
  table has a UNIQUE constraint on source_path (RESEARCH A2), which makes the
  select-then-upsert pattern reliable without relying on ON CONFLICT syntax.

expire_on_commit=False MANDATORY on the session_factory (Pitfall 2):
  Accessing attributes on an ORM object after session.commit() inside an async
  context raises MissingGreenlet if expire_on_commit=True (the default).
  The caller (db conftest + cli.py) must pass an async_sessionmaker built with
  ``expire_on_commit=False``.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trezarr.bible.models import ProcessedFile
from trezarr.output._ledger_protocol import LedgerProtocol  # noqa: F401
from trezarr.output.ledger import LedgerEntry

logger = logging.getLogger(__name__)


class LedgerSQLA:
    """SQLAlchemy-backed implementation of LedgerProtocol (D-37, D-20).

    Backed by the ``processed_file`` table (created by the Alembic baseline
    migration). Implements the same check/record/content_hash interface as the
    JSON Ledger so all call sites are swap-transparent.

    Interface contract (same as Ledger):
        await ledger.check(source_path)        -> LedgerEntry | None
        await ledger.record(entry: LedgerEntry) -> None
        LedgerSQLA.content_hash(source_bytes)  -> str  (staticmethod)

    Args:
        session_factory: async_sessionmaker built from build_engine() output.
                         MUST be constructed with ``expire_on_commit=False``
                         (Pitfall 2 — MissingGreenlet after commit in async context).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialise LedgerSQLA with an async session factory.

        Args:
            session_factory: async_sessionmaker[AsyncSession] with
                             expire_on_commit=False (Pitfall 2).
        """
        self._session_factory = session_factory

    async def check(self, source_path: str | Path) -> LedgerEntry | None:
        """Return the ledger entry for source_path, or None if not recorded.

        Args:
            source_path: Absolute path to the source subtitle file (str or Path).

        Returns:
            The LedgerEntry if source_path is in the processed_file table,
            else None.
        """
        key = str(source_path)
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProcessedFile).where(ProcessedFile.source_path == key)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _row_to_entry(row)

    async def check_by_output_path(self, output_path: str | Path) -> LedgerEntry | None:
        """Return any ledger entry whose output_path matches — secondary D-110 check.

        Used by gap.is_eligible Case 1.5 to detect Trezarr-owned vi sidecars that
        were written from a different (lower-priority) source path. This allows the
        source-language upgrade seam to distinguish:
          - Trezarr-owned vi (from a different source) → re-translate from richer source
          - Genuinely foreign vi (no ledger record) → D-26 never-clobber guard

        Pattern is identical to check() but queries ProcessedFile.output_path instead
        of ProcessedFile.source_path.

        Args:
            output_path: Absolute path to the output (vi sidecar) file (str or Path).

        Returns:
            The LedgerEntry if output_path is found in the processed_file table,
            else None.
        """
        key = str(output_path)
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProcessedFile).where(ProcessedFile.output_path == key)
            )
            row = result.scalar_one_or_none()
            return _row_to_entry(row) if row is not None else None

    async def record(self, entry: LedgerEntry) -> None:
        """Persist or update the ledger entry (upsert semantics).

        Uses SELECT-then-INSERT/UPDATE for portability (no dialect-specific
        INSERT OR REPLACE). The UNIQUE constraint on source_path (RESEARCH A2)
        makes this safe from concurrent writes in Phase 3's single-writer model.

        Args:
            entry: The LedgerEntry to persist. entry.source_path is the unique key.
        """
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ProcessedFile).where(
                        ProcessedFile.source_path == entry.source_path
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    # INSERT: new source_path
                    row = ProcessedFile(
                        source_path=entry.source_path,
                        output_path=entry.output_path,
                        status=entry.status,
                        content_hash=entry.content_hash,
                        series_id=entry.series_id,
                        source_lang=entry.source_lang,
                        episode_key=entry.episode_key,
                        translated_at=entry.translated_at,
                        quarantine_path=entry.quarantine_path,
                    )
                    session.add(row)
                else:
                    # UPDATE: existing source_path — apply all mutable fields
                    row.output_path = entry.output_path
                    row.status = entry.status
                    row.content_hash = entry.content_hash
                    row.series_id = entry.series_id
                    row.source_lang = entry.source_lang
                    row.episode_key = entry.episode_key
                    row.translated_at = entry.translated_at
                    row.quarantine_path = entry.quarantine_path
                # session.begin() commit happens on context manager __aexit__

    @staticmethod
    def content_hash(source_bytes: bytes) -> str:
        """Return a short deterministic hash of source_bytes.

        Identical to Ledger.content_hash — 16-char SHA-256 hex digest.
        Both implementations share the same hash function so idempotency
        keys computed before the migration remain valid after the swap.

        Args:
            source_bytes: Raw bytes of the source subtitle file.

        Returns:
            A 16-character lowercase hex string (first 64 bits of SHA-256).
        """
        return hashlib.sha256(source_bytes).hexdigest()[:16]


async def translated_counts_for_series(
    session_factory: async_sessionmaker,
    series_ids: list[int],
) -> dict[str, int]:
    """Return {str(series_id): count} of status='done' ProcessedFile rows (D-05).

    Executes a single GROUP BY aggregate query rather than one query per series,
    so the library list endpoint scales to large libraries without N round-trips.

    Keys are ``str`` because ``ProcessedFile.series_id`` is ``Mapped[str | None]``;
    Sonarr series IDs are ints, so callers must use ``str(series_id)`` as the key.
    A series absent from the DB returns 0 via the caller's ``.get(key, 0)`` idiom.

    Security (T-13-02): ``ProcessedFile.series_id.in_(str_ids)`` uses SQLAlchemy's
    parameterised IN clause — values are never interpolated as raw SQL.

    Args:
        session_factory: Async session factory (``async_sessionmaker``).
        series_ids:      List of Sonarr/Radarr series IDs (ints). Returns ``{}``
                         immediately when the list is empty.

    Returns:
        Mapping of ``str(series_id)`` → count of ``status='done'`` rows.
        Only series_ids that have at least one matching row appear in the result.
    """
    if not series_ids:
        return {}

    str_ids = [str(sid) for sid in series_ids]

    async with session_factory() as session:
        result = await session.execute(
            select(
                ProcessedFile.series_id,
                func.count().label("n"),
            )
            .where(
                ProcessedFile.series_id.in_(str_ids),
                ProcessedFile.status == "done",
            )
            .group_by(ProcessedFile.series_id)
        )
        return {row.series_id: row.n for row in result}


def _row_to_entry(row: ProcessedFile) -> LedgerEntry:
    """Convert a ProcessedFile ORM row to a LedgerEntry dataclass.

    Field names match 1:1 (D-20 contract), so this is a straightforward
    attribute copy with no name translation.

    Args:
        row: A ProcessedFile ORM row loaded from the database.

    Returns:
        LedgerEntry populated from the row's column values.
    """
    return LedgerEntry(
        source_path=row.source_path,
        output_path=row.output_path,
        status=row.status,  # type: ignore[arg-type]
        content_hash=row.content_hash,
        series_id=row.series_id,
        source_lang=row.source_lang,
        episode_key=row.episode_key,
        translated_at=row.translated_at,
        quarantine_path=row.quarantine_path,
    )
