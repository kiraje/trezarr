---
phase: quick-260608-scy
plan: 01
subsystem: translate/reconcile + bible/analyze
tags: [pronoun-consistency, moat-core, cross-episode, carry-forward, create-or-affirm]
dependency_graph:
  requires: []
  provides: [cross-episode-pronoun-carry-forward, pass1-create-or-affirm]
  affects: [reconcile.py, analyze.py, engine.py]
tech_stack:
  added: []
  patterns:
    - carry-forward: established Bible pair propagated into resolved_map when no survivors + no transition + no lock
    - create-or-affirm: Pass-1 Step 4 passes self_term=None/address_term=None for existing pairs; store.py None-guard preserves terms
key_files:
  created: []
  modified:
    - trezarr/translate/reconcile.py
    - trezarr/bible/analyze.py
    - trezarr/translate/engine.py
    - tests/translate/test_reconcile.py
    - tests/bible/test_address_map.py
decisions:
  - "Carry-forward fires on `not survivors` (any no-survivors path) not `zero attributions only` — the broader trigger closes Vector 2 for the common case (recurring dyad spoken below threshold). Both re-pointed tests reflect this deliberate contract change (linguist-verified)."
  - "Carry-forward does NOT call upsert_address_pair — resolved_map entry alone is sufficient for Pass-3 hints; valid_from_episode stays as-is in the DB. Lower-risk minimal fix; survivors-branch upsert handles updates when there IS a witness."
  - "Pass-1 create-or-affirm passes None for terms on existing pairs; store.py already has the None-guard at line 705. No store.py change needed."
metrics:
  duration: "~35 min"
  completed: "2026-06-08"
  tasks_completed: 2
  files_changed: 5
  tests_added: 7
  tests_baseline: 505
  tests_final: 512
---

# Phase quick-260608-scy Plan 01: Cross-Episode Pronoun Carry-Forward Summary

**One-liner:** Carry established unlocked Bible pairs forward in reconcile.py's no-survivors else-branch and make Pass-1 Step 4 create-or-affirm-only, closing both vectors of cross-episode pronoun drift that silently dropped `(anh/em)` to `(tôi/bạn)` mid-series.

## What Was Built

### Vector 2 Fix — reconcile.py carry-forward (no-survivors else-branch)

The `reconcile_attributions` else-branch (~line 441) previously ran `get_safe_default()` unconditionally when `survivors` was empty — explicitly ignoring the `existing_map` entry with the comment "we deliberately do NOT consult existing_map here." This caused an established `(anh/em)` pair to silently revert to `(tôi/bạn)` in any episode where the dyad lacked a high-confidence attribution, with no narrative cause.

The fix inserts a carry-forward check before `get_safe_default`:

```python
if (
    existing is not None
    and existing.self_term is not None
    and existing.address_term is not None
):
    resolved_map[pair] = (existing.self_term, existing.address_term)
    logger.debug("reconcile: carried prior pair for %d→%d: (%s/%s) at %s", ...)
    continue
```

`existing` is already computed at the lock check above — no re-fetch. Lock and transition branches already `continue`d before the else-branch, so carry-forward is correctly scoped to no-survivors + no-transition + no-lock only. Truly-new dyads (no prior entry, or prior entry with None terms) still fall through to `get_safe_default`.

### Vector 1 Fix — analyze.py create-or-affirm in Step 4

Pass-1 Step 4 previously called `upsert_address_pair` with `self_term=pair.self_term, address_term=pair.address_term` unconditionally — silently overwriting an established unlocked pair with the current episode's raw LLM inference, with no `relationship_event` authorizing the change.

The fix builds `existing_pair_keys` from `load_series_bible().address_map` (in the same try block that already pre-loads `name_to_id`), then in the Step 4 loop:

```python
pair_already_exists = (spk_id, addr_id) in existing_pair_keys
await upsert_address_pair(
    ...,
    self_term=None if pair_already_exists else pair.self_term,
    address_term=None if pair_already_exists else pair.address_term,
    ...
)
```

`store.py`'s `if new_val is None: continue` guard (line 705) already skips None fields — no store.py change needed. Safe degrade: if `load_series_bible` raises, `existing_pair_keys = set()` and the create-with-terms path applies.

### Vector 2b Confirmation — engine.py (comment only)

`engine.py` line 1785 already keys hints on `resolved_map.get((spk_id, addr_id))`. After the carry-forward fix, `resolved_map` contains carried Bible pairs, so any line whose Pass-2 attribution resolves both `spk_id` and `addr_id` will receive the carried pronoun hint in `batch_hints`. No engine.py code change was needed; one clarifying comment was added.

## Tests

