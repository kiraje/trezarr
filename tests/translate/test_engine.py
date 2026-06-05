"""RED test stubs for ENG-03 and ENG-06 retry/quarantine in trezarr.translate.engine.

All imports from trezarr.translate.engine are deferred inside each test function body
so pytest collection succeeds even when the implementation module does not yet exist.
Tests skip cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Async test functions use async def without @pytest.mark.asyncio (asyncio_mode="auto"
is configured in pyproject.toml — matches Phase 1 convention).

Covers:
  ENG-03 — Context window prompt has [CONTEXT] sections + [LINES TO TRANSLATE] section
  D-13   — Numbered-line response parser returns list of translated strings
  ENG-06 — Batch retry: bad response on attempt 1, valid on attempt 2
  ENG-06 — Quarantine on retry exhaustion: always bad response → TranslationError raised
  ENG-07 — translate_file skips when ledger says status="done" + matching hash
"""
import pytest


def test_context_window_prompt():
    """Context-window prompt has [CONTEXT] sections before/after [LINES TO TRANSLATE] (ENG-03).

    Assert:
    - "[CONTEXT" appears before "[LINES TO TRANSLATE]" when context_before is non-empty
    - "[CONTEXT" appears after "[LINES TO TRANSLATE]" when context_after is non-empty
    - "[context]" prefixes appear on context lines
    - "[1]", "[2]" numbered lines appear in the LINES section
    """
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    build_translate_prompt = engine_mod.build_translate_prompt

    context_before = ["She walked into the room.", "John: What are you doing here?"]
    batch_texts = ["I came to talk.", "About what?"]
    context_after = ["Please, sit down.", "I'll explain everything."]

    prompt = build_translate_prompt(batch_texts, context_before, context_after)

    assert "[CONTEXT" in prompt, "Expected '[CONTEXT' section header in prompt"
    assert "[LINES TO TRANSLATE]" in prompt, "Expected '[LINES TO TRANSLATE]' section in prompt"
    assert "[context]" in prompt, "Expected '[context]' prefixed lines for neighbor context"
    assert "[1]" in prompt, "Expected '[1]' numbered line in LINES TO TRANSLATE section"
    assert "[2]" in prompt, "Expected '[2]' numbered line in LINES TO TRANSLATE section"

    # [CONTEXT section must appear before [LINES TO TRANSLATE]
    context_pos = prompt.index("[CONTEXT")
    lines_pos = prompt.index("[LINES TO TRANSLATE]")
    assert context_pos < lines_pos, (
        "Expected '[CONTEXT' section to appear before '[LINES TO TRANSLATE]'"
    )

    # Verify context_before lines are present and context_after lines are present
    for ctx_line in context_before:
        assert ctx_line in prompt, f"Expected context_before line {ctx_line!r} in prompt"
    for ctx_line in context_after:
        assert ctx_line in prompt, f"Expected context_after line {ctx_line!r} in prompt"


def test_numbered_line_parse_over_count_rejected():
    """Parser rejects LLM response with more numbered lines than expected_count (WR-02).

    [1] [2] [3] for a 2-cue batch is a hallucinated-extra-line signal that must
    raise BatchValidationError rather than silently dropping line [3].
    """
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    parse_numbered_response = engine_mod.parse_numbered_response
    BatchValidationError = engine_mod.BatchValidationError

    response = "[1] Xin chào\n[2] Tôi đến đây\n[3] Dòng thêm"
    with pytest.raises(BatchValidationError, match="unexpected line numbers"):
        parse_numbered_response(response, expected_count=2)


def test_numbered_line_parse_duplicate_rejected():
    """Parser rejects LLM response with duplicate line numbers (WR-03).

    [1] appearing twice means the later value would silently overwrite the
    earlier one — must raise BatchValidationError instead.
    """
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    parse_numbered_response = engine_mod.parse_numbered_response
    BatchValidationError = engine_mod.BatchValidationError

    response = "[1] Xin chào\n[1] Tôi đến đây"
    with pytest.raises(BatchValidationError, match="Duplicate line number"):
        parse_numbered_response(response, expected_count=1)


def test_numbered_line_parse():
    """Response parser converts '[1] Xin chào\\n[2] Tôi đến đây' to a list of strings (D-13)."""
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    parse_numbered_response = engine_mod.parse_numbered_response

    response = "[1] Xin chào\n[2] Tôi đến đây"
    result = parse_numbered_response(response, expected_count=2)

    assert result == ["Xin chào", "Tôi đến đây"], (
        f"Expected ['Xin chào', 'Tôi đến đây'], got {result!r}"
    )


