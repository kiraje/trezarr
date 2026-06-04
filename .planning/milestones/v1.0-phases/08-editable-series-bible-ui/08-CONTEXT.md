# Phase 8: Editable Series Bible UI - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** mvp (vertical slice — keep each capability to its success criterion; do not gold-plate)
**Discussion mode:** `--auto` (recommended defaults auto-selected; every decision below is a sensible default the planner/researcher may tune). Codebase grounded by the Trezarr harness specialists — **bible-consistency-auditor** + **vietnamese-linguist** scouted the store/merge/reconcile layers and the **finding-verifier** adversarially confirmed all six load-bearing premises (6 CONFIRMED, 0 refuted). Evidence is cited inline as `file:line`.

<domain>
## Phase Boundary

Phase 8 ships the **single human override valve** the product's blind-trust mission depends on: a web UI to **view, correct, and lock** the per-series Series Bible, where locked corrections survive re-analysis and propagate forward to every subsequent episode. It adds **no new translation logic, no new format/source surface, and no new persistence engine** — Phase 4 already shipped the storage (`locked_fields` JSON + `merge_inferred` precedence + the `bible_event` audit log) and explicitly deferred the *production lock-setter* to this phase; Phase 7 already shipped the React 19 + Vite 7 SPA + FastAPI `/api` surface this builds on.

Concretely, Phase 8 delivers (each mapped to a success criterion / requirement):

1. **View + edit the Bible (BIBLE-08, criterion 1).** A new SPA section lets the user view and edit **Characters** (name/gender/age/role), the directed **Address Map** (per ordered pair: self-term + address-term), the **Term Dictionary** (source term → Vietnamese rendering + category), and the series **Register**, with **provenance + lock state visible** per field.

2. **Lock a corrected field (BIBLE-08, criterion 2).** Any edited field can be **locked**; locked fields become read-only to Pass-1 inference merges and survive re-analysis unchanged. This is the FIRST production code that ever writes a non-empty `locked_fields` (verified C1 — every store insert helper hard-codes `locked_fields=[]` today: `store.py:172,461,554,669`).

3. **Locked corrections propagate forward (BIBLE-09, criterion 3).** A locked correction appears in subsequent episode translations for at least the next several episodes without reverting. This is **already structurally guaranteed** by the merge precedence (`human lock > prior > inference`) + carry-forward + the reconcile lock-first branch — the UI only needs to *set the lock correctly* (verified: `merge.py:84`, `reconcile.py:267-277`, `engine.py:785-814`).

Requirements covered: **BIBLE-08, BIBLE-09.**

**In scope:**
- A new FastAPI **`bible` router** under `/api` (mounted before the SPA `StaticFiles` mount — Pitfall E), following the Phase-7 route pattern (`APIRouter`, `request.app.state.session_factory`). Read endpoints reuse the existing `load_series_bible` / `load_address_map` store reads + the existing DTOs; write endpoints call a **new lock-aware store writer**.
- A **new store write path** — `apply_human_edit` / `set_lock` / `clear_lock` (+ an AddressMap-specific variant) — that sets a value AND/OR a lock AND emits a `bible_event(source="lock")` in **one transaction**, with an **in-transaction re-read** of the live row (WR-01 stale-DTO defence). This is NOT `merge_inferred` (verified C2: `merge_inferred` *skips* locked fields at `merge.py:84` and *raises `TypeError`* on an `AddressMapDTO` at `store.py:1086` — Pitfall G).
- A **read-only per-field history** read (e.g. `load_field_history(series_id, entity_type, entity_id, field?) -> list[BibleEventDTO]`) over the existing `bible_event` table (index-covered: `ix_bible_event_series_entity_time`). No schema change.
- New **SPA pages/components**: a Series list, a Series-Bible editor with Characters / Address Map / Term Dictionary / Register sections, lock toggles, provenance badges, and a per-field history drill-down — reusing `AppShell`, `StatusBadge`, `Toast`, `MaskedSecretInput`-style inputs, and `api/client.ts`.
- A shared **`KNOWN_PRONOUN_TERMS`** vocabulary constant (self-list + address-list), co-located with `KINSHIP_RECIPROCAL` in `reconcile.py`, surfaced through the API to power the Address-Map term picker (single source of truth — never duplicated in the frontend).
- **Additively filling the H1 `KINSHIP_RECIPROCAL` gaps** so the editor's reciprocal-suggestion UX has coverage for the relationships it exposes (uncle/aunt, teacher/student, intimate-rude) — see D-90.

