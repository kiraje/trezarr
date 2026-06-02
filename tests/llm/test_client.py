"""Wave 0 RED stubs for LLMClient per-call model override (D-113).

These stubs test the Phase-10 D-113 extension where LLMClient.call() accepts
an optional `model` kwarg that overrides the client's configured global model
for a single call. This is needed for per-series model overrides (SVC-05).

Both stubs are xfail because LLMClient.call() does not yet accept a `model`
kwarg — it only uses self._model.

Pattern mirrors tests/llm/test_client_tiers.py: deferred imports, AsyncMock
patching of client._client.chat.completions.parse.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="LLMClient.call() does not yet accept model= kwarg (D-113, Phase 10)",
)
async def test_per_call_model_override():
    """LLMClient.call(messages, model="override") uses override-model, not global model (D-113).

    When call() is invoked with model="override-model", the underlying
    OpenAI parse() call must receive model="override-model" — NOT the global
    model from settings ("global-model").
    """
    from trezarr.llm.client import LLMClient  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="global-model",
        llm_max_concurrency=1,
    )
    client = LLMClient(settings)

    ok_msg = MagicMock(content="ok", refusal=None, parsed=None)
    mock_parse = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=ok_msg)]))
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "test"}], model="override-model")

    assert mock_parse.called, "Expected .parse() to be called"
    call_kwargs = mock_parse.call_args[1] if mock_parse.call_args[1] else {}
    used_model = call_kwargs.get("model")
    assert used_model == "override-model", (
        f"D-113: expected model='override-model', got {used_model!r}. "
        f"call() must forward the per-call model kwarg to the underlying API call."
    )


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="LLMClient.call() model kwarg fallback to global model not yet implemented (D-113, Phase 10)",
)
async def test_call_uses_global_model_when_no_override():
    """LLMClient.call(messages) with no model kwarg uses self._model (global model).

    This is the non-override baseline: when model= is not passed, the global
    model from TrezarrSettings is used (current behavior confirmed by this stub
    once call() is extended to accept the optional kwarg).
    """
    from trezarr.llm.client import LLMClient  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="global-model",
        llm_max_concurrency=1,
    )
    client = LLMClient(settings)

    ok_msg = MagicMock(content="ok", refusal=None, parsed=None)
    mock_parse = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=ok_msg)]))
    # Call without model= kwarg — should use global-model
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "test"}])

    assert mock_parse.called, "Expected .parse() to be called"
    call_kwargs = mock_parse.call_args[1] if mock_parse.call_args[1] else {}
    used_model = call_kwargs.get("model")
    assert used_model == "global-model", (
        f"D-113: expected global model='global-model' when no override, got {used_model!r}"
    )
