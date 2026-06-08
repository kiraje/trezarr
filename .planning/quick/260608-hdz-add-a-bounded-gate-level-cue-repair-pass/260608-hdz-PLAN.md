---
phase: quick-260608-hdz
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - trezarr/config.py
  - trezarr/translate/engine.py
  - tests/translate/test_gate_repair.py
autonomous: true
requirements: [IMP-02b]
must_haves:
  truths:
    - "enable_gate_repair: bool = True and gate_repair_max_attempts: int = 3 exist in TrezarrSettings with matching TREZARR_ env-var prefix (IMP-02b config D-06-style)"
    - "repairable gate-check set is exactly {3, 9, 10, 11, 12}; structural checks {1,2,4,5,6,7,8} immediately quarantine without calling the repair LLM"
    - "enable_gate_repair=False reproduces exact current behavior: first GateError quarantines, _repair_failing_cues is never called"
    - "gate stays the sole arbiter: repaired doc must PASS a real validate_subdoc call before write; nothing defective ships"
    - "repair re-translates failing cues through existing Pass-3 machinery (build_translate_prompt + _translate_batch) with injected CORRECTION directive, same glossary_lines / register_value / resolved_map pronoun hints as original Pass-3, so Bible consistency is preserved and the pronoun/relational moat is untouched"
    - "repair uses the existing LLMClient (its semaphore is the sole concurrency gate); no new asyncio.Semaphore and no per-call tenacity added"
    - "budget is bounded at gate_repair_max_attempts attempts; if repair cannot fix within budget, the file quarantines via the same _write_quarantine + ledger.record path as today"
    - "reconcile.py, attribute.py, and Address-Map logic are NOT touched"
    - "repaired SubLine objects preserve index/start_tc/end_tc byte-identically from the translated_doc; only .text is replaced"
    - "test_gate_repair.py covers: (1) honorific repair success Check-11, (2) structural Check-1/Check-8 not repaired, (3) budget exhaustion quarantines, (4) moat regression: resolved_map hint + glossary forwarded to repair, (5) enable_gate_repair=False quarantines on first GateError"
---

<objective>
Implement IMP-02b: a bounded gate-level cue-repair pass in translate_file() so a single
re-translatable defective cue (e.g. Check-11 "Miss Mei, chúng ta nên đi thôi.") cannot
quarantine a 269-cue episode.

Purpose: Jobs 8/9/10 each quarantined all of Ep-142 on ONE straggler cue. The gate today
raises GateError and immediately quarantines the whole file. This plan wraps the Step-9
validate_subdoc call in a bounded loop that re-translates only the failing source cues (not
the whole file), re-validates, and only quarantines if the budget is exhausted or the check
is structural.

Output:
  - trezarr/config.py: two new settings fields
  - trezarr/translate/engine.py: _repair_failing_cues() async helper + repair loop wrapping Step 9
  - tests/translate/test_gate_repair.py: 5 targeted tests (all must pass green)
</objective>

<execution_context>
@/Users/dustin/.claude/get-shit-done/workflows/execute-plan.md
@/Users/dustin/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260608-hdz-add-a-bounded-gate-level-cue-repair-pass/260608-hdz-PLAN.md

