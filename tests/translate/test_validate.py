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


# ── B2/M3/H4/H5 — per-cue leak checks 9-12 + additive signature ──────────────


def _make_line_raw(index: int, text: str, raw: str | None = None, *,
                   start_tc: str = "00:00:01,000", end_tc: str = "00:00:03,000") -> object:
    """Helper: construct a SubLine, optionally with .raw set (for skip-path tests)."""
    from trezarr.subtitles.model import SubLine
    sl = SubLine(index=str(index), start_tc=start_tc, end_tc=end_tc, text=text)
    if raw is not None:
        sl.raw = raw
    return sl


# Clean Vietnamese padding cues (each carries narrow-range VI diacritics) used to keep the
# per-FILE Check 3 ratio above threshold so a SINGLE bad cue reaches the per-cue checks 9-12.
# (Audit B2: Check 3 averages a single bad cue away; it still runs FIRST as a backstop, so a
# 1-cue no-diacritic doc would trip Check 3 before Check 9/10/12 — the padding avoids that.)
_VI_PAD = ["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn nhiều", "Hẹn gặp lại sau"]


def _doc_with_bad_cue(bad_text: str, *, start_index: int = 1):
    """Translated SubDoc: the bad cue first, then 4 clean VI padding cues (ratio passes)."""
    lines = [_make_line(start_index, text=bad_text)]
    for j, pad in enumerate(_VI_PAD, start=start_index + 1):
        lines.append(_make_line(j, text=pad))
    return _make_doc(lines)


def _src_for_bad_cue(src_first: str):
    """Source SubDoc paired with _doc_with_bad_cue (English first cue + 4 source pads)."""
    src_pads = ["Hello friend", "I am well", "Thanks a lot", "See you later"]
    lines = [_make_line(1, text=src_first)]
    for j, pad in enumerate(src_pads, start=2):
        lines.append(_make_line(j, text=pad))
    return _make_doc(lines)


def test_gate_check9_cjk_leak():
    """Check 9 (B2/M3): a CJK / Hangul / Kana codepoint in a translated cue raises check 9.

    The source cue is English so checks 1-8 pass first; the translated cue carries a
    VI-diacritic-bearing rest plus a raw CJK/Hangul/Kana fragment. A clean Vietnamese-only
    doc must NOT raise on check 9.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("Hello there friends")

    # CJK ideograph leak (rest carries VI diacritics so check 3 per-line is satisfied).
    with pytest.raises(GateError) as ei:
        validate_subdoc(_doc_with_bad_cue("你好 các bạn"), src, _settings())
    assert ei.value.failure.check == 9, f"Expected check 9 (CJK leak), got {ei.value.failure.check}"

    # Pure CJK fragment, Hangul, and Hiragana variants each raise check 9.
    for leak in ("修真", "안녕", "こんにちは"):
        with pytest.raises(GateError) as ei_v:
            validate_subdoc(_doc_with_bad_cue(leak), src, _settings())
        assert ei_v.value.failure.check == 9, f"Expected check 9 for {leak!r}"

    # Clean Vietnamese-only doc — no check-9 raise.
    src_clean = _make_doc([_make_line(1, text="Hello there"), _make_line(2, text="Goodbye now")])
    trn_clean = _make_doc([_make_line(1, text="Xin chào bạn"), _make_line(2, text="Tạm biệt nhé")])
    assert validate_subdoc(trn_clean, src_clean, _settings()) is None


def test_gate_check9_cjk_hangul_kana_leak():
    """Check 9 (specialist): CJK ideograph / Hangul / Hiragana each raise check 9; raw cues skipped.

    A clean all-Vietnamese doc has zero false positives. A cue whose SubLine.raw is set is
    skipped (intentional pass-through) even if it contains CJK.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("Feng Tianji speaks")
    with pytest.raises(GateError) as ei:
        validate_subdoc(_doc_with_bad_cue("Feng 风 Tianji"), src, _settings())
    assert ei.value.failure.check == 9

    # No false positive on a clean doc.
    src_ok = _make_doc([_make_line(1, text="Hello")])
    trn_ok = _make_doc([_make_line(1, text="Xin chào bạn")])
    assert validate_subdoc(trn_ok, src_ok, _settings()) is None

    # Raw cue carrying CJK is skipped (pass-through verbatim) — padded so Check 3 passes.
    cjk = "修真者"
    src_raw = _make_doc([_make_line_raw(1, text=cjk, raw=cjk)] +
                        [_make_line(i + 2, text=p) for i, p in enumerate(_VI_PAD)])
    trn_raw = _make_doc([_make_line_raw(1, text=cjk, raw=cjk)] +
                        [_make_line(i + 2, text=p) for i, p in enumerate(_VI_PAD)])
    assert validate_subdoc(trn_raw, src_raw, _settings()) is None, (
        "A raw (pass-through) cue must be skipped by check 9"
    )


def test_gate_check10_source_passthrough_leak():
    """Check 10 (B2/H5): a verbatim English source-passthrough cue raises check 10.

    'I am here to help' translated verbatim (>=2 ASCII tokens all in source, no VI
    diacritics) raises check 10. MUST NOT false-positive on: a short VI cue 'Là anh.'
    (1 ASCII token), a fully translated cue, or a name-only cue covered by the allowlist.
    With an empty allowlist the name-only cue raises check 10.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Verbatim passthrough (cue 1) among VI padding → check 10. The source cue 1 carries
    # the same tokens so the all-in-source test fires; padding keeps Check 3 above threshold.
    src = _src_for_bad_cue("I am here to help")
    with pytest.raises(GateError) as ei:
        validate_subdoc(_doc_with_bad_cue("I am here to help"), src, _settings())
    assert ei.value.failure.check == 10, f"Expected check 10, got {ei.value.failure.check}"

    # Short VI cue with a single ASCII token ('Là anh.') — passes check 10 (need >=2 ASCII
    # tokens). Padded with VI cues so the per-file Check 3 ratio clears the threshold and the
    # cue reaches the per-cue check 10 (where its single ASCII token exempts it).
    src2 = _src_for_bad_cue("Is it you")
    trn2 = _doc_with_bad_cue("Là anh.")
    assert validate_subdoc(trn2, src2, _settings()) is None

    # Fully translated cue — passes (carries narrow-range VI diacritics).
    src3 = _make_doc([_make_line(1, text="I am here to help")])
    trn3 = _make_doc([_make_line(1, text="Tôi đến đây để giúp")])
    assert validate_subdoc(trn3, src3, _settings()) is None

    # Name-only cue (cue 1) among VI padding: passes when both tokens are in the allowlist...
    src4 = _src_for_bad_cue("Han Mei is here")
    trn4 = _doc_with_bad_cue("Han Mei")
    assert validate_subdoc(trn4, src4, _settings(), proper_noun_allowlist={"han", "mei"}) is None
    # ...but raises check 10 when the allowlist is empty/None.
    with pytest.raises(GateError) as ei4:
        validate_subdoc(trn4, src4, _settings())
    assert ei4.value.failure.check == 10


def test_gate_check10_source_passthrough_with_allowlist():
    """Check 10 (specialist): allowlist exempts a name-only passthrough; diacritics/single tokens safe.

    A no-diacritic cue whose >=2 ASCII tokens all appear in the source raises check 10;
    the SAME cue with all tokens in the allowlist does NOT; a VI-diacritic cue is never
    flagged; single-token cues are not flagged. Confirms the per-file Check 3 average no
    longer hides a single English passthrough.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("The dark forest")
    trn = _doc_with_bad_cue("The dark forest")
    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())
    assert ei.value.failure.check == 10

    # Same tokens, all allowlisted → no raise.
    assert validate_subdoc(
        trn, src, _settings(), proper_noun_allowlist={"the", "dark", "forest"}
    ) is None

    # VI-diacritic cue never flagged (1-cue doc with its own 1-cue source).
    src_vi = _make_doc([_make_line(1, text="The dark forest")])
    trn_vi = _make_doc([_make_line(1, text="Khu rừng tối")])
    assert validate_subdoc(trn_vi, src_vi, _settings()) is None

    # Single ASCII token never flagged by check 10 (padded so it reaches the per-cue check;
    # an unpadded 1-cue ASCII doc would legitimately trip the Check 3 file backstop first).
    src1 = _src_for_bad_cue("Okay then")
    trn1 = _doc_with_bad_cue("Okay")
    assert validate_subdoc(trn1, src1, _settings()) is None


