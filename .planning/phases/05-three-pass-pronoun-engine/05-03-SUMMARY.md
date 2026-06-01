---
phase: 05-three-pass-pronoun-engine
plan: "03"
subsystem: translate/reconcile
tags: [pronoun-engine, reconcile, kinship-table, confidence-gate, series-bible]
dependency_graph:
  requires: [05-01, 05-02]
  provides: [PRON-02, PRON-03, reconcile_attributions, get_safe_default, KINSHIP_RECIPROCAL]
  affects: [trezarr/translate/reconcile.py, tests/translate/]
tech_stack:
  added: []
  patterns:
    - "Threshold-gated reconciliation: confidence >= threshold → use Address Map; else safe default"
    - "Reciprocal kinship coherence: A→B resolved pair triggers KINSHIP_RECIPROCAL lookup for B→A"
    - "TYPE_CHECKING-only SQLAlchemy import (D-39, Pitfall D)"
    - "Duck-typed test fixtures for LineAttribution before attribute.py exists"
key_files:
  created:
    - trezarr/translate/reconcile.py
    - tests/translate/conftest.py
  modified:
    - tests/translate/test_reconcile.py
decisions:
  - "D-44 threshold gate: survivors = attributions with confidence >= threshold; if any, use existing Address Map entry terms; if none, locked entry honoured, unlocked skipped → safe default"
  - "LineAttribution carries speaker/addressee/confidence only (no self_term/address_term); Address Map entry supplies the actual pronoun terms"
  - "Test uses duck-typed SimpleNamespace for LineAttribution since attribute.py (Plan 05-04) does not yet exist — satisfies reconcile.py duck-typed access pattern"
  - "reconcile_attributions processes all_pairs = observed pairs ∪ existing address_map pairs to also apply threshold logic to pre-existing Address Map entries"
metrics:
  duration: "4 minutes"
  completed: "2026-06-01"
  tasks_completed: 1
  files_changed: 3
---

# Phase 05 Plan 03: Reconcile Module Summary

**One-liner:** Threshold-gated deterministic reconciliation module with 18-entry Vietnamese kinship reciprocal table, confidence-based Address Map lookup, and safe-default fallback for Pass-3 pronoun hints.

## What Was Built

`trezarr/translate/reconcile.py` implements the D-44/D-45 deterministic pronoun-pair reconciliation algorithm as a self-contained utility module:

- **`KINSHIP_RECIPROCAL`** — 18-entry dict mapping `(self_term, address_term)` to the expected reciprocal pair for B→A (covering all common Vietnamese kinship pronoun pairs: anh/em, chị/em, ông/cháu, bà/cháu, bố/con, mẹ/con, cha/con, tôi/bạn, tôi/anh, etc.)
- **`SAFE_DEFAULT_*` constants** — tôi (self), anh (male), chị (female), bạn (neutral)
- **`get_safe_default(addressee_gender, settings)`** — pure function; returns `settings.pronoun_safe_default` if set, otherwise selects by gender
- **`reconcile_attributions(...)`** — async function implementing the full D-44 algorithm:
  - Builds name→char_id index from bible.characters (case-insensitive)
  - Groups LineAttribtion objects by (speaker_id, addressee_id)
  - Applies confidence threshold gate per pair
  - Uses existing Address Map entry terms for confirmed pairs
  - Honours LOCKED Address Map entries even below threshold; skips UNLOCKED entries below threshold
  - Writes resolved pairs via `upsert_address_pair`
  - Infers reciprocal pairs from KINSHIP_RECIPROCAL for pairs not yet resolved

`tests/translate/conftest.py` re-exports `db_engine` and `session_factory` fixtures from `tests/db/conftest.py` so reconcile tests have DB access.

`tests/translate/test_reconcile.py` replaced all four xfail stubs with real async tests using in-memory SQLite via the session_factory fixture.

## All 4 Tests GREEN

| Test | Assertion | Result |
|------|-----------|--------|
| `test_low_confidence_safe_default` | LOW confidence + "medium" threshold → (`tôi`, `bạn`) | PASSED |
| `test_high_confidence_uses_address_map` | HIGH confidence + existing Address Map entry → (`anh`, `em`) | PASSED |
| `test_reciprocal_coherence` | A→B (`anh`,`em`) → B→A (`em`,`anh`) inferred via KINSHIP_RECIPROCAL | PASSED |
| `test_below_threshold_ignores_address_map` | MEDIUM confidence + "high" threshold + unlocked entry → safe default | PASSED |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Design Clarifications

**1. LineAttribution has no self_term/address_term fields**

The plan's algorithm description says "pick the first HIGH-confidence one (first-seen wins)" — but `LineAttribution` (defined in attribute.py, Plan 05-04) only carries `speaker`, `addressee`, `confidence`. The actual (self_term, address_term) comes from the **existing Address Map entry** in the bible, not from the attribution. This was implicit in the plan but not stated explicitly. Reconciliation confirms whether a pair was observed with sufficient confidence, then uses the Address Map's stored terms.

**2. Duck-typed test fixtures for LineAttribution**

Since `attribute.py` doesn't exist until Plan 05-04, tests use `SimpleNamespace` objects that duck-type the required fields (`speaker`, `addressee`, `confidence`). The `_FakeConfidence` inner class handles both `.value` and `str()` access patterns to match reconcile.py's `_confidence_value()` helper.

## Self-Check: PASSED

Files created/modified:
- `trezarr/translate/reconcile.py` — EXISTS
- `tests/translate/conftest.py` — EXISTS
- `tests/translate/test_reconcile.py` — EXISTS (modified)

Commits:
- `5b7941d` — feat(05-03): implement reconcile.py — all 4 tests GREEN

Constraints verified:
- `grep -n "from sqlalchemy" trezarr/translate/reconcile.py` → only line 26 inside `TYPE_CHECKING` block (runtime-safe)
- `grep -n "asyncio.Semaphore" trezarr/translate/reconcile.py` → only comment on line 12

Full suite: 214 passed, 1 skipped, 7 xfailed — green.

## Threat Flag Check

No new network endpoints, auth paths, file access patterns, or schema changes introduced. reconcile.py is a pure in-process algorithm; DB writes go through the parameterized ORM `upsert_address_pair` store function. All T-05-03-* mitigations implemented:
- T-05-03-01: Unmatched speaker/addressee names resolve to safe default (not crash), never write to DB
- T-05-03-02: `KINSHIP_RECIPROCAL.get()` with default=None — unknown pairs not written as reciprocals
