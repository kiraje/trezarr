---
phase: quick-260607-dbe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - trezarr/config.py
  - trezarr/llm/client.py
  - trezarr/translate/engine.py
  - trezarr/translate/attribute.py
  - trezarr/bible/analyze.py
  - tests/llm/test_client_thinking.py
  - tests/translate/test_engine.py
  - tests/translate/test_attribute.py
  - tests/bible/test_analyze.py
autonomous: true
requirements:
  - "FIX-A: unhinted-line name-substitution guardrail in Pass-3"
  - "FIX-B: per-pass reasoning (thinking) override on Pass-1 and Pass-2"

must_haves:
  truths:
    - "Per-call thinking=True on LLMClient.call() produces extra_body={'thinking':{'type':'enabled'}} plus reasoning_effort across all three tiers without mutating self._call_kwargs"
    - "Per-call thinking=False on LLMClient.call() produces extra_body={'thinking':{'type':'disabled'}} for that call only, overriding the global default"
    - "thinking=None (default) leaves self._call_kwargs unchanged — no regression for existing callers"
    - "attribute_batch() passes thinking=settings.enable_reasoning_attribution to llm_client.call()"
    - "_analyze_one_chunk() passes thinking=settings.enable_reasoning_analysis to llm_client.call()"
    - "_translate_batch() does NOT pass a thinking argument (stays on global default)"
    - "build_translate_prompt emits a numbered RULE for unhinted lines instructing the model to use a register-aware neutral 2nd-person pronoun (ngươi/các hạ for classical; anh/em/bạn for modern) and NEVER substitute a character name when no speaker/addressee hint is present"
    - "Guardrail rule text adapts to the register argument: classical xianxia/wuxia/cultivation text differs from modern text"
    - "All existing tests pass; no regression on the 12-check validation gate, sentinel/<<BR>> protocol, or tier-fallback semantics"
  artifacts:
    - path: trezarr/config.py
      provides: "New config knobs: enable_reasoning_analysis, enable_reasoning_attribution, llm_reasoning_effort"
    - path: trezarr/llm/client.py
      provides: "per-call thinking: bool | None override on call() and _call_with_fallback()"
    - path: trezarr/translate/engine.py
      provides: "register-aware unhinted-line guardrail RULE in build_translate_prompt"
    - path: trezarr/translate/attribute.py
      provides: "thinking kwarg threaded into llm_client.call()"
    - path: trezarr/bible/analyze.py
      provides: "thinking kwarg threaded into llm_client.call() inside _analyze_one_chunk"
    - path: tests/llm/test_client_thinking.py
      provides: "per-call override tests for all three tiers + no-leak test"
    - path: tests/translate/test_engine.py
      provides: "guardrail rule presence tests (classical + modern register)"
    - path: tests/translate/test_attribute.py
      provides: "attribute_batch passes thinking kwarg test"
    - path: tests/bible/test_analyze.py
      provides: "analyze_file passes thinking kwarg test"
  key_links:
    - from: trezarr/translate/attribute.py
      to: trezarr/llm/client.py
      via: "llm_client.call(thinking=settings.enable_reasoning_attribution)"
    - from: trezarr/bible/analyze.py
      to: trezarr/llm/client.py
      via: "llm_client.call(thinking=settings.enable_reasoning_analysis)"
    - from: trezarr/llm/client.py
      to: DeepSeek API
      via: "extra_body={'thinking':{'type':'enabled'}, 'reasoning_effort': settings.llm_reasoning_effort}"
---

<objective>
Fix two independent bugs that together cause Pass-3 to invert speaker/addressee for cues
where attribution resolves to None (unknown character).

FIX A — Unhinted-line guardrail: add a numbered RULE to build_translate_prompt that
explicitly instructs the model to render unanchored 2nd-person pronouns ("you/your") as a
register-aware Vietnamese pronoun and NEVER substitute a character name when no
(speaker says / addresses as) hint is present on the line. The rule is register-aware:
classical/xianxia/wuxia/cultivation registers get classical pronoun examples; modern
registers get modern pronoun examples.

