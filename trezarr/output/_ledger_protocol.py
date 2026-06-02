"""LedgerProtocol — typing.Protocol declaring the async Ledger contract (Phase 4).

BREAKING INTERNAL API CHANGE (Phase 4): Ledger.check and Ledger.record were
sync in Phase 2. As of Phase 4 they are ASYNC in both implementations (Ledger
and LedgerSQLA). Rationale: CLAUDE.md mandates 'Async everywhere — no sync
sqlite3 calls in the FastAPI/async event loop'. This is an INTERNAL change
only — the Ledger is not a public/external API. No external contract is broken.

Both Ledger (trezarr/output/ledger.py) and LedgerSQLA (trezarr/output/ledger_sqla.py)
implicitly implement this Protocol. Type-check callers by annotating the ledger
parameter as LedgerProtocol.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from trezarr.output.ledger import LedgerEntry


@runtime_checkable
class LedgerProtocol(Protocol):
    """Structural protocol for the async idempotency ledger.

    @runtime_checkable so isinstance(obj, LedgerProtocol) works in tests.

    Design decisions honoured:
      D-37  Both Ledger (JSON-backed) and LedgerSQLA (SQLAlchemy-backed) implement
            this protocol. The call-site data shape (LedgerEntry field names) is the
            frozen contract from D-20; sync-vs-async is NOT part of that contract.
      D-38  Async everywhere: check and record are async coroutines, ensuring the
            FastAPI/asyncio event loop is never blocked by database I/O.
    """

    async def check(self, source_path: "str | Path") -> "LedgerEntry | None":
        """Return the existing ledger entry for source_path, or None.

        Args:
            source_path: Absolute path to the source subtitle file (str or Path).

        Returns:
            The LedgerEntry if source_path is known, else None.
        """
        ...

    async def record(self, entry: "LedgerEntry") -> None:
        """Persist or update the ledger entry (upsert semantics).

        Args:
            entry: The LedgerEntry to persist. entry.source_path is the unique key.
        """
        ...

    async def check_by_output_path(self, output_path: "str | Path") -> "LedgerEntry | None":
        """Return any ledger entry whose output_path matches — secondary D-110 check.

        Used by gap.is_eligible Case 1.5 to detect Trezarr-owned vi sidecars
        written from a different (lower-priority) source path.

        Args:
            output_path: Absolute path to the output (vi sidecar) file (str or Path).

        Returns:
            The LedgerEntry if output_path is known, else None.
        """
        ...

    @staticmethod
    def content_hash(source_bytes: bytes) -> str:
        """Return a short deterministic hash of source_bytes.

        Args:
            source_bytes: Raw bytes of the source subtitle file.

        Returns:
            A 16-character lowercase hex string (first 64 bits of SHA-256).
        """
        ...
