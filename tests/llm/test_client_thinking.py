"""Tests for the LLMClient reasoning/"thinking" mode toggle (llm_disable_thinking).

When llm_disable_thinking is True, EVERY tier (Tier 1 parse, Tier 2 json_object
create, Tier 3 plain-text create) must carry
extra_body={"thinking": {"type": "disabled"}} so auto-mode degradation can never
leak a thinking-enabled request. When False (default), no extra_body is sent.

Also covers per-call thinking: bool | None override (FIX-B, 260607-dbe):
  - thinking=True forces enabled+reasoning_effort on that single call only.
  - thinking=False forces disabled on that single call only (overrides global default).
  - thinking=None leaves self._call_kwargs unchanged (zero regression for existing callers).
  - No state leaks between consecutive calls.

And new config knobs: enable_reasoning_analysis, enable_reasoning_attribution,
llm_reasoning_effort (all tested via test_config_new_fields_defaults).
"""
from unittest.mock import AsyncMock, MagicMock, patch

DISABLED_BODY = {"extra_body": {"thinking": {"type": "disabled"}}}
ENABLED_BODY = {"extra_body": {"thinking": {"type": "enabled"}}}


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
    """Tier 2 (.create, json_object) forwards the disabled-thinking extra_body.

    Must use response_model!=None so the Tier 2 guard lets the call through.
    (Tier 2 is only reached when response_model is not None in json_object mode —
    this is the fix for the deepseek 400 bug where response_model=None calls
    incorrectly received response_format=json_object.)
    """
    from pydantic import BaseModel

    from trezarr.llm.client import LLMClient

    class Dummy(BaseModel):
        v: str

    client = LLMClient(
        settings_factory(llm_structured_output_mode="json_object", llm_disable_thinking=True)
    )
    mock_create = _ok_create()
    with patch.object(client._client.chat.completions, "create", mock_create):
        await client.call(
            [{"role": "user", "content": "return json with v field"}],
            response_model=Dummy,
        )

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


# ── Per-call thinking override tests (FIX-B, 260607-dbe) ─────────────────────


def test_config_new_fields_defaults(settings_factory):
    """TrezarrSettings has enable_reasoning_analysis=True, enable_reasoning_attribution=True,
    llm_reasoning_effort='high' as defaults (FIX-B new config knobs).
    """
    settings = settings_factory()
    assert settings.enable_reasoning_analysis is True, (
        "enable_reasoning_analysis must default to True"
    )
    assert settings.enable_reasoning_attribution is True, (
        "enable_reasoning_attribution must default to True"
    )
    assert settings.llm_reasoning_effort == "high", (
        "llm_reasoning_effort must default to 'high'"
    )


async def test_per_call_thinking_true_tier1(settings_factory):
    """call(thinking=True) on Tier 1 (json_schema) → parse() receives
    extra_body={"thinking":{"type":"enabled"}} AND reasoning_effort="high".
    self._call_kwargs must not be mutated by the call.
    """
    from trezarr.llm.client import LLMClient

    client = LLMClient(settings_factory(
        llm_structured_output_mode="auto",
        llm_disable_thinking=False,     # global default: no disable
        llm_reasoning_effort="high",
    ))
    original_call_kwargs = dict(client._call_kwargs)  # snapshot before call

    mock_parse = _ok_parse()
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "x"}], thinking=True)

    kw = mock_parse.call_args.kwargs
    assert kw.get("extra_body") == {"thinking": {"type": "enabled"}}, (
        f"thinking=True must inject enabled extra_body; got {kw.get('extra_body')!r}"
    )
    assert kw.get("reasoning_effort") == "high", (
        f"thinking=True must inject reasoning_effort='high'; got {kw.get('reasoning_effort')!r}"
    )
    # No mutation of self._call_kwargs
    assert client._call_kwargs == original_call_kwargs, (
        "thinking=True must NOT mutate self._call_kwargs"
    )


async def test_per_call_thinking_true_tier2(settings_factory):
    """call(thinking=True) on Tier 2 (json_object) → create() receives enabled extra_body
    and reasoning_effort.
    """
    from pydantic import BaseModel

    from trezarr.llm.client import LLMClient

    class Dummy(BaseModel):
        v: str

    client = LLMClient(settings_factory(
        llm_structured_output_mode="json_object",
        llm_disable_thinking=False,
        llm_reasoning_effort="high",
    ))

    mock_create = _ok_create()
    with patch.object(client._client.chat.completions, "create", mock_create):
        await client.call(
            [{"role": "user", "content": "return json with v field"}],
            response_model=Dummy,
            thinking=True,
        )

    kw = mock_create.call_args.kwargs
    assert kw.get("extra_body") == {"thinking": {"type": "enabled"}}, (
        f"Tier 2 thinking=True must inject enabled extra_body; got {kw.get('extra_body')!r}"
    )
    assert kw.get("reasoning_effort") == "high", (
        f"Tier 2 thinking=True must inject reasoning_effort; got {kw.get('reasoning_effort')!r}"
    )


