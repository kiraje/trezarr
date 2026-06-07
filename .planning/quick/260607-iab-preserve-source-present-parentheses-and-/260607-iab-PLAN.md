---
phase: quick-260607-iab
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - trezarr/translate/engine.py
  - tests/translate/test_engine.py
  - tests/translate/test_validate.py
autonomous: true
requirements:
  - benchmark-paren-preservation
must_haves:
  truths:
    - "build_translate_prompt no longer contains an unqualified 'Do NOT add parentheticals' instruction — the rule is qualified to forbid ADDING glosses while PRESERVING source-present parentheses/brackets"
    - "A title-card cue like '(Title Card Line A<<BR>>Line B)' produces a prompt that positively instructs the model to keep the surrounding '(' ')' envelope and translate the text inside"
    - "A translated Vietnamese parenthetical with diacritics like '(Phàm Nhân Tu Tiên Ký)' passes validate_subdoc without triggering Check 10 or Check 12"
    - "The existing H4 gloss-leak backstop (Check 11/12 in validate.py) is not weakened — English-gloss parentheticals like '(Miss Mei's brother)' still raise GateError(check=12)"
    - "reconcile.py, attribute.py, and Address-Map logic are untouched"
  artifacts:
    - path: "trezarr/translate/engine.py"
      provides: "Reworked H4 RULE in build_translate_prompt"
      contains: "PRESERVE"
    - path: "tests/translate/test_engine.py"
      provides: "Regression test: prompt no longer forbids source-present parentheses"
    - path: "tests/translate/test_validate.py"
      provides: "Regression test: translated Vietnamese parenthetical passes Check 10 + Check 12"
  key_links:
    - from: "trezarr/translate/engine.py"
      to: "trezarr/translate/validate.py"
      via: "Check 12 GLOSS_PAREN_RE + LATIN_DIACRITIC_RE"
      pattern: "GLOSS_PAREN_RE|LATIN_DIACRITIC_RE"
---

<objective>
Rework the H4 anti-parenthetical RULE in build_translate_prompt() so it preserves
source-present parentheses/brackets in translated output, without weakening the
gloss-leak gate (Check 11/12) that backstops against the model ADDING its own English
explanatory notes.

Root cause (confirmed): the current H4 rule at ~line 299 of engine.py reads:
  "Do NOT add parentheticals, glosses, or translator notes. Translate the dialogue only."
A weak model (DeepSeek) over-applies this and strips parentheses that were ALREADY in
the source cue — e.g. the Ep-142 title card "(A Record…)" became "A Record…" with no
parens, losing structural markup present in ContextWeave and the gold reference.

The fix is prompt-only. validate.py needs no changes: Check 12 already exempts
parentheticals whose inner text has Latin diacritics (Vietnamese translations), and
Check 10 only trips on no-diacritic source-passthrough — a translated Vietnamese
title card clears both.

Purpose: Close the single structural benchmark sub-dimension where ContextWeave beat
Trezarr — parenthesis preservation on on-screen title cards and SDH cues.

Output: Modified engine.py + two regression tests.
</objective>

