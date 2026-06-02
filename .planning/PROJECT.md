# Trezarr

## What This Is

Trezarr is an automated Vietnamese subtitle translator that runs as a companion to the
Bazarr / Sonarr / Radarr self-hosted media stack. It watches for media that has a
source-language subtitle but no high-quality Vietnamese one, translates it with the user's
own LLM endpoint, and writes a Vietnamese sidecar subtitle (`Show.S01E01.vi.srt`) next to the
media — fully automated, no human in the loop. Its mission is to produce Vietnamese subtitles
good enough to **replace a human translator**, with the glossary, pronoun, and relationship
consistency that ordinary machine translation destroys.

## Core Value

Vietnamese subtitles that stay **consistent and relationally correct across an entire series** —
the right pronoun pair (anh/em, chị/em, ông/bà...) for every relationship, the same character
names and terms from episode 1 to the finale — produced automatically. If everything else fails,
this consistency must work.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**Integration & automation (partial — Phase 3):**
- [x] Connect to Sonarr / Radarr via their REST APIs (X-Api-Key, pyarr 6.x) to discover the media library — Validated in Phase 3 (INTG-01). Bazarr connection deferred to Phase 10.
- [x] Share the same filesystem and write Vietnamese subtitles as sidecar files next to the media (auto-detected by Plex/Jellyfin/Emby) — Validated in Phase 3 (INTG-04: PUID/PGID/UMASK applied in-process; chmod failure quarantines; container↔host path mapping with traversal guard, INTG-03).
- [x] Detect media that has a source subtitle but no good Vietnamese subtitle and queue it — Validated in Phase 3 (AUTO-01 gap detection, AUTO-03 source-sub-hash idempotency, AUTO-04 self-output exclusion via ledger provenance). Continuous monitoring (poll + watchfiles + webhook) deferred to Phase 7.

**Vietnamese consistency engine — Series Bible (partial — Phase 4):**
- [x] Maintain a persistent, per-series Series Bible that is carried forward across all episodes — Validated in Phase 4 (BIBLE-01 SQLite-backed schema + LedgerSQLA, BIBLE-06 carry-forward via `merge_inferred` with lock-precedence; auto-population by LLM is Phase 5).
- [x] Bible tracks Characters (name kept in original Latin form, gender, rough age, role) — Validated in Phase 4 (BIBLE-02 `character` table + `upsert_character`).
- [x] Bible tracks a Term Dictionary — recurring proper nouns, titles, places, domain/fantasy/sci-fi jargon → fixed Vietnamese rendering — Validated in Phase 4 (BIBLE-02 `term_dictionary` table + `upsert_term`).
- [x] The Series Bible is auto-built but **editable** — corrections lock and propagate forward — Validated in Phase 4 (BIBLE-04 per-field `locked_fields` JSON enforced by `merge_inferred`; "human lock > prior value > new inference" verified). Editor UI shipped in Phase 8 (BIBLE-08/09).

**Pronoun engine + Bible auto-population (Phase 5):**
- [x] Three-pass pipeline — Pass 1 analyzes the full file + media metadata into the Bible (barrier), Pass 2 infers speaker/addressee per line, Pass 3 translates applying the resolved pronoun pair — Validated in Phase 5 (ENG-04 analyze-before-translate ordering). LLM self-review pass is Phase 6 (ENG-05).
- [x] Bible tracks a directed Address Map — per ordered character pair, self-term + address-term (e.g. `John→Mary: self=anh, address=em`), with reciprocal coherence — Validated in Phase 5 (BIBLE-03 `upsert_address_pair` + deterministic per-episode reconciliation).
- [x] Bible Register/tone inferred from media metadata + dialogue and grounded into prompts — Validated in Phase 5 (BIBLE-05, populated via `merge_inferred`).
- [x] Infer speaker and addressee per line from dialogue context and apply the correct pronoun pair; low-confidence → safe neutral/polite default rather than a wrong intimate pronoun — Validated in Phase 5 (PRON-01 attribution, PRON-02 application, PRON-03 safe fallback). Per-episode consistency is a deterministic reconciliation property, not an LLM gamble. (Live-LLM pronoun quality tracked in `05-HUMAN-UAT.md`.)

### Active

<!-- Current scope. Building toward these. Hypotheses until shipped. -->

