"""Tests for LLMClient concurrency cap via asyncio.Semaphore (ENG-01).

Verifies that the client never exceeds max_concurrency simultaneous in-flight LLM
calls, regardless of how many coroutines are awaiting it concurrently.

Marked xfail(strict=False) until Plan 03 ships the LLMClient.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.xfail(strict=False, reason="LLMClient not yet implemented (Plan 03)")
async def test_semaphore_caps_concurrent_calls():
    """LLMClient with max_concurrency=2 allows at most 2 simultaneous in-flight calls.

    Strategy: create a controlled async function that records the maximum observed
    concurrency. Fire 5 calls concurrently via asyncio.gather; assert peak <= 2.
    """
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=2,
    )
    client = LLMClient(settings)

    active = 0
    peak = 0

    async def _fake_call(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)  # yield to event loop to allow other coroutines to enter
        active -= 1
        return MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))])

    messages = [{"role": "user", "content": "test"}]
    with patch.object(client._client.chat.completions, "create", side_effect=_fake_call):
        # Also patch .parse() to avoid it being called before .create()
        with patch.object(
            client._client.chat.completions,
            "parse",
            side_effect=Exception("force text path"),
        ):
            await asyncio.gather(*[client.call(messages) for _ in range(5)])

    assert peak <= 2, (
        f"Peak concurrency was {peak}, expected at most {settings.llm_max_concurrency}"
    )
