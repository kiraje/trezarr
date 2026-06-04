"""RED test stubs for ENG-06: 7-check validation gate in trezarr.translate.validate.

All imports from trezarr.translate.validate are deferred inside each test function body
so pytest collection succeeds even when the implementation module does not yet exist.
Tests skip cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Covers all 7 gate checks (D-16, ENG-06):
  Check 1 — Cue count mismatch → GateError(check=1)
  Check 2 — Whitespace-only translated line → GateError(check=2)
  Check 3 — VI diacritic ratio below threshold → GateError(check=3)
  Check 3 — Allowlist-exempt lines excluded from ratio denominator
  Check 4 — Timecode mutation → GateError(check=4)
  Check 5 — Non-monotonic timestamps → GateError(check=5)
  Check 6 — Orphan sentinel token → GateError(check=6)
  Check 7 — Lone surrogate (invalid UTF-8) → GateError(check=7)
  All checks pass → returns None
"""
import pytest


def _make_line(index: int, start_tc: str = "00:00:01,000", end_tc: str = "00:00:03,000", text: str = "Xin chào") -> object:
    """Helper: construct a SubLine."""
    from trezarr.subtitles.model import SubLine
    return SubLine(index=str(index), start_tc=start_tc, end_tc=end_tc, text=text)


def _make_doc(lines: list) -> object:
    """Helper: construct a SubDoc."""
    from trezarr.subtitles.model import SubDoc
    return SubDoc(
        lines=lines,
        encoding="utf-8",
        line_ending="\n",
        separators=["\n\n"] * max(0, len(lines) - 1),
        leading="",
        trailer="\n",
    )


def _settings():
    """Return a TrezarrSettings with test-safe defaults."""
    from trezarr.config import TrezarrSettings
    return TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
    )


def test_gate_review_scaffolding_leak():
    """A cue carrying leaked Pass-4 '(source: …)' review scaffolding raises GateError(check=8).

    Defense-in-depth backstop for the 260604-gza finding: even if the engine's
    splice guard were bypassed, a sidecar containing the review-prompt scaffolding
    must never ship — the gate quarantines it. The VI 'Đừng' clears Check 3's
    per-line diacritic test, so the file reaches Check 8.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _make_doc([_make_line(1, text="不要")])
    trn = _make_doc([_make_line(1, text="(source: 不要) Đừng")])  # scaffolding echoed into output

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 8, (
        f"Expected GateError.failure.check == 8 (review scaffolding leak), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_count_mismatch():
    """Translated SubDoc with one fewer line than source raises GateError(check=1) (ENG-06)."""
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc
    from trezarr.subtitles.model import SubDoc, SubLine

    src = _make_doc([_make_line(1), _make_line(2)])
    trn = _make_doc([_make_line(1)])  # one line dropped

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 1, (
        f"Expected GateError.failure.check == 1 (cue count mismatch), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_empty_line():
    """Whitespace-only translated line raises GateError(check=2) (ENG-06)."""
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _make_doc([_make_line(1, text="Hello world")])
    trn = _make_doc([_make_line(1, text="   ")])  # whitespace-only

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 2, (
        f"Expected GateError.failure.check == 2 (empty translated line), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_vi_ratio():
    """Translated lines byte-identical to English source → GateError(check=3) (ENG-06).

    No Vietnamese diacritics → VI diacritic ratio below threshold.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc
    from trezarr.config import TrezarrSettings

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
        translate_vi_diacritic_ratio=0.70,
    )

    # All 5 lines are pure ASCII — no Vietnamese diacritics
    lines_src = [_make_line(i + 1, text=f"English line {i+1}") for i in range(5)]
    lines_trn = [_make_line(i + 1, text=f"English line {i+1}") for i in range(5)]
    src = _make_doc(lines_src)
    trn = _make_doc(lines_trn)

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, settings)

    assert exc_info.value.failure.check == 3, (
        f"Expected GateError.failure.check == 3 (VI diacritic ratio), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_vi_ratio_allowlist_exempt():
    """Lines composed entirely of punctuation/digits/symbols are excluded from ratio denominator.

    A file of all-punctuation lines should not trigger check 3 (ENG-06 / D-17).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc
    from trezarr.config import TrezarrSettings

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
        translate_vi_diacritic_ratio=0.70,
    )

    # Lines that are ALL punctuation — on the allowlist → excluded from ratio denominator
    # With 0 translatable lines, ratio should default to 1.0 (all exempt)
    lines_src = [_make_line(i + 1, text=text) for i, text in enumerate(["...", "♪♫", "---", "!!!", "???"])]
    lines_trn = [_make_line(i + 1, text=text) for i, text in enumerate(["...", "♪♫", "---", "!!!", "???"])]
    src = _make_doc(lines_src)
    trn = _make_doc(lines_trn)

    # Should NOT raise — all-punctuation lines are allowlisted
    result = validate_subdoc(trn, src, settings)
    assert result is None, f"Expected None (no gate failure) for all-punctuation lines, got {result}"


def test_gate_timecode_mutation():
    """Translated SubLine with different start_tc raises GateError(check=4) (ENG-06)."""
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_line = _make_line(1, start_tc="00:00:01,000", end_tc="00:00:03,000", text="Xin chào bạn")
    trn_line = _make_line(1, start_tc="00:00:02,000", end_tc="00:00:03,000", text="Xin chào bạn")  # mutated start_tc

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 4, (
        f"Expected GateError.failure.check == 4 (timecode mutation), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_overlapping_source_cues_preserved_timing_passes():
    """Overlapping source cues with timing preserved by translation PASS Check 5.

    Regression for the codec-fidelity invariant (D-08/D-09): simultaneous/overlapping
    cues (e.g. dual-speaker lines, song karaoke layers) are legitimate in source SRTs.
    Translation copies timing verbatim.  The gate must NOT quarantine such files.

    Line 1: 00:00:05,000 → 00:00:10,000
    Line 2: 00:00:08,000 → 00:00:12,000 — overlaps with line 1 in BOTH source and translated.
    Both source and translated have identical timing → PASS (no GateError).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    # Both source and translated carry the same overlapping timecodes.
    src_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    src_line2 = _make_line(2, start_tc="00:00:08,000", end_tc="00:00:12,000", text="Tôi ổn cảm ơn")
    trn_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    trn_line2 = _make_line(2, start_tc="00:00:08,000", end_tc="00:00:12,000", text="Tôi ổn cảm ơn")

    src = _make_doc([src_line1, src_line2])
    trn = _make_doc([trn_line1, trn_line2])

    # Must NOT raise — overlapping cues that are present in the source are faithfully
    # preserved by translation and must pass the gate.
    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        f"Expected None (overlapping SOURCE cues with preserved timing should PASS), got {result}"
    )


