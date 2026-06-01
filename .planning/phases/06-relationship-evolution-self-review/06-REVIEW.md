---
phase: 06-relationship-evolution-self-review
reviewed: 2026-06-02T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - trezarr/bible/models.py
  - trezarr/bible/dto.py
  - trezarr/bible/store.py
  - trezarr/bible/analyze.py
  - trezarr/translate/reconcile.py
  - trezarr/translate/engine.py
  - trezarr/translate/batching.py
  - trezarr/config.py
  - tests/bible/test_relationship_events.py
  - tests/translate/test_self_review.py
  - tests/translate/test_reconcile.py
  - tests/translate/test_pronoun_engine.py
  - tests/bible/test_lazy_series_create.py
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-06-02
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 6 extends the three-pass pronoun engine with relationship-event tracking (BIBLE-07) and a Pass-4 self-review step (ENG-05). The structural wiring is sound: D-39 is honoured (no SQLAlchemy outside `store.py`), no new `asyncio.Semaphore` was introduced, and the D-59 best-effort contract for `_review_batch` is correctly implemented. The quarantine firewall around Pass-4 is intact.

Three correctness bugs were found: two are blockers that will silently corrupt the pronoun-consistency contract under realistic conditions; one is a silent data-loss path where the LLM-inferred `suggested_self_term`/`suggested_address_term` from `RelationshipEventInference` are discarded before they can reach reconciliation. The remaining issues are quality/hygiene items.

---

## Critical Issues

### CR-01: `dominant_pair` is always `None` in Pass-4 review batches — reviewer never knows which pronoun pair to check

**File:** `trezarr/translate/batching.py:100`, `trezarr/translate/engine.py:887-892`

**Issue:** The `Batch` dataclass has a `dominant_pair: tuple[int, int] | None = None` field added in Phase 6 (D-56). However `_make_batch` — the only function that constructs `Batch` objects — never populates it:

```python
# batching.py line 100
return Batch(cues=cues, context_before=context_before, context_after=context_after)
# dominant_pair is never passed → always None
```

`batch_subdoc` is called for Pass-4 review batches at `engine.py:887`. `_review_batch` retrieves the value via `getattr(review_batch, "dominant_pair", None)` (line 302) and passes it to `build_review_prompt`. Since it is always `None`, the reviewer's prompt omits the pronoun-pair context block entirely — the most important grounding for a self-review is silently absent. The LLM gets no pronoun pair to check against, defeating the primary purpose of Pass 4.

**Fix:** `batch_subdoc` cannot compute `dominant_pair` because it has no attribution data. The dominant pair must be assigned after reconciliation. In `translate_file`, after `review_batches = batch_subdoc(translated_doc, ...)`, compute dominant pairs from `flat_attributions` and `resolved_map` and stamp them onto the review batches before dispatching `_review_batch`:

```python
# After building review_batches (engine.py ~line 892):
name_to_char_id_rev = {
    c.original_latin_name.strip().lower(): c.id for c in bible.characters
} if bible else {}

review_doc_offset = 0
for rb in review_batches:
    batch_size = len(rb.cues)
    rb_attrs = flat_attributions[review_doc_offset: review_doc_offset + batch_size]
    pair_counts: dict[tuple[int, int], int] = {}
    for attr in rb_attrs:
        spk_id = name_to_char_id_rev.get((attr.speaker or "").strip().lower())
        addr_id = name_to_char_id_rev.get((attr.addressee or "").strip().lower())
        if spk_id and addr_id:
            pair_counts[(spk_id, addr_id)] = pair_counts.get((spk_id, addr_id), 0) + 1
    rb.dominant_pair = max(pair_counts, key=pair_counts.get) if pair_counts else None
    review_doc_offset += batch_size
```

This is a functional correctness bug that makes Pass-4's pronoun-adherence checking inoperative.

---

### CR-02: `suggested_self_term` / `suggested_address_term` from `RelationshipEventInference` are never carried into `RelationshipEventDTO` — transition-authorized pronoun changes silently fall back to safe default

