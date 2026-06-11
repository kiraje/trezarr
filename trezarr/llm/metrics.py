"""Per-pass LLM performance metrics (260612-1tm step-0 observability).

Provides a lightweight, log-only accumulator for tracking per-pass timing
and token usage in the translation pipeline.  No schema change, no DB table.

Design decisions:
  - PassMetrics is a frozen dataclass (immutable snapshot returned by summary()).
  - PassStatsCollector is a mutable plain class accumulating per-call data.
  - Uses only stdlib (dataclasses) — no new dependencies.
  - Thread-safety: asyncio is single-threaded; concurrent coroutines cannot
    interleave record() calls (D-06 semaphore bounds concurrent LLM calls).
  - None-safe: SDK responses with usage=None silently contribute 0 tokens.

Trust boundary (T-1tm-01): log lines contain only numeric durations and token
counts — no PII, no prompt content, no API keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PassMetrics:
    """Immutable snapshot of accumulated per-pass LLM call statistics.

    All fields default to zero so an empty collector's summary() is safe to log.

    Fields:
        call_count:       Number of LLM calls recorded.
        total_duration_s: Sum of wall-clock durations (seconds) for all calls.
        prompt_tokens:    Sum of prompt tokens from response.usage (0 if usage missing).
        completion_tokens: Sum of completion tokens from response.usage (0 if usage missing).
        retry_count:      Sum of retry counts (reserved for future use; SDK retries are opaque).
    """

    call_count: int = 0
    total_duration_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retry_count: int = 0


class PassStatsCollector:
    """Mutable accumulator for per-call LLM performance data.

    One instance per pass per translate_file() invocation.  Not shared across
    files — each invocation creates fresh instances, so there is no global state.

    Usage::

        col = PassStatsCollector()
        # ... around each LLM call:
        _t0 = time.perf_counter()
        resp = await llm_client.call(messages, collector=col)
        # (collector.record() called inside LLMClient._call_with_fallback)
        m = col.summary()
        logger.info("pass=3 calls=%d tokens=%d", m.call_count, m.prompt_tokens)
    """

    def __init__(self) -> None:
        self._call_count: int = 0
        self._total_duration_s: float = 0.0
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._retry_count: int = 0

    def record(
        self,
        duration_s: float,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        retries: int = 0,
    ) -> None:
        """Record metrics for a single completed LLM call.

        Args:
            duration_s:         Wall-clock duration of the raw SDK call (seconds).
            prompt_tokens:      Prompt token count from response.usage; None treated as 0.
            completion_tokens:  Completion token count from response.usage; None treated as 0.
            retries:            SDK-level retry count (always 0 — SDK retries are opaque;
                                field present for future instrumentation).
        """
        self._call_count += 1
        self._total_duration_s += duration_s
        self._prompt_tokens += prompt_tokens or 0
        self._completion_tokens += completion_tokens or 0
        self._retry_count += retries

    def summary(self) -> PassMetrics:
        """Return an immutable snapshot of the accumulated statistics."""
        return PassMetrics(
            call_count=self._call_count,
            total_duration_s=self._total_duration_s,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            retry_count=self._retry_count,
        )
