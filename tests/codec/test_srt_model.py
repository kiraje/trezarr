"""Tests for SubLine and SubDoc model field semantics (FMT-01).

Verifies:
- SubLine.text is the only LLM-mutable field
- SubLine.index, .start_tc, .end_tc are preserved verbatim (no normalization)
"""
def test_subline_text_mutable():
    """SubLine.text field can be mutated in-place after construction."""
    from trezarr.subtitles.model import SubLine  # deferred import

    sl = SubLine(
        index="1",
        start_tc="00:00:01,000",
        end_tc="00:00:03,500",
        text="Original text",
    )
    sl.text = "Translated text"
    assert sl.text == "Translated text"


def test_subline_timing_fields_preserved():
    """SubLine index, start_tc, end_tc hold exactly the strings passed at construction.

    No normalization is applied — non-sequential indices, period-separator timecodes,
    and 2-digit milliseconds must all survive unchanged (D-08).
    """
    from trezarr.subtitles.model import SubLine  # deferred import

    # Non-sequential index + period separator + 2-digit ms
    sl = SubLine(
        index="42",
        start_tc="00:00:05.50",
        end_tc="00:00:07.00",
        text="Timing test",
    )
    assert sl.index == "42"
    assert sl.start_tc == "00:00:05.50"
    assert sl.end_tc == "00:00:07.00"
