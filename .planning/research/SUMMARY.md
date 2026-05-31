# Project Research Summary

**Project:** Trezarr
**Domain:** Self-hosted, Dockerized LLM Vietnamese subtitle-translation daemon — companion to the Sonarr/Radarr/Bazarr (*arr) stack
**Researched:** 2026-05-31
**Confidence:** MEDIUM-HIGH

## Executive Summary

Trezarr is a long-running, Dockerized companion service that sits one level above Bazarr in the *arr stack: it learns the media library through **APIs**, acts on files through a **shared filesystem**, and delivers value as **sidecar subtitle files** (`Show.S01E01.vi.srt`) that Plex/Jellyfin/Emby auto-detect. The expert way to build this is unambiguous — **Python**, because the reference product (Bazarr) is Python and Python is the only runtime with mature, styling-preserving subtitle libraries (`pysubs2`), the most complete *arr API client (`pyarr`), and first-class OpenAI SDK support all at once. The recommended stack is Python 3.12 + FastAPI/Uvicorn (async, Pydantic-native), `pysubs2` for subtitle I/O, `openai` AsyncOpenAI for the user-provided endpoint, SQLAlchemy 2.0 + SQLite (`/config` volume) for the Series Bible, APScheduler + `watchfiles` for the daemon, and a React+Vite SPA served as static files from the same single LinuxServer.io-style container.

The product's entire moat is the **Series Bible**: a persistent, versioned, per-series consistency store (Characters, a *directed* Address Map of pronoun pairs, a Term Dictionary, Register, and a relationship-evolution timeline) that carries forward across episodes. No existing tool — not Bazarr's NMT hacks, not the leading LLM tools like `llm-subtrans` — is series-aware, relationship-aware, or Vietnamese-aware. The architecture is an **async, idempotent job pipeline** built around three LLM passes per item (Pass 1 analyze→Bible, Pass 2 windowed translate with Bible injection + speaker/addressee inference, Pass 3 self-review) followed by a mandatory no-LLM validation gate before any file is written.

The dominant risk is that, in an **unattended blind-trust system**, every error silently ships a wrong-but-plausible file the user never reviews. The critical mitigations are non-negotiable and must be designed in from the start, not bolted on: (1) a hard **line-count/timing validation gate** that quarantines rather than writes bad output; (2) the **directed Address Map + reliable speaker attribution** that is the whole reason Trezarr exists (a flipped pronoun is socially insulting, not just wrong); (3) **Bible lock/precedence + versioning** so human corrections never get re-derived away; (4) **per-series serialization + idempotency** so concurrency races don't corrupt the Bible and the watcher doesn't re-translate its own output; and (5) **Docker path-mapping + PUID/PGID** handling, the *arr ecosystem's #1 setup trap. Confidence is HIGH on stack and integration patterns (verified against real tools and official docs) and MEDIUM on the novel Bible/pronoun engine, which deserves its own deep research and a validation harness.

## Key Findings

### Recommended Stack