**Out of scope (deferred to owning phases / v2):**
- **Per-line / per-cue human review or correction workflow** — explicitly out of scope project-wide; the editable Series Bible is the *only* human touchpoint (PROJECT.md §Out of Scope).
- **Relationship-event AUTHORING** (creating/editing episode-marked transitions, BIBLE-07) — the editor is event-*aware* (read-only display + `valid_from_episode` marker) but does not author transitions (D-88). BIBLE-08 scope lists characters/address-map/terms/register, not events.
- **Retroactive re-translation** of already-finished episodes after a lock — forward-only, carried from Phase 6 (D-84).
- **Web UI authentication / multi-user accounts / per-lock `locked_by`/`reason` provenance** — v1 is single-user, no-auth, trusted-LAN (D-78); `bible_event(source="lock")` covers what/when/old/new (D-79).
- **Per-series source/register/model overrides** (SVC-05) → **Phase 10**. (Register *value* is editable here; per-series source/model *override config* is Phase 10.)
- **ASS/SSA + VTT** → **Phase 9**; **Bazarr inventory / source selection** → **Phase 10**.
- **Character delete + adding DB UNIQUE constraints on Bible identity** — flagged risks, not v1-mandated (D-83, D-90).

</domain>

<decisions>
## Implementation Decisions

Continues the project decision ledger (Phase 1 D-01…D-11, Phase 2 D-12…D-20, Phase 3 D-21…D-30, Phase 4 D-31…D-39, Phase 5 D-40…D-50, Phase 6 D-51…D-60, Phase 7 D-61…D-78). **Phase 8 = D-79…D-90.** All numbered values are sensible defaults the planner/researcher may tune; all are overridable in planning.

> **Scale note for the planner.** This phase is narrower than Phase 7 — it adds one router + one store-write path + one SPA section on top of fully-built persistence and a fully-built SPA shell. A reasonable slicing: (W0) RED test scaffold; (W1) the lock-aware store writer + history read + the `KNOWN_PRONOUN_TERMS`/H1 additive engine fix; (W2) the `bible` REST router; (W3) the SPA editor pages. The riskiest code is the **new write path honoring the store invariants** (section §Landmines), not the UI.

### Capability A — Bible persistence: the lock-write path (BIBLE-08/09 server side)

#### Lock storage model (D-79)
- **D-79: Keep the Phase-4 `locked_fields: JSON` array per row. Do NOT introduce a `bible_lock` table. No migration for locks.** Verified (C3): no `bible_lock` table and no `locked_by`/`locked_at`/`reason` columns exist; `locked_fields` JSON is already on `series`/`character`/`term_dictionary`/`address_map` (`models.py:85,126,154,185`; `0001_baseline_bible_schema.py:52,72,83,106`). For a single-user/no-auth deployment (D-78), `locked_by` is always the one operator and `bible_event(source="lock")` already records who-equivalent/when/old/new — so the deferred `bible_lock` table (Phase-4 §Deferred) adds cost (migration + rewriting `get_locked_fields` and the direct lock-reads at `analyze.py`, `reconcile.py`, `store.py:693`) with no v1 value. `merge.py:5-6` documents the `get_locked_fields` accessor as the future swap point — keep it as the seam, defer the table to a multi-user phase.

