# Phase 8: Editable Series Bible UI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 8-editable-series-bible-ui
**Mode:** `--auto` (autonomous — recommended option auto-selected per area; no interactive prompts)
**Areas discussed:** Lock storage model, Human-edit write path, Concurrency/stale-edit defense, Provenance display depth, Add/Delete scope, Re-analysis & propagation, Address Map reciprocal coherence, Pronoun vocabulary input, Edit validation/warnings, Relationship-event editing scope, Frontend surface, Pre-existing engine gaps
**Harness agents used (per user request):** `bible-consistency-auditor` + `vietnamese-linguist` (parallel codebase scout), then `finding-verifier` (adversarial verification of 6 load-bearing premises → 6 CONFIRMED, 0 refuted)

---

## Lock storage model

| Option | Description | Selected |
|--------|-------------|----------|
| Keep `locked_fields` JSON | No migration; provenance via `bible_event(source="lock")` | ✓ |
| Introduce `bible_lock` table | `locked_by`/`locked_at`/`reason` columns; richer provenance; needs migration | |

**Auto choice:** Keep `locked_fields` JSON (D-79).
**Notes:** Verified C3 — no `bible_lock` table exists; JSON column already on all four entities. Single-user/no-auth (D-78) makes `locked_by` redundant; `bible_event` already records what/when/old/new. `get_locked_fields` accessor (`merge.py`) is the documented future swap seam.

---

## Human-edit write path

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse `merge_inferred(source="lock")` | One existing path | |
| New dedicated writer (`apply_human_edit`/`set_lock`/`clear_lock`) | Sets value+lock+`bible_event` in one txn; AddressMap-specific variant | ✓ |

**Auto choice:** New dedicated store writer (D-80).
**Notes:** Verified C1 (no lock-writer exists — all inserts hard-code `locked_fields=[]`) + C2 (`merge_inferred` skips locked fields and raises `TypeError` on `AddressMapDTO`). Writer must do an in-txn re-read (WR-01), reassign the `locked_fields` list (JSON dirty-tracking footgun), and own a single transaction.

---

## Concurrency / stale-edit defense

