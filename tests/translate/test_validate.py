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


def test_gate_nonmonotonic():
    """Two adjacent lines where start_tc[1] < end_tc[0] raises GateError(check=5) (ENG-06)."""
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Line 1: 00:00:05,000 → 00:00:10,000
    # Line 2: 00:00:08,000 → 00:00:12,000 — overlaps with line 1
    src_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    src_line2 = _make_line(2, start_tc="00:00:08,000", end_tc="00:00:12,000", text="Tôi ổn cảm ơn")
    trn_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    trn_line2 = _make_line(2, start_tc="00:00:08,000", end_tc="00:00:12,000", text="Tôi ổn cảm ơn")

    src = _make_doc([src_line1, src_line2])
    trn = _make_doc([trn_line1, trn_line2])

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 5, (
        f"Expected GateError.failure.check == 5 (non-monotonic timestamps), "
        f"got {exc_info.value.failure.check}"
    )


def test_gate_backward_jump():
    """Cue that starts before previous cue (backward jump) raises GateError(check=5) (WR-01).

    cue0 = [5000ms, 10000ms], cue1 = [3000ms, 4000ms]: cue1 starts before cue0,
    which is a non-monotonic ordering violation.  The original overlap check missed
    this because 3000 > 5000 is False (the first conjunct was false).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # cue0: 5000ms–10000ms, cue1: 3000ms–4000ms (backward start)
    src_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    src_line2 = _make_line(2, start_tc="00:00:03,000", end_tc="00:00:04,000", text="Tôi ổn cảm ơn")
    trn_line1 = _make_line(1, start_tc="00:00:05,000", end_tc="00:00:10,000", text="Xin chào bạn")
    trn_line2 = _make_line(2, start_tc="00:00:03,000", end_tc="00:00:04,000", text="Tôi ổn cảm ơn")

    src = _make_doc([src_line1, src_line2])
    trn = _make_doc([trn_line1, trn_line2])

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 5, (
        f"Expected GateError.failure.check == 5 (backward jump in timestamps), "
        f"got {exc_info.value.failure.check}"
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