**File:** `trezarr/bible/analyze.py:566-574`, `trezarr/bible/store.py:994-1004`

**Issue:** `RelationshipEventInference` (analyze.py:63-71) carries `suggested_self_term` and `suggested_address_term` inferred by the LLM. These are the mechanism by which Pass-1 communicates the new pronoun terms to reconciliation. However `merge_bible_analysis` discards them when calling `record_relationship_event`:

```python
# analyze.py line 567-574
await record_relationship_event(
    session_factory,
    series_id=series_id,
    character_a_id=char_a_id,
    character_b_id=char_b_id,
    episode_marker=episode_key,
    description=event.description,   # <-- only description is passed
    # suggested_self_term and suggested_address_term are silently dropped
)
```

`record_relationship_event` in `store.py` has no parameters for these fields, and `RelationshipEventDTO` (dto.py:171-172) marks them as `# In-memory only (from inference, not stored in DB)`. They are populated from `RelationshipEventInference` in-memory — but there is no code path that copies `event.suggested_self_term`/`event.suggested_address_term` from the `RelationshipEventInference` object into the `RelationshipEventDTO` that `load_series_bible` returns.

When `reconcile_attributions` calls `_derive_transition_terms` (reconcile.py:159), `transition.suggested_self_term` and `transition.suggested_address_term` are always `None`, causing the fallback to `get_safe_default`. The LLM's inferred pronoun transition is silently lost every time. Every relationship transition uses generic safe defaults instead of the LLM-suggested terms, defeating the key D-51/D-54 design goal.

**Fix:** One of two approaches:

Option A — populate the in-memory fields after `load_series_bible`. In `merge_bible_analysis`, after calling `record_relationship_event`, reload the bible and patch the returned `RelationshipEventDTO` with the in-memory terms before passing it to reconciliation. This requires a post-load patch step since the fields are not persisted.

Option B (simpler) — pass the inference objects alongside the DTOs through the pipeline. Add a caller-local dict keyed by `(char_a_id, char_b_id, episode_marker)` that maps to `(suggested_self_term, suggested_address_term)`, and populate `RelationshipEventDTO.suggested_self_term/suggested_address_term` after `load_series_bible` in `translate_file` using this dict.

Without this fix, `_derive_transition_terms` can never use suggested terms; all transitions get safe defaults.

---

### CR-03: Pass-4 TaskGroup `except Exception` catches `BaseException` subclasses including `asyncio.CancelledError` — can suppress legitimate task cancellation

**File:** `trezarr/translate/engine.py:912`

**Issue:** The Pass-4 TaskGroup is wrapped in a bare `except Exception` block:

```python
try:
    async with asyncio.TaskGroup() as tg:
        review_tasks = [tg.create_task(_review_batch(...)) for rb in review_batches]
    review_results = [t.result() for t in review_tasks]
except Exception:                   # line 912
    logger.warning(...)
    review_results = [None] * len(review_batches)
```

`_review_batch` already catches all exceptions internally and returns `None` (D-59), meaning the TaskGroup should never raise under normal failure conditions. However, `asyncio.CancelledError` (in Python 3.8+, a `BaseException` not an `Exception`) can propagate from the task creation itself or from the enclosing context being cancelled. While `except Exception` does not catch `CancelledError` in Python 3.8+, there is a different risk: if `asyncio.TaskGroup` itself raises an `ExceptionGroup` (its standard failure mode for unhandled task exceptions), `except Exception` will catch it — but `_review_batch` is supposed to absorb all exceptions and never propagate them out.

The real issue is the comment at line 896: "CRITICAL DIFFERENCE from Pass-3 TaskGroup: NO except* block here." This is intentionally correct. But the comment at line 879 claims "Pass 4 naturally degrades via the `except Exception` catch in `_review_batch` (plain-text LLM still returns numbered lines)." A Tier-3 text endpoint returning plain text (not `[1] line` format) will cause `parse_numbered_response` to raise `BatchValidationError` inside `_review_batch` — which IS caught by `_review_batch`'s outer `except Exception` and returns `None`. So that path is actually safe.