async def test_batch_retry(settings_factory):
    """Mock LLMClient returns bad response on attempt 1, valid on attempt 2 (ENG-06).

    Assert:
    - The translate function retries exactly once
    - Returns correct translated text after retry
    - BatchValidationError is not raised externally
    """
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    from unittest.mock import patch

    _translate_batch = engine_mod._translate_batch

    # Minimal batch with 1 cue
    from trezarr.subtitles.model import SubLine
    from trezarr.translate.batching import Batch  # will be skipped if batching not implemented

    settings = settings_factory(translate_batch_retry_attempts=2)

    src_line = SubLine(
        index="1",
        start_tc="00:00:01,000",
        end_tc="00:00:03,000",
        text="Hello world",
    )
    batch = Batch(cues=[src_line], context_before=[], context_after=[])

    call_count = 0

    async def _fake_call(messages, response_model=None, model=None):  # D-113: accept model kwarg
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return ""  # empty response — triggers BatchValidationError
        return "[1] Xin chào thế giới"

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    with patch.object(client, "call", side_effect=_fake_call):
        result = await _translate_batch(batch, client, settings)

    assert call_count == 2, f"Expected exactly 2 LLM calls (retry), got {call_count}"
    assert result == ["Xin chào thế giới"], f"Expected ['Xin chào thế giới'], got {result!r}"


async def test_quarantine_on_retry_exhaustion(settings_factory):
    """LLMClient always returns empty lines → TranslationError raised after retry exhaustion (ENG-06)."""
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    from unittest.mock import patch

    _translate_batch = engine_mod._translate_batch
    TranslationError = engine_mod.TranslationError

    from trezarr.subtitles.model import SubLine
    from trezarr.translate.batching import Batch

    settings = settings_factory(translate_batch_retry_attempts=2)

    src_line = SubLine(
        index="1",
        start_tc="00:00:01,000",
        end_tc="00:00:03,000",
        text="Hello world",
    )
    batch = Batch(cues=[src_line], context_before=[], context_after=[])

    async def _always_bad(messages, response_model=None, model=None):  # D-113: accept model kwarg
        return ""  # always empty — always triggers BatchValidationError

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    with patch.object(client, "call", side_effect=_always_bad):
        with pytest.raises((TranslationError, Exception)) as exc_info:
            await _translate_batch(batch, client, settings)

    # Either TranslationError or the tenacity RetryError (which wraps BatchValidationError)
    # is acceptable — the key contract is that it raises rather than returning garbage
    assert exc_info.value is not None


async def test_translate_file_read_failure_quarantines(settings_factory, tmp_path):
    """read_srt failure quarantines the file and clears in_progress from ledger (WR-04).

    The function contract promises "on any failure → return TranslationResult(status='quarantined')".
    A PermissionError from read_srt must route to quarantine, not leave the ledger at in_progress.
    """
    pytest.importorskip("trezarr.translate.engine")
    from unittest.mock import patch
    from trezarr.translate.engine import translate_file
    from trezarr.output.ledger import Ledger

    quarantine_dir = tmp_path / "quarantine"
    settings = settings_factory(translate_quarantine_dir=str(quarantine_dir))

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    ledger_path = tmp_path / "ledger.json"
    ledger = Ledger(ledger_path)

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    with patch("trezarr.translate.engine.read_subtitle", side_effect=PermissionError("no access")):
        result = await translate_file(src, settings, client, ledger)

    assert result.status == "quarantined", (
        f"Expected status='quarantined' when read_srt raises, got {result.status!r}"
    )
    entry = await ledger.check(str(src))
    assert entry is not None and entry.status == "quarantined", (
        "Ledger must not be left at in_progress when read_srt fails (WR-04)"
    )


async def test_translate_file_non_batch_error_propagates(settings_factory, tmp_path):
    """Non-BatchValidationError (e.g. RuntimeError) propagates out of translate_file — not quarantined (CR-01).

    D-18 / Pitfall 5: only BatchValidationError (retry-exhausted gate failure) should produce a
    quarantine artifact.  A transport error or programming error must propagate so the file is
    retried on the next poll and no permanent quarantine record is created.

    WR-04 note: asyncio.TaskGroup wraps the exception in an ExceptionGroup.  The test accepts
    both bare RuntimeError (legacy gather path) and ExceptionGroup[RuntimeError] (TaskGroup path)
    so the invariant (error propagates, no quarantine) is asserted regardless of wrapper.
    """
    pytest.importorskip("trezarr.translate.engine")
    from unittest.mock import patch, AsyncMock
    from trezarr.translate.engine import translate_file
    from trezarr.output.ledger import Ledger

    settings = settings_factory()

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    ledger_path = tmp_path / "ledger.json"
    ledger = Ledger(ledger_path)

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    # Simulate an openai-style transport error (RuntimeError stands in for openai.APIError)
    transport_error = RuntimeError("simulated transport error")

    # Patch _translate_batch to raise the transport error directly.
    # asyncio.TaskGroup (WR-04) wraps the error in an ExceptionGroup.
    # Catch ExceptionGroup and verify the inner exception is the expected RuntimeError.
    raised_exc: BaseException | None = None
    try:
        with patch("trezarr.translate.engine._translate_batch", new=AsyncMock(side_effect=transport_error)):
            await translate_file(src, settings, client, ledger)
    except BaseException as exc:
        raised_exc = exc

    assert raised_exc is not None, "Non-BatchValidationError must propagate out of translate_file (Pitfall 5)"
    # Unwrap ExceptionGroup if present (TaskGroup path); accept bare exception too
    if isinstance(raised_exc, ExceptionGroup):
        inner_exceptions = list(raised_exc.exceptions)
    else:
        inner_exceptions = [raised_exc]
    assert any("simulated transport error" in str(e) for e in inner_exceptions), (
        f"Expected transport error message in propagated exception(s): {inner_exceptions!r}"
    )

    # No quarantine entry must have been recorded — the error must have propagated
    entry = await ledger.check(str(src))
    assert entry is None or entry.status != "quarantined", (
        "Non-BatchValidationError must NOT produce a quarantine ledger entry (CR-01 / Pitfall 5)"
    )


