"""Gate allowlist extension tests for karaoke, drawing, and tag-only cues (D-102).

Covers:
  D-102 — Karaoke cue (SubLine.raw set) does not raise GateError at check 3
  D-102 — Drawing cue (SubLine.raw set) does not raise GateError at check 3
  D-102 — Pure-tag cue (text = '<<T0>><<T1>>') matches SENTINEL_ONLY_RE and is skipped
  D-102 — Check 2 (no empty text) does not raise for raw-set SubLine with original text
"""
import pytest


# ---------------------------------------------------------------------------
# Helpers (copied from test_validate.py to avoid cross-module state coupling)
# ---------------------------------------------------------------------------


def _make_line(
    index: int,
    start_tc: str = "00:00:01,000",
    end_tc: str = "00:00:03,000",
    text: str = "Xin chào",
    raw: str | None = None,
) -> object:
    """Helper: construct a SubLine, optionally with .raw set (for karaoke/drawing cues)."""
    from trezarr.subtitles.model import SubLine
    sl = SubLine(index=str(index), start_tc=start_tc, end_tc=end_tc, text=text)
    if raw is not None:
        sl.raw = raw
    return sl


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


# ---------------------------------------------------------------------------
# Allowlist tests
# ---------------------------------------------------------------------------


def test_karaoke_cue_allowlisted():
    r"""Karaoke SubLine (raw set) must pass check 3 without GateError (D-102 / D-99).

    The gate's _check_untranslated must skip SubLines where raw is not None.
    Without this, a karaoke cue like '{\k50}syl{\k60}la' has no Vietnamese diacritics
    and trips check 3 (VI diacritic ratio too low) → false-quarantine.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc
    GateError = validate_mod.GateError

    karaoke_text = r"{\k50}syl{\k60}la{\k70}ble"

    # Both source and translated have the same karaoke cue (verbatim pass-through).
    src_line = _make_line(1, text=karaoke_text, raw=karaoke_text)
    trn_line = _make_line(1, text=karaoke_text, raw=karaoke_text)

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    # Should NOT raise GateError — karaoke cue is allowlisted.
    try:
        result = validate_subdoc(trn, src, _settings())
    except GateError as exc:
        pytest.fail(
            f"validate_subdoc raised GateError for karaoke cue (should be allowlisted): {exc}"
        )


def test_drawing_cue_allowlisted():
    r"""Drawing-run SubLine (raw set) must pass check 3 without GateError (D-102 / D-98).

    The gate's _check_untranslated must skip SubLines where raw is not None.
    Without this, a drawing cue like '{\p1}m 0 0 l 100 100{\p0}' trips check 3.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc
    GateError = validate_mod.GateError

    drawing_text = r"{\p1}m 0 0 l 100 0 100 100 0 100{\p0}"

    src_line = _make_line(1, text=drawing_text, raw=drawing_text)
    trn_line = _make_line(1, text=drawing_text, raw=drawing_text)

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    try:
        validate_subdoc(trn, src, _settings())
    except GateError as exc:
        pytest.fail(
            f"validate_subdoc raised GateError for drawing cue (should be allowlisted): {exc}"
        )


def test_pure_tag_cue_allowlisted():
    """SubLine.text = '<<T0>><<T1>>' (pure sentinel tokens) must be allowlisted at check 3 (D-102).

    After sentinel extraction, a cue that was entirely override tags has no natural
    language content — its cleaned text is only <<TN>> tokens. SENTINEL_ONLY_RE
    matches this and excludes it from the VI diacritic ratio denominator.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc
    GateError = validate_mod.GateError

    # Simulate post-sentinel-extraction text: only <<TN>> tokens remain.
    sentinel_only_text = "<<T0>><<T1>>"

    src_line = _make_line(1, text=sentinel_only_text)
    trn_line = _make_line(1, text=sentinel_only_text)

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    try:
        validate_subdoc(trn, src, _settings())
    except GateError as exc:
        # Only allowlist failures are unexpected; other checks may still legitimately fire.
        if exc.failure.check == 3:
            pytest.fail(
                f"validate_subdoc raised GateError(check=3) for pure-sentinel-token cue "
                f"(should match SENTINEL_ONLY_RE): {exc}"
            )


def test_check2_skips_raw_lines():
    """Check 2 (no empty text) must not raise for a raw-set SubLine with non-empty text (D-102).

    For karaoke/drawing cues, SubLine.raw = original_text AND SubLine.text = original_text.
    Check 2 asserts text.strip() is not empty — this must pass because .text is set
    to the non-empty original. This test confirms that contract.
    """
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    validate_subdoc = validate_mod.validate_subdoc
    GateError = validate_mod.GateError

    karaoke_text = r"{\k50}syl{\k60}la"

    src_line = _make_line(1, text=karaoke_text, raw=karaoke_text)
    # Translated line also has raw set (verbatim pass-through).
    trn_line = _make_line(1, text=karaoke_text, raw=karaoke_text)

    src = _make_doc([src_line])
    trn = _make_doc([trn_line])

    try:
        validate_subdoc(trn, src, _settings())
    except GateError as exc:
        if exc.failure.check == 2:
            pytest.fail(
                f"validate_subdoc raised GateError(check=2) for raw-set SubLine with "
                f"non-empty text (check 2 should pass): {exc}"
            )