Build in **Python 3.12** — not a close call. The single-container pattern is a multi-stage Dockerfile that builds the Vite SPA and lets FastAPI serve the static `dist/`, with all state in a `/config` volume, matching *arr conventions self-hosters expect. Everything async (AsyncOpenAI + async SQLAlchemy + httpx) because the app is entirely I/O-bound on LLM/*arr/filesystem calls. See [STACK.md](STACK.md) for full detail.

**Core technologies:**
- **FastAPI 0.136 + Uvicorn**: async-native, Pydantic-native REST API + SPA host — one type system for config, Bible, and LLM structured outputs.
- **openai 2.38 (AsyncOpenAI)**: user-provided endpoint via `base_url`/`api_key`/`model`; `chat.completions.parse()` for typed Bible outputs, SDK `max_retries` for backoff. Fall back to JSON mode for endpoints lacking strict `json_schema`.
- **pysubs2 1.8**: single library covering SRT/ASS/VTT — the only one that round-trips ASS/SSA styling, fonts, positioning, and override tags.
- **pyarr 6.6**: one client for Sonarr + Radarr + Bazarr (sets the Python >=3.12 floor); returns plain JSON, resilient to API drift.
- **SQLAlchemy 2.0 + aiosqlite + Alembic**: relational Series Bible in a single SQLite file in `/config`; Alembic because the Bible schema will evolve.
- **APScheduler + watchfiles**: in-process scheduler (no Redis) for polling + event-driven filesystem reaction.
- **React 19 + Vite 7**: dashboard/Bible editor SPA, mirroring Bazarr; built to static assets.

**Explicitly avoid:** Celery/Redis broker (overkill for single-user), flat JSON/YAML Bible (loses integrity + locking), pure-polling or pure-webhook (use hybrid), per-call tenacity around OpenAI (double-retry storm), unbounded LLM concurrency (use an `asyncio.Semaphore`, default 4-8), running container as root.

### Expected Features

The bar is **low on translation quality but high on seamlessness** — a tool that doesn't match *arr conventions feels broken regardless of quality. The differentiator is the Series Bible consistency engine; everything else is table stakes. See [FEATURES.md](FEATURES.md).

**Must have (table stakes):**
- Sonarr/Radarr/Bazarr API connection + path mapping
- Monitor + auto-act on "has source sub, no good `vi` sub" + idempotency
- SRT parse/write preserving timing 1:1; atomic sidecar write with exact `Show.S01E01.vi.srt` naming
- OpenAI-compatible endpoint config; batching + surrounding-line context
- Web UI: config, queue, history, logs, retry; Dockerized service

**Should have (competitive — the moat):**
- Two-pass analyze→translate pipeline producing/using the Series Bible
- Series Bible: Characters + **directed Address Map** + Term Dictionary + Register
- LLM-inferred speaker/addressee attribution → correct pronoun pair
- Persistent cross-episode Bible + relationship-evolution tracking
- Editable Series Bible (view/correct/lock/propagate) — the human override valve
- LLM self-review pass; source-language selection by relational fidelity (zh/ko/ja/th > en)

**Defer (v1.x / v2+):**
- ASS/SSA styling preservation, VTT (after SRT baseline proves out)
- Webhook-driven triggering (polling first), per-series setting overrides
- Attribution confidence flags, notifications, glossary sharing

**Anti-features (explicitly rejected):** re-downloading source subs (Bazarr's job), multi-target languages (dilutes the moat), bundling a local model, segment-by-segment human review UI, burn-in/re-mux, ASR/Whisper, auto-resync.

### Architecture Approach

Trezarr discovers the library through **service APIs (never disk scanning)**, touches the filesystem only to read the chosen source sub and write the VI sidecar, and runs an async job queue where the unit of work is a 3-pass translation pipeline anchored by the Series Bible. Episodes of one series process **in order with per-series serialization** (correctness over throughput); different series run in parallel freely. See [ARCHITECTURE.md](ARCHITECTURE.md) for diagrams and the suggested 14-step build order.

**Major components:**
1. **Integration/Discovery layer** — *arr/Bazarr/TMDB clients + webhook receiver + poller; normalizes everything to an internal `MediaItem`; the only place that knows external wire formats.
2. **Discovery + idempotency engine** — "needs-VI?" decision, source-selection ranking, dedupe/skip-done.
3. **Subtitle codec (`pysubs2`)** — parse/serialize/validate SRT/ASS/VTT; LLM-agnostic and fully unit-testable; kept separate from the pipeline.
4. **Translation pipeline** — orchestrator state machine over Pass 1 analyze → Pass 2 windowed translate → Pass 3 self-review → validate → write.
5. **Series Bible store** — persist/version/carry-forward per-series state with per-field locks; read (inject into prompts), write (merge Pass-1 deltas respecting locks), user-edit.
6. **LLM client** — single choke-point wrapper for the user's endpoint (retries, JSON/structured output, concurrency cap).
7. **Web UI + internal API** — config, dashboard, history, and the Bible editor (the only human write path).

### Critical Pitfalls

All five top pitfalls share one theme: in unattended mode a silent error ships a wrong file the user trusts forever. See [PITFALLS.md](PITFALLS.md).

1. **Line-count drift / structural desync** — the LLM merges/splits/drops cues, causing an off-by-one timestamp cascade. Avoid: never let the model touch timecodes/indices (strip and re-attach locally); validate cue count after every batch with cascading batch-size fallback (20→10→5→1); treat 1:1 as a hard write gate — quarantine on failure.
2. **Wrong relational pronoun (the core-value failure)** — grammatical but socially insulting output. Avoid: directed Address Map grounded in real relationship facts + reliable attribution + relational-fidelity source selection + self-review checking pronoun consistency (not just fluency).
3. **Mis-inferred speaker/addressee flips the pair** — one wrong attribution poisons an exchange (junior speaking down to senior). Avoid: context-window attribution, confidence signals with a safe neutral fallback, reciprocal-pronoun check in self-review.
4. **Bible drift / stale-after-edit / bloat** — re-derivation overwrites human fixes; unbounded growth overflows context and silently truncates. Avoid: locked fields (human lock > prior value > new inference), append-with-provenance + versioning, explicit episode-marked relationship transitions, salience-based pruning.
5. **Silent bad-file write + concurrency/idempotency failures** — unvalidated output written and trusted; parallel same-series jobs corrupt the Bible; the watcher re-translates its own output in a loop. Avoid: mandatory pre-write validation gate (count, no untranslated/empty lines, UTF-8, parseable, monotonic timestamps); per-series single-writer serialization + atomic writes; idempotency record (source hash) + exclude self-produced files from watch events.

Also high-priority: **Docker path-mapping mismatch** (mirror *arr volume conventions, provide a path-map escape hatch, probe readability at startup) and **PUID/PGID/UMASK permissions** so sidecars are readable by the media server.

## Implications for Roadmap

Research strongly favors getting one real `.vi.srt` written end-to-end as early as possible (de-risking integration + path-mapping, the ecosystem's biggest friction), *then* layering the novel, expensive Bible/pronoun engine onto a working mechanical loop. The hard dependency is: **Pass 2 cannot pick a pronoun without the Address Map, which requires Pass 1, which requires a parsed source and a stable Bible schema.** Suggested phase structure:

### Phase 1: Mechanical Translation Core (file-in → file-out)
**Rationale:** Codec and LLM client are dependency-free leaves; build/test them in isolation before any novel logic. A single-pass translate proves the format/timing path (most likely to have bugs) before the expensive LLM layer.
**Delivers:** `pysubs2` SRT parse/serialize/validate; OpenAI-compatible LLM client wrapper (retries, JSON mode, concurrency cap); single-pass translate + validate + atomic sidecar write.
**Addresses:** SRT preserve-timing, sidecar naming, OpenAI-compatible endpoint, batching + surrounding-line context.
**Avoids:** Pitfall 1 (line-count drift — build the validation gate HERE, it is foundational) and Pitfall 7 (silent bad-file write — validate before overwrite from day one).

### Phase 2: *arr Integration + First Vertical Slice
**Rationale:** Proves the "knowledge-in" half and de-risks path-mapping/permissions early, while still crude. Completing this = a real episode discovered via Sonarr and translated to a sidecar.
**Delivers:** Sonarr/Radarr (+ later Bazarr) clients via `pyarr`, normalized `MediaItem`, path-mapping config + startup readability probe, discovery + idempotency engine, trivial in-process job runner, PUID/PGID/UMASK Docker handling.
**Uses:** `pyarr`, httpx, pydantic-settings, LinuxServer.io base / s6-overlay.
**Implements:** Integration/Discovery layer + Discovery/idempotency engine.
**Avoids:** Pitfall 8 (path mismatch), Pitfall 9 (permissions), Pitfall 10 (Bazarr race / re-processing loop), and the disk-scanning anti-pattern.

### Phase 3: The Series Bible + Three-Pass Pronoun Engine (the differentiator)
**Rationale:** This is the entire moat and depends on the slice working — no point building consistency state until something translates. This is the phase most likely to need dedicated research (prompt design, Bible schema, speaker-inference quality).
**Delivers:** Series Bible store (SQLite tables: character, address_map, term_dictionary, relationship_event, processed_file) with versioning, carry-forward, and per-field locks; upgrade to 3-pass (Pass 1 analyze→Bible merge respecting locks, Pass 2 windowed translate with Bible injection + speaker/addressee attribution, Pass 3 self-review); token-budgeted chunking with overlap.
**Addresses:** Two-pass+self-review pipeline, directed Address Map, attribution, persistent cross-episode Bible, register grounding, relationship evolution.
**Avoids:** Pitfall 2 (wrong pronoun), Pitfall 3 (mis-attribution), Pitfall 4 (Bible drift/stale — lock/precedence is a design decision settled before multi-episode runs), the stateless-glossary and per-line/whole-file anti-patterns.

### Phase 4: Bible Editor UI + Hardening for Unattended Operation
**Rationale:** The editable Bible is what earns blind trust; a real queue + observability makes the unattended promise safe. Depends on a stable Bible schema (Phase 3).
**Delivers:** Web UI (config, library/job dashboard, queue/history/logs/retry) + Series Bible editor with field locking + provenance display; real job queue with per-series serialization, retries, backpressure; webhook receiver; APScheduler poll + retry sweeps; crash-resumable checkpointing; full Dockerization + compose-alongside-arr + path-mapping UX polish.
**Addresses:** Editable Bible (human override valve), *arr-citizen UI baseline, automatic monitoring.
**Avoids:** Pitfall 5 (concurrency race — per-series single-writer), Pitfall 11 (no resumability), UX pitfalls (silent edit overwrite, invisible failures, unexplained skips).

### Phase 5: Depth — Multi-format, Source Selection, Self-Review Tuning
**Rationale:** Each item deepens a working core and can be ordered by user-visible value; none blocks v1's central thesis.
**Delivers:** ASS/SSA styling preservation + VTT (extend codec), source-language selection by relational fidelity + Bazarr inventory integration, self-review tuning, per-series setting overrides.
**Addresses:** ASS/VTT formats, relational-fidelity source ranking, per-series tuning.
**Avoids:** Pitfall 6 (ASS tag mangling — parse out `{...}`/`\N`, translate only plain spans, reassemble byte-identical) and encoding corruption.

### Phase Ordering Rationale
- **Leaves first, novel logic last:** codec + LLM client have no dependencies; the Bible/pronoun engine is the riskiest and most novel, so it sits on top of a proven mechanical loop.
- **Validation gate is Phase 1, not polish:** the blind-trust contract means line-count/timing validation must exist before any LLM ever writes a file.
- **Integration before differentiator:** path-mapping/permissions are the ecosystem's #1 friction and must be de-risked before investing in the Bible.
- **Per-series serialization is co-designed with the queue (Phase 4):** consistency-over-throughput is a deliberate correctness choice that must not be retrofitted onto a naive parallel queue.
- **ASS deferred but isolated:** orthogonal parser-layer concern; developed in parallel without entangling the consistency engine.

### Research Flags

Phases likely needing deeper research (`/gsd-plan-phase --research-phase <N>`) during planning:
- **Phase 3 (Series Bible + pronoun engine):** the novel core — prompt design per pass, Bible schema + lock/merge semantics, speaker/addressee inference reliability, Vietnamese pronoun-pair selection rules, and a cross-episode consistency validation harness. Highest research priority; needs native-speaker spot-checking.
- **Phase 5 (ASS/SSA support):** ASS override-tag grammar (`\an`, `\pos`, `\k` karaoke, `\N`, color/font) is intricate and easy to corrupt — flagged for dedicated research.
- **Phase 5 (source selection):** relational-fidelity ranking + source quality/sync scoring is a genuinely novel heuristic worth scoping.

Phases with standard, well-documented patterns (can likely skip research-phase):
- **Phase 1 (mechanical core):** `pysubs2` and OpenAI SDK are well-documented; strip-timecodes + per-cue-ID is a verified industry pattern.
- **Phase 2 (*arr integration):** API auth, path-mapping, and PUID/PGID are canonical, documented *arr conventions (TRaSH/Servarr guides).
- **Phase 4 (UI + Docker packaging):** FastAPI+SPA single-image pattern and *arr queue/history UX norms are established.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core libraries verified against PyPI (live), Context7, and official docs; versions/compat confirmed. Architecture-glue patterns MEDIUM. |
| Features | MEDIUM-HIGH | Integration + LLM-subtitle features HIGH from real tools (llm-subtrans, Bazarr); the Vietnamese-consistency engine is novel, so its feature shape is reasoned-from-evidence (MEDIUM). |
| Architecture | MEDIUM-HIGH | Bazarr companion-integration model HIGH from official sources; the specific Series-Bible design + 3-pass internals are well-attested patterns but Trezarr's exact realization is novel/unvalidated (MEDIUM). |
| Pitfalls | HIGH | HIGH for structural/format/integration (verified against tool implementations + *arr trackers + MT literature); MEDIUM for Vietnamese-specific and Bible pitfalls (reasoned from linguistics + MT research, not observed). |

**Overall confidence:** MEDIUM-HIGH — the mechanical and integration halves are well-trodden ground; the consistency engine is the one genuinely novel, unvalidated piece and is the right place to concentrate research and a validation harness.

### Gaps to Address

- **Pronoun-pair selection rules:** how to derive the directed Address Map from gender/age/role/relationship (including romantic convention: man=anh, woman=em regardless of age) is not fully specified — needs prompt-engineering + linguistics research and a native-speaker-validated test harness in Phase 3.
- **Speaker/addressee attribution reliability:** the quality ceiling depends on how well a frontier model infers who-speaks-to-whom from unlabeled dialogue. Needs empirical measurement on real episodes; design confidence-flagging + safe-default fallback.
- **Bible context budgeting:** salience-based pruning thresholds are unspecified; context-window overflow is a *correctness* risk (silent truncation) even though token cost is out of scope. Validate Bible-token measurement on a 10+ episode series.
- **Endpoint capability variance:** many user/local endpoints lack strict `json_schema` structured outputs; detect at config-test time and degrade to JSON mode + manual validation. Recommend a frontier model for the Bible pass.
- **ASS karaoke remapping:** if syllable count changes on translation, `\k` timing can't be cleanly remapped — for v1, prefer preserving karaoke lines verbatim over corrupting them.

## Sources

### Primary (HIGH confidence)
- `/openai/openai-python` (Context7) — AsyncOpenAI base_url/key/max_retries config, `chat.completions.parse()` structured outputs, retry/backoff.
- `/tkarabela/pysubs2` (Context7) + PyPI + readthedocs — SRT/ASS/SSA/VTT support, style preservation, `keep_ssa_tags`.
- PyPI JSON API (live 2026-05-31) — current versions + `requires_python` for the full dependency set.
- Bazarr repo + Wiki (architecture reference) — Python backend + separate frontend, API-not-disk discovery, sidecar output, path mapping, auto-translation explicitly not on roadmap.
- LinuxServer.io / TRaSH Guides / Servarr Docker Guide — PUID/PGID/UMASK, `/config` volume, remote path mappings (the canonical *arr conventions).
- Bazarr issues #3195/#3252/#703 + Plex/Jellyfin docs — sidecar naming pitfalls, ISO-639-1 `vi`, UTF-8 requirement.
- `Cerlancism/chatgpt-subtitle-translator` + `rockbenben/subtitle-translator` (implementation-verified) — strip-timecodes-locally, per-cue-ID, cascading batch-size retry, timestamp-boundary validation.
- `machinewrapped/llm-subtrans` — leading LLM subtitle tool feature set (batching, terminology maps, format preservation; confirms the gap Trezarr fills).
- Vietnamese pronouns/honorifics (Wikipedia, Migaku, Vietnameselab) — relational/register system, romantic convention.
- Aegisub / Nikse ASSA override-tag references — ASS tag grammar.
- arXiv 1909.05362 (subtitle MT problems) — proper-noun gap, over-translation.

### Secondary (MEDIUM confidence)
- `totaldebug/pyarr` + PyPI — covers Sonarr/Radarr/Bazarr, sync+async, JSON results.
- Sonarr/Radarr/Bazarr API + webhook docs (notifiarr/servarr wikis) — X-Api-Key auth, /api/v3 roots, Connect webhooks (best-effort/lossy → hybrid poll+webhook).
- apoorvamittal.substack.com (LLM subtitle pipeline) — multi-pass split-brain, chunking, self-refine, alignment failure modes.
- arXiv 2412.20440 — adaptive context/style dialogue translation.
- Idempotency/checkpointing in LLM pipelines (tianpan.co, zylos.ai) — idempotency keys, resumability.
- arr-dashboard / Homarr — queue/history/retry UX norms.

### Tertiary (LOW confidence)
- Alibaba product-insights (anime honorific translation) — English flattening of honorifics (vendor source; corroborates linguistic claim only).

---
*Research completed: 2026-05-31*
*Ready for roadmap: yes*
