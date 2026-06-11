"""Deterministic TDD tests for IMP-02: self-correcting batch retry (engine.py).

Design under test:
  - _translate_batch uses a message-accumulating correction loop (not tenacity on
    BatchValidationError) to recover from dropped/wrong-count LLM responses.
  - The correction user-turn references hints as "from my FIRST message" and NEVER
    re-emits "(speaker says: ...)" content — the pronoun-hint moat is never broken.
  - After translate_batch_retry_attempts+1 total LLM calls with no valid response,
    BatchValidationError propagates. Tenacity does NOT add another retry layer on
    BatchValidationError.

All tests use a deterministic FakeLLMClient (no real LLM required).

Async functions run via asyncio_mode="auto" (configured in pyproject.toml).
"""
import pytest

from trezarr.subtitles.model import SubLine
from trezarr.translate.batching import Batch
from trezarr.translate.engine import BatchValidationError, _translate_batch


# ── FakeLLMClient ──────────────────────────────────────────────────────────────

class FakeLLMClient:
    """Deterministic fake LLM client for testing the correction loop.

    Records all message lists passed to each call so tests can inspect the
    correction-turn structure. The scripted responses are consumed in order;
    the last one repeats if call_count exceeds the length of the list.

    call_count starts at 0 and is incremented BEFORE returning so
    ``assert fake_llm.call_count == N`` is a real attribute read.

    Signature matches LLMClient.call() including the thinking kwarg added in
    FIX-B (260607-dbe).
    """

    def __init__(self, scripted_responses: list[str]) -> None:
        self.scripted_responses: list[str] = scripted_responses
        self.call_count: int = 0
        # Each element is a COPY of the messages list at the time of the call.
        self.calls: list[list[dict]] = []

    async def call(
        self,
        messages: list[dict],
        response_model=None,
        model=None,
        thinking=None,
        collector=None,  # 260612-1tm: accept collector kwarg (ignored in fake)
    ) -> str:
        self.calls.append(list(messages))  # snapshot for assertion
        response_idx = min(self.call_count, len(self.scripted_responses) - 1)
        self.call_count += 1
        return self.scripted_responses[response_idx]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_4cue_batch() -> Batch:
    """Return a 4-cue Batch with SubLine objects (no sentinels, plain text)."""
    cues = [
        SubLine(index=str(i), start_tc=f"00:00:0{i},000", end_tc=f"00:00:0{i + 1},000", text=f"Source line {i}")
        for i in range(1, 5)
    ]
    return Batch(cues=cues, context_before=[], context_after=[])


def _make_settings(retry_attempts: int = 1, *, settings_factory):
    """Build a TrezarrSettings with the given retry attempt count."""
    return settings_factory(translate_batch_retry_attempts=retry_attempts)


# ── Test A: Recovery ───────────────────────────────────────────────────────────

async def test_a_recovery_on_second_call(settings_factory):
    """Test A (Recovery): dropped line on call 1, all 4 on call 2 → returns all 4.

    Ep-142 job 8 reproduction: batch has 4 cues, LLM returns only 3 on the first
    call (drops [1]), returns all 4 on the second call. _translate_batch must
    recover and return all 4 translated lines without raising BatchValidationError.
    """
    # Call 1: missing [1]  — triggers BatchValidationError
    call1 = "[2] line two\n[3] line three\n[4] line four"
    # Call 2: all 4 present — correction loop succeeds
    call2 = "[1] line one\n[2] line two\n[3] line three\n[4] line four"
    fake_llm = FakeLLMClient([call1, call2])

    settings = _make_settings(retry_attempts=1, settings_factory=settings_factory)
    batch = _make_4cue_batch()

    result = await _translate_batch(batch, fake_llm, settings)

    assert result == ["line one", "line two", "line three", "line four"], (
        f"Expected all 4 translated lines, got: {result!r}"
    )
    assert fake_llm.call_count == 2, (
        f"Expected exactly 2 LLM calls, got {fake_llm.call_count}"
    )


# ── Test B: Moat ───────────────────────────────────────────────────────────────

