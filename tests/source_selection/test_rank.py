"""Wave 0 RED stubs for source-language ranking heuristic (SRC-01, SRC-02, D-107).

All imports target trezarr.source_selection.rank which does not exist yet.
xfail(strict=False) ensures stubs are XFAIL not FAILED during Wave 0.

Covers:
  SRC-02  rank_sources: Korean drama — original_language="ko" → ko ranks first
  SRC-02  rank_sources: US show — original_language="en" → en ranks first
  SRC-02  rank_sources: tier order — no native bias, Tier-1 (non-Latin) beats Tier-3 (Latin)
  SRC-02  rank_sources: fallback chain — fr (Tier-2) beats en (Tier-3) with no native bias
  SRC-01  normalize_original_language: "English" → "en"
  SRC-01  normalize_original_language: "Korean" → "ko"

D-107 sort_key design:
  native (original_language match) → Tier 0 (sort_key = 0.0)
  Tier 1 (non-Latin: ko, zh, ja, ar, ...) → sort_key = 1.0
  Tier 2 (Romance/Germanic with dense syllabary: fr, de, es, ...) → sort_key = 2.0
  Tier 3 (Latin/ASCII: en) → sort_key = 3.0
  (lower sort_key = higher priority — ranks earlier)
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="rank_sources not yet implemented (SRC-02 / D-107, Phase 10)",
)
def test_korean_drama():
    """K-drama: rank_sources(["en","ko"], original_language="ko") → ["ko","en"].

    Korean is the native language (Tier 0 / sort_key=0.0); English is Tier 3.
    """
    from trezarr.source_selection.rank import rank_sources  # type: ignore[import-not-found]

    result = rank_sources(["en", "ko"], "ko")
    assert result == ["ko", "en"], (
        f"K-drama: expected ['ko','en'] (native first), got {result!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="rank_sources not yet implemented (SRC-02 / D-107, Phase 10)",
)
def test_us_show():
    """US show: rank_sources(["ko","en"], original_language="en") → ["en","ko"].

    English is the native language (Tier 0 / sort_key=0.0); Korean is Tier 1.
    """
    from trezarr.source_selection.rank import rank_sources  # type: ignore[import-not-found]

    result = rank_sources(["ko", "en"], "en")
    assert result == ["en", "ko"], (
        f"US show: expected ['en','ko'] (native first), got {result!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="rank_sources not yet implemented (SRC-02 / D-107, Phase 10)",
)
def test_tier_order():
    """Tier order: rank_sources(["zh","en"], None) → ["zh","en"].

    No native bias (original_language=None). zh is Tier 1 (non-Latin);
    en is Tier 3. Tier 1 beats Tier 3 so zh ranks first.
    """
    from trezarr.source_selection.rank import rank_sources  # type: ignore[import-not-found]

    result = rank_sources(["zh", "en"], None)
    assert result == ["zh", "en"], (
        f"Tier order: expected ['zh','en'] (Tier-1 beats Tier-3), got {result!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="rank_sources not yet implemented (SRC-02 / D-107, Phase 10)",
)
def test_fallback_chain():
    """Fallback chain: rank_sources(["fr","en"], None) → ["fr","en"].

    No native bias. fr is Tier 2 (Romance); en is Tier 3. Tier 2 beats Tier 3.
    """
    from trezarr.source_selection.rank import rank_sources  # type: ignore[import-not-found]

    result = rank_sources(["fr", "en"], None)
    assert result == ["fr", "en"], (
        f"Fallback chain: expected ['fr','en'] (Tier-2 beats Tier-3), got {result!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="normalize_original_language not yet implemented (SRC-01, Phase 10)",
)
def test_normalize_original_language_english():
    """normalize_original_language("English") → "en" (SRC-01 ISO 639-1 normalization)."""
    from trezarr.source_selection.rank import normalize_original_language  # type: ignore[import-not-found]

    result = normalize_original_language("English")
    assert result == "en", (
        f"Expected normalize_original_language('English') == 'en', got {result!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="normalize_original_language not yet implemented (SRC-01, Phase 10)",
)
def test_normalize_original_language_korean():
    """normalize_original_language("Korean") → "ko" (SRC-01 ISO 639-1 normalization)."""
    from trezarr.source_selection.rank import normalize_original_language  # type: ignore[import-not-found]

    result = normalize_original_language("Korean")
    assert result == "ko", (
        f"Expected normalize_original_language('Korean') == 'ko', got {result!r}"
    )