<execution_context>
@/Users/dustin/.claude/get-shit-done/workflows/execute-plan.md
@/Users/dustin/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@trezarr/translate/engine.py
@trezarr/translate/validate.py
@tests/translate/test_engine.py
@tests/translate/test_validate.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Rework H4 RULE in build_translate_prompt to preserve source-present parentheses</name>
  <files>trezarr/translate/engine.py, tests/translate/test_engine.py</files>
  <behavior>
    - Test A: build_translate_prompt(["(Title Card A<<BR>>Line B)"], [], []) produces a prompt
      that does NOT contain the unqualified string "Do NOT add parentheticals" as a standalone
      instruction (i.e. the old unqualified form is gone).
    - Test B: the same prompt DOES contain an instruction to PRESERVE parentheses/brackets
      already present in the source — assert "PRESERVE" or "already present" or "source" +
      "parenthes" appears in the prompt (use a single assert covering the new wording).
    - Test C: the same prompt still contains language forbidding the model from ADDING its own
      glosses/translator notes — assert "gloss" or "translator note" or "add" + "parenthetical"
      appears in the prompt (the anti-gloss half must remain).
    - Tests follow the existing pattern in test_engine.py: direct import of build_translate_prompt
      from trezarr.translate.engine (no pytest.importorskip needed — module exists), synchronous
      function, plain asserts with descriptive failure messages.
  </behavior>
  <action>
    Write the three tests (A, B, C) in tests/translate/test_engine.py, grouped under a
    comment block "# ── H4-fix: parenthesis preservation ─────────────────────────────────"
    following the existing section-header convention. Run pytest tests/translate/test_engine.py
    -k "parenthes" — confirm RED (test B/C or A fails against the old prompt wording).

    Then rework the H4 block in trezarr/translate/engine.py. The existing block is at
    approximately lines 298-303:

      # H4 fix: forbid adding explanatory parentheticals/glosses (e.g. "(Miss Mei's brother)").
      parts.append(
          f"{rule_n}. Do NOT add parentheticals, glosses, or translator notes. Translate the "
          "dialogue only."
      )
      rule_n += 1

    Replace the comment and the parts.append() call with a two-part rework:
    - Keep the "[linguist: refine wording]" comment convention (per codebase pattern).
    - Keep the rule_n counter increment (no change to surrounding counter logic).
    - New rule text must:
      (a) POSITIVELY instruct the model: if the source cue contains parentheses "( )" or
          square brackets "[ ]", TRANSLATE the text inside them and PRESERVE the surrounding
          "(" ")" / "[" "]" envelope in the output — do not strip the delimiters.
      (b) STILL forbid the model from ADDING its own explanatory parentheticals, glosses,
          or translator notes that are NOT present in the source cue.
    - Keep the comment tag "# H4 fix:" so grep-based history works.
    - Do NOT change rule numbering logic, do NOT touch any other RULE, do NOT touch
      validate.py, reconcile.py, attribute.py, or any Address-Map code.

    After the implementation edit, run pytest tests/translate/test_engine.py -k "parenthes"
    to confirm GREEN. Then run the full suite: pytest tests/translate/ to confirm no regressions.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_engine.py -k "parenthes" -v && python -m pytest tests/translate/ -x -q</automated>
  </verify>
  <done>
    Three tests (A/B/C) pass. Full translate test suite passes (466+ tests). The prompt
    built by build_translate_prompt no longer contains an unqualified "Do NOT add
    parentheticals" instruction and does contain a positive preservation instruction.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add validate.py regression tests — translated Vietnamese parenthetical passes Check 10 + Check 12</name>
  <files>tests/translate/test_validate.py</files>
  <behavior>
    - Test D: validate_subdoc with source cue "(A Record of Mortal's Journey to Immortality\nUpheaval in Outer Sea Season 3)"
      and translated cue "(Phàm Nhân Tu Tiên Ký\nNgoại Hải Phong Vân)" returns None (no gate failure).
      This confirms that a properly-translated parenthetical with Vietnamese diacritics is NOT
      quarantined by Check 10 (source-passthrough) or Check 12 (gloss-paren).
    - Test E: validate_subdoc with source cue "(WIND HOWLING)" and translated cue "(WIND HOWLING)"
      — a kept-verbatim SDH sound cue in source language — does raise GateError. This is the
      known Check 10 behavior. Do NOT solve it; just document the existing behavior by asserting
      the check number. This prevents the Task 1 prompt change from accidentally masking a
      pre-existing validator behavior.
    - Tests follow the existing test_validate.py pattern: use _make_line/_make_doc helpers
      (already defined at the top of test_validate.py), call validate_subdoc with _settings().
      Both tests are synchronous. Group them under comment
      "# ── H4-fix: parenthesis preservation — validate gate regression ───────────────"
  </behavior>
  <action>
    Write the failing Test D and Test E stubs in tests/translate/test_validate.py. Run pytest
    tests/translate/test_validate.py -k "paren" — confirm RED (at minimum, Test D fails if the
    validator incorrectly quarantines a valid Vietnamese title card, or confirm GREEN if the
    validator already handles it correctly — either is a valid RED/GREEN baseline; record what
    you observe).

    No changes to validate.py are expected or permitted unless the baseline run shows Test D
    actually raises GateError. If it does raise (unexpected — the task description says it
    should not), stop and surface the finding to the user before proceeding: "validate.py
    Check N is incorrectly quarantining '(Phàm Nhân Tu Tiên Ký)' — please review before
    proceeding." Do not silently work around a genuine validator bug.

    If Test D passes (no gate failure) as expected, finalize both tests and run the full
    validate suite: pytest tests/translate/test_validate.py -x -q.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_validate.py -k "paren" -v && python -m pytest tests/translate/test_validate.py -x -q</automated>
  </verify>
  <done>
    Test D passes (translated Vietnamese parenthetical with diacritics is not quarantined).
    Test E behavior is confirmed and documented. Full validate test suite passes with no
    regressions.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM prompt → LLM response | Untrusted model output; prompt wording change must not weaken Check 11/12 gloss backstop |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-iab-01 | Tampering | H4 RULE wording change | mitigate | Test C explicitly asserts the anti-gloss half of the rule remains; Check 11/12 in validate.py is the hard backstop and is not modified |
| T-iab-02 | Spoofing | LLM injects English gloss inside parentheses | accept | Check 12 GLOSS_PAREN_RE + HONORIFIC_CAPNAME_RE already catches "'s" / "Miss X" patterns; the prompt change does not alter this defense |
</threat_model>

<verification>
After both tasks complete:

1. pytest tests/translate/ passes (466+ tests, zero failures)
2. ruff check trezarr/translate/engine.py passes
3. grep -n "Do NOT add parentheticals" trezarr/translate/engine.py returns zero unqualified occurrences (the old unqualified form is gone)
4. grep -n "PRESERVE\|already present\|source.*parenthes\|parenthes.*source" trezarr/translate/engine.py returns at least one hit in the H4 block
</verification>

<success_criteria>
- build_translate_prompt emits a rule that both (a) preserves source-present parentheses/brackets and (b) forbids the model from adding new ones
- A translated Vietnamese title card "(Phàm Nhân Tu Tiên Ký)" passes validate_subdoc without triggering Check 10 or Check 12
- All 466+ existing tests remain green
- reconcile.py, attribute.py, and Address-Map code are unmodified (git diff confirms)
</success_criteria>

<output>
Create `.planning/quick/260607-iab-preserve-source-present-parentheses-and-/260607-iab-SUMMARY.md` when done.
</output>
