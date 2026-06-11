"""RED→GREEN tests for per-cue accumulation in validate_subdoc (260612-4lq).

Before the fix:  validate_subdoc raises GateError on the FIRST failing cue it encounters.
After the fix:   validate_subdoc collects ALL failing cue indices for the highest-priority
                 check (9 > 11 > 12 > 10) and raises ONE GateError with a complete
                 failing_indices list.

Tests A/B/C/E/F: FAIL before the fix (indices list incomplete), PASS after.
Test D:          regression guard — MUST PASS both before and after (single failing cue).

Execution mode:  asyncio_mode=auto (pyproject.toml global setting);
                 validate_subdoc is synchronous — called directly in regular test functions.
"""

from __future__ import annotations

from typing import Any


# ── Helpers (mirrors test_gate_repair.py) ─────────────────────────────────────


def _make_line(
    index: int,
    start_tc: str = "00:00:01,000",
    end_tc: str = "00:00:03,000",
    text: str = "Xin chào",
) -> object:
    from trezarr.subtitles.model import SubLine

    return SubLine(index=str(index), start_tc=start_tc, end_tc=end_tc, text=text)


def _make_doc(lines: list) -> object:
    from trezarr.subtitles.model import SubDoc

    return SubDoc(
        lines=lines,
        encoding="utf-8",
        line_ending="\n",
        separators=["\n\n"] * max(0, len(lines) - 1),
        leading="",
        trailer="\n",
    )


def _settings(**overrides: Any) -> object:
    from trezarr.config import TrezarrSettings

    defaults = dict(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
    )
    defaults.update(overrides)
    return TrezarrSettings(**defaults)


# ── Shared VI padding (carries diacritics so Check 3 passes) ──────────────────
# Four clean VI cues used to keep the per-file diacritic ratio above threshold.
_VI_PAD = ["Xin chào bạn", "Tôi rất khỏe", "Cảm ơn nhiều", "Hẹn gặp lại sau"]
_SRC_PAD = ["Hello friend", "I am well", "Thanks a lot", "See you later"]


# ── Test A — multi-CJK (check 9) ──────────────────────────────────────────────


def test_A_multi_cjk_all_failing_indices_collected():
    """A 5-cue file with 3 CJK-leaking cues raises ONE GateError(check=9)
    with failing_indices containing all three indices (sorted).

    5-cue SubDoc layout (0-based):
      0: clean VI  — "Xin chào bạn"
      1: CJK leak  — "你好 các bạn"        ← fails check 9
      2: clean VI  — "Tôi rất khỏe"
      3: CJK leak  — "修真 người tu"        ← fails check 9
      4: CJK leak  — "안녕 thôi"            ← fails check 9

    Expected AFTER fix: GateError(check=9, failing_indices=[1, 3, 4]).
    Before the fix: GateError raised with failing_indices=[1] only (first hit).
    """
    import pytest
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    trn_lines = [
        _make_line(0, text="Xin chào bạn"),
        _make_line(1, text="你好 các bạn"),      # CJK leak — index 1
        _make_line(2, text="Tôi rất khỏe"),
        _make_line(3, text="修真 người tu"),     # CJK leak — index 3
        _make_line(4, text="안녕 thôi"),          # Hangul leak — index 4
    ]
    src_lines = [
        _make_line(0, text="Hello there"),
        _make_line(1, text="Hello world"),
        _make_line(2, text="I am fine"),
        _make_line(3, text="Cultivation energy"),
        _make_line(4, text="Goodbye now"),
    ]
    trn = _make_doc(trn_lines)
    src = _make_doc(src_lines)

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())

    failure = ei.value.failure
    assert failure.check == 9, f"Expected check=9, got check={failure.check}"
    assert sorted(failure.failing_indices) == [1, 3, 4], (
        f"Expected all three failing indices [1, 3, 4], got {failure.failing_indices!r}"
    )


# ── Test B — mixed check 9 + check 10 (check-9 priority) ─────────────────────


