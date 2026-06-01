"""JSON idempotency ledger for processed subtitle files (D-20).

Design decisions honoured:
  D-20  Idempotency via /config processed-files ledger.  Schema fields match
        the Phase-4 processed_file SQLAlchemy table column names so Phase 4
        can migrate this JSON backend without changing any call sites in engine.py.
        Behavior: unchanged source + valid output → skip; changed source →
        regenerate; foreign .vi.srt (not in ledger as ours) → skip + log;
        previously quarantined → retry.

BREAKING INTERNAL API CHANGE (Phase 4):
  Ledger.check and Ledger.record are NOW ASYNC (async def). Rationale: CLAUDE.md
  mandates 'Async everywhere — no sync sqlite3 calls in the FastAPI/async event
  loop'. This is an INTERNAL change only — the Ledger is not a public/external API.
  No external contract is broken.
  Scope of change:
    - check() and record() are now coroutine functions (async def).
    - All call sites in trezarr/translate/engine.py and trezarr/discover/gap.py
      MUST use `await ledger.check(...)` and `await ledger.record(...)`.
    - A repo-wide grep gate in tests/integration/test_translate_engine_async_ledger.py
      (test_repo_wide_ledger_await_gate) enforces this at test time.
    - LedgerProtocol (trezarr/output/_ledger_protocol.py) declares the async contract.

Phase-4 migration path:
  The Ledger class exposes a minimal interface (check/record) that Phase 4 has
  swapped for a SQLAlchemy async_sessionmaker backend (LedgerSQLA). Both
  implementations implement LedgerProtocol structurally (@runtime_checkable).
  The JSON field names map 1-to-1 to processed_file table columns.

Atomic write:
  _write() uses NamedTemporaryFile(dir=self._path.parent) + os.replace() — the
  same POSIX-atomic pattern as write.py (D-19).  JSONDecodeError on load falls
  back to an empty ledger with a loud warning — never raises (Pitfall 4).
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from trezarr.output._ledger_protocol import LedgerProtocol  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass
class LedgerEntry:
    """A single processed-file record.

    Field names match the Phase-4 processed_file SQLAlchemy column names (D-20).

    Attributes:
        source_path:    Absolute path to the source subtitle file.
        output_path:    Absolute path to the written .vi.srt sidecar, or None
                        if the translation was quarantined / not yet written.
        status:         Current processing status: "done" | "quarantined" | "in_progress".
        content_hash:   source-subtitle content hash (SHA-256[:16] of source file bytes
                        at processing time). This IS the source-subtitle hash — not the
                        vi-sidecar hash. Used for skip/regenerate logic (D-20, D-27).
                        Per Phase 3 D-27 + 03-RESEARCH.md Pitfall 7: no parallel
                        `source_sub_hash` field is added because that would create the
                        divergence risk (two fields drifting between translate_file()'s
                        skip logic and the gap-detection re-translate check).
        series_id:      Optional series identifier (reserved for Phase-4 foreign key).
        source_lang:    Optional ISO-639 language code of the source subtitle (e.g. "en").
        episode_key:    Optional episode identifier string (reserved for Phase-4 cross-linking).
        translated_at:  ISO-8601 UTC timestamp of the last successful translation, or None.
        quarantine_path: Absolute path to the quarantine JSON artifact, or None.
    """
    source_path: str
    output_path: str | None
    status: Literal["done", "quarantined", "in_progress"]
    content_hash: str
    series_id: str | None = None
    source_lang: str | None = None
    episode_key: str | None = None
    translated_at: str | None = None
    quarantine_path: str | None = None


class Ledger:
    """JSON-backed idempotency ledger for processed subtitle files.

    Stores a dict[source_path → LedgerEntry] serialised as a JSON file on disk.
    Reads the full ledger into memory on construction; writes atomically (via
    NamedTemporaryFile + os.replace) on every record() call.

    Interface contract (swap-compatible with Phase-4 SQLAlchemy backend):
        ledger.check(source_path) -> LedgerEntry | None
        ledger.record(entry: LedgerEntry) -> None
        Ledger.content_hash(source_bytes: bytes) -> str
    """

    def __init__(self, ledger_path: str | Path) -> None:
        """Initialise the ledger from the given JSON file path.

        If the file does not exist, starts with an empty ledger.
        If the file exists but contains invalid JSON, logs a warning and starts
        with an empty ledger (never raises — Pitfall 4).

        Args:
            ledger_path: Path to the JSON ledger file (e.g. /config/processed_files.json).
        """
        self._path = Path(ledger_path)
        self._data: dict[str, LedgerEntry] = self._load()

    def _load(self) -> dict[str, LedgerEntry]:
        """Load the ledger from disk.

        Returns an empty dict if the file does not exist or contains corrupt data.

        CR-03: the per-entry try/except previously caught only (TypeError, KeyError),
        which let an AttributeError escape when an entry's value was a non-dict
        (e.g. a stray scalar or list at a key — common after a partial Phase-4
        schema migration or hand-edit). The top-level `raw` was also assumed to
        be a dict, so a JSON array at top-level crashed before the loop began.
        Both gaps violated the "never raises (Pitfall 4)" contract documented in
        the module docstring. We now guard the top-level shape AND each entry
        shape before iteration, and widen the per-entry catch to also include
        AttributeError + ValueError.
        """
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            logger.warning("Ledger at %s is corrupt JSON — starting fresh", self._path)
            return {}

        # CR-03: a JSON array / scalar / null at top-level previously raised
        # AttributeError on `raw.items()`. Guard explicitly so the never-raises
        # contract holds for any legal-but-wrong-shape JSON.
        if not isinstance(raw, dict):
            logger.warning(
                "Ledger at %s is not a JSON object (got %s) — starting fresh",
                self._path, type(raw).__name__,
            )
            return {}

        # Parse entries individually so a single malformed/extended record only skips
        # that entry rather than dropping the entire ledger (WR-07: forward-compat schema drift).
        valid_keys = {f.name for f in dataclasses.fields(LedgerEntry)}
        out: dict[str, LedgerEntry] = {}
        for k, v in raw.items():
            # CR-03: a non-dict value at an entry key (a scalar, list, or None)
            # previously raised AttributeError from `v.items()` outside the
            # try/except and aborted the whole load. Pre-filter explicitly.
            if not isinstance(v, dict):
                logger.warning(
                    "Ledger entry %r is not an object (got %s) — skipping that entry",
                    k, type(v).__name__,
                )
                continue
            try:
                out[k] = LedgerEntry(**{kk: vv for kk, vv in v.items() if kk in valid_keys})
            except (TypeError, KeyError, AttributeError, ValueError):
                logger.warning("Ledger entry %r is malformed — skipping that entry", k)
        return out

    async def check(self, source_path: str | Path) -> LedgerEntry | None:
        """Return the ledger entry for source_path, or None if not recorded.

        BREAKING INTERNAL API CHANGE (Phase 4): this method is now async.
        All call sites MUST use `await ledger.check(...)`.

        Args:
            source_path: Absolute path to the source subtitle file (str or Path).

        Returns:
            The LedgerEntry if source_path is in the ledger, else None.
        """
        return self._data.get(str(source_path))

    async def record(self, entry: LedgerEntry) -> None:
        """Record (insert or update) an entry in the ledger and persist to disk.

        BREAKING INTERNAL API CHANGE (Phase 4): this method is now async.
        All call sites MUST use `await ledger.record(...)`.

        Uses the same NamedTemporaryFile + os.replace atomic write pattern as write.py
        so a crash during write never leaves a partial/corrupt ledger file.

        WR-04: the underlying ``_write`` is synchronous blocking file I/O
        (NamedTemporaryFile + json.dump + os.replace + fsync). Running it
        directly on the asyncio event loop thread violates the "async
        everywhere — no sync sqlite3/file I/O in the event loop" contract
        documented on ``_ledger_protocol.py``. ``asyncio.to_thread`` hands the
        write off to the default executor so the loop yields back to other
        tasks. Phase 4 should not import Ledger in production (LedgerSQLA is
        the authoritative backend) but the one-shot JSON→SQLite migration
        path still touches it indirectly — and a slow sync write can
        starve the LLM-translate semaphore for a few hundred milliseconds.

        Args:
            entry: The LedgerEntry to record.  entry.source_path is the dict key.
        """
        self._data[entry.source_path] = entry
        await asyncio.to_thread(self._write)

    def _write(self) -> None:
        """Atomically write the in-memory ledger to self._path as formatted JSON.

        Creates the parent directory if it does not exist, writes to a sibling temp
        file in self._path.parent (same filesystem → os.replace is atomic), then
        renames to the final path.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                suffix='.tmp',
                dir=self._path.parent,
                delete=False,
            ) as f:
                tmp_path = Path(f.name)
                json.dump({k: asdict(v) for k, v in self._data.items()}, f, indent=2)
            os.replace(tmp_path, self._path)
            tmp_path = None  # prevent cleanup in finally — rename succeeded
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()  # cleanup if write failed before os.replace

    @staticmethod
    def content_hash(source_bytes: bytes) -> str:
        """Compute a 16-character SHA-256 hex digest of source_bytes.

        The hash is used as the idempotency key: if the source file bytes have not
        changed since last processing, the ledger entry's content_hash will match
        and the file will be skipped.

        Args:
            source_bytes: Raw bytes read from the source subtitle file.

        Returns:
            A 16-character lowercase hex string (first 64 bits of SHA-256).
        """
        return hashlib.sha256(source_bytes).hexdigest()[:16]
