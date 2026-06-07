"""Tests for Pass-1 Bible analysis audit fixes (H2 Hán-Việt name terms, M2 chunk loop).

Covers the audit fixes applied to trezarr.bible.analyze:
  H2 — plan_character_name_terms prefers the inferred Hán-Việt vietnamese_rendering;
       CharacterInference round-trips the additive vietnamese_rendering field (no migration).
  M2 — analyze_file's real chunk loop unions per-chunk results de-duplicated (no dropped tail),
       tolerates a single bad chunk, raises only when EVERY chunk fails, and the
       Tier-3/disabled early-returns still produce an empty BibleAnalysis with no LLM call.

asyncio_mode="auto" is configured project-wide in pyproject.toml, so async def test
functions run without @pytest.mark.asyncio.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from trezarr.bible.analyze import (
    analyze_file,
    plan_character_name_terms,
    BibleAnalysis,
    BibleAnalysisError,
    CharacterInference,
)
from trezarr.config import TrezarrSettings
from trezarr.subtitles.model import SubDoc, SubLine


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
    """Build a TrezarrSettings with sensible Pass-1 test defaults."""
    defaults = dict(
        llm_api_key="test-key",
        enable_pass1_analysis=True,
        pass1_max_cues_per_chunk=0,  # 0 = no chunking unless overridden
    )
    defaults.update(kwargs)
    return TrezarrSettings(**defaults)


def _empty_bible():
    """A minimal SeriesBibleDTO-like object with no prior content (for _build_analysis_prompt)."""
    from types import SimpleNamespace
    return SimpleNamespace(register_value=None, characters=[], address_map=[], terms=[])


def _term(source_term: str, vietnamese_rendering: str):
    from types import SimpleNamespace
    return SimpleNamespace(source_term=source_term, vietnamese_rendering=vietnamese_rendering)


# ---------------------------------------------------------------------------
# H2 — Hán-Việt name terms + CharacterInference field
# ---------------------------------------------------------------------------


def test_plan_character_name_terms_prefers_vietnamese_rendering():
    """H2: the inferred Hán-Việt rendering pins the name term, not 'Han'→'Han'.

    - CharacterInference(original_latin_name='Han', vietnamese_rendering='Hàn') with no
      existing term → NameTermSpec rendering 'Hàn' (not 'Han').
    - An existing Term Dictionary rendering for the Latin name still wins (the existing
      'Han' term is preserved, not clobbered or re-planned).
    - With neither an existing term nor a vietnamese_rendering, canonical falls back to the
      raw Latin name.
    """
    # (1) inferred Hán-Việt rendering pins the term
    specs = plan_character_name_terms(
        [CharacterInference(original_latin_name="Han", vietnamese_rendering="Hàn")],
        existing_terms=[],
    )
    spec = next(s for s in specs if s.source_term == "Han")
    assert spec.vietnamese_rendering == "Hàn", (
        f"Expected inferred Hán-Việt 'Hàn', got {spec.vietnamese_rendering!r}"
    )

    # (2) existing Term Dictionary rendering wins — the existing 'Han' is left untouched
    # (plan_character_name_terms skips a source form already present in existing_terms, so
    # the human/prior rendering 'Hàn Lập' is never clobbered by the inferred 'Hàn').
    specs2 = plan_character_name_terms(
        [CharacterInference(original_latin_name="Han", vietnamese_rendering="Hàn")],
        existing_terms=[_term("Han", "Hàn Lập")],
    )
    assert all(s.source_term.lower() != "han" for s in specs2), (
        "An existing 'Han' term must win — no override spec should be re-planned for it"
    )

    # (3) neither existing term nor vietnamese_rendering → fall back to the Latin name
    specs3 = plan_character_name_terms(
        [CharacterInference(original_latin_name="Daisy")],
        existing_terms=[],
    )
    spec3 = next(s for s in specs3 if s.source_term == "Daisy")
    assert spec3.vietnamese_rendering == "Daisy", (
        f"Expected fallback to Latin name 'Daisy', got {spec3.vietnamese_rendering!r}"
    )


def test_character_inference_has_vietnamese_rendering_field():
    """H2: CharacterInference round-trips vietnamese_rendering and defaults to None (no migration).

    The field is a pure Pydantic inference field — model_validate accepts it, attribute
    access returns it, and it defaults to None when omitted.
    """
    c = CharacterInference.model_validate(
        {"original_latin_name": "Feng Tianji", "vietnamese_rendering": "Phong Thiên Cực"}
    )
    assert c.vietnamese_rendering == "Phong Thiên Cực"
    assert c.original_latin_name == "Feng Tianji"

    # Omitted → defaults to None (no DB migration needed; pure Pydantic).
    c2 = CharacterInference(original_latin_name="Daisy")
    assert c2.vietnamese_rendering is None


# ---------------------------------------------------------------------------
# M2 — Pass-1 chunk loop
# ---------------------------------------------------------------------------


def _chunk_client(per_chunk: dict[str, BibleAnalysis | str]):
    """Build a fake LLMClient whose .call() returns a value keyed by a cue in the chunk.

    The fake inspects the prompt (messages[0]['content']) for one of the marker substrings
    in ``per_chunk`` and returns the mapped BibleAnalysis (Tier-1) or raw JSON string (Tier-2).
    """
    client = AsyncMock()
    client._mode = "json_schema"

    async def _call(messages=None, response_model=None, **kwargs):
        prompt = messages[0]["content"] if messages else ""
        for marker, value in per_chunk.items():
            if marker in prompt:
                return value
        raise AssertionError(f"no per_chunk marker matched the prompt; markers={list(per_chunk)}")

    client.call = AsyncMock(side_effect=_call)
    return client


async def test_analyze_file_chunk_loop_covers_all_cues():
    """M2: chunking issues one call per chunk and the merged result drops no tail cue.

    With pass1_max_cues_per_chunk=2 and a 5-cue source_doc → 3 chunks → 3 LLM calls. The
    merged BibleAnalysis unions characters/terms/address_map de-duplicated and keeps the
    first non-empty register_value. A character appearing ONLY in the last chunk is present
    in the merged result (no dropped tail).
    """
    settings = _make_settings(pass1_max_cues_per_chunk=2)
    # 5 cues, each tagged so the fake client can identify which chunk it is in.
    source_doc = _make_subdoc(["CUE_A x", "CUE_B y", "CUE_C z", "CUE_D w", "CUE_E v"])

    # chunk0 = [CUE_A, CUE_B], chunk1 = [CUE_C, CUE_D], chunk2 = [CUE_E]
    chunk0 = BibleAnalysis(
        register_value="xianxia",
        characters=[CharacterInference(original_latin_name="Alpha")],
    )
    chunk1 = BibleAnalysis(
        register_value="cultivation",  # later register must NOT override the first non-empty
        characters=[CharacterInference(original_latin_name="Beta")],
    )
    # Character that appears ONLY in the last chunk — must survive the merge.
    chunk2 = BibleAnalysis(characters=[CharacterInference(original_latin_name="Tail")])

    client = _chunk_client({"CUE_A": chunk0, "CUE_C": chunk1, "CUE_E": chunk2})

    result = await analyze_file(
        source_doc=source_doc,
        bible=_empty_bible(),
        arr_metadata={"title": "Chunk Show"},
        llm_client=client,
        settings=settings,
        episode_key="S01E01",
    )

    assert client.call.await_count == 3, (
        f"Expected one LLM call per chunk (3), got {client.call.await_count}"
    )
    names = {c.original_latin_name for c in result.characters}
    assert names == {"Alpha", "Beta", "Tail"}, f"Merged characters dropped cues: {names}"
    assert result.register_value == "xianxia", (
        f"First non-empty register_value must be kept, got {result.register_value!r}"
    )


async def test_analyze_file_chunk_loop_tolerates_one_bad_chunk():
    """M2 tolerance: one unparseable chunk is skipped; all-bad raises; Tier-3/disabled empty.

    - One chunk returns invalid JSON (Tier-2 path → ValidationError) but others succeed →
      analyze_file returns the merged result of the good chunks (no BibleAnalysisError).
    - When EVERY chunk fails to parse → BibleAnalysisError is raised.
    - Tier-3 (_mode=='text') and enable_pass1_analysis=False return an empty BibleAnalysis
      with NO LLM call.
    """
    settings = _make_settings(pass1_max_cues_per_chunk=2)
    source_doc = _make_subdoc(["CUE_A x", "CUE_B y", "CUE_C z", "CUE_D w", "CUE_E v"])

    # One good chunk + one bad (invalid JSON) + one good. The bad chunk uses a Tier-2-style
    # raw string that fails model_validate_json.
    good0 = BibleAnalysis(characters=[CharacterInference(original_latin_name="Alpha")])
    good2 = BibleAnalysis(characters=[CharacterInference(original_latin_name="Tail")])
    client = _chunk_client({"CUE_A": good0, "CUE_C": "not json {{{", "CUE_E": good2})

    result = await analyze_file(
        source_doc=source_doc,
        bible=_empty_bible(),
        arr_metadata={"title": "Tolerant Show"},
        llm_client=client,
        settings=settings,
        episode_key="S01E01",
    )
    names = {c.original_latin_name for c in result.characters}
    assert names == {"Alpha", "Tail"}, (
        f"One bad chunk must not lose the good chunks; merged names={names}"
    )

    # EVERY chunk fails → BibleAnalysisError.
    client_all_bad = _chunk_client(
        {"CUE_A": "bad {{{", "CUE_C": "also bad {{{", "CUE_E": "still bad {{{"}
    )
    with pytest.raises(BibleAnalysisError):
        await analyze_file(
            source_doc=source_doc,
            bible=_empty_bible(),
            arr_metadata={"title": "Broken Show"},
            llm_client=client_all_bad,
            settings=settings,
            episode_key="S01E01",
        )

    # Tier-3 (_mode == 'text') → empty BibleAnalysis, no LLM call.
    tier3 = AsyncMock()
    tier3._mode = "text"
    tier3.call = AsyncMock()
    res_tier3 = await analyze_file(
        source_doc=source_doc,
        bible=_empty_bible(),
        arr_metadata={"title": "Tier3 Show"},
        llm_client=tier3,
        settings=settings,
        episode_key="S01E01",
    )
    assert res_tier3.characters == [] and res_tier3.register_value is None
    assert tier3.call.await_count == 0, "Tier-3 endpoint must not make an LLM call (D-47)"

    # enable_pass1_analysis=False → empty BibleAnalysis, no LLM call.
    disabled_settings = _make_settings(enable_pass1_analysis=False, pass1_max_cues_per_chunk=2)
    disabled_client = AsyncMock()
    disabled_client._mode = "json_schema"
    disabled_client.call = AsyncMock()
    res_disabled = await analyze_file(
        source_doc=source_doc,
        bible=_empty_bible(),
        arr_metadata={"title": "Disabled Show"},
        llm_client=disabled_client,
        settings=disabled_settings,
        episode_key="S01E01",
    )
    assert res_disabled.characters == []
    assert disabled_client.call.await_count == 0, (
        "enable_pass1_analysis=False must not make an LLM call (D-50)"
    )


# ---------------------------------------------------------------------------
# FIX-B — thinking kwarg threading (260607-dbe)
# ---------------------------------------------------------------------------


async def test_analyze_file_passes_thinking_kwarg():
    """analyze_file() passes thinking=settings.enable_reasoning_analysis to llm_client.call.

    When enable_reasoning_analysis=True, every _analyze_one_chunk LLM call must be made
    with keyword argument thinking=True.
    """
    from unittest.mock import AsyncMock

    settings = _make_settings(enable_reasoning_analysis=True, pass1_max_cues_per_chunk=0)
    source_doc = _make_subdoc(["Hello world.", "Who are you?"])

    # Minimal valid BibleAnalysis JSON response
    valid_analysis = BibleAnalysis(
        register_value="xianxia",
        characters=[CharacterInference(original_latin_name="Han")],
    )

    call_kwargs_captured: list[dict] = []

    async def _capturing_call(messages=None, response_model=None, **kwargs):
        call_kwargs_captured.append(dict(kwargs))
        return valid_analysis

    llm_client = AsyncMock()
    llm_client._mode = "json_schema"
    llm_client.call = AsyncMock(side_effect=_capturing_call)

    result = await analyze_file(
        source_doc=source_doc,
        bible=_empty_bible(),
        arr_metadata={"title": "Test Show"},
        llm_client=llm_client,
        settings=settings,
        episode_key="S01E01",
    )

    assert llm_client.call.await_count >= 1, "analyze_file must make at least one LLM call"
    for kw in call_kwargs_captured:
        assert kw.get("thinking") is True, (
            f"Every _analyze_one_chunk call must pass thinking=True when "
            f"enable_reasoning_analysis=True; got {kw!r}"
        )
    # Basic sanity: result must contain the character we returned
    names = {c.original_latin_name for c in result.characters}
    assert "Han" in names
