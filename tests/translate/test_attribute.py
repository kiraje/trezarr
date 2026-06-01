"""Tests for PRON-01 speaker/addressee attribution (Pass 2).

Tests cover:
  PRON-01 — LineAttribution parsed from mock LLM response
  PRON-01 — Unknown speaker/addressee → safe default (no crash)

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.

No DB access — attribute.py is pure LLM call + Pydantic parsing (D-39).
"""
import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock


from trezarr.bible.dto import CharacterDTO, SeriesBibleDTO
from trezarr.translate.attribute import (
    AttributionConfidence,
    BatchAttribution,
    LineAttribution,
    attribute_batch,
)


# ── Test helpers ───────────────────────────────────────────────────────────────

@dataclass
class _FakeSubLine:
    """Minimal SubLine-like object for test batches (no subtitle module dependency)."""
    text: str
    start_tc: str = "00:00:01,000"
    end_tc: str = "00:00:03,000"


@dataclass
class _FakeBatch:
    """Minimal Batch-like object — has .cues, .context_before, .context_after."""
    cues: list[Any] = field(default_factory=list)
    context_before: list[Any] = field(default_factory=list)
    context_after: list[Any] = field(default_factory=list)


def _make_settings(*, enable_attribution: bool = True, mode: str = "json_schema") -> Any:
    """Return a minimal settings-like namespace."""
    from types import SimpleNamespace
    return SimpleNamespace(
        enable_attribution=enable_attribution,
        attribute_context_lines_k=8,
    )


def _make_llm_client(return_value: Any, mode: str = "json_schema") -> AsyncMock:
    """Return a mock LLMClient with .call returning return_value."""
    client = AsyncMock()
    client.call = AsyncMock(return_value=return_value)
    client._mode = mode
    return client


