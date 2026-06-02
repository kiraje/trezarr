# Phase 10: Source Selection & Per-Series Overrides - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** `--auto` (all gray areas auto-resolved to the recommended default; every D-number below is a sensible default the researcher/planner may tune with rationale)

<domain>
## Phase Boundary

Phase 10 makes Trezarr's **source-language selection intelligent and per-series tunable**.
Today the pipeline picks a source subtitle by globbing the filesystem against a flat
`source_lang_priority` list (default `["en"]`, D-25). Phase 10 turns that crude leaf into
the relational-fidelity selector the moat was designed for, and adds the power-user override
valve for source/register/model. The three-pass engine, the Series Bible, the validation
gate, reconciliation, and the codec are **untouched** — this phase only changes the
**selection / ranking / override layer that feeds source bytes into the existing pipeline**.

Concretely, four capabilities, each mapped to a requirement:

1. **Bazarr inventory client (INTG-02).** A new `trezarr/arr/bazarr.py` reads which
   source-language subtitle files already exist for each item via Bazarr's API — so Trezarr
   knows the *available* source languages without scanning, and **never re-downloads** (it
   only reads inventory; downloading/acquisition is out of scope, owned by Bazarr). The
   Bazarr *connection* (host/port/api_key/enabled) + webhook already shipped in Phase 7
   (D-76); Phase 10 lights up the *inventory read*.

2. **Source-agnostic input (SRC-01).** Generalize selection so translation can run from
   **any** available source language, not just English. English becomes the universal
   fallback, not the only option.

3. **Relational-fidelity source ranking (SRC-02).** When multiple source subtitles exist,
   pick the one whose honorific/relational system best preserves what Vietnamese needs —
   prefer Chinese/Korean/Japanese/Thai for East-Asian content over English (which flattens
   every relationship to "I/you") — and **fall back gracefully** to whatever is available.

4. **Per-series overrides (SVC-05).** A power user can override **source-language
   preference, register, and model** per series, via the existing per-series UI surface
   (the Phase-8 Bible editor).

Requirements covered: **INTG-02, SRC-01, SRC-02, SVC-05.**

**In scope:**
- `trezarr/arr/bazarr.py` — an httpx-based Bazarr inventory client (typed `BazarrError`,
  `_normalize_arr_host` reuse) reading per-item existing source-sub languages + paths.
- A **source-selection layer** that ranks available sources by relational richness biased
  by the content's original language, with an explicit graceful-fallback chain.
- Capturing **`original_language`** into the `MediaItem` snapshot + `Series.arr_metadata`
  (the primary SRC-02 signal — NOT captured today).
- A **per-series override store** — nullable override columns on the `series` table
  (Alembic migration 0003) + a pure override-resolution function; register override reuses
  the Phase-8 lock mechanism.
- A **per-series Overrides UI** section in the existing Bible editor + its REST endpoint,
  behind the D-39 Pydantic-only boundary.
- New Phase-10 `TrezarrSettings` fields (default relational-richness priority, Bazarr
  inventory toggle) under a Phase-10 header (mirroring the D-50/D-60/D-76 grouping).

**Out of scope (deferred to owning phases / v2):**
- **Re-downloading / acquiring source subtitles** — Bazarr's job; explicitly out of scope
  (PROJECT.md Out of Scope). Trezarr only *reads* inventory (INTG-02).
- **ASS/SSA + VTT formats** → Phase 9 (FMT-02/03/04). Source selection operates on whatever
  format the chosen source sub is, via the Phase-9 dispatcher when present; it does not add
  format handling itself.
- **Multi-instance Sonarr/Radarr/Bazarr** (SCALE-01), **notifications / confidence-flagging**
  (OBS-01/02), **Bible/glossary import-export** (COMM-01) → v2.
- **Retroactive re-translation** of already-done episodes when an override changes →
  forward-only by default (consistent with the Phase 6/8 forward-only posture); a manual
  per-series "re-translate" is a deferred nicety, not a Phase-10 requirement.
- **Web UI auth** — unchanged single-user trusted-LAN posture (D-78).

</domain>

<decisions>
## Implementation Decisions

Continues the project decision ledger (Phase 1 D-01…D-11, Phase 2 D-12…D-20, Phase 3
D-21…D-30, Phase 4 D-31…D-39, Phase 5 D-40…D-50, Phase 6 D-51…D-60, Phase 7 D-61…D-78,
Phase 8 D-79…D-90, Phase 9 D-91…D-102). **Phase 10 = D-103…D-114.** All numbered values are
defaults the researcher/planner may tune; all are overridable in planning.

