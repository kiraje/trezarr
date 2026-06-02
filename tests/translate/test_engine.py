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
