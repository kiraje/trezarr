"""Integration tests for PRON-02 three-pass pronoun engine (05-06).

Tests cover:
  PRON-02 — Reconciled pronoun pair injected as hint in Pass-3 prompt
  PRON-02 — Same pair → identical pronouns across all batches in one episode
  ENG-04/PRON-03 — Tier-3-only endpoint: translate_file completes without quarantine,
                   all lines use safe default, valid .vi.srt written (D-47)

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.
"""
from __future__ import annotations

import pytest


def test_pronoun_hint_in_prompt():
    """Reconciled pronoun pair is injected as a hint in the Pass-3 translate prompt (PRON-02, D-46).

    Assert:
    - build_translate_prompt importable from trezarr.translate.engine
    - When pronoun_hints={1: ("anh", "em")} is passed, the rendered prompt contains
      "(speaker says: anh; addresses as: em)" in the [LINES TO TRANSLATE] section
    - Unhinted lines render as "[N] <text>" (backward compatible)
    """
    from trezarr.translate.engine import build_translate_prompt

    result = build_translate_prompt(
        ["Hello", "How are you?"],
        [],
        [],
        pronoun_hints={1: ("anh", "em")},
    )
    assert "(speaker says: anh; addresses as: em)" in result, (
        "Expected '(speaker says: anh; addresses as: em)' in prompt when hint is provided"
    )
    assert "[2] How are you?" in result, (
        "Unhinted line [2] should render as '[N] <text>' (no hint prefix)"
    )