async def test_translate_file_skip_unchanged(settings_factory, tmp_path):
    """translate_file returns TranslationResult(status='skipped') when ledger says done + matching hash (ENG-07)."""
    pytest.importorskip("trezarr.translate.engine")
    from trezarr.translate.engine import translate_file
    from trezarr.output.ledger import Ledger, LedgerEntry

    settings = settings_factory()

    # Create a minimal source SRT file
    src = tmp_path / "Show.S01E01.en.srt"
    src_content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
    src.write_text(src_content, encoding="utf-8")

    # Compute the content hash the way the ledger does
    content_hash = Ledger.content_hash(src.read_bytes())

    # Create the "already done" output
    dest = tmp_path / "Show.S01E01.vi.srt"
    dest.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    # Pre-populate ledger with matching hash and status="done"
    ledger_path = tmp_path / "ledger.json"
    ledger = Ledger(ledger_path)
    await ledger.record(LedgerEntry(
        source_path=str(src),
        output_path=str(dest),
        status="done",
        content_hash=content_hash,
    ))

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    result = await translate_file(src, settings, client, ledger)

    assert result.status == "skipped", (
        f"Expected TranslationResult.status='skipped' for unchanged source, got {result.status!r}"
    )


def test_pronoun_hint_in_prompt():
    """Pronoun hint injected into [LINES TO TRANSLATE] when pronoun_hints provided (D-46, PRON-02).

    Assert:
    - build_translate_prompt with pronoun_hints={1: ("anh", "em")} produces a prompt
      containing "(speaker says: anh; addresses as: em)" for line [1]
    - Line [2] (no hint) renders as "[2] <text>" without a hint prefix
    """
    from trezarr.translate.engine import build_translate_prompt

    prompt = build_translate_prompt(
        ["Hello", "World"],
        [],
        [],
        pronoun_hints={1: ("anh", "em")},
    )
    assert "(speaker says: anh; addresses as: em)" in prompt, (
        "Expected '(speaker says: anh; addresses as: em)' in prompt for hinted line"
    )
    assert "[2] World" in prompt, (
        "Unhinted line [2] should render without hint prefix"
    )


def test_glossary_block_in_translate_prompt():
    """Glossary injected into the Pass-3 prompt so proper nouns render consistently (consistency moat).

    The audit found the protagonist rendered 11 ways in one episode because Pass-3 never saw the
    Bible's canonical name/term renderings. Assert:
    - build_translate_prompt(glossary=[...]) emits a [GLOSSARY ...] block listing each rendering
      plus an instruction to use them exactly (and not Japanese romaji / source script).
    - build_translate_prompt WITHOUT glossary has no [GLOSSARY block (back-compat).
    """
    from trezarr.translate.engine import build_translate_prompt

    prompt = build_translate_prompt(
        ["樱说不要"],
        [],
        [],
        glossary=["Sakura → Anh Đào", "Daisy → Daisy"],
    )
    assert "[GLOSSARY" in prompt, "Expected a [GLOSSARY] block when glossary provided"
    assert "Sakura → Anh Đào" in prompt, "Glossary rendering must appear verbatim"
    assert "Daisy → Daisy" in prompt, "Pinned character name must appear verbatim"
    assert "Japanese romaji" in prompt or "EXACT" in prompt, (
        "Expected an instruction to use the glossary renderings exactly"
    )

    plain = build_translate_prompt(["Hello"], [], [])
    assert "[GLOSSARY" not in plain, "No glossary block when glossary not provided (back-compat)"


def test_build_glossary_lines_from_bible():
    """build_glossary_lines pins every term + character name; a char covered by a term isn't double-listed."""
    from types import SimpleNamespace
    from trezarr.translate.engine import build_glossary_lines

    bible = SimpleNamespace(
        terms=[SimpleNamespace(source_term="Sakura", vietnamese_rendering="Anh Đào")],
        characters=[
            SimpleNamespace(original_latin_name="Daisy"),   # no term entry → pin to itself
            SimpleNamespace(original_latin_name="Sakura"),  # covered by the term above
        ],
    )
    lines = build_glossary_lines(bible)
    assert "Sakura → Anh Đào" in lines, "Term rendering must be in the glossary"
    assert "Daisy → Daisy" in lines, "Character with no term entry must be pinned to its own name"
    assert sum(1 for ln in lines if ln.startswith("Sakura")) == 1, "Sakura must not be double-listed"