The genuine correctness gap: `except Exception` at line 912 — if ever reached — swallows the `ExceptionGroup` from the TaskGroup without unwrapping it, logging only the group summary. More importantly, if `_review_batch`'s internal `except Exception` were ever removed or narrowed by a future refactor, this outer catch would silently convert a real bug into a no-op. Given that D-59 requires the best-effort contract to be in `_review_batch` itself (not the TaskGroup wrapper), the outer catch should be narrowed or documented more precisely.

**Fix:** Change to `except* Exception` (Python 3.11+) matching the established pattern, which correctly unwraps `ExceptionGroup`. Since `_review_batch` should never raise, log as an error (not warning) if this path is reached, as it indicates a violated internal contract:

```python
try:
    async with asyncio.TaskGroup() as tg:
        review_tasks = [tg.create_task(_review_batch(...)) for rb in review_batches]
    review_results = [t.result() for t in review_tasks]
except* Exception as eg:
    # _review_batch must never raise (D-59); reaching here indicates a bug
    logger.error(
        "Pass 4 TaskGroup raised unexpectedly (%d exceptions) — "
        "this violates the D-59 best-effort contract; keeping pre-review doc",
        len(eg.exceptions), exc_info=True,
    )
    review_results = [None] * len(review_batches)
```

---

## Warnings

### WR-01: `_make_settings` in `test_reconcile.py` omits `enable_relationship_events` — Phase-6 transition tests rely on `getattr` fallback default

**File:** `tests/translate/test_reconcile.py:150-157`

**Issue:** `reconcile_attributions` reads `settings.enable_relationship_events` via `getattr(settings, "enable_relationship_events", True)` (reconcile.py:259). The `_make_settings` helper in `test_reconcile.py` returns a `SimpleNamespace` without this attribute, so the default of `True` is always used. This is intentional and currently correct. However, there is no test that verifies the `enable_relationship_events=False` toggle suppresses transition lookups. If the `getattr` is ever refactored to a direct attribute access (which is the correct production code style — `TrezarrSettings` has the field), tests would fail with `AttributeError` rather than silently using the wrong default. This is a test-quality gap that leaves the toggle's off-path untested.

**Fix:** Add `enable_relationship_events=True` (or `False` for a toggle test) to `_make_settings` so the tests are not silently depending on `getattr` fallback behavior. At minimum add a test that `enable_relationship_events=False` prevents `_find_transition_for_pair` from being invoked.

---

### WR-02: `merge_bible_analysis` register merge guarded by `series_dto is not None` — Series ID-only callers silently skip register update

**File:** `trezarr/bible/analyze.py:379-391`

**Issue:** The register merge in Step 1 of `merge_bible_analysis` is gated on `series_dto is not None`:

```python
reg = (analysis.register_value or "").strip()
if reg and series_dto is not None:   # line 380
    try:
        await merge_inferred(...)
```

