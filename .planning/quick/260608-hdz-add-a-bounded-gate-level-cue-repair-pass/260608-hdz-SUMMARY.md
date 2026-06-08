---
phase: quick-260608-hdz
plan: 01
subsystem: translate/engine
tags: [gate-repair, imp-02b, quarantine, translate]
dependency_graph:
  requires: [trezarr/translate/engine.py, trezarr/translate/validate.py, trezarr/config.py]
  provides: [_repair_failing_cues, _REPAIRABLE_CHECKS, enable_gate_repair, gate_repair_max_attempts]
  affects: [translate_file Step 9, test_gate_repair.py]
tech_stack:
  added: []
  patterns: [bounded-repair-loop, TDD-RED-GREEN]
key_files:
  created: [tests/translate/test_gate_repair.py]
  modified: [trezarr/config.py, trezarr/translate/engine.py]
decisions:
  - "Directive injection via Batch.context_before (SubLine wrapper) rather than a new _translate_batch parameter — keeps the existing function signature stable while putting the directive before the numbered lines"
  - "Repair batch pronoun_hints are None (no attribution data for isolated failing cues) — the unhinted-line guardrail + glossary + register carry sufficient context for repair effectiveness"
  - "_REPAIRABLE_CHECKS = frozenset({3, 9, 10, 11, 12}); structural {1,2,4,5,6,7,8} always quarantine"
  - "Test fixture: 5-cue SRT (4 good VI cues + 1 defective 'Miss Mei') — ensures Check-3 ratio 0.80 >= 0.70 so Check-11 fires instead of Check-3"
metrics:
  duration: "~20 min"
  completed: "2026-06-08T05:48:40Z"
  tasks: 2
  files: 3
---

# Phase quick-260608-hdz Plan 01: Add Bounded Gate-Level Cue Repair Pass Summary

**One-liner:** Bounded gate-level cue-repair loop in translate_file Step 9 using `_repair_failing_cues` + `_REPAIRABLE_CHECKS = {3,9,10,11,12}` so a single Check-11 straggler no longer quarantines the whole episode.

## What Was Built

### trezarr/config.py
Two new `TrezarrSettings` fields under a new `# Phase 2: Gate-level cue repair (IMP-02b)` section:
- `enable_gate_repair: bool = True` — when True, translate_file attempts repair before quarantining on a repairable GateError; set False to reproduce exact pre-IMP-02b behavior
- `gate_repair_max_attempts: int = 3` — maximum LLM repair calls per file; budget decremented on each attempt; exhausted → quarantine

Both fields read from `TREZARR_ENABLE_GATE_REPAIR` and `TREZARR_GATE_REPAIR_MAX_ATTEMPTS` env vars (pydantic-settings prefix).

### trezarr/translate/engine.py

**New module-level constants:**
- `_REPAIRABLE_CHECKS: frozenset[int] = frozenset({3, 9, 10, 11, 12})` — the set of gate checks whose failure is content-only (re-translating can fix); structural checks {1,2,4,5,6,7,8} fall straight to quarantine unchanged
- `_REPAIR_DIRECTIVE: dict[int, str]` — per-check correction text injected into the repair prompt as `context_before`

**New async helper `_repair_failing_cues(...) -> list[SubLine] | None`:**
- Accepts `failing_indices, source_doc, translated_doc, check_number, llm_client, settings, glossary_lines, register_value, resolved_map, bible, model`
- Builds a minimal `Batch` from only the failing source cues; injects the correction directive as a `SubLine` in `Batch.context_before` (the directive appears as a `[context]` read-only line in the prompt — RULE 3 prevents the model from outputting it)
- Calls the existing `_translate_batch` (which routes through `LLMClient._semaphore` — no new Semaphore) with the same `glossary_lines`, `register_value`, and `model` as the original Pass-3 call
- Constructs NEW `SubLine` objects with `index/start_tc/end_tc` copied byte-identically from `translated_doc.lines[i]`; replaces only `.text` (Pitfall 8: never mutate)
- Returns `None` on any `Exception` (LLM failure, parse failure) — caller quarantines immediately on `None`

