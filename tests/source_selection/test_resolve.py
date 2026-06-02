"""Wave 0 RED stubs for resolve_effective_settings (SVC-05, D-112).

All imports target trezarr.source_selection.resolve which does not exist yet.
xfail(strict=False) ensures stubs are XFAIL not FAILED during Wave 0.

resolve_effective_settings(series_dto, settings) -> (source_lang_priority, model_override | None, effective_model)

Covers:
  D-112  Per-series source_lang_override wins over global settings.source_lang_priority
  D-112  series_dto with source_lang_override=None → falls back to global
  D-113  series_dto with model_override → returned model is the override
  D-112  resolve_effective_settings(None, settings) → returns global defaults

The stubs construct a minimal fake TrezarrSettings via monkeypatch to avoid
requiring all environment variables.
"""
from __future__ import annotations

import pytest


def _make_settings(monkeypatch, **overrides):
    """Build a TrezarrSettings with test-safe defaults via monkeypatch."""
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    defaults = dict(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="global-model",
        source_lang_priority=["en"],
    )
    defaults.update(overrides)
    return TrezarrSettings(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# Stubs (xfail — trezarr.source_selection.resolve does not exist yet)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="resolve_effective_settings not yet implemented (SVC-05 / D-112, Phase 10)",
)
def test_per_series_source_override_wins(monkeypatch):
    """series_dto.source_lang_override wins over global settings.source_lang_priority (D-112).

    When a series has an explicit source_lang_override, that list is the
    effective source priority regardless of global settings.
    """
    from trezarr.source_selection.resolve import resolve_effective_settings  # type: ignore[import-not-found]

    settings = _make_settings(monkeypatch, source_lang_priority=["en"])

    # Minimal DTO-like object with per-series override
    class _SeriesDto:
        source_lang_override = ["ko", "en"]
        model_override = None

    result = resolve_effective_settings(_SeriesDto(), settings)
    # result is (source_priority, model_override_or_none, effective_model)
    source_priority = result[0]
    assert source_priority == ["ko", "en"], (
        f"Expected per-series ['ko','en'] to win over global ['en'], got {source_priority!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="resolve_effective_settings not yet implemented (SVC-05 / D-112, Phase 10)",
)
def test_null_inherits_global_source(monkeypatch):
    """series_dto.source_lang_override=None → falls back to settings.source_lang_priority (D-112)."""
    from trezarr.source_selection.resolve import resolve_effective_settings  # type: ignore[import-not-found]

    settings = _make_settings(monkeypatch, source_lang_priority=["en", "zh"])

    class _SeriesDto:
        source_lang_override = None
        model_override = None

    result = resolve_effective_settings(_SeriesDto(), settings)
    source_priority = result[0]
    assert source_priority == ["en", "zh"], (
        f"Expected global fallback ['en','zh'], got {source_priority!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="resolve_effective_settings not yet implemented (SVC-05 / D-113, Phase 10)",
)
def test_null_inherits_global_model(monkeypatch):
    """series_dto.model_override='gpt-4o' → effective model is 'gpt-4o' (D-113)."""
    from trezarr.source_selection.resolve import resolve_effective_settings  # type: ignore[import-not-found]

    settings = _make_settings(monkeypatch, llm_model="global-model")

    class _SeriesDto:
        source_lang_override = None
        model_override = "gpt-4o"

    result = resolve_effective_settings(_SeriesDto(), settings)
    # result[1] = model_override (or None), result[2] = effective_model
    effective_model = result[2] if len(result) > 2 else result[1]
    assert effective_model == "gpt-4o", (
        f"Expected model_override 'gpt-4o' to be used, got {effective_model!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="resolve_effective_settings not yet implemented (SVC-05 / D-112, Phase 10)",
)
def test_none_series_dto_uses_global(monkeypatch):
    """resolve_effective_settings(None, settings) → global defaults (D-112 null-series path)."""
    from trezarr.source_selection.resolve import resolve_effective_settings  # type: ignore[import-not-found]

    settings = _make_settings(monkeypatch, source_lang_priority=["en"], llm_model="global-model")

    result = resolve_effective_settings(None, settings)
    source_priority = result[0]
    assert source_priority == ["en"], (
        f"Expected global ['en'] when series_dto=None, got {source_priority!r}"
    )