Phase-6 callers may pass `series_id=...` instead of `series_dto=...` (as explicitly documented in the function's docstring at line 356). When called with `series_id` only (e.g., in future engine refactors), `series_dto` is `None` and the register update is silently skipped even when the LLM returned a valid register value. The function accepts both signatures but the register update only works with the `series_dto` path.

**Fix:** When `series_dto is None`, load a minimal SeriesDTO from the session_factory using `series_id` before the merge call, or refactor `merge_inferred` to accept `series_id` directly.

---

### WR-03: `_find_transition_for_pair` is undirected — a B→A event authorizes an A→B pronoun change

**File:** `trezarr/translate/reconcile.py:142-143`

**Issue:** `_find_transition_for_pair` matches relationship events in both directions:

```python
if (event.character_a_id == spk_id and event.character_b_id == addr_id) or \
   (event.character_a_id == addr_id and event.character_b_id == spk_id):
    return event
```

This means if the LLM records a transition for the (B, A) directed pair, it will also match when reconciling the (A, B) pair. `_derive_transition_terms` then uses `transition.suggested_self_term` as A's self-term, but those suggested terms were inferred for B's perspective. The self/address terms are directed; applying B→A suggested terms for A→B is semantically incorrect.

This is a design-level ambiguity: `relationship_event` is documented as undirected (the CLAUDE.md schema: `character_a`, `character_b` without directionality). But the suggested terms in `RelationshipEventInference` are explicitly A→B. If the stored event was created with B as character_a, applying `suggested_self_term` (B's self-term) to the A→B pair produces wrong pronouns.

**Fix:** Either (a) require callers to always store events with character_a = speaker, making the event directed, and only match `event.character_a_id == spk_id and event.character_b_id == addr_id`; or (b) when the reverse match fires, swap `suggested_self_term` and `suggested_address_term` if both are present.

---

### WR-04: `test_reconcile.py` non-xfail Phase-6 tests (`test_transition_authorizes_terms_change`, `test_lock_beats_transition`, `test_no_transition_no_survivors_safe_default`) will always XPASS silently — regressions will not fail CI

**File:** `tests/translate/test_reconcile.py:482, 556, 633`

**Issue:** The three Phase-6 tests in `test_reconcile.py` (BIBLE-07-C, D, E) carry `@pytest.mark.xfail(strict=False, ...)`. The implementation they test (`_find_transition_for_pair`, the transition branch in `reconcile_attributions`) was shipped in this phase. These tests are now passing (XPASS). With `strict=False`, pytest reports XPASS as a pass — it does NOT turn into a test failure. If a future commit accidentally breaks `_find_transition_for_pair`, these tests would revert to XFAIL (the marker's expected state) and pytest would still report them as passing. The regression would be invisible to CI.

The same applies to the 3 tests in `test_relationship_events.py` (BIBLE-07-A, B, F) and 4 tests in `test_self_review.py` (ENG-05-A, B, C, D).

**Fix:** Remove the `@pytest.mark.xfail` decorator from all 10 tests that now pass. If the policy is to keep Wave-0 scaffolding comments, replace with `# formerly @pytest.mark.xfail — promoted to passing in Phase 6` inline comments. With `strict=False`, leaving these markers is a correctness risk, not just a style issue: future regressions in the relationship-evolution and self-review code paths will silently XFAIL rather than failing CI.

---

## Info

### IN-01: `get_term` in `store.py` uses case-sensitive lookup for `source_term` while `get_character` uses case-insensitive lookup

**File:** `trezarr/bible/store.py:766-770`

**Issue:** Character lookups are case/whitespace-insensitive (CR-01 fix). Term lookups are case-sensitive:

```python
# store.py line 766-770
stmt = select(TermDictionary).where(
    TermDictionary.series_id == series_id,
    TermDictionary.source_term == source_term,   # exact-match, case-sensitive
)
```

If the LLM returns a term with different casing than stored (e.g. `"Sonarr"` vs `"sonarr"`), `get_term` would return `None` while `upsert_term` would create a duplicate row. `_upsert_term_in_session` at line 538-542 also uses exact match. This inconsistency may be intentional (terms are proper nouns where case matters) but is not documented and creates a subtle asymmetry with the CR-01 character fix.

**Fix:** Add a comment in `get_term` and `_upsert_term_in_session` confirming case-sensitivity is intentional for terms (unlike characters) to prevent a future "fix" from inadvertently breaking proper noun matching.

---

### IN-02: `_build_analysis_prompt` injects the raw `episode_key` string directly into the f-string instruction block without sanitization

**File:** `trezarr/bible/analyze.py:215`

**Issue:**

```python
f"    Each entry: character_a_name, character_b_name, episode_marker (use \"{episode_key}\"),\n"
```

`episode_key` is derived from a filename stem (via `derive_episode_key`) and generally follows the `SxxExx` pattern, but there is no validation that it lacks quote characters. If `episode_key` were ever crafted to include `"` or newlines (e.g., from a pathological filename), it could break prompt structure. This is a low-severity injection surface since `episode_key` is internally derived, not user-controlled in the current pipeline.

**Fix:** Strip or validate `episode_key` to `[A-Za-z0-9\-]` characters before interpolation into the prompt, or use `repr(episode_key)` instead of the bare string.

---

_Reviewed: 2026-06-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
