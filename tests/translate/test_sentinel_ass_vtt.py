r"""Wave 0 RED stubs: sentinel extension tests for ASS and VTT inline tags (D-98 / D-100).

All tests are xfail stubs — the sentinel TAG_RE extension (\\N/\\n/\\h hard-breaks
and VTT voice/inline-timestamp tags) lands in Wave 1. The tests in this file verify
the EXTENDED sentinel behavior, not the already-implemented base behavior
(that is covered by tests/translate/test_sentinel.py).

Covers:
  D-98 — \\N (ASS hard line-break) is placeholder-protected, not in cleaned text
  D-98 — \\n (ASS soft line-break) is placeholder-protected
  D-98 — \\h (ASS non-breaking space) is placeholder-protected
  D-100 — <v Speaker> VTT voice annotation tag is placeholder-protected
  D-100 — <00:01:23.456> VTT inline timestamp tag is placeholder-protected
"""
import pytest


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="sentinel TAG_RE \\N/\\n/\\h extension not yet implemented (Wave 1)",
)
def test_extract_ass_hard_break():
    r"""\\N (ASS hard line-break) is extracted as a sentinel token, not left in cleaned text (D-98).

    After extraction, cleaned_text must contain <<TN>> but NOT the literal \\N sequence.
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = r"Line one\NLine two"
    cleaned, sentinel_map = extract_sentinels(text)

    assert r"\N" not in cleaned, (
        r"Expected \N to be replaced by a sentinel token, but it remains in cleaned text"
    )
    assert len(sentinel_map) >= 1, "Expected at least one sentinel for \\N"
    assert r"\N" in sentinel_map.values(), r"Expected sentinel_map to contain '\N' as a value"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="sentinel TAG_RE \\N/\\n/\\h extension not yet implemented (Wave 1)",
)
def test_extract_ass_lowercase_n():
    r"""\\n (ASS soft line-break) is extracted as a sentinel token (D-98)."""
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = r"Soft\nbreak here"
    cleaned, sentinel_map = extract_sentinels(text)

    assert r"\n" not in cleaned, (
        r"Expected \n to be replaced by a sentinel token"
    )
    assert r"\n" in sentinel_map.values(), r"Expected sentinel_map to contain '\n' as a value"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="sentinel TAG_RE \\N/\\n/\\h extension not yet implemented (Wave 1)",
)
def test_extract_ass_h():
    r"""\\h (ASS non-breaking space) is extracted as a sentinel token (D-98)."""
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = r"Non\hbreaking space"
    cleaned, sentinel_map = extract_sentinels(text)

    assert r"\h" not in cleaned, (
        r"Expected \h to be replaced by a sentinel token"
    )
    assert r"\h" in sentinel_map.values(), r"Expected sentinel_map to contain '\h' as a value"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="VTT <v> voice tag is already matched by existing TAG_RE <[^>]+>; "
           "this test documents the behavior and will pass when confirmed (Wave 1)",
)
def test_vtt_voice_tag():
    """<v Speaker Name> VTT voice annotation is extracted as a sentinel token (D-100).

    The existing TAG_RE arm <[^>]+> already matches <v Speaker Name>. This test
    documents and enforces that behavior.
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = "<v Alice>Hello there</v>"
    cleaned, sentinel_map = extract_sentinels(text)

    assert "<v Alice>" not in cleaned, "Expected <v Alice> to be replaced by sentinel"
    assert "<v Alice>" in sentinel_map.values(), (
        "Expected sentinel_map to contain '<v Alice>' as a value"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="VTT inline timestamp <00:01:23.456> is already matched by existing TAG_RE <[^>]+>; "
           "this test documents the behavior and will pass when confirmed (Wave 1)",
)
def test_vtt_inline_timestamp():
    """<00:01:23.456> VTT inline timestamp cue tag is extracted as a sentinel token (D-100).

    The existing TAG_RE arm <[^>]+> already matches inline timestamps. This test
    documents and enforces that behavior.
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = "Word <00:01:23.456> by word"
    cleaned, sentinel_map = extract_sentinels(text)

    assert "<00:01:23.456>" not in cleaned, (
        "Expected <00:01:23.456> to be replaced by a sentinel token"
    )
    assert "<00:01:23.456>" in sentinel_map.values(), (
        "Expected sentinel_map to contain '<00:01:23.456>' as a value"
    )
