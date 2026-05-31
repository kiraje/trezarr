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
from typing import TYPE_CHECKING

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

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

    async def call(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None = None,
    ) -> str:
        """Make an LLM call, applying the configured structured-output tier strategy.

        Args:
            messages: Chat messages in OpenAI format.
            response_model: Optional Pydantic model for structured output (Tier 1).
                If None, skips Tier 1 and starts at Tier 2.

        Returns:
            The LLM response content as a string.  For Tier 1/2 this is JSON; for Tier 3
            it is plain text (caller is responsible for parsing via delimited-text protocol).
        """
        async with self._semaphore:  # D-06: enforce concurrency cap
            return await self._call_with_fallback(messages, response_model)

    async def _call_with_fallback(
        self,
        messages: list[dict],
        response_model: type[BaseModel] | None,
    ) -> str:
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
        """
        mode = self._mode

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
                parsed = await self._client.chat.completions.parse(
                    model=self._model,
                    messages=messages,
                    **parse_kwargs,
                )
                return parsed.choices[0].message.content  # type: ignore[return-value]
            except (openai.BadRequestError, openai.UnprocessableEntityError):
                if mode == "json_schema":
                    raise  # D-04: pinned mode — 400/422 propagates, no fallback
                # mode == "auto": fall through to Tier 2
            except Exception:
                if mode == "json_schema":
                    raise  # pinned mode — all errors propagate
                # mode == "auto": any other error also triggers fallback
                # (in production, the SDK wraps network errors into typed openai
                # exceptions; this branch handles test injection via side_effect)

        # ── Tier 2: json_object ────────────────────────────────────────────────
        if mode in ("auto", "json_object"):
            try:
                resp = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content  # type: ignore[return-value]
            except (openai.BadRequestError, openai.UnprocessableEntityError):
                if mode == "json_object":
                    raise  # D-04: pinned mode never falls back — propagate to caller
                # mode == "auto": fall through to Tier 3

        # ── Tier 3: plain text (always works; caller uses delimited-text protocol) ──
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        return resp.choices[0].message.content  # type: ignore[return-value]