#### Human-edit write path (D-80)
- **D-80: Add a NEW dedicated store writer — `apply_human_edit` / `set_lock` / `clear_lock` (+ an AddressMap-specific variant). Do NOT reuse `merge_inferred`.** Verified (C2): `merge_inferred` *skips* any field already in `locked_fields` (`compute_field_changes`, `merge.py:83-85`) so it would silently no-op an authoritative human re-edit of a locked field; and its isinstance dispatch raises `TypeError` on `AddressMapDTO` (`store.py:1073-1089`, Pitfall G). The new writer MUST, in **one `async with session.begin()`**: (1) re-read the live row via `session.get(model, id)` **inside** the txn and read current value+locks off the **row**, never the request DTO (WR-01 stale-DTO defence); (2) set the new value and, when locking, add the field to `locked_fields` by **reassigning a new list** (`row.locked_fields = [*row.locked_fields, field]`) — never `.append()`, because the column is a plain `JSON` type, not `MutableList`, and in-place mutation is not dirty-tracked (silent data loss footgun); (3) emit a `BibleEvent(source="lock", old_value, new_value, episode_key=None)` in the **same** txn (D-32 audit completeness); (4) return a **DTO**, never the ORM row (D-39 boundary). Mirror the existing transaction-owning pattern of `upsert_character`/`upsert_term`/`upsert_address_pair` (`store.py:779-952`); for address pairs clone `_upsert_address_pair_in_session` (`store.py:601-717`), which already reads locks off the row. Decide & document the lock-toggle-without-value-change case explicitly (emit a lock-only event or skip).

#### Concurrency / stale-edit defense (D-81)
- **D-81: Route UI Bible writes through the SAME per-series `asyncio.Lock` the worker uses, plus the in-txn re-read (D-80).** Verified (C6): the worker holds `_series_locks[series_id]` (`worker.py:51`, acquired `:412-417`) for a whole episode, but Pass-1 (`merge_bible_analysis`) issues **many independent short transactions** — one `merge_inferred`/`upsert_*` per entity, each its own `session.begin()` (`analyze.py:382,410,446`; `store.py:825,877,936,1097`). A UI write that doesn't take the same lock can interleave between two inference commits and be clobbered, and there is **no DB UNIQUE** to catch a concurrent duplicate-insert. Optimistic concurrency (a version/`updated_at` column) only *detects* a clobber and needs a migration; last-writer-wins silently violates the moat. Cheapest correct fix: the write endpoint acquires `_series_locks[series_id]` before its store write. Expose a small accessor (e.g. `get_series_lock(series_id)`) instead of reaching into the private dict. (Per-process `asyncio.Lock` is sufficient — D-61 mandates one uvicorn process.)

