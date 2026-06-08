---
phase: quick-260608-pbz
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - trezarr/config.py
  - trezarr/translate/engine.py
  - tests/translate/test_envelope_preservation.py
autonomous: true
requirements:
  - deterministic-envelope-preservation

must_haves:
  truths:
    - "D-ENV-01: A source cue fully enclosed in a single outer ( ) bracket pair is re-wrapped in ( ) when the translated output is missing that envelope — Ep-142 cue-1 shape: '(A Record…\\nSeason 3)' → '(Phàm Nhân…\\nPhần 3)'"
    - "D-ENV-02: Full-enclosure detection operates on the stripped joined text of the cue (multi-line joined); the opener at position 0 must span to the LAST character as confirmed by a bracket-depth scan — a mid-sentence aside like 'Anh ấy (cười) nói' is NOT touched, and a two-group source like '(a) and (b)' is NOT touched"
    - "D-ENV-03: The fix is idempotent — a translated cue already wrapped '(Tập 142)' is never double-wrapped '((Tập 142))'"
    - "D-ENV-04: Square-bracket envelopes [ ] are also preserved by the same logic using the matching closer ]"
    - "D-ENV-05: Raw/opaque cues (SubLine.raw is not None) are skipped — the function only processes non-raw translated lines"
    - "D-ENV-06: Byte identity is preserved — index/start_tc/end_tc are copied verbatim onto the new SubLine; raw stays None for translated cues (never mutate source SubLines, Pitfall 8)"
    - "D-ENV-07: The step runs AFTER Pass-4 splice assembles translated_doc and BEFORE Step-9 validate_subdoc gate — a re-wrapped Vietnamese title card with diacritics passes Check 10 (diacritics disqualify the source-passthrough branch) and passes Check 12 (GLOSS_PAREN_RE: LATIN_DIACRITIC_RE exempts diacritic-bearing parens)"
    - "D-ENV-08: enable_envelope_preservation=False is a complete no-op — the step is bypassed, translated_doc is unchanged, exact pre-change behavior is restored"
    - "D-ENV-09: The function _preserve_source_envelopes is pure (no LLM calls, no async, no side effects) — it returns a new SubDoc carrying encoding/line_ending/separators/leading/trailer/envelope forward (D-92 pattern)"
    - "D-ENV-10: Pronoun/term engine is untouched — reconcile.py, attribute.py, validate.py, and the Address-Map are not modified"
  artifacts:
    - path: "trezarr/config.py"
      provides: "enable_envelope_preservation: bool = True toggle in TrezarrSettings"
      contains: "enable_envelope_preservation"
    - path: "trezarr/translate/engine.py"
      provides: "_preserve_source_envelopes(translated_doc, source_doc, settings) + wire in translate_file"
      exports: ["_preserve_source_envelopes"]
    - path: "tests/translate/test_envelope_preservation.py"
      provides: "10 test cases including validate_subdoc gate-compatibility test"
      min_lines: 100
  key_links:
    - from: "trezarr/translate/engine.py:translate_file"
      to: "_preserve_source_envelopes"
      via: "called after Pass-4 translated_doc reassembly, before Step-9 validate_subdoc loop"
      pattern: "_preserve_source_envelopes"
    - from: "trezarr/config.py:TrezarrSettings"
      to: "engine.py:translate_file"
      via: "settings.enable_envelope_preservation guard"
      pattern: "enable_envelope_preservation"
---

<objective>
Deterministically re-wrap bracket envelopes that the LLM drops from title-card cues.

Purpose: The H4 prompt rule (iab) asking deepseek to preserve source parens is unreliable for
all-caps title cards — it is silently ignored and no existing gate check flags the dropped
envelope. This step is the deterministic backstop: purely structural code that restores the
( ) or [ ] wrapper whenever the source was fully enclosed and the translation is not.