FIX B — Per-pass reasoning override: add thinking: bool | None = None to
LLMClient.call() and _call_with_fallback(). True forces enabled+reasoning_effort; False
forces disabled; None preserves the global self._call_kwargs default unchanged. Three new
config knobs: enable_reasoning_analysis (default True), enable_reasoning_attribution
(default True), llm_reasoning_effort (default "high"). Thread thinking into Pass-1
(analyze_file) and Pass-2 (attribute_batch) only; Pass-3 and Pass-4 are untouched.

Purpose: restore speaker-direction fidelity for unattributed cues (Ep-142 cue 33-34 failure)
and give attribution the reasoning horsepower it needs when the global disable flag is set.

Output:
  - trezarr/config.py  (3 new fields)
  - trezarr/llm/client.py  (thinking param on call + _call_with_fallback; per-call extra_body)
  - trezarr/translate/engine.py  (guardrail RULE in build_translate_prompt)
  - trezarr/translate/attribute.py  (thinking= kwarg on llm_client.call)
  - trezarr/bible/analyze.py  (thinking= kwarg on llm_client.call in _analyze_one_chunk)
  - 4 test files extended/added
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@trezarr/llm/client.py
@trezarr/config.py
@trezarr/translate/engine.py
@trezarr/translate/attribute.py
@trezarr/bible/analyze.py
@trezarr/translate/reconcile.py
@tests/llm/test_client_thinking.py
@tests/translate/test_engine.py
@tests/translate/test_attribute.py
@tests/bible/test_analyze.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: FIX-B — Per-call thinking override in LLMClient + new config knobs</name>
  <files>trezarr/config.py, trezarr/llm/client.py, tests/llm/test_client_thinking.py</files>
  <behavior>
    - test_per_call_thinking_true_tier1: call(thinking=True) → parse() receives extra_body={"thinking":{"type":"enabled"}} and reasoning_effort="high" (from llm_reasoning_effort config default)
    - test_per_call_thinking_true_tier2: same with json_object mode
    - test_per_call_thinking_true_tier3: same with text mode
    - test_per_call_thinking_false_overrides_global_default: when global default is empty (llm_disable_thinking=False), call(thinking=False) still forces the disabled extra_body on that one call
    - test_per_call_thinking_none_no_change: call(thinking=None) → extra_body identical to what the global self._call_kwargs produces (no override)
    - test_per_call_thinking_does_not_leak: two sequential calls — first with thinking=True, second with thinking=None — second call must not carry reasoning_effort or the enabled extra_body
    - test_config_new_fields_defaults: TrezarrSettings() has enable_reasoning_analysis=True, enable_reasoning_attribution=True, llm_reasoning_effort="high"
  </behavior>
  <action>
    In trezarr/config.py, after the existing llm_disable_thinking line (~line 69), add three new fields inside TrezarrSettings:

      enable_reasoning_analysis: bool = True
      enable_reasoning_attribution: bool = True
      llm_reasoning_effort: str = "high"

    Add docstrings/comments consistent with the surrounding style: enable_reasoning_analysis/enable_reasoning_attribution gate Pass-1/Pass-2 thinking; llm_reasoning_effort maps to DeepSeek's top-level reasoning_effort param when thinking is forced enabled.

    In trezarr/llm/client.py, add thinking: bool | None = None to both call() and _call_with_fallback() signatures. Update call() to forward thinking to _call_with_fallback(). In _call_with_fallback():

    1. Compute effective_call_kwargs at the TOP of the method (before the tier branches), using this logic:
       - If thinking is None → use self._call_kwargs unchanged (current behaviour, zero risk)
       - If thinking is False → build {"extra_body": {"thinking": {"type": "disabled"}}} locally; do NOT reference self._call_kwargs at all for this call
       - If thinking is True → build {"extra_body": {"thinking": {"type": "enabled"}}, "reasoning_effort": settings_reasoning_effort} locally. The effort value must come from a stored attribute self._reasoning_effort (set from settings.llm_reasoning_effort in __init__). Do NOT reference self._call_kwargs.

    2. In __init__, store self._reasoning_effort = settings.llm_reasoning_effort.

    3. Replace the three **self._call_kwargs spreads (lines ~145, ~189, ~204) with **effective_call_kwargs.

    4. Do NOT mutate self._call_kwargs anywhere. effective_call_kwargs is a local variable per call.

    5. Update the docstring for call() and _call_with_fallback() to document the thinking param.

    Add tests to tests/llm/test_client_thinking.py following the existing mock pattern (_ok_parse / _ok_create helpers). Each test uses settings_factory() fixture with appropriate mode flags. The test for True on Tier 1 patches parse, verifies extra_body and reasoning_effort in call_args.kwargs. The no-leak test runs two awaited calls in sequence and inspects both.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/llm/test_client_thinking.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>All tests in test_client_thinking.py pass including the 7 new tests; no existing test regresses; self._call_kwargs is never mutated.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: FIX-A — Unhinted-line guardrail in build_translate_prompt</name>
  <files>trezarr/translate/engine.py, tests/translate/test_engine.py</files>
  <behavior>
    - test_guardrail_rule_present_no_register: build_translate_prompt with no register, no pronoun_hints → prompt contains the guardrail keyword "no speaker/addressee hint" and modern pronoun examples (anh/em/bạn)
    - test_guardrail_rule_present_classical_register: build_translate_prompt with register="xianxia" → prompt contains the guardrail keyword and classical pronoun examples (ngươi/các hạ)
    - test_guardrail_rule_present_modern_register: build_translate_prompt with register="romantic" → prompt contains modern pronoun examples (anh/em/bạn), not classical
    - test_guardrail_rule_does_not_affect_hinted_lines: when all lines have pronoun_hints, the hint "(speaker says: X; addresses as: Y)" is still emitted correctly on the line
    - test_guardrail_rule_numbering_sequential: when both glossary and register are supplied, all RULES are numbered sequentially without gaps (no duplicate rule_n values)
  </behavior>
  <action>
    In trezarr/translate/engine.py, inside build_translate_prompt(), add a new numbered RULE after the existing last rule (currently the mixed-gender plural rule). Insert it before the closing parts.append("") that ends the RULES block.

    The rule text must:
    1. State the condition: "For any line WITHOUT a (speaker says / addresses as) hint..."
    2. Instruct: "...render English 'you/your/yourself' as a register-appropriate 2nd-person Vietnamese pronoun — NEVER substitute a character name."
    3. Branch on register (use the same _is_classical_register() helper already used in reconcile.py, or inline an equivalent local check using the existing register variable already in scope):
       - Classical/historical/wuxia/xianxia/cultivation: "Use ngươi or các hạ (not a proper name)."
       - Modern (or no register): "Use anh, em, or bạn depending on context (not a proper name)."

    The check for classical register should match the same keywords already in the register RULE block (lines ~309-317): classical / historical / wuxia / xianxia / cultivation. A simple `register and any(k in register.lower() for k in ("classical","historical","wuxia","xianxia","cultivation","cổ trang","tiên hiệp","kiếm hiệp"))` condition is sufficient — do not import from reconcile.py.

    Increment rule_n after appending. Keep the existing final parts.append("") that terminates the RULES block in its original position.

    Do NOT add a [HINTS] section or change how pronoun_hints is applied to individual lines (the existing "(speaker says: X; addresses as: Y)" format on hinted lines is unchanged).

    Add tests to tests/translate/test_engine.py following the existing pytest style (no @pytest.mark.asyncio needed, these are sync tests on build_translate_prompt).
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_engine.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>All tests in test_engine.py pass including the 5 new guardrail tests; prompt rule numbering is sequential; existing engine tests are green.</done>
</task>

