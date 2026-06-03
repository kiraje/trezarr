"""Tests for the LLMClient reasoning/"thinking" mode toggle (llm_disable_thinking).

When llm_disable_thinking is True, EVERY tier (Tier 1 parse, Tier 2 json_object
create, Tier 3 plain-text create) must carry
extra_body={"thinking": {"type": "disabled"}} so auto-mode degradation can never
leak a thinking-enabled request. When False (default), no extra_body is sent.
"""
from unittest.mock import AsyncMock, MagicMock, patch

DISABLED_BODY = {"extra_body": {"thinking": {"type": "disabled"}}}


def _ok_parse():
    """A mock .parse() returning a plain content string (no response_model)."""
    msg = MagicMock(content="ok", refusal=None, parsed=None)
    return AsyncMock(return_value=MagicMock(choices=[MagicMock(message=msg)]))


def _ok_create():
    """A mock .create() returning a plain content string."""
    return AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))])
    )


async def test_default_sends_no_extra_body(settings_factory):
    """By default (toggle off) the client computes empty call-kwargs and passes no extra_body."""
    from trezarr.llm.client import LLMClient

    client = LLMClient(settings_factory(llm_structured_output_mode="auto"))
    assert client._call_kwargs == {}, "default must add no per-call kwargs"

    mock_parse = _ok_parse()
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "x"}])

    assert "extra_body" not in mock_parse.call_args.kwargs, (
        "no extra_body should be sent when thinking is left enabled"
    )


async def test_disable_thinking_precomputed(settings_factory):
    """The disable-thinking extra_body is built once at construction time."""
    from trezarr.llm.client import LLMClient

    client = LLMClient(settings_factory(llm_disable_thinking=True))
    assert client._call_kwargs == DISABLED_BODY


async def test_tier1_parse_carries_disabled_thinking(settings_factory):
    """Tier 1 (.parse, json_schema) forwards the disabled-thinking extra_body."""
    from trezarr.llm.client import LLMClient

    client = LLMClient(
        settings_factory(llm_structured_output_mode="auto", llm_disable_thinking=True)
    )
    mock_parse = _ok_parse()
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "x"}])

    assert mock_parse.call_args.kwargs.get("extra_body") == DISABLED_BODY["extra_body"]


async def test_tier2_json_object_carries_disabled_thinking(settings_factory):
    """Tier 2 (.create, json_object) forwards the disabled-thinking extra_body."""
    from trezarr.llm.client import LLMClient

    client = LLMClient(
        settings_factory(llm_structured_output_mode="json_object", llm_disable_thinking=True)
    )
    mock_create = _ok_create()
    with patch.object(client._client.chat.completions, "create", mock_create):
        await client.call([{"role": "user", "content": "x"}])

    kwargs = mock_create.call_args.kwargs
    assert kwargs.get("extra_body") == DISABLED_BODY["extra_body"]
    # Tier 2 still pins json_object — the toggle must not displace response_format.
    assert kwargs.get("response_format") == {"type": "json_object"}


async def test_tier3_text_carries_disabled_thinking(settings_factory):
    """Tier 3 (.create, plain text) forwards the disabled-thinking extra_body."""
    from trezarr.llm.client import LLMClient

    client = LLMClient(
        settings_factory(llm_structured_output_mode="text", llm_disable_thinking=True)
    )
    mock_create = _ok_create()
    with patch.object(client._client.chat.completions, "create", mock_create):
        await client.call([{"role": "user", "content": "x"}])

    kwargs = mock_create.call_args.kwargs
    assert kwargs.get("extra_body") == DISABLED_BODY["extra_body"]
    # Tier 3 sends no response_format at all — toggle is the only extra kwarg.
    assert "response_format" not in kwargs