def test_gate_check11_honorific_capname():
    """Check 11 (B2/H5): an English honorific + Capitalized name bigram raises check 11.

    'Mr. Han đến rồi' / 'Elder Zhou nói gì đó' / 'Miss Mei' raise check 11. Legitimate
    Vietnamese without an honorific+CapName bigram passes.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("Mr Han has arrived")
    for leak in ("Mr. Han đến rồi", "Elder Zhou nói gì đó", "Miss Mei"):
        with pytest.raises(GateError) as ei:
            validate_subdoc(_doc_with_bad_cue(leak), src, _settings())
        assert ei.value.failure.check == 11, (
            f"Expected check 11 for {leak!r}, got {ei.value.failure.check}"
        )

    # Legitimate Vietnamese — no honorific+CapName bigram.
    for ok in ("Anh ấy là bạn của tôi", "Chào anh, em khỏe không"):
        assert validate_subdoc(_doc_with_bad_cue(ok), src, _settings()) is None, (
            f"Legitimate VI cue {ok!r} must not trip check 11"
        )


def test_gate_check12_gloss_parenthetical():
    """Check 12 (H4): an English-gloss parenthetical raises check 12.

    "Em trai (Miss Mei's brother)" / "Anh (X's brother)" raise check 12. A Vietnamese
    parenthetical that carries diacritics passes; an inner with a VI diacritic ('nhanh
    lên') passes; tiny tokens '(!)'/'(?)'/'(A)' pass. Source cues carry VI diacritics so
    checks 9/10/11 don't pre-empt.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("My brother is here")
    for leak in ("Em trai (Miss Mei's brother)", "Anh (X's brother)"):
        with pytest.raises(GateError) as ei:
            validate_subdoc(_doc_with_bad_cue(leak), src, _settings())
        assert ei.value.failure.check == 12, (
            f"Expected check 12 for {leak!r}, got {ei.value.failure.check}"
        )

    # Vietnamese parenthetical carrying diacritics — passes.
    assert validate_subdoc(
        _doc_with_bad_cue("Anh Hàn (huynh trưởng của tôi)"), src, _settings()
    ) is None

    # Inner carries a VI diacritic ('lên' → ê) — recognized by LATIN_DIACRITIC_RE.
    assert validate_subdoc(_doc_with_bad_cue("Đi đi (nhanh lên)"), src, _settings()) is None

    # Tiny tokens are too short to be a gloss.
    for tiny in ("Được (!)", "Sao (?)", "Câu (A)"):
        assert validate_subdoc(_doc_with_bad_cue(tiny), src, _settings()) is None, (
            f"Tiny parenthetical in {tiny!r} must not trip check 12"
        )


def test_validate_subdoc_signature_backcompat_and_check_numbers_unchanged():
    """B2: additive proper_noun_allowlist signature + no renumbering of checks 1-8.

    validate_subdoc(trn, src, settings) (3 positional args) still works for a clean VI doc.
    Existing check numbers are preserved: count mismatch → check 1; scaffolding leak →
    check 8; a pure-ASCII English doc → check 3 (the per-file backstop fires before per-cue
    check 10 because check 3 runs earlier). proper_noun_allowlist is keyword-only (passing it
    positionally as the 4th arg raises TypeError).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # 3-positional-arg call on a clean doc → None.
    src = _make_doc([_make_line(1, text="Hello"), _make_line(2, text="Goodbye")])
    trn = _make_doc([_make_line(1, text="Xin chào bạn"), _make_line(2, text="Tạm biệt nhé")])
    assert validate_subdoc(trn, src, _settings()) is None

    # Count mismatch → check 1.
    trn1 = _make_doc([_make_line(1, text="Xin chào")])
    with pytest.raises(GateError) as ei1:
        validate_subdoc(trn1, src, _settings())
    assert ei1.value.failure.check == 1

    # Scaffolding leak → check 8.
    src_s = _make_doc([_make_line(1, text="不要")])
    trn_s = _make_doc([_make_line(1, text="(source: 不要) Đừng")])
    with pytest.raises(GateError) as ei8:
        validate_subdoc(trn_s, src_s, _settings())
    assert ei8.value.failure.check == 8

    # Pure-ASCII English doc → check 3 (per-file backstop fires before per-cue check 10).
    src_en = _make_doc([_make_line(i + 1, text=f"English line {i+1}") for i in range(5)])
    trn_en = _make_doc([_make_line(i + 1, text=f"English line {i+1}") for i in range(5)])
    with pytest.raises(GateError) as ei3:
        validate_subdoc(trn_en, src_en, _settings())
    assert ei3.value.failure.check == 3

    # proper_noun_allowlist is keyword-only — positional 4th arg raises TypeError.
    with pytest.raises(TypeError):
        validate_subdoc(trn, src, _settings(), {"han"})


def test_validate_subdoc_backward_compatible_signature():
    """C2 (specialist): 3-arg validate_subdoc still works; checks 2 and 8 keep their numbers.

    An empty-cue still raises check 2; a scaffold leak still raises check 8 — proving the
    additive checks 9-12 did not renumber the structural checks.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Empty cue → check 2 (no allowlist kwarg supplied).
    src = _make_doc([_make_line(1, text="Hello world")])
    trn_empty = _make_doc([_make_line(1, text="   ")])
    with pytest.raises(GateError) as ei2:
        validate_subdoc(trn_empty, src, _settings())
    assert ei2.value.failure.check == 2

    # Scaffold leak → check 8.
    src_s = _make_doc([_make_line(1, text="不要")])
    trn_s = _make_doc([_make_line(1, text="(source: 不要) Đừng")])
    with pytest.raises(GateError) as ei8:
        validate_subdoc(trn_s, src_s, _settings())
    assert ei8.value.failure.check == 8


# ── H4-fix: parenthesis preservation — validate gate regression ───────────────


def test_h4_vietnamese_parenthetical_passes_gate():
    """Test D: a properly-translated Vietnamese parenthetical passes Check 10 + Check 12.

    Source: "(A Record of Mortal's Journey to Immortality\\nUpheaval in Outer Sea Season 3)"
    Translated: "(Phàm Nhân Tu Tiên Ký\\nNgoại Hải Phong Vân)"

    The translated cue has Vietnamese diacritics inside the parentheses, so:
    - Check 10: VN_DIACRITIC_RE matches → skipped (not a source passthrough)
    - Check 12: LATIN_DIACRITIC_RE matches the inner text → skipped (not an English gloss)
    Expected: validate_subdoc returns None (no gate failure).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    # Source cue: English title card with parentheses
    src_text = "(A Record of Mortal's Journey to Immortality\nUpheaval in Outer Sea Season 3)"
    # Translated cue: Vietnamese rendering with diacritics, preserving the parentheses
    trn_text = "(Phàm Nhân Tu Tiên Ký\nNgoại Hải Phong Vân)"

    # Pad with VI cues so the per-file Check 3 ratio stays above threshold when the
    # parenthetical cue has diacritics (it clears Check 3 on its own; padding ensures
    # the doc has enough lines for a robust ratio even in edge cases).
    src_lines = [_make_line(1, text=src_text)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Hello there", "I am well", "Thanks"])
    ]
    trn_lines = [_make_line(1, text=trn_text)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]
    src = _make_doc(src_lines)
    trn = _make_doc(trn_lines)

    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        f"Expected None (no gate failure) for a properly-translated Vietnamese parenthetical "
        f"with diacritics. Got: {result!r}. A Vietnamese title card like '(Phàm Nhân Tu Tiên "
        f"Ký)' must NOT trigger Check 10 (VI diacritics detected) or Check 12 (LATIN_DIACRITIC_RE "
        f"matches Vietnamese diacritics → not an English gloss)."
    )


def test_h4_verbatim_sdh_sound_cue_raises_check10():
    """Test E: a verbatim SDH sound cue kept in source language raises GateError(check=10).

    Source: "(WIND HOWLING)" — an SDH sound description
    Translated: "(WIND HOWLING)" — kept verbatim in English (not translated)

    This is the known Check 10 behavior: a no-diacritic cue whose ASCII word tokens
    ("WIND", "HOWLING") all appear verbatim in the corresponding source cue is flagged
    as a source-passthrough leak. This test documents the pre-existing behavior and
    prevents the Task 1 prompt change from accidentally masking it.

    NOTE: This is EXPECTED behavior. The model should translate SDH cues, not pass them
    through verbatim. A properly-translated cue like "(Tiếng gió hú)" would pass.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_text = "(WIND HOWLING)"
    trn_text = "(WIND HOWLING)"  # verbatim, untranslated

    src_lines = [_make_line(1, text=src_text)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Hello there", "I am well", "Thanks"])
    ]
    trn_lines = [_make_line(1, text=trn_text)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]
    src = _make_doc(src_lines)
    trn = _make_doc(trn_lines)

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 10, (
        f"Expected GateError.failure.check == 10 (source-passthrough: verbatim SDH English), "
        f"got check={exc_info.value.failure.check}. A verbatim English SDH cue '(WIND HOWLING)' "
        f"must still be quarantined by Check 10 — the model must translate it, not pass it through."
    )


def test_gate_check9_credit_cue_passes():
    """Check 9 (260608-t53 exemption): a fansub credit cue translated with a short CJK handle does NOT raise.

    Live incident: Job #6 quarantined Moon Knight cue 437 because the model correctly rendered
    the Chinese credit prefix into Vietnamese ('Phụ đề dịch bởi:') and left the fansub handle
    '虫二' (a proper-name signature, untranslatable). This credit-line exemption must fire so
    the whole 437-cue file is not quarantined over a single 2-char handle.

    Preconditions: source carries CJK credit keywords (字幕翻译) AND translated CJK count ≤ threshold.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("字幕翻译：虫二")
    trn = _doc_with_bad_cue("Phụ đề dịch bởi: 虫二")

    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        f"Expected None (credit cue with short CJK handle must NOT raise GateError(9) — 260608-t53 exemption), "
        f"got {result!r}. Live incident: 'Phụ đề dịch bởi: 虫二' quarantined the whole file."
    )


def test_gate_check9_credit_long_cjk_still_quarantines():
    """Check 9 (260608-t53 threshold guard): a credit-keyword cue with a LONG CJK body STILL raises check 9.

    A fully-untranslated credit block (many CJK chars) signals a real translation failure.
    The narrow exemption must NOT mask it — both conditions must hold (keyword AND short CJK ≤ 8).
    Source carries credit keyword (字幕翻译制作团队); translated is a long fully-CJK line (>8 chars).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("字幕翻译制作团队")
    # 12 CJK chars → exceeds CJK_CREDIT_EXEMPT_MAX_CJK threshold (8)
    trn = _doc_with_bad_cue("字幕翻译制作团队制作感谢")

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())
    assert ei.value.failure.check == 9, (
        f"Expected check 9 (long CJK in credit cue must still quarantine — 260608-t53 threshold guard), "
        f"got check {ei.value.failure.check}"
    )