def test_gate_timing_mutation_fails():
    """Translated doc whose timing was mutated relative to source FAILS Check 5.

    If the engine somehow altered a cue's start_ms or end_ms, Check 5 must catch it
    even when Check 4 (byte-identity of timecode strings) passed (e.g. a codec that
    re-formats the timecode string identically but shifts the underlying milliseconds).
    Here we simulate a direct ms-level mutation that produces a different timecode string.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Source: cue at [5000ms, 10000ms]
    src_line = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    # Translated: start_tc shifted by 1 s → timecodes differ from source
    trn_line = _make_line(1, start_tc="00:00:06,000", end_tc="00:00:10,000", text="Xin chào bạn")

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    # Check 4 catches the timecode string mutation first; Check 5 would also catch it
    # if Check 4 didn't.  Either way, a GateError must be raised.
    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    # Check 4 fires first for a timecode string mismatch; accept either check 4 or 5.
    assert exc_info.value.failure.check in (4, 5), (
        f"Expected GateError.failure.check in (4, 5) for timing mutation, "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_backward_jump_preserved_from_source_passes():
    """Backward-jump in SOURCE with timing preserved by translation PASSES Check 5.

    Under the codec-fidelity invariant (D-08/D-09), Check 5 only catches timing
    mutations introduced by translation.  A backward jump that already exists in the
    source file is faithfully preserved — it is a SOURCE quality issue, not a
    translation error.  The gate must not quarantine such files.

    cue0 = [5000ms, 10000ms], cue1 = [3000ms, 4000ms] — both in source and translated.
    Timing is preserved verbatim → PASS.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    src_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    src_line2 = _make_line(2, start_tc="00:00:03,000", end_tc="00:00:04,000", text="Tôi ổn cảm ơn")
    trn_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    trn_line2 = _make_line(2, start_tc="00:00:03,000", end_tc="00:00:04,000", text="Tôi ổn cảm ơn")

    src = _make_doc([src_line1, src_line2])
    trn = _make_doc([trn_line1, trn_line2])

    # Must NOT raise — backward jump was in the source; translation preserved it faithfully.
    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        f"Expected None (backward-jump in SOURCE with preserved timing should PASS), got {result}"
    )


def test_gate_sentinel_orphan():
    """Translated SubLine containing <<T0>> raises GateError(check=6) (ENG-06)."""
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_line = _make_line(1, text="Xin chào bạn tôi ơi")
    trn_line = _make_line(1, text="Xin chào <<T0>> tôi ơi")  # unreinserted sentinel

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 6, (
        f"Expected GateError.failure.check == 6 (orphan sentinel), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_utf8_invalid():
    """Translated SubLine containing a lone surrogate raises GateError(check=7) (ENG-06)."""
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_line = _make_line(1, text="Xin chào bạn")
    trn_line = _make_line(1, text="Xin ch" + chr(0xD800) + "o bạn")  # lone surrogate

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 7, (
        f"Expected GateError.failure.check == 7 (UTF-8 invalid), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_all_checks_pass():
    """A correctly translated SubDoc (Vietnamese diacritics, same cue count, same timecodes,
    no sentinels, monotonic) returns None (no exception) (ENG-06).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    tc1_start, tc1_end = "00:00:01,000", "00:00:03,000"
    tc2_start, tc2_end = "00:00:04,000", "00:00:06,000"

    src = _make_doc([
        _make_line(1, start_tc=tc1_start, end_tc=tc1_end, text="Hello world"),
        _make_line(2, start_tc=tc2_start, end_tc=tc2_end, text="How are you"),
    ])
    trn = _make_doc([
        _make_line(1, start_tc=tc1_start, end_tc=tc1_end, text="Xin chào thế giới"),
        _make_line(2, start_tc=tc2_start, end_tc=tc2_end, text="Bạn có khỏe không"),
    ])

    result = validate_subdoc(trn, src, _settings())

    assert result is None, f"Expected None (no gate failure) for valid translation, got {result}"
