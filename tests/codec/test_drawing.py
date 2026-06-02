"""Drawing-run verbatim pass-through tests (D-98 / FMT-02).

Covers:
  D-98 / FMT-02 — Drawing-run cue SubLine.raw is set to the original Text field
  D-98 / FMT-02 — Drawing-run cue does not appear in the LLM translation batch
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_drawing_run_is_raw():
    r"""drawing.ass: SubLine for {\p1}...{\p0} must have raw set to the original Text (D-98).

    When the codec detects {\pN} (N >= 1) in the Text field, it marks the entire
    cue as a verbatim pass-through by setting SubLine.raw = original_text.
    The drawing coordinate geometry must never be sent to the LLM.
    """
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass

    src = FIXTURES / "drawing.ass"
    doc = read_ass(str(src))

    drawing_lines = [sl for sl in doc.lines if sl.raw is not None]
    assert len(drawing_lines) >= 1, (
        "Expected at least one SubLine with raw set (drawing cue) in drawing.ass"
    )
    # The raw value must contain the drawing start tag.
    assert any(r"{\p1}" in sl.raw for sl in drawing_lines), (
        r"Expected drawing SubLine.raw to contain {\p1} drawing start tag"
    )
    # raw and text must be equal (both set to the original Text field, per D-98 / A7).
    for sl in drawing_lines:
        assert sl.raw == sl.text, (
            f"Expected SubLine.raw == SubLine.text for drawing cue, "
            f"got raw={sl.raw!r}, text={sl.text!r}"
        )


def test_drawing_run_not_in_llm_batch():
    r"""Drawing-run SubLine (raw set) must not appear in any translate batch (D-98 / FMT-02).

    batch_subdoc skips SubLines where raw is set — these are opaque
    pass-through cues that are never sent to the LLM.
    """
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    batching_mod = pytest.importorskip("trezarr.translate.batching")
    read_ass = ass_mod.read_ass
    batch_subdoc = batching_mod.batch_subdoc

    src = FIXTURES / "drawing.ass"
    sub_doc = read_ass(str(src))

    from trezarr.config import TrezarrSettings
    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
    )

    batches = batch_subdoc(sub_doc, settings)

    # Gather all texts across all batches.
    batched_texts = []
    for batch in batches:
        batched_texts.extend([sl.text for sl in batch.cues])

    # No drawing-run cue should appear in any batch.
    drawing_lines = [sl for sl in sub_doc.lines if sl.raw is not None]
    for dl in drawing_lines:
        assert dl.text not in batched_texts, (
            f"Drawing-run SubLine with raw set appeared in LLM batch: {dl.text!r}"
        )