def test_gate_check9_noncredit_short_cjk_still_quarantines():
    """Check 9 (260608-t53 narrow guard): a non-credit cue with a short CJK handle STILL raises check 9.

    Both conditions are required: credit keyword in source AND short CJK count ≤ threshold.
    A cue from plain dialogue (source has NO credit keyword) carrying a short 2-char CJK
    handle ('虫二') must still be quarantined — the exemption must NOT fire on keyword absence.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Source is plain dialogue — no credit keyword at all
    src = _src_for_bad_cue("Hello there friends")
    trn = _doc_with_bad_cue("Đây là 虫二")

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())
    assert ei.value.failure.check == 9, (
        f"Expected check 9 (non-credit source with short CJK must still quarantine — 260608-t53 narrow guard), "
        f"got check {ei.value.failure.check}"
    )


def test_gate_check9_credit_no_cjk_passes():
    """Check 9 (260608-t53 no-regression): a credit-keyword cue with NO CJK in translated passes.

    Source carries 'Translated by FanSubTeam'; translated renders it in Vietnamese ('Phụ đề dịch bởi:
    FanSubTeam') with zero CJK codepoints. Check 9 never fires anyway (CJK_LEAK_RE finds nothing),
    so this is a no-regression test confirming the exemption path does not break the clean case.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("Translated by FanSubTeam")
    trn = _doc_with_bad_cue("Phụ đề dịch bởi: FanSubTeam")

    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        f"Expected None (credit cue with no CJK passes Check 9 without exemption — 260608-t53 no-regression), "
        f"got {result!r}"
    )