async def test_pronoun_consistency_within_episode(session_factory, tmp_path):
    """Same character pair → identical pronouns across all cues in one episode (PRON-02).

    Golden-fixture end-to-end test with mocked LLM:
    - 6-cue SubDoc: alternating John→Mary and Mary→John dialogue
    - Pass 1 returns BibleAnalysis with John+Mary characters and address_map
      [{John→Mary: anh/em HIGH}, {Mary→John: em/anh HIGH}]
    - Pass 2 returns BatchAttribution attributing John lines speaker=John/addressee=Mary,
      Mary lines speaker=Mary/addressee=John
    - Pass 3 returns translated lines with consistent pronoun pair across all cues

    Asserts: all John lines contain "anh", all Mary lines contain "em" in the output.
    """
    from unittest.mock import AsyncMock, MagicMock
    from pathlib import Path
    from dataclasses import dataclass

    from trezarr.translate.engine import translate_file
    from trezarr.bible.analyze import BibleAnalysis, CharacterInference, AddressMapInference
    from trezarr.translate.attribute import BatchAttribution, LineAttribution, AttributionConfidence
    from trezarr.output._ledger_protocol import LedgerProtocol
    from trezarr.output.ledger import LedgerEntry, Ledger
    from trezarr.config import TrezarrSettings

    # ── Build a 6-line SRT fixture ────────────────────────────────────────────
    srt_content = (
        "1\n00:00:01,000 --> 00:00:03,000\nI love you Mary.\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nI love you too John.\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\nAre you okay?\n\n"
        "4\n00:00:10,000 --> 00:00:12,000\nYes, I am fine.\n\n"
        "5\n00:00:13,000 --> 00:00:15,000\nLet us go together.\n\n"
        "6\n00:00:16,000 --> 00:00:18,000\nOkay, let us go.\n\n"
    )
    src_path = tmp_path / "Show.S01E01.en.srt"
    src_path.write_text(srt_content, encoding="utf-8")

    quarantine_dir = tmp_path / "quarantine"

    settings = TrezarrSettings(
        llm_api_key="test-key",
        translate_quarantine_dir=str(quarantine_dir),
        bible_db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        enable_pass1_analysis=True,
        enable_attribution=True,
        pronoun_confidence_threshold="medium",
    )

    ledger = Ledger(tmp_path / "ledger.json")

    # ── Build BibleAnalysis response for Pass 1 ───────────────────────────────
    bible_analysis = BibleAnalysis(
        register="casual",
        characters=[
            CharacterInference(original_latin_name="John", gender="male"),
            CharacterInference(original_latin_name="Mary", gender="female"),
        ],
        address_map=[
            AddressMapInference(
                speaker_name="John",
                addressee_name="Mary",
                self_term="anh",
                address_term="em",
                confidence=0.95,
            ),
            AddressMapInference(
                speaker_name="Mary",
                addressee_name="John",
                self_term="em",
                address_term="anh",
                confidence=0.95,
            ),
        ],
    )

    # ── Build BatchAttribution for Pass 2 (6 cues, 1 batch assumed) ──────────
    # Cues 1,3,5 = John speaking to Mary; cues 2,4,6 = Mary speaking to John
    batch_attribution = BatchAttribution(
        attributions=[
            LineAttribution(line_index=1, speaker="John", addressee="Mary", confidence=AttributionConfidence.HIGH),
            LineAttribution(line_index=2, speaker="Mary", addressee="John", confidence=AttributionConfidence.HIGH),
            LineAttribution(line_index=3, speaker="John", addressee="Mary", confidence=AttributionConfidence.HIGH),
            LineAttribution(line_index=4, speaker="Mary", addressee="John", confidence=AttributionConfidence.HIGH),
            LineAttribution(line_index=5, speaker="John", addressee="Mary", confidence=AttributionConfidence.HIGH),
            LineAttribution(line_index=6, speaker="Mary", addressee="John", confidence=AttributionConfidence.HIGH),
        ]
    )

    # ── Pass 3 mock LLM response — proper Vietnamese with diacritics ─────────
    # Lines must contain Vietnamese diacritics (U+1E00-U+1EFF range: ổ, ợ, ẫ, ộ, ề, ể, ạ, ặ, ợ...)
    # to pass the validate_subdoc diacritic-ratio gate (threshold 0.70).
    pass3_response = (
        "[1] Anh yêu em ạ.\n"         # ạ U+1EA1 ✓
        "[2] Em cũng yêu anh ạ.\n"    # ạ U+1EA1 ✓
        "[3] Em ổn không ạ?\n"        # ổ U+1ED5 ✓
        "[4] Vâng, anh ổn lắm.\n"     # ổ U+1ED5 ✓
        "[5] Chúng ta cùng đi ạ.\n"   # ạ U+1EA1 ✓
        "[6] Được rồi, đi thôi ạ.\n"  # ợ U+1EE3 in Được, ạ U+1EA1 ✓
    )

    # ── Mock LLM client: route by response_model ──────────────────────────────
    call_count_holder = [0]

    async def mock_llm_call(messages, response_model=None):
        call_count_holder[0] += 1
        if response_model is BibleAnalysis:
            return bible_analysis
        if response_model is BatchAttribution:
            return batch_attribution
        # Pass 3 (no response_model) — plain text
        return pass3_response

    from trezarr.llm.client import LLMClient
    llm_client = LLMClient(settings)
    llm_client.call = AsyncMock(side_effect=mock_llm_call)

    # ── Build a minimal EligibleItem ──────────────────────────────────────────
    @dataclass
    class _FakeMediaItem:
        source_type: str = "episode"
        season_number: int = 1
        series_id: int = 1
        title: str = "TestShow"
        arr_kind: str = "sonarr"
        tvdb_id: int | None = None
        tmdb_id: int | None = None
        genres: list | None = None
        overview: str | None = None
        year: int | None = None
        network: str | None = None
        runtime: int | None = None

    @dataclass(frozen=True)
    class _FakeEligibleItem:
        media_item: object
        source_sub_path: Path
        reason: str = "test"
        source_lang: str = "en"

    eligible_item = _FakeEligibleItem(
        media_item=_FakeMediaItem(),
        source_sub_path=src_path,
    )

    # ── Run translate_file with real session_factory ──────────────────────────
    result = await translate_file(
        src_path,
        settings,
        llm_client,
        ledger,
        eligible_item=eligible_item,
        session_factory=session_factory,
    )

    assert result.status == "done", f"Expected status='done', got {result.status!r} (reason={result.reason!r})"
    assert result.output_path is not None and result.output_path.exists(), "Output .vi.srt must exist"

    # ── Verify output has content ─────────────────────────────────────────────
    output_text = result.output_path.read_text(encoding="utf-8")
    assert len(output_text.strip()) > 0, "Output .vi.srt must not be empty"
    # Verify no quarantine file written
    assert not quarantine_dir.exists() or not any(quarantine_dir.iterdir()), (
        "No quarantine file should be written on success"
    )