> **Carried forward (must not regress).** **D-25** source-language priority list (Phase 10
> generalizes it). **D-26** never clobber a foreign `.vi` sidecar; **D-27** content-hash
> idempotency on the *source* sub; **D-28** self-output exclusion via ledger provenance —
> all three must still hold when selection changes the chosen source. **D-22/D-23** pyarr
> discovery + `apply_path_mapping` (the Bazarr client mirrors the host/path-mapping
> conventions). **D-06** the single `LLMClient._semaphore` is the only global LLM
> concurrency cap — a per-series *model* override must NOT introduce a second client or a
> second cap. **D-39** SQLAlchemy stays inside `bible/`; routes use Pydantic DTOs only.
> **D-69/D-37** Alembic-migration-on-startup discipline (Phase 10 adds migration 0003).
> **D-79/BIBLE-08/09** the Phase-8 lock-aware edit + forward propagation (register override
> reuses this verbatim).

### Capability A — Bazarr inventory (INTG-02)

- **D-103: Build `trezarr/arr/bazarr.py` as an httpx client, not pyarr.** Phase 7 already
  established (in `web/routes/test_connection.py::test_bazarr`) that Bazarr is reached with
  raw httpx (`GET /api/system/status` + `X-Api-Key`) because pyarr's Bazarr coverage is
  thin. The inventory client reads Bazarr's per-item subtitle lists (existing
  source-language subs + their language codes + paths). Wrap transport/HTTP failures in a
  typed `BazarrError` (mirroring `arr.DiscoveryError`) so callers degrade gracefully, and
  route the host through `_normalize_arr_host` (host normalization + WR-01 log redaction).
  Resolve `bazarr_api_key` via `SecretStr.get_secret_value()` at the client boundary only
  (D-11 discipline). **Rejected:** adding a pyarr Bazarr dependency (coverage gap; httpx is
  already a dep and the established pattern).

- **D-104: Bazarr is the inventory/selection AUTHORITY; the filesystem is the byte source
  and the graceful fallback.** Bazarr answers "which source languages exist for this item";
  Trezarr then resolves the chosen language to a local, path-mapped file and reads the bytes
  off the **shared filesystem** as it does today. **When `bazarr_enabled=False` or Bazarr is
  unreachable, degrade to the existing `find_source_sub` filesystem glob** — Bazarr is never
  a hard dependency for translation (SRC-01 source-agnostic survives a Bazarr outage). This
  keeps the Phase-3 behavior intact as the floor and layers Bazarr intelligence on top.
  INTG-02's "never re-download" is satisfied structurally: Trezarr calls only Bazarr's
  *read* endpoints, never its download/search endpoints.

- **D-105: Reconcile Bazarr-reported paths via the existing `apply_path_mapping` (D-23).**
  Bazarr reports paths in its own container namespace; run them through the same
  container↔host path-mapping the *arr discovery layer uses. A Bazarr-reported sub that
  cannot be resolved or read falls back to the filesystem glob for that one item (per-item
  resilience, mirroring the per-service resilience of `DiscoveryError`).

### Capability B — Source-agnostic + relational-fidelity ranking (SRC-01, SRC-02)

- **D-106: Source-agnostic by default; English is the universal fallback, not the default
  source.** Generalize the selection layer so any available source language can feed the
  pipeline (SRC-01). The Phase-3 default `source_lang_priority=["en"]` (D-25) is superseded
  by a **relational-richness-ordered default** priority; `en` remains present as the
  last-resort universal fallback.

