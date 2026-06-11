"""LLMClient — AsyncOpenAI wrapper with semaphore and three-tier structured output (D-03/D-04/D-06/D-07).

Design decisions honoured:
  D-03  AsyncOpenAI with user-supplied base_url/api_key/model.
  D-04  Auto-detect degradation: json_schema → json_object → plain text.
        Pinned modes (json_schema|json_object|text) never fall back — they raise on failure.
  D-06  asyncio.Semaphore bounds concurrent in-flight LLM calls (default cap: 4).
  D-07  SDK max_retries=4 for exponential backoff; no external retry wrapper in this module.
  D-11  API key extracted ONLY in __init__ via SecretStr; key never stored as plain str;
        SecretStr masking enforced by TrezarrSettings.

Exception policy (Pitfall 7 in 01-RESEARCH.md):
  Catch ONLY openai.BadRequestError (400) and openai.UnprocessableEntityError (422) for tier
  fallback.  Do NOT catch the openai base exception class — that would intercept 429/5xx
  errors that the SDK is meant to retry, routing them to the wrong fallback tier.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

from trezarr.llm.metrics import PassStatsCollector

if TYPE_CHECKING:
    from ..config import TrezarrSettings


class LLMClient:
    """Async LLM client wrapping AsyncOpenAI with concurrency cap and tier-fallback logic.

    Usage::

        settings = TrezarrSettings()
        client = LLMClient(settings)
        result = await client.call(messages=[{"role": "user", "content": "..."}])
    """

    def __init__(self, settings: "TrezarrSettings") -> None:
        """Initialise the client from TrezarrSettings.

        Args:
            settings: Validated settings object.  The API key is extracted here (once)
                and passed directly to AsyncOpenAI — it is never stored separately.
        """
        # D-11: SecretStr resolved ONLY here — the resolved string is passed
        # straight into AsyncOpenAI and never retained as an attribute on this object.
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            max_retries=settings.llm_max_retries,   # D-07: explicit 4, not SDK default 2
            timeout=settings.llm_request_timeout,
        )
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(settings.llm_max_concurrency)  # D-06
        self._mode: str = settings.llm_structured_output_mode  # D-04
        self._model: str = settings.llm_model
        # Reasoning/"thinking" mode toggle: when disabled, inject
        # extra_body={"thinking": {"type": "disabled"}} into EVERY tier (parse +
        # both create() calls), not just one — auto-mode degradation means a single
        # call may traverse any tier. Computed once; spread into each request below.
        # An empty dict means "send nothing extra", keeping requests clean for
        # endpoints that have no thinking mode.
        self._call_kwargs: dict = (
            {"extra_body": {"thinking": {"type": "disabled"}}}
            if settings.llm_disable_thinking
            else {}
        )
        # Per-call reasoning override (FIX-B, 260607-dbe): the effort level to forward
        # to the DeepSeek reasoning_effort param when a per-call thinking=True is supplied.
        # Stored once from settings so _call_with_fallback does not need a settings reference.
        self._reasoning_effort: str = settings.llm_reasoning_effort

    async def call(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None = None,
        model: str | None = None,   # D-113: per-call model override; None = use self._model
        thinking: bool | None = None,  # FIX-B: per-call reasoning override; None = global default
        collector: PassStatsCollector | None = None,  # 260612-1tm: per-pass metrics accumulator
    ) -> BaseModel | str:
        """Make an LLM call, applying the configured structured-output tier strategy.

        Args:
            messages: Chat messages in OpenAI format.  Must be a non-empty list.
            response_model: Optional Pydantic model for structured output (Tier 1).
                If None, skips Tier 1 and starts at Tier 2.
            model: Optional per-call model name override (D-113).  When provided,
                overrides self._model for this single call.  When None (default),
                self._model is used.  The single _semaphore is unchanged (D-06).
            thinking: Optional per-call reasoning (thinking) mode override (FIX-B, 260607-dbe).
                True  — force enabled+reasoning_effort for this call only.
                False — force disabled for this call only (overrides global default).
                None  — use self._call_kwargs unchanged (zero regression for existing callers).
                self._call_kwargs is NEVER mutated; effective_call_kwargs is a local variable.
            collector: Optional PassStatsCollector for per-call duration + token capture
                (260612-1tm step-0 observability). When provided, record() is called inside
                _call_with_fallback after each successful SDK call.  When None (default),
                existing callers get identical behavior — zero regression.

        Returns:
            When Tier 1 (json_schema) succeeds with a ``response_model``, the parsed
            Pydantic object (``response_model`` instance) is returned — the typed
            structured output (CR-02).  Otherwise the raw response content string is
            returned: for Tier 2 this is JSON; for Tier 3 it is plain text (caller is
            responsible for parsing via the delimited-text protocol).

        Raises:
            ValueError: if ``messages`` is empty (WR-05 — fail fast at the boundary).
            RuntimeError: if the model refuses structured output, or returns empty
                content on any tier (CR-02 — never return ``None``).
        """
        # WR-05: validate input at the boundary so malformed input fails clearly
        # here rather than deep inside the SDK with an opaque error.
        if not messages:
            raise ValueError("messages must be a non-empty list of chat messages")

        async with self._semaphore:  # D-06: enforce concurrency cap — UNCHANGED
            return await self._call_with_fallback(messages, response_model, model, thinking, collector)

    async def _call_with_fallback(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None,
        model: str | None = None,  # D-113: per-call override; None = use self._model
        thinking: bool | None = None,  # FIX-B: per-call reasoning override; None = global default
        collector: PassStatsCollector | None = None,  # 260612-1tm: per-call metrics
    ) -> BaseModel | str:
        """Internal dispatch implementing the three-tier degradation (D-04).

        Tier 1 — json_schema: uses chat.completions.parse() with a Pydantic model as
            response_format.  Requires the endpoint to support strict JSON Schema output.
            Used when mode in ("auto", "json_schema") and response_model is not None.

        Tier 2 — json_object: uses chat.completions.create() with
            response_format={"type": "json_object"}.  Broader endpoint support.
            Used when mode in ("auto", "json_object") or after Tier 1 fails in auto mode.

        Tier 3 — plain text: uses chat.completions.create() with no response_format.
            Always works; caller parses response with a delimited-text protocol.
            Used as final fallback in auto mode or when mode == "text".

        Pinned modes (json_schema|json_object) propagate exceptions instead of falling back.

        Args:
            thinking: Per-call override for the reasoning/thinking mode (FIX-B, 260607-dbe).
                True  — build effective_call_kwargs with enabled extra_body + reasoning_effort.
                False — build effective_call_kwargs with disabled extra_body only.
                None  — use self._call_kwargs as-is (zero regression for existing callers).
                self._call_kwargs is NEVER mutated; effective_call_kwargs is a local per-call variable.
            collector: Optional PassStatsCollector (260612-1tm).  When provided, record() is
                called after each successful SDK call with the wall-clock duration and token
                counts from response.usage (None-guarded).  The collector= param is a pure
                side-effect; it never influences the return value or exception propagation.
        """
        mode = self._mode
        effective_model = model or self._model  # D-113: per-call override, falls back to global

        # FIX-B (T-dbe-01 mitigation): compute effective_call_kwargs as a LOCAL variable per call.
        # self._call_kwargs is NEVER mutated — no state leaks between sequential calls.
        if thinking is None:
            effective_call_kwargs = self._call_kwargs  # global default (zero regression)
        elif thinking is False:
            effective_call_kwargs = {"extra_body": {"thinking": {"type": "disabled"}}}
        else:  # thinking is True
            effective_call_kwargs = {
                "extra_body": {"thinking": {"type": "enabled"}},
                "reasoning_effort": self._reasoning_effort,
            }

        # ── Tier 1: json_schema (strict structured output) ────────────────────
        # parse() is attempted in auto/json_schema mode regardless of whether
        # response_model is provided — the endpoint signals unsupported json_schema
        # via 400/422, triggering the fallback.  response_model is passed as
        # response_format only when present.
        if mode in ("auto", "json_schema"):
            try:
                parse_kwargs: dict = {}
                if response_model is not None:
                    parse_kwargs["response_format"] = response_model
                _t0 = time.perf_counter()
                parsed = await self._client.chat.completions.parse(
                    model=effective_model,
                    messages=messages,
                    **parse_kwargs,
                    **effective_call_kwargs,  # thinking-mode toggle (local per-call)
                )
                _dur = time.perf_counter() - _t0
                if collector is not None:
                    _u = getattr(parsed, "usage", None)
                    collector.record(
                        duration_s=_dur,
                        prompt_tokens=getattr(_u, "prompt_tokens", None),
                        completion_tokens=getattr(_u, "completion_tokens", None),
                    )
                msg = parsed.choices[0].message
                # CR-02: a model refusal carries no usable output — surface it
                # instead of silently returning None.
                if getattr(msg, "refusal", None):
                    raise RuntimeError(
                        f"LLM refused structured output: {msg.refusal}"
                    )
                # CR-02: when a response_model was requested and the SDK parsed it,
                # return the *typed* Pydantic object — the whole point of Tier 1.
                if response_model is not None and getattr(msg, "parsed", None) is not None:
                    return msg.parsed
                content = msg.content
                if content is None:
                    raise RuntimeError("LLM returned empty content (Tier 1)")
                return content
            except (openai.BadRequestError, openai.UnprocessableEntityError):
                if mode == "json_schema":
                    raise  # D-04: pinned mode — 400/422 propagates, no fallback
                # mode == "auto": fall through to Tier 2
            except openai.APIError:
                # WR-04: only OpenAI SDK transport/API errors trigger a tier
                # downgrade.  TypeError/AttributeError/KeyError from a genuine
                # bug in call construction (or a malformed `messages` arg) MUST
                # propagate — never silently downgrade a programming error.
                if mode == "json_schema":
                    raise  # pinned mode — propagate
                # mode == "auto": SDK error → fall through to Tier 2

        # ── Tier 2: json_object ────────────────────────────────────────────────
        # Guard: json_object only applies to structured/JSON callers.  When
        # response_model is None the caller uses the delimited-text protocol
        # (parse_numbered_response) and must receive plain text from Tier 3.
        # Sending response_format={"type":"json_object"} for a non-JSON prompt
        # causes deepseek (and other endpoints) to reject with a 400 "Prompt
        # must contain the word 'json'" — breaking every translate/self-review
        # call in pinned json_object mode (the deployed configuration).
        if mode in ("auto", "json_object") and response_model is not None:
            try:
                _t0 = time.perf_counter()
                resp = await self._client.chat.completions.create(
                    model=effective_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    **effective_call_kwargs,  # thinking-mode toggle (local per-call)
                )
                _dur = time.perf_counter() - _t0
                if collector is not None:
                    _u = getattr(resp, "usage", None)
                    collector.record(
                        duration_s=_dur,
                        prompt_tokens=getattr(_u, "prompt_tokens", None),
                        completion_tokens=getattr(_u, "completion_tokens", None),
                    )
                content = resp.choices[0].message.content
                if content is None:
                    raise RuntimeError("LLM returned empty content (Tier 2)")
                return content
            except (openai.BadRequestError, openai.UnprocessableEntityError):
                if mode == "json_object":
                    raise  # D-04: pinned mode never falls back — propagate to caller
                # mode == "auto": fall through to Tier 3

        # ── Tier 3: plain text (always works; caller uses delimited-text protocol) ──
        _t0 = time.perf_counter()
        resp = await self._client.chat.completions.create(
            model=effective_model,
            messages=messages,
            **effective_call_kwargs,  # thinking-mode toggle (local per-call)
        )
        _dur = time.perf_counter() - _t0
        if collector is not None:
            _u = getattr(resp, "usage", None)
            collector.record(
                duration_s=_dur,
                prompt_tokens=getattr(_u, "prompt_tokens", None),
                completion_tokens=getattr(_u, "completion_tokens", None),
            )
        content = resp.choices[0].message.content
        if content is None:
            raise RuntimeError("LLM returned empty content (Tier 3)")
        return content