**Integration (continuous monitoring + Bazarr):**
- [x] Continuous monitor for media that has a source subtitle but no good Vietnamese subtitle, and act automatically — Validated in Phase 7 (AUTO-02 hybrid trigger: APScheduler interval poll as source of truth + inbound `/webhook` for Sonarr/Radarr/Bazarr, both enqueue-only; AUTO-05 crash-safe per-series-serialized resume — `reconcile_in_progress` re-enqueues both `job` rows and `processed_file.in_progress` ledger rows on startup, per-series `asyncio.Lock` ordering with the single `LLMClient._semaphore` preserved). `watchfiles` shipped as a default-off toggle. Bazarr appears as a connection only; reading its inventory remains Phase 10 (INTG-02).
- [ ] Connect to Bazarr's API to read existing source-language subtitle inventory (Phase 10, INTG-02)

**Translation engine:**
- [ ] Use the user's own OpenAI-SDK-compatible LLM endpoint (configurable base URL / model / key)
- [x] LLM self-review pass — model critiques and corrects its own translation for consistency before the file is finalized — Validated in Phase 6 (ENG-05). Pass 4 runs after Pass-3 assembly and before the validation gate, checks Bible adherence (pronoun pair, terms, register), and is best-effort (D-59 — review failure never quarantines). (Live-LLM review quality pending in `06-HUMAN-UAT.md`.)
- [ ] Translation context includes: surrounding subtitle lines, full-file glossary, media metadata (plot/cast/genre from Sonarr/Radarr/TMDB), and the prior-episode Series Bible (Pass-1 metadata + Bible grounding shipped in Phase 5)

**Vietnamese consistency engine — the "Series Bible" (persistence Phase 4, LLM auto-population + Address Map Phase 5):**
- [x] Track relationship **evolution** across episodes (enemies→lovers, strangers→friends) with episode markers so pronoun choices change correctly over the series — Validated in Phase 6 (BIBLE-07). Relationship shifts are recorded as episode-marked `relationship_event` rows; `reconcile_attributions` applies precedence `human lock > logged transition (this episode) > carried-forward pair > safe default`, so an established pair's pronouns change intentionally (forward-only, never by silent drift) and auditably via `bible_event`.

**Smart attribution & source selection:**
- [ ] Source-agnostic input, but **intelligently prioritized**: when multiple source subtitles exist for the same media, prefer the source language whose honorific/relational system best preserves the information Vietnamese needs (e.g. prefer a Chinese/Korean/Japanese source for East-Asian content over English, which flattens all relationships to "I/you"); fall back to whatever is available

**Formats & delivery:**
- [ ] Handle SRT (universal baseline)
- [ ] Handle ASS/SSA while preserving styling, fonts, and positioning (anime/fansub use)
- [ ] Handle VTT
- [x] Ship as a Dockerized, long-running self-hosted service with a web config/dashboard UI, deployable alongside the *arr stack — Validated in Phase 7 (SVC-01 single multi-stage image [node→python], `/config` volume, port 6868, PUID/PGID via gosu, `trezarr serve` started by a FastAPI lifespan that owns one engine/scheduler/worker; SVC-02 config + connection-test UI with write-only/masked secrets; SVC-03/04 Queue/History/per-job-logs + Retry; a React 19 + Vite 7 SPA served by FastAPI `StaticFiles`)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Target languages other than Vietnamese — Vietnamese is the entire focus and the hard problem worth solving; other targets dilute it
- Replacing Bazarr's subtitle *downloading* — Bazarr already fetches source subs seamlessly; Trezarr's value is translation, not acquisition (full-replacement was considered and rejected)
- A human review/correction *UI workflow* — the product is fully automated; the editable Series Bible file is the only human touchpoint for v1
- Local/self-hosted model bundling — the user brings their own OpenAI-compatible endpoint; Trezarr does not host or ship a model
- Cost/token budgeting features — the user runs their own endpoint, so per-translation cost is not a v1 concern

## Context