async def test_b_moat_correction_turn_has_no_pronoun_hints(settings_factory):
    """Test B (Moat): correction turn at messages[2] NEVER contains '(speaker says:'.

    The pronoun hints appear in messages[0] (the original prompt). The correction
    user-turn at messages[2] must reference hints as 'from my FIRST message' and
    must NEVER re-emit the "(speaker says: X; addresses as: Y)" content.
    """
    call1 = "[2] line two\n[3] line three\n[4] line four"
    call2 = "[1] line one\n[2] line two\n[3] line three\n[4] line four"
    fake_llm = FakeLLMClient([call1, call2])

    settings = _make_settings(retry_attempts=1, settings_factory=settings_factory)
    batch = _make_4cue_batch()

    # Supply pronoun hints so "(speaker says:" WOULD appear in messages[0].
    pronoun_hints = {1: ("ta", "ngươi")}

    await _translate_batch(batch, fake_llm, settings, pronoun_hints=pronoun_hints)

    # Verify messages[0] contains the hint (setup sanity check)
    assert fake_llm.call_count == 2, "Expected 2 calls for setup"
    first_call_messages = fake_llm.calls[0]
    assert "(speaker says:" in first_call_messages[0]["content"], (
        "Setup check: expected '(speaker says:' in messages[0] (the original prompt)"
    )

    # CORE MOAT ASSERTION: correction turn (messages[2] of the second call) must
    # NOT contain "(speaker says:" — the pronoun hint must never be re-emitted.
    second_call_messages = fake_llm.calls[1]
    # messages[2] is the correction user-turn
    assert len(second_call_messages) >= 3, (
        f"Expected at least 3 messages in second call, got {len(second_call_messages)}: {second_call_messages}"
    )
    correction_turn = second_call_messages[2]
    assert correction_turn["role"] == "user", (
        f"Expected messages[2] to be a user turn, got role={correction_turn['role']!r}"
    )
    assert "(speaker says:" not in correction_turn["content"], (
        "MOAT VIOLATION: correction turn contains '(speaker says:' — "
        "pronoun hints must NEVER be re-emitted in the correction user-turn. "
        f"Correction content: {correction_turn['content']!r}"
    )


# ── Test C: Correction phrasing ────────────────────────────────────────────────

async def test_c_correction_turn_phrasing(settings_factory):
    """Test C (Correction phrasing): correction turn describes the defect and re-affirms rules.

    The correction user-turn must contain:
    - A description of the structural defect (the specific missing line number from
      the BatchValidationError message, e.g. "Missing line [1]").
    - A re-affirmation of the rules/glossary/hints from the first message.
    """
    call1 = "[2] line two\n[3] line three\n[4] line four"
    call2 = "[1] line one\n[2] line two\n[3] line three\n[4] line four"
    fake_llm = FakeLLMClient([call1, call2])

    settings = _make_settings(retry_attempts=1, settings_factory=settings_factory)
    batch = _make_4cue_batch()

    await _translate_batch(batch, fake_llm, settings)

    second_call_messages = fake_llm.calls[1]
    correction_turn_content = second_call_messages[2]["content"]

    # Must mention the missing line number (defect description from BatchValidationError)
    assert "Missing line [1]" in correction_turn_content or "missing" in correction_turn_content.lower(), (
        f"Expected defect description ('Missing line [1]' or 'missing') in correction turn, "
        f"got: {correction_turn_content!r}"
    )

    # Must re-affirm rules/glossary/hints from the first message (the moat re-affirmation phrase)
    re_affirmation_present = any(
        keyword in correction_turn_content
        for keyword in ("GLOSSARY", "hints", "rules", "RULES", "FIRST message", "first message")
    )
    assert re_affirmation_present, (
        f"Expected a rules/glossary/hints re-affirmation phrase in correction turn, "
        f"got: {correction_turn_content!r}"
    )


# ── Test D: Budget exhaustion ──────────────────────────────────────────────────

async def test_d_budget_exhaustion_raises_after_max_calls(settings_factory):
    """Test D (Budget exhaustion): always-bad LLM → BatchValidationError after max calls.

    With translate_batch_retry_attempts=1, total allowed LLM calls = 2 (1 initial + 1
    retry). When the LLM always drops line [1], BatchValidationError must propagate
    after exactly 2 LLM calls. No more calls must happen.
    """
    always_bad = "[2] line two\n[3] line three\n[4] line four"
    fake_llm = FakeLLMClient([always_bad])  # always returns the same bad response

    settings = _make_settings(retry_attempts=1, settings_factory=settings_factory)
    batch = _make_4cue_batch()

    with pytest.raises(BatchValidationError):
        await _translate_batch(batch, fake_llm, settings)

    assert fake_llm.call_count == 2, (
        f"Expected exactly 2 LLM calls (1 initial + 1 retry), got {fake_llm.call_count}"
    )


# ── Test E: No retry storm ─────────────────────────────────────────────────────

async def test_e_no_tenacity_storm_on_batch_validation_error(settings_factory):
    """Test E (No storm): tenacity does NOT add an extra retry layer on BatchValidationError.

    With translate_batch_retry_attempts=1, total allowed calls = 2. The call_count
    on the FakeLLMClient must be EXACTLY translate_batch_retry_attempts + 1 = 2.
    If tenacity also caught BatchValidationError, the count would be higher
    (e.g. 4 for 2 tenacity retries on top of 2 correction retries).
    """
    always_bad = "[2] line two\n[3] line three\n[4] line four"
    fake_llm = FakeLLMClient([always_bad])

    settings = _make_settings(retry_attempts=1, settings_factory=settings_factory)
    batch = _make_4cue_batch()

    with pytest.raises(BatchValidationError):
        await _translate_batch(batch, fake_llm, settings)

    # EXACTLY retry_attempts + 1 calls — no multiplicative tenacity storm.
    expected_calls = settings.translate_batch_retry_attempts + 1
    assert fake_llm.call_count == expected_calls, (
        f"Expected exactly {expected_calls} LLM calls (no tenacity storm on BatchValidationError), "
        f"got {fake_llm.call_count}. If tenacity also caught BatchValidationError, "
        "the count would be higher."
    )