| Option | Description | Selected |
|--------|-------------|----------|
| Per-series `asyncio.Lock` (reuse worker's) + in-txn re-read | Prevents interleave with Pass-1 merges | ✓ |
| Optimistic concurrency (version/`updated_at` column) | Detects clobber; needs migration | |
| Last-writer-wins | Simplest; silently violates the moat | |

**Auto choice:** Reuse the per-series lock + in-txn re-read (D-81).
**Notes:** Verified C6 — Pass-1 issues many independent short transactions; only the shared per-series lock prevents a UI write interleaving between inference commits. No DB UNIQUE to catch concurrent dup-inserts.

---

## Provenance display depth

| Option | Description | Selected |
|--------|-------------|----------|
| Lock badge + source only | Zero new query (from `locked_fields`) | |
| Badge + cheap read-only per-field `bible_event` history drill-down | Reuses index-covered table + `BibleEventDTO` | ✓ |

**Auto choice:** Badge inline + cheap history drill-down (D-82).
**Notes:** `bible_event` is index-covered and `BibleEventDTO` already serializes the row; only a read function is missing. No schema change. No actor/reason promised beyond the `source` enum.

---

## Add / Delete scope

| Option | Description | Selected |
|--------|-------------|----------|
| Edit-only | Safest; misses high-value glossary adds | |
| Edit + Add + scoped Delete | Add via upsert; delete Term & Address-pair only; Character delete deferred | ✓ |
| Full CRUD incl. Character delete | FK-orphan hazard (address_map/relationship_event → character) | |

**Auto choice:** View+edit+lock+Add; delete limited to Term & Address-pair; Character delete deferred (D-83).
**Notes:** Adds must route through identity-aware upsert (no DB UNIQUE — verified C3). Address-pair add needs character pickers (FK). Character delete is the referential-integrity hazard.

---

## Re-analysis & propagation (criteria 2 & 3)

| Option | Description | Selected |
|--------|-------------|----------|
| UI only sets the lock; forward-only | Engine already guarantees survival + propagation | ✓ |
| Add a "re-translate affected episodes" action | Retroactive; contradicts forward-only (Phase 6) | |

**Auto choice:** UI only sets the lock; forward-only, no retroactive re-translate (D-84/D-89).
**Notes:** Verified — `merge.py:84` / `store.py:698` skip locked fields; `reconcile.py:267-277` lock-first; `engine.py:785-814` applies to Pass-3. Criteria 2 & 3 are a test concern, not a build. Caveat: contingent on identity normalization (terms case-sensitive).

---

## Address Map reciprocal coherence on edit

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-write the reciprocal | Overrides a human who knows an asymmetric exception | |
| Suggest reciprocal side-by-side, pre-filled, user confirms | Keeps coherence + respects override; explicit "set manually" on H1 gaps | ✓ |
| Leave reciprocal untouched | Replicates the H1 silent-incoherence bug | |

**Auto choice:** Suggest + confirm (D-85).
**Notes:** Directed asymmetry is two separate rows (`store.py:644-648`). On a missing `KINSHIP_RECIPROCAL` key (H1, verified C4), show an explicit manual-entry state, not a blank.

---

## Pronoun vocabulary input

| Option | Description | Selected |
|--------|-------------|----------|
| Free-text | Highest-yield typo vector (silently breaks reciprocity + application) | |
| Dropdown only | Handcuffs advanced fansubbers (dì/cậu/tao-mày/regional) | |
| Combo (dropdown of `KNOWN_PRONOUN_TERMS` + custom escape hatch) | Typo-proof 95% case; expert override preserved | ✓ |

**Auto choice:** Combo (D-86).
**Notes:** Introduce a shared `KNOWN_PRONOUN_TERMS` constant co-located with `KINSHIP_RECIPROCAL` in `reconcile.py`, exposed via API — never duplicated in the frontend.

---

## Edit validation / warnings

| Option | Description | Selected |
|--------|-------------|----------|
| Block on relational risks | Defeats the override-valve purpose | |
| Warn-but-allow; block only empty term on lock | Surfaces reciprocal/gender/low-confidence risks without handcuffing | ✓ |
| No validation | Silent typos/incoherence reach subtitles | |

**Auto choice:** Warn-but-allow; hard-block only an empty/whitespace term when locking (D-87).
**Notes:** Verified C5 — `reconcile.py:275` requires BOTH terms non-None for the lock to win; an incomplete locked pair is silently safe-defaulted. Warnings: reciprocal incoherence, pair-not-in-table, intimate-on-low-confidence, gender mismatch (vs `Character.gender`).

---

## Relationship-event editing scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full transition editor in v1 | Risks the precedence chain; beyond BIBLE-08 scope | |
| Event-aware (read-only display) + "lock to pin"; defer authoring | Prevents silent clobber without precedence risk | ✓ |
| Ignore events entirely | Unlocked edits silently clobbered by logged transitions | |

**Auto choice:** Event-aware editor; defer authoring (D-88).
**Notes:** Display existing `relationship_events` + `valid_from_episode` read-only; make "lock to pin against a future transition" unmistakable.

---

## Frontend surface

| Option | Description | Selected |
|--------|-------------|----------|
| Extend the Phase-7 React/Vite SPA | Reuse AppShell/StatusBadge/Toast/api client; new `/api` bible router | ✓ |
| Server-rendered (HTMX/Jinja) mini-app | Diverges from the SPA Phase 7 built for exactly this | |

**Auto choice:** Extend the Phase-7 SPA + new `bible` router (D-84).
**Notes:** Router registered before `StaticFiles` (Pitfall E); reads `request.app.state.session_factory`; Register uses the `register_value` alias `"register"` (CR-02). Functional-first; client-side refetch.

---

## Pre-existing engine gaps the editor exposes

| Option | Description | Selected |
|--------|-------------|----------|
| Additively fill H1 `KINSHIP_RECIPROCAL` gaps; flag missing DB-UNIQUE | Low-risk additive; constraint is planner's discretion (lean defer) | ✓ |
| Leave both as-is | Editor's reciprocal-suggestion would have coverage holes | |
| Fix both now (incl. UNIQUE migration + dedup) | UNIQUE constraint needs migration + data-dedup; not v1-mandated | |

**Auto choice:** Fill H1 gaps additively; flag DB-UNIQUE as planner's discretion (D-90).
**Notes:** Verified C4 — table missing `bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày` and doesn't round-trip asymmetric entries. UNIQUE-constraint mitigated for single-user by the per-series lock + reuse-upsert.

---

## Claude's Discretion

Deferred to planner/researcher (see CONTEXT.md §Claude's Discretion): exact store-function names/signatures; one-function-with-flag vs separate set/lock/clear; precise REST routes + DTO envelopes; one-generic vs per-entity history endpoint; SPA component decomposition + form/validation library; how warnings are surfaced; `KNOWN_PRONOUN_TERMS` shape; exact H1 keys added and whether to add the DB UNIQUE now; per-series-lock accessor form.

## Deferred Ideas

- Relationship-event authoring (event-aware only in v1)
- `bible_lock` table with `locked_by`/`locked_at`/`reason` (multi-user phase)
- DB `UniqueConstraint` on Bible identity (migration + dedup; planner's discretion)
- Character delete with cascading dependents
- Optimistic-concurrency version column / multi-process locking
- Per-series source/register/model override config → Phase 10 (SVC-05)
- Deeper bidirectional H1 reconcile refactor (beyond the additive fill)
- SSE/WebSocket live updates for the editor