#### Provenance / history read (D-82)
- **D-82: Lock badge + current `source` shown inline (derived from `locked_fields`, zero new query); a cheap read-only per-field `bible_event` history as a drill-down.** Verified: `bible_event` is index-covered (`ix_bible_event_series_entity_time`) and `BibleEventDTO` (`dto.py:175-203`) already serializes `field/old_value/new_value/source/created_at`. Add one read-only store function returning `list[BibleEventDTO]`; no schema change. Do **not** promise actor/reason beyond the `source` enum — there is no such column. (Criterion 1's "provenance/lock state visible" is satisfied by the badge alone; the timeline is the high-value, low-cost extra.)

#### Add / delete scope (D-83)
- **D-83: View + edit + lock + ADD; DELETE limited to Term and Address-pair (leaf rows); Character delete DEFERRED.** Adds MUST go through the identity-aware upsert helpers (`upsert_character`/`upsert_term`/`upsert_address_pair`) so the normalization SELECT-before-INSERT runs — a hand-rolled `session.add(...)` can fork a duplicate-identity row (there is **no DB UNIQUE** on Character/Term/AddressMap identity — verified C3 — only a non-unique `ix_character_series_name`). Address-pair add requires two existing `character.id`s (FK `address_map.*_character_id → character.id`), so the UI uses **character pickers**, not free-text. **Character delete is the referential-integrity hazard**: `address_map` and `relationship_event` FK to `character.id` with no DB-level cascade (the ORM `cascade` is only on the `Series` relationships, and SQLite enforces FKs only under `PRAGMA foreign_keys=ON`). For v1: no character delete (edit-only); if demanded later, do a cascading delete of dependent pairs/events in one transaction with explicit confirm.

### Capability B — Address Map editing (the Vietnamese-correctness surface)

#### Reciprocal coherence on edit (D-85)
- **D-85: When the user edits a directed pair (e.g. John→Mary self=`anh`,address=`em`), SUGGEST the reciprocal (Mary→John) side-by-side, pre-filled from `KINSHIP_RECIPROCAL`, and let the user confirm — do not force-write it, do not leave it silently untouched.** Directed asymmetry is sacred (two separate rows keyed `(series_id, speaker_id, addressee_id)`, `store.py:644-648`) — period/historical drama has legitimate asymmetric address. Pure auto-write overrides a human who knows the exception; leave-untouched replicates the H1 silent-incoherence bug. If the forward pair has **no** `KINSHIP_RECIPROCAL` entry (the H1 gap — verified C4), show an explicit "no known reciprocal — set the reverse manually" state rather than a blank. On save, write both rows; if the user locks only the forward direction, the reverse stays inference-updatable.

#### Term vocabulary input (D-86)
- **D-86: Self-term / address-term inputs are a COMBO — a dropdown of the shared `KNOWN_PRONOUN_TERMS` constant + a "custom…" escape hatch; custom values are `.strip()`-ed.** Free-text alone is the highest-yield typo vector (`"ahn"`/`"anh"`, trailing space, near-identical diacritics) — a typo silently never matches `KINSHIP_RECIPROCAL` (reciprocity drops) and is applied verbatim into subtitles. A pure dropdown handcuffs advanced fansubbers needing `dì/cậu/mợ`, regional terms, or `tao/mày`. The combo keeps the 95% case typo-proof while preserving expert override. `KNOWN_PRONOUN_TERMS` is a new constant co-located with `KINSHIP_RECIPROCAL` in `reconcile.py`, exposed via the API — **never** duplicated in the frontend (so the picker and the reciprocity table can't drift).

#### Edit validation / warnings (D-87)
- **D-87: Warn-but-allow on relational risks; BLOCK only on an empty/whitespace term when locking a pair.** The lock is the override valve — a hard block defeats it. **Warn** (non-blocking) on: (1) reciprocal incoherence (entered pair contradicts the existing reverse row — surfaces H1 to the human); (2) self/address pair not in the kinship table ("no auto-reciprocal will be inferred"); (3) an intimate term (`anh/em`, `tao/mày`) on a pair the analyzer resolved by safe-default / below `pronoun_confidence_threshold` ("analyzer wasn't confident — confirm"); (4) gender mismatch — `address_term` contradicting the addressee's `Character.gender` (e.g. `anh/ông` on a female). **Block** only on locking a pair with an empty/whitespace term: verified (C5) the reconcile lock-first branch writes the locked pair into `resolved_map` **only when `self_term is not None AND address_term is not None`** (`reconcile.py:275`) — otherwise it falls straight through to the confidence/safe-default gate and the human's lock is **silently ignored**. So a locked pair MUST persist both terms non-None.

#### Relationship-event scope (D-88)
- **D-88: Defer relationship-event AUTHORING; make the editor event-AWARE.** BIBLE-08 scope is characters/address-map/terms/register — not events. A full transition editor risks the precedence chain (`lock > logged-transition > carried-forward > safe-default`, `reconcile.py`). BUT editing the current Address-Map pair while hiding that a transition exists is a trap: a logged `relationship_event` at the current episode re-derives the pair's terms and an unlocked human edit gets clobbered on the next run (`store.py:691-703`). So the v1 editor MUST: display existing `relationship_events` for the pair (read-only) and the `valid_from_episode` marker, and make unmistakable that **locking is the only way to pin an edited pair against a future transition.** Event authoring is a clean follow-up phase.

#### Lock reaches application (D-89, confirmation — not a new build)
- **D-89: Confirmed — a locked Address-Map pair defeats the PRON-03 safe-default gate and reaches Pass-3 application, contingent on both terms non-None (D-87).** Verified end-to-end: reconcile lock-first branch checks the lock *before* the confidence gate (`reconcile.py:267-277`); persistence skips locked fields on re-run (`store.py:691-699`); the locked `(self,address)` flows `resolved_map → per_batch_hints → build_translate_prompt` onto the cue (`engine.py:785-814`). No new engine work is required for the lock to "win" — only the correct lock write (D-80) + the non-None guard (D-87).

### Capability C — Frontend (SPA editor)

#### SPA surface (D-84)
- **D-84: Extend the Phase-7 React 19 + Vite 7 SPA; reuse its shell, components, and API client. Client-side refetch/polling; functional-first.** New pages: a **Series list** → a **Series-Bible editor** with Characters / Address Map / Term Dictionary / Register sections, lock toggles, provenance badges, and the per-field history drill-down (D-82). Reuse `frontend/src/components/{AppShell,StatusBadge,Toast}.tsx`, a masked/validated input akin to `MaskedSecretInput.tsx`, and `frontend/src/api/client.ts`; add routes to `App.tsx`. DTOs (`SeriesBibleDTO`/`CharacterDTO`/`TermDTO`/`AddressMapDTO`/`BibleEventDTO`) are the wire models; **Register uses the `register_value` Pydantic alias `"register"`** (CR-02 shadowing fix, `dto.py`) — the API contract must respect it. No design mandate (this is the override valve, not a visual-design phase); it is a real SPA, not server-rendered.

### Pre-existing engine gaps the editor exposes (D-90)
- **D-90: Additively FILL the H1 `KINSHIP_RECIPROCAL` gaps; FLAG the missing DB-UNIQUE on Bible identity (planner's discretion, lean defer).** Verified (C4): the reciprocal pass does a single forward `.get()` (`reconcile.py:353-358`) and the table (`reconcile.py:35-54`) is missing `bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày` and does not round-trip asymmetric entries (e.g. `("con","cha")` is not a key). Since the editor's reciprocal-suggestion UX (D-85) exposes exactly these relationships, add the missing forward + reverse keys so entries round-trip — a low-risk additive change, ideally with a junior-only-attribution regression test. Separately, the absence of a DB `UniqueConstraint` on Character/Term/AddressMap identity (verified C3) means a bypass of the upsert path can fork duplicate rows; adding the constraints is a migration + data-dedup and is **not** v1-mandated — the per-series lock (D-81) + reuse-upsert (D-83) mitigate it for single-user. Recommend defer unless the planner finds it cheap.

### Claude's Discretion
Planner/researcher retain latitude on: exact new store-function names/signatures (`apply_human_edit` vs `set_field` + `set_lock`); whether the writer is one function with a `lock: bool` flag or separate set/lock/clear functions; the precise REST route shapes (`GET /api/series`, `GET /api/series/{id}/bible`, `PATCH /api/series/{id}/characters/{cid}`, `POST .../lock`, `GET .../history`, etc.) and response DTO envelopes; whether the history drill-down is one generic endpoint or per-entity; the SPA component decomposition, routing, and form/validation library (functional-first, no design mandate); how the warnings (D-87) are surfaced (inline vs toast); whether `KNOWN_PRONOUN_TERMS` is one flat list or split self/address with gender hints; the exact set of H1 reciprocal keys added (D-90) and whether to add the DB UNIQUE constraints now or defer; and whether to expose the per-series-lock accessor as a worker helper or a small service object.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` §Series Bible — **BIBLE-08** (view/edit characters/address-map/terms/register; edits lockable, survive re-analysis), **BIBLE-09** (locked corrections propagate forward — the override valve); also **BIBLE-01..BIBLE-07** for the data model the UI edits and the invariants it must not break (carry-forward BIBLE-06, relationship evolution BIBLE-07)
- `.planning/ROADMAP.md` §"Phase 8: Editable Series Bible UI" — goal + the **3 success criteria** (view+edit with provenance/lock visible; lock survives re-analysis; locked correction propagates forward several episodes)
- `.planning/PROJECT.md` §Out of Scope ("the editable Series Bible is the **only** human touchpoint"; no per-line review UI) and §Key Decisions ("Persistent, **editable** per-series Series Bible … corrections lock and propagate forward" — this phase closes the "Editor UI deferred" note)

### Project-wide grounding (the prescriptions for THIS phase)
- `CLAUDE.md` §"Series Bible Persistence — Prescribed Shape" — the entity model (`character`, `address_map` directed pairs, `term_dictionary`, `relationship_event`) + the `locked` per-field "human-override valve" this UI sets
- `CLAUDE.md` §"Technology Stack" / "Recommended Stack" — React 19 / Vite 7 SPA served by FastAPI `StaticFiles` (single image/port), Pydantic v2 DTOs end-to-end, SQLAlchemy 2.0 async; §"What NOT to Use" — no second web server, no sync clients in the loop

### Prior-phase foundations this phase consumes & extends (read these first)
- `.planning/phases/04-series-bible-store-schema/04-CONTEXT.md` — **D-32** (`bible_event` append-only audit log — explicitly *"the foundation for Phase 8's UI"*; source enum `inference|lock|import|system`), **D-34** (`locked_fields` JSON + `merge_inferred` precedence + the `get_locked_fields(entity)` accessor as the swap seam; *"Phase 4 never sets locks — Phase 8's UI is the production setter"*; the deferred `bible_lock` table note D-79 evaluates), **D-39** (Pydantic DTOs at the store boundary; SQLAlchemy never escapes `store.py`)
- `.planning/phases/07-web-ui-service-hardening/07-CONTEXT.md` — **D-73** (React 19 + Vite 7 SPA + REST + client-side polling; *"sets up the Phase-8 Bible editor"*), **D-70** (config-writer / masked-secret pattern + `request.app.state` wiring), **D-78** (single-user/no-auth/trusted-LAN — why D-79 needs no `locked_by`), **D-68** (the per-series `asyncio.Lock` D-81 reuses), the router-before-`StaticFiles` mount ordering (Pitfall E)
- `.planning/phases/05-three-pass-pronoun-engine/05-CONTEXT.md` + `.planning/phases/06-relationship-evolution-self-review/06-CONTEXT.md` — the directed Address Map + reconciliation + `relationship_event` evolution + the PRON-03 safe-default gate the lock must defeat (D-89); the cross-module name-normalization contract
- `.trezarr-harness/REVIEW-20260601_194849.md` — Phase-5 review: **B1/M1** (`.strip().lower()` name normalization is a cross-module contract — the edit UI's character identity must honor it; now applied at the DB identity SELECT, `store.py:445`), **H1** (the `KINSHIP_RECIPROCAL` single-directional reciprocity gap D-90 fills)

### Existing code to reuse / extend (do not reinvent — file:line verified)
- `trezarr/bible/store.py` — `load_series_bible` (`:189-246`, the eager-loaded read API the editor reuses verbatim), `load_address_map` (`:1007-1023`), `get_character` (`:725-744`, normalized identity), `upsert_character`/`upsert_term`/`upsert_address_pair` + `_upsert_*_in_session` (`:779-952`, `:601-717` — the identity-aware, single-txn, lock-respecting write pattern to MIRROR for D-80), the hard-coded `locked_fields=[]` insert sites (`:172,461,554,669`) Phase 8 supersedes
- `trezarr/bible/merge.py` — `get_locked_fields` (`:30-46`, reuse for reads / future swap seam) + `compute_field_changes` (`:49-90`, the precedence engine the human-edit writer must NOT route through, since it skips locked fields)
- `trezarr/bible/models.py` — entity tables + `locked_fields` JSON columns (`:85,126,154,185`); `AddressMap` directed identity (`:159-187`); `Character` index-not-unique (`:117`); `BibleEvent` schema (`:221-264`)
- `trezarr/bible/dto.py` — `SeriesBibleDTO`/`CharacterDTO`/`TermDTO`/`AddressMapDTO`/`BibleEventDTO` (the API wire models); **Register `register_value` alias=`"register"`** (CR-02)
- `trezarr/translate/reconcile.py` — `KINSHIP_RECIPROCAL` (`:35-54`) + reciprocal pass (`:351-359`) [D-90 fills gaps; D-86 adds `KNOWN_PRONOUN_TERMS` here], lock-first branch (`:267-277`, the non-None guard `:275`), safe-default (`:99-125`)
- `trezarr/translate/engine.py` — lock→hint→Pass-3 application (`:785-814`) confirming a locked pair reaches the subtitle
- `trezarr/web/app.py` — router-include-before-`StaticFiles` (Pitfall E) + `app.state.session_factory`; the new `bible` router registers here
- `trezarr/web/routes/queue.py` / `trezarr/web/routes/settings.py` — the `APIRouter()` + `_get_session_factory(request)` pattern to mirror; `settings.py` `GET/PUT` shape for an editable resource
- `trezarr/web/worker.py` — `_series_locks` (`:51`) + acquire (`:412-417`); expose a `get_series_lock(series_id)` accessor for D-81
- `trezarr/db/migration_runner.py` — `run_migrations_to_head` (only if a migration is added — recommended: none; chain a `0003_*` to head `0002` if so)
- `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/components/{AppShell,StatusBadge,Toast,MaskedSecretInput}.tsx`, `frontend/src/pages/{Settings,Queue,History,JobLogs}.tsx` — extend with Bible pages/components

### Research (risk & stack grounding)
- `.planning/research/STACK.md` — SQLAlchemy 2.0 async + Pydantic-everywhere + React/Vite serving patterns
- `.planning/research/ARCHITECTURE.md` — "API for knowledge, filesystem for action"; the Series Bible as the consistency substrate the UI now exposes
- `.planning/research/PITFALLS.md` — re-check anything tagged Bible / lock / concurrency / DTO-boundary / SQLite-single-writer; specifically the stale-DTO and single-txn concerns D-80/D-81 address

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`load_series_bible` (`store.py:189-246`)** — already eager-loads characters, terms, address_map, relationship_events in one query (`selectinload`). The editor's "view Bible" screen reuses it verbatim; no new read for the main view.
- **`_upsert_*_in_session` helpers (`store.py:601-717`, `405-461`, etc.)** — the canonical single-transaction, identity-normalized, lock-respecting write shape. D-80's human-edit writer mirrors them; D-83's add path calls the public `upsert_*` wrappers so normalization runs.
- **`bible_event` table + `BibleEventDTO`** — the provenance/history substrate (D-32) is fully built and index-covered; the only missing piece for D-82 is a read function returning `list[BibleEventDTO]`.
- **Phase-7 SPA shell + `/api` router pattern + `_series_locks`** — `AppShell`/`StatusBadge`/`Toast`/`api/client.ts`, the `APIRouter` + `request.app.state.session_factory` route pattern, and the per-series lock are all in place; Phase 8 adds one router + one SPA section + one lock-aware writer on top.

### Established Patterns
- **Lock precedence `human lock > prior > inference` (D-34)** — enforced in `compute_field_changes` (`merge.py:84`) and the AddressMap skip (`store.py:698`) and the reconcile lock-first branch (`reconcile.py:267-277`). The human-edit writer is the ONE path allowed to override a lock; inference paths never.
- **Pydantic-only store boundary (D-39)** — routes receive/return DTOs; SQLAlchemy models never escape `store.py` (a contract test guards this). New routes must not import models.
- **`.strip().lower()` name-normalization cross-module contract (B1/M1)** — applied at the DB character identity SELECT (`store.py:445`) and every resolver; the edit UI's character create/rename MUST go through the upsert path to honor it. **Terms are case-SENSITIVE** (`store.py:539-541`) — surface this in the UI or a case-variant lock will appear "not to propagate."
- **JSON-column dirty-tracking** — `locked_fields` is a plain `JSON` column; reassign a new list to mark it dirty, never `.append()` in place (D-80 footgun).
- **Single uvicorn process (D-61)** — a per-process `asyncio.Lock` is a sufficient cross-cutting guard (D-81).

### Integration Points
- **`bible` router** (`/api/series`, `/api/series/{id}/bible`, edit/lock/history endpoints) ← React Bible-editor pages; registered in `app.py` before the `StaticFiles` mount (Pitfall E); reads `request.app.state.session_factory`.
- **Write endpoint** → acquire `get_series_lock(series_id)` (D-81) → new lock-aware store writer (D-80) → single txn: re-read row + set value + reassign `locked_fields` + `BibleEvent(source="lock")` → return DTO.
- **History endpoint** → `load_field_history(series_id, entity_type, entity_id, field?)` → `list[BibleEventDTO]` (D-82).
- **Lock → engine** (no new code): a set lock survives Pass-1 (`merge.py:84` / `store.py:698`), is carried forward (`load_series_bible`) and reaches Pass-3 (`engine.py:785-814`) — verifying criteria 2 & 3 is a test concern, not a build.

</code_context>

<specifics>
## Specific Ideas

- **Phase 4 built this phase's runway on purpose.** `bible_event` was specced as *"the foundation for Phase 8's UI"* and `locked_fields` + `get_locked_fields` were shipped with *"Phase 8's UI is the production setter"* written into D-34. Phase 8 is the INSERT/writer + the screen, not new persistence — exactly the leaves-first payoff the roadmap promised.
- **The whole phase reduces to "set `locked_fields` correctly, atomically, and through the right identity."** The harness verification showed criteria 2 & 3 are already guaranteed by the merge engine; the risk is entirely in the new write path (WR-01 re-read, JSON dirty-tracking, AddressMap special-casing, name normalization, the non-None-on-lock guard). Tests should prove "edit→lock→re-analyze→still there" and "edit→lock→next episode→still applied," which the engine already supports.
- **Locking is the only thing that pins a human edit.** An edited-but-UNLOCKED Address-Map pair or character field is overwritten by the next Pass-1 inference run (and a logged transition re-derives terms). The UI must make "lock to pin" unmistakable, or corrections will appear to silently revert episode-to-episode — the exact cross-episode-drift failure the moat exists to prevent.
- **A locked pair with a missing term is silently ignored.** `reconcile.py:275` requires both `self_term` and `address_term` non-None for the lock to win; the UI MUST block locking an incomplete pair (D-87). This is the single subtlest correctness trap in the phase.
- **One vocabulary source of truth.** `KNOWN_PRONOUN_TERMS` + `KINSHIP_RECIPROCAL` live together in `reconcile.py` and are surfaced via the API — never re-typed in the frontend — so the term picker and the reciprocity engine can't drift apart.

</specifics>

<deferred>
## Deferred Ideas

- **Relationship-event AUTHORING in the editor** (create/edit episode-marked transitions with suggested terms) → a clean follow-up phase. v1 editor is event-*aware* only (read-only display + `valid_from_episode`, D-88).
- **`bible_lock` table with `locked_by`/`locked_at`/`reason`** → a multi-user / audit-rich phase. v1 keeps `locked_fields` JSON + `bible_event(source="lock")` (D-79); the `get_locked_fields` accessor is the painless swap seam.
- **DB `UniqueConstraint` on Character/Term/AddressMap identity** → flagged risk (verified C3 — none exist today). A migration + data-dedup; mitigated for single-user by the per-series lock + reuse-upsert. Planner's discretion to add now or defer (D-90).
- **Character delete (with cascading dependent address-pairs/events)** → deferred; v1 is edit-only for characters to avoid the FK-orphan hazard (D-83).
- **Optimistic-concurrency version column / multi-process locking** → only needed if v1's single-process / per-series-lock model is outgrown.
- **Per-series source/register/model OVERRIDE config** (SVC-05) → **Phase 10**. (Register *value* is editable here; the per-series override *settings* are Phase 10.)
- **A richer engine fix for H1 beyond filling the table** (a fully bidirectional reciprocal-inference rewrite, junior-only-attribution coverage as a first-class concept) → Phase 8 does the low-risk additive fill (D-90); a deeper reconcile refactor can come later.
- **SSE / WebSocket live updates for the Bible editor** → nice-to-have; v1 uses client-side refetch like Phase 7 (D-84).

None of these block Phase 8. Discussion (auto-mode) stayed within phase scope.

</deferred>

---

*Phase: 08-editable-series-bible-ui*
*Context gathered: 2026-06-02*