- **D-107: Rank available sources by a static relational-richness tier, biased by the
  content's original language (SRC-02).** Recommended shape (algorithm research-flagged):
  - **Tier 1 (relationally richest):** `zh`/`ko`/`ja`/`th` — honorific/speech-level/kinship
    systems that carry the relationship information Vietnamese needs.
  - **Tier 2:** other languages with grammatical relational/honorific marking.
  - **Tier 3 (flat-relational, universal fallback):** `en` and similar.
  Selection prefers the **content's `original_language`** when that language is relationally
  rich (a Korean drama's `ko` sub beats its `en` sub), but does NOT displace a native
  English source with a likely-fan-made foreign sub for genuinely English-original content.
  The precise weighting (how strongly original_language biases the tier order), the exact
  language→tier table, and tie-breaking are **Claude's discretion to the researcher** — this
  is the novel heuristic STATE.md flagged for research.

- **D-108: Capture `original_language` into the arr_metadata snapshot — the primary SRC-02
  signal (NOT captured today).** Sonarr's series payload and Radarr's movie payload both
  expose `originalLanguage`; add it to `arr.MediaItem` and persist it in
  `Series.arr_metadata` (it is absent from the current snapshot — confirmed in
  `arr/sonarr.py`). When `original_language` is unknown/absent, fall back to ranking purely
  over the available-source set (D-107 Tier order). Genre/country are secondary, optional
  signals (planner discretion); original language is the clean primary.

- **D-109: Explicit graceful-fallback chain (SRC-02 "fall back to whatever is available").**
  Per-item resolution order:
  1. **Per-series source override** (D-111), if set.
  2. **SRC-02 richness ranking** over the available sources (Bazarr inventory ∪ filesystem),
     biased by `original_language` (D-107).
  3. **Global `source_lang_priority`** (effective default, D-106).
  4. **First available source of any language** — never skip translation solely because the
     *ideal* source is missing (SRC-01).
  Only when **zero** source subs exist does the item stay "no source / skip" (existing
  `ScanStats.no_source` path).

- **D-110: Idempotency must survive a source-language change (preserve D-26/D-27/D-28).**
  The ledger keys on `source_sub_path` + `content_hash`; a different chosen source = a
  different path = a distinct ledger row. If a higher-priority (richer) source appears later
  (e.g. a `ko` sub arrives where `en` was used), re-selection picks it and re-translates
  from the richer source — but the **foreign-`.vi` never-clobber guard (D-26)** and
  **self-output exclusion (D-28)** must still hold for any `.vi` sidecar Trezarr itself
  wrote. The planner must decide + test the "preferred source appeared later" transition so
  it (a) does not loop, (b) does not clobber a foreign vi sidecar, and (c) updates/honors the
  ledger provenance for the new source path. This is the highest-regression-risk seam in the
  phase.

### Capability C — Per-series overrides (SVC-05)

- **D-111: Per-series overrides live on the `series` table (Alembic migration 0003).** Add
  nullable columns: `source_lang_override` (JSON ordered list | NULL) and `model_override`
  (str | NULL). **The register override REUSES the existing Phase-8 lock** on
  `Series.register` — a user-set + locked register *is* the override; BIBLE-08/09 already
  make it survive re-analysis and propagate forward, so no new field/mechanism is needed for
  register. NULL columns = inherit global config. Migration 0003 follows the D-69/D-37
  startup-migration discipline (reversible, `run_migrations_to_head`). **Rejected:** a
  separate `series_override` table (the per-series `series` row is already the natural home;
  a join adds nothing) and a `config.yaml` series map (loses referential integrity, races
  the config writer — the exact reasons the Bible is SQLite, not flat files).

- **D-112: Override resolution is a single pure function**
  `resolve_effective_settings(series, settings) -> (source_priority, register, model)`. The
  worker/engine consult it per item; global config is the default, per-series columns win
  when non-NULL. Keeping it pure makes it unit-testable in isolation (mirrors the
  `reconcile_attributions` precedence-function precedent).

- **D-113: A model override flows per-CALL, not per-client — D-06 preserved.** The single
  global `LLMClient` and its one `asyncio.Semaphore` (D-06) stay the only LLM concurrency
  cap; Phase 10 does **not** build a per-series client or a second semaphore (Pitfall 1
  preserved). The engine threads the effective `model` into each LLM request (the OpenAI SDK
  accepts `model` per call), defaulting to `settings.llm_model`. The planner picks the exact
  threading (e.g. an optional `model` param on the batch-translate callables).

### Capability D — Per-series override UI (SVC-05, UI hint: yes)

- **D-114: Extend the Phase-8 per-series Bible editor with an "Overrides" section** (source-
  language preference list, register, model), served by the existing
  `/api/bible/series/{id}/...` router behind the D-39 Pydantic-only boundary. Register
  editing already lives there (`PATCH /series/{id}/register`, lock-aware); add a
  `PATCH /series/{id}/overrides` for source-priority + model. Reuse Phase-8 SPA assets
  (`api/client.ts` wrappers, `Toast`, `LockBadge`/`LockToggleButton` for the register lock).
  Show provenance (global default vs per-series override) so the operator sees what is
  inherited vs overridden. **Rejected:** a separate top-level per-series settings page — the
  Bible editor (`BibleList` → `BibleEditor`) is already *the* per-series surface.

### Claude's Discretion
Delegated to researcher/planner:
- The exact Bazarr API endpoints + response shapes for inventory (episodes/movies subtitle
  lists), and whether to fetch per-item or bulk-and-index; Bazarr API version/auth specifics.
- The precise **SRC-02 ranking algorithm**, the language→relational-richness table, and how
  strongly `original_language` biases the tier order (the research-flagged novel heuristic).
- Whether source selection extends `scan_for_eligible_items`'s signature or becomes a new
  `select_source` step ahead of it; how the chosen `source_lang` + override provenance are
  carried into `EligibleItem`/`job` rows for History/logs.
- Exact override column names/types, the overrides DTO/route shape, and how much to validate
  `model_override` against the configured endpoint.
- Whether secondary signals (genre/country) augment `original_language` for SRC-02.
- Default numeric/string values for the new Phase-10 settings.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/ROADMAP.md` §"Phase 10: Source Selection & Per-Series Overrides" — goal + 4
  success criteria (Bazarr inventory read / never re-download; source-agnostic;
  relationally-richest selection with fallback; per-series source/register/model overrides)
- `.planning/REQUIREMENTS.md` §Integration **INTG-02** (read Bazarr inventory), §Source
  Selection **SRC-01** (source-agnostic) + **SRC-02** (relational-fidelity ranking),
  §Service & Web UI **SVC-05** (per-series overrides); and the invariants this phase must not
  break — **AUTO-03** (idempotency / source-sub hash), **AUTO-04** (no self-reprocessing),
  **INTG-03** (path mapping)
- `.planning/PROJECT.md` §Context (the key linguistic insight driving source selection:
  zh/ko/ja/th carry relational info English discards), §Requirements ›"Smart attribution &
  source selection", §Out of Scope ("Replacing Bazarr's subtitle downloading" — Phase 10
  reads, never acquires), §Key Decisions ("Source-agnostic input, prioritized by relational
  fidelity" — Pending, this phase closes it)

### Project-wide grounding (the prescriptions for THIS phase)
- `CLAUDE.md` §"*arr Integration — Prescribed Approach" — Bazarr exposes `/api/*`; X-Api-Key
  auth; "query Bazarr for existing subtitle state per item … identifies 'has source sub,
  lacks good Vietnamese sub'" (the INTG-02 prescription); §"Series Bible Persistence" (the
  `series` row is the per-series home for overrides); §"Stack Patterns by Variant" (source
  selection by relational fidelity)

### Prior-phase foundations this phase consumes & extends
- `.planning/phases/03-arr-integration-first-vertical-slice/03-CONTEXT.md` — **D-22/D-23**
  pyarr discovery + `apply_path_mapping` (Bazarr client mirrors these), **D-25**
  source-language priority (generalized here), **D-26/D-27/D-28** never-clobber-foreign-vi /
  source-hash idempotency / self-output exclusion (must not regress under new selection)
- `.planning/phases/04-series-bible-store-schema/04-CONTEXT.md` — **D-31..D-35** the `series`
  schema + `arr_metadata` JSON snapshot + the Alembic baseline (`original_language` is added
  to the snapshot; migration 0003 sits on this baseline), **D-39** Pydantic-only store
  boundary
- `.planning/phases/07-web-ui-service-hardening/07-CONTEXT.md` — **D-69/D-37** Alembic
  migration-on-startup discipline (0003 follows it), **D-71** the httpx Bazarr connection
  test (the client pattern to mirror), **D-76** Bazarr connection fields (already in config),
  **D-77** staged-rollout toggles, **D-06/D-68** the single LLM semaphore (D-113 preserves it)
- `.planning/phases/08-editable-series-bible-ui/08-CONTEXT.md` — the lock-aware edit + the
  `/api/bible/series/{id}/...` router + the React `BibleEditor`/`BibleList` (register override
  reuses the lock; the Overrides UI extends this editor); **D-39** boundary contract-tested

### Existing code to reuse / extend (the integration seams — read before planning)
- `trezarr/arr/__init__.py` — `_normalize_arr_host` + `DiscoveryError` (template for
  `BazarrError`); `trezarr/arr/sonarr.py` / `radarr.py` — the client + `MediaItem` snapshot
  pattern; **add `original_language` to `MediaItem` and the Sonarr/Radarr capture** (D-108)
- `trezarr/web/routes/test_connection.py` — `test_bazarr` (the httpx + X-Api-Key Bazarr call
  shape to build the inventory client from — D-103)
- `trezarr/discover/scan.py` — `find_source_sub(media_path, lang_priority)` +
  `scan_for_eligible_items` + `EligibleItem(source_lang)` (the selection layer to generalize;
  filesystem glob is the D-104 fallback); `trezarr/discover/gap.py` — `is_eligible`
  (D-26/27/28 guards selection must preserve — D-110)
- `trezarr/config.py` — `source_lang_priority` (D-25; generalize) + the Bazarr connection
  fields (D-76); add the Phase-10 settings group
- `trezarr/bible/models.py` — `Series` (add `source_lang_override`/`model_override` columns —
  D-111; `register` already present + lockable); `trezarr/bible/dto.py` — the SeriesDTO/
  SeriesBibleDTO boundary the overrides flow through; `trezarr/bible/store.py` — the
  lock-aware writers (register override) + where override read/write lands
- `trezarr/web/routes/bible.py` — the per-series router (`PATCH /series/{id}/register`
  exists; add `PATCH /series/{id}/overrides` — D-114)
- `trezarr/db/migration_runner.py` + `alembic/versions/0002_job_queue.py` — the migration
  authoring template for **0003** (per-series override columns — D-111)
- `trezarr/llm/client.py` — `self._model = settings.llm_model` (single global client; D-113
  threads `model` per-call rather than rebinding); `trezarr/translate/engine.py` —
  `build_translate_prompt` reads `register` (register override flows here) + the batch
  callables (model threading)
- `trezarr/web/worker.py` + `trezarr/web/scheduler.py` + `trezarr/cli.py` — the callers that
  pass `settings.source_lang_priority` into scan (route the resolved effective settings here
  — D-112)
- `frontend/src/pages/BibleEditor.tsx` / `BibleList.tsx` / `Settings.tsx` +
  `frontend/src/api/client.ts` — the SPA surfaces the Overrides section extends (D-114)

### External references
- Bazarr API — https://github.com/morpheus65535/bazarr (reference product; `/api/*`
  subtitle-inventory endpoints + X-Api-Key auth; the integration posture Trezarr mirrors)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`arr/__init__.py` `_normalize_arr_host` + `DiscoveryError`** — host normalization +
  WR-01 log redaction + the typed-error/per-service-resilience pattern; `BazarrError`
  mirrors `DiscoveryError` (D-103).
- **`web/routes/test_connection.py::test_bazarr`** — the working httpx + `X-Api-Key` +
  `GET /api/system/status` Bazarr call already exists; the inventory client is built from
  this exact shape (D-103), and the connection test can share the new client.
- **`discover/scan.py` `find_source_sub` + `EligibleItem` + `ScanStats`** — the selection
  layer to generalize; the filesystem glob becomes the D-104 fallback and the byte source;
  `EligibleItem.source_lang` already carries the chosen language downstream to the ledger.
- **`Series` table + `arr_metadata` JSON + `register` + `locked_fields`** — the per-series
  persistence already exists; overrides are nullable columns on it (D-111) and the register
  override reuses the existing lock; `arr_metadata` is where `original_language` is persisted.
- **`apply_path_mapping` (D-23)** — reused verbatim to reconcile Bazarr-reported paths to
  Trezarr's local filesystem (D-105).
- **Alembic baseline + 0002 + `run_migrations_to_head`** — the migration discipline for
  0003 (D-111).
- **Phase-8 `/api/bible/series/{id}/...` router + `BibleEditor` SPA** — the per-series UI +
  REST surface the Overrides section extends (D-114).

### Established Patterns
- **"API for knowledge, filesystem for action" (D-22)** — Bazarr inventory is *knowledge*
  (what languages exist); the filesystem is still where bytes are read and the `.vi` sidecar
  is written. D-104 keeps that split.
- **Per-service / per-item resilience** — one *arr down must not abort the run
  (`DiscoveryError` caught per service); Bazarr down → degrade to filesystem glob (D-104),
  one unresolved Bazarr path → filesystem fallback for that item (D-105).
- **Single `LLMClient._semaphore` (D-06, Pitfall 1)** — preserved; a per-series model
  override is a per-call `model` arg, never a second client/semaphore (D-113).
- **Pydantic-only store boundary (D-39)** — the overrides route imports no SQLAlchemy;
  it goes through DTOs/store writers (D-114).
- **Forward-only propagation (Phase 6/8)** — an override applies forward by default; no
  retroactive re-translation of done episodes unless explicitly requested.

### Integration Points (each a regression risk)
1. **`arr/sonarr.py` + `radarr.py` MediaItem capture** — add `original_language` (D-108);
   the `Series.arr_metadata` snapshot must persist it.
2. **`discover/scan.py` selection** — generalize from `["en"]` glob to the D-109 fallback
   chain (Bazarr inventory ∪ filesystem, richness-ranked, override-aware). The
   `find_source_sub`/`scan_for_eligible_items` signatures + `EligibleItem` may grow.
3. **`discover/gap.py` D-26/27/28 guards** — must keep holding when the chosen source
   language changes (D-110) — the "preferred source appeared later" case.
4. **`bible/models.py` + Alembic 0003** — new nullable override columns on `series` (D-111).
5. **`translate/engine.py` + `llm/client.py`** — thread the effective `register` (already
   read in `build_translate_prompt`) + per-call `model` (D-113) from `resolve_effective_settings`.
6. **`web/worker.py` / `scheduler.py` / `cli.py`** — route the resolved effective settings
   (not raw global config) into scan + translate (D-112).
7. **`web/routes/bible.py` + `frontend` BibleEditor** — the Overrides endpoint + UI (D-114).

</code_context>

<specifics>
## Specific Ideas

- **This is the phase the whole "source selection" thesis pays off.** PROJECT.md's core
  linguistic insight — zh/ko/ja/th carry the relational/honorific information English
  discards — only becomes real here. The selection heuristic is the deliverable; a Bazarr
  client with a flat `["en"]` priority would miss the point.
- **Bazarr is knowledge, not a hard dependency.** A Bazarr outage (or `bazarr_enabled=False`)
  must degrade cleanly to today's filesystem behavior (D-104). The product still works
  source-agnostically without Bazarr; Bazarr just makes selection smarter and avoids
  re-download confusion.
- **Don't displace a native English source with a fan foreign sub.** SRC-02's richness
  ranking must be *original-language-aware* (D-107): prefer `ko` for a Korean drama, but
  don't prefer a likely-low-quality `zh` fansub over the native `en` for a US show. This
  nuance is why `original_language` (D-108) is captured, not just "rank by a fixed table."
- **Register override = the Phase-8 lock, not a new field.** The cleanest SVC-05 register
  override is "set + lock `Series.register`" — it already survives re-analysis and propagates
  forward (BIBLE-08/09). Only source-priority and model need new columns (D-111).
- **Live-Bazarr + UI items will need human UAT.** Success criteria 1 (live Bazarr inventory
  read) and 4 (per-series override visibly changing a translation) are best confirmed against
  a real Bazarr instance + a browser walkthrough — flag these for `10-HUMAN-UAT.md`, in
  keeping with the project's hold-at-human-gate pattern.

</specifics>

<deferred>
## Deferred Ideas

- **Style-based sign/OP/ED skipping as a per-series toggle** — carried from Phase 9's
  deferred list; it aligns naturally with per-series overrides but is not an SRC/SVC-05
  requirement. Revisit once real output shows signs being unhelpfully translated.
- **Manual per-series "re-translate all episodes" action** — when an override changes,
  Phase 10 applies it forward only; a button to retroactively re-translate prior episodes is
  a UI nicety for later (not required by SVC-05).
- **Per-series enable/disable of Trezarr, per-series concurrency, per-series glossary
  import** — broader per-series control surface; COMM-01 (Bible/glossary import-export) is
  v2.
- **Auto-detecting `original_language` from dialogue** when *arr/TMDB lacks it — a fallback
  inference; for v1, unknown original-language just ranks over the available-source set
  (D-108).
- **Multi-instance Sonarr/Radarr/Bazarr** (SCALE-01) and **notifications / confidence-flagging**
  (OBS-01/02) → v2.

None of these block Phase 10. Discussion stayed within phase scope.

</deferred>

---

*Phase: 10-source-selection-per-series-overrides*
*Context gathered: 2026-06-02*