def test_gate_check9_credit_english_keyword_cue_passes():
    """Check 9 (260608-t53 English credit path): source 'Subtitles by 虫二' + translated 'Phụ đề bởi: 虫二'.

    Strengthened moat test: source carries an English credit keyword ('Subtitles by') AND the
    translated cue has a short 2-char CJK handle '虫二'. Without the fix, CJK_LEAK_RE fires on
    '虫二' in the translated text → GateError(9). With the fix, is_credit_fansub_cue() detects
    the English credit keyword in the source and the CJK count (2) ≤ CJK_CREDIT_EXEMPT_MAX_CJK
    → exemption fires → no raise. This makes the test a real coverage test for the English path.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Source carries English credit keyword 'Subtitles by'; translated keeps the 2-char CJK handle
    src = _src_for_bad_cue("Subtitles by 虫二")
    trn = _doc_with_bad_cue("Phụ đề bởi: 虫二")

    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        f"Expected None (English credit keyword + short CJK handle must pass via exemption — 260608-t53), "
        f"got {result!r}. Without fix: CJK_LEAK_RE fires on '虫二' → GateError(9); "
        f"with fix: is_credit_fansub_cue detects 'Subtitles by' in source + CJK count 2 ≤ threshold."
    )


@pytest.mark.parametrize(
    "leaked",
    [
        # classical/diacritic variant — the exact string the Ep-142 audit saw leak on-screen
        "(speaker says: tại hạ; addresses as: Mai cô nương) Ba tháng,",
        # modern variant
        "(speaker says: anh; addresses as: em) Em đừng đi.",
        # recased / spaced echo
        "( Speaker Says: ta; addresses as: ngươi) Ngươi tới rồi.",
    ],
)
def test_h4_leaked_pass3_pronoun_hint_raises_check8(leaked):
    """A leaked Pass-3 pronoun-hint parenthetical must be quarantined by Check 8.

    Regression for the trezarr-quality HIGH finding on the parenthesis-preservation
    rework: build_translate_prompt injects the per-line attribution hint as a LEADING
    parenthetical "(speaker says: …; addresses as: …)". The H4 "preserve source
    parentheses" rule raises the risk that a weak model (DeepSeek class) echoes that
    note into the cue — the 260604/260607 scaffolding-leak class (the audit showed
    "(speaker says: tại hạ; addresses as: Mai cô nương)" shipping in 7 on-screen cues).

    Defense-in-depth backstop: even though the rule wording now tells the model the hint
    is private, a leaked hint must NEVER ship — the gate quarantines it on Check 8. Each
    leaked cue carries VI diacritics in its dialogue tail so it clears Check 3 and reaches
    Check 8 (which runs before the per-cue Check 10/12 that the audit proved this string
    slips past).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_lines = [_make_line(1, text="Three months,")] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Hello there", "I am well", "Thanks"])
    ]
    trn_lines = [_make_line(1, text=leaked)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]
    src = _make_doc(src_lines)
    trn = _make_doc(trn_lines)

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 8, (
        f"Expected GateError.failure.check == 8 (Pass-3 hint scaffolding leak), got "
        f"check={exc_info.value.failure.check} for leaked cue {leaked!r}. A leaked "
        f"'(speaker says: …; addresses as: …)' hint must be quarantined, never shipped."
    )


# ---------------------------------------------------------------------------
# Check 9 codec-fidelity-guardian HIGH — false-exemption regression suite
# (260608-t53 post-review remediation)
# ---------------------------------------------------------------------------


def test_gate_check9_dialogue_mentioning_timing_still_quarantines():
    """Check 9 (260608-t53 moat regression): a dialogue cue mentioning 'timing' still quarantines.

    Codec-guardian HIGH finding: bare 'timing' in CREDIT_FANSUB_RE fires on source cues that
    contain the word 'timing' as ordinary dialogue, wrongly exempting a real CJK leak.
    Example: source 'The timing is wrong', translated 'Thời điểm 时机 sai rồi' — the 2-char
    CJK fragment 时机 (meaning 'timing') ships through to screen unchecked.

    After narrowing: 'timing' is removed from the keyword set (bare word collides with dialogue);
    English credit signals require the attribution form '... by', so this cue no longer matches
    CREDIT_FANSUB_RE and must quarantine via GateError(check=9).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("The timing is wrong")
    trn = _doc_with_bad_cue("Thời điểm 时机 sai rồi")

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())
    assert exc_info.value.failure.check == 9, (
        f"Expected GateError.failure.check == 9 (bare 'timing' in dialogue must not exempt CJK leak "
        f"— 260608-t53 moat regression), got check={exc_info.value.failure.check}. "
        f"Source 'The timing is wrong' / translated 'Thời điểm 时机 sai rồi': the 2-char CJK 时机 "
        f"must quarantine; bare 'timing' must no longer be in CREDIT_FANSUB_RE."
    )


def test_gate_check9_dialogue_mentioning_subtitle_still_quarantines():
    """Check 9 (260608-t53 moat regression): a dialogue cue mentioning 'subtitle' still quarantines.

    Codec-guardian HIGH finding: bare 'subtitle' in CREDIT_FANSUB_RE fires on source cues where
    'subtitle' is ordinary dialogue, wrongly exempting a real CJK leak.
    Example: source 'I read the subtitle aloud', translated 'Tôi đọc 字幕 to lên' — the 2-char
    CJK fragment 字幕 (meaning 'subtitle') ships through to screen unchecked.

    After narrowing: bare 'subtitle'/'subtitles' are removed; English credit signals require the
    attribution form '... by' (e.g. 'Subtitles by'), so this cue no longer matches CREDIT_FANSUB_RE
    and must quarantine via GateError(check=9). Note: 字幕 (Chinese source marker) stays in the set;
    only the ENGLISH bare word is removed.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("I read the subtitle aloud")
    trn = _doc_with_bad_cue("Tôi đọc 字幕 to lên")

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())
    assert exc_info.value.failure.check == 9, (
        f"Expected GateError.failure.check == 9 (bare 'subtitle' in dialogue must not exempt CJK leak "
        f"— 260608-t53 moat regression), got check={exc_info.value.failure.check}. "
        f"Source 'I read the subtitle aloud' / translated 'Tôi đọc 字幕 to lên': the 2-char CJK 字幕 "
        f"must quarantine; bare 'subtitle' must no longer be in CREDIT_FANSUB_RE."
    )


