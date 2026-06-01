"""RED stubs for ENG-04 Pass-1 Bible analysis orchestration.

Tests cover:
  ENG-04 — Pass 1 (Bible analysis) runs and Bible updated BEFORE any line is translated
  ENG-04 — Pass 1 failure quarantines the file, writes no translation output

All trezarr.* imports are deferred inside each test function body so pytest
collection succeeds even when the implementation module does not yet exist.
Tests are marked xfail(strict=False) — they pass at Wave 0 (ImportError expected)
and will be turned GREEN in Phase 5 Plan 02.

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.
"""
import pytest


@pytest.mark.xfail(strict=False, reason="trezarr.bible.analyze not yet implemented", raises=ImportError)
def test_pass1_runs_before_pass3():
    """Pass 1 (Bible analysis) runs and Bible is updated BEFORE any line is translated (ENG-04).

    Assert:
    - analyze_file() is called (callable importable from trezarr.bible.analyze)
    - Bible state is updated with character/address-map data before Pass 3 starts
    """
    from trezarr.bible.analyze import analyze_file
    assert False, "stub — implement in Plan 05-02"


@pytest.mark.xfail(strict=False, reason="trezarr.bible.analyze not yet implemented", raises=ImportError)
def test_pass1_failure_quarantines():
    """Pass 1 failure quarantines the file and writes no translation output (ENG-04).

    Assert:
    - BibleAnalysisError is importable from trezarr.bible.analyze
    - When Pass 1 raises BibleAnalysisError, translate_file returns status='quarantined'
    - No .vi.srt output file is written
    """
    from trezarr.bible.analyze import BibleAnalysisError
    assert False, "stub — implement in Plan 05-02"
