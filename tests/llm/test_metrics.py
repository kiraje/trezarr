"""TDD tests for PassMetrics dataclass and PassStatsCollector accumulator.

Task 1 (260612-1tm): step-0 per-pass timing + token observability.

Tests verify:
- PassStatsCollector zero-initializes correctly
- record() accumulates correctly after one call
- record() accumulates correctly after two calls
- PassMetrics is frozen (FrozenInstanceError on assignment)
- record() handles None prompt_tokens and completion_tokens as 0
"""
import pytest


async def test_empty_collector_returns_zero_metrics():
    """PassStatsCollector() with no records returns all-zero PassMetrics.

    Trust boundary: before any LLM call, the collector is empty.
    """
    from trezarr.llm.metrics import PassMetrics, PassStatsCollector  # noqa: PLC0415

    col = PassStatsCollector()
    m = col.summary()

    assert isinstance(m, PassMetrics)
    assert m.call_count == 0
    assert m.total_duration_s == 0.0
    assert m.prompt_tokens == 0
    assert m.completion_tokens == 0
    assert m.retry_count == 0


async def test_single_record_produces_correct_summary():
    """After one record(), summary() returns the correct per-field totals.

    Accumulates call_count=1, correct duration, token counts, zero retries.
    """
    from trezarr.llm.metrics import PassStatsCollector  # noqa: PLC0415

    col = PassStatsCollector()
    col.record(duration_s=1.5, prompt_tokens=100, completion_tokens=50, retries=0)
    m = col.summary()

    assert m.call_count == 1
    assert abs(m.total_duration_s - 1.5) < 1e-9
    assert m.prompt_tokens == 100
    assert m.completion_tokens == 50
    assert m.retry_count == 0


async def test_two_records_accumulate_correctly():
    """After two record() calls, summary() returns correctly summed totals.

    call_count=2, totals are the sum of both calls.
    """
    from trezarr.llm.metrics import PassStatsCollector  # noqa: PLC0415

    col = PassStatsCollector()
    col.record(duration_s=1.23, prompt_tokens=100, completion_tokens=50, retries=0)
    col.record(duration_s=0.77, prompt_tokens=80, completion_tokens=30, retries=1)
    m = col.summary()

    assert m.call_count == 2
    assert abs(m.total_duration_s - 2.0) < 1e-6
    assert m.prompt_tokens == 180
    assert m.completion_tokens == 80
    assert m.retry_count == 1


async def test_pass_metrics_is_frozen():
    """PassMetrics is a frozen dataclass — assignment to any field raises FrozenInstanceError."""
    from dataclasses import FrozenInstanceError  # noqa: PLC0415
    from trezarr.llm.metrics import PassMetrics  # noqa: PLC0415

    m = PassMetrics()
    with pytest.raises(FrozenInstanceError):
        m.call_count = 99  # type: ignore[misc]


async def test_record_none_tokens_treated_as_zero():
    """record() with None prompt_tokens and completion_tokens treats them as 0 (None-safe).

    Some SDK responses have usage=None; the collector must not fail or accumulate None.
    """
    from trezarr.llm.metrics import PassStatsCollector  # noqa: PLC0415

    col = PassStatsCollector()
    col.record(duration_s=0.5, prompt_tokens=None, completion_tokens=None)
    m = col.summary()

    assert m.call_count == 1
    assert m.prompt_tokens == 0
    assert m.completion_tokens == 0
    assert abs(m.total_duration_s - 0.5) < 1e-9