Output: _preserve_source_envelopes() in engine.py + enable_envelope_preservation toggle in
config.py + 10 TDD tests covering the full spec (including validate_subdoc gate compatibility).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@trezarr/subtitles/model.py
@trezarr/translate/engine.py
@trezarr/translate/validate.py
@trezarr/config.py
@tests/translate/test_gate_repair.py
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1 (RED): Config toggle + failing tests for _preserve_source_envelopes</name>
  <files>trezarr/config.py, tests/translate/test_envelope_preservation.py</files>
  <behavior>
    - Test 1 (multi-line title card): source "(A Record of Mortal's Journey to Immortality\nUpheaval in Outer Sea Season 3)", translated "Phàm Nhân Tu Tiên Truyện\nNgoại Hải Phong Vân Phần 3" → after _preserve_source_envelopes, translated text = "(Phàm Nhân Tu Tiên Truyện\nNgoại Hải Phong Vân Phần 3)"; timecodes byte-identical.
    - Test 2 (single-line title card): source "(Tập 142)", translated "Tập 142" → "(Tập 142)".
    - Test 3 (square brackets): source "[Note]", translated "Ghi chú" → "[Ghi chú]".
    - Test 4 (idempotent): source "(Tập 142)", translated "(Tập 142)" → unchanged, no double-wrap.
    - Test 5 (mid-sentence aside): source "Anh ấy (cười) nói gì đó.", translated "Anh ấy (cười) nói gì đó." → output untouched (parens are not a full wrapper).
    - Test 6 (source not wrapped): source "Han Lập nói rằng.", translated "Hàn Lập nói rằng." → output untouched.
    - Test 7 (raw/opaque cue): SubLine(raw="some karaoke block") → skipped, output line unchanged.
    - Test 8 (gate compatibility): re-wrapped Vietnamese title card "(Phàm Nhân Tu Tiên Truyện)" is passed to the real validate_subdoc (not mocked) against a matching source doc and must not raise GateError — verifies Check 10 (diacritics disqualify source-passthrough branch) and Check 12 (LATIN_DIACRITIC_RE exempts diacritic-bearing parens).
    - Test 9 (flag off): enable_envelope_preservation=False → no-op, output keeps no parens.
    - Test 10 (two-parens not a full wrapper): source "(a) and (b)" (depth returns to 0 before the final char) → output untouched.
  </behavior>
  <action>
    Add to trezarr/config.py in the Phase 2 Gate section (after enable_gate_repair / gate_repair_max_attempts):

    ```
    # ── Phase 2: Deterministic envelope preservation (pbz) ──────────────────────
    # When True, _preserve_source_envelopes() re-wraps translated cues whose source
    # was fully enclosed in a single ( ) or [ ] bracket pair but whose translation
    # is missing the wrapper. Pure structural post-processing — no LLM calls.
    # Set False to reproduce exact pre-pbz behavior.
    enable_envelope_preservation: bool = True
    ```

    Create tests/translate/test_envelope_preservation.py using the _make_line / _make_doc /
    _settings helpers (copy from test_gate_repair.py — same module-local pattern, lazy imports).
    Import _preserve_source_envelopes from trezarr.translate.engine at call time (not at module
    top, so the test file can be parsed before the function exists — RED phase). Each test
    constructs source_doc and translated_doc via _make_doc(_make_line(...)) then calls
    _preserve_source_envelopes(translated_doc, source_doc, settings).

    Test 8 (gate compat): build a translated_doc whose line 1 text is "(Phàm Nhân Tu Tiên Truyện)"
    and whose remaining lines are valid Vietnamese cues (use "Xin chào." × 4 so diacritic ratio
    passes Check 3). Source doc must have matching index/timecodes, source text "(A Record of
    Mortal's Journey to Immortality)", and the same count of valid cues. Call the real
    validate_subdoc(translated_doc, source_doc, settings) — assert it does NOT raise.

    Run: pytest tests/translate/test_envelope_preservation.py -x
    All tests MUST FAIL (ImportError or AttributeError on _preserve_source_envelopes) — RED confirmed.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_envelope_preservation.py -x 2>&1 | tail -20</automated>
  </verify>
  <done>All 10 tests fail (RED) due to missing _preserve_source_envelopes; enable_envelope_preservation field exists in TrezarrSettings and TrezarrSettings(**{}) constructs without error.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2 (GREEN): Implement _preserve_source_envelopes + wire into translate_file</name>
  <files>trezarr/translate/engine.py</files>
  <behavior>
    All 10 tests in test_envelope_preservation.py pass.
    Full suite (494+ tests) remains green — no regressions.
  </behavior>
  <action>
    Add _preserve_source_envelopes as a module-level pure function in engine.py, near
    _splice_review_corrections (around line 1190). Place it BEFORE _repair_failing_cues.

    Function signature: def _preserve_source_envelopes(translated_doc: SubDoc, source_doc: SubDoc, settings: "TrezarrSettings") -> SubDoc

    Full-enclosure detection (per spec) — THREE steps that ALL must pass:

    Step A — opener/closer character check:
    - opener_map = {'(': ')', '[': ']'}
    - stripped_src = src_line.text.strip()
    - Condition: len(stripped_src) >= 2 AND stripped_src[0] in opener_map AND
      stripped_src[-1] == opener_map[stripped_src[0]]
    - If False: skip this cue (not enclosed), continue to next pair.
    - If True: opener = stripped_src[0], closer = stripped_src[-1]. Proceed to Step B.

    Step B — bracket-depth scan (confirms the opener at position 0 spans to the FINAL position,
    not just that two groups happen to share the same bracket type):
    - Initialize depth = 0.
    - Iterate over each character c in stripped_src along with its index i:
        - If c == opener: depth += 1
        - Elif c == closer: depth -= 1
        - Only the opener/closer type that MATCHES stripped_src[0] participates in the count.
          A '[' inside a '(...)' envelope is plain inner text and does not affect depth.
        - After processing character at index i:
            - If depth == 0 AND i < len(stripped_src) - 1:
                The bracket closed before the end of the string — this is NOT a single spanning
                envelope (e.g. "(a) and (b)" closes at index 2, well before the end).
                Mark as NOT enclosed. Break out of the loop.
    - After the loop: if depth == 0 AND the NOT-enclosed flag was NOT raised (i.e. depth first
      reached 0 exactly at the final character), the cue IS fully enclosed. Otherwise skip.

    Example walkthroughs:
    - "(Tập 142)": depth 0→1 at '(', →0 at ')' which IS index 8 (len-1) → enclosed. PASS.
    - "(a) and (b)": depth 0→1 at '(', →0 at ')' which is index 2, NOT len-1=10 → NOT enclosed. SKIP.
    - "(Season 3 (Finale))": depth 0→1 at outer '(', →2 at inner '(', →1 at inner ')', →0 at
      outer ')' which IS index 19 (len-1) → enclosed. PASS. (Nested title card works correctly.)
    - "Anh ấy (cười) nói": stripped_src[0]='A', NOT in opener_map → Step A fails. SKIP.

    Step C — idempotency check:
    - stripped_trn = trn_line.text.strip()
    - If stripped_trn already starts with opener AND ends with closer → no-op (already wrapped).

    Re-wrap:
    - new_text = opener + trn_line.text + closer
      (Prepend/append to the ORIGINAL .text, not the stripped form — preserves any internal
      leading/trailing whitespace the LLM may have left inside the cue.)
    - Construct new SubLine(index=src_line.index, start_tc=src_line.start_tc,
      end_tc=src_line.end_tc, text=new_text, raw=None) — byte-identical timecodes (D-ENV-06).
    - Collect all lines (re-wrapped or original), return new SubDoc carrying
      encoding/line_ending/separators/leading/trailer/envelope from translated_doc (D-92 pattern).

    IMPORTANT: The function is a pure sync function — no async, no LLM, no DB. The opener_map
    dict is { '(': ')', '[': ']' } — only these two pairs. Do NOT add '{' / '<' / any others.

    Wire into translate_file:
    Insert a new Step 8.6 block AFTER the Pass-4 translated_doc reassembly (after the
    `translated_doc = SubDoc(lines=corrected_lines, ...)` at ~line 1923) and BEFORE the
    "Step 9" comment / while True gate loop:

    ```
    # Step 8.6: Deterministic envelope preservation (pbz).
    # For cues whose SOURCE is fully enclosed in a single outer ( ) or [ ] bracket pair
    # and whose translated output is missing that wrapper, re-wrap deterministically.
    # Pure structural pass — no LLM, no gate. Runs pre-gate so validate_subdoc validates
    # the final wrapped text. enable_envelope_preservation=False → exact pre-pbz behavior.
    if settings.enable_envelope_preservation:
        translated_doc = _preserve_source_envelopes(translated_doc, source_doc, settings)
    ```

    Note: the Pass-4 block is conditional (enable_self_review gate), so Step 8.6 must be
    placed OUTSIDE and AFTER the `if settings.enable_self_review:` block to run regardless
    of whether Pass-4 ran. The correct insertion point is immediately before the "Step 9"
    comment on the line beginning `# Step 9: Document-level validation gate`.

    After implementation: run pytest tests/translate/test_envelope_preservation.py -x
    All 10 MUST pass (GREEN). Then run the full suite.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_envelope_preservation.py tests/translate/test_gate_repair.py tests/translate/test_validate.py -x -q 2>&1 | tail -30</automated>
  </verify>
  <done>All 10 envelope tests pass (GREEN). Gate repair + validate suites remain green. Full suite passes (ruff clean: ruff check trezarr/translate/engine.py trezarr/config.py tests/translate/test_envelope_preservation.py).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM output → engine.py | Translated text arrives from untrusted LLM; envelope step operates on already-parsed SubLines |
