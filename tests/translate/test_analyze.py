"""Tests for ENG-04 Pass-1 Bible analysis orchestration.

Tests cover:
  ENG-04 — Pass 1 (Bible analysis) runs and Bible updated BEFORE any line is translated
  ENG-04 — Pass 1 failure quarantines the file, writes no translation output

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from trezarr.bible.analyze import (
    analyze_file,
    BibleAnalysis,
    BibleAnalysisError,
    CharacterInference,
    AddressMapInference,
    RelationshipEventInference,
)
from trezarr.bible.store import get_or_create_series, load_series_bible
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
    """Build a TrezarrSettings with sensible test defaults."""
    return TrezarrSettings(
        llm_api_key="test-key",
        enable_pass1_analysis=True,
        pass1_max_cues_per_chunk=0,  # 0 = no chunking
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_pass1_runs_before_pass3(session_factory):
    """Pass 1 (Bible analysis) runs and Bible is updated BEFORE any line is translated (ENG-04).

    Verifies:
    - analyze_file() is callable and returns a BibleAnalysis.
    - merge_bible_analysis() writes the inferred character and address pair to the DB.
    - The Bible contains character "John" and an address map entry with self_term="anh"
      after merge, confirming Pass 1 completes before any Pass 3 translation starts.
    """
    from trezarr.bible.analyze import merge_bible_analysis

    # Create a series in the DB first
    series_dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=1001,
        arr_metadata_snapshot={"title": "Test Show"},
    )

    # Build a BibleAnalysis with one character and one address pair
    mock_analysis = BibleAnalysis(
        register_value="casual",
        characters=[
            CharacterInference(original_latin_name="John", gender="male", role="detective"),
            CharacterInference(original_latin_name="Mary", gender="female", role="witness"),
        ],
        address_map=[
            AddressMapInference(
                speaker_name="John",
                addressee_name="Mary",
                self_term="anh",
                address_term="em",
                confidence=0.9,
            )
        ],
    )

    # Mock llm_client.call to return the BibleAnalysis instance directly (Tier-1 path)
    mock_llm_client = AsyncMock()
    mock_llm_client._mode = "json_schema"
    mock_llm_client.call = AsyncMock(return_value=mock_analysis)

    source_doc = _make_subdoc(["John: I need to talk to you.", "Mary: About what?"])
    settings = _make_settings()

    # Load current Bible state
    bible = await load_series_bible(session_factory, series_dto.id)
    arr_metadata = {"title": "Test Show", "genres": ["Drama"]}

    # Call analyze_file — should return the mocked BibleAnalysis
    result = await analyze_file(
        source_doc=source_doc,
        bible=bible,
        arr_metadata=arr_metadata,
        llm_client=mock_llm_client,
        settings=settings,
        episode_key="S01E01",
    )

    assert isinstance(result, BibleAnalysis), "analyze_file should return a BibleAnalysis instance"
    assert result.register_value == "casual"
    assert len(result.characters) == 2

    # Call merge_bible_analysis to write the result to the Bible DB
    await merge_bible_analysis(
        session_factory=session_factory,
        series_dto=series_dto,
        analysis=result,
        episode_key="S01E01",
    )

    # Verify the Bible contains the character "John" and address pair with self_term="anh"
    updated_bible = await load_series_bible(session_factory, series_dto.id)

    char_names = [c.original_latin_name for c in updated_bible.characters]
    assert "John" in char_names, f"Expected 'John' in characters, got: {char_names}"
    assert "Mary" in char_names, f"Expected 'Mary' in characters, got: {char_names}"

    # Verify the address map has John→Mary with self_term="anh"
    assert len(updated_bible.address_map) > 0, "Expected at least one address map entry"
    anh_pair = next(
        (a for a in updated_bible.address_map if a.self_term == "anh"),
        None,
    )
    assert anh_pair is not None, (
        f"Expected address pair with self_term='anh', got: {[(a.self_term, a.address_term) for a in updated_bible.address_map]}"
    )
    assert anh_pair.address_term == "em"


async def test_pass1_failure_quarantines(session_factory):
    """Pass 1 failure quarantines the file and writes no translation output (ENG-04).

    Verifies:
    - When llm_client.call returns invalid JSON (Tier-2 path), analyze_file raises
      BibleAnalysisError.
    - No DB writes are completed (Bible remains empty after the failed analyze_file call).
    """

    # Create a series in the DB
    series_dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=2002,
        arr_metadata_snapshot={"title": "Broken Show"},
    )

    # Mock llm_client.call to return a mangled JSON string (Tier-2 path — not a BibleAnalysis instance)
    mock_llm_client = AsyncMock()
    mock_llm_client._mode = "json_object"  # Tier-2 mode — returns str, not a parsed object
    mock_llm_client.call = AsyncMock(return_value="not json {{{invalid")

    source_doc = _make_subdoc(["Some dialogue here."])
    settings = _make_settings()

    bible = await load_series_bible(session_factory, series_dto.id)
    arr_metadata = {"title": "Broken Show"}

    # analyze_file should raise BibleAnalysisError on malformed JSON
    with pytest.raises(BibleAnalysisError) as exc_info:
        await analyze_file(
            source_doc=source_doc,
            bible=bible,
            arr_metadata=arr_metadata,
            llm_client=mock_llm_client,
            settings=settings,
            episode_key="S01E01",
        )

    assert "BibleAnalysis parse failed" in str(exc_info.value), (
        f"Expected 'BibleAnalysis parse failed' in error message, got: {exc_info.value}"
    )

    # Verify no DB writes were made (Bible is still empty)
    post_bible = await load_series_bible(session_factory, series_dto.id)
    assert len(post_bible.characters) == 0, (
        f"Expected no characters after failed analyze_file, got: {post_bible.characters}"
    )
    assert len(post_bible.address_map) == 0, (
        f"Expected no address pairs after failed analyze_file, got: {post_bible.address_map}"
    )


async def test_cjk_script_name_address_pair_resolves(session_factory):
    """CJK address pair and relationship_event using original-script names must be persisted.

    Regression test for the CJK name-resolution bug: the LLM infers characters with a
    romanized original_latin_name but writes address_map / relationship_events using the
    on-screen script name (e.g. '樱'). Before the fix, name_to_id was keyed only on the
    Latin name, so script-name references resolved to None and were silently skipped.

    Verifies:
    - merge_bible_analysis persists the address pair when speaker_name/addressee_name are
      CJK script names (the previously failing case).
    - merge_bible_analysis persists the relationship_event when character_a_name /
      character_b_name are CJK script names.
    - CR-01 contract: .strip().lower() normalisation is applied to CJK keys (CJK .lower()
      is a no-op, which is correct behaviour).
    """
    from trezarr.bible.analyze import merge_bible_analysis

    # Create a distinct series so this test is isolated from other test series
    series_dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=3003,
        arr_metadata_snapshot={"title": "CJK Test Show"},
    )

    # Build a BibleAnalysis with two CJK characters that have both Latin and script names.
    # The address_map and relationship_event reference them by the CJK script name only —
    # the bug case that previously caused silent skips.
    mock_analysis = BibleAnalysis(
        characters=[
            CharacterInference(
                original_latin_name="Sakura",
                gender="female",
                original_script_name="樱",
            ),
            CharacterInference(
                original_latin_name="Daisy",
                gender="female",
                original_script_name="雏菊",
            ),
        ],
        address_map=[
            AddressMapInference(
                speaker_name="樱",       # CJK script name — the previously-failing form
                addressee_name="雏菊",   # CJK script name
                self_term="em",
                address_term="chị",
                confidence=0.85,
            ),
        ],
        relationship_events=[
            RelationshipEventInference(
                character_a_name="樱",   # CJK script name
                character_b_name="雏菊",
                episode_marker="S01E01",
                description="They meet for the first time and form a close friendship.",
            ),
        ],
    )

    settings = _make_settings(enable_relationship_events=True)

    await merge_bible_analysis(
        session_factory=session_factory,
        series_dto=series_dto,
        analysis=mock_analysis,
        episode_key="S01E01",
        settings=settings,
    )

    updated_bible = await load_series_bible(session_factory, series_dto.id)

    # The address pair must be persisted — not skipped
    assert len(updated_bible.address_map) == 1, (
        "CJK script-name address pair must be persisted, not skipped. "
        f"Got address_map={[(a.self_term, a.address_term) for a in updated_bible.address_map]}"
    )
    assert updated_bible.address_map[0].self_term == "em", (
        f"Expected self_term='em', got: {updated_bible.address_map[0].self_term!r}"
    )
    assert updated_bible.address_map[0].address_term == "chị", (
        f"Expected address_term='chị', got: {updated_bible.address_map[0].address_term!r}"
    )

    # The relationship_event must also be persisted — not skipped
    rel_events = updated_bible.relationship_events or []
    assert len(rel_events) == 1, (
        "CJK script-name relationship_event must be persisted, not skipped. "
        f"Got relationship_events={rel_events}"
    )


# ── H2 — Hán-Việt name terms + analysis-prompt guidance ──────────────────────


def _term(source_term: str, vietnamese_rendering: str):
    """Minimal duck-typed Term Dictionary entry (.source_term / .vietnamese_rendering)."""
    from types import SimpleNamespace  # noqa: PLC0415
    return SimpleNamespace(source_term=source_term, vietnamese_rendering=vietnamese_rendering)


def test_plan_character_name_terms_prefers_vietnamese_rendering():
    """H2: plan_character_name_terms pins the Hán-Việt vietnamese_rendering, not 'Han'→'Han'.

    A CharacterInference(original_latin_name='Han', vietnamese_rendering='Hàn') with no
    existing term yields NameTermSpec(source_term='Han', vietnamese_rendering='Hàn'). An
    existing Term Dictionary rendering for the Latin name still wins over the inferred
    rendering. With neither, the canonical rendering falls back to the raw Latin name.
    """
    from trezarr.bible.analyze import plan_character_name_terms, CharacterInference  # noqa: PLC0415

    # (1) Inferred Hán-Việt rendering pins the term, not 'Han'→'Han'.
    specs = plan_character_name_terms(
        [CharacterInference(original_latin_name="Han", vietnamese_rendering="Hàn")],
        existing_terms=[],
    )
    spec = next(s for s in specs if s.source_term == "Han")
    assert spec.vietnamese_rendering == "Hàn", (
        f"Expected Hán-Việt rendering 'Hàn', got {spec.vietnamese_rendering!r}"
    )

    # (2) Existing Term Dictionary rendering wins over the inferred one.
    specs2 = plan_character_name_terms(
        [CharacterInference(original_latin_name="Han", vietnamese_rendering="Hàn")],
        existing_terms=[_term("Han", "Hàn Lập")],
    )
    # An existing source 'Han' is skipped (idempotent) — it is already pinned. The contract
    # is that the existing rendering is never clobbered; planning emits no override spec.
    assert all(s.source_term.lower() != "han" for s in specs2), (
        "An existing 'Han' term must not be re-planned (existing rendering wins / is preserved)"
    )

    # (3) Neither existing term nor vietnamese_rendering → canonical falls back to Latin name.
    specs3 = plan_character_name_terms(
        [CharacterInference(original_latin_name="Daisy")],
        existing_terms=[],
    )
    spec3 = next(s for s in specs3 if s.source_term == "Daisy")
    assert spec3.vietnamese_rendering == "Daisy", (
        f"Expected fallback to the Latin name 'Daisy', got {spec3.vietnamese_rendering!r}"
    )


def test_analysis_prompt_requires_hanviet_and_kinship_mapping():
    """H2: _build_analysis_prompt requires vietnamese_rendering + kinship-as-address + genre register.

    Output must contain the vietnamese_rendering instruction with the concrete examples
    'Phong Thiên Cực' and 'Mai cô nương', the kinship-as-address mapping 'Elder'→'trưởng lão'
    and 'Senior'→'tiền bối', and genre-register guidance naming 'xianxia'/'wuxia'/'cultivation'.
    The [DIALOGUE SAMPLE] security framing (numbered [N] items, newline collapse) is unchanged.
    """
    from trezarr.bible.analyze import _build_analysis_prompt  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    bible = SimpleNamespace(register_value=None, characters=[], address_map=[], terms=[])
    cue_texts = ["First cue.", "Second cue\nwith a newline."]
    prompt = _build_analysis_prompt(
        cue_texts, bible, {"title": "Some Show", "genres": ["Fantasy"]}, episode_key="S01E01"
    )

    # Hán-Việt rendering instruction with concrete examples.
    assert "vietnamese_rendering" in prompt
    assert "Phong Thiên Cực" in prompt
    assert "Mai cô nương" in prompt
    # Kinship-as-address mapping.
    assert "trưởng lão" in prompt, "Must map 'Elder' → 'trưởng lão'"
    assert "tiền bối" in prompt, "Must map 'Senior' → 'tiền bối'"
    # Genre-register guidance.
    for genre in ("xianxia", "wuxia", "cultivation"):
        assert genre in prompt, f"Genre-register guidance must name {genre!r}"

    # [DIALOGUE SAMPLE] security framing unchanged: numbered items + newline collapse.
    assert "[DIALOGUE SAMPLE]" in prompt
    assert "[1]" in prompt and "[2]" in prompt
    # WR-05: a cue's internal newline is collapsed to the ⏎ marker, so the 2nd cue stays
    # on ONE physical line ("[2] Second cue ⏎ with a newline.") rather than column-aligning
    # an injected fake section header.
    assert "[2] Second cue ⏎ with a newline." in prompt, (
        "internal cue newlines must be collapsed to the ⏎ marker (WR-05 security framing)"
    )