**Repair loop replacing Step-9 try/except GateError:**
```
_repair_budget = settings.gate_repair_max_attempts
while True:
    try:
        validate_subdoc(translated_doc, source_doc, settings, ...)
        break  # gate passed
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
            # Standard quarantine path (unchanged)
            ...
            return TranslationResult(status="quarantined", ...)
        _repair_budget -= 1
        repaired_lines = await _repair_failing_cues(...)
        if repaired_lines is None:
            # LLM failure → immediate quarantine
            return TranslationResult(status="quarantined", ...)
        # Splice → new translated_doc → re-validate
        translated_doc = SubDoc(lines=repaired_lines, ...)
```

### tests/translate/test_gate_repair.py (new, 5 tests)

1. **test_honorific_repair_success** — 5-cue SRT; cues 1-4 translate correctly (Check-3 ratio 0.80); cue 5 returns "Miss Mei, tạm biệt." → Check-11 fires; mock LLM returns "Cô Mai, tạm biệt." on repair call; asserts `status == "done"`
2. **test_structural_not_repaired** — 2-cue source; Pass-3 returns 1 line → Check-1; patches `_repair_failing_cues` as `AsyncMock`; asserts `call_count == 0` and `status == "quarantined"`
3. **test_budget_exhausted** — `gate_repair_max_attempts=2`; `_repair_failing_cues` always returns the defective cue; asserts `repair_call_count == 2` and `status == "quarantined"` (bounded — never more than budget)
4. **test_moat_regression** — spy on `_repair_failing_cues`; captures `translated_doc.lines[failing_index]`; asserts `index/start_tc/end_tc` are non-empty (byte-identity from codec); asserts spy was invoked and repair succeeded
5. **test_gate_repair_disabled** — `enable_gate_repair=False`; patches `_repair_failing_cues` as `AsyncMock`; asserts `call_count == 0` and `status == "quarantined"` on first GateError

## Deviations from Plan

### [Rule 1 - Bug] Correction directive injected via Batch.context_before SubLine wrapper, not a string context_before list

**Found during:** Task 2 implementation

**Issue:** The plan described passing the directive as `context_before=["[CORRECTION REQUIRED] " + directive]`. But `build_translate_prompt`'s `context_before` parameter is typed as `list[str]` (the texts), while `Batch.context_before` is `list[SubLine]`. `_translate_batch_inner` computes `context_before_texts = [c.text for c in batch.context_before]` — so the directive must be wrapped as a `SubLine` object to reach `build_translate_prompt`. The implementation wraps the directive as `SubLine(index="0", ..., text="[CORRECTION REQUIRED] " + directive)` and places it in `Batch.context_before`. This keeps `_translate_batch`'s signature unchanged and puts the directive before the numbered lines exactly as designed. Noted per TUNING HINT.

**Impact:** Functionally equivalent — the directive appears in the prompt as a `[context] [CORRECTION REQUIRED] ...` line that the model reads but does not output (RULE 3).

### [Rule 1 - Bug] Test fixture redesigned: 5-cue SRT instead of 1-cue SRT

**Found during:** Task 2 GREEN phase debugging

**Issue:** The plan specified a 1-cue SRT with "Miss Mei, chúng ta nên đi thôi." to trigger Check-11. However, this text — like the repair target "Cô Mai, chúng ta nên đi thôi." — has NO Vietnamese diacritics in the `VN_DIACRITIC_RE` range (U+1E00-U+1EFF). Both trigger Check-3 (VI diacritic ratio 0.00 < 0.70) before Check-11 is reached (gate is fail-fast). Check-3 is in `_REPAIRABLE_CHECKS` but the "repaired" text still fails Check-3 → infinite budget consumption.

**Fix:** 5-cue SRT where cues 1-4 return "Được rồi."/"Thế giới." (confirmed VI diacritics in range) and cue 5 returns "Miss Mei, tạm biệt." The "ạ" in "tạm" (U+1EA1) is in the VI range, so the diacritic ratio is 4/5=0.80 before repair and 5/5=1.00 after. Check-11 fires (not Check-3) and the repaired "Cô Mai, tạm biệt." passes all checks. Test design documents the exact rationale in the module docstring.

