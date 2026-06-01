---
phase: 6
slug: relationship-evolution-self-review
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-02
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from 06-RESEARCH.md §Validation Architecture. Brownfield phase — all 226 existing tests must stay green; Phase-6 test files are purely additive.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/bible/test_relationship_events.py tests/translate/test_self_review.py tests/translate/test_reconcile.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~30 seconds (quick), ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run the quick command (Phase-6 test files)
- **After every plan wave:** Run the full suite — all 226 existing tests must remain green
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds (quick), ~90 seconds (full)

---

## Per-Task Verification Map

> Task IDs are assigned by the planner; rows are keyed by requirement + behavior. Each maps to a named test in the Wave-0 RED stubs.

| Req | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| BIBLE-07-A | `RelationshipEventInference` in `BibleAnalysis`; Pass-1 transition → row written via `merge_bible_analysis` | T-06 V5 | LLM-derived `description`, not raw subtitle text | unit | `uv run pytest tests/bible/test_relationship_events.py::test_relationship_event_written_to_db -x` | ❌ W0 | ⬜ pending |
| BIBLE-07-B | `load_series_bible` returns `relationship_events` in `SeriesBibleDTO` | — | N/A | unit | `uv run pytest tests/bible/test_relationship_events.py::test_load_series_bible_includes_events -x` | ❌ W0 | ⬜ pending |
| BIBLE-07-C | `reconcile_attributions` — transition authorizes terms change + `valid_from_episode` bump; no-event pair carries forward | — | N/A | unit | `uv run pytest tests/translate/test_reconcile.py::test_transition_authorizes_terms_change -x` | ❌ W0 (extend) | ⬜ pending |
| BIBLE-07-D | `reconcile_attributions` — lock beats transition (D-34/D-54) | — | Human lock wins | unit | `uv run pytest tests/translate/test_reconcile.py::test_lock_beats_transition -x` | ❌ W0 (extend) | ⬜ pending |
| BIBLE-07-E | `reconcile_attributions` — no transition → below-threshold → safe default (Phase-5 success #4 preserved) | — | Never a wrong intimate pronoun | unit | `uv run pytest tests/translate/test_reconcile.py::test_no_transition_no_survivors_safe_default -x` | ❌ W0 (extend) | ⬜ pending |
| BIBLE-07-F | Case-insensitive name matching in `merge_bible_analysis` for relationship events (CR-01) | T-06 V5 | Warn-and-skip on unresolved names | unit | `uv run pytest tests/bible/test_relationship_events.py::test_name_matching_case_insensitive -x` | ❌ W0 | ⬜ pending |
| ENG-05-A | Pass 4 runs after assembly, before `validate_subdoc`; corrects a pronoun violation; gate sees corrected output | — | N/A | integration | `uv run pytest tests/translate/test_self_review.py::test_pass4_corrects_violation_before_gate -x` | ❌ W0 | ⬜ pending |
| ENG-05-B | Pass 4 review failure (mock LLM raises) → pre-review output used; gate still runs; no quarantine (D-59) | T-06 | No quarantine on transient error | unit | `uv run pytest tests/translate/test_self_review.py::test_pass4_failure_fallback_no_quarantine -x` | ❌ W0 | ⬜ pending |
| ENG-05-C | `enable_self_review=False` → Pass 4 skipped; `translated_doc` unchanged | — | N/A | unit | `uv run pytest tests/translate/test_self_review.py::test_pass4_disabled_skips_review -x` | ❌ W0 | ⬜ pending |
| ENG-05-D | Sentinel integrity failure in review → pre-review batch kept; rest of file unaffected | T-06 | Inline-tag integrity preserved | unit | `uv run pytest tests/translate/test_self_review.py::test_sentinel_failure_fallback_per_batch -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/bible/test_relationship_events.py` — RED stubs for BIBLE-07-A, B, F (store writer, DTO, load, case-insensitive names)
- [ ] `tests/translate/test_self_review.py` — RED stubs for ENG-05-A, B, C, D (Pass-4 lifecycle, failure fallback, toggle, sentinel)
- [ ] Extend `tests/translate/test_reconcile.py` — add RED stubs for BIBLE-07-C, D, E (transition precedence, lock-beats-transition, preserved Phase-5 invariant)

*All existing 226 tests remain green throughout — these are purely additive.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-episode relationship-shift produces a correct, intentional pronoun change across two episodes | BIBLE-07 | Requires a real series + live LLM endpoint; pronoun-quality judgment is human | Translate two episodes of a series with a known relationship arc (e.g. strangers→lovers); confirm the pronoun pair changes only from the transition episode forward and the change is logged in `relationship_event` + `bible_event` |
| Self-review measurably improves Bible adherence on real output | ENG-05 | "Did the review actually fix violations?" needs human judgment against a live model | Translate a file with `enable_self_review` off then on; diff outputs; confirm review only corrected genuine pronoun/term/register violations and did not paraphrase adherent lines |

*Persist these to `06-HUMAN-UAT.md` at execution close, mirroring `05-HUMAN-UAT.md`.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (3 test files above)
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
