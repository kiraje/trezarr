"""Live endpoint smoke test for LLMClient (ENG-01).

This module is excluded from the standard CI run and must be invoked manually:

    pytest tests/llm/test_client_live.py -v -s -m live

The test auto-skips if TREZARR_LLM_BASE_URL is not set in the environment,
making it safe to include in the test suite without breaking CI.

Manual invocation requirements:
    export TREZARR_LLM_BASE_URL=http://your-endpoint/v1
    export TREZARR_LLM_MODEL=your-model-name
    export TREZARR_LLM_API_KEY=your-api-key
    pytest tests/llm/test_client_live.py -v -s
"""
import os
import pytest


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("TREZARR_LLM_BASE_URL"),
    reason="no live endpoint configured — set TREZARR_LLM_BASE_URL to run",
)
async def test_live_endpoint_returns_completion():
    """Creates LLMClient from real env vars and asserts a non-empty response.

    Run with:
        pytest tests/llm/test_client_live.py -v -s -m live

    Requires environment variables:
        TREZARR_LLM_BASE_URL  — base URL of the OpenAI-compatible endpoint
        TREZARR_LLM_MODEL     — model identifier (must be recognised by the endpoint)
        TREZARR_LLM_API_KEY   — API key (can be a dummy string for local endpoints)
    """
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings(
        llm_base_url=os.environ["TREZARR_LLM_BASE_URL"],
        llm_model=os.environ.get("TREZARR_LLM_MODEL", "gpt-4o"),
        llm_api_key=os.environ.get("TREZARR_LLM_API_KEY", "not-set"),
        llm_max_concurrency=1,
        llm_max_retries=2,
    )
    client = LLMClient(settings)

    messages = [{"role": "user", "content": "Say 'hello' in one word."}]
    result = await client.call(messages)

    assert result is not None, "Response was None"
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result.strip()) > 0, "Response was empty"
    print(f"\nLive endpoint response: {result!r}")