| source_doc → _preserve_source_envelopes | Source doc is filesystem-read; full-enclosure check is read-only |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-pbz-01 | Tampering | _preserve_source_envelopes — re-wrap logic | mitigate | Opener/closer map is a closed set {( ), [ ]} only; full-enclosure requires Step A (char check) + Step B (depth scan) — two-group sources like "(a) and (b)" fail Step B and are never re-wrapped |
| T-pbz-02 | Denial of Service | GLOSS_PAREN_RE (Check 12) false-positive on re-wrapped Vietnamese | mitigate | LATIN_DIACRITIC_RE inside Check 12 exempts any parenthetical carrying diacritics; Vietnamese title card has diacritics → exempt; covered by Test 8 driving real validate_subdoc |
| T-pbz-03 | Tampering | Double-wrap if step runs twice | accept | Idempotent guard (Step C): stripped_trn starts with opener AND ends with closer → no-op; Test 4 covers this; no side-effect path re-runs the step |
| T-pbz-SC | Tampering | npm/pip/cargo installs | accept | No new package installs — pure Python implementation using only the existing SubLine/SubDoc model |
</threat_model>

<verification>
Full-suite smoke:
  cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/ -q 2>&1 | tail -10

Ruff clean:
  ruff check trezarr/translate/engine.py trezarr/config.py tests/translate/test_envelope_preservation.py

Moat check (reconcile/attribute untouched):
  git diff --name-only | grep -E "reconcile|attribute"  # must be empty
</verification>

<success_criteria>
- _preserve_source_envelopes() exists in engine.py, is pure/sync, handles (, ), [, ] pairs only.
- Full-enclosure detection uses Step A (char check) + Step B (depth scan) — "(a) and (b)" is correctly rejected by Step B (depth hits 0 at index 2, before the final char).
- enable_envelope_preservation: bool = True exists in TrezarrSettings (config.py).
- Step 8.6 is wired in translate_file after Pass-4 corrected_doc reassembly and before the Step-9 while True loop.
- All 10 tests in test_envelope_preservation.py pass GREEN including the live validate_subdoc gate-compat test (Test 8).
- Full pytest suite (494+ tests) passes with no regressions.
- reconcile.py, attribute.py, validate.py are NOT modified.
- ruff reports zero errors on the changed files.
</success_criteria>

<output>
Create `.planning/quick/260608-pbz-deterministically-preserve-source-bracke/260608-pbz-SUMMARY.md` when done.
</output>
