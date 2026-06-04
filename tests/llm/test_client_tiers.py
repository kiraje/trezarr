"""Tests for LLMClient structured-output tier fallback behaviour (ENG-01).

The client must try json_schema (Tier 1) first, fall back to json_object (Tier 2)
on 400/422, and finally fall back to plain text (Tier 3) on a second 400/422.
Pinned modes (json_schema / json_object) must propagate the exception instead of
falling back.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_bad_request_error():
    """Create a minimal openai.BadRequestError for mocking."""
    import openai  # deferred import — avoids collection error if openai is absent

    # BadRequestError requires (message, response, body)
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.headers = {}
    return openai.BadRequestError("Bad Request", response=mock_response, body={})


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

    # refusal=None / parsed=None so the success path returns .content (no
    # response_model passed here, so Tier 1 yields the raw JSON string).
    ok_msg = MagicMock(content="ok", refusal=None, parsed=None)
    mock_parse = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=ok_msg)]))
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "test"}])
    assert mock_parse.called, "Expected .parse() to be called for Tier 1 json_schema"


async def test_falls_back_to_json_object_on_400_with_response_model():
    """When .parse() raises BadRequestError(400) and response_model is provided,
    the client falls back to json_object (Tier 2).

    Note: with response_model=None the fix routes directly to Tier 3 (plain text)
    because json_object is meaningless for delimited-text callers.  This test
    exercises the structured-caller path (response_model!=None) where Tier 2
    json_object is still the correct fallback.
    """
    from pydantic import BaseModel

    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    class Dummy(BaseModel):
        v: str

    settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_structured_output_mode="auto",
        llm_max_concurrency=1,
    )
    client = LLMClient(settings)

    mock_create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content='{"v":"ok"}'))])
    )
    with (
        patch.object(
            client._client.chat.completions,
            "parse",
            side_effect=_make_bad_request_error(),
        ),
        patch.object(client._client.chat.completions, "create", mock_create),
    ):
        await client.call(
            [{"role": "user", "content": "test"}],
            response_model=Dummy,
        )

    assert mock_create.called, "Expected .create() to be called after Tier 1 fallback"
    call_kwargs = mock_create.call_args.kwargs
    # response_format should be {"type": "json_object"} for Tier 2
    rf = call_kwargs.get("response_format")
    assert rf == {"type": "json_object"}, f"Expected json_object response_format, got: {rf}"


async def test_falls_back_to_text_on_400_with_no_response_model():
    """When .parse() raises BadRequestError(400) and response_model is None,
    the client falls back directly to Tier 3 plain text (skipping Tier 2 json_object).

    This is the corrected auto-mode behavior for translate/self-review callers:
    since they use the delimited-text protocol, Tier 2 (json_object) is bypassed
    entirely — it only applies when a structured JSON response is needed.
    """
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
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="[1] plain text result"))]
        )
    )
    with (
        patch.object(
            client._client.chat.completions,
            "parse",
            side_effect=_make_bad_request_error(),
        ),
        patch.object(client._client.chat.completions, "create", mock_create),
    ):
        result = await client.call(
            [{"role": "user", "content": "test"}],
            response_model=None,
        )

    assert result == "[1] plain text result", f"Expected plain text result, got: {result}"
    assert mock_create.call_count == 1, (
        f"Expected exactly 1 create() call (Tier 3 plain text), got {mock_create.call_count}"
    )
    # Must NOT send json_object format — that would fail on deepseek with 400
    call_kwargs = mock_create.call_args.kwargs
    rf = call_kwargs.get("response_format")
    assert rf is None, f"response_format must be absent for Tier 3 plain-text call; got: {rf!r}"


async def test_falls_back_to_text_on_second_400_with_response_model():
    """With response_model!=None in auto mode, if both parse() and json_object create()
    fail with 400, the final fallback to plain text is reached.

    This exercises the full 3-tier degradation chain for structured callers.
    """
    from pydantic import BaseModel

    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import

    class Dummy(BaseModel):
        v: str

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
        result = await client.call(
            [{"role": "user", "content": "test"}],
            response_model=Dummy,
        )

    assert result == "plain text result", f"Expected plain text result, got: {result}"
    assert call_count == 2, f"Expected 2 create() calls (json_object + text), got {call_count}"


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


async def test_tier1_returns_parsed_object(settings_factory):
    """Tier-1 with a response_model returns the typed Pydantic object, not raw JSON (CR-02)."""
    from pydantic import BaseModel

    from trezarr.llm.client import LLMClient  # deferred import

    class Reply(BaseModel):
        greeting: str

    client = LLMClient(settings_factory(llm_structured_output_mode="auto"))

    expected = Reply(greeting="xin chào")
    # ParsedChatCompletionMessage carries the typed object in .parsed; .content is
    # the raw JSON string. The client must return .parsed, not .content.
    msg = MagicMock(parsed=expected, content='{"greeting": "xin chào"}', refusal=None)
    mock_parse = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=msg)]))

    with patch.object(client._client.chat.completions, "parse", mock_parse):
        result = await client.call(
            [{"role": "user", "content": "greet"}], response_model=Reply
        )

    assert result is expected, "Tier 1 must return the parsed Pydantic object (CR-02)"


async def test_tier1_refusal_raises(settings_factory):
    """A model refusal on Tier 1 raises instead of returning None (CR-02)."""
    from trezarr.llm.client import LLMClient  # deferred import

    client = LLMClient(settings_factory(llm_structured_output_mode="auto"))

    msg = MagicMock(parsed=None, content=None, refusal="policy violation")
    mock_parse = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=msg)]))

    with patch.object(client._client.chat.completions, "parse", mock_parse):
        with pytest.raises(RuntimeError, match="refused"):
            await client.call([{"role": "user", "content": "x"}])


async def test_empty_messages_raises(settings_factory):
    """An empty messages list fails fast with ValueError at the boundary (WR-05)."""
    from trezarr.llm.client import LLMClient  # deferred import

    client = LLMClient(settings_factory())

    with pytest.raises(ValueError, match="non-empty"):
        await client.call([])


# ── Regression tests: json_object mode must not apply to response_model=None callers ──
# Bug: in pinned json_object mode, _call_with_fallback sent response_format={"type":
# "json_object"} on ALL calls, including translate/self-review (response_model=None).
# Against deepseek this caused a 400 "Prompt must contain the word 'json'", meaning
# NO translation ever completed in the deployed configuration. Fix: gate Tier 2 on
# response_model is not None so response_model=None callers always reach Tier 3.


async def test_json_object_mode_with_no_response_model_uses_plain_text(settings_factory):
    """In pinned json_object mode, a response_model=None call must NOT send
    response_format=json_object; it must reach Tier 3 and return plain text.

    This is the regression guard for the deepseek 400 bug: translate/self-review
    pass no response_model and use the numbered-line TEXT protocol — injecting
    json_object breaks them.
    """
    from trezarr.llm.client import LLMClient  # deferred import

    client = LLMClient(settings_factory(llm_structured_output_mode="json_object"))

    plain_text_content = "[1] Xin chào\n[2] Tạm biệt"
    mock_create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content=plain_text_content))]
        )
    )

    with patch.object(client._client.chat.completions, "create", mock_create):
        result = await client.call(
            [{"role": "user", "content": "Translate: Hello / Goodbye"}],
            response_model=None,  # translate/self-review callers pass None
        )

    assert mock_create.called, "Tier 3 create() must be called for response_model=None"
    assert result == plain_text_content, f"Expected plain text, got: {result!r}"

    # Critical: response_format must NOT be json_object in the kwargs sent to create()
    call_kwargs = mock_create.call_args.kwargs if mock_create.call_args else {}
    rf = call_kwargs.get("response_format")
    assert rf is None, (
        f"response_format must be absent for response_model=None in json_object mode; "
        f"got: {rf!r}.  This would cause a deepseek 400 'prompt must contain json'."
    )


async def test_json_object_mode_with_response_model_uses_json_object_tier(settings_factory):
    """In pinned json_object mode, a call WITH a response_model must still use Tier 2
    (response_format=json_object).  analyze/attribute callers must be unaffected by the fix.
    """
    from pydantic import BaseModel

    from trezarr.llm.client import LLMClient  # deferred import

    class SomeModel(BaseModel):
        value: str

    client = LLMClient(settings_factory(llm_structured_output_mode="json_object"))

    json_content = '{"value": "test"}'
    mock_create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content=json_content))]
        )
    )

    with patch.object(client._client.chat.completions, "create", mock_create):
        result = await client.call(
            [{"role": "user", "content": "Return json with value field"}],
            response_model=SomeModel,
        )

    assert mock_create.called, "Tier 2 create() must be called for response_model!=None in json_object mode"
    assert result == json_content, f"Expected raw JSON string from Tier 2, got: {result!r}"

    # response_format MUST be json_object for structured callers
    call_kwargs = mock_create.call_args.kwargs if mock_create.call_args else {}
    rf = call_kwargs.get("response_format")
    assert rf == {"type": "json_object"}, (
        f"response_format must be json_object for response_model!=None; got: {rf!r}"
    )
