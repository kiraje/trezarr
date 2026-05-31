"""RED test stubs for ENG-02: batch-packing algorithm in trezarr.translate.batching.

All imports from trezarr.translate.batching are deferred inside each test function body
so pytest collection succeeds even when the implementation module does not yet exist.
Tests skip cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Covers:
  ENG-02 — Token budget respected (no batch exceeds char budget)
  ENG-02 — Scene-gap boundary triggers batch split
  ENG-02 — Max-cue-per-batch cap enforced when no scene gap
  ENG-02 — Single cue exceeding budget emitted as one-cue batch (not skipped/raised)
  ENG-02 — context_before and context_after populated with K neighbor lines
"""
import pytest


def _make_line(index: int, start_ms: int = 0, end_ms: int = 1000, text: str = "Hello") -> object:
    """Helper: construct a SubLine using deferred import. Returns SubLine or None."""
    from trezarr.subtitles.model import SubLine  # always available after Phase 1
    h_s, m_s, s_s, ms_s = start_ms // 3600000, (start_ms % 3600000) // 60000, (start_ms % 60000) // 1000, start_ms % 1000
    h_e, m_e, s_e, ms_e = end_ms // 3600000, (end_ms % 3600000) // 60000, (end_ms % 60000) // 1000, end_ms % 1000
    return SubLine(
        index=str(index),
        start_tc=f"{h_s:02d}:{m_s:02d}:{s_s:02d},{ms_s:03d}",
        end_tc=f"{h_e:02d}:{m_e:02d}:{s_e:02d},{ms_e:03d}",
        text=text,
    )


def _make_doc(lines: list) -> object:
    """Helper: construct a SubDoc using deferred import."""
    from trezarr.subtitles.model import SubDoc
    return SubDoc(
        lines=lines,
        encoding="utf-8",
        line_ending="\n",
        separators=["\n\n"] * max(0, len(lines) - 1),
        leading="",
        trailer="\n",
    )


def test_token_budget_respected():
    """No batch exceeds the char budget computed from TrezarrSettings defaults (ENG-02).

    Construct a SubDoc with enough SubLines to force multiple batches and assert
    every batch's total len(cue.text) <= budget.
    """
    batching = pytest.importorskip("trezarr.translate.batching")
    from trezarr.config import TrezarrSettings

    batch_subdoc = batching.batch_subdoc

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
        translate_max_cues_per_batch=100,  # large cap so budget binds, not cue cap
    )

    # Compute expected budget using same formula as implementation
    budget_chars = int(
        (settings.llm_context_window * (1 - settings.translate_overhead_fraction))
        / (1 + settings.translate_output_expansion)
        * settings.translate_chars_per_token
    )

    # Each cue text is 80 chars; create enough cues to fill more than one budget
    cue_text = "A" * 80
    n_cues = (budget_chars // 80) + 5  # enough to overflow into a second batch
    lines = [
        _make_line(i + 1, start_ms=i * 500, end_ms=(i + 1) * 500 - 100, text=cue_text)
        for i in range(n_cues)
    ]
    doc = _make_doc(lines)

    batches = batch_subdoc(doc, settings)

    assert len(batches) >= 2, "Expected at least 2 batches when budget is exceeded"
    for batch in batches:
        total_chars = sum(len(cue.text) for cue in batch.cues)
        # Allow single-cue batches to exceed budget (single-cue-never-split rule)
        if len(batch.cues) > 1:
            assert total_chars <= budget_chars, (
                f"Batch with {len(batch.cues)} cues exceeded budget: "
                f"{total_chars} > {budget_chars}"
            )


def test_scene_gap_boundary():
    """A time gap >= translate_scene_gap_ms triggers a batch split (ENG-02).

    Construct two SubLines whose gap >= 2000ms and assert they land in different batches.
    """
    batching = pytest.importorskip("trezarr.translate.batching")
    from trezarr.config import TrezarrSettings

    batch_subdoc = batching.batch_subdoc

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
        translate_scene_gap_ms=2000,
        translate_max_cues_per_batch=100,
    )

    # Two lines with a 3000ms gap between them (end of line1=1000ms, start of line2=4000ms)
    line1 = _make_line(1, start_ms=0, end_ms=1000, text="Line before gap")
    line2 = _make_line(2, start_ms=4000, end_ms=5000, text="Line after gap")
    doc = _make_doc([line1, line2])

    batches = batch_subdoc(doc, settings)

    assert len(batches) == 2, f"Expected 2 batches (scene gap split), got {len(batches)}"
    assert len(batches[0].cues) == 1
    assert batches[0].cues[0].text == "Line before gap"
    assert len(batches[1].cues) == 1
    assert batches[1].cues[0].text == "Line after gap"