def test_gate_check9_sub_by_substring_in_word_still_quarantines():
    """Check 9 (260608-t53 moat regression): 'sub by' matched as substring inside 'bystander' still quarantines.

    Codec-guardian HIGH finding: unanchored 'sub by' in CREDIT_FANSUB_RE fires when 'by' appears
    as a substring inside another word (e.g. 'bystander'), wrongly exempting a real CJK leak.
    Example: source 'a sub bystander', translated 'một 路人 ngoài lề' — the 2-char CJK fragment
    路人 ships through because 'sub by' (substring of 'bystander') triggers the exemption.

    After narrowing: English credit signals use word-boundary-anchored form r'\b... by\b', so
    'bystander' no longer matches ('by\b' fails before 'stander') and the cue quarantines.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("a sub bystander")
    trn = _doc_with_bad_cue("một 路人 ngoài lề")

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())
    assert exc_info.value.failure.check == 9, (
        f"Expected GateError.failure.check == 9 ('sub by' substring in 'bystander' must not exempt "
        f"CJK leak — 260608-t53 moat regression), got check={exc_info.value.failure.check}. "
        f"Source 'a sub bystander' / translated 'một 路人 ngoài lề': word-boundary anchoring of "
        f"'sub by' must prevent the substring match inside 'bystander'."
    )


def test_gate_check9_credit_cjk_boundary():
    """Check 9 (260608-t53 threshold boundary): exactly 8 CJK chars exempts; 9 CJK chars quarantines.

    Pins the CJK_CREDIT_EXEMPT_MAX_CJK = 8 threshold boundary for the credit exemption.
    A credit-keyword cue with EXACTLY 8 CJK codepoints in the translated text must NOT raise
    (exemption fires); with EXACTLY 9 CJK codepoints it MUST raise GateError(check=9).

    This test ensures the <= 8 threshold is not accidentally widened or narrowed by future changes.
    Source carries a credit keyword in both sub-tests to ensure CREDIT_FANSUB_RE matches.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # 8 CJK chars: 字幕翻译制作团队 (exactly 8) → exemption fires → no raise
    src_8 = _src_for_bad_cue("字幕翻译制作")
    trn_8 = _doc_with_bad_cue("Phụ đề dịch bởi: 字幕翻译制作团队")  # 8 CJK
    result = validate_subdoc(trn_8, src_8, _settings())
    assert result is None, (
        f"Expected None (exactly 8 CJK chars with credit keyword must be exempt — 260608-t53 boundary), "
        f"got {result!r}. CJK_CREDIT_EXEMPT_MAX_CJK threshold is 8; count=8 must pass."
    )

    # 9 CJK chars: 字幕翻译制作团队组 (exactly 9) → threshold exceeded → raises check 9
    src_9 = _src_for_bad_cue("字幕翻译制作")
    trn_9 = _doc_with_bad_cue("Phụ đề dịch bởi: 字幕翻译制作团队组")  # 9 CJK
    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn_9, src_9, _settings())
    assert exc_info.value.failure.check == 9, (
        f"Expected GateError.failure.check == 9 (9 CJK chars exceeds threshold 8 — 260608-t53 boundary), "
        f"got check={exc_info.value.failure.check}. Count=9 must quarantine even with credit keyword."
    )


# ---------------------------------------------------------------------------
# Check 9 codec-fidelity-guardian — CJK source-marker self-exempt class
# (260608-t53 final round: CJK markers must be matched source-side ONLY)
# ---------------------------------------------------------------------------


def test_gate_check9_cjk_marker_leak_fanyi_in_translation_still_quarantines():
    """Check 9 (260608-t53 final): CJK source-marker '翻译' leaked into translated text must NOT exempt.

    Root hole: CREDIT_FANSUB_RE previously matched both src_text AND trn_text. A cue whose
    source has NO credit keyword but whose translated output leaks the Chinese marker '翻译'
    (because the model copied the source-language word verbatim) would self-exempt — the leaked
    token satisfies the keyword condition and also satisfies the ≤8 CJK threshold.

    After the split fix (CREDIT_SRC_RE / CREDIT_TRN_RE): CJK markers are matched source-side
    only. trn_text is matched only against Vietnamese markers. So '翻译' in the translated
    output is correctly treated as a CJK leak, not a credit keyword, and GateError(9) fires.

    Source: plain English dialogue (no credit keyword).
    Translated: Vietnamese text with leaked '翻译' (2 CJK chars ≤ threshold — self-exempt risk).
    Expected: GateError(check=9). (260608-t53)
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Source is plain dialogue — no credit keyword in Chinese or English
    src = _src_for_bad_cue("I read something")
    # Translated leaks the Chinese marker '翻译' (exactly 2 CJK chars — within ≤8 threshold)
    trn = _doc_with_bad_cue("Tôi đọc 翻译 rồi")

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())
    assert exc_info.value.failure.check == 9, (
        f"Expected GateError.failure.check == 9 (leaked '翻译' in translated text must not self-exempt "
        f"— 260608-t53 CJK source-marker split), got check={exc_info.value.failure.check}. "
        f"Source 'I read something' has NO credit keyword; '翻译' in translated output is the leak "
        f"itself — CJK markers must be matched source-side only."
    )


def test_gate_check9_cjk_marker_leak_jiaodui_in_translation_still_quarantines():
    """Check 9 (260608-t53 final): CJK source-marker '校对' leaked into translated text must NOT exempt.

    Analogous to the '翻译' case above — covers a second kept CJK marker ('校对', meaning
    'proofreading/QC') to confirm the fix is not marker-specific.

    Source: plain English dialogue (no credit keyword).
    Translated: Vietnamese text with leaked '校对' (2 CJK chars ≤ threshold — self-exempt risk).
    Expected: GateError(check=9). (260608-t53)
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Source is plain dialogue — no credit keyword
    src = _src_for_bad_cue("He checked the work carefully")
    # Translated leaks '校对' (2 CJK chars — within ≤8 threshold, self-exempt risk)
    trn = _doc_with_bad_cue("Anh ấy 校对 rất cẩn thận")

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())
    assert exc_info.value.failure.check == 9, (
        f"Expected GateError.failure.check == 9 (leaked '校对' in translated text must not self-exempt "
        f"— 260608-t53 CJK source-marker split), got check={exc_info.value.failure.check}. "
        f"Source 'He checked the work carefully' has NO credit keyword; '校对' in translated output "
        f"is the leak itself — CJK markers must be matched source-side only."
    )


