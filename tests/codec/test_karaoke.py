"""Wave 0 RED stubs: karaoke verbatim pass-through tests (D-99 / FMT-03).

All tests are xfail stubs — the implementation (trezarr.subtitles.ass) does not
yet exist. Tests will go GREEN in Wave 2.

Covers:
  D-99 / FMT-03 — Karaoke cue SubLine.raw is set to the original Text field
  D-99 / FMT-03 — Karaoke cue does not appear in the LLM translation batch
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
def test_karaoke_text_is_raw():
    r"""karaoke.ass: SubLine for the karaoke cue must have raw set to the original Text (D-99).

    When the codec detects \k / \kf / \K / \ko / \kt in the Text field, it marks
    the entire cue as a verbatim pass-through by setting SubLine.raw = original_text.
    The LLM never sees this cue.
    """
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass

    src = FIXTURES / "karaoke.ass"
    doc = read_ass(str(src))

    karaoke_lines = [sl for sl in doc.lines if sl.raw is not None]
    assert len(karaoke_lines) >= 1, (
        "Expected at least one SubLine with raw set (karaoke cue) in karaoke.ass"
    )
    # The raw value must equal the text value (both set to the original Text field).
    for sl in karaoke_lines:
        assert sl.raw == sl.text, (
            f"Expected SubLine.raw == SubLine.text for karaoke cue, "
            f"got raw={sl.raw!r}, text={sl.text!r}"
        )
    # The raw value must contain the karaoke tag pattern.
    assert any(r"\k" in sl.raw for sl in karaoke_lines), (
        r"Expected karaoke SubLine.raw to contain \k tag"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
def test_karaoke_not_in_llm_batch():
    r"""Karaoke SubLine (raw set) must not appear in any translate batch (D-99 / FMT-03).

    batch_subdoc filters out SubLines where raw is set — these are opaque
    pass-through cues that are never sent to the LLM.
    """
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    batching_mod = pytest.importorskip("trezarr.translate.batching")
    read_ass = ass_mod.read_ass
    batch_subdoc = batching_mod.batch_subdoc

    src = FIXTURES / "karaoke.ass"
    sub_doc = read_ass(str(src))

    # batch_subdoc takes a SubDoc and settings; use minimal settings.
    from trezarr.config import TrezarrSettings
    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
    )

    batches = batch_subdoc(sub_doc, settings)

    # Gather all SubLines that appear in any batch.
    batched_texts = []
    for batch in batches:
        batched_texts.extend([sl.text for sl in batch.lines])

    # No karaoke cue should appear in any batch.
    karaoke_lines = [sl for sl in sub_doc.lines if sl.raw is not None]
    for kl in karaoke_lines:
        assert kl.text not in batched_texts, (
            f"Karaoke SubLine with raw set appeared in LLM batch: {kl.text!r}"
        )
