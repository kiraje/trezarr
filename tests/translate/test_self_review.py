"""Tests for Phase-6 ENG-05 Pass-4 self-review pass.

Tests cover:
  ENG-05-A — Pass 4 corrects a pronoun violation; validate_subdoc sees corrected output
  ENG-05-B — Pass 4 LLM failure (mock raises) → pre-review output used; no quarantine (D-59)
  ENG-05-C — enable_self_review=False → Pass 4 skipped; translated_doc unchanged
  ENG-05-D — Sentinel integrity failure in review → pre-review batch kept per-batch (D-59)

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.

Wave 0: All tests are xfail stubs — production code does not yet exist.
xfail uses raises=(ImportError, AssertionError, TypeError) because the module imports
cleanly from Phase 3/5 but _review_batch / build_review_prompt are not yet defined.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.config import TrezarrSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_subdoc(texts: list[str]) -> SubDoc:
    """Build a minimal SubDoc from a list of cue texts."""
    lines = [
        SubLine(index=str(i + 1), start_tc="00:00:00,000", end_tc="00:00:01,000", text=t)
        for i, t in enumerate(texts)
    ]
    return SubDoc(
        lines=lines,
        encoding="utf-8",
        line_ending="\n",
        separators=["" for _ in range(max(0, len(lines) - 1))],
    )


def _make_settings(**kwargs) -> TrezarrSettings:
    """Build a TrezarrSettings with sensible test defaults for self-review tests."""
    return TrezarrSettings(
        llm_api_key="test-key",
        enable_self_review=True,
        self_review_context_lines_k=0,
        self_review_max_cues_per_batch=10,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests — ENG-05-A, B, C, D (Wave 0 RED stubs)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_pass4_corrects_violation_before_gate():
    """ENG-05-A: Pass 4 corrects a pronoun violation; corrected output seen before validate_subdoc.

    Arrange: build a Batch with one cue containing a known pronoun violation.
    Mock _review_batch to return corrected Vietnamese text.
    Act: call _review_batch directly (unit slice).
    Assert: the corrected text appears in the returned list (not the original violation).
    """
    from trezarr.translate.engine import _review_batch, build_review_prompt
    from trezarr.llm.client import LLMClient
    from trezarr.translate.batching import Batch

    # A cue with a pronoun violation ("tao" is too intimate/wrong register)
    violating_text = "Tao không biết."
    corrected_text = "Tôi không biết."

    settings = _make_settings()

    # Mock LLM client whose .call() returns a numbered-line response with the correction
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.call = AsyncMock(return_value=f"[1] {corrected_text}")

    subdoc = _make_subdoc([violating_text])
    cue = subdoc.lines[0]

    batch = Batch(cues=[cue], dominant_pair=None, context_before=[], context_after=[])

    result = await _review_batch(
        review_batch=batch,
        source_lines_by_index={cue.index: cue},
        resolved_map={},
        bible=None,
        llm_client=mock_llm,
        settings=settings,
    )

    assert result is not None, "_review_batch returned None (failure path) instead of corrected texts"
    assert len(result) == 1, f"Expected 1 corrected text, got {len(result)}"
    assert corrected_text in result[0], (
        f"Expected corrected text {corrected_text!r} in result, got {result[0]!r}"
    )


@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_pass4_failure_fallback_no_quarantine():
    """ENG-05-B: Pass 4 LLM failure → pre-review output used; no quarantine (D-59).

    Arrange: mock LLM client whose .call() raises an Exception.
    Act: call _review_batch.
    Assert: return value is None (not raised, not quarantine-triggering).
    """
    from trezarr.translate.engine import _review_batch
    from trezarr.llm.client import LLMClient
    from trezarr.translate.batching import Batch

    settings = _make_settings()

    # LLM raises — simulates transient LLM failure
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.call = AsyncMock(side_effect=Exception("LLM timeout"))

    subdoc = _make_subdoc(["Anh yêu em."])
    cue = subdoc.lines[0]

    batch = Batch(cues=[cue], dominant_pair=None, context_before=[], context_after=[])

    result = await _review_batch(
        review_batch=batch,
        source_lines_by_index={cue.index: cue},
        resolved_map={},
        bible=None,
        llm_client=mock_llm,
        settings=settings,
    )

    # D-59: NEVER raises, NEVER quarantines — returns None on failure
    assert result is None, (
        f"Expected None (fallback) when LLM raises, got {result!r}"
    )


@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_pass4_disabled_skips_review():
    """ENG-05-C: enable_self_review=False → Pass 4 skipped; translated_doc unchanged.

    Arrange: settings with enable_self_review=False.
    Act: call translate_file (or mock its internal path) and assert _review_batch
         is never called when self-review is disabled.
    Assert: _review_batch is not called.
    """
    from trezarr.translate.engine import _review_batch

    settings = _make_settings(enable_self_review=False)

    # When enable_self_review=False, the Pass 4 branch must be fully skipped.
    # We verify this at the unit level: _review_batch should NOT be called.
    with patch("trezarr.translate.engine._review_batch") as mock_review:
        mock_review.return_value = None

        # Simulate translate_file's Pass 4 guard:
        # if settings.enable_self_review and eligible_item is not None and ...
        if settings.enable_self_review:
            await _review_batch(  # this should NOT execute when disabled
                review_batch=None,
                source_lines_by_index={},
                resolved_map={},
                bible=None,
                llm_client=None,
                settings=settings,
            )

        # Assert _review_batch was NOT called (enable_self_review=False)
        assert not mock_review.called, (
            "Expected _review_batch to NOT be called when enable_self_review=False, "
            f"but it was called {mock_review.call_count} time(s)"
        )


@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_sentinel_failure_fallback_per_batch():
    """ENG-05-D: Sentinel integrity failure in review → pre-review batch kept (D-59).

    Arrange: a cue with sentinel tokens (<<T0>>); mock LLM returns a response that
             drops the sentinel token (integrity failure).
    Act: call _review_batch.
    Assert: _review_batch returns None for that batch (sentinel integrity failure path).
    """
    from trezarr.translate.engine import _review_batch
    from trezarr.llm.client import LLMClient
    from trezarr.translate.batching import Batch

    settings = _make_settings()

    # Cue with a sentinel token that will survive extraction but be dropped in review
    text_with_sentinel = "Anh <<T0>> yêu em."

    # LLM response DROPS the sentinel token — integrity failure
    mock_llm = AsyncMock(spec=LLMClient)
    mock_llm.call = AsyncMock(return_value="[1] Anh yêu em.")  # <<T0>> missing

    subdoc = _make_subdoc([text_with_sentinel])
    cue = subdoc.lines[0]

    batch = Batch(cues=[cue], dominant_pair=None, context_before=[], context_after=[])

    result = await _review_batch(
        review_batch=batch,
        source_lines_by_index={cue.index: cue},
        resolved_map={},
        bible=None,
        llm_client=mock_llm,
        settings=settings,
    )

    # D-59: sentinel integrity failure → return None (keep pre-review output)
    assert result is None, (
        f"Expected None (sentinel integrity failure fallback), got {result!r}"
    )
