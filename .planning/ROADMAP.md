# Roadmap: Trezarr

## Overview

Trezarr is built leaves-first, novel-logic-last. We start by proving the mechanical file-in → file-out path (parse a real SRT, hit the user's LLM endpoint, validate, write a sidecar) with the blind-trust validation gate built in from day one. We then wire in \*arr discovery to get one real episode translated end-to-end — de-risking path-mapping and permissions, the ecosystem's biggest friction — before investing in the moat. With a working slice, we build the persistent Series Bible store, then the three-pass pronoun engine (the differentiator), then relationship-evolution and self-review on top of a proven consistency core. Finally we add the operator surfaces (web UI, hardened service, editable Bible) and the orthogonal depth (ASS/SSA + VTT formats, relational-fidelity source selection). Each phase delivers a coherent, verifiable capability; every v1 requirement lands in exactly one phase.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Codec & LLM Client Foundation** - Parse/serialize SRT and call the user's OpenAI-compatible endpoint as isolated, testable leaves (completed 2026-05-31)
- [x] **Phase 2: Mechanical Translation Core + Validation Gate** - Single-pass translate a parsed file and write a valid sidecar, gated by a hard pre-write quality check (completed 2026-05-31)
- [ ] **Phase 3: \*arr Integration + First Vertical Slice** - Discover a real episode via Sonarr/Radarr and translate it to a sidecar end-to-end (de-risk path-mapping & permissions)
- [x] **Phase 4: Series Bible Store & Schema** - Persistent, versioned, lockable per-series consistency store carried forward across episodes (completed 2026-06-01)
- [ ] **Phase 5: Three-Pass Pronoun Engine** - Analyze → translate with the directed Address Map + speaker/addressee attribution to apply correct Vietnamese pronouns
- [ ] **Phase 6: Relationship Evolution + Self-Review** - Track relationship shifts across episodes and run an LLM self-critique pass before finalizing
- [ ] **Phase 7: Web UI & Service Hardening** - Dockerized long-running service with config/queue/history/logs/retry, monitoring, and crash-safe resumption
- [ ] **Phase 8: Editable Series Bible UI** - View, correct, and lock Bible fields so human overrides propagate forward (the override valve)
- [ ] **Phase 9: Multi-Format — ASS/SSA + VTT** - Translate ASS/SSA and VTT while preserving styling, tags, positioning, and cue settings byte-identical
- [ ] **Phase 10: Source Selection & Per-Series Overrides** - Read Bazarr's subtitle inventory and pick the source language whose relational system best serves Vietnamese; per-series tuning

## Phase Details

### Phase 1: Codec & LLM Client Foundation

**Goal**: A standalone subtitle codec that round-trips SRT losslessly and a standalone LLM client wrapping the user's OpenAI-compatible endpoint — both fully testable without each other.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: FMT-01, ENG-01
**Success Criteria** (what must be TRUE):

  1. A real SRT file parses into an internal line model and serializes back byte-identical (indices, timecodes, segmentation preserved exactly)
  2. The codec exposes timecodes/indices as locally-owned data the LLM never touches (text is separable from timing)
  3. A configured base URL / model / API key produces a successful test call against the user's endpoint, with retries and a concurrency cap
  4. The LLM client degrades gracefully (JSON mode fallback) when an endpoint lacks strict structured-output support

**Plans:** 3/3 plans complete

- [x] 01-01-PLAN.md — Wave 0: project scaffold, pytest harness, 6 SRT fixtures, all test stubs (RED suite)
- [x] 01-02-PLAN.md — Wave 1A: SRT codec — SubLine/SubDoc model, encoding detection, byte-identical read_srt/write_srt (FMT-01)
- [x] 01-03-PLAN.md — Wave 1B: Config (TrezarrSettings + YAML source + SecretStr) and LLM client (AsyncOpenAI + semaphore + tier fallback) (ENG-01)

### Phase 2: Mechanical Translation Core + Validation Gate

**Goal**: Given a parsed source file, produce a translated Vietnamese SRT through a single LLM pass and write it as a correctly-named, atomic, UTF-8 sidecar — but only if it passes a hard pre-write validation gate.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: ENG-02, ENG-03, ENG-06, ENG-07, FMT-05
**Success Criteria** (what must be TRUE):

  1. A long file is batched within token limits without splitting a sentence or scene across batch boundaries, each batch translated with surrounding-line context
  2. Every output is gated before write: cue-count match, no untranslated/empty lines, monotonic timestamps, valid format — failing files are quarantined and logged, never written
  3. A passing translation is written as `Show.S01E01.vi.srt` (matching the video basename, ISO-639 `vi`) atomically (temp+rename) and as valid UTF-8
  4. A failed or rejected translation can be re-run idempotently without duplicating or corrupting output

**Plans:** 3/3 plans complete
**Wave 1**

- [x] 02-01-PLAN.md — Wave 0: test scaffold — tests/translate/ and tests/output/ RED stubs for all Phase 2 modules (ENG-02, ENG-03, ENG-06, ENG-07, FMT-05)
- [x] 02-02-PLAN.md — Wave 1: pure-Python transform layer — sentinel.py, batching.py, validate.py (7-check gate), write.py (atomic sidecar), TrezarrSettings Phase-2 fields

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Wave 2: engine.py + ledger.py + tenacity install — translate_file() entry point, numbered-line protocol, batch retry/quarantine, idempotency ledger

### Phase 3: \*arr Integration + First Vertical Slice

**Goal**: A real episode is discovered through Sonarr/Radarr, its source subtitle located on the shared filesystem, translated, and written as a Vietnamese sidecar the media server can read — the complete vertical slice, crude but end-to-end.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: INTG-01, INTG-03, INTG-04, AUTO-01, AUTO-03, AUTO-04
**Success Criteria** (what must be TRUE):

  1. Trezarr connects to Sonarr and Radarr via their REST APIs (API-key auth) and discovers media identity, file paths, and metadata without scanning disk
  2. A configured container↔host path mapping resolves the same media files the \*arr stack sees, and an unreadable path surfaces a clear error at startup rather than failing silently per-file
  3. Sidecars are written with correct PUID/PGID/UMASK permissions so the media server can read them
  4. Trezarr detects "has a source sub, lacks a good `vi` sub", queues it, tracks per-item state (incl. source-sub hash) to skip already-done items, and never re-triggers on its own output

**Plans**: 5 plans
**Wave 1**

- [x] 03-01-PLAN.md — Wave 0: dependency install (pyarr, pytest-httpx) + RED test stubs for all Phase-3 modules
- [x] 03-02-PLAN.md — Wave 1: TrezarrSettings Phase-3 fields + paths.py (path mapping, startup probe, traversal guard) + ledger D-27 docstring

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-03-PLAN.md — Wave 1: arr discovery clients sonarr.py + radarr.py (pyarr 6.x, X-Api-Key, path mapping)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-04-PLAN.md — Wave 2: discover layer (scan.py + gap.py) + apply_permissions (write.py extension)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 03-05-PLAN.md — Wave 4: CLI entry point trezarr run --once + console_scripts registration (end-to-end vertical slice)

### Phase 4: Series Bible Store & Schema

**Goal**: A persistent, versioned per-series Series Bible exists that records characters, terms, and register, carries forward across episodes, and supports per-field human locks — the stable schema everything downstream depends on.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: BIBLE-01, BIBLE-02, BIBLE-04, BIBLE-05, BIBLE-06
**Success Criteria** (what must be TRUE):

  1. A per-series Bible persists to SQLite, is loaded as context at the start of each episode, and is updated (versioned, append-with-provenance) after each
  2. The Bible records Characters (name in original Latin form, gender, rough age, role) and a Term Dictionary (proper nouns/titles/places/jargon → fixed Vietnamese rendering, incl. name-romanization policy)
  3. The Bible records a per-series Register/tone grounded in media metadata (genre/plot/era from Sonarr/Radarr/TMDB)
  4. A character/term established in S01E01 is carried forward unchanged to a later episode unless a locked edit or logged event changes it (precedence: human lock > prior value > new inference)

**Plans:** 4/4 plans complete
**Wave 1**

- [x] 04-01-PLAN.md — SQLAlchemy 2.0 async + aiosqlite + Alembic foundation; single baseline migration creates all 7 Bible tables; PRAGMA-per-connection engine; typed declarative models

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-02-PLAN.md — Series + register slice: MediaItem arr_metadata extension, Pydantic DTO boundary, get_or_create_series + load_series_bible (BIBLE-01, BIBLE-05)
- [x] 04-03-PLAN.md — Character + term_dictionary + merge_inferred + bible_event audit log; lock-precedence + atomic UPDATE+INSERT + carry-forward (BIBLE-02, BIBLE-04, BIBLE-06)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-04-PLAN.md — Ledger backend swap (JSON → SQLAlchemy LedgerSQLA), one-shot JSON→SQLite migration with commit-FIRST/rename-SECOND ordering, async ledger.check/record, cli.py startup wiring

### Phase 5: Three-Pass Pronoun Engine

**Goal**: The translation pipeline becomes Bible-aware: Pass 1 analyzes the full file into the Bible (building the directed Address Map), Pass 2 infers speaker/addressee per line and applies the correct Vietnamese pronoun pair. This is the core differentiator.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: ENG-04, BIBLE-03, PRON-01, PRON-02, PRON-03
**Success Criteria** (what must be TRUE):

  1. Pass 1 analyzes the full source file + metadata to build/update the Bible before Pass 2 translates any line, producing a directed Address Map (per ordered pair: self-term + address-term, supporting asymmetry)
  2. Pass 2 infers the speaker and addressee for each line from dialogue content, turn-taking, and vocatives, then applies the correct pronoun pair from the Address Map
  3. The same character pair keeps the same pronoun pair across an episode (no flips inside an exchange; reciprocal directions consistent)
  4. When attribution is low-confidence, the engine falls back to a safe register rather than risk a wrong intimate pronoun

**Plans:** 4/6 plans executed

**Wave 0**

- [x] 05-01-PLAN.md — Wave 0: test scaffold — RED stubs for all Phase-5 test files (ENG-04, BIBLE-03, PRON-01, PRON-02, PRON-03)

**Wave 1**

- [x] 05-02-PLAN.md — Wave 1A: Address Map store foundation — Series.address_maps ORM relationship, AddressMapDTO, upsert_address_pair/load_address_map, Phase-5 TrezarrSettings fields (BIBLE-03, ENG-04)
- [x] 05-03-PLAN.md — Wave 1B: Deterministic reconciliation utility — KINSHIP_RECIPROCAL, get_safe_default, reconcile_attributions (PRON-02, PRON-03)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-04-PLAN.md — Wave 2A: Pass 1 Bible analysis — analyze.py (BibleAnalysis model + analyze_file + merge_bible_analysis + BibleAnalysisError) (ENG-04, BIBLE-03)
- [ ] 05-05-PLAN.md — Wave 2B: Pass 2 attribution — attribute.py (LineAttribution + attribute_batch + Tier-3 degradation) (PRON-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 05-06-PLAN.md — Wave 3: Pipeline wiring — engine.py (build_translate_prompt pronoun hints + translate_file 3-pass flow + derive_episode_key) + cli.py (pass eligible_item + session_factory) (ENG-04, PRON-02, PRON-03)

### Phase 6: Relationship Evolution + Self-Review

**Goal**: The consistency engine deepens — relationship changes are tracked across episodes as episode-marked events so pronoun pairs evolve correctly, and an LLM self-review pass critiques and repairs its own output against the Bible before the file is finalized.
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: BIBLE-07, ENG-05
**Success Criteria** (what must be TRUE):

  1. A relationship shift (e.g. strangers→lovers, enemies→rivals) is recorded as an episode-marked transition, and the active pronoun pair derived from events up to episode N changes intentionally — not by silent drift
  2. A self-review pass re-reads translated output, checks Series Bible adherence (pronoun pairs, terms, register), and corrects violations before the validation gate
  3. The same character pair keeps a consistent pronoun pair from S01E01 to a later episode across a logged relationship change, with the change auditable

**Plans**: TBD

### Phase 7: Web UI & Service Hardening

**Goal**: Trezarr runs as a Dockerized, long-running, crash-safe service alongside the \*arr stack, with a web UI to configure connections and watch the queue/history/logs and retry failures — the \*arr-citizen baseline that makes unattended operation trustworthy.
**Mode:** mvp
**Depends on**: Phase 6
**Requirements**: SVC-01, SVC-02, SVC-03, SVC-04, AUTO-02, AUTO-05
**Success Criteria** (what must be TRUE):

  1. Trezarr deploys as a single Docker container with a `/config` volume (DB + config) and runs as a long-lived service alongside the \*arr stack
  2. A web UI configures Sonarr/Radarr/Bazarr connections, the LLM endpoint, and paths, with connection tests
  3. The UI shows a Queue (in-flight), History (completed/failed with per-item reason), and per-job logs, and a failed/rejected item can be retried from the UI
  4. Trezarr monitors for newly added media / new source subs on an ongoing basis (polling with webhook-trigger support), and resumes safely after a crash or restart without losing or duplicating work (per-series serialized, checkpointed)

**Plans**: TBD
**UI hint**: yes

### Phase 8: Editable Series Bible UI

**Goal**: The user can open the Series Bible, correct any field, and lock it; locked corrections survive re-analysis and propagate forward to every subsequent episode — the single human override valve that earns blind trust.
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: BIBLE-08, BIBLE-09
**Success Criteria** (what must be TRUE):

  1. The user can view and edit Characters, Address Map, Term Dictionary, and Register in the UI, with provenance/lock state visible
  2. An edited field can be locked; locked fields are read-only to Pass-1 merges and survive re-analysis unchanged
  3. A locked correction propagates forward — it appears in subsequent episode translations for at least the next several episodes without reverting

**Plans**: TBD
**UI hint**: yes

### Phase 9: Multi-Format — ASS/SSA + VTT

**Goal**: Trezarr handles ASS/SSA and VTT in addition to SRT, translating only dialogue text while leaving override tags, fonts, positioning, karaoke timing, headers, and cue settings byte-identical.
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: FMT-02, FMT-03, FMT-04
**Success Criteria** (what must be TRUE):

  1. ASS/SSA output translates only dialogue text and leaves override tags (`{\an8}`, `\pos`, fonts), drawing commands, `\N` breaks, and `[Script Info]`/`[V4+ Styles]` headers byte-identical
  2. Karaoke (`\k`) lines round-trip without corruption (preserved verbatim where remapping is unsafe)
  3. VTT parses and writes back round-tripping cue settings/positioning, and signs render in their original screen position in a media player

**Plans**: TBD
**UI hint**: yes

### Phase 10: Source Selection & Per-Series Overrides

**Goal**: When multiple source subtitles exist, Trezarr reads Bazarr's inventory and picks the source language whose honorific/relational system best preserves what Vietnamese needs (zh/ko/ja/th > en for East-Asian content), falling back gracefully — and power users can override source/register/model per series.
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: INTG-02, SRC-01, SRC-02, SVC-05
**Success Criteria** (what must be TRUE):

  1. Trezarr connects to Bazarr via its API and reads which source-language subtitles already exist for each item (never re-downloading)
  2. Trezarr can translate from any available source-language subtitle to Vietnamese (source-agnostic)
  3. When multiple sources exist, Trezarr selects the relationally-richest source (prefers Chinese/Korean/Japanese/Thai for East-Asian content over English) and falls back to whatever is available
  4. A user can set per-series overrides for source-language preference, register, and model

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Codec & LLM Client Foundation | 3/3 | Complete    | 2026-05-31 |
| 2. Mechanical Translation Core + Validation Gate | 3/3 | Complete    | 2026-05-31 |
| 3. \*arr Integration + First Vertical Slice | 5/5 | Awaiting Verification |  |
| 4. Series Bible Store & Schema | 4/4 | Complete   | 2026-06-01 |
| 5. Three-Pass Pronoun Engine | 4/6 | In Progress|  |
| 6. Relationship Evolution + Self-Review | 0/TBD | Not started | - |
| 7. Web UI & Service Hardening | 0/TBD | Not started | - |
| 8. Editable Series Bible UI | 0/TBD | Not started | - |
| 9. Multi-Format — ASS/SSA + VTT | 0/TBD | Not started | - |
| 10. Source Selection & Per-Series Overrides | 0/TBD | Not started | - |