### Re-pointed (deliberate contract change, verifier-confirmed correct)

| Test | Old assertion | New assertion |
|------|---------------|---------------|
| `test_below_threshold_established_pair_carries_forward` (renamed from `test_below_threshold_ignores_address_map`) | `!= ("anh","em")` + `== get_safe_default()` | `== ("anh","em")` |
| `test_reconcile_within_episode_dyad_lock_no_flip` sub-case 2 | `== ("tôi","bạn")` | `== ("anh","em")` |

### New regression tests

**test_reconcile.py (5 tests):**
- `test_carry_forward_established_unlocked_pair` — zero-witness carry
- `test_truly_new_dyad_no_prior_safe_defaults` — no prior entry → safe-default guard intact
- `test_relationship_event_still_evolves_carried_pair` — genuine evolution overrides carry-forward
- `test_lock_still_wins_carry_forward` — locked pair still wins
- `test_reciprocal_coherence_carry_forward` — both S→A and A→S carried from their own rows

**test_address_map.py (2 tests):**
- `test_pass1_create_or_affirm_existing_pair` — None call leaves established terms unchanged
- `test_pass1_creates_brand_new_pair` — brand-new pair created with supplied terms

## Deviations from Plan

None — plan executed exactly as written. The `existing` variable was already in scope at line 368 as specified; the `existing_pair_keys` degrade path was added to the except block alongside the existing warning log exactly as specified.

## Threat Mitigations Applied

| Threat | Mitigation |
|--------|------------|
| T-scy-01: carry-forward on DB row with None terms | Guarded by `existing.self_term is not None and existing.address_term is not None` — safe-default still fires for term-less rows |
| T-scy-02: existing_pair_keys build failure | `except` block sets `existing_pair_keys = set()` — create-with-terms path applies (safe degradation) |
| T-scy-03: lock precedence | Lock check at reconcile.py:366-376 `continue`s before the else-branch; carry-forward cannot override a lock |

## Harness LOW Fix (appended 260608-scy)

**Finding:** `analyze.py` Step 4 passed `valid_from_episode=episode_key` unconditionally, bumping the D-53 evolution marker each episode for recurring pairs and emitting spurious `BibleEvent` rows. No pronoun/viewer effect (no pronoun-selection site reads `valid_from_episode`; `_find_transition_for_pair` keys off `relationship_events.episode_marker`), but semantically wrong for a series-long tool and contradicts the no-op-skip spirit (BIBLE-06).

**Fix (analyze.py line ~782):** `valid_from_episode=None if pair_already_exists else episode_key` — symmetric with the existing terms None-guards. store.py's `if new_val is None: continue` (line 705) already covers `valid_from_episode` in the `mergeable_fields` loop — no store.py change needed.

**Scope confirmed:** The affirm path is bare-inference only. The reconcile/transition/relationship_event path (genuine evolution) flows through a different code branch and is untouched.

**RED commit:** `53caf44` — test(quick-260608-scy): RED — affirm existing pair must not bump valid_from_episode
**GREEN commit:** `f82b33b` — fix(quick-260608-scy): valid_from_episode=None for existing pairs in Pass-1 create-or-affirm

## Test Results

- Baseline: 505 passed
- After Vector 1+2 fix: 512 passed (7 new tests)
- After Harness LOW fix: 513 passed (1 additional new test), 1 skipped, 3 xfailed, 52 xpassed
- Full suite: green, 0 regressions

## Commits

- `3424f9b` — feat(quick-260608-scy-01): carry-forward established unlocked pair in no-survivors else-branch
- `167b264` — feat(quick-260608-scy-02): Pass-1 create-or-affirm + Vector 2b comment + store tests
- `53caf44` — test(quick-260608-scy): RED — affirm existing pair must not bump valid_from_episode
- `f82b33b` — fix(quick-260608-scy): valid_from_episode=None for existing pairs in Pass-1 create-or-affirm

## Self-Check: PASSED

- `/Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr/trezarr/translate/reconcile.py` — FOUND, contains `existing.self_term is not None`
- `/Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr/trezarr/bible/analyze.py` — FOUND, contains `existing_pair_keys` and `valid_from_episode=None if pair_already_exists else episode_key`
- `/Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr/tests/translate/test_reconcile.py` — FOUND, contains `test_carry_forward_established_unlocked_pair`
- `/Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr/tests/bible/test_address_map.py` — FOUND, contains `test_affirm_existing_pair_does_not_bump_valid_from_episode`
- Commit `3424f9b`: FOUND in git log
- Commit `167b264`: FOUND in git log
- Commit `53caf44`: FOUND in git log
- Commit `f82b33b`: FOUND in git log
