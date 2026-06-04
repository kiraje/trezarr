---
quick_id: 260604-hp2
slug: fix-pass4-leak-and-register-merge
status: complete
date: 2026-06-04
commits: d651c5a, 562bad9
---

# Summary — Fix the two bugs the S01E06 live-verify (260604-gza) found

The orphan-sentinel fix (260604-hb4) unblocked the pipeline; the live re-run of
S01E06 then translated clean end-to-end on deepseek (57 orphans stripped, gate
passed) — **confirming the harness, not the model, was the v1.0 blocker**. But the
written `.vi.srt` was not yet shippable: two more harness bugs surfaced. Both fixed.

## 1. Pass-4 self-review scaffolding leak (CRITICAL) — `d651c5a`
`build_review_prompt` formats `[N] (source: <orig>) <vi>`; deepseek echoed the
scaffolded line back, `parse_numbered_response` accepted it, and the splice
overwrote good Pass-3 VI → ~28% of cues shipped containing `(source: 不要) Đừng`.
The 7-check gate missed it (trailing VI cleared Check 3's diacritic ratio) — silent
corruption to disk, worse than a quarantine.

- `_review_batch` Step 4.5: discard any correction matching `REVIEW_SCAFFOLD_RE`,
  keep the clean pre-review Pass-3 text (per-line D-59).
- `validate` Check 8: quarantine if scaffolding reaches the final doc (defense in depth).
- Shared case-insensitive `REVIEW_SCAFFOLD_RE` (tolerant of recasing/spacing) so the
  guard and gate never drift. Residual risk (accepted): a *translated* scaffold token
  (`(nguồn:`) would evade a literal match.
- pipeline-reliability-reviewer: **PASS** (2 LOW → folded in: shared RE + case-insensitive).

## 2. Series-entity register merge AttributeError (was silently dropping register) — `562bad9`
`merge_inferred` built `BibleEvent(series_id=fresh_row.series_id)`, but a Series row's
PK is `.id` (no `.series_id`) → AttributeError AFTER `setattr` → transaction rolled
back → register/source_lang/model overrides never persisted (caught as a WARNING).
Fix: `event_series_id = fresh_row.id if entity_type=='series' else fresh_row.series_id`.
Only character/term merges were tested before, so the series path slipped through.
bible-consistency-auditor: **PASS**.

## Verification
- Full suite: **390 passed, 1 skipped, 3 xfailed, 52 xpassed**. New tests: scaffolding
  guard (drop/keep), gate Check 8, series-register persistence (DB-confirmed).
- Two specialist reviews PASS.

## Net effect on the core value
The translation pipeline now runs clean end-to-end AND produces uncorrupted output
on the weak deepseek endpoint. A frontier model is now an OPTIONAL quality lift, not
a prerequisite. Remaining open (non-code): Stage-2 pronoun/term consistency audit on a
clean run + cross-episode (≥2 eps) — the [[vietnamese-relational-correctness]] audit.

## Files
- `trezarr/translate/engine.py`, `trezarr/translate/validate.py`, `trezarr/bible/store.py`
- tests: `tests/translate/test_engine.py`, `tests/translate/test_validate.py`, `tests/bible/test_merge_inferred.py`