def test_B_mixed_check9_and_check10_check9_wins():
    """A file with both check-9 and check-10 failures raises check-9 (priority).

    6-cue layout (0-based) — 4 VI cues keep the Check-3 ratio at 4/6 ≈ 0.67
    which is just under threshold; use 5 VI + 1 CJK + 1 passthrough (7 total):
      0: CJK leak  — "修真者 thôi"              ← fails check 9
      1: clean VI  — "Xin chào bạn"
      2: verbatim English passthrough — "Go go" ← fails check 10 (2 tokens, in source)
      3: clean VI  — "Tôi rất khỏe"
      4: clean VI  — "Cảm ơn nhiều"
      5: clean VI  — "Hẹn gặp lại sau"
      6: clean VI  — "Chào buổi sáng"

    7 cues total: 5 VI (indices 1,3,4,5,6), 1 CJK (0), 1 passthrough (2).
    Translatable cues = all 7 (no ALLOWLIST_RE matches since "Go go" has letters).
    Check 3 denominator = 7; VI diacritic cues = 5; ratio = 5/7 ≈ 0.714 ≥ 0.70 → passes.

    Expected AFTER fix: GateError(check=9, failing_indices=[0]).
    Check 9 takes priority over check 10.
    Before the fix: GateError raised with failing_indices=[0] on check 9 (same result
    in this specific case since check-9 fires first), but FAILS because test B specifically
    verifies that check-9 priority is correct even when check-10 failures are also present.
    The RED failure comes from Test A which demonstrates the multi-index collection gap.
    """
    import pytest
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    trn_lines = [
        _make_line(0, text="修真者 thôi"),          # CJK leak — index 0
        _make_line(1, text="Xin chào bạn"),
        _make_line(2, text="Go go"),                 # verbatim passthrough — index 2
        _make_line(3, text="Tôi rất khỏe"),
        _make_line(4, text="Cảm ơn nhiều"),
        _make_line(5, text="Hẹn gặp lại sau"),
        _make_line(6, text="Chào buổi sáng"),
    ]
    src_lines = [
        _make_line(0, text="Cultivation energy"),
        _make_line(1, text="Hello friend"),
        _make_line(2, text="Go go"),                 # same tokens → check 10 trigger
        _make_line(3, text="I am fine"),
        _make_line(4, text="Thanks a lot"),
        _make_line(5, text="See you later"),
        _make_line(6, text="Good morning"),
    ]
    trn = _make_doc(trn_lines)
    src = _make_doc(src_lines)

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())

    failure = ei.value.failure
    assert failure.check == 9, (
        f"check-9 must win over check-10, got check={failure.check}"
    )
    assert sorted(failure.failing_indices) == [0], (
        f"Expected failing_indices=[0], got {failure.failing_indices!r}"
    )


# ── Test C — multi-check-10 only ──────────────────────────────────────────────


def test_C_multi_check10_all_indices_collected():
    """A file with only check-10 failures raises GateError(check=10) with all indices.

    7-cue layout (0-based) — 5 VI cues to keep Check-3 ratio at 5/7 ≈ 0.714 ≥ 0.70:
      0: verbatim English passthrough  — "I am here"   ← fails check 10
      1: clean VI                      — "Xin chào bạn"
      2: verbatim English passthrough  — "Go away now"  ← fails check 10
      3: clean VI                      — "Tôi rất khỏe"
      4: clean VI                      — "Cảm ơn nhiều"
      5: clean VI                      — "Hẹn gặp lại sau"
      6: clean VI                      — "Chào buổi sáng"

    7 cues: 5 VI (indices 1,3,4,5,6), 2 passthrough (0,2).
    Translatable cues = 7 (passthrough cues have ASCII letters, not ALLOWLIST_RE).
    VI diacritic cues = 5; ratio = 5/7 ≈ 0.714 ≥ 0.70 → Check-3 passes.

    Source cues carry the same tokens for cues 0 and 2 so all_in_source fires.
    No CJK, no honorific bigrams, no gloss parens.

    Expected AFTER fix: GateError(check=10, failing_indices=[0, 2]).
    Before the fix: GateError raised with failing_indices=[0] only.
    """
    import pytest
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    trn_lines = [
        _make_line(0, text="I am here"),           # verbatim — index 0
        _make_line(1, text="Xin chào bạn"),
        _make_line(2, text="Go away now"),          # verbatim — index 2
        _make_line(3, text="Tôi rất khỏe"),
        _make_line(4, text="Cảm ơn nhiều"),
        _make_line(5, text="Hẹn gặp lại sau"),
        _make_line(6, text="Chào buổi sáng"),
    ]
    src_lines = [
        _make_line(0, text="I am here"),            # same → all_in_source True
        _make_line(1, text="Hello friend"),
        _make_line(2, text="Go away now"),           # same → all_in_source True
        _make_line(3, text="I am fine"),
        _make_line(4, text="Thanks a lot"),
        _make_line(5, text="See you later"),
        _make_line(6, text="Good morning"),
    ]
    trn = _make_doc(trn_lines)
    src = _make_doc(src_lines)

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())

    failure = ei.value.failure
    assert failure.check == 10, f"Expected check=10, got check={failure.check}"
    assert sorted(failure.failing_indices) == [0, 2], (
        f"Expected failing_indices=[0, 2], got {failure.failing_indices!r}"
    )


# ── Test D — single failing cue regression (must pass before AND after) ───────