def test_gate_check9_cjk_source_marker_in_source_still_exempts():
    """Check 9 (260608-t53 positive guard): Chinese credit marker in SOURCE text still exempts correctly.

    After the split: CREDIT_SRC_RE matches CJK markers against src_text. A source cue whose
    text contains '字幕组制作' (a Chinese fansub credit marker) plus a short CJK handle in
    the translated output must still be EXEMPT — the source-side match is the correct path.

    This is the positive guard confirming the split does not break the source-side path.

    Source: '字幕组制作' (Chinese fansub group credit, contains source-marker '字幕组').
    Translated: 'Phụ đề bởi: 虫二' (Vietnamese with 2-char CJK handle).
    Expected: None (exempt). (260608-t53)
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    src = _src_for_bad_cue("字幕组制作")
    trn = _doc_with_bad_cue("Phụ đề bởi: 虫二")

    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        f"Expected None (Chinese credit marker in source + short CJK handle must be exempt — "
        f"260608-t53 positive guard), got {result!r}. CREDIT_SRC_RE must still match '字幕组' "
        f"in src_text and grant the exemption for a ≤8 CJK translated handle."
    )


# ── R4: gate leak classes (260611-ru6) ──────────────────────────────────────────
# Audit 260611-l74 C1: three cue forms leak through all 12 checks and ship on-screen.
# Verbatim from the shipped Moon Knight S01E03 .vi.srt (confirmed raw bytes / raw cue text):
#
#   Cue 146: 'Anh không đi cùng sao? \n (Correct; "tôi"→"anh" is the right pair; no violation)'
#   Cue 147: 'Tôi sẽ đi. (No violation)'
#   Cue 459: '<<T153'  (raw, NOT HTML-escaped)
#
# WHY each bypasses all 12 existing checks (per 03_verdicts.md):
#   Cues 146/147: Check 10 skipped (VN diacritics present); Check 12 skipped (diacritic in paren
#     inner / no possessive); Check 8 does not match '(No violation)' or '(Correct;...)'.
#   Cue 459: SENTINEL_RE requires closing '>>' — '<<T153' has none → Check 6 misses it;
#     Check 10 skipped (0 ASCII word tokens >= 2 letters: 'T153' = 1 letter + digits).
#
# Fixes:
#   Class 1+2: new ATTRIBUTION_META_RE added to Check 8 — catches '(No violation)' and
#     '(Correct; ...)' patterns that cannot appear in genuine Vietnamese dialogue.
#   Class 3: new UNCLOSED_SENTINEL_RE added to Check 6 — catches '<<TN' without closing '>>'.
#
# Regression guards: t53 credit exemption ('Phụ đề dịch bởi: 虫二') still passes;
# envelope-preservation tests unchanged; all existing Check 6/8/10/12 behavior unchanged.
# D-03: gate may only get STRICTER — no regression broadening.


def test_r4_leak_attribution_meta_correct_prefix():
    """R4-I: '(Correct; "tôi"→"anh" is the right pair; no violation)' raises GateError(check=8).

    Verbatim E03 cue 146 leak (audit 260611-l74 C1). Currently passes all 12 checks because
    Check 10 is skipped (VN diacritics 'Anh không' present) and Check 12 is skipped
    (diacritics in inner text). After fix, ATTRIBUTION_META_RE in Check 8 must catch it.

    Uses _doc_with_bad_cue / _src_for_bad_cue helpers to keep Check 3 (diacritic ratio)
    passing so the per-cue Check 8 is reached.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Verbatim E03 cue 146 — source is Chinese, output leaked the attribution meta-comment.
    # The text has VN diacritics ('Anh không', 'tôi', 'anh') so Check 10/12 skip it,
    # letting it pass all 12 checks before the R4 fix.
    src = _src_for_bad_cue("你不一起来吗？")
    trn = _doc_with_bad_cue('Anh không đi cùng sao? (Correct; "tôi"→"anh" is the right pair; no violation)')

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 8, (
        f"R4-I: cue 146 attribution meta '(Correct; ...)' must raise GateError(check=8); "
        f"got check={exc_info.value.failure.check}. "
        "Before fix: passes all 12 checks because Check 10/12 skip on VN diacritics."
    )


def test_r4_leak_attribution_meta_no_violation():
    """R4-J: 'Tôi sẽ đi. (No violation)' raises GateError(check=8).

    Verbatim E03 cue 147 leak (audit 260611-l74 C1). Currently passes because
    Check 12 does not fire (no possessive/'s), Check 10 skipped (VN diacritics present).
    After fix, ATTRIBUTION_META_RE must catch '(No violation)'.

    Uses _doc_with_bad_cue helper to keep Check 3 diacritic ratio passing.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Verbatim E03 cue 147 — source is Chinese, output leaked the review note.
    # 'Tôi sẽ đi.' has VN diacritics, so Check 10/12 skip the cue before R4 fix.
    src = _src_for_bad_cue("我会去的")
    trn = _doc_with_bad_cue("Tôi sẽ đi. (No violation)")

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 8, (
        f"R4-J: '(No violation)' must raise GateError(check=8); "
        f"got check={exc_info.value.failure.check}. "
        "Before fix: passes all 12 checks because Check 10/12 skip on VN diacritics."
    )


def test_r4_leak_unclosed_sentinel():
    """R4-K: '<<T153' (unclosed sentinel, no closing >>) raises GateError(check=6).

    Verbatim E03 cue 459 (raw bytes 3c3c 5431 3533 — NOT HTML-escaped, per 03_verdicts.md).
    Currently passes because SENTINEL_RE requires closing '>>' and Check 10 is skipped
    (0 ASCII word tokens >= 2 letters: 'T153' = 1 letter + digits).
    After fix, UNCLOSED_SENTINEL_RE must catch '<<T153' in Check 6.

    Uses _doc_with_bad_cue helper to keep Check 3 diacritic ratio passing so
    the structural Check 6 is reached.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    # Verbatim E03 cue 459 — source is Chinese, output has bare unclosed sentinel.
    src = _src_for_bad_cue("没事的")
    trn = _doc_with_bad_cue("<<T153")

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, _settings())

    assert exc_info.value.failure.check == 6, (
        f"R4-K: unclosed sentinel '<<T153' must raise GateError(check=6); "
        f"got check={exc_info.value.failure.check}. "
        "Before fix: SENTINEL_RE needs closing '>>' → passes Check 6; "
        "Check 10 skipped (T153 has only 1 ASCII letter)."
    )