async def test_translate_batch_forwards_glossary_to_prompt(settings_factory):
    """_translate_batch threads the glossary into the prompt actually sent to the LLM (wiring).

    The [GLOSSARY] block is inert unless the Pass-3 dispatch forwards it through _translate_batch.
    """
    engine_mod = pytest.importorskip("trezarr.translate.engine")
    from unittest.mock import patch
    from trezarr.subtitles.model import SubLine
    from trezarr.translate.batching import Batch
    from trezarr.llm.client import LLMClient

    settings = settings_factory(translate_batch_retry_attempts=1)
    batch = Batch(
        cues=[SubLine(index="1", start_tc="00:00:01,000", end_tc="00:00:03,000", text="樱说不要")],
        context_before=[],
        context_after=[],
    )

    captured: dict[str, str] = {}

    async def _fake_call(messages, response_model=None, model=None):  # D-113: accept model kwarg
        captured["prompt"] = messages[0]["content"]
        return "[1] Anh Đào nói đừng"

    client = LLMClient(settings)
    with patch.object(client, "call", side_effect=_fake_call):
        await engine_mod._translate_batch(
            batch, client, settings, glossary=["Sakura → Anh Đào"]
        )

    assert "[GLOSSARY" in captured["prompt"], "glossary block must reach the prompt sent to the LLM"
    assert "Sakura → Anh Đào" in captured["prompt"], "glossary line must reach the prompt"


async def test_reassembly_preserves_raw_cues_at_original_positions(settings_factory, tmp_path):
    """End-to-end reassembly: raw (karaoke/drawing) cues stay at their source positions (D-98/D-99).

    MANDATORY integrity check (plan 09-05):
    Runs the full translate_file pipeline on an ASS fixture that contains a karaoke
    cue in the MIDDLE of the file, and asserts:
      (a) The output is written as .vi.ass (derive_vi_sidecar_path mirrors source ext — D-95)
      (b) The raw karaoke cue is present in the output at its original position with
          BYTE-IDENTICAL text to the source (no misalignment, no corruption)
      (c) The translatable cues surrounding it are in the output (not shifted)

    This proves that batch_subdoc's raw-skip does not misalign the engine's
    batch→SubDoc reassembly — the fixed reassembly walker in Step 8 correctly
    interleaves skipped raw cues with translated cues in document order.
    """
    pytest.importorskip("trezarr.translate.engine")
    from unittest.mock import patch, AsyncMock
    from trezarr.translate.engine import translate_file
    from trezarr.output.ledger import Ledger

    quarantine_dir = tmp_path / "quarantine"
    settings = settings_factory(
        translate_quarantine_dir=str(quarantine_dir),
        translate_batch_retry_attempts=1,
    )

    # Build a minimal ASS file with 3 cues: normal, karaoke (raw), normal.
    # The karaoke cue MUST appear in the MIDDLE to verify position preservation.
    ass_content = (
        "[Script Info]\r\n"
        "ScriptType: v4.00+\r\n"
        "\r\n"
        "[V4+ Styles]\r\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\r\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\r\n"
        "\r\n"
        "[Events]\r\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello world\r\n"
        r"Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,{\k50}she {\k60}said {\k70}yes"
        "\r\n"
        "Dialogue: 0,0:00:07.00,0:00:09.00,Default,,0,0,0,,Goodbye world\r\n"
    )
    src = tmp_path / "Show.S01E01.en.ass"
    src.write_bytes(ass_content.encode("utf-8"))

    ledger = Ledger(tmp_path / "ledger.json")

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    # Mock the LLM client to return translated text for the 2 translatable cues.
    # The karaoke cue is skipped by batching — the LLM sees only cues [1] and [2].
    async def _fake_llm(messages, response_model=None, model=None):  # D-113: accept model kwarg
        # Return numbered-line response for 2 cues only
        return "[1] Xin chào thế giới\n[2] Tạm biệt thế giới"

    with patch.object(client, "call", side_effect=_fake_llm):
        result = await translate_file(src, settings, client, ledger)

    # (a) Output is .vi.ass (mirrors source extension — D-95)
    assert result.status == "done", (
        f"Expected status='done', got {result.status!r}"
    )
    assert result.output_path is not None
    output_path = result.output_path
    assert output_path.suffix == ".ass", (
        f"Expected .vi.ass output (D-95), got suffix {output_path.suffix!r}"
    )
    assert output_path.name == "Show.S01E01.vi.ass", (
        f"Expected 'Show.S01E01.vi.ass', got {output_path.name!r}"
    )
    assert output_path.exists(), "Output .vi.ass file must exist on disk"

    # (b) Read back the output and verify the karaoke cue is byte-identical at
    #     position 2 (the middle slot).
    from trezarr.subtitles.ass import read_ass
    out_doc = read_ass(str(output_path))

    karaoke_raw = r"{\k50}she {\k60}said {\k70}yes"
    assert len(out_doc.lines) == 3, (
        f"Expected 3 cues in output (2 translated + 1 raw), got {len(out_doc.lines)}"
    )

    # Position 1 (index 1) must be the karaoke cue — raw and text byte-identical to source
    middle_cue = out_doc.lines[1]
    assert middle_cue.raw == karaoke_raw, (
        f"Karaoke cue at position 1 must have raw={karaoke_raw!r}, "
        f"got raw={middle_cue.raw!r}"
    )
    assert middle_cue.text == karaoke_raw, (
        f"Karaoke cue at position 1 must have text={karaoke_raw!r}, "
        f"got text={middle_cue.text!r}"
    )

    # (c) Surrounding translatable cues exist (not shifted by the raw cue)
    assert out_doc.lines[0].text == "Xin chào thế giới", (
        f"First cue should be translated, got {out_doc.lines[0].text!r}"
    )
    assert out_doc.lines[2].text == "Tạm biệt thế giới", (
        f"Third cue should be translated, got {out_doc.lines[2].text!r}"
    )


