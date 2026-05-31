"""Tests for LLMClient structured-output tier fallback behaviour (ENG-01).

The client must try json_schema (Tier 1) first, fall back to json_object (Tier 2)
on 400/422, and finally fall back to plain text (Tier 3) on a second 400/422.
Pinned modes (json_schema / json_object) must propagate the exception instead of
falling back.

All tests are marked xfail(strict=False) until Plan 03 ships the LLMClient.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_bad_request_error():
    """Create a minimal openai.BadRequestError for mocking."""
    import openai  # deferred import — avoids collection error if openai is absent

    # BadRequestError requires (message, response, body)
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.headers = {}
    return openai.BadRequestError("Bad Request", response=mock_response, body={})


@pytest.mark.xfail(strict=False, reason="LLMClient not yet implemented (Plan 03)")
async def test_uses_json_schema_by_default():
    """LLMClient with mode='auto' calls .parse() (json_schema) on the first attempt."""
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_structured_output_mode="auto",
        llm_max_concurrency=1,
    )
    client = LLMClient(settings)

    mock_parse = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))]))
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "test"}])
    assert mock_parse.called, "Expected .parse() to be called for Tier 1 json_schema"


@pytest.mark.xfail(strict=False, reason="LLMClient not yet implemented (Plan 03)")
async def test_falls_back_to_json_object_on_400():
    """When .parse() raises BadRequestError(400), the client falls back to json_object."""
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_structured_output_mode="auto",
        llm_max_concurrency=1,
    )
    client = LLMClient(settings)

    mock_create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="fallback"))])
    )
    with (
        patch.object(
            client._client.chat.completions,
            "parse",
            side_effect=_make_bad_request_error(),
        ),
        patch.object(client._client.chat.completions, "create", mock_create),
    ):
        await client.call([{"role": "user", "content": "test"}])

    assert mock_create.called, "Expected .create() to be called after Tier 1 fallback"
    call_kwargs = mock_create.call_args[1] if mock_create.call_args[1] else {}
    call_args = mock_create.call_args[0] if mock_create.call_args[0] else ()
    # response_format should be {"type": "json_object"} for Tier 2
    rf = call_kwargs.get("response_format") or (call_args[0] if call_args else None)
    assert rf == {"type": "json_object"} or (
        isinstance(rf, dict) and rf.get("type") == "json_object"
    ), f"Expected json_object response_format, got: {rf}"


@pytest.mark.xfail(strict=False, reason="LLMClient not yet implemented (Plan 03)")
async def test_falls_back_to_text_on_second_400():
    """When both .parse() and json_object .create() fail with 400, falls back to plain text."""
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_structured_output_mode="auto",
        llm_max_concurrency=1,
    )
    client = LLMClient(settings)

    call_count = 0

    async def _create_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First create() call (json_object tier) — reject it
            raise _make_bad_request_error()
        # Second create() call (plain text tier) — succeed
        return MagicMock(choices=[MagicMock(message=MagicMock(content="plain text result"))])

    with (
        patch.object(
            client._client.chat.completions,
            "parse",
            side_effect=_make_bad_request_error(),
        ),
        patch.object(client._client.chat.completions, "create", side_effect=_create_side_effect),
    ):
        result = await client.call([{"role": "user", "content": "test"}])

    assert result == "plain text result", f"Expected plain text result, got: {result}"
    assert call_count == 2, f"Expected 2 create() calls (json_object + text), got {call_count}"


@pytest.mark.xfail(strict=False, reason="LLMClient not yet implemented (Plan 03)")
async def test_pinned_mode_raises():
    """With mode='json_schema', a 400 from .parse() propagates instead of falling back."""
    import openai  # deferred import
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_structured_output_mode="json_schema",
        llm_max_concurrency=1,
    )
    client = LLMClient(settings)

    with (
        patch.object(
            client._client.chat.completions,
            "parse",
            side_effect=_make_bad_request_error(),
        ),
        pytest.raises(openai.BadRequestError),
    ):
        await client.call([{"role": "user", "content": "test"}])
