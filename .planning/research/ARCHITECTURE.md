# Architecture Research

**Domain:** Self-hosted, Dockerized media-companion service (subtitle translation) for the Sonarr/Radarr/Bazarr "arr" stack
**Researched:** 2026-05-31
**Confidence:** MEDIUM-HIGH (Bazarr integration model HIGH from official sources; LLM pipeline internals MEDIUM — pattern is well-attested but Trezarr's specific Series-Bible design is novel and unvalidated)

## Standard Architecture

Trezarr is a long-running service that sits one level "above" Bazarr in the same way Bazarr
sits above Sonarr/Radarr: it learns the library through **APIs**, acts on files through a
**shared filesystem**, and delivers value as **sidecar files** that downstream consumers
(Plex/Jellyfin/Emby) auto-detect. The internal heart is an **async job pipeline** that turns
"a media item with a source sub but no good VI sub" into "a finalized `.vi.srt/.ass`",
mediated by a per-series **Series Bible** that carries consistency state across episodes.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL SYSTEMS                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │  Sonarr  │  │  Radarr  │  │  Bazarr  │  │   TMDB   │  │ User's LLM  │  │
│  │   API    │  │   API    │  │   API    │  │  (meta)  │  │  endpoint   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘  │
└───────┼─────────────┼─────────────┼─────────────┼───────────────┼─────────┘
        │  (HTTP API + webhooks)    │             │   (OpenAI SDK) │
┌───────┼─────────────┼─────────────┼─────────────┼───────────────┼─────────┐
│       ▼             ▼             ▼             ▼               ▼          │
│  ┌──────────────────────────────────────────┐  ┌──────────────────────┐  │
│  │      INTEGRATION / DISCOVERY LAYER         │  │   LLM CLIENT          │  │
│  │  *arr clients · Bazarr client · TMDB       │  │  (retries, rate-limit,│  │
│  │  metadata · webhook receiver · poller      │  │   JSON-mode, model    │  │
│  └────────────────────┬───────────────────────┘  │   config)             │  │
│                       │                            └──────────┬───────────┘ │
│                       ▼                                       │             │
│  ┌──────────────────────────────────────────┐                │             │
│  │   DISCOVERY + IDEMPOTENCY ENGINE           │                │             │
│  │  "needs-VI?" decision · source selection   │                │             │
│  │  (relational-fidelity ranking) · dedupe    │                │             │
│  └────────────────────┬───────────────────────┘                │             │
│                       │ enqueue translate-job                   │             │
│                       ▼                                          ▼             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                  JOB QUEUE + WORKERS (async, idempotent)               │  │
│  │   ┌────────────────── TRANSLATION PIPELINE (per media item) ───────┐  │  │
│  │   │ Pass 1 Analyze → Pass 2 Translate → Pass 3 Self-review →        │  │  │
│  │   │ Format/Timing validate → Write sidecar                          │  │  │
│  │   └──────────┬─────────────────────────────────────┬───────────────┘  │  │
│  └──────────────┼─────────────────────────────────────┼──────────────────┘  │
│                 │ read/write per-series state          │ parse/serialize     │
│                 ▼                                       ▼                     │
│  ┌────────────────────────┐              ┌────────────────────────────────┐ │
│  │   SERIES BIBLE STORE     │              │  SUBTITLE CODEC                 │ │
│  │  characters · address-map│              │  pysubs2-based parse/serialize  │ │
│  │  term dict · register ·  │              │  SRT / ASS-SSA / VTT,           │ │
│  │  relationship timeline · │              │  style-preserving               │ │
│  │  versions (editable)     │              └────────────────────────────────┘ │
│  └────────────────────────┘                                                  │
│                 ▲                                                             │
│  ┌──────────────┴───────────────────────────────────────────────────────┐  │
│  │              WEB UI + INTERNAL API (FastAPI + SPA)                     │  │
│  │  config · library/job dashboard · Series Bible editor · history       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────────┤
│   PERSISTENCE: SQLite (jobs, history, config, Series Bible) +              │
│   SHARED FILESYSTEM (read source subs / write VI sidecars, path-mapped)    │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility (what it owns) | Typical Implementation |
|-----------|-------------------------------|------------------------|
| **Integration/Discovery layer** | Talk to Sonarr/Radarr/Bazarr/TMDB APIs; receive *arr webhooks; poll as fallback; build a normalized model of "media item + its subtitle files + metadata" | Thin async HTTP clients (httpx) per service; a webhook endpoint on the FastAPI app; an APScheduler poll job |
| **Discovery + idempotency engine** | Decide if an item *needs* a VI sub; rank available source subs by relational fidelity; skip items already done (hash/marker check) | Pure-Python decision functions over the normalized model; reads history table |
| **Subtitle codec** | Parse SRT/ASS/VTT into a uniform internal line model; serialize back preserving ASS styling/positioning; line-count integrity | `pysubs2` (single lib spans all three formats, SSA-native so styling survives) |
| **Translation pipeline** | The 3-pass + validate flow per media item; orchestrates Bible reads/writes and LLM calls | A worker task = a deterministic state machine over pipeline stages |
| **LLM client** | One choke-point for the user's OpenAI-compatible endpoint: retries, backoff, JSON/structured output, model/base-URL config | `openai` Python SDK pointed at user base_url |
| **Series Bible store** | Persist/version per-series consistency state; expose read (inject into prompts) + write (merge pass-1 output) + user-edit (lock fields) | SQLite tables (or JSON column) with a versioned, append-on-episode model |
| **Job queue + workers** | Durable, concurrent, idempotent execution of translation jobs; retries, backpressure, one-series-at-a-time serialization | Redis-less option first (SQLite-backed) or RQ/Huey if Redis is acceptable |
| **Web UI + internal API** | Config, library/job dashboard, history, and the **Series Bible editor** (the only human touchpoint) | FastAPI backend + a small SPA (mirrors Bazarr's Python+TS split) |

## Recommended Project Structure

```
trezarr/
├── app/
│   ├── main.py                 # FastAPI app factory, lifespan (start scheduler/workers)
│   ├── config.py               # settings (endpoints, keys, path mappings, model)
│   ├── api/                    # internal HTTP API for the SPA
│   │   ├── routes_library.py   #   media/job dashboard
│   │   ├── routes_bible.py     #   Series Bible read/edit/lock
│   │   ├── routes_config.py    #   settings + connection tests
│   │   └── routes_webhook.py   #   receives Sonarr/Radarr/Bazarr webhooks
│   ├── integrations/           # OUTBOUND clients to external systems
│   │   ├── sonarr.py
│   │   ├── radarr.py
│   │   ├── bazarr.py
│   │   ├── tmdb.py
│   │   └── llm.py              #   OpenAI-SDK-compatible wrapper (retries, JSON mode)
│   ├── discovery/              # "what needs translating + which source to use"
│   │   ├── scanner.py          #   normalize library, find candidates
│   │   ├── source_selection.py #   relational-fidelity ranking
│   │   └── idempotency.py      #   existing-good-VI detection, dedupe markers
│   ├── subtitles/              # the codec — format in/out, line model
│   │   ├── model.py            #   internal SubLine / SubDoc dataclasses
│   │   ├── parse.py            #   pysubs2 load (srt/ass/vtt)
│   │   ├── serialize.py        #   pysubs2 save, style preservation
│   │   └── validate.py         #   line-count, timing, tag-integrity checks
│   ├── pipeline/               # the 3-pass translation flow
│   │   ├── orchestrator.py     #   stage state machine (resumable, idempotent)
│   │   ├── pass1_analyze.py    #   full file + metadata -> Bible update
│   │   ├── pass2_translate.py  #   windowed per-line translate + Bible inject
│   │   ├── pass3_review.py     #   LLM self-critique/repair
│   │   ├── chunking.py         #   token-budgeted batching with overlap
│   │   └── prompts/            #   prompt templates per pass
│   ├── bible/                  # Series Bible domain
│   │   ├── models.py           #   Character, AddressPair, Term, Register, RelationshipEvent
│   │   ├── store.py            #   persist / version / carry-forward
│   │   └── merge.py            #   merge pass-1 deltas, respect user locks
│   ├── jobs/                   # queue + worker glue
│   │   ├── queue.py            #   enqueue/claim, per-series serialization
│   │   ├── worker.py           #   pulls jobs, runs orchestrator
│   │   └── scheduler.py        #   APScheduler poll + retry sweeps
│   └── db/                     # SQLite models + migrations
│       ├── models.py
│       └── migrations/
├── frontend/                   # SPA (mirror Bazarr: separate build, served by app)
├── tests/
├── Dockerfile
└── docker-compose.example.yml  # alongside *arr stack, shared media volume
```

### Structure Rationale

- **`integrations/` is the only place that knows external wire formats.** Everything inside the app works on a normalized model, so the *arr/Bazarr/TMDB APIs (and the LLM endpoint) can change without rippling into the pipeline. This mirrors how Bazarr isolates Sonarr/Radarr clients.
- **`subtitles/` (codec) is separate from `pipeline/` (semantics).** Format parsing/serialization is mechanical and heavily testable; translation is the messy LLM part. Keeping them apart means format support (ASS styling, VTT) is provable without an LLM in the loop.
- **`bible/` is its own domain, not a pipeline sub-folder**, because it is read *and* written by the pipeline, edited by the UI, and persisted/versioned independently. It is the consistency core — it deserves a hard boundary.
- **`pipeline/orchestrator.py` owns sequencing only**; each pass is a pure-ish function (inputs → LLM → structured output). This makes passes individually testable and the flow resumable.

## Architectural Patterns

### Pattern 1: Companion-service integration (API for knowledge, filesystem for action)

**What:** Discover the library through service **APIs** (never scan disk to *find* media), but read source subs and write VI sidecars through a **shared filesystem volume**. Trigger on *arr/Bazarr **webhooks** ("On Import"/"On Download") with a periodic **poll** as a safety net.
**When to use:** Always — this is the defining pattern and the explicit "mirror Bazarr" requirement.
**Trade-offs:** Requires path-mapping config (the host paths *arr/Bazarr see may differ from Trezarr's mount) — this is the #1 setup friction in the whole arr ecosystem and must be a first-class config concern. Webhooks give low latency; polling gives reliability when a webhook is missed.

**Example:**
```python
# integrations/sonarr.py
async def list_episodes_with_files(client) -> list[MediaItem]:
    # Sonarr is the source of truth for "what exists" — Trezarr never globs the disk to discover.
    series = await client.get("/api/v3/series")
    ...  # normalize to MediaItem(path, ids, lang_subs=[...], metadata_ref=tmdb_id)

# routes_webhook.py  (Sonarr "On Import" -> instant candidate check)
@router.post("/webhook/sonarr")
async def on_sonarr_event(evt: SonarrWebhook):
    if evt.eventType in ("Download", "Upgrade"):
        enqueue_scan(series_id=evt.series.id, episode_ids=[e.id for e in evt.episodes])
```

### Pattern 2: Per-series stateful pipeline with the Series Bible as carried-forward context

**What:** The Bible is loaded at the *start* of each episode's job (carrying forward the latest version), injected into Pass 2/3 prompts, and updated by Pass 1. Episodes of one series must process **in order** so relationship evolution is causal (episode N sees the state left by N-1).
**When to use:** All series content. (Movies are the degenerate single-item case — a one-shot Bible.)
**Trade-offs:** Forces **per-series serialization** inside an otherwise parallel queue. Cross-series parallelism is free; intra-series is sequential. This is a deliberate correctness-over-throughput choice and matches the non-negotiable consistency bar.

**Example:**
```python
# pipeline/orchestrator.py
def run(job: TranslateJob):
    bible = bible_store.load_latest(job.series_id)        # carry forward
    src   = codec.parse(select_source(job))               # relational-fidelity pick
    bible = pass1_analyze(src, job.metadata, bible)        # build/update (respect locks)
    draft = pass2_translate(src, bible, window=2)          # windowed per-line + inject
    final = pass3_review(draft, bible)                     # self-critique
    codec.validate(final, against=src)                    # line-count/timing/tag check
    codec.write_sidecar(final, lang="vi", path=job.media_path)
    bible_store.commit(job.series_id, bible, episode=job.episode_marker)
```

### Pattern 3: Token-budgeted chunking with full-file consistency anchor

**What:** Pass 1 sees the *whole* file once (it only needs to extract entities/relationships/terms/register, which fits even long files as a compact summary task, or is itself chunked with running-summary accumulation). Pass 2 translates in **overlapping windows** (e.g. batches of N lines + a few lines of look-back/look-ahead context) so each line has local dialogue context, while the **Bible provides the global consistency anchor** that chunking would otherwise destroy.
**When to use:** Any file that, with prompt overhead, approaches the model's context budget.
**Trade-offs:** Overlap costs tokens (re-sending boundary lines) but prevents the well-documented failure where line-by-line gives zero context and whole-file gives hallucination/positional drift. The Bible is what lets you chunk *without* losing series-wide consistency — chunk boundaries can't break a glossary that lives outside the chunk.

**Example:**
```python
# pipeline/chunking.py
def windows(lines, batch=40, overlap=4, token_budget=...):
    # yield (context_before, batch_to_translate, context_after)
    # batch sized to stay under token_budget once Bible + prompt are added
    ...
```

### Pattern 4: Idempotent, resumable jobs

**What:** Before doing work, check whether a good VI sub already exists (sidecar present + a Trezarr provenance marker, e.g. a stored content hash or a comment/userdata tag in the file). Each pipeline stage records progress so a crashed/restarted worker resumes rather than re-spending LLM calls.
**When to use:** Always — re-translation is expensive and the service is long-running/restart-prone in Docker.
**Trade-offs:** Need a provenance signal that survives a bare filesystem (a sidecar Plex sees but Trezarr also recognizes). Store the source-sub hash so a *changed* source legitimately re-triggers.

## Data Flow

### Discovery → Enqueue Flow

```
Sonarr/Radarr "On Import" webhook  ──┐
                                      ├──▶  Discovery engine
APScheduler periodic poll  ──────────┘        │
                                              ▼
                            normalize via *arr/Bazarr APIs (+ TMDB metadata)
                                              │
                                              ▼
                            idempotency check: good VI sub already? ──yes──▶ skip
                                              │ no
                                              ▼
                            source selection: rank available subs by
                            relational fidelity (zh/ko/ja/th > en)  ──▶  enqueue TranslateJob
```

### Translation Pipeline Flow (per media item)

```
TranslateJob
   │
   ▼  load carried-forward Series Bible (series, latest version)
   ▼  parse selected source subtitle  (pysubs2 → internal SubDoc)
   │
   ├─▶ PASS 1  ANALYZE
   │     full file + media metadata (plot/cast/genre/register)
   │     → extract/UPDATE: characters, directed address-map,
   │       term dictionary, register, relationship events
   │     → merge into Bible (respect user-locked fields)
   │
   ├─▶ PASS 2  TRANSLATE  (windowed)
   │     for each window: source lines + surrounding-line context
   │     + Bible injection + inferred speaker/addressee
   │     → Vietnamese lines with correct pronoun pair
   │
   ├─▶ PASS 3  SELF-REVIEW
   │     model critiques its own output vs Bible
   │     (pronoun consistency, term consistency, register) → repairs
   │
   ├─▶ VALIDATE  (no LLM)
   │     line count == source, timings preserved, ASS tags/styles intact
   │
   ├─▶ WRITE SIDECAR  Show.S01E01.vi.srt|.ass  next to media (path-mapped)
   │
   └─▶ COMMIT Bible version + episode marker + history record
```

### State Management

```
Series Bible (SQLite, versioned)
   ▲ write (Pass 1 merge, episode commit)        ▲ edit + lock (UI)
   │                                              │
Pipeline workers ──read (inject into prompts)──   Web UI / Bible editor
   │
History/Jobs tables ──read (idempotency)──▶ Discovery engine
```

### Key Data Flows

1. **Knowledge in / files out:** library knowledge always arrives via API; the only filesystem writes are VI sidecars (plus reading source subs). Never the reverse.
2. **Bible carry-forward:** the Bible is the only state that crosses episode boundaries; everything else (a job, a parsed file) is per-item and disposable.
3. **User-override propagation:** a user edit in the UI sets a *lock* on a Bible field; subsequent Pass-1 merges must not overwrite locked fields, and Pass 2/3 inject the locked value — corrections propagate forward automatically.

## Series Bible Data Model

The Bible is the architectural center of gravity. Suggested shape (persist as SQLite tables, or a versioned JSON document per series — start with tables for queryability and per-field locking):

| Entity | Fields | Notes |
|--------|--------|-------|
| **Character** | name (original Latin form, never translated), gender, rough age, role/title | Stable identity used by the address-map |
| **AddressPair** (directed) | speaker→addressee, self_term, address_term (e.g. `John→Mary: self=anh, address=em`) | Directed and asymmetric; the pronoun engine. May be conditioned on the *current* relationship state |
| **Term** | source_term → fixed VI rendering, type (place/title/jargon) | Locks proper nouns and domain/fantasy/sci-fi terms across the series |
| **Register** | tone (formal-historical … casual-sitcom), grounded by metadata | Global default; can be scene-modulated |
| **RelationshipEvent** | character_pair, from_state → to_state, **episode_marker** | The evolution timeline (enemies→lovers). The active AddressPair at episode N is derived from events up to N |
| **Version / lock metadata** | version no., per-field `locked_by_user` flag, episode each fact was last touched | Enables carry-forward, audit, and the human-override valve |

**Persistence & versioning:** one logical Bible per series, versioned by episode commit. Reads always fetch the latest-as-of-episode-N; writes append a new version with the merged deltas. Locked fields are immutable to the merge step. User-editable via the UI (`routes_bible.py`), which is the single human touchpoint in v1.

## Scaling Considerations

This is a single-household self-hosted service; "scale" means library size and LLM throughput, not concurrent users.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Small (a few hundred episodes, incremental) | SQLite + in-process APScheduler + a small worker pool is entirely sufficient. No Redis. |
| Large backfill (thousands of episodes at once) | Bottleneck is the user's LLM endpoint, not Trezarr. Add concurrency *across series* (parallel) while keeping *within series* serial; add rate-limit/backoff in the LLM client; persist job state so a multi-day backfill survives restarts. |
| Many series in parallel | If SQLite write contention or a single-process worker becomes limiting, graduate the queue to RQ/Huey on Redis (still optional, still self-host-friendly). |

### Scaling Priorities

1. **First bottleneck:** the LLM endpoint (latency + rate limits). Fix with cross-series concurrency, batching within Pass 2 windows, and robust retry/backoff — *not* by parallelizing within a series (that breaks consistency).
2. **Second bottleneck:** SQLite under heavy concurrent writes during a big backfill. Fix with WAL mode and serialized writers before reaching for a separate DB/broker.

## Anti-Patterns

### Anti-Pattern 1: Scanning the disk to discover media

**What people do:** Glob the media volume to find files to translate.
**Why it's wrong:** Duplicates the *arr stack's job, mishandles renames/path-mapping, and diverges from the source of truth. Bazarr explicitly does *not* do this.
**Do this instead:** Discover via Sonarr/Radarr (and Bazarr) APIs + webhooks; touch the filesystem only to read the chosen source sub and write the VI sidecar.

### Anti-Pattern 2: Translating line-by-line with no context (or the whole file in one prompt)

**What people do:** Send each subtitle line to the LLM independently, or paste the entire file into one prompt.
**Why it's wrong:** Per-line loses all context (the LLM can't choose a Vietnamese pronoun without knowing who's speaking to whom); whole-file causes hallucination and positional/line-count drift in long files.
**Do this instead:** Windowed batches with overlap (local context) anchored by the Series Bible (global consistency), and a no-LLM validation step that enforces line-count/timing integrity.

### Anti-Pattern 3: A stateless or per-episode-only glossary

**What people do:** Build a glossary fresh per file (or hold it only in memory for one job).
**Why it's wrong:** Pronoun pairs, names, and terms drift between episodes — the exact failure Trezarr exists to fix. Relationships that evolve (enemies→lovers) can't be modeled at all.
**Do this instead:** A persistent, versioned, per-series Bible carried forward across episodes with an explicit relationship-evolution timeline keyed by episode markers.

### Anti-Pattern 4: Losing ASS styling by round-tripping through SRT

**What people do:** Normalize everything to plain SRT internally, then write back.
**Why it's wrong:** SubRip has no concept of styles/positioning/fonts; anime/fansub ASS files lose their formatting permanently.
**Do this instead:** Use an SSA-native internal model (pysubs2) and serialize back to the *original* format; translate only the text payload of each event, leaving timing and override tags intact.

### Anti-Pattern 5: Non-idempotent jobs that re-translate on every restart

**What people do:** Re-process the whole library on each startup/poll.
**Why it's wrong:** Wastes the user's LLM budget and can clobber good output; long-running Docker services restart often.
**Do this instead:** Provenance markers + source-sub hashing so an item is translated once unless the source changes; resumable pipeline stages so a restart continues mid-job.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Sonarr / Radarr** | REST API (`/api/v3`, API-key auth) for library + metadata; "On Import"/"On Download" webhooks for triggers | Source of truth for what exists; primary metadata source (title/IDs); path-mapping required |
| **Bazarr** | REST API for existing subtitle inventory + languages | Tells Trezarr which source subs already exist, so it doesn't fetch (acquisition stays Bazarr's job) |
| **TMDB** | REST API for plot/cast/genre to ground register and entity inference | Optional but high-value for Pass 1; cache per series |
| **User's LLM endpoint** | OpenAI-SDK-compatible (`base_url`, model, key) | Single client wrapper; needs JSON/structured output, retries, backoff; capability varies by endpoint — degrade gracefully |
| **Plex/Jellyfin/Emby** | Indirect — they auto-detect the `.vi.srt`/`.vi.ass` sidecars | No API integration; correctness is purely naming convention (ISO-639-1 `vi`) + placement next to media |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Integration layer ↔ rest of app | Normalized `MediaItem` model | External wire formats never leak inward |
| Discovery ↔ Job queue | Enqueue `TranslateJob` | One-way; discovery never runs translation inline |
| Pipeline ↔ Subtitle codec | `SubDoc` / `SubLine` model | Codec is LLM-agnostic and fully unit-testable |
| Pipeline ↔ Series Bible store | read (inject) / write (merge+commit) | Per-series serialization enforced here |
| Web UI ↔ Bible store | read + edit-with-lock | The only human write path into pipeline behavior |

## Suggested Build Order (dependency graph, MVP vertical slice)

The dependency graph favors getting one real `.vi.srt` written end-to-end as early as possible,
then deepening each component. Foundational/leaf components first.

```
[1] Subtitle codec (parse/serialize/validate SRT first)   ── no external deps, pure + testable
        │
[2] LLM client wrapper (OpenAI-compatible, JSON, retries)  ── independent leaf
        │
[1]+[2] ─▶ [3] Minimal pipeline: single-pass translate + validate + write sidecar
        │            (proves the file-out half of the system end-to-end)
        │
[4] Integration layer: Sonarr/Radarr client + path mapping ── proves the knowledge-in half
        │
[3]+[4] ─▶ [5] Discovery + idempotency (find candidates, skip done)   ◀── FIRST VERTICAL SLICE:
        │            + trivial in-process job runner                        library → translate → sidecar
        │
[6] Series Bible store + models (persist/version/carry-forward)
        │
[6] ─▶ [7] Upgrade pipeline to 3-pass: Pass1 analyze→Bible,
        │            Pass2 windowed translate w/ Bible inject + speaker/addressee,
        │            Pass3 self-review   ◀── THIS is the core differentiator
        │
[8] Chunking/token-budget (needed once real long files hit Pass 2)
        │
[9] Source selection (relational-fidelity ranking) + Bazarr client
        │
[10] ASS/SSA + VTT format support (extend codec [1])
        │
[11] Web UI + internal API: config, dashboard, history
        │
[12] Series Bible editor UI + field locking (the human-override valve)
        │
[13] Real job queue (concurrency, per-series serialization, retries) +
     webhook receiver + scheduler   ── hardening for many-episode operation
        │
[14] Dockerization + compose-alongside-arr + path-mapping UX polish
```

**Why this order:**
- **Codec + LLM client are leaves** with no dependencies — build and test them in isolation first.
- **Single-pass pipeline before three-pass:** proves the mechanical file-in/file-out path (the part most likely to have format/timing bugs) before layering the expensive, novel LLM logic. Validation must exist before any LLM writes a file.
- **First vertical slice = steps 1–5:** a real episode discovered via Sonarr and translated to a sidecar, even crudely. This de-risks integration + path-mapping (the ecosystem's biggest friction) early.
- **Series Bible (6–7) is the differentiator and depends on the slice working** — there's no point building consistency state until something translates. This is also the phase most likely to need its own deep research (prompt design, Bible schema, speaker inference quality).
- **Source selection, multi-format, UI, real queue, Docker** are deepening/hardening layers that each assume the core loop works; they can be ordered by user-visible value.

## Sources

- Bazarr (architecture reference) — https://github.com/morpheus65535/bazarr (HIGH; official repo, confirms Python backend, separate frontend, API-not-disk discovery, sidecar output)
- Bazarr Wiki — Setup/Settings (path mapping, "Alongside Media File") — https://wiki.bazarr.media/Getting-Started/Setup-Guide/ , https://wiki.bazarr.media/Additional-Configuration/Settings/ (HIGH)
- pysubs2 docs — SRT/ASS/SSA/VTT, style preservation, `keep_ssa_tags`/`keep_html_tags` — https://pysubs2.readthedocs.io/en/latest/tutorial.html , https://github.com/tkarabela/pysubs2 (HIGH)
- Sonarr/Radarr webhook & "On Import" connect triggers — https://notifiarr.wiki/pages/integrations/sonarr/ (MEDIUM; community wiki, corroborated by multiple sources)
- LLM subtitle translation pipeline (multi-pass split-brain, 3–5 line chunking, plot/character context for consistency, self-refine) — https://apoorvamittal.substack.com/p/how-subtitles-are-generated-using (MEDIUM; single detailed source, pattern corroborated by chunking literature)
- Chunking/context-window practice — https://weaviate.io/blog/chunking-strategies-for-rag , https://www.typedef.ai/resources/tackle-chunking-context-windows-llm-data-pipelines (MEDIUM)
- Python job-queue options (Celery/RQ/Huey/APScheduler tradeoffs; "start with APScheduler, add a queue for retries/backpressure") — https://medium.com/@ThinkingLoop/7-scheduler-strategies-for-python-jobs-celery-rq-arq-48b1eb5f8f79 (MEDIUM)
- Sidecar naming / ISO-639-1 `vi` for Plex/Jellyfin auto-detect — https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/ , https://jellywatch.app/blog/jellyfin-subtitles-complete-guide-2026 (MEDIUM-HIGH)

---
*Architecture research for: self-hosted Vietnamese subtitle-translation companion to the arr stack*
*Researched: 2026-05-31*
