"""RED test stubs for D-12: sentinel extraction and reinsertion in trezarr.translate.sentinel.

All imports from trezarr.translate.sentinel are deferred inside each test function body
so pytest collection succeeds even when the implementation module does not yet exist.
Tests skip cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Covers:
  D-12 — Plain text returns unchanged text with empty sentinel_map
  D-12 — <i>word</i> tag is extracted; cleaned text contains <<T0>> not <i>
  D-12 — Multiple different tags each get a unique <<TN>> key
  D-12 — Extracted text reinserted returns original with integrity_ok=True
  D-12 — Sentinel removed from translated text (lost real tag) → integrity_ok=False
  v1.0 #5 — Hallucinated orphan sentinel (no map entry) → stripped, integrity_ok=True
  D-12 — ASS override tag {\an8} is extracted correctly
"""
import pytest


def test_extract_no_tags():
    """Plain text with no tags returns (text, {}) with empty sentinel_map (D-12)."""
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = "Hello, world!"
    cleaned, sentinel_map = extract_sentinels(text)

    assert cleaned == text, f"Expected text unchanged, got: {cleaned!r}"
    assert sentinel_map == {}, f"Expected empty sentinel_map, got: {sentinel_map}"


def test_extract_italic_tag():
    """Text with <i>word</i> extracts the tags into sentinel_map (D-12).

    The cleaned text must contain <<T0>> and <<T1>> (one per tag), not <i>.
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = "<i>Hello</i>"
    cleaned, sentinel_map = extract_sentinels(text)

    assert "<i>" not in cleaned, "Opening <i> tag should have been replaced by sentinel"
    assert "</i>" not in cleaned, "Closing </i> tag should have been replaced by sentinel"
    assert "<<T0>>" in cleaned, "First sentinel <<T0>> should be in cleaned text"
    assert len(sentinel_map) == 2, f"Expected 2 sentinels for <i> + </i>, got {len(sentinel_map)}"

    # Sentinel values must map back to the original tags
    assert "<i>" in sentinel_map.values(), "sentinel_map should contain '<i>' as a value"
    assert "</i>" in sentinel_map.values(), "sentinel_map should contain '</i>' as a value"


def test_extract_multiple_tags():
    """Multiple different tags each get a unique <<TN>> key (D-12).

    Each sentinel key must be unique and map to the correct original tag.
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels

    text = "<b>Bold</b> and <i>italic</i>"
    cleaned, sentinel_map = extract_sentinels(text)

    assert "<b>" not in cleaned
    assert "</b>" not in cleaned
    assert "<i>" not in cleaned
    assert "</i>" not in cleaned

    # Should have 4 unique sentinel keys (<<T0>>, <<T1>>, <<T2>>, <<T3>>)
    assert len(sentinel_map) == 4, (
        f"Expected 4 unique sentinels for <b>, </b>, <i>, </i>, got {len(sentinel_map)}"
    )
    # All keys are unique
    assert len(set(sentinel_map.keys())) == len(sentinel_map.keys())
    # All sentinel keys match the <<TN>> pattern
    import re
    sentinel_pattern = re.compile(r"^<<T\d+>>$")
    for key in sentinel_map.keys():
        assert sentinel_pattern.match(key), f"Sentinel key {key!r} does not match <<TN>> format"


def test_reinsert_round_trips():
    """Extracted text reinserted returns original text with integrity_ok=True (D-12)."""
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels
    reinsert_sentinels = sentinel_mod.reinsert_sentinels

    original = "<i>Xin chào</i>, <b>bạn ơi</b>!"
    cleaned, sentinel_map = extract_sentinels(original)

    # Simulate: model "translates" the cleaned text but preserves <<TN>> tokens
    restored, integrity_ok = reinsert_sentinels(cleaned, sentinel_map)

    assert integrity_ok is True, f"Expected integrity_ok=True on clean round-trip, got False"
    assert restored == original, (
        f"Expected round-trip to restore original text.\n"
        f"  original: {original!r}\n"
        f"  restored: {restored!r}"
    )


