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

    Golden-fixture end-to-end test with mocked LLM that CAPTURES Pass-3 prompts and
    ECHOES injected hints in its output — so a broken hint/reconcile/bridge pipeline
    causes the output-content assertions to FAIL (CR-02 hardening):

    - 6-cue SubDoc: alternating John→Mary and Mary→John dialogue
    - Pass 1 returns BibleAnalysis with John+Mary characters and address_map
      [{John→Mary: anh/em HIGH}, {Mary→John: em/anh HIGH}]
    - Pass 2 returns BatchAttribution attributing John lines speaker=John/addressee=Mary,
      Mary lines speaker=Mary/addressee=John
    - Pass 3 mock: captures the prompt it receives, then echoes the hint terms back in
      the numbered-line response; if no hints reach it the echo can't produce "anh"/"em"

    Asserts:
    - "(speaker says: anh; addresses as: em)" hint appears in at least one Pass-3 prompt
    - "(speaker says: em; addresses as: anh)" reciprocal hint appears in a Pass-3 prompt
    - Output contains "anh" (the self_term John uses) somewhere in the translated text
    - Output contains "em" (the address_term John uses / Mary's self_term) in the text
    - status == "done", output file exists, no quarantine written
    """
    import re as _re
    from unittest.mock import AsyncMock
    from pathlib import Path
    from dataclasses import dataclass

    from trezarr.translate.engine import translate_file
    from trezarr.bible.analyze import BibleAnalysis, CharacterInference, AddressMapInference
    from trezarr.translate.attribute import BatchAttribution, LineAttribution, AttributionConfidence
    from trezarr.output.ledger import Ledger
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
        enable_self_review=False,  # Phase-5 test: disable Phase-6 self-review (mock does not handle review prompts)
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

    # ── Mock LLM client: capture prompts; echo hints back in Pass-3 output ────
    # The mock CAPTURES every Pass-3 prompt it receives.
    # For Pass 3 (no response_model), it reads the hint text from the prompt and
    # ECHOES it into the numbered output — so if hints never reach Pass 3, the
    # output lines won't contain "anh"/"em" and the assertions below WILL FAIL.
    # This is the guard: a broken hint/reconcile/bridge pipeline breaks this test.
    captured_prompts: list[str] = []

    # Regex to extract hint terms from "[N] (speaker says: X; addresses as: Y) ..." lines
    _HINT_RE = _re.compile(r'\[\d+\]\s*\(speaker says:\s*(\w+);\s*addresses as:\s*(\w+)\)')

    def _build_pass3_response(prompt: str) -> str:
        """Build a numbered-line response that echoes injected hint terms.

        For each line [N] in [LINES TO TRANSLATE]:
          - If the line has a hint "(speaker says: X; addresses as: Y)", echo
            "[N] <X> ơi, <Y> ạ." — so "anh"/"em" appear only when hints are present.
          - Without a hint, return a generic Vietnamese phrase that has diacritics but
            does NOT contain "anh" or "em" (proves the terms come from hints, not defaults).
        """
        lines_section = prompt.split("[LINES TO TRANSLATE]", 1)[-1]
        result_lines: list[str] = []
        for raw in lines_section.splitlines():
            m_hint = _HINT_RE.match(raw.strip())
            m_num = _re.match(r'\[(\d+)\]', raw.strip())
            if m_hint:
                n = _re.match(r'\[(\d+)\]', raw.strip()).group(1)
                self_t = m_hint.group(1)
                addr_t = m_hint.group(2)
                # Output echoes the hint terms — Vietnamese diacritics satisfy the gate
                result_lines.append(f"[{n}] {self_t} ơi, {addr_t} ạ.")
            elif m_num:
                n = m_num.group(1)
                # No hint: neutral output WITHOUT "anh"/"em"
                result_lines.append(f"[{n}] Vâng, được rồi ổn.")
        return "\n".join(result_lines)

    async def mock_llm_call(messages, response_model=None, model=None, **kwargs):  # D-113 / FIX-B: accept model + thinking kwargs
        prompt_text = messages[0]["content"] if messages else ""
        if response_model is BibleAnalysis:
            return bible_analysis
        if response_model is BatchAttribution:
            return batch_attribution
        # Pass 3 (no response_model) — capture prompt and echo hints
        captured_prompts.append(prompt_text)
        return _build_pass3_response(prompt_text)

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

    # ── Verify pronoun hints were injected into Pass-3 prompts ───────────────
    # These assertions FAIL if hint injection, reconciliation, or the
    # resolved_map→hint bridge (engine.py per_batch_hints) is broken.
    assert len(captured_prompts) > 0, "Mock LLM must have received at least one Pass-3 prompt"

    john_mary_hint = "(speaker says: anh; addresses as: em)"
    mary_john_hint = "(speaker says: em; addresses as: anh)"

    assert any(john_mary_hint in p for p in captured_prompts), (
        f"John→Mary hint {john_mary_hint!r} must appear in at least one Pass-3 prompt. "
        "If this fails, pronoun hints are not reaching Pass 3 (broken reconcile/bridge)."
    )
    assert any(mary_john_hint in p for p in captured_prompts), (
        f"Mary→John hint {mary_john_hint!r} must appear in at least one Pass-3 prompt. "
        "If this fails, reciprocal hint injection is broken."
    )

    # ── Verify output pronouns come from hints (not hardcoded) ───────────────
    # The mock echoes hint terms: "anh" appears ONLY in hint-carrying lines.
    # If hints don't reach Pass 3, _build_pass3_response returns neutral lines
    # without "anh"/"em", and the assertions below fail.
    output_text = result.output_path.read_text(encoding="utf-8")
    assert len(output_text.strip()) > 0, "Output .vi.srt must not be empty"
    assert "anh" in output_text, (
        "Output must contain 'anh' — echoed from John→Mary hint. "
        "Absence means hints did not reach Pass-3 mock."
    )
    assert "em" in output_text, (
        "Output must contain 'em' — echoed from Mary→John hint. "
        "Absence means hints did not reach Pass-3 mock."
    )

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


# ── H1 / H2 / B4 — register, glossary Hán-Việt, and mixed-gender plural RULES ─


def test_build_translate_prompt_injects_register_block_and_rule():
    """H1: register='xianxia' adds a [REGISTER] block + a classical Sino-Vietnamese RULE.

    With register='xianxia' the prompt must (a) contain a [REGISTER block whose body
    includes 'xianxia', and (b) contain a RULE naming Hán-Việt + a classical pronoun
    example ('tại hạ') and forbidding flattening into modern speech ('do NOT flatten ...
    the dialogue'). Without register there is NO [REGISTER block (back-compat). Both calls
    still emit RULES 1-3 unchanged.
    """
    from trezarr.translate.engine import build_translate_prompt  # noqa: PLC0415

    with_reg = build_translate_prompt(["Foo"], [], [], register="xianxia")
    assert "[REGISTER" in with_reg, "Expected a [REGISTER block when register is set"
    assert "xianxia" in with_reg, "[REGISTER block body must include the register value"
    assert "Hán-Việt" in with_reg, "Register RULE must name Hán-Việt"
    assert "tại hạ" in with_reg, "Register RULE must give a classical pronoun example ('tại hạ')"
    assert "do NOT flatten" in with_reg, "Register RULE must forbid flattening into modern speech"
    # RULES 1-3 unchanged.
    assert "1. Output ONLY the numbered lines" in with_reg
    assert "2. Keep <<T0>>" in with_reg
    assert "3. Do NOT translate or output the [context] lines." in with_reg

    no_reg = build_translate_prompt(["Foo"], [], [])
    assert "[REGISTER" not in no_reg, "No [REGISTER block when register omitted (back-compat)"
    assert "1. Output ONLY the numbered lines" in no_reg
    assert "2. Keep <<T0>>" in no_reg
    assert "3. Do NOT translate or output the [context] lines." in no_reg


def test_build_translate_prompt_glossary_rule_requires_hanviet_and_forbids_pinyin():
    """H2: the glossary RULE requires Hán-Việt for romanized names and forbids leaving pinyin.

    With glossary=['Han -> Hàn'] the prompt must (a) require Hán-Việt readings with a
    concrete example ('Phong Thiên Cực') and (b) forbid leaving pinyin (the substring
    'pinyin' appears) alongside the existing 'Japanese romaji' clause. Rule numbering stays
    contiguous: '4.' appears exactly once at the start of a rule line.
    """
    from trezarr.translate.engine import build_translate_prompt  # noqa: PLC0415

    prompt = build_translate_prompt(["Foo"], [], [], glossary=["Han -> Hàn"])
    assert "Hán-Việt" in prompt, "Glossary RULE must require Hán-Việt readings"
    assert "Phong Thiên Cực" in prompt, "Glossary RULE must give the concrete Hán-Việt example"
    assert "pinyin" in prompt, "Glossary RULE must reference pinyin (forbidding leaving it)"
    assert "leave pinyin" in prompt, "Glossary RULE must forbid leaving pinyin"
    assert "Japanese romaji" in prompt, "Existing 'Japanese romaji' clause must remain"

    # '4.' must appear exactly once at the start of a rule line (contiguous numbering).
    rule_4_starts = [ln for ln in prompt.splitlines() if ln.lstrip().startswith("4.")]
    assert len(rule_4_starts) == 1, (
        f"Expected exactly one rule line starting with '4.', got {rule_4_starts!r}"
    )


def test_build_translate_prompt_mixed_gender_plural_rule_present():
    """B4: a mixed-gender plural RULE is always present (even with no glossary/register/hints).

    The RULE must name the non-gendered plurals 'chư vị', 'các vị', 'các bạn', 'mọi người'
    and name the forbidden gendered plurals 'các cô' / 'các cậu'.
    """
    from trezarr.translate.engine import build_translate_prompt  # noqa: PLC0415

    prompt = build_translate_prompt(["You all"], [], [])
    for form in ("chư vị", "các vị", "các bạn", "mọi người"):
        assert form in prompt, f"Mixed-gender plural RULE must name the non-gendered form {form!r}"
    for forbidden in ("các cô", "các cậu"):
        assert forbidden in prompt, (
            f"Mixed-gender plural RULE must name the forbidden gendered plural {forbidden!r}"
        )