## Security / Threat Surface Scan

No new network endpoints or auth paths introduced. The repair path is fully internal to `translate_file` — the same `LLMClient` (with its `_semaphore` gate) handles repair calls. The gate (`validate_subdoc`) remains the sole arbiter before any write; nothing defective can ship. No new dependencies added.

| Flag | File | Description |
|------|------|-------------|
| (none) | — | No new threat surface detected |

## Known Stubs

None. The repair loop is fully wired: config fields → repair loop → `_repair_failing_cues` → `_translate_batch` → `validate_subdoc` gate.

## Self-Check

### Files Created/Modified

- `trezarr/config.py` — `enable_gate_repair` and `gate_repair_max_attempts` present
- `trezarr/translate/engine.py` — `_REPAIRABLE_CHECKS`, `_REPAIR_DIRECTIVE`, `_repair_failing_cues`, repair loop present
- `tests/translate/test_gate_repair.py` — 5 tests collected and passing

### Commits

- `a729f69` — `test(260608-hdz): RED gate-repair tests`
- `3199156` — `feat(260608-hdz): implement IMP-02b bounded gate-level cue repair`

### Test Results

- `tests/translate/test_gate_repair.py`: 5/5 GREEN
- Full suite: 489 passed, 1 skipped, 3 xfailed, 52 xpassed (baseline was 484 + 5 new = 489)
- ruff check: clean on all 3 changed files

### Invariant Checks

- `reconcile.py` and `attribute.py`: NOT modified (git diff confirms)
- No new `asyncio.Semaphore` in engine.py (grep confirms)
- `validate.py`: NOT modified (read-only per guardrail)

## Self-Check: PASSED

---

## Harness Fixes (2026-06-08 post-merge review)

The trezarr-quality harness returned 1 BLOCKER + 2 HIGH findings after the initial IMP-02b commit.
All were fixed in commits `3a30cd2` (RED tests) and `4e1e482` (fixes).

### FIX 1 (BLOCKER) — Directive-echo bypasses all 12 gate checks

**Finding:** The codec guardian proved the `[CORRECTION REQUIRED] <directive>` injected into
`Batch.context_before` passes all 12 gate checks when deepseek echoes it verbatim (e8r/job-9
incident proved deepseek ignores "do not output" on context lines). The echo carrier had no
`(speaker says:` or `(source:` prefix so neither `HINT_SCAFFOLD_RE` nor `REVIEW_SCAFFOLD_RE`
matched it.

**Three-layer fix (a+b+c):**
- **(a)** Moved directive injection from `Batch.context_before` to `build_translate_prompt`'s new
  `correction_directive` param, rendered as a RULE with `[CORRECTION REQUIRED]` prefix.
  Instruction-block injection is significantly less echo-prone than context lines.
- **(b)** Added `_LEAKED_DIRECTIVE_RE` to `parse_numbered_response` (alongside `_LEAKED_HINT_RE`):
  strips a leading `[CORRECTION REQUIRED] ...` echo to empty → `BatchValidationError` → correction
  loop retries. Recovery path mirrors the e8r hint-strip.
- **(c)** Added `CORRECTION_DIRECTIVE_RE` to `validate.py` Check 8 (alongside `HINT_SCAFFOLD_RE`):
  fail-closed gate backstop — `[CORRECTION REQUIRED]` cannot appear in Vietnamese dialogue so
  quarantining is safe with zero false positives.

