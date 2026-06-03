# Roadmap: Trezarr

## Overview

Trezarr is built leaves-first, novel-logic-last. We start by proving the mechanical file-in → file-out path (parse a real SRT, hit the user's LLM endpoint, validate, write a sidecar) with the blind-trust validation gate built in from day one. We then wire in \*arr discovery to get one real episode translated end-to-end — de-risking path-mapping and permissions, the ecosystem's biggest friction — before investing in the moat. With a working slice, we build the persistent Series Bible store, then the three-pass pronoun engine (the differentiator), then relationship-evolution and self-review on top of a proven consistency core. Finally we add the operator surfaces (web UI, hardened service, editable Bible) and the orthogonal depth (ASS/SSA + VTT formats, relational-fidelity source selection). Each phase delivers a coherent, verifiable capability; every v1 requirement lands in exactly one phase.

**v1.1 (UI v2: shadcn dashboard)** continues phase numbering at 11. The build order is dependency-forced: shadcn foundation first (gates everything), then app shell + route restructure (wraps all pages), then backend episodes enrichment (can run in parallel with shell; must land before the Series detail page), then new library pages (headline deliverables), then reskin-in-place of existing pages (BibleEditor last — highest regression risk), then Docker rebuild and live smoke test as the release gate.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

### v1.0 Phases (Complete)

- [x] **Phase 1: Codec & LLM Client Foundation** - Parse/serialize SRT and call the user's OpenAI-compatible endpoint as isolated, testable leaves (completed 2026-05-31)
- [x] **Phase 2: Mechanical Translation Core + Validation Gate** - Single-pass translate a parsed file and write a valid sidecar, gated by a hard pre-write quality check (completed 2026-05-31)
- [ ] **Phase 3: \*arr Integration + First Vertical Slice** - Discover a real episode via Sonarr/Radarr and translate it to a sidecar end-to-end (de-risk path-mapping & permissions)
- [x] **Phase 4: Series Bible Store & Schema** - Persistent, versioned, lockable per-series consistency store carried forward across episodes (completed 2026-06-01)
- [x] **Phase 5: Three-Pass Pronoun Engine** - Analyze → translate with the directed Address Map + speaker/addressee attribution to apply correct Vietnamese pronouns (completed 2026-06-01)
- [x] **Phase 6: Relationship Evolution + Self-Review** - Track relationship shifts across episodes and run an LLM self-critique pass before finalizing (completed 2026-06-01)
- [x] **Phase 7: Web UI & Service Hardening** - Dockerized long-running service with config/queue/history/logs/retry, monitoring, and crash-safe resumption (completed 2026-06-01)
- [x] **Phase 8: Editable Series Bible UI** - View, correct, and lock Bible fields so human overrides propagate forward (the override valve) (completed 2026-06-02)
- [ ] **Phase 9: Multi-Format — ASS/SSA + VTT** - Translate ASS/SSA and VTT while preserving styling, tags, positioning, and cue settings byte-identical
- [x] **Phase 10: Source Selection & Per-Series Overrides** - Read Bazarr's subtitle inventory and pick the source language whose relational system best serves Vietnamese; per-series tuning (completed 2026-06-02)

### v1.1 Phases (UI v2: shadcn dashboard)

- [ ] **Phase 11: shadcn Foundation & Purple Theme** - Install shadcn@2.10.0 + jolly-ui on Tailwind v3, wire the `@/` alias, establish the HSL CSS-variable purple dark theme, and verify a green build with no page content changes
- [ ] **Phase 12: App Shell + Route Restructure** - Replace the current AppShell with SidebarProvider + AppSidebar + Outlet, restructure routes so `/library` → `/series` + `/movies` + `/series/:id` and `/` → `/series`
- [ ] **Phase 13: Backend Episodes Enrichment** - Rewrite `GET /api/library/series/{id}/episodes` to return season-grouped episode records from Sonarr with audio languages and Bazarr subtitle inventory (fail-soft); expose `translated_count`/`total_count` on list endpoints
- [ ] **Phase 14: New Library Pages + Nav Badge Wiring** - Build Series list, Series detail (season-grouped Accordion with audio/subtitle badges, translate actions, search/filter/sort), Movies list, and wire the sidebar count+LIVE badges to live API data
- [ ] **Phase 15: Reskin Existing Pages** - Reskin-in-place Queue, History, Settings, Bible List, JobLogs, and Bible Editor onto shadcn primitives; remove legacy bridge tokens after all pages pass
- [ ] **Phase 16: Docker Rebuild + Live Smoke Test** - Rebuild the multi-stage Docker image with `--no-cache`, run the new dashboard on :6868 against the live *arr stack, and verify all six nav routes, episode badges, translate flow, and deep-link fallback

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

- [x] 04-02-PLAN.md — Wave 1: Series + register slice: MediaItem arr_metadata extension, Pydantic DTO boundary, get_or_create_series + load_series_bible (BIBLE-01, BIBLE-05)
- [x] 04-03-PLAN.md — Wave 1: Character + term_dictionary + merge_inferred + bible_event audit log; lock-precedence + atomic UPDATE+INSERT + carry-forward (BIBLE-02, BIBLE-04, BIBLE-06)

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

**Plans:** 6/6 plans complete

**Wave 0**

- [x] 05-01-PLAN.md — Wave 0: test scaffold — RED stubs for all Phase-5 test files (ENG-04, BIBLE-03, PRON-01, PRON-02, PRON-03)

**Wave 1**

- [x] 05-02-PLAN.md — Wave 1A: Address Map store foundation — Series.address_maps ORM relationship, AddressMapDTO, upsert_address_pair/load_address_map, Phase-5 TrezarrSettings fields (BIBLE-03, ENG-04)
- [x] 05-03-PLAN.md — Wave 1B: Deterministic reconciliation utility — KINSHIP_RECIPROCAL, get_safe_default, reconcile_attributions (PRON-02, PRON-03)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-04-PLAN.md — Wave 2A: Pass 1 Bible analysis — analyze.py (BibleAnalysis model + analyze_file + merge_bible_analysis + BibleAnalysisError) (ENG-04, BIBLE-03)
- [x] 05-05-PLAN.md — Wave 2B: Pass 2 attribution — attribute.py (LineAttribution + attribute_batch + Tier-3 degradation) (PRON-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 05-06-PLAN.md — Wave 3: Pipeline wiring — engine.py (build_translate_prompt pronoun hints + translate_file 3-pass flow + derive_episode_key) + cli.py (pass eligible_item + session_factory) (ENG-04, PRON-02, PRON-03)

### Phase 6: Relationship Evolution + Self-Review

**Goal**: The consistency engine deepens — relationship changes are tracked across episodes as episode-marked events so pronoun pairs evolve correctly, and an LLM self-review pass critiques and repairs its own output against the Bible before the file is finalized.
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: BIBLE-07, ENG-05
**Success Criteria** (what must be TRUE):

  1. A relationship shift (e.g. strangers→lovers, enemies→rivals) is recorded as an episode-marked transition, and the active pronoun pair derived from events up to episode N changes intentionally — not by silent drift
  2. A self-review pass re-reads translated output, checks Series Bible adherence (pronoun pairs, terms, register), and corrects violations before the validation gate
  3. The same character pair keeps a consistent pronoun pair from S01E01 to a later episode across a logged relationship change, with the change auditable

**Plans:** 3/3 plans complete

**Wave 0**

- [x] 06-01-PLAN.md — Wave 0: RED test scaffold — 3 test files (10 xfail stubs) for all Phase-6 behaviors (BIBLE-07, ENG-05)

**Wave 1** *(blocked on Wave 0 completion)*

- [x] 06-02-PLAN.md — Wave 1: Relationship Evolution slice — models.py ORM relationship, RelationshipEventDTO, record_relationship_event store writer, load_series_bible extension, RelationshipEventInference + BibleAnalysis + merge_bible_analysis Step 5, _find_transition_for_pair + reconcile_attributions transition-precedence branch, Phase-6-A config fields (BIBLE-07)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-03-PLAN.md — Wave 2: Self-Review slice — build_review_prompt + _review_batch + translate_file Step 8.5 (Pass 4 best-effort, no quarantine), Phase-6-B config fields (ENG-05)

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

**Plans**: 6 plans

**Wave 1**

- [x] 07-01-PLAN.md — Wave 1: RED test scaffold — tests/web/ package (8 test files) + migration stub for Alembic 0002 (SVC-01..04, AUTO-02, AUTO-05)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 07-02-PLAN.md — Wave 2: Service spine — job/job_log models + Alembic 0002 migration + Phase-7 TrezarrSettings + FastAPI lifespan (CR-01) + worker loop (per-series asyncio.Lock + crash-resume reconcile) + trezarr serve CLI (SVC-01, AUTO-05)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 07-03-PLAN.md — Wave 3A: Continuous monitoring — APScheduler interval poll + POST /webhook enqueue-only handler (AUTO-02)
- [x] 07-04-PLAN.md — Wave 3B: Config API — config read/write + secret masking + POST /api/test/{sonarr|radarr|bazarr|llm} connection tests (SVC-02)

**Wave 5** *(blocked on Wave 3 completion)*

- [x] 07-05-PLAN.md — Wave 5: Queue/History/Logs REST API + per-job log capture + React 19 + Vite 7 SPA (Settings/Queue/History/Logs + Retry) (SVC-03, SVC-04)

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 07-06-PLAN.md — Wave 6: Docker multi-stage packaging (PUID/PGID + /config volume + port 6868) + config.yaml.example Phase-7 fields (SVC-01 completion)

### Phase 8: Editable Series Bible UI

**Goal**: The user can open the Series Bible, correct any field, and lock it; locked corrections survive re-analysis and propagate forward to every subsequent episode — the single human override valve that earns blind trust.
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: BIBLE-08, BIBLE-09
**Success Criteria** (what must be TRUE):

  1. The user can view and edit Characters, Address Map, Term Dictionary, and Register in the UI, with provenance/lock state visible
  2. An edited field can be locked; locked fields are read-only to Pass-1 merges and survive re-analysis unchanged
  3. A locked correction propagates forward — it appears in subsequent episode translations for at least the next several episodes without reverting

**Plans:** 4/4 plans complete

**Wave 1**

- [x] 08-01-PLAN.md — Wave 0: RED test scaffold — tests/bible/test_human_edit.py, tests/web/test_bible_api.py, test_reconcile.py D-90 stub (BIBLE-08, BIBLE-09)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 08-02-PLAN.md — Wave 1: Engine layer — KINSHIP_RECIPROCAL gap fill (D-90), KNOWN_PRONOUN_TERMS constants (D-86), get_series_lock accessor (D-81), apply_human_edit_character/apply_human_edit_address_pair/load_field_history/load_all_series store writers (D-79, D-80, D-82, D-83)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 08-03-PLAN.md — Wave 2: REST router — trezarr/web/routes/bible.py + app.py registration; all Bible endpoints with D-39 boundary, entity_type allowlist, D-87 HTTP 422 guard, D-81 series lock (BIBLE-08, BIBLE-09)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 08-04-PLAN.md — Wave 3: SPA layer — api/client.ts wrappers, LockBadge, LockToggleButton, PronounCombo, FieldHistoryPanel, ReciprocalSuggestionPanel, BibleList, BibleEditor, App.tsx + AppShell.tsx (D-84, D-85, D-86, D-87, D-88) + human-verify checkpoint (BIBLE-08)

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

**Plans:** 5/6 plans executed

**Wave 1**

- [x] 09-01-PLAN.md — Wave 0: RED test stubs (10 files in tests/codec/ + tests/translate/ + tests/output/ + tests/discover/) + 16 ASS/SSA/VTT fixture files (FMT-02, FMT-03, FMT-04)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 09-02-PLAN.md — Wave 1: Shared foundation — SubDoc.envelope field (D-92), tc_to_ms extension for ASS centiseconds + VTT hourless (D-101), sentinel TAG_RE \\N/\\n/\\h arm (D-98) (FMT-02, FMT-03, FMT-04)

**Wave 3** *(blocked on Wave 2 completion — plans 09-03 and 09-04 run in parallel)*

- [x] 09-03-PLAN.md — Wave 2A: ASS/SSA codec — hand-rolled read_ass/write_ass with AssDoc/AssOpaqueSegment/AssDialogueSlot; karaoke + drawing verbatim pass-through; validate.py gate extension SENTINEL_ONLY_RE + raw-is-not-None guard (D-91, D-97, D-98, D-99, D-102) (FMT-02, FMT-03)
- [x] 09-04-PLAN.md — Wave 2B: VTT codec — hand-rolled read_vtt/write_vtt with VttDoc/VttOpaqueBlock/VttCueBlock; WEBVTT header, NOTE/STYLE/REGION verbatim, cue settings in timing_line (D-91, D-100) (FMT-04)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 09-05-PLAN.md — Wave 3: Pipeline wiring — dispatch.py (read_subtitle/write_subtitle, D-94), derive_vi_sidecar_path generalized to mirror source extension (D-95), engine.py + gap.py seam swap + envelope carry-through, AUTO-04 generalized for .vi.<ext> (D-96) (FMT-02, FMT-03, FMT-04)

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 09-06-PLAN.md — Wave 4: Human visual UAT — positioned sign rendering in mpv/Jellyfin for .vi.ass ({\pos}/{\an8}) and .vi.vtt (position:/line:) confirms FMT-04 success criterion 3 (FMT-02, FMT-03, FMT-04)

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

**Plans:** 4/4 plans complete

**Wave 0**

- [x] 10-01-PLAN.md — Wave 0: RED test scaffold — Bazarr client stubs, source_selection package, gap Case 1.5 / D-110, migration 0003, model override, PATCH overrides route, original_language capture (INTG-02, SRC-01, SRC-02, SVC-05)

**Wave 1** *(blocked on Wave 0 completion — plans 10-02 and 10-03 run in parallel)*

- [x] 10-02-PLAN.md — Wave 1A: BazarrClient + source_selection/rank.py + source_selection/resolve.py + original_language capture + ledger check_by_output_path + gap.py Case 1.5 + scan.py extensions (INTG-02, SRC-01, SRC-02)
- [x] 10-03-PLAN.md — Wave 1B: Migration 0003 + Series ORM override columns + DTOs + set_series_overrides store writer + PATCH /overrides route + LLMClient model-per-call + engine.py threading + cli.py/worker.py wiring (SVC-05)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 10-04-PLAN.md — Wave 2: BibleEditor Overrides tab (SourcePriorityEditor + model field + register sub-section) + client.ts wrappers + human-verify checkpoint (SVC-05)

**UI hint**: yes

---

## v1.1 Phase Details

### Phase 11: shadcn Foundation & Purple Theme

**Goal**: The shadcn/ui + jolly-ui component infrastructure is installed on the existing Tailwind v3 stack, the `@/` path alias is wired in both TypeScript and Vite configs, and a purple dark-mode CSS-variable theme replaces the legacy hex tokens — all verified with a green production build before any page content changes.
**Depends on**: Phase 10 (v1.0 complete)
**Requirements**: UI-01, UI-02
**Success Criteria** (what must be TRUE):
  1. Running `npm run build` after setup produces a green build with no TypeScript or Vite errors, and the built `trezarr/web/static/` is populated
  2. Opening the app in a browser shows the existing pages rendered on a dark purple background with the new CSS-variable theme (the `.dark` class on `<html>` is active)
  3. A shadcn `<Button variant="default">` renders with the purple primary color and correct opacity on `bg-primary/50` — confirming HSL channel-triple format is correct
  4. No existing page breaks or shows unstyled text; the bridge-period dual-token setup keeps legacy classes functional
**Plans**: TBD
**UI hint**: yes

### Phase 12: App Shell + Route Restructure

**Goal**: The current AppShell is replaced with a SidebarProvider + AppSidebar + Outlet layout, the route table is restructured with `/library` split into `/series` + `/movies` + `/series/:id` and `/` redirecting to `/series`, and all existing pages load correctly inside the new full-height sidebar shell.
**Depends on**: Phase 11
**Requirements**: NAV-01, NAV-02
**Success Criteria** (what must be TRUE):
  1. Navigating to `/` in the browser redirects to `/series`; refreshing `/series`, `/movies`, `/queue`, `/history`, `/bible`, or `/settings` loads the correct page (SPA deep-link fallback intact)
  2. The full-height sidebar is visible on all pages showing the Trezarr brand, all six nav items (Series / Movies / Queue / History / Bible / Settings), and a left 2-pixel purple accent bar on the active nav item
  3. All existing pages (Queue, History, Settings, Bible List, Bible Editor) remain navigable and fully functional inside the new shell with no regressions
  4. Stub Series, SeriesDetail, and Movies pages render a heading placeholder at their new routes without errors
**Plans**: TBD
**UI hint**: yes

### Phase 13: Backend Episodes Enrichment

**Goal**: The `GET /api/library/series/{id}/episodes` endpoint is rewritten to return season-grouped episode records from Sonarr with audio languages and Bazarr subtitle inventory (fail-soft HTTP 200 always), and the Series + Movies list endpoints expose `translated_count`/`total_count` per item.
**Depends on**: Phase 11 (for deployment context; backend work is parallel-eligible with Phase 12)
**Requirements**: API-01, API-02
**Success Criteria** (what must be TRUE):
  1. `GET /api/library/series/{id}/episodes` returns a JSON envelope with `seasons[]` (grouped by season number), each episode carrying `audio_languages`, `subtitles[]` (with `code2`, `hi`), `episode_key`, and `status`; the endpoint always returns HTTP 200 even when Bazarr is down (`bazarr_available: false` in the envelope)
  2. When Bazarr is unreachable, the endpoint returns all episode records with `subtitles: []` for each and `bazarr_available: false` — no 502, no empty page
  3. `GET /api/library` series and movies list items include `translated_count` and `total_count` fields
  4. Backend tests cover the Bazarr fail-soft path, the correct `episode.id` (not `episodeFile.id`) join to Bazarr inventory, and the `audioLanguages` full-name-to-ISO lookup
**Plans**: TBD

### Phase 14: New Library Pages + Nav Badge Wiring

**Goal**: The Series list, Series detail (season-grouped Accordion with audio and subtitle-language badges, translate actions, search/filter/sort), and Movies list pages are built and fully functional; the sidebar count and LIVE badges are wired to live API data; Library.tsx is deleted.
**Depends on**: Phase 12 (shell + stubs), Phase 13 (stable API contract)
**Requirements**: LIB-01, LIB-02, LIB-03, LIB-04, LIB-05, LIB-06, LIB-07, NAV-03
**Success Criteria** (what must be TRUE):
  1. The Series list page shows all Sonarr series in a dense table with a "X/Y translated" progress bar per series; clicking a series navigates to `/series/:id`
  2. The Series detail page shows episodes grouped by season in collapsible sections with the latest season auto-expanded; each episode row shows an Audio badge (blue) and subtitle-language badges (`CODE2` uppercase, amber = source / purple = VI, `VI:HI` when `hi=true`); when `bazarr_available=false` the subtitle badge column is suppressed rather than showing all-empty badges
  3. A "Translate" button on an episode row or season header enqueues the item and navigates to the Queue page; the button is absent for episodes with no file
  4. The Movies page shows all Radarr movies with source-subtitle status and a Translate button
  5. The Series and Movies lists support search by title, filter by subtitle status, and sort; the sidebar Series and Movies nav rows show a count badge of items needing a Vietnamese subtitle (auto-hidden at zero) and a LIVE badge when the backing *arr service is connected
**Plans**: TBD
**UI hint**: yes

### Phase 15: Reskin Existing Pages

**Goal**: Queue, History, Settings, Bible List, JobLogs, and Bible Editor are all reskinned in-place onto shadcn primitives; the legacy bridge tokens are removed from tailwind.config.js; the existing test suite remains green throughout.
**Depends on**: Phase 12 (new shell), Phase 14 (proves badge system on new code before touching high-risk BibleEditor)
**Requirements**: RSK-01, RSK-02
**Success Criteria** (what must be TRUE):
  1. Queue, History, Settings, Bible List, and JobLogs pages render on the new shadcn component system with no visible legacy hex colors; each page shows loading, empty, and error states correctly
  2. The Bible Editor renders identically to its pre-reskin behavior: all five tabs (Characters, Address Map, Term Dictionary, Register, Overrides) load, lock badges display provenance correctly, field history panels populate, and pronoun combos work — confirmed by the existing test suite (all tests green)
  3. After all pages are reskinned, a grep for `bg-[#` and `text-[#` in `src/` returns no results; legacy bridge tokens are removed from `tailwind.config.js`
**Plans**: TBD
**UI hint**: yes

### Phase 16: Docker Rebuild + Live Smoke Test

**Goal**: The multi-stage Docker image is rebuilt from scratch, the new dashboard is verified live on :6868 against the real *arr stack, and all six nav routes, episode badges, translate flow, Settings save, and SPA deep-link fallback are confirmed working in the production build.
**Depends on**: Phase 15 (all pages reskinned)
**Requirements**: RSK-03
**Success Criteria** (what must be TRUE):
  1. `docker build --no-cache` completes the full multi-stage build (node Vite build → python:3.12-slim) without error; the image starts on :6868 and `/api/health` returns 200
  2. Navigating to all six sidebar routes (/series, /movies, /queue, /history, /bible, /settings) in the browser at :6868 renders the new shadcn dashboard with no blank pages or missing styles
  3. The Series detail page for a real Sonarr series shows season-grouped episodes with audio and subtitle-language badges populated from Bazarr
  4. Triggering a translation from the Series detail view enqueues it and the Queue page shows the job; a hard-refresh on `/series/42` serves `index.html` (SPA deep-link fallback intact)
**Plans**: TBD

## Progress

**Execution Order:**
v1.0 phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10
v1.1 phases execute in numeric order: 11 → 12 → 13 (parallel-eligible with 12) → 14 → 15 → 16

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Codec & LLM Client Foundation | 3/3 | Complete | 2026-05-31 |
| 2. Mechanical Translation Core + Validation Gate | 3/3 | Complete | 2026-05-31 |
| 3. \*arr Integration + First Vertical Slice | 5/5 | Awaiting Verification | |
| 4. Series Bible Store & Schema | 4/4 | Complete | 2026-06-01 |
| 5. Three-Pass Pronoun Engine | 6/6 | Complete | 2026-06-01 |
| 6. Relationship Evolution + Self-Review | 3/3 | Complete | 2026-06-01 |
| 7. Web UI & Service Hardening | 6/6 | Complete | 2026-06-01 |
| 8. Editable Series Bible UI | 4/4 | Complete | 2026-06-02 |
| 9. Multi-Format — ASS/SSA + VTT | 5/6 | In Progress | |
| 10. Source Selection & Per-Series Overrides | 4/4 | Complete | 2026-06-02 |
| 11. shadcn Foundation & Purple Theme | 0/TBD | Not started | - |
| 12. App Shell + Route Restructure | 0/TBD | Not started | - |
| 13. Backend Episodes Enrichment | 0/TBD | Not started | - |
| 14. New Library Pages + Nav Badge Wiring | 0/TBD | Not started | - |
| 15. Reskin Existing Pages | 0/TBD | Not started | - |
| 16. Docker Rebuild + Live Smoke Test | 0/TBD | Not started | - |