def test_max_cue_fallback():
    """translate_max_cues_per_batch is enforced when no scene gap exists (ENG-02).

    Construct (max_cues + 1) SubLines with no gaps and assert they produce 2 batches.
    """
    batching = pytest.importorskip("trezarr.translate.batching")
    from trezarr.config import TrezarrSettings

    batch_subdoc = batching.batch_subdoc

    max_cues = 5  # small cap to keep the test fast
    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
        translate_max_cues_per_batch=max_cues,
        translate_scene_gap_ms=9999999,  # effectively disable scene-gap splits
    )

    # (max_cues + 1) lines packed closely together (100ms apart, no 10s gap)
    lines = [
        _make_line(i + 1, start_ms=i * 200, end_ms=(i + 1) * 200 - 50, text=f"Cue {i+1}")
        for i in range(max_cues + 1)
    ]
    doc = _make_doc(lines)

    batches = batch_subdoc(doc, settings)

    assert len(batches) == 2, (
        f"Expected 2 batches when {max_cues+1} cues exceed max_cues={max_cues}, "
        f"got {len(batches)}"
    )
    assert len(batches[0].cues) == max_cues
    assert len(batches[1].cues) == 1


def test_single_cue_never_split():
    """A single cue that exceeds the token budget is emitted as a one-cue batch (ENG-02).

    The single cue must not be skipped or raise an exception.
    """
    batching = pytest.importorskip("trezarr.translate.batching")
    from trezarr.config import TrezarrSettings

    batch_subdoc = batching.batch_subdoc

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
        # Tiny context window forces budget = tiny
        llm_context_window=100,
        translate_chars_per_token=3.5,
        translate_overhead_fraction=0.30,
        translate_output_expansion=1.40,
        translate_max_cues_per_batch=50,
    )

    # A single cue with far more text than the minuscule budget
    big_cue = _make_line(1, start_ms=0, end_ms=5000, text="X" * 500)
    doc = _make_doc([big_cue])

    import warnings
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        batches = batch_subdoc(doc, settings)

    assert len(batches) == 1, f"Expected 1 batch for single oversized cue, got {len(batches)}"
    assert len(batches[0].cues) == 1
    assert batches[0].cues[0].text == "X" * 500


def test_context_before_after_attached():
    """Batch objects have context_before and context_after populated (ENG-02 / D-15).

    K = translate_context_lines_k lines from the source doc are attached as
    read-only neighbor lines before and after each batch.
    """
    batching = pytest.importorskip("trezarr.translate.batching")
    from trezarr.config import TrezarrSettings

    batch_subdoc = batching.batch_subdoc

    k = 2
    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
        translate_context_lines_k=k,
        translate_max_cues_per_batch=2,   # force a 2-batch split
        translate_scene_gap_ms=9999999,  # disable scene-gap splits
    )

    # 4 lines → 2 batches of 2 each
    lines = [
        _make_line(i + 1, start_ms=i * 200, end_ms=(i + 1) * 200 - 50, text=f"Line {i+1}")
        for i in range(4)
    ]
    doc = _make_doc(lines)

    batches = batch_subdoc(doc, settings)

    assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}"

    # First batch: no context_before (starts at doc beginning), context_after = up to k lines
    assert hasattr(batches[0], "context_before"), "Batch missing context_before attribute"
    assert hasattr(batches[0], "context_after"), "Batch missing context_after attribute"
    assert len(batches[0].context_before) == 0, "First batch should have no context_before"
    assert len(batches[0].context_after) <= k, (
        f"context_after should have at most {k} lines, got {len(batches[0].context_after)}"
    )

    # Second batch: context_before = up to k lines from end of first batch
    assert len(batches[1].context_before) <= k, (
        f"context_before should have at most {k} lines, got {len(batches[1].context_before)}"
    )
    assert len(batches[1].context_after) == 0, "Last batch should have no context_after"