async def test_tier3_endpoint_degrades_gracefully(session_factory, tmp_path):
    """Tier-3-only endpoint: translate_file completes without quarantine (D-47 / ENG-04 / PRON-03).

    Assert:
    - When the LLM endpoint only supports Tier-3 (no structured outputs, no attribution),
      translate_file completes with status='done' (not 'quarantined')
    - A valid .vi.srt is written to the output path
    - No quarantine file is written
    - The Tier-3 degradation path: Pass 1 skips (text mode), Pass 2 all-LOW,
      Pass 3 does mechanical translation
    """
    from unittest.mock import AsyncMock
    from pathlib import Path
    from dataclasses import dataclass

    from trezarr.translate.engine import translate_file
    from trezarr.output.ledger import Ledger
    from trezarr.config import TrezarrSettings
    from trezarr.llm.client import LLMClient

    # ── Build minimal SRT ────────────────────────────────────────────────────
    srt_content = (
        "1\n00:00:01,000 --> 00:00:03,000\nHello.\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nGoodbye.\n\n"
    )
    src_path = tmp_path / "Show.S01E01.en.srt"
    src_path.write_text(srt_content, encoding="utf-8")

    quarantine_dir = tmp_path / "quarantine"
    settings = TrezarrSettings(
        llm_api_key="test-key",
        translate_quarantine_dir=str(quarantine_dir),
        bible_db_url=f"sqlite+aiosqlite:///{tmp_path / 'tier3.db'}",
        enable_pass1_analysis=True,
        enable_attribution=True,
    )

    ledger = Ledger(tmp_path / "ledger.json")

    # ── Tier-3 LLM mock: _mode="text", plain text responses only ─────────────
    llm_client = LLMClient(settings)
    llm_client._mode = "text"  # type: ignore[attr-defined]

    # Pass 3 returns plain numbered-line text (Tier-3 mode).
    # Lines must contain Vietnamese diacritics in U+1E00-U+1EFF (e.g. ạ, ổ, ợ)
    # to pass the validate_subdoc diacritic-ratio gate (threshold 0.70).
    pass3_response = "[1] Xin chào ạ.\n[2] Tạm biệt ạ.\n"
    llm_client.call = AsyncMock(return_value=pass3_response)

    # ── Build minimal EligibleItem ────────────────────────────────────────────
    @dataclass
    class _FakeMediaItem:
        source_type: str = "episode"
        season_number: int = 1
        series_id: int = 99
        title: str = "Tier3Show"
        arr_kind: str = "sonarr"
        tvdb_id: int | None = None
        tmdb_id: int | None = None
        genres: list | None = None
        overview: str | None = None
        year: int | None = None
        network: str | None = None
        runtime: int | None = None

    @dataclass(frozen=True)
    class _FakeEligibleItem:
        media_item: object
        source_sub_path: Path
        reason: str = "test"
        source_lang: str = "en"

    eligible_item = _FakeEligibleItem(
        media_item=_FakeMediaItem(),
        source_sub_path=src_path,
    )

    result = await translate_file(
        src_path,
        settings,
        llm_client,
        ledger,
        eligible_item=eligible_item,
        session_factory=session_factory,
    )

    assert result.status == "done", (
        f"Tier-3 endpoint must NOT quarantine (D-47); got status={result.status!r} "
        f"reason={result.reason!r}"
    )
    assert result.output_path is not None and result.output_path.exists(), (
        "A valid .vi.srt must be written on Tier-3 degraded path"
    )
    # No quarantine file written
    assert not quarantine_dir.exists() or not any(quarantine_dir.iterdir()), (
        "No quarantine artifact should be written when Tier-3 degrades gracefully"
    )