def test_D_single_failing_cue_regression():
    """Regression guard: a single CJK-leaking cue still raises GateError with failing_indices=[2].

    4-cue layout (0-based):
      0: clean VI  — "Xin chào bạn"
      1: clean VI  — "Tôi rất khỏe"
      2: CJK leak  — "修真 người tu"    ← only failing cue
      3: clean VI  — "Cảm ơn nhiều"

    This test MUST PASS both before and after the refactor.
    If it fails on current code, there is a pre-existing bug — stop and surface it.
    """
    import pytest
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    trn_lines = [
        _make_line(0, text="Xin chào bạn"),
        _make_line(1, text="Tôi rất khỏe"),
        _make_line(2, text="修真 người tu"),    # CJK leak — index 2
        _make_line(3, text="Cảm ơn nhiều"),
    ]
    src_lines = [
        _make_line(0, text="Hello there"),
        _make_line(1, text="I am fine"),
        _make_line(2, text="Cultivation energy"),
        _make_line(3, text="Thank you much"),
    ]
    trn = _make_doc(trn_lines)
    src = _make_doc(src_lines)

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())

    failure = ei.value.failure
    assert failure.check == 9, f"Expected check=9, got check={failure.check}"
    assert failure.failing_indices == [2], (
        f"Expected failing_indices=[2], got {failure.failing_indices!r}"
    )


# ── Test E — multi-check-11 ────────────────────────────────────────────────────


def test_E_multi_check11_all_indices_collected():
    """A file with 2 check-11 (honorific+name bigram) failures collects both indices.

    4-cue layout (0-based):
      0: clean VI  — "Xin chào bạn"
      1: honorific — "Miss Mei, tạm biệt."    ← fails check 11
      2: clean VI  — "Tôi rất khỏe"
      3: honorific — "Elder Zhao đến rồi."    ← fails check 11

    Expected AFTER fix: GateError(check=11, failing_indices=[1, 3]).
    Before the fix: GateError raised with failing_indices=[1] only.

    Note: "tạm biệt" and "đến rồi" carry VN diacritics so check 10 is skipped for
    these cues; check 11 fires because HONORIFIC_CAPNAME_RE matches the bigram.
    HONORIFIC_CAPNAME_RE word list: Mr, Mrs, Ms, Miss, Sir, Elder, Brother, Sister,
    Master, Lord, Lady — "Doctor" is NOT in the list; use "Elder" instead.
    """
    import pytest
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    trn_lines = [
        _make_line(0, text="Xin chào bạn"),
        _make_line(1, text="Miss Mei, tạm biệt."),     # check 11 — index 1
        _make_line(2, text="Tôi rất khỏe"),
        _make_line(3, text="Elder Zhao đến rồi."),     # check 11 — index 3
    ]
    src_lines = [
        _make_line(0, text="Hello friend"),
        _make_line(1, text="Miss Mei goodbye"),
        _make_line(2, text="I am fine"),
        _make_line(3, text="Elder Zhao has arrived"),
    ]
    trn = _make_doc(trn_lines)
    src = _make_doc(src_lines)

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())

    failure = ei.value.failure
    assert failure.check == 11, f"Expected check=11, got check={failure.check}"
    assert sorted(failure.failing_indices) == [1, 3], (
        f"Expected failing_indices=[1, 3], got {failure.failing_indices!r}"
    )


# ── Test F — multi-check-12 ────────────────────────────────────────────────────


def test_F_multi_check12_all_indices_collected():
    """A file with 2 check-12 (English-gloss parenthetical) failures collects both indices.

    4-cue layout (0-based):
      0: gloss paren — "Được rồi (Miss Mei's idea)."   ← fails check 12
      1: clean VI    — "Xin chào bạn"
      2: gloss paren — "Tốt thôi (Han's brother)."     ← fails check 12
      3: clean VI    — "Tôi rất khỏe"

    The gloss parentheticals carry a possessive ('s) — the English-gloss signal.
    Cues 0 and 2 carry VN diacritics (ữ, ồ, ốt) so check 10 is skipped.
    Check 11 HONORIFIC_CAPNAME_RE does NOT match (no honorific word in outer text).
    Check 12 fires first on the GLOSS_PAREN_RE possessive trigger.

    Expected AFTER fix: GateError(check=12, failing_indices=[0, 2]).
    Before the fix: GateError raised with failing_indices=[0] only.
    """
    import pytest
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    GateError = validate_mod.GateError
    validate_subdoc = validate_mod.validate_subdoc

    trn_lines = [
        _make_line(0, text="Được rồi (Miss Mei's idea)."),   # check 12 — index 0
        _make_line(1, text="Xin chào bạn"),
        _make_line(2, text="Tốt thôi (Han's brother)."),     # check 12 — index 2
        _make_line(3, text="Tôi rất khỏe"),
    ]
    src_lines = [
        _make_line(0, text="Okay (Miss Mei's idea)."),
        _make_line(1, text="Hello friend"),
        _make_line(2, text="Good (Han's brother)."),
        _make_line(3, text="I am fine"),
    ]
    trn = _make_doc(trn_lines)
    src = _make_doc(src_lines)

    with pytest.raises(GateError) as ei:
        validate_subdoc(trn, src, _settings())

    failure = ei.value.failure
    assert failure.check == 12, f"Expected check=12, got check={failure.check}"
    assert sorted(failure.failing_indices) == [0, 2], (
        f"Expected failing_indices=[0, 2], got {failure.failing_indices!r}"
    )
