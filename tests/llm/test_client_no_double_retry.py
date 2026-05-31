"""Tests verifying LLMClient does NOT double-stack tenacity on top of SDK retries (ENG-01).

D-07 mandates that per-request retries come from the OpenAI SDK's built-in
max_retries + exponential backoff. Stacking tenacity on top causes retry storms
against self-hosted endpoints. These tests guard against that anti-pattern.

Marked xfail(strict=False) until Plan 03 ships the LLMClient.
"""
import inspect
import pytest


@pytest.mark.xfail(strict=False, reason="LLMClient not yet implemented (Plan 03)")
def test_no_tenacity_on_client():
    """The LLMClient module must not import tenacity.

    The correct retry strategy is AsyncOpenAI(max_retries=N). Adding tenacity on top
    creates double-retry storms. This test verifies the module source does not import
    tenacity in any form.
    """
    import trezarr.llm.client as client_module  # deferred import

    source = inspect.getsource(client_module)
    assert "tenacity" not in source, (
        "LLMClient imports tenacity — this creates double-retry storms. "
        "Use AsyncOpenAI(max_retries=N) instead (D-07)."
    )


@pytest.mark.xfail(strict=False, reason="LLMClient not yet implemented (Plan 03)")
def test_max_retries_from_settings():
    """LLMClient passes settings.llm_max_retries to the inner AsyncOpenAI instance."""
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_retries=3,
    )
    client = LLMClient(settings)
    # The inner AsyncOpenAI client must have max_retries=3
    assert client._client.max_retries == 3, (
        f"Expected max_retries=3 on inner AsyncOpenAI, got {client._client.max_retries}"
    )
