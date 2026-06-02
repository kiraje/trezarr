"""Effective settings resolver (SVC-05, D-112).

Pure function — no I/O, no ORM imports, fully unit-testable in isolation.

Design decisions honoured:
  D-112  resolve_effective_settings is a pure function:
         (series_dto, settings) → (source_priority, register, model)
         Per-series non-NULL overrides win over global config.
  D-113  Model override is resolved HERE (not inside LLMClient) so the single
         global LLMClient and one asyncio.Semaphore (D-06) are preserved.
         The per-call model string is threaded from the engine layer downward.

TYPE_CHECKING-only imports for SeriesDTO and TrezarrSettings avoid circular
import chains: resolve.py → dto.py → store.py → config.py would be circular.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trezarr.bible.dto import SeriesDTO
    from trezarr.config import TrezarrSettings


def resolve_effective_settings(
    series_dto: "SeriesDTO | None",
    settings: "TrezarrSettings",
) -> tuple[list[str], str | None, str]:
    """Resolve effective (source_priority, register, model) for one series.

    Per-series non-NULL overrides win over global config (D-112).
    Series.register is the register override (Phase-8 lock = the override valve).

    Args:
        series_dto: Optional per-series DTO from the Bible. None uses global defaults.
        settings:   TrezarrSettings carrying global source_lang_priority, llm_model.

    Returns:
        A 3-tuple:
          (source_priority, register, model)
          - source_priority: ordered list of source language codes
          - register: str | None (None = no register set for this series)
          - model: str — always a valid string (falls back to settings.llm_model)

    Examples:
        >>> resolve_effective_settings(None, settings)
        (settings.source_lang_priority, None, settings.llm_model)

        >>> # Per-series override wins:
        >>> series_dto.source_lang_override = ["ko", "en"]
        >>> resolve_effective_settings(series_dto, settings)
        (["ko", "en"], series_dto.register_value, series_dto.model_override or settings.llm_model)
    """
    if series_dto is None:
        return settings.source_lang_priority, None, settings.llm_model

    # source_lang_override: per-series list wins over global when non-None (D-112).
    source_priority: list[str] = (
        series_dto.source_lang_override
        if series_dto.source_lang_override is not None
        else settings.source_lang_priority
    )

    # register: the Phase-8 lock value. The Python attribute is register_value
    # (aliased to avoid shadowing the Pydantic classmethod `model.register`).
    # Per PATTERNS.md §resolve.py: use series_dto.register_value, NOT "register".
    # Use getattr with None default so minimal test DTOs (without register_value)
    # do not raise AttributeError.
    register: str | None = getattr(series_dto, "register_value", None)

    # model_override: per-series model string wins over global when non-None (D-113).
    model: str = (
        series_dto.model_override  # type: ignore[attr-defined]
        if series_dto.model_override is not None  # type: ignore[attr-defined]
        else settings.llm_model
    )

    return source_priority, register, model