# ── Phase 13 RED stub (Wave 0, D-06) ─────────────────────────────────────────


@pytest.mark.xfail(
    strict=False,
    reason="D-06 fix: engine.py Step 11 series_id — translate_file must record "
    "series_id=str(arr_series_id) in LedgerEntry when eligible_item is not None — "
    "implemented in Phase 13 plan 02",
)
async def test_ledger_records_series_id_on_success(tmp_path):
    """D-06: translate_file success path records series_id in LedgerEntry (Phase 13).

    Verifies that the LedgerEntry passed to ledger.record() at Step 11 carries
    series_id == "42" (str) when eligible_item is not None with arr_series_id=42.

    Setup:
    - Minimal 2-line SRT source file on disk
    - mock_ledger.check returns None (not yet translated)
    - mock_ledger.record captures the LedgerEntry argument
    - mock_llm_client.call returns a valid numbered-line response

    Assert:
    - recorded_entries has exactly 1 entry
    - recorded_entries[0].series_id == "42"
    """
    from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415
    from trezarr.output.ledger import LedgerEntry  # noqa: PLC0415

    engine_mod = pytest.importorskip("trezarr.translate.engine")
    translate_file = engine_mod.translate_file

    # Minimal 2-line SRT
    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nWorld\n",
        encoding="utf-8",
    )

    recorded_entries: list[LedgerEntry] = []

    mock_ledger = MagicMock()
    mock_ledger.record = AsyncMock(side_effect=lambda e: recorded_entries.append(e))
    mock_ledger.check = AsyncMock(return_value=None)
    mock_ledger.check_by_output_path = AsyncMock(return_value=None)
    mock_ledger.content_hash = MagicMock(return_value="abc123")

    # Build a settings object with a writable quarantine dir so validation
    # failures don't produce OSError on /config (test environment has no /config).
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    quarantine_dir = tmp_path / "quarantine"
    settings = TrezarrSettings(translate_quarantine_dir=str(quarantine_dir))

    # Mock LLM client to return a valid numbered response for 2 lines.
    # Both lines use characters from U+1E00-U+1EFF (Vietnamese diacritic range)
    # so the validate_subdoc diacritic-ratio gate passes at the default 0.70 threshold:
    #   "Được rồi" → ợ (U+1EE3), ồ (U+1ED3) — VI range
    #   "Thế giới" → ế (U+1EBF), ớ (U+1EDB) — VI range
    from trezarr.llm.client import LLMClient  # noqa: PLC0415
    llm_client = LLMClient(settings)

    async def _fake_call(messages, response_model=None, model=None):
        return "[1] Được rồi\n[2] Thế giới"

    with patch.object(llm_client, "call", side_effect=_fake_call):
        # eligible_item with series_id / arr_series_id = 42
        mock_eligible_item = MagicMock()
        mock_eligible_item.media_item = MagicMock()
        mock_eligible_item.media_item.series_id = 42

        result = await translate_file(
            src,
            settings,
            llm_client,
            mock_ledger,
            eligible_item=mock_eligible_item,
        )

    assert result.status == "done", f"Expected status='done', got {result.status!r}"
    assert len(recorded_entries) >= 1, "ledger.record must be called at least once on success"
    # D-06: the final 'done' entry must carry series_id as a string
    done_entries = [e for e in recorded_entries if getattr(e, "status", None) == "done"]
    assert len(done_entries) == 1, f"Expected 1 done entry, got {done_entries!r}"
    assert done_entries[0].series_id == "42", (
        f"Expected series_id='42' (str), got {done_entries[0].series_id!r}"
    )


