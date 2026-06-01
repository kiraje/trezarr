---
phase: 06-relationship-evolution-self-review
verified: 2026-06-02T07:00:00Z
status: human_needed
score: 9/9
overrides_applied: 0
human_verification:
  - test: "Translate two consecutive episodes of a series with a known relationship arc (e.g. strangers become lovers). Confirm pronoun pair changes only from the transition episode forward and is logged in relationship_event + bible_event tables."
    expected: "Prior-episode pronoun pair is unchanged; from the transition episode, the new pair applies consistently. relationship_event row exists with correct episode_marker. bible_event row shows address_map before→after for each affected pair."
    why_human: "Requires a real series, real subtitle files, and a live LLM endpoint. Narrative-intent detection (did the LLM identify the transition correctly?) requires human judgment."
  - test: "Translate a file with enable_self_review=False, then again with enable_self_review=True. Diff the two outputs."
    expected: "With self-review enabled, at least one line is corrected to use the Bible-specified pronoun pair, term, or register. No line is paraphrased or 'improved' if it was already adherent (D-58). No quarantine is triggered."
    why_human: "Whether a correction is genuine vs over-correction cannot be determined without live LLM output and human judgment of Vietnamese pronoun correctness."
---

# Phase 6: Relationship Evolution + Self-Review — Verification Report