def test_reinsert_missing_sentinel():
    """If <<T0>> is removed from translated text before reinsert, integrity_ok=False (D-12).

    Simulates the LLM dropping a sentinel token.
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels
    reinsert_sentinels = sentinel_mod.reinsert_sentinels

    original = "<i>Hello</i>"
    cleaned, sentinel_map = extract_sentinels(original)

    # Simulate model stripping the first sentinel
    # cleaned looks like "<<T0>>Hello<<T1>>"
    # Remove the first sentinel from the "translated" text
    first_key = next(iter(sentinel_map))
    mutated = cleaned.replace(first_key, "", 1)

    _, integrity_ok = reinsert_sentinels(mutated, sentinel_map)

    assert integrity_ok is False, (
        "Expected integrity_ok=False when a sentinel is missing from translated text"
    )


def test_reinsert_strips_hallucinated_orphan():
    """A <<TN>> with no sentinel_map entry is a hallucination — strip it, integrity_ok=True.

    v1.0 verification finding #5: the weak model invents <<TN>> tokens into
    untagged cues (empty sentinel_map). The old contract quarantined the whole
    file; the new contract strips the never-extracted token and keeps the
    otherwise-valid translation. A LOST REAL sentinel still fails
    (test_reinsert_missing_sentinel).
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    reinsert_sentinels = sentinel_mod.reinsert_sentinels

    # Empty sentinel_map so <<T0>> in the text is an orphan (never extracted).
    restored, integrity_ok = reinsert_sentinels("Hello <<T0>> world", {})

    assert integrity_ok is True, "hallucinated orphan must be stripped, not quarantined"
    assert "<<T0>>" not in restored, "orphan token must be removed"
    assert restored == "Hello world", f"expected clean strip, got {restored!r}"


def test_reinsert_strips_orphan_but_keeps_real_sentinel():
    """A real sentinel is restored AND a co-occurring hallucinated orphan is stripped."""
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    reinsert_sentinels = sentinel_mod.reinsert_sentinels

    # Map has one real tag (<<T0>> -> <i>); the model also hallucinated <<T1>>.
    restored, integrity_ok = reinsert_sentinels("<<T0>>Xin chào<<T1>>", {"<<T0>>": "<i>"})

    assert integrity_ok is True
    assert restored == "<i>Xin chào", f"real tag kept, orphan stripped; got {restored!r}"


def test_reinsert_lost_real_sentinel_still_fails():
    """A sentinel present in the map but missing from text is a LOST REAL tag → integrity_ok=False.

    This must NOT be confused with the orphan-strip path — a dropped real tag
    must still quarantine (we cannot emit output missing a real formatting tag).
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    reinsert_sentinels = sentinel_mod.reinsert_sentinels

    # Map expects <<T0>> but the translated text dropped it entirely.
    _, integrity_ok = reinsert_sentinels("Xin chào", {"<<T0>>": "<i>"})

    assert integrity_ok is False, "a lost real sentinel must still fail (not be silently dropped)"


def test_reinsert_never_deletes_source_lookalike_token():
    """A literal <<TN>>-shaped token in SOURCE text must NOT be silently deleted.

    Codec-fidelity BLOCKER guard: TAG_RE's `<[^>]+>` arm over-matches a literal
    "<<T1000>>" out of source, so it becomes a sentinel_map VALUE. The orphan
    strip must run BEFORE reinsertion (on raw model output, by key set-difference)
    so it never deletes that legitimately-restored content. Acceptable outcomes:
    round-trip (ideal) or quarantine (safe) — NEVER strip to "Designation approaching".
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels
    reinsert_sentinels = sentinel_mod.reinsert_sentinels

    original = "Designation <<T1000>> approaching"
    cleaned, smap = extract_sentinels(original)
    # Model returns the cleaned text verbatim (preserves the extracted token).
    restored, integrity_ok = reinsert_sentinels(cleaned, smap)

    assert restored != "Designation approaching", (
        "source content must never be silently stripped (the BLOCKER regression)"
    )
    if integrity_ok:
        assert "1000" in restored, "if it passes, the source token content must survive"


def test_extract_ass_override_tag():
    r"""Text with {\an8} extracts the ASS override tag correctly (D-12).

    ASS override tags have the form {\anX} or {\pos(x,y)} — matched by the
    TAG_RE pattern r'(<[^>]+>|\{\\[^}]+\})'.
    """
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels
    reinsert_sentinels = sentinel_mod.reinsert_sentinels

    text = r"{\an8}This is centered text"
    cleaned, sentinel_map = extract_sentinels(text)

    assert r"{\an8}" not in cleaned, r"ASS tag {\an8} should have been replaced by sentinel"
    assert len(sentinel_map) == 1, f"Expected exactly 1 sentinel for \\{{an8\\}}, got {len(sentinel_map)}"
    assert r"{\an8}" in sentinel_map.values(), r"sentinel_map should contain '{\an8}' as a value"

    # Round-trip integrity check
    restored, integrity_ok = reinsert_sentinels(cleaned, sentinel_map)
    assert integrity_ok is True
    assert restored == text