# Key source files — read before writing any code
@trezarr/config.py
@trezarr/translate/engine.py
@trezarr/translate/validate.py
@tests/translate/test_validate.py
@tests/translate/test_engine.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add config fields + write failing RED tests</name>
  <files>trezarr/config.py, tests/translate/test_gate_repair.py</files>
  <behavior>
    - Config fields exist: `enable_gate_repair: bool = True` and `gate_repair_max_attempts: int = 3`
    - TrezarrSettings(enable_gate_repair=False) does not raise
    - test_honorific_repair_success: a translated doc containing "Miss Mei, chúng ta nên đi thôi." at cue index 0 triggers Check-11 GateError; with enable_gate_repair=True and a mock LLM returning "Cô Mai, chúng ta nên đi thôi.", translate_file returns status="done" and no GateError escapes
    - test_structural_not_repaired: a cue-count-1 doc vs source-count-2 triggers Check-1; _repair_failing_cues is NOT called (assert mock LLM call_count == 0); status="quarantined"
    - test_budget_exhausted: mock LLM always returns a still-leaking honorific cue; after gate_repair_max_attempts attempts status="quarantined"; assert LLM repair call count == gate_repair_max_attempts
    - test_moat_regression: capture the kwargs passed to the repair LLM call; assert (a) resolved_map pronoun hint for the failing cue index was forwarded, (b) glossary_lines was forwarded, (c) the new SubLine at the repaired index has identical index/start_tc/end_tc to the original translated_doc line
    - test_gate_repair_disabled: TrezarrSettings(enable_gate_repair=False); a Check-11 defect quarantines immediately; assert mock repair LLM was NOT called
  </behavior>
  <action>
    In trezarr/config.py, add two fields under the "Phase 2: Retry + quarantine (D-18)" section (after `translate_batch_retry_attempts`). Follow the exact field/comment style of neighbors:

    ```
    # ── Phase 2: Gate-level cue repair (IMP-02b) ──────────────────────────────────
    # When True, translate_file() attempts to re-translate only the failing cue(s)
    # on a repairable GateError check ({3, 9, 10, 11, 12}) before quarantining.
    # Set False to reproduce exact pre-IMP-02b quarantine-on-first-GateError behavior.
    enable_gate_repair: bool = True
    # Maximum repair attempts per file. Each attempt is one small LLM call translating
    # only the failing source cues. Budget is decremented on each attempt; if exhausted
    # the file quarantines via the standard path. Default 3 covers ~3 distinct straggler
    # cues (fail-fast gate surfaces one failing cue at a time in many check variants).
    gate_repair_max_attempts: int = 3
    ```

    Write tests/translate/test_gate_repair.py from scratch. Use pytest-asyncio (asyncio_mode=auto
    via conftest.ini; no @pytest.mark.asyncio needed). Use the existing _make_line / _make_doc /
    _settings helpers (copy the pattern from test_validate.py — define them locally in this file
    as module-level helpers). Build a FakeLedger that stores records in a dict and implement the
    async check/record methods. Build a FakeLLMClient that returns canned responses from a list;
    exhaust list → raise StopAsyncIteration to detect over-calling.

    Each test calls translate_file() with a real tmp_path SRT file (same pattern as
    test_translate_file_read_failure_quarantines in test_engine.py). The SRT file for the
    honorific tests must contain exactly ONE cue: "Miss Mei, chúng ta nên đi thôi." so validate
    Check-11 fires. Use monkeypatch or unittest.mock.patch to intercept the actual LLM call
    inside _translate_batch to return the Pass-3 translation, and intercept the repair LLM call
    inside _repair_failing_cues (once it exists) to return either the fixed cue or the broken one.

    At this stage the tests MUST FAIL (RED) because _repair_failing_cues does not exist yet.
    Confirm RED before committing; commit: `test(260608-hdz): RED gate-repair tests`
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_gate_repair.py -x --tb=short 2>&1 | tail -20</automated>
  </verify>
  <done>
    Config fields present (grep confirms `enable_gate_repair` and `gate_repair_max_attempts` in
    trezarr/config.py). All 5 tests in test_gate_repair.py are collected; they FAIL (RED) because
    the engine helper does not exist yet. Full test suite (excluding test_gate_repair.py) still
    passes: `python -m pytest --ignore=tests/translate/test_gate_repair.py -q` green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement _repair_failing_cues + repair loop to GREEN</name>
  <files>trezarr/translate/engine.py</files>
  <behavior>
    - _repair_failing_cues(failing_indices, source_doc, translated_doc, check_number, llm_client, settings, glossary_lines, register_value, resolved_map, bible, model) -> list[SubLine] | None
    - Returns a NEW list of SubLine objects (full translated_doc length) with only the failing indices replaced; returns None on any LLM/parse failure; never raises
    - Replacement SubLine objects have index/start_tc/end_tc byte-identical to the corresponding translated_doc.lines[i]; only .text is replaced with the repair translation
    - Uses build_translate_prompt with a CORRECTION directive prepended to the batch_texts list prefix, same glossary_lines, same register_value, and resolved_map pronoun hints for failing cue indices (1-based within the repair batch)
    - The repair call goes through the same _translate_batch machinery (which uses LLMClient._semaphore as the sole concurrency gate); no new Semaphore, no tenacity
    - Step-9 validate_subdoc call is wrapped in a repair loop: if enable_gate_repair=False or check not in {3,9,10,11,12} or failing_indices empty or budget=0, quarantine immediately (current path unchanged). Otherwise decrement budget, call _repair_failing_cues, splice result back as new translated_doc, and re-validate
  </behavior>
  <action>
    Add `_repair_failing_cues` as a new async helper immediately above the `# Step 9` comment
    (after _splice_review_corrections, before the Step-9 validate_subdoc call). Signature:

      async def _repair_failing_cues(
          failing_indices: list[int],
          source_doc: SubDoc,
          translated_doc: SubDoc,
          check_number: int,
          llm_client: LLMClient,
          settings: TrezarrSettings,
          glossary_lines: list[str] | None,
          register_value: str | None,
          resolved_map: dict,
          bible: object,
          model: str | None,
      ) -> list[SubLine] | None:

    Implementation:
    1. Build correction directive from check_number using a mapping dict (defined at module level
       as _REPAIR_DIRECTIVE: dict[int, str]):
         3  → "One or more lines lacked Vietnamese diacritics (possible source-language passthrough). Translate EVERY line in full Vietnamese with proper diacritics."
         9  → "One or more lines contained CJK/Hangul/Kana script (source leak). Translate ALL script characters into Vietnamese — output NO CJK, Hangul, or Kana codepoints."
         10 → "One or more lines appear to be source-language passthrough (no Vietnamese diacritics, all tokens matching source). Translate fully into Vietnamese."
         11 → "A prior attempt left an English honorific+name untranslated (e.g. 'Miss Mei', 'Mr. Han'). Render EVERY name in its Vietnamese Hán-Việt form and EVERY honorific/title as a kinship/address word (cô / cô nương / tiền bối / huynh / trưởng lão / …). NEVER output an English honorific like 'Miss/Mr/Elder + Name'."
         12 → "A prior attempt added an English-gloss parenthetical (e.g. '(Miss Mei's brother)'). NEVER add parentheticals not in the source. Remove any English-gloss parenthetical from the output."
    2. Extract only the SOURCE cues at failing_indices (0-based) from source_doc.lines.
    3. Build a repair batch_texts list: [f"[CORRECTION REQUIRED — see below]\n{directive}"] prefix line
       is NOT part of batch_texts — instead, prepend it as a single-item context_before entry so
       the numbered protocol is unaffected (batch_texts = [source_doc.lines[i].text for i in failing_indices]).
       Pass the directive as context_before=["[CORRECTION REQUIRED] " + directive].
    4. Build pronoun_hints for the repair batch: 1-based index within failing_indices maps to the
       resolved_map hint for that cue (same logic as per_batch_hints construction, but scoped to
       failing_indices only). Reuse _resolve_char_id + name_to_char_id from bible if bible is not None.
    5. Call the existing _translate_batch function (not a new one) with the repair batch, forwarding
       llm_client, settings, pronoun_hints, model, glossary_lines, register_value. _translate_batch
       uses LLMClient._semaphore as the sole concurrency gate and handles all retries internally.
    6. On BatchValidationError or any Exception → log a warning, return None.
    7. On success: build the repaired SubLine list. Walk translated_doc.lines; for each line at a
       failing index, replace .text with the repair translation. Preserve index/start_tc/end_tc
       byte-identically; return a NEW SubLine (never mutate). Return the full repaired lines list.

    MODULE-LEVEL CONSTANT (add near the _STRUCT_CORRECTION_MSG constant):
      _REPAIRABLE_CHECKS: frozenset[int] = frozenset({3, 9, 10, 11, 12})

    REPAIR LOOP (replace the existing Step-9 try/except GateError block):

      _repair_budget = settings.gate_repair_max_attempts
      while True:
          try:
              validate_subdoc(translated_doc, source_doc, settings, proper_noun_allowlist=proper_noun_allowlist)
              break  # gate passed — proceed to write
          except GateError as exc:
              check = exc.failure.check
              failing = exc.failure.failing_indices or []
              _can_repair = (
                  settings.enable_gate_repair
                  and check in _REPAIRABLE_CHECKS
                  and bool(failing)
                  and _repair_budget > 0
              )
              if not _can_repair:
                  # Standard quarantine path (unchanged from pre-IMP-02b)
                  reason = str(exc)
                  quarantine_path = _write_quarantine(path, reason, failing, settings)
                  await ledger.record(LedgerEntry(
                      source_path=str(path),
                      output_path=None,
                      status="quarantined",
                      content_hash=content_hash,
                      quarantine_path=str(quarantine_path),
                  ))
                  return TranslationResult(status="quarantined", quarantine_path=quarantine_path, reason=reason)
              _repair_budget -= 1
              logger.info(
                  "Gate repair attempt (budget=%d remaining): check=%d failing=%r",
                  _repair_budget, check, failing,
              )
              repaired_lines = await _repair_failing_cues(
                  failing_indices=failing,
                  source_doc=source_doc,
                  translated_doc=translated_doc,
                  check_number=check,
                  llm_client=llm_client,
                  settings=settings,
                  glossary_lines=glossary_lines,
                  register_value=register_value,
                  resolved_map=resolved_map,
                  bible=bible,
                  model=model,
              )
              if repaired_lines is None:
                  # Repair LLM failed — treat as budget exhausted, quarantine now
                  reason = str(exc)
                  quarantine_path = _write_quarantine(path, reason, failing, settings)
                  await ledger.record(LedgerEntry(
                      source_path=str(path),
                      output_path=None,
                      status="quarantined",
                      content_hash=content_hash,
                      quarantine_path=str(quarantine_path),
                  ))
                  return TranslationResult(status="quarantined", quarantine_path=quarantine_path, reason=reason)
              # Splice repaired cues → new translated_doc → re-validate
              translated_doc = SubDoc(
                  lines=repaired_lines,
                  encoding=translated_doc.encoding,
                  line_ending=translated_doc.line_ending,
                  separators=translated_doc.separators,
                  leading=translated_doc.leading,
                  trailer=translated_doc.trailer,
                  envelope=translated_doc.envelope,
              )
      # (proceed to Step 10 write as today)

    VARIABLES AVAILABLE at the repair loop site (already bound in translate_file scope):
      path, settings, llm_client, ledger, content_hash, source_doc, translated_doc,
      proper_noun_allowlist, glossary_lines, register_value, resolved_map, bible, model

    NOTE: resolved_map may be an empty dict when Bible-unaware (not None); _repair_failing_cues
    must tolerate this (no pronoun hints computed, which is safe — falls back to unhinted lines).

    Do NOT touch reconcile.py, attribute.py, or any Address-Map logic.
    Do NOT add a new asyncio.Semaphore (D-06 Pitfall 1).
    Do NOT add tenacity around the repair LLM call (Pitfall 5 — SDK handles retries).
    Run ruff check + ruff format before committing.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_gate_repair.py -v --tb=short && python -m pytest -q --tb=short 2>&1 | tail -10</automated>
  </verify>
  <done>
    All 5 tests in test_gate_repair.py pass GREEN. Full suite passes (484+ tests, ruff clean).
    Specifically:
    - test_honorific_repair_success: status="done", no GateError
    - test_structural_not_repaired: status="quarantined", repair LLM call_count == 0
    - test_budget_exhausted: status="quarantined", repair LLM call_count == gate_repair_max_attempts
    - test_moat_regression: resolved_map hint + glossary forwarded; repaired SubLine index/start_tc/end_tc byte-identical
    - test_gate_repair_disabled: status="quarantined", repair LLM not called
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM response → repair output | Repair translations are untrusted; validate_subdoc remains the gate before any write |
| Config env var → enable_gate_repair | Boolean flag; pydantic-settings handles coercion; no attack surface |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-hdz-01 | Tampering | repair SubLine construction | mitigate | New SubLine objects only; index/start_tc/end_tc copied byte-identical from translated_doc; raw=None on repaired cues; never mutate source SubLines (Pitfall 8) |
| T-hdz-02 | Denial of Service | repair loop budget | mitigate | bounded at gate_repair_max_attempts; no infinite loop; budget decremented on every attempt whether LLM succeeds or fails |
| T-hdz-03 | Elevation of Privilege | repaired doc bypasses gate | mitigate | repaired doc ALWAYS re-enters validate_subdoc; no write path that skips the gate exists |
| T-hdz-04 | Information Disclosure | CORRECTION directive leaks prompt to output | mitigate | directive is passed as context_before (not batch_texts); [context] prefix marks it read-only in the prompt; Check 8 / HINT_SCAFFOLD_RE remains the defense-in-depth backstop |
| T-hdz-SC | Tampering | no new package installs | accept | no new dependencies; all code reuses existing engine helpers |
</threat_model>