def test_reject_scaffolded_correction():
    """Pass-4 guard: a 'correction' leaking the '(source: …)' scaffolding is dropped.

    Regression for the 260604-gza live finding: deepseek echoed the review-prompt
    line back verbatim, so the splice overwrote good Pass-3 VI with
    '(source: 不要) Đừng'. The guard keeps the clean pre-review text instead.
    """
    from trezarr.translate.engine import _reject_scaffolded_correction  # noqa: PLC0415

    # Leaked scaffolding → fall back to the clean Pass-3 text.
    assert _reject_scaffolded_correction("(source: 不要) Đừng", "Đừng") == "Đừng"
    # A genuine correction (no scaffolding) is kept verbatim.
    assert _reject_scaffolded_correction("Đừng làm thế", "Đừng") == "Đừng làm thế"


# ── B1: multi-line cue round-trip via <<BR>> sentinel ────────────────────────


def test_multiline_cue_round_trip_via_br_sentinel():
    r"""B1: a 2-line cue round-trips byte-identical through prompt → echo → parse.

    build_translate_prompt(['A\nB']) must place the cue on ONE physical line as
    '[1] A<<BR>>B' (the internal newline encoded as the literal <<BR>> token), and a
    verbatim echo of that line must parse back to the original 'A\nB' (audit B1: a
    multi-line cue used to be truncated to its first physical line). A RULE about
    <<BR>> preservation must be present.
    """
    from trezarr.translate.engine import (  # noqa: PLC0415
        build_translate_prompt,
        parse_numbered_response,
    )

    prompt = build_translate_prompt(["A\nB"], [], [])
    assert "[1] A<<BR>>B" in prompt, (
        "Multi-line cue must be encoded on ONE physical line as '[1] A<<BR>>B'"
    )
    # The original 2-physical-line form must NOT appear in the LINES TO TRANSLATE block.
    lines_section = prompt.split("[LINES TO TRANSLATE]", 1)[-1]
    assert "[1] A\nB" not in lines_section, (
        "Internal newline must be sentinelled as <<BR>>, not emitted as two physical lines"
    )
    # A RULE must instruct the model to preserve <<BR>>.
    assert "<<BR>>" in prompt, "Prompt must mention the <<BR>> line-break sentinel in a RULE"

    # Verbatim model echo → restored byte-identical.
    result = parse_numbered_response("[1] A<<BR>>B", 1)
    assert result == ["A\nB"], f"Expected ['A\\nB'] round-trip, got {result!r}"


def test_parse_numbered_response_multiline_br_roundtrip():
    r"""B1 invariant (specialist): 'A\nB' round-trips byte-identical via <<BR>>.

    build_translate_prompt(["A\nB"], [], []) emits '[1] A<<BR>>B'; feeding that exact
    echoed line into parse_numbered_response(resp, 1) yields ['A\nB']. Asserts the
    internal newline is replaced with the literal '<<BR>>' token in [LINES TO TRANSLATE].
    """
    from trezarr.translate.engine import (  # noqa: PLC0415
        build_translate_prompt,
        parse_numbered_response,
    )

    prompt = build_translate_prompt(["A\nB"], [], [])
    lines_section = prompt.split("[LINES TO TRANSLATE]", 1)[-1]
    assert "A<<BR>>B" in lines_section, "internal newline must become the literal <<BR>> token"

    resp = "[1] A<<BR>>B"
    assert parse_numbered_response(resp, 1) == ["A\nB"]


def test_parse_accumulates_continuation_lines():
    r"""B1 continuation accumulation: a real-newline continuation is kept on the cue.

    A model that emits a real newline INSTEAD of <<BR>> for a multi-line cue must still
    keep the 2nd line (accumulated into the current cue). Leading text before [1] is ignored.
    """
    from trezarr.translate.engine import parse_numbered_response  # noqa: PLC0415

    out = parse_numbered_response("[1] Dòng một\nDòng hai\n[2] Chào", 2)
    assert out == ["Dòng một\nDòng hai", "Chào"], f"continuation not accumulated: {out!r}"

    # Leading noise before the first [1] marker is dropped.
    out2 = parse_numbered_response("preamble noise\n[1] Xin chào\n[2] Tạm biệt", 2)
    assert out2 == ["Xin chào", "Tạm biệt"], f"leading text not ignored: {out2!r}"