# ── FIX4: UNCLOSED_SENTINEL_RE comment accuracy (260611-ru6 LOW) ─────────────
# Codec-fidelity-guardian finding: the comment on UNCLOSED_SENTINEL_RE at
# validate.py:100-101 claims "(?!>>) prevents matching the closed form <<T153>>"
# but this is factually wrong. The regex DOES match <<T153>> (at a shorter digit
# offset due to backtracking: tries 153, lookahead fails, backtracks to 15 → matches
# <<T15). The closed form is already caught by SENTINEL_RE, so the double-fire is
# harmless (belt-and-suspenders), but the comment's claimed guarantee is false.
#
# TDD flow:
#   RED: assert the comment's claim (closed form does NOT match → search returns None)
#        → FAILS because the regex DOES match at the backtracked position.
#   FIX: rewrite the comment to state the actual behaviour; flip test to GREEN form.
#   GREEN: assert actual behaviour — closed form DOES match (backtracking occurs).


def test_fix4_unclosed_sentinel_re_closed_form_does_match_via_backtrack():
    """FIX4 GREEN: documents actual UNCLOSED_SENTINEL_RE behaviour for the closed form.

    The prior comment claimed '(?!>>) prevents matching <<T153>>'. This was wrong.
    Actual behaviour (confirmed by codec-fidelity-guardian review):
      - <<T153>> → digit-group tries '153'; lookahead fails (next is '>>'); backtracks to '15';
        lookahead sees '3' (not '>>') → MATCHES at span (0, 5) = '<<T15'.
    The double-fire is harmless: SENTINEL_RE catches '<<T153>>' via the OR in Check 6,
    so the verdict (GateError check=6) is the same regardless.

    The comment has been corrected (FIX4) to state the actual backtracking behaviour.
    This test is the contract: the closed form DOES match UNCLOSED_SENTINEL_RE.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    UNCLOSED_SENTINEL_RE = validate_mod.UNCLOSED_SENTINEL_RE

    # Actual behaviour: closed form DOES match (at backtracked offset '<<T15')
    result = UNCLOSED_SENTINEL_RE.search("<<T153>>")
    assert result is not None, (
        "FIX4: UNCLOSED_SENTINEL_RE must match '<<T153>>' (at backtracked position '<<T15'). "
        "The (?!>>) lookahead does not exclude the closed form due to digit backtracking."
    )
    # The match is at the backtracked position (spans 0-5, matching '<<T15')
    assert result.group() == "<<T15", (
        f"FIX4: match on '<<T153>>' expected '<<T15' (backtracked digit group), "
        f"got {result.group()!r}"
    )

    # Genuine unclosed form (no closing >>) still matches as before
    result2 = UNCLOSED_SENTINEL_RE.search("<<T153")
    assert result2 is not None, "FIX4: genuine unclosed '<<T153' must still match"
    assert result2.group() == "<<T153", (
        f"FIX4: unclosed match expected '<<T153', got {result2.group()!r}"
    )


# ---------------------------------------------------------------------------
# 260612-7kt Task 1 — VN-label hint scaffold detection (Check 8 + VN_HINT_SCAFFOLD_RE)
# ---------------------------------------------------------------------------
# E143 cue 148: "(tại hạ nói: tại hạ; xưng hô: cô nương) xin cô nương nén bi thương."
# A weak model translated the English labels into Vietnamese.  HINT_SCAFFOLD_RE is
# anchored to "speaker says:" and misses this form.  VN_HINT_SCAFFOLD_RE closes the gap.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leaked_vn",
    [
        # Exact E143 cue 148 string
        "(tại hạ nói: tại hạ; xưng hô: cô nương) xin cô nương nén bi thương.",
        # Bare nói: label only
        "(nói: ta; xưng hô: ngươi) Ngươi tới rồi.",
        # Bare xưng hô: label only
        "(xưng hô: muội) Em đừng đi.",
        # nói: with surrounding text before the colon — structural label must still fire
        "(tôi nói: rằng sao) Điều đó sai rồi.",
    ],
)
def test_vn_label_hint_scaffold_raises_check8(leaked_vn):
    """A translated-label pronoun hint — e.g. '(tại hạ nói: tại hạ; xưng hô: cô nương)' —
    must be quarantined by Check 8 via VN_HINT_SCAFFOLD_RE.

    E143 cue 148 incident: the model translated the English labels 'speaker says' / 'addresses
    as' into Vietnamese ('nói' / 'xưng hô'), evading both _LEAKED_HINT_RE (engine strip) and
    HINT_SCAFFOLD_RE (Check 8).  VN_HINT_SCAFFOLD_RE adds the Vietnamese-label variant.

    The discriminating structural signal is the COLON after the role token (`nói:` or
    `xưng hô:`) — distinguishing a label structure from a stage direction (`nói to`).
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_lines = [_make_line(1, text="English source cue")] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["A", "B", "C"])
    ]
    trn_lines = [_make_line(1, text=leaked_vn)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(_make_doc(trn_lines), _make_doc(src_lines), _settings())

    assert exc_info.value.failure.check == 8, (
        f"Expected GateError.failure.check == 8 (VN-label hint scaffold), "
        f"got check={exc_info.value.failure.check} for {leaked_vn!r}. "
        f"VN_HINT_SCAFFOLD_RE must catch translated-label form (nói:/xưng hô: colon structure)."
    )


@pytest.mark.parametrize(
    "safe_vn",
    [
        # Stage directions — nói WITHOUT colon → must pass
        "(thì thầm)",
        "(nói to)",
        "(nói chậm rãi)",
        "(vui vẻ)",
        # Title-card with colon after chapter label — NOT a pronoun/speaker label
        "(Hồi 01: Mở Đầu)",
        # Title card no colon
        "(Phàm Nhân Tu Tiên Ký)",
    ],
)
def test_vn_label_false_positive_battery(safe_vn):
    """Stage directions, title-cards and chapter labels must NOT be quarantined by VN_HINT_SCAFFOLD_RE.

    False-positive battery for the colon-discriminator design: `nói` and `xưng hô` without a
    COLON after them are stage directions, not pronoun-label structures.  `(Hồi 01: Mở Đầu)`
    has a colon but the token before the colon is `Hồi 01`, not a pronoun-role word.

    All inputs must pass validate_subdoc without raising GateError.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    # Build a doc where the first cue contains the parenthetical plus enough Vietnamese
    # diacritics to clear Check 3.
    cue_text = safe_vn + " Xin chào thế giới."
    src_lines = [_make_line(1, text="English source")] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["A", "B", "C"])
    ]
    trn_lines = [_make_line(1, text=cue_text)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]

    # Must not raise GateError
    result = validate_subdoc(_make_doc(trn_lines), _make_doc(src_lines), _settings())
    assert result is None, (
        f"Stage direction / title-card {safe_vn!r} must NOT be quarantined by VN_HINT_SCAFFOLD_RE. "
        f"The colon-discriminator must require the token before ':' to be a pronoun-role word "
        f"(nói or xưng hô), not an arbitrary chapter/episode marker."
    )


def test_t53_credit_exemption_unaffected_by_vn_hint_change():
    """t53 credit cue 'Phụ đề bởi: 虫二' still passes via Check 9 exemption.

    Regression guard: VN_HINT_SCAFFOLD_RE must NOT match 'Phụ đề bởi:' — the token before
    ':' is 'bởi', not 'nói' or 'xưng hô'.  Check 9 credit exemption remains the gating path.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    src = _make_doc([_make_line(1, text="Subtitles by 虫二")])
    trn = _make_doc([_make_line(1, text="Phụ đề bởi: 虫二")])

    result = validate_subdoc(trn, src, _settings())
    assert result is None, (
        "t53 credit cue 'Phụ đề bởi: 虫二' must still pass via Check 9 exemption. "
        "VN_HINT_SCAFFOLD_RE must NOT match 'Phụ đề bởi:' (bởi is not nói or xưng hô)."
    )


# ---------------------------------------------------------------------------
# 260612-7kt review round — Finding A: nói:-only reported speech is a false positive
# ---------------------------------------------------------------------------
# Ordinary Vietnamese reported speech uses 'nói:' without 'xưng hô:'.
# '(Hắn nói: đợi ta ở đây)' is legitimate text that _preserve_source_envelopes can produce.
# Fix: require 'xưng hô:' as the mandatory anchor (nói: optional prefix).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reported_speech",
    [
        # Ordinary reported speech — nói: without xưng hô: → must NOT be quarantined
        "(Hắn nói: đợi ta ở đây) Anh đợi ta nhé.",
        "(Cô ấy nói: đừng lo) anh ạ.",
        # Previously false-positive in 7kt: nói: without xưng hô:
        "(tôi nói: rằng sao) Điều đó sai rồi.",
    ],
)
def test_noi_only_reported_speech_not_quarantined(reported_speech):
    """Reported speech '(X nói: Y)' without 'xưng hô:' must NOT be quarantined by Check 8.

    'nói' alone is the ordinary Vietnamese verb for 'says/speaks'.  It appears in
    legitimate subtitle text such as '(Hắn nói: đợi ta ở đây)' which
    _preserve_source_envelopes can produce from source '（他说：在这里等我）'.

    The mandatory anchor for VN_HINT_SCAFFOLD_RE must be 'xưng hô:' — the
    pronoun-role label that can NEVER appear in genuine Vietnamese dialogue.
    'nói:' alone has too high a false-positive rate.

    RED: currently VN_HINT_SCAFFOLD_RE matches nói:-only and raises Check 8 incorrectly.
    GREEN: pattern changed to require xưng hô: as mandatory anchor.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    src_lines = [_make_line(1, text="Source line")] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["A", "B", "C"])
    ]
    trn_lines = [_make_line(1, text=reported_speech)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]

    result = validate_subdoc(_make_doc(trn_lines), _make_doc(src_lines), _settings())
    assert result is None, (
        f"Reported speech {reported_speech!r} must NOT be quarantined by VN_HINT_SCAFFOLD_RE. "
        f"The mandatory anchor must be 'xưng hô:' (the pronoun-role label), not 'nói:' alone."
    )


# ---------------------------------------------------------------------------
# 260612-7kt review round — Finding B: fullwidth colon ： and square brackets [...]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leaked_vn_fw",
    [
        # Fullwidth colon variant of the E143 leak — must be caught
        "(tại hạ nói：tại hạ; xưng hô：cô nương) xin cô nương nén bi thương.",
        # Fullwidth colon, xưng hô: anchor only
        "(xưng hô：muội) Em đừng đi.",
    ],
)
def test_fullwidth_colon_vn_hint_scaffold_raises_check8(leaked_vn_fw):
    """Fullwidth-colon variant '：' (U+FF1A) of the VN-label hint must be quarantined.

    A model may emit the fullwidth colon when translating the hint labels.
    VN_HINT_SCAFFOLD_RE must treat '：' identically to ':' (ASCII U+003A).

    RED: current pattern only matches ASCII ':'; fullwidth '：' evades it.
    GREEN: colon class becomes [:：] in VN_HINT_SCAFFOLD_RE.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_lines = [_make_line(1, text="English source")] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["A", "B", "C"])
    ]
    trn_lines = [_make_line(1, text=leaked_vn_fw)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(_make_doc(trn_lines), _make_doc(src_lines), _settings())

    assert exc_info.value.failure.check == 8, (
        f"Fullwidth-colon variant {leaked_vn_fw!r} must raise Check 8. "
        f"Colon class must be [:：] to catch U+FF1A."
    )


@pytest.mark.parametrize(
    "leaked_vn_sq",
    [
        # Square-bracket envelope variant — must be caught
        "[tại hạ nói: tại hạ; xưng hô: cô nương] xin cô nương nén bi thương.",
        # Square-bracket, xưng hô: only
        "[xưng hô: muội] Em đừng đi.",
    ],
)
def test_square_bracket_vn_hint_scaffold_raises_check8(leaked_vn_sq):
    """Square-bracket variant '[...]' of the VN-label hint must be quarantined by Check 8.

    A model that uses '[' instead of '(' for the hint envelope still leaks scaffold.
    VN_HINT_SCAFFOLD_RE opener must match both '(' and '['.

    RED: current pattern uses \\( literal; '[...]' evades it.
    GREEN: opener class becomes [(\[] in VN_HINT_SCAFFOLD_RE.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    src_lines = [_make_line(1, text="English source")] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["A", "B", "C"])
    ]
    trn_lines = [_make_line(1, text=leaked_vn_sq)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(_make_doc(trn_lines), _make_doc(src_lines), _settings())

    assert exc_info.value.failure.check == 8, (
        f"Square-bracket variant {leaked_vn_sq!r} must raise Check 8. "
        f"Opener must be [(\[] to catch '[' as well as '('."
    )


def test_legit_bracket_title_card_not_quarantined():
    """Legitimate bracket title card '[Phàm Nhân Tu Tiên Ký]' must NOT be quarantined.

    Guards the Finding B fix: the opener class [(\[] must not cause false positives on
    square-bracket title cards.  '[Phàm Nhân Tu Tiên Ký]' has no 'xưng hô:' inside —
    the mandatory anchor — so it must pass Check 8 cleanly.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc

    cue_text = "[Phàm Nhân Tu Tiên Ký] Hồi Ức Đầu Tiên."
    src_lines = [_make_line(1, text="Source")] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["A", "B", "C"])
    ]
    trn_lines = [_make_line(1, text=cue_text)] + [
        _make_line(i + 2, text=p) for i, p in enumerate(["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn"])
    ]

    result = validate_subdoc(_make_doc(trn_lines), _make_doc(src_lines), _settings())
    assert result is None, (
        f"Bracket title card {cue_text!r} must pass Check 8. "
        f"No 'xưng hô:' inside — mandatory anchor missing — must not be caught."
    )