<task type="auto">
  <name>Task 3: Thread thinking into Pass-1 and Pass-2; verify full suite</name>
  <files>trezarr/translate/attribute.py, trezarr/bible/analyze.py, tests/translate/test_attribute.py, tests/bible/test_analyze.py</files>
  <action>
    In trezarr/translate/attribute.py, in attribute_batch(), find the existing llm_client.call() call (~line 298) and add the keyword argument thinking=settings.enable_reasoning_attribution. The settings parameter is already present in the function signature.

    In trezarr/bible/analyze.py, in the nested _analyze_one_chunk() helper (~line 401), find the llm_client.call() call and add thinking=settings.enable_reasoning_analysis. The settings parameter is in the enclosing analyze_file() scope (it is captured by _analyze_one_chunk via closure).

    Do NOT touch _translate_batch or _review_batch in engine.py — those stay on the global default (no thinking kwarg).

    Add tests:

    tests/translate/test_attribute.py — add test_attribute_batch_passes_thinking_kwarg:
    Mock llm_client.call as AsyncMock returning a minimal valid BatchAttribution JSON string.
    Call attribute_batch() with settings.enable_reasoning_attribution=True.
    Assert llm_client.call was called with thinking=True.
    Add test_attribute_batch_passes_thinking_false_when_disabled:
    settings.enable_reasoning_attribution=False → the fast-path returns early before the call, so no assertion on the call is needed — just verify the function returns without raising.

    tests/bible/test_analyze.py — add test_analyze_file_passes_thinking_kwarg:
    Mock llm_client.call as AsyncMock returning a minimal valid BibleAnalysis JSON string (empty characters/terms/events, no register_value).
    Call analyze_file() with settings.enable_reasoning_analysis=True.
    Assert llm_client.call was called with keyword argument thinking=True.

    Follow the existing test fixtures and async def pattern already established in those files (asyncio_mode="auto", settings_factory, mock bible/arr_metadata helpers if already present).

    After all changes, run the full test suite to confirm no regressions.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/ -x -q 2>&1 | tail -30</automated>
  </verify>
  <done>Full test suite passes; attribute_batch and analyze_file both pass the correct thinking kwarg; no thinking kwarg is present in _translate_batch or _review_batch calls (verify with grep -n "thinking" trezarr/translate/engine.py — result must be empty or only appear in comments).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| config → LLM API | New extra_body fields forwarded to external endpoint; a misconfigured llm_reasoning_effort string is passed as-is |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-dbe-01 | Tampering | effective_call_kwargs construction | mitigate | Build as a local variable per call; never mutate self._call_kwargs; tests assert no leakage between consecutive calls |