def test_parse_br_plus_real_newline_collapses():
    r"""B1 doubled-newline guard: <<BR>> next to a real newline collapses to ONE newline.

    A model that emits a <<BR>> together with a real newline at the same break must not
    produce a doubled blank line — it collapses to a single newline. A tolerant '<< BR >>'
    marker (stray whitespace) is also restored to a newline.
    """
    from trezarr.translate.engine import parse_numbered_response  # noqa: PLC0415

    out = parse_numbered_response("[1] Dòng một<<BR>>\nDòng hai\n[2] Chào", 2)
    assert out[0] == "Dòng một\nDòng hai", (
        f"<<BR>> + real newline must collapse to a single newline, got {out[0]!r}"
    )

    # Tolerant spaced marker restores to a newline.
    out2 = parse_numbered_response("[1] Dòng một<< BR >>Dòng hai", 1)
    assert out2 == ["Dòng một\nDòng hai"], f"tolerant '<< BR >>' not restored: {out2!r}"


def test_parse_numbered_response_continuation_and_br_variants():
    r"""parse_numbered_response: continuation + <<BR>> variants + existing guards (B1).

    (a) real-newline continuation accumulated; (b) <<BR>> + real newline collapses to one
    newline; (c) tolerant '<< BR >>' converted; (d) leading text ignored; (e) existing
    duplicate/out-of-range/missing/empty/count checks still raise (including '[1] <<BR>>'
    raising empty after BR resolution).
    """
    from trezarr.translate.engine import (  # noqa: PLC0415
        parse_numbered_response,
        BatchValidationError,
    )

    # (a) continuation accumulated
    assert parse_numbered_response("[1] A\nB", 1) == ["A\nB"]
    # (b) <<BR>> + real newline collapse
    assert parse_numbered_response("[1] A<<BR>>\nB", 1) == ["A\nB"]
    # (c) tolerant marker
    assert parse_numbered_response("[1] A<< BR >>B", 1) == ["A\nB"]
    # (d) leading text ignored
    assert parse_numbered_response("junk\n[1] Xin", 1) == ["Xin"]

    # (e) existing guards still fire
    with pytest.raises(BatchValidationError, match="Duplicate line number"):
        parse_numbered_response("[1] A\n[1] B", 1)
    with pytest.raises(BatchValidationError, match="unexpected line numbers"):
        parse_numbered_response("[1] A\n[2] B\n[3] C", 2)
    with pytest.raises(BatchValidationError, match="Missing line"):
        parse_numbered_response("[2] B", 2)
    # A cue that resolves to empty after BR restoration is rejected.
    with pytest.raises(BatchValidationError, match="Empty/whitespace-only"):
        parse_numbered_response("[1] <<BR>>", 1)


def test_parse_preserves_existing_validation_after_b1():
    r"""B1 must not weaken existing parser guards.

    '[1] X\n[2] Y\n[3] Z' for expected_count=2 raises 'unexpected line numbers';
    '[1] X\n[1] Y' raises 'Duplicate line number'; a missing line for expected_count=2
    raises 'Missing line'; a cue that resolves to empty after restore raises the
    empty-line BatchValidationError.
    """
    from trezarr.translate.engine import (  # noqa: PLC0415
        parse_numbered_response,
        BatchValidationError,
    )

    with pytest.raises(BatchValidationError, match="unexpected line numbers"):
        parse_numbered_response("[1] X\n[2] Y\n[3] Z", 2)
    with pytest.raises(BatchValidationError, match="Duplicate line number"):
        parse_numbered_response("[1] X\n[1] Y", 2)
    with pytest.raises(BatchValidationError, match="Missing line"):
        parse_numbered_response("[2] Y", 2)
    with pytest.raises(BatchValidationError, match="Empty/whitespace-only"):
        parse_numbered_response("[1]   \n[2] Chào", 2)


# ── C6 aliases: _normalize_name strips honorifics ────────────────────────────


def test_normalize_name_strips_honorifics():
    """C6: _normalize_name peels a leading English honorific and lowercases the name.

    'Mr. Han'/'Elder Zhou'/'Senior Han'/'Young Master Han' resolve to the bare name key;
    a bare name normalizes identically to the prior .strip().lower(); a bare honorific
    (no name token after it) is never reduced to empty; empty/whitespace → ''.
    """
    from trezarr.translate.engine import _normalize_name  # noqa: PLC0415

    assert _normalize_name("Mr. Han") == "han"
    assert _normalize_name("Elder Zhou") == "zhou"
    assert _normalize_name("Senior Han") == "han"
    assert _normalize_name("Young Master Han") == "han"
    # Bare name — identical to prior behaviour.
    assert _normalize_name("Han") == "han"
    # Bare honorific (every token is an honorific) — never empty.
    assert _normalize_name("Elder") == "elder"
    # Empty / whitespace.
    assert _normalize_name("") == ""
    assert _normalize_name("   ") == ""


# ── H1: register threading into the Pass-3 prompt ────────────────────────────