def _make_bible(characters: list[CharacterDTO]) -> SeriesBibleDTO:
    """Build a minimal SeriesBibleDTO for test use."""
    return SeriesBibleDTO(
        id=1,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=100,
        characters=characters,
        terms=[],
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

async def test_attribution_parsing():
    """LineAttribution and BatchAttribution are parsed from a mock LLM response (PRON-01).

    Assert:
    - LineAttribution importable from trezarr.translate.attribute (satisfied by module-level import)
    - BatchAttribution importable from trezarr.translate.attribute (satisfied by module-level import)
    - Parsing a mock LLM JSON response produces LineAttribution objects with
      speaker and addressee fields populated
    - First entry has speaker="John", confidence=HIGH
    """
    # Set up: two-cue batch, bible with John and Mary
    batch = _FakeBatch(
        cues=[
            _FakeSubLine("I need to talk to you."),
            _FakeSubLine("Sure, what about?"),
        ]
    )
    john = CharacterDTO(id=1, series_id=1, original_latin_name="John", gender="male")
    mary = CharacterDTO(id=2, series_id=1, original_latin_name="Mary", gender="female")
    bible = _make_bible([john, mary])

    # LLM returns a BatchAttribution Tier-1 object (structured output succeeded)
    mock_response = BatchAttribution(
        attributions=[
            LineAttribution(
                line_index=1,
                speaker="John",
                addressee="Mary",
                confidence=AttributionConfidence.HIGH,
            ),
            LineAttribution(
                line_index=2,
                speaker="Mary",
                addressee="John",
                confidence=AttributionConfidence.LOW,
            ),
        ]
    )
    llm_client = _make_llm_client(mock_response)
    settings = _make_settings()

    result = await attribute_batch(batch, bible, llm_client, settings)

    assert len(result) == 2
    assert result[0].speaker == "John"
    assert result[0].addressee == "Mary"
    assert result[0].confidence == AttributionConfidence.HIGH
    assert result[1].speaker == "Mary"
    assert result[1].confidence == AttributionConfidence.LOW


async def test_unmatched_name_safe_default():
    """Unknown speaker/addressee name → safe default returned, no crash (PRON-01, D-43).

    Assert:
    - attribute_batch importable from trezarr.translate.attribute (satisfied by module-level import)
    - When LLM returns a speaker name not in the character roster,
      attribute_batch returns speaker=None, confidence=LOW (not raises)
    """
    batch = _FakeBatch(
        cues=[_FakeSubLine("Hello there.")]
    )
    john = CharacterDTO(id=1, series_id=1, original_latin_name="John", gender="male")
    bible = _make_bible([john])

    # LLM returns a JSON string (Tier 2) with an unrecognised speaker name
    raw_json = json.dumps({
        "attributions": [
            {
                "line_index": 1,
                "speaker": "UnknownPerson",
                "addressee": None,
                "confidence": "high",
            }
        ]
    })
    llm_client = _make_llm_client(raw_json)
    settings = _make_settings()

    # Must not raise
    result = await attribute_batch(batch, bible, llm_client, settings)

    assert len(result) == 1
    # Unmatched name → speaker=None, confidence=LOW (D-43 name-matching rule)
    assert result[0].speaker is None
    assert result[0].confidence == AttributionConfidence.LOW


async def test_tier3_degradation_returns_all_low():
    """Tier-3 (text-only) LLMClient → all-LOW-unknown, no crash (D-47)."""
    batch = _FakeBatch(
        cues=[_FakeSubLine("Text A."), _FakeSubLine("Text B.")]
    )
    bible = _make_bible([])
    llm_client = _make_llm_client("some plain text", mode="text")
    settings = _make_settings()

    result = await attribute_batch(batch, bible, llm_client, settings)

    assert len(result) == 2
    assert all(a.confidence == AttributionConfidence.LOW for a in result)
    assert all(a.speaker is None for a in result)
    assert all(a.addressee is None for a in result)
    # LLM should NOT have been called (Tier-3 fast-path before the call)
    llm_client.call.assert_not_called()


async def test_enable_attribution_false_returns_all_low():
    """enable_attribution=False → all-LOW-unknown without LLM call (D-50)."""
    batch = _FakeBatch(cues=[_FakeSubLine("Hello.")])
    bible = _make_bible([])
    llm_client = _make_llm_client(BatchAttribution(attributions=[]))
    settings = _make_settings(enable_attribution=False)

    result = await attribute_batch(batch, bible, llm_client, settings)

    assert len(result) == 1
    assert result[0].confidence == AttributionConfidence.LOW
    assert result[0].speaker is None
    llm_client.call.assert_not_called()


async def test_missing_indices_filled_with_low():
    """If LLM returns fewer entries than batch.cues, missing indices get LOW defaults (Pitfall E)."""
    batch = _FakeBatch(
        cues=[_FakeSubLine("A."), _FakeSubLine("B."), _FakeSubLine("C.")]
    )
    john = CharacterDTO(id=1, series_id=1, original_latin_name="John", gender="male")
    bible = _make_bible([john])

    # Only 1 of 3 entries returned
    mock_response = BatchAttribution(
        attributions=[
            LineAttribution(line_index=1, speaker="John", confidence=AttributionConfidence.HIGH)
        ]
    )
    llm_client = _make_llm_client(mock_response)
    settings = _make_settings()

    result = await attribute_batch(batch, bible, llm_client, settings)

    assert len(result) == 3
    assert result[0].speaker == "John"
    assert result[0].confidence == AttributionConfidence.HIGH
    # Missing indices 2 and 3 → LOW defaults
    assert result[1].line_index == 2
    assert result[1].speaker is None
    assert result[1].confidence == AttributionConfidence.LOW
    assert result[2].line_index == 3
    assert result[2].speaker is None


async def test_tier2_invalid_json_returns_all_low():
    """Tier-2 JSON parse failure → all-LOW-unknown, no crash (D-47)."""
    batch = _FakeBatch(cues=[_FakeSubLine("Hello.")])
    bible = _make_bible([])
    llm_client = _make_llm_client("this is not valid json")
    settings = _make_settings()

    result = await attribute_batch(batch, bible, llm_client, settings)

    assert len(result) == 1
    assert result[0].confidence == AttributionConfidence.LOW
    assert result[0].speaker is None
