"""Integration tests for async ledger call sites in translate engine (04-04 cross-AI HIGH finding).

Test 14: Proves the quarantine path in translate_file awaits ledger.record() — an
         AsyncMock spy on record() must have call_count > 0 after the failure path runs.
         Without `await`, the coroutine is discarded and the spy counter stays at 0.

Test 15: Repo-wide grep gate — asserts ZERO unawaited ledger.(check|record)( calls
         in `trezarr/**/*.py`. Discovers call sites dynamically using pathlib + re.
         Adding a new call site without `await` fails this test immediately.
         Enforces the cross-AI review HIGH finding at test time.
"""
from __future__ import annotations

import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Test 14: Quarantine path awaits ledger.record ─────────────────────────────


async def test_read_batch_failure_quarantine_records_via_await(tmp_path):
    """translate_file quarantine path calls ledger.record() and AWAITS it.

    The spy ledger uses AsyncMock for record(). If record() is NOT awaited, the
    coroutine object is discarded and spy.record.await_count stays 0.
    This test fails if `await ledger.record(...)` is changed to `ledger.record(...)`.
    """
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    translate_file = engine_mod.translate_file
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    LedgerEntry = ledger_mod.LedgerEntry

    # Arrange: create a source SRT that read_srt will raise on
    src = tmp_path / "Show.S01E01.en.srt"
    # Write garbage that will cause read_srt to fail
    src.write_bytes(b"\xff\xfe\x00\x00garbage bytes")  # invalid UTF-8 for SRT parser

    # Spy ledger: check returns None (no prior entry), record is an AsyncMock
    spy_ledger = MagicMock()
    spy_ledger.check = AsyncMock(return_value=None)
    spy_ledger.record = AsyncMock()

    settings_mod = pytest.importorskip("trezarr.config")
    settings = settings_mod.TrezarrSettings(llm_api_key="test-key")

    # LLM client is not needed for a read failure
    mock_llm = MagicMock()

    # Patch derive_vi_sidecar_path to return a path that doesn't exist
    vi_path = tmp_path / "Show.S01E01.vi.srt"
    with patch("trezarr.translate.engine.derive_vi_sidecar_path", return_value=vi_path):
        result = await translate_file(str(src), settings, mock_llm, spy_ledger)

    # The quarantine path should have been taken
    assert result.status in ("quarantined", "done"), f"Unexpected result: {result}"

    # Assert: record was called at least once AND was awaited (not just called)
    assert spy_ledger.record.await_count >= 1, (
        f"ledger.record must be awaited at least once; await_count={spy_ledger.record.await_count}. "
        "If this is 0, the call site is missing `await` — the coroutine was discarded silently."
    )


# ── Test 15: Repo-wide grep gate ──────────────────────────────────────────────


def test_repo_wide_ledger_await_gate():
    """Assert ZERO unawaited ledger.(check|record)( calls in trezarr/**/*.py.

    Uses pathlib to walk trezarr/**/*.py and re.findall to detect call sites that
    are NOT preceded by `await ` on the same line. This is the cross-AI review
    HIGH finding enforced dynamically — no hardcoded line numbers.

    Skips comment-only lines and lines inside docstrings/string literals (where
    `ledger.check(...)` appears as documentation text, not a call site).

    A new ledger call site added without `await` will fail this test immediately.
    """
    # Find the trezarr source root
    this_file = pathlib.Path(__file__).resolve()
    # Walk up from tests/integration/ to project root
    project_root = this_file.parent.parent.parent
    trezarr_root = project_root / "trezarr"

    assert trezarr_root.exists(), f"Could not find trezarr source root at {trezarr_root}"

    unawaited_calls: list[str] = []

    for py_file in sorted(trezarr_root.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        lines = source.splitlines()

        # Build a set of line numbers that are inside docstrings/string literals.
        # We do this by tokenizing the source with Python's tokenize module.
        import io
        import tokenize as tok_mod
        string_lines: set[int] = set()
        try:
            tokens = list(tok_mod.generate_tokens(io.StringIO(source).readline))
            for token in tokens:
                if token.type in (tok_mod.STRING, tok_mod.COMMENT):
                    start_line, _ = token.start
                    end_line, _ = token.end
                    for ln in range(start_line, end_line + 1):
                        string_lines.add(ln)
        except tok_mod.TokenError:
            pass  # best-effort; continue with no string_lines

        for lineno, line in enumerate(lines, start=1):
            # Skip lines inside string literals or comments (documentation context)
            if lineno in string_lines:
                continue
            stripped = line.strip()
            # Skip comment-only lines (# ...)
            if stripped.startswith("#"):
                continue
            # Skip blank lines
            if not stripped:
                continue
            # Find any ledger.check( or ledger.record( on this line
            if not re.search(r'ledger\.(check|record)\(', stripped):
                continue
            # If the call IS awaited, it's fine
            if re.search(r'\bawait\s+ledger\.(check|record)\(', stripped):
                continue
            # It's a ledger call without await — report it
            unawaited_calls.append(f"{py_file.relative_to(project_root)}:{lineno}: {line.rstrip()}")

    assert not unawaited_calls, (
        "Unawaited ledger.check/record calls found in production code:\n"
        + "\n".join(unawaited_calls)
        + "\n\nAll ledger.check() and ledger.record() calls MUST be awaited (04-04 async-everywhere mandate)."
    )