async def test_per_call_thinking_true_tier3(settings_factory):
    """call(thinking=True) on Tier 3 (text mode) → create() receives enabled extra_body
    and reasoning_effort.
    """
    from trezarr.llm.client import LLMClient

    client = LLMClient(settings_factory(
        llm_structured_output_mode="text",
        llm_disable_thinking=False,
        llm_reasoning_effort="high",
    ))

    mock_create = _ok_create()
    with patch.object(client._client.chat.completions, "create", mock_create):
        await client.call([{"role": "user", "content": "x"}], thinking=True)

    kw = mock_create.call_args.kwargs
    assert kw.get("extra_body") == {"thinking": {"type": "enabled"}}, (
        f"Tier 3 thinking=True must inject enabled extra_body; got {kw.get('extra_body')!r}"
    )
    assert kw.get("reasoning_effort") == "high", (
        f"Tier 3 thinking=True must inject reasoning_effort; got {kw.get('reasoning_effort')!r}"
    )


async def test_per_call_thinking_false_overrides_global_default(settings_factory):
    """call(thinking=False) forces disabled extra_body even when global default adds no extra_body.

    When llm_disable_thinking=False (global default = empty call_kwargs), passing
    thinking=False on a single call must still emit {"thinking":{"type":"disabled"}}
    for that call — independently of the global state.
    """
    from trezarr.llm.client import LLMClient

    client = LLMClient(settings_factory(
        llm_structured_output_mode="auto",
        llm_disable_thinking=False,   # global: no extra_body
    ))
    assert client._call_kwargs == {}, "precondition: global default must be empty"

    mock_parse = _ok_parse()
    with patch.object(client._client.chat.completions, "parse", mock_parse):
        await client.call([{"role": "user", "content": "x"}], thinking=False)

    kw = mock_parse.call_args.kwargs
    assert kw.get("extra_body") == {"thinking": {"type": "disabled"}}, (
        f"thinking=False must inject disabled extra_body on this call; got {kw.get('extra_body')!r}"
    )
    # No reasoning_effort when forcing disabled
    assert "reasoning_effort" not in kw, (
        "thinking=False must NOT inject reasoning_effort"
    )


async def test_per_call_thinking_none_no_change(settings_factory):
    """call(thinking=None) (the default) → call kwargs identical to what self._call_kwargs produces.

    Specifically: if llm_disable_thinking=False (empty), parse() receives no extra_body.
    If llm_disable_thinking=True, parse() receives the disabled extra_body.
    """
    from trezarr.llm.client import LLMClient

    # Case A: global empty → thinking=None leaves it empty
    client_a = LLMClient(settings_factory(
        llm_structured_output_mode="auto",
        llm_disable_thinking=False,
    ))
    mock_parse_a = _ok_parse()
    with patch.object(client_a._client.chat.completions, "parse", mock_parse_a):
        await client_a.call([{"role": "user", "content": "x"}], thinking=None)

    kw_a = mock_parse_a.call_args.kwargs
    assert "extra_body" not in kw_a, (
        "thinking=None with empty global default must NOT inject extra_body"
    )

    # Case B: global disabled → thinking=None preserves the disabled body
    client_b = LLMClient(settings_factory(
        llm_structured_output_mode="auto",
        llm_disable_thinking=True,
    ))
    mock_parse_b = _ok_parse()
    with patch.object(client_b._client.chat.completions, "parse", mock_parse_b):
        await client_b.call([{"role": "user", "content": "x"}], thinking=None)

    kw_b = mock_parse_b.call_args.kwargs
    assert kw_b.get("extra_body") == {"thinking": {"type": "disabled"}}, (
        "thinking=None with disabled global must still carry disabled extra_body"
    )


async def test_per_call_thinking_does_not_leak(settings_factory):
    """Two sequential calls: first with thinking=True, second with thinking=None.

    The second call must NOT carry reasoning_effort or the enabled extra_body.
    self._call_kwargs must remain unchanged after both calls.
    """
    from trezarr.llm.client import LLMClient

    client = LLMClient(settings_factory(
        llm_structured_output_mode="auto",
        llm_disable_thinking=False,
        llm_reasoning_effort="high",
    ))
    original_call_kwargs = dict(client._call_kwargs)

    call_args_list: list = []

    async def _capturing_parse(**kwargs):
        call_args_list.append(dict(kwargs))
        msg = MagicMock(content="ok", refusal=None, parsed=None)
        return MagicMock(choices=[MagicMock(message=msg)])

    with patch.object(client._client.chat.completions, "parse", side_effect=_capturing_parse):
        await client.call([{"role": "user", "content": "first"}], thinking=True)
        await client.call([{"role": "user", "content": "second"}], thinking=None)

    # First call: must have enabled extra_body + reasoning_effort
    first_kw = call_args_list[0]
    assert first_kw.get("extra_body") == {"thinking": {"type": "enabled"}}, (
        f"First call must have enabled extra_body; got {first_kw.get('extra_body')!r}"
    )
    assert first_kw.get("reasoning_effort") == "high", (
        f"First call must have reasoning_effort; got {first_kw.get('reasoning_effort')!r}"
    )

    # Second call (thinking=None → global empty): must NOT have extra_body or reasoning_effort
    second_kw = call_args_list[1]
    assert "extra_body" not in second_kw, (
        f"Second call (thinking=None) must NOT carry extra_body; got {second_kw!r}"
    )
    assert "reasoning_effort" not in second_kw, (
        f"Second call (thinking=None) must NOT carry reasoning_effort; got {second_kw!r}"
    )

    # self._call_kwargs must be unchanged after both calls
    assert client._call_kwargs == original_call_kwargs, (
        "Per-call thinking override must never mutate self._call_kwargs"
    )