**Accepted residual risk:** Markerless-paraphrase echoes (e.g. "Render EVERY name in its Vietnamese
Hán-Việt form.") are NOT matched — these are benign instruction semantics, not internal-machinery
tokens. Moving the directive to the RULES block cuts this likelihood vs. context lines; the
marker+backstop closes all proven bare/marker echo forms.

**Tests:** `test_directive_echo_quarantined` (gate), `test_parse_strips_leading_directive_echo`
(parse layer), `test_validate_check8_trips_on_correction_required` (validate.py backstop).

### FIX 2 (HIGH / D-47) — Repair swallows openai.APIError into quarantine

**Finding:** The `except Exception: return None` in `_repair_failing_cues` converted transient
`openai.APIError` / `RuntimeError("LLM returned empty content")` into permanent quarantine.
The Step-7 main translate path correctly catches only `BatchValidationError`; the repair path
was asymmetric and wrong.

**Fix:** Narrowed the catch to `except BatchValidationError: return None` (genuine repair miss —
the LLM couldn't produce a valid translation after retries). All other exceptions propagate:
`openai.APIError` leaves the file `in_progress` for retry next poll (D-47 / Pitfall B); logic
bugs are now loud failures.

**Test:** `test_repair_api_error_propagates` — asserts `translate_file` raises the error and
no quarantine record is written.

### FIX 3 (HIGH / MOAT) — Directed pronoun dropped on repaired cue

**Finding:** The linguist found `repair_pronoun_hints = None` hard-coded, so a repaired Check-11
cue dropped its directed pair (e.g. `huynh↔muội`) and fell to the safe-default (`bạn`), while
its neighbors kept the relationship-specific pair — a visible single-cue register stumble.
`resolved_map` was accepted as a param but never read (dead param); the docstring falsely
claimed the moat was "untouched."

**Fix:** Added `flat_attributions: list | None` and `name_to_char_id: dict[str, int] | None`
params to `_repair_failing_cues`. For each failing index `i`, if `flat_attributions[i]` has
attribution, resolve speaker/addressee → char ids → `resolved_map[(spk, addr)]` → directed pair,
keyed by the repair batch's local 1-based index. Missing attribution falls to safe-default
(unchanged — correct where attribution is genuinely absent). The call site in `translate_file`
builds `_repair_name_to_char_id` from `bible.characters` when the Phase-5 path is active.
`resolved_map` is now a live param; docstring updated.

**Test:** `test_repair_receives_directed_pronoun_hint` — calls `_repair_failing_cues` directly
with seeded `flat_attributions` and `name_to_char_id`, spies on `_translate_batch`, asserts
`pronoun_hints[1] == ("huynh", "muội")`.

### FIX 4 (MEDIUM) — `huynh` in directive suggestion list risks seniority inversion

**Finding:** `_REPAIR_DIRECTIVE[11]` included `huynh` (a directed seniority term) in its
suggestion list. An unhinted repair prompted with `huynh` could stamp a false seniority direction.

**Fix:** Removed `huynh` from the suggestion list. Kept only non-directed/safe terms:
`cô / cô nương / tiền bối / trưởng lão / các hạ`.

### FIX 5 (LOW) — Raw cue could lose its `raw` field in the splice

**Finding:** The splice set `raw=None` for any index in `failing_set` without checking if the
source line was a raw opaque pass-through (D-98/D-99). Latent today (repairable checks already
skip raw cues in validate.py) but unsafe for future check additions.

**Fix:** The splice now tracks `repair_batch_local_indices` (doc indices that actually entered the
repair batch, excluding skipped raw cues) and `repair_set` (the set of re-translated doc indices).
If a failing index is in `failing_indices` but NOT in `repair_set` (raw cue, skipped), it is
preserved verbatim with its original `raw` field.

### Test additions (harness review)

- Added `flat_attributions=None, name_to_char_id=None` kwargs to spy functions in
  `test_budget_exhausted` and `test_moat_regression` (forward-compat with new signature).
- Fixed `test_validate_check8_trips_on_correction_required` to use 5-cue doc (Check-3 ratio
  4/5=0.80 ≥ 0.70, so Check-8 fires rather than Check-3).

### Final test count

- `tests/translate/test_gate_repair.py`: 10/10 GREEN (5 original + 5 new)
- Full suite: **494 passed**, 1 skipped, 3 xfailed, 52 xpassed
- `ruff check` + `ruff format`: clean