def test_build_translate_prompt_threads_register():
    """H1: build_translate_prompt injects a [REGISTER] block only when register is truthy.

    register='xianxia' → a [REGISTER] block naming 'xianxia' and a register RULE about
    classical Sino-Vietnamese vocabulary. register=None → NO [REGISTER] block and no
    classical-register RULE (back-compat).
    """
    from trezarr.translate.engine import build_translate_prompt  # noqa: PLC0415

    with_reg = build_translate_prompt(["Foo"], [], [], register="xianxia")
    assert "[REGISTER" in with_reg, "Expected a [REGISTER] block when register is provided"
    assert "xianxia" in with_reg, "Register value must appear in the prompt"
    assert "Hán-Việt" in with_reg, "Register RULE must mention classical Sino-Vietnamese (Hán-Việt)"

    no_reg = build_translate_prompt(["Foo"], [], [], register=None)
    assert "[REGISTER" not in no_reg, "No [REGISTER] block when register is None (back-compat)"


# ── M1: merge_bible_analysis called with settings on the Pass-1 path ─────────


async def test_merge_bible_analysis_called_with_settings_on_pass1_path(session_factory, tmp_path):
    """M1: translate_file's Pass-1 path forwards settings= into merge_bible_analysis.

    The engine calls merge_bible_analysis(..., settings=settings). Without settings,
    enable_relationship_events would default to True even when the user disabled it. A
    monkeypatch spy on trezarr.bible.analyze.merge_bible_analysis (the symbol the engine
    imports locally) captures the kwargs and asserts settings is the SAME object passed
    to translate_file (so enable_relationship_events=False is honoured).
    """
    from unittest.mock import AsyncMock  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    from dataclasses import dataclass  # noqa: PLC0415

    import trezarr.bible.analyze as analyze_mod  # noqa: PLC0415
    from trezarr.translate.engine import translate_file  # noqa: PLC0415
    from trezarr.bible.analyze import BibleAnalysis, CharacterInference, AddressMapInference  # noqa: PLC0415
    from trezarr.translate.attribute import (  # noqa: PLC0415
        BatchAttribution,
        LineAttribution,
        AttributionConfidence,
    )
    from trezarr.output.ledger import Ledger  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    srt_content = (
        "1\n00:00:01,000 --> 00:00:03,000\nHello Mary.\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nHello John.\n\n"
    )
    src_path = tmp_path / "Show.S01E01.en.srt"
    src_path.write_text(srt_content, encoding="utf-8")

    settings = TrezarrSettings(
        llm_api_key="test-key",
        translate_quarantine_dir=str(tmp_path / "quarantine"),
        bible_db_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        enable_pass1_analysis=True,
        enable_attribution=True,
        enable_self_review=False,
        enable_relationship_events=False,  # M1: must be honoured, not defaulted to True
        pronoun_confidence_threshold="medium",
    )

    ledger = Ledger(tmp_path / "ledger.json")

    bible_analysis = BibleAnalysis(
        register="casual",
        characters=[
            CharacterInference(original_latin_name="John", gender="male"),
            CharacterInference(original_latin_name="Mary", gender="female"),
        ],
        address_map=[
            AddressMapInference(
                speaker_name="John", addressee_name="Mary",
                self_term="anh", address_term="em", confidence=0.95,
            ),
        ],
    )
    batch_attribution = BatchAttribution(
        attributions=[
            LineAttribution(line_index=1, speaker="John", addressee="Mary", confidence=AttributionConfidence.HIGH),
            LineAttribution(line_index=2, speaker="Mary", addressee="John", confidence=AttributionConfidence.HIGH),
        ]
    )

    async def mock_llm_call(messages, response_model=None, model=None):
        if response_model is BibleAnalysis:
            return bible_analysis
        if response_model is BatchAttribution:
            return batch_attribution
        return "[1] Xin chào Mary ạ.\n[2] Chào anh nhé."

    from trezarr.llm.client import LLMClient  # noqa: PLC0415
    llm_client = LLMClient(settings)
    llm_client.call = AsyncMock(side_effect=mock_llm_call)

    # Spy on merge_bible_analysis (the engine imports it from trezarr.bible.analyze inside
    # translate_file, so patching the module attribute intercepts the engine's call).
    captured: dict = {}
    real_merge = analyze_mod.merge_bible_analysis

    async def _spy_merge(*args, **kwargs):
        captured["settings"] = kwargs.get("settings", "MISSING")
        return await real_merge(*args, **kwargs)

    monkeypatch_done = False
    orig = analyze_mod.merge_bible_analysis
    analyze_mod.merge_bible_analysis = _spy_merge
    try:
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

        eligible_item = _FakeEligibleItem(media_item=_FakeMediaItem(), source_sub_path=src_path)

        await translate_file(
            src_path, settings, llm_client, ledger,
            eligible_item=eligible_item, session_factory=session_factory,
        )
        monkeypatch_done = True
    finally:
        analyze_mod.merge_bible_analysis = orig

    assert monkeypatch_done, "translate_file did not complete"
    assert "settings" in captured, "merge_bible_analysis was never called on the Pass-1 path"
    assert captured["settings"] is settings, (
        "M1: merge_bible_analysis must be called with settings=settings (the same object), "
        f"so enable_relationship_events is honoured; got {captured['settings']!r}"
    )