**Phase Goal:** The consistency engine deepens — relationship changes are tracked across episodes as episode-marked events so pronoun pairs evolve correctly, and an LLM self-review pass critiques and repairs its own output against the Bible before the file is finalized.
**Verified:** 2026-06-02T07:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC #1: A relationship shift is recorded as an episode-marked transition, and the active pronoun pair changes intentionally — not by silent drift | VERIFIED | `record_relationship_event` in store.py (line 955), `_find_transition_for_pair` with exact `episode_marker == episode_key` filter (reconcile.py:140-141), lock-check structurally first in for-loop (reconcile.py:267-277). BIBLE-07-A/B/C/D/E/F all PASS. |
| 2 | SC #2: A self-review pass re-reads translated output, checks Bible adherence, and corrects violations before the validation gate | VERIFIED | `build_review_prompt` + `_review_batch` exist in engine.py (lines 198, 268). Step 8.5 at lines 875-975, inserted between Step 8 (`translated_doc = SubDoc(...)` at ~870) and Step 9 (`validate_subdoc` at line 977). ENG-05-A/B/C/D all PASS. |
| 3 | SC #3: Consistent pronoun pair across a logged change, with the change auditable | VERIFIED | Transition branch calls `upsert_address_pair` with `valid_from_episode=episode_key` (reconcile.py:296-306). `record_relationship_event` creates the narrative audit row (store.py:994-1004). `_derive_transition_terms` 3-step precedence: LLM-suggested → attribution-confirmed → safe default (reconcile.py:177-185). |
| 4 | CR-01 fix: dominant_pair stamped on review batches from flat_attributions | VERIFIED | engine.py:895-917 — after `batch_subdoc`, iterates `flat_attributions` aligned 1:1 with review batch cues, counts `(spk_id, addr_id)` pairs, stamps `rb.dominant_pair = max(...)`. Tests `test_build_review_prompt_includes_pronoun_pair_when_dominant_pair_set` and `..._omits_...` both PASS. |
| 5 | CR-02+WR-03 fix: transition adopts attribution-confirmed terms (not always safe-default) | VERIFIED | `_derive_transition_terms` step 2: `if survivors and existing is not None and existing.self_term and existing.address_term: return (existing.self_term, existing.address_term)` (reconcile.py:181-182). `test_transition_adopts_attribution_confirmed_terms` PASS. `test_transition_no_survivors_falls_to_safe_default` PASS. |
| 6 | CR-03 fix: Pass-4 TaskGroup uses except* to correctly unwrap ExceptionGroup | VERIFIED | engine.py:939 — `except* Exception as eg:` with `logger.error(...)` (not warning). Uses `_review_failed` flag variable since `return` is not allowed inside `except*`. |
| 7 | WR-04 fix: all 10 Phase-6 tests promoted from xfail to real PASS | VERIFIED | `grep xfail tests/bible/test_relationship_events.py tests/translate/test_self_review.py tests/translate/test_reconcile.py` — all occurrences are inline comments only (formerly xfail note). No `@pytest.mark.xfail` decorators remain. |
| 8 | Cross-cutting: 0 new asyncio.Semaphore; no SQLAlchemy outside store.py; D-39 boundary preserved | VERIFIED | `grep -rn "asyncio.Semaphore" trezarr/ grep -v llm/client.py` — 0 instantiations (comment-only hits). `grep "from trezarr.bible.models import" analyze.py reconcile.py` — 0 matches. `test_dto_boundary.py` PASS (3/3). |
| 9 | Full test suite green (245 passed, 1 skipped) | VERIFIED | `uv run pytest -q` output: `245 passed, 1 skipped, 1 warning` — all 226 pre-existing tests green plus 19 new Phase-6 tests (10 original + 2 CR-01 build_review_prompt tests + 2 CR-02 transition term tests + 1 WR-01 toggle test + 4 additional reconcile tests). |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/bible/models.py` | Series.relationship_events ORM + RelationshipEvent.series back-ref | VERIFIED | 2 occurrences of `relationship_events` — one on `Series` (line ~96), one on `RelationshipEvent` (line ~218). `back_populates="relationship_events"` in both directions. |
| `trezarr/bible/dto.py` | RelationshipEventDTO + SeriesBibleDTO.relationship_events field | VERIFIED | `RelationshipEventDTO` at lines 163-172. `suggested_self_term/suggested_address_term` as in-memory-only fields. `SeriesBibleDTO.relationship_events: list[RelationshipEventDTO] = []` present. |
| `trezarr/bible/store.py` | record_relationship_event + load_series_bible extension | VERIFIED | `record_relationship_event` at line 955. `selectinload(Series.relationship_events)` at line 218. DTO construction list-comprehension at lines 242-244. |
| `trezarr/bible/analyze.py` | RelationshipEventInference, BibleAnalysis.relationship_events, merge Step 5 | VERIFIED | `RelationshipEventInference` at line 63. `BibleAnalysis.relationship_events` at line 111. `merge_bible_analysis` Step 5 at lines 538-586 with CR-01 `.strip().lower()` and per-row try/except. |
| `trezarr/translate/reconcile.py` | _find_transition_for_pair, _derive_transition_terms, transition branch | VERIFIED | `_find_transition_for_pair` at line 128 (exact `episode_marker == episode_key` filter). `_derive_transition_terms` at line 148 (D-54 3-step). Transition branch at lines 284-311 (after lock-check, before survivors gate). |
| `trezarr/translate/engine.py` | build_review_prompt, _review_batch, translate_file Step 8.5 | VERIFIED | `build_review_prompt` at line 198. `_review_batch` at line 268 (returns `list[str] | None`, full `except Exception → return None`). Step 8.5 block at lines 875-975 between Step 8 and Step 9. |
| `trezarr/config.py` | Phase-6 settings: enable_relationship_events, enable_self_review, self_review_* | VERIFIED | `python -c "... print(s.enable_self_review, s.enable_relationship_events, s.self_review_max_cues_per_batch)"` prints `True True 20`. |
| `tests/bible/test_relationship_events.py` | BIBLE-07-A/B/F — real PASS (no xfail) | VERIFIED | 3 tests, all PASS (no xfail markers). |
| `tests/translate/test_self_review.py` | ENG-05-A/B/C/D — real PASS (no xfail) | VERIFIED | 4 core tests + 2 CR-01 tests, all PASS. |
| `tests/translate/test_reconcile.py` | BIBLE-07-C/D/E — real PASS (no xfail) + WR-01/CR-02 tests | VERIFIED | 12 tests total, all PASS. Includes `test_enable_relationship_events_false_suppresses_transition` (WR-01), `test_transition_adopts_attribution_confirmed_terms` and `test_transition_no_survivors_falls_to_safe_default` (CR-02). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `analyze.py merge_bible_analysis Step 5` | `store.py record_relationship_event` | `await record_relationship_event(...)` | WIRED | analyze.py:567 — `await record_relationship_event(session_factory, series_id=..., character_a_id=..., episode_marker=episode_key, description=event.description)` |
| `store.py load_series_bible` | `models.py Series.relationship_events` | `selectinload(Series.relationship_events)` | WIRED | store.py:218 — `selectinload(Series.relationship_events)` in stmt.options block |
| `reconcile.py reconcile_attributions` | `store.py upsert_address_pair` | `await upsert_address_pair(..., valid_from_episode=episode_key)` | WIRED | reconcile.py:296-306 — transition branch calls `upsert_address_pair` with `valid_from_episode=episode_key` |
| `engine.py translate_file Step 8.5` | `engine.py _review_batch` | `asyncio.TaskGroup tg.create_task(_review_batch(...))` | WIRED | engine.py:927-937 — TaskGroup creates `_review_batch` tasks for each review batch |
| `engine.py _review_batch` | `llm/client.py LLMClient.call` | `await llm_client.call([...])` — no response_model | WIRED | engine.py:313 — `raw_response = await llm_client.call([{"role": "user", "content": prompt}])` — no `response_model` argument |
| `engine.py translate_file Step 8.5` | `validate.py validate_subdoc` | Step 9 after Step 8.5 splices corrections | WIRED | engine.py:977-979 — `validate_subdoc(translated_doc, source_doc, settings)` immediately after the Step 8.5 correction splice |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `reconcile.py reconcile_attributions` | `bible.relationship_events` | `load_series_bible` via `selectinload(Series.relationship_events)` → DB | Yes — DB rows loaded via ORM | FLOWING |
| `engine.py _review_batch` | `dominant_pair` | `flat_attributions` + `resolved_map` stamped post-`batch_subdoc` (engine.py:895-917) | Yes — attribution data from Pass-2 gather | FLOWING |
| `engine.py Step 8.5` | `review_results` | `_review_batch` tasks via TaskGroup | Real LLM call (or `None` on failure) | FLOWING |
| `analyze.py merge_bible_analysis Step 5` | `analysis.relationship_events` | LLM-returned `BibleAnalysis.relationship_events` list from `analyze_file` Pass-1 | Real LLM response parsed via Pydantic | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 10 original Phase-6 test nodes pass | `uv run pytest tests/bible/test_relationship_events.py tests/translate/test_self_review.py tests/translate/test_reconcile.py::test_transition_authorizes_terms_change tests/translate/test_reconcile.py::test_lock_beats_transition tests/translate/test_reconcile.py::test_no_transition_no_survivors_safe_default -v` | 12 passed (includes 2 extra CR-01 tests) | PASS |
| Full suite clean | `uv run pytest -q` | 245 passed, 1 skipped, 1 warning | PASS |
| Config fields available | `python -c "from trezarr.config import TrezarrSettings; s = TrezarrSettings(llm_api_key='x'); print(s.enable_self_review, s.enable_relationship_events, s.self_review_max_cues_per_batch)"` | `True True 20` | PASS |
| build_review_prompt + _review_batch importable | `python -c "from trezarr.translate.engine import build_review_prompt, _review_batch; print('OK')"` | OK | PASS |
| RelationshipEventDTO + record_relationship_event importable | `python -c "from trezarr.bible.dto import RelationshipEventDTO; from trezarr.bible.store import record_relationship_event; print('OK')"` | OK | PASS |
| D-39 DTO boundary | `uv run pytest tests/bible/test_dto_boundary.py -x -q` | 3 passed | PASS |
| No new asyncio.Semaphore | `grep -rn "asyncio.Semaphore" trezarr/ \| grep -v "llm/client.py"` | 0 instantiations (comment-only hits) | PASS |
| No SQLAlchemy leakage | `grep "from trezarr.bible.models import" trezarr/bible/analyze.py trezarr/translate/reconcile.py` | 0 matches | PASS |
| No _write_quarantine reachable from Pass-4 | All 5 `_write_quarantine` calls at lines 521 (def), 678, 738, 837, 983 — all in pre-Step-8.5 or Step-9 paths | 0 new quarantine triggers from Pass-4 | PASS |
| except* used in Step 8.5 TaskGroup (CR-03) | engine.py:939 `except* Exception as eg:` | Confirmed | PASS |
| xfail markers removed from all 10 tests (WR-04) | `grep "xfail" tests/bible/test_relationship_events.py tests/translate/test_self_review.py tests/translate/test_reconcile.py` | 13 hits — all inline comments, 0 decorators | PASS |

### Probe Execution

Step 7c: SKIPPED — no conventional probe scripts exist (`find scripts -path '*/tests/probe-*.sh'` returns empty). Phase does not declare explicit probes in PLAN frontmatter.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| BIBLE-07 | 06-02-PLAN.md | Track relationship evolution across episodes with episode markers | SATISFIED | `record_relationship_event`, `load_series_bible` extension, `_find_transition_for_pair`, transition branch in `reconcile_attributions` all implemented and tested. BIBLE-07-A/B/C/D/E/F tests all PASS. |
| ENG-05 | 06-03-PLAN.md | LLM self-review pass over translated output, check Bible adherence, correct before finalizing | SATISFIED | `build_review_prompt`, `_review_batch`, Step 8.5 block in `translate_file` all implemented and tested. ENG-05-A/B/C/D tests all PASS. Step 8.5 is structurally between Step 8 and Step 9. |

No orphaned requirements: BIBLE-07 and ENG-05 are the only requirements mapped to Phase 6 in REQUIREMENTS.md traceability table.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `trezarr/bible/store.py` | 100, 144 | `XXX` substring | Info | Part of the literal string `\\uXXXX` in a comment about Unicode escape sequences — not a debt marker. No issue. |
| `analyze.py:567-574` | 566-574 | `record_relationship_event` does not forward `suggested_self_term/suggested_address_term` from `RelationshipEventInference` to the DB row | Warning (WR-03 carry-over) | The LLM-suggested terms are never stored in DB. The CR-02+WR-03 fix in `_derive_transition_terms` handles this via step 2 (attribution-confirmed from existing entry) when suggested terms are absent at reconciliation time. The fix is structurally sound. The in-memory fields in `RelationshipEventDTO` remain unused in the DB-load path. This is a known accepted limitation — the in-memory path requires the same-pass inference data to be wired through, which is deferred. |

No `TBD`, `FIXME`, unresolved `XXX` debt markers. No placeholder returns (`return null`, `return {}`, `return []`). No stub implementations.

### Human Verification Required

The following behaviors require a real LLM endpoint and actual subtitle content to verify. These are carry-forward items from the Phase-6 VALIDATION.md §Manual-Only Verifications and the 06-03-SUMMARY.md human verification checklist.

### 1. Real-Episode Relationship Shift Produces Correct Intentional Pronoun Change

**Test:** Translate two episodes of a series with a known relationship arc (e.g. strangers→lovers). Episode 1 uses the pre-transition pair. Episode 2 includes the transition event.
**Expected:** The pronoun pair changes only from the transition episode forward. The change is logged in `relationship_event` (with the correct `episode_marker`) and `bible_event` tables. Prior episodes retain the original pronoun pair (forward-only evolution, D-53).
**Why human:** Requires a real multi-episode series and live LLM endpoint. Whether the LLM correctly identified a relationship transition vs emitting a false positive requires human judgment of narrative intent and Vietnamese relational correctness.

### 2. Self-Review Measurably Improves Bible Adherence on Real Output

**Test:** Translate a file with `enable_self_review=False`, then again with `enable_self_review=True`. Diff the outputs.
**Expected:** With self-review enabled, at least one line is corrected to use the Bible-specified pronoun pair, term, or register. No adherent lines are paraphrased or "improved" (D-58 scope constraint). No quarantine is triggered by the self-review pass (D-59 best-effort contract).
**Why human:** "Did the review actually fix violations and leave adherent lines alone?" requires human judgment against live LLM output. Cannot verify from unit tests with mock LLMs.

### Gaps Summary

No gaps. All must-have truths are VERIFIED. The human verification items above are genuinely human-dependent behaviors — not code failures. The phase goal is structurally achieved in the codebase.

---

_Verified: 2026-06-02T07:00:00Z_
_Verifier: Claude (gsd-verifier)_