| T-dbe-02 | Denial of Service | reasoning_effort="max" with slow endpoint | accept | User-configurable; default "high"; same timeout as existing calls; no SDK change |
| T-dbe-SC | Tampering | npm/pip installs | accept | No new package installs in this fix |
</threat_model>

<verification>
1. python -m pytest tests/llm/test_client_thinking.py -x -q — all thinking tests including new per-call override tests pass
2. python -m pytest tests/translate/test_engine.py -x -q — guardrail rule tests pass
3. python -m pytest tests/translate/test_attribute.py tests/bible/test_analyze.py -x -q — thinking threading tests pass
4. python -m pytest tests/ -x -q — full suite green, no regressions
5. grep -n "thinking" trezarr/translate/engine.py — must not appear in _translate_batch or _review_batch call sites
</verification>

<success_criteria>
- LLMClient.call(thinking=True) injects enabled+reasoning_effort on all three tiers for that call only; self._call_kwargs is unchanged after the call.
- LLMClient.call(thinking=None) (default) is behaviourally identical to the pre-fix code for all existing callers.
- attribute_batch and _analyze_one_chunk pass thinking= derived from their respective settings flags; _translate_batch and _review_batch do not.
- build_translate_prompt includes a numbered guardrail RULE that names register-appropriate 2nd-person pronouns and explicitly forbids substituting a character name for unhinted lines; the rule varies between classical and modern registers.
- All existing tests remain green.
</success_criteria>

<output>
Create .planning/quick/260607-dbe-fix-attribution-hint-gap-guardrail-per-p/260607-dbe-SUMMARY.md when done.
</output>