<verification>
## Overall Phase Checks

1. `python -m pytest tests/translate/test_gate_repair.py -v` — all 5 tests GREEN
2. `python -m pytest -q` — full suite green (484+ tests)
3. `ruff check trezarr/config.py trezarr/translate/engine.py tests/translate/test_gate_repair.py` — clean
4. Grep confirms `_REPAIRABLE_CHECKS` = `frozenset({3, 9, 10, 11, 12})` in engine.py
5. Grep confirms `enable_gate_repair` and `gate_repair_max_attempts` in config.py
6. Grep confirms no new `asyncio.Semaphore` in engine.py (beyond the existing LLMClient one)
7. Grep confirms `reconcile.py` and `attribute.py` were NOT modified (git diff --name-only)
</verification>

<success_criteria>
- A single Check-11 defective cue no longer quarantines the whole episode when enable_gate_repair=True (default)
- enable_gate_repair=False reproduces exact pre-IMP-02b behavior (no repair call, immediate quarantine)
- Structural checks {1,2,4,5,6,7,8} still quarantine immediately without a repair attempt
- Budget is provably bounded (test asserts call count == gate_repair_max_attempts, never more)
- Pronoun moat untouched: repair re-translates through the same resolved_map hints + glossary as original Pass-3
- reconcile.py and attribute.py are unchanged (git diff confirms)
- Full test suite green; ruff clean
</success_criteria>

<output>
Create `.planning/quick/260608-hdz-add-a-bounded-gate-level-cue-repair-pass/260608-hdz-SUMMARY.md` when done.
</output>
