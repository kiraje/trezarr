"""CR-02 (FMT-03) regression: Pass-4 self-review splice over interleaved raw cues.

batch_subdoc SKIPS raw-flagged (karaoke/drawing) cues, so review batches span
only the NON-raw cues. The splice must therefore map corrections to non-raw cues
only and pass raw cues through verbatim. The pre-fix code indexed the full line
list by a non-raw running offset, which overwrote raw pass-through slots and
shifted every subsequent cue — corrupting karaoke/drawing output whenever any raw
cue was present. Self-review is ENABLED by default (config.enable_self_review),
so this was a default-path bug, not an edge case.

These tests exercise `_splice_review_corrections` directly (no LLM/Bible mocking)
and would fail on the pre-fix offset-indexed implementation.
"""
from __future__ import annotations

from trezarr.config import TrezarrSettings
from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.translate.batching import Batch, batch_subdoc
from trezarr.translate.engine import _splice_review_corrections


def _line(idx: int, text: str, raw: str | None = None) -> SubLine:
    return SubLine(
        index=str(idx),
        start_tc="00:00:01,000",
        end_tc="00:00:02,000",
        text=text,
        raw=raw,
    )


def test_splice_preserves_interleaved_raw_cue_and_aligns_corrections():
    """A karaoke (raw) cue between two normal cues stays verbatim while
    corrections land on the correct non-raw cues."""
    normal0 = _line(1, "tr0")
    karaoke = _line(2, r"{\k50}ka{\k50}ra", raw=r"{\k50}ka{\k50}ra")  # raw → pass-through
    normal1 = _line(3, "tr1")
    translated_lines = [normal0, karaoke, normal1]

    # batch_subdoc excludes raw cues, so the review batch holds only the 2 normals.
    review_batches = [Batch(cues=[normal0, normal1])]
    review_results = [["CORR0", "CORR1"]]

    out = _splice_review_corrections(translated_lines, review_batches, review_results)

    assert len(out) == 3
    assert out[0].text == "CORR0", "first non-raw cue must receive its correction"
    # The karaoke cue MUST be untouched — same object, text and raw preserved.
    assert out[1] is karaoke, "raw cue must pass through verbatim (not overwritten)"
    assert out[1].raw == karaoke.raw
    assert out[1].text == karaoke.text
    # Pre-fix bug: this slot received "CORR1" overwriting karaoke, and CORR1 was
    # mis-indexed. Post-fix the correction aligns to the SECOND non-raw cue.
    assert out[2].text == "CORR1", "correction must align to the second non-raw cue"


def test_splice_none_batch_keeps_translated_text_and_raw():
    """A batch whose review returned None keeps the pre-review translated text;
    interleaved raw (drawing) cues still pass through verbatim."""
    normal0 = _line(1, "keep0")
    drawing = _line(2, r"{\p1}m 0 0 l 10 0{\p0}", raw=r"{\p1}m 0 0 l 10 0{\p0}")
    normal1 = _line(3, "keep1")

    out = _splice_review_corrections(
        [normal0, drawing, normal1],
        [Batch(cues=[normal0, normal1])],
        [None],  # review failed / no correction for this batch
    )

    assert [ln.text for ln in out] == ["keep0", r"{\p1}m 0 0 l 10 0{\p0}", "keep1"]
    assert out[1] is drawing
    assert out[1].raw == drawing.raw


def test_splice_aligned_with_real_batch_subdoc():
    """End-to-end: batch_subdoc skips the raw cue, and the splice realigns over
    the FULL document — independent of how batch_subdoc chunks the non-raw cues."""
    normal0 = _line(1, "tr0")
    karaoke = _line(2, r"{\k50}la", raw=r"{\k50}la")
    normal1 = _line(3, "tr1")
    doc = SubDoc(
        lines=[normal0, karaoke, normal1],
        encoding="utf-8",
        line_ending="\n",
        separators=["", ""],
    )
    settings = TrezarrSettings(
        llm_api_key="test-key",
        self_review_context_lines_k=0,
        self_review_max_cues_per_batch=10,
    )
    batches = batch_subdoc(
        doc, settings, context_lines_k=0, max_cues_per_batch=10,
    )

    all_cues = [c for b in batches for c in b.cues]
    assert karaoke not in all_cues, "batch_subdoc must skip the raw karaoke cue"
    assert len(all_cues) == 2

    # One correction per cue, in document order, robust to any batch splitting.
    review_results: list[list[str]] = []
    gi = 0
    for b in batches:
        review_results.append([f"C{gi + j}" for j in range(len(b.cues))])
        gi += len(b.cues)

    out = _splice_review_corrections(doc.lines, batches, review_results)

    assert out[1] is karaoke, "raw cue verbatim after real batch_subdoc + splice"
    assert out[0].text == "C0"
    assert out[2].text == "C1"