- The target audience is self-hosters running the Sonarr/Radarr/Bazarr stack first; the Vietnamese fansub/media community is an eventual, intended audience (build for self, design to share).
- Vietnamese is uniquely hard for machine translation: it has no neutral "I/you" — every utterance encodes the relationship between speaker and listener through an extensive system of relational pronouns and kinship/honorific terms. Standard MT (and Bazarr's built-in translators) flatten this and produce subtitles that are tonally wrong or outright rude.
- Reference product for integration patterns and conventions: Bazarr (https://github.com/morpheus65535/bazarr) — Python + web UI, Dockerized, connects to Sonarr/Radarr via API, writes sidecar subtitle files. Trezarr mirrors this relationship one level up (Trezarr ↔ Bazarr/*arr).
- Key linguistic insight driving source selection: source languages structurally similar to Vietnamese (Chinese, Korean, Japanese, Thai — relational address, honorifics, speech levels) carry the relationship information that English discards, and therefore translate more faithfully into Vietnamese.

## Constraints

- **Tech stack**: LLM access is via an OpenAI-SDK-compatible endpoint (user-provided base URL/model/key)
- **Deployment**: Must run as a Dockerized self-hosted service with a web UI, deployable alongside Bazarr/Sonarr/Radarr
- **Integration**: Must interoperate cleanly with Sonarr/Radarr/Bazarr APIs and the *arr-stack filesystem/sidecar conventions
- **Compatibility**: Output subtitles must be auto-detected by common media players (Plex/Jellyfin/Emby) and preserve original styling for ASS/SSA
- **Quality bar**: Fully automated output must be trustworthy enough to use blind ("replace human translator") — consistency is non-negotiable

## Key Decisions

<!-- Decisions that constrain future work. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Companion to Bazarr/*arr, not a replacement | Bazarr already downloads source subs seamlessly; Trezarr adds translation as the smart layer | — Pending |
| Persistent, editable per-series "Series Bible" as the consistency core | Vietnamese needs relationship state to choose pronouns; it must persist across episodes and be human-correctable | ✓ Implemented (Phase 4 persistence/locks + Phase 5 LLM auto-population incl. directed Address Map; editor UI + production lock-setter shipped Phase 8, BIBLE-08/09). |
| LLM infers speaker/addressee from context | Subtitles rarely carry speaker labels; frontier-model inference is where "ultimate" quality comes from | ✓ Implemented (Phase 5) — Pass 2 attribution + deterministic reconciliation; one pronoun pair per ordered pair per episode, low-confidence → safe default |
| Track relationship evolution across episodes | Pronoun pairs change as relationships change (enemies→lovers); static maps would drift wrong | ✓ Implemented (Phase 6, BIBLE-07) — episode-marked `relationship_event` rows + reconciliation precedence make the active pair change intentionally (forward-only), not by silent drift |
| Source-agnostic input, prioritized by relational fidelity to Vietnamese | English flattens relationships; the original East-Asian source preserves the info Vietnamese needs | — Pending |
| Two-pass + LLM self-review pipeline | Full-file analysis enables consistency; a self-critique pass earns blind-trust automation | ✓ Implemented — three-pass analyze→attribute→translate shipped (Phase 5); LLM self-review (Pass 4, best-effort, pre-gate) shipped (Phase 6, ENG-05) |
| User-provided OpenAI-compatible endpoint | User already has their own LLM endpoint; avoids hosting models and cost-management scope | ✓ Implemented (Phase 1) — AsyncOpenAI client wraps base_url/model/key with retries, an asyncio.Semaphore concurrency cap, and json_schema→json_object→text fallback, as an isolated tested leaf |
| Dockerized service + web UI | Matches *arr-stack conventions self-hosters expect | ✓ Implemented (Phase 7) — single multi-stage image, `/config` volume, port 6868, PUID/PGID; FastAPI lifespan owns the APScheduler poll + `/webhook` receiver + per-series-serialized worker + the React/Vite SPA; crash-safe resume reuses the `in_progress` ledger checkpoint |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-02 after Phase 8 (Editable Series Bible UI) — see Phase 8 entry below for what shipped.*

*Phase 8 (Editable Series Bible UI, 2026-06-02): the single human override valve shipped — the first production code that ever writes a non-empty `locked_fields`. **BIBLE-08:** a new lock-aware store layer (`apply_human_edit_character/term/series/address_pair` + `set_lock`/unlock + `delete_address_pair`/`delete_term` + `load_field_history` + `load_all_series`) — each a single-transaction owner that re-reads the live row in-txn (WR-01 stale-DTO defence), reassigns the JSON `locked_fields` list (never `.append()`), and emits a `bible_event` (`source="lock"` only when locking, else `import`); it NEVER routes AddressMap through `merge_inferred` (Pitfall G). A thin `/api` `bible` router (13 endpoints, registered before StaticFiles — Pitfall E) enforces the entity/field allowlists, the D-87 empty-term-on-lock → HTTP 422 block, D-82 LIMIT bounds, and the per-series `asyncio.Lock` (D-81), all behind the D-39 Pydantic-only boundary (no SQLAlchemy import in the route, contract-tested). A React 19 editor extends the Phase-7 SPA: BibleList + a four-section BibleEditor (Characters / directed Address Map / Term Dictionary / Register) with LockBadge provenance, an inline FieldHistoryPanel, a PronounCombo sourced from `/api/pronouns` (D-86 + the WR-06 parental/elder terms), and a reciprocal-suggestion panel (D-85) that falls back to manual entry on the H1 kinship gaps (which Phase 8 additively filled — D-90). **BIBLE-09** (forward propagation) was already structurally guaranteed by the merge precedence + carry-forward + reconcile lock-first branch (verified by `test_locked_pair_survives_reconcile` / `..._propagates_to_next_episode`); the UI only needed to set the lock correctly. No Alembic migration (D-79 — `locked_fields` JSON reused). Discuss/plan/execute ran via the `--auto` chain; the discuss-phase decisions were grounded by the Trezarr harness (bible-consistency-auditor + vietnamese-linguist) and adversarially confirmed (finding-verifier, 6/6). Post-execution code review found + fixed 5 critical + 6 warnings (notably a broken address-pair unlock path, `term_id` not being authoritative, and a no-op D-90 regression test). A live agent-driven browser walkthrough (all 10 UAT steps) then caught + fixed a history-endpoint 500 (BibleEventDTO `datetime` not JSON-serialized) that unit tests + static review missed. 293 tests GREEN (292 passed, 1 skipped). Known follow-up: the SPA has no deep-link/refresh history-fallback (whole-SPA, affects Phase-7 routes too) — captured for a future task.*

*Phase 7 (Web UI & Service Hardening, 2026-06-02): Trezarr became a Dockerized, long-running, crash-safe *arr-citizen service. The CLI-only app gained a `trezarr serve` subcommand that starts a FastAPI app whose `lifespan` owns ONE async engine (disposed on shutdown — the CR-01 pattern re-homed to process scope), an APScheduler poll, an inbound `/webhook`, and a per-series-serialized queue worker — and serves a React 19 + Vite 7 SPA via `StaticFiles`. **SVC-01:** single multi-stage Dockerfile (node→python:3.12-slim), `/config` volume, port 6868, `gosu` PUID/PGID drop-privilege, `/api/health` HEALTHCHECK. **SVC-02:** `/api/settings` (write-only/masked secrets — D-70, a HIGH security gate) + `/api/test/{sonarr|radarr|bazarr|llm}` connection tests; YAML config-writer that filters unknown keys. **SVC-03/04:** `/api/queue`, `/api/jobs`, `/api/jobs/{id}/logs`, `/api/jobs/{id}/retry` (Retry re-enqueues, D-74) with per-job structured log capture (D-75); SPA Settings/Queue/History/JobLogs pages. **AUTO-02:** hybrid poll (source of truth) + webhook (enqueue-only, fast-200). **AUTO-05:** crash-safe resume reuses the `processed_file.in_progress` ledger checkpoint plus a new `job`/`job_log` table (Alembic 0002, the first migration since the Phase-4 baseline); `reconcile_in_progress` re-enqueues both arms on startup; per-series `asyncio.Lock` serializes a series' episodes while distinct series run concurrently, with the single `LLMClient._semaphore` left as the only global LLM cap (D-68). The shared `process_one_item` body was extracted from `cli.py` so the one-shot CLI and the daemon worker run identical per-item logic (D-62). Post-execution code review caught + fixed 2 blockers — CR-01 (the daemon Bible-aware path crashed because the worker stub lacked `media_item`; fixed by persisting a `media_item_json` snapshot on the Job and reconstructing it, with mechanical fallback) and CR-02 (GC-collectible `create_task` results) — plus 4 warnings. 274 tests GREEN. Verified 4/4 success criteria (SVC-01/02/03/04, AUTO-02/05); 10 live/visual items pending in `07-HUMAN-UAT.md` (SPA browser conformance, real `docker build`/run + PUID/PGID ownership, live *arr webhook).*

*Phase 6 (Relationship Evolution + Self-Review, 2026-06-02): the consistency core deepened — relationship changes now evolve pronouns across episodes, and the model self-reviews its own output before the gate. **BIBLE-07:** Pass 1's holistic `BibleAnalysis` now emits `relationship_events`; `merge_bible_analysis` writes episode-marked `relationship_event` rows (no migration — the table shipped empty in Phase 4); `load_series_bible` surfaces them on `SeriesBibleDTO`; `reconcile_attributions` gained a transition-precedence branch (`human lock > logged transition this episode > carried-forward pair > safe default`), with `_find_transition_for_pair` filtering `episode_marker == episode_key` (forward-only). A logged transition adopts this episode's attribution-confirmed terms (D-54 3-step `_derive_transition_terms`), so an established pair's pronouns change intentionally and auditably (`bible_event`), never by silent drift. **ENG-05:** a new best-effort Pass 4 (`build_review_prompt` + `_review_batch` + a Step-8.5 block in `translate_file`) runs after Pass-3 assembly and before `validate_subdoc`, re-checking pronoun pair / terms / register against the Bible and correcting violations via the numbered-line text protocol (no `response_model`, sentinel-protected, 1:1 cue mapping). It is structurally incapable of quarantining a file (D-59): `_review_batch` returns `list[str] | None` and never raises; the Pass-4 `TaskGroup` uses `except* Exception` with a pre-review fallback and no `_write_quarantine`. The single `LLMClient._semaphore` and the Pydantic-only store boundary (D-39) are preserved. Post-execution code review found + fixed 3 blockers (self-review ran blind because `dominant_pair` was never populated; transitions always collapsed to safe-default because suggested terms can't be persisted under the locked schema; a bare `except` mis-handled the Pass-4 `ExceptionGroup`) and 4 warnings; the 10 Phase-6 tests were promoted from xfail to real passes. 245 tests GREEN. Verified 9/9 must-haves (BIBLE-07, ENG-05). 2 live-LLM items pending in `06-HUMAN-UAT.md` (real-episode relationship-shift pronoun change; self-review quality on real output).*

*Phase 5 (Three-Pass Pronoun Engine, 2026-06-02): the translation pipeline became Bible-aware and shipped the core differentiator. `translate_file` now runs Pass 1 (full-file Bible analysis → merge characters/terms/register/directed Address Map, a barrier) → Pass 2 (per-cue speaker/addressee attribution with confidence) → deterministic reconciliation (one `(self_term, address_term)` per ordered pair per episode, reciprocal-coherent via a Vietnamese kinship table) → Pass 3 (numbered-line translation with per-line pronoun hints injected into the prompt; no mechanical substitution) → existing document gate → atomic write. New: `trezarr/bible/analyze.py`, `trezarr/translate/attribute.py`, `trezarr/translate/reconcile.py`, `upsert_address_pair`/`load_address_map` + `AddressMapDTO`, `Series.address_maps` relationship (no migration), `derive_episode_key` (parses SxxExx from filename), and Phase-5 `TrezarrSettings` fields. Low-confidence/unknown → safe neutral default (`tôi`/`bạn`); Tier-3-only endpoints degrade gracefully rather than quarantine; only Pass-1/2 logic failures quarantine. Single `asyncio.Semaphore` invariant and Pydantic-only store boundary preserved. Code review found + fixed 2 blockers (case-sensitive name resolution silently dropping pairs; a consistency test that didn't actually test consistency) and 7 warnings. 226 tests GREEN, 0 xfailed. Verified 4/4 must-haves (ENG-04, BIBLE-03, PRON-01/02/03). 2 live-LLM items pending in `05-HUMAN-UAT.md` (real-episode pronoun quality; the enable_pass1_analysis/enable_attribution toggle in production).*

*Phase 2 (Mechanical Translation Core + Validation Gate, 2026-05-31): `translate_file()` batches a parsed source (scene-gap/token-aware), translates via a single LLM pass with surrounding-line context, enforces a hard 7-check pre-write validation gate (failing files quarantined, never written), and writes an atomic UTF-8 `Show.S01E01.vi.srt` sidecar with idempotent re-run via a content-hash ledger (ENG-02, ENG-03, ENG-06, ENG-07, FMT-05 — verified 4/4).*

*Phase 4 (Series Bible Store & Schema, 2026-06-01): SQLite-backed Series Bible substrate ships — SQLAlchemy 2.0 async + aiosqlite + Alembic baseline migration creating 7 tables (series, character, term_dictionary, address_map, bible_event, relationship_event, processed_file). `get_or_create_series` lazily persists per-series rows with an arr_metadata snapshot from Sonarr/Radarr. `merge_inferred` enforces `human lock > prior value > new inference` and writes the row UPDATE + `bible_event` audit row in a single transaction (D-32). Per-field locks via `locked_fields` JSON survive merges. The Phase-2 JSON ledger is retired in favor of `LedgerSQLA` with a commit-first/rename-second one-shot JSON→SQLite migration. 208 tests GREEN. Register stays NULL by design — LLM populates it in Phase 5. Known advisory issues: CR-01 missing `await engine.dispose()` in `_run_once`, CR-02 Pydantic `register` field shadows BaseModel.register (rename + alias needed). 2 human UAT items pending in `04-HUMAN-UAT.md` (live *arr smoke, asyncio teardown). BIBLE-01/02/04/05/06 verified 5/5.*
