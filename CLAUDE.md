<!-- GSD:project-start source:PROJECT.md -->
## Project

**Trezarr**

Trezarr is an automated Vietnamese subtitle translator that runs as a companion to the
Bazarr / Sonarr / Radarr self-hosted media stack. It watches for media that has a
source-language subtitle but no high-quality Vietnamese one, translates it with the user's
own LLM endpoint, and writes a Vietnamese sidecar subtitle (`Show.S01E01.vi.srt`) next to the
media — fully automated, no human in the loop. Its mission is to produce Vietnamese subtitles
good enough to **replace a human translator**, with the glossary, pronoun, and relationship
consistency that ordinary machine translation destroys.

**Core Value:** Vietnamese subtitles that stay **consistent and relationally correct across an entire series** —
the right pronoun pair (anh/em, chị/em, ông/bà...) for every relationship, the same character
names and terms from episode 1 to the finale — produced automatically. If everything else fails,
this consistency must work.

### Constraints

- **Tech stack**: LLM access is via an OpenAI-SDK-compatible endpoint (user-provided base URL/model/key)
- **Deployment**: Must run as a Dockerized self-hosted service with a web UI, deployable alongside Bazarr/Sonarr/Radarr
- **Integration**: Must interoperate cleanly with Sonarr/Radarr/Bazarr APIs and the *arr-stack filesystem/sidecar conventions
- **Compatibility**: Output subtitles must be auto-detected by common media players (Plex/Jellyfin/Emby) and preserve original styling for ASS/SSA
- **Quality bar**: Fully automated output must be trustworthy enough to use blind ("replace human translator") — consistency is non-negotiable
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## TL;DR Prescription
## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Backend runtime | Matches Bazarr/*arr ecosystem; only runtime with mature, styling-preserving subtitle libs AND the best *arr client AND first-class OpenAI SDK. `pyarr` 6.x requires `>=3.12`, so 3.12 is the floor. |
| FastAPI | 0.136.x | Web framework + REST API for the dashboard | Async-native (critical — the whole app is I/O bound on LLM + *arr + filesystem calls), Pydantic-native (the Series Bible and LLM structured outputs are both Pydantic models — one type system end to end), auto-generates OpenAPI/Swagger for the UI to consume. |
| Uvicorn | 0.48.x | ASGI server | Standard FastAPI production server; single process is fine for a single-user self-hosted daemon. Run the daemon/scheduler in the same process via FastAPI lifespan. |
| openai | 2.38.x | LLM client (user-provided OpenAI-compatible endpoint) | The constraint is "OpenAI-SDK-compatible endpoint." `AsyncOpenAI(base_url=..., api_key=..., max_retries=...)` makes base URL / key / model fully configurable and gives free exponential-backoff retries on 429/5xx/timeouts. `chat.completions.parse(response_format=PydanticModel)` gives typed structured outputs for the Series Bible. |
| pysubs2 | 1.8.x | Subtitle parse/serialize (SRT, ASS/SSA, VTT) | Single library covers ALL three required formats with a unified API, and is the only one that round-trips ASS/SSA styles, fonts, positioning, and inline override tags — exactly the "preserve styling" requirement. Avoids juggling three separate libraries. |
| pyarr | 6.6.x | Sonarr/Radarr/Bazarr API client | Maintained, covers Sonarr + Radarr + Bazarr in one client, returns plain JSON (resilient to *arr API drift), supports sync and asyncio. Saves writing/maintaining REST plumbing for three services. |
| SQLAlchemy | 2.0.x | ORM / persistence layer for the Series Bible | The Series Bible is relational (Characters → directed Address-Map pairs → relationship-evolution markers → Term Dictionary). SQLAlchemy 2.0 async + a single SQLite file fits the *arr `/config` convention and supports the editable, propagating-correction model. |
| aiosqlite | 0.22.x | Async SQLite driver | Lets the FastAPI/async stack hit SQLite without blocking the event loop. |
| React + Vite | React 19 / Vite 7 | Dashboard SPA (Series Bible editor, job status, config) | Bazarr uses React; matches user/community expectations. Vite builds to static assets that FastAPI serves directly — no second web server, one container, one port. |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pydantic | 2.13.x | Models for config, Series Bible, and LLM structured outputs | Always. One model type used as the LLM `response_format`, the API response schema, and the DB shape (or paired with SQLModel). |
| pydantic-settings | 2.14.x | Env-var + file config loading | Always — *arr images are env-config driven; this reads `TREZARR_*` env vars and a `/config/config.yaml` with one declarative model. |
| APScheduler | 3.11.x | In-process job scheduling (poll *arr APIs, periodic library scans) | Always — the daemon polls Sonarr/Radarr/Bazarr on an interval and runs the two-pass translation pipeline. In-process scheduler avoids a separate worker/broker for a single-user daemon. |
| watchfiles | 1.2.x | Filesystem watching for new/changed subtitle sidecars | Use as the event-driven complement to polling — react immediately when Bazarr writes a new source `.srt`/`.ass` into the media tree. Rust-backed, async, debounced. |
| httpx | 0.28.x | HTTP client | Already pulled in by openai/fastapi; use directly for the Bazarr webhook receiver or any *arr call pyarr doesn't cover. |
| tenacity | 9.1.x | Retry/backoff for the multi-step pipeline | Use for orchestration-level retries (whole translation step / *arr call). The OpenAI SDK handles per-request retries itself, so use tenacity at the pipeline boundary, not around individual LLM calls. |
| Alembic | 1.18.x | DB schema migrations | Add once the Series Bible schema is real — the Bible WILL evolve (relationship-evolution markers, locked corrections) and self-hosted users have existing DBs to migrate. |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Dependency + venv management | Fast, lockfile-based; standard for new 2025/2026 Python projects. Reproducible Docker builds. |
| Ruff | Lint + format | Replaces black + isort + flake8 in one fast tool. |
| pytest + pytest-asyncio | Testing | Async tests for the FastAPI/pipeline code; fixture-based SQLite for Series Bible tests. |
| s6-overlay | Container init / PUID-PGID handling | The LinuxServer.io base image mechanism; gives you PUID/PGID drop-privileges and `/config` ownership fixup for free. |
## Installation
# Project + deps (uv)
# Dev dependencies
# Frontend (separate package, built to static assets FastAPI serves)
## OpenAI-Compatible Client — Prescribed Patterns
- **Configurability:** instantiate one `AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key, max_retries=4, timeout=120)`. `base_url`, `api_key`, and `model` (passed per-call) come from `pydantic-settings`. This satisfies "user brings their own OpenAI-compatible endpoint."
- **Structured outputs:** use `client.chat.completions.parse(model=..., messages=..., response_format=SeriesBible)` so the Series Bible and per-line translation results come back as typed Pydantic objects, not hand-parsed JSON. Falls back to `response_format={"type": "json_object"}` (JSON mode) if the user's endpoint doesn't support strict json_schema (many local/proxy endpoints don't — detect and degrade).
- **Retries:** rely on the SDK's built-in exponential backoff for transient 429/5xx/timeout. Set `max_retries` on the client. Do NOT wrap individual `create`/`parse` calls in tenacity (double-retry storm). Use tenacity only at the pipeline-step level.
- **Concurrency control:** the daemon translates many lines/files; cap parallel in-flight LLM calls with an `asyncio.Semaphore` (e.g. 4–8) rather than firing all `create()` coroutines at once. This is the single most important reliability knob against user endpoints with low rate limits.
## *arr Integration — Prescribed Approach
- **Auth:** all three (Sonarr/Radarr/Bazarr) authenticate with an API key. Send it as the `X-Api-Key` header (preferred) or `?apikey=` query param. `pyarr` handles this.
- **API roots:** Sonarr/Radarr expose REST v3 at `/api/v3` (series, episode, movie, queue, calendar, system status). Bazarr exposes `/api/*` and a `/api/webhooks/plex` incoming hook.
- **Discovery + subtitle state:** poll Sonarr/Radarr for the library (series/episodes/movies + file paths + TMDB/TVDB metadata for the register/genre signal), and query Bazarr for existing subtitle state per item. This identifies "has source sub, lacks good Vietnamese sub."
- **Events:** Sonarr/Radarr support outgoing webhooks via Settings → Connect (On Import / On Download / On Upgrade). Bazarr can POST outgoing webhooks on subtitle events. **Recommendation: hybrid.** Accept inbound webhooks (a FastAPI `/webhook` endpoint) for low-latency reaction, but ALSO poll on an APScheduler interval as the source of truth — webhooks are best-effort/lossy in this ecosystem and a missed event must not mean a permanently-untranslated episode.
## Series Bible Persistence — Prescribed Shape
- `series` — id, *arr/TMDB id, title, register/tone, source-language-priority decision
- `character` — id, series_id, original_latin_name, gender, rough_age, role
- `address_map` — id, series_id, speaker_character_id, addressee_character_id (the directed pair), self_term, address_term, `locked` (bool — the human-override valve), valid_from_episode (evolution marker)
- `term_dictionary` — id, series_id, source_term, vietnamese_rendering, category (proper noun / title / place / jargon), `locked`
- `relationship_event` — id, series_id, character_a, character_b, episode_marker, description (drives evolution of the address_map over the series)
- `processed_file` — id, series_id, episode key, source_path, source_lang, output_path, status, content_hash (idempotency for the watcher/poller)
## Docker Packaging — Prescribed Conventions
- **Base on the LinuxServer.io pattern** (`ghcr.io/linuxserver/baseimage-*` with s6-overlay) OR a plain `python:3.12-slim` + a small entrypoint that does PUID/PGID. The LSIO base gives PUID/PGID and `/config` permission handling for free — recommended.
- **PUID/PGID env vars** — drop privileges to the host user so sidecar `.vi.srt` files are written with correct ownership next to the media (non-negotiable: files must be owned like the rest of the *arr stack's output).
- **`/config` volume** — all state lives here: SQLite Bible DB, `config.yaml`, logs. This is the universal *arr convention.
- **Media volume(s)** mounted at the SAME paths as Sonarr/Radarr/Bazarr see them, so path mapping from the *arr APIs resolves on Trezarr's filesystem (path-mapping gotcha — see PITFALLS).
- **Env-based config** via `pydantic-settings`: `TREZARR_OPENAI_BASE_URL`, `TREZARR_OPENAI_API_KEY`, `TREZARR_MODEL`, `TREZARR_SONARR_URL/_APIKEY`, etc., with `/config/config.yaml` overrides editable from the UI.
- **Single image, single port** (e.g. 6868, echoing Bazarr's 6767): multi-stage Dockerfile builds the Vite SPA in a node stage, copies the static `dist/` into the Python image, and FastAPI serves it. No nginx, no second process.
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI | Flask (what Bazarr uses) | Only if you want byte-for-byte Bazarr parity. FastAPI's native async + Pydantic is strictly better for this I/O-bound, structured-output-heavy workload — prefer it. |
| Python | Node/TypeScript | Only if the team has zero Python skill. You'd lose `pysubs2` (no equally complete styling-preserving ASS lib in JS) and `pyarr`, and have to build that plumbing — net negative for this domain. |
| pysubs2 | `srt` + `ass` + `webvtt-py` (three libs) | If you needed deep, format-specific control beyond what pysubs2 exposes. For Trezarr, pysubs2's unified API covering all three formats is the right default; reach for `ass` 1.0.x only if pysubs2's ASS style fidelity proves insufficient for an edge case. |
| pyarr | Custom httpx wrapper | If pyarr lacks a specific Bazarr endpoint you need — drop to httpx for that one call (you already have httpx). Don't replace the whole client. |
| APScheduler (in-process) | arq / Celery + Redis | Only at multi-worker scale. A single-user self-hosted daemon should NOT require users to run Redis — keep it in-process. |
| SQLite | Postgres | Never for v1 — SQLite in `/config` is the *arr convention and single-writer is fine. Revisit only for a hypothetical multi-instance future. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Celery / arq + Redis broker | Forces users to run an extra service; massive overkill for a single-user daemon | APScheduler in-process + asyncio |
| Flatten Series Bible into JSON/YAML files | Loses referential integrity, no atomic per-field locking/propagation, full-file rewrites race the watcher | SQLite (SQLAlchemy 2.0 + aiosqlite) |
| Pure polling OR pure webhooks | Polling alone is high-latency; webhooks alone are lossy in the *arr ecosystem | Hybrid: webhook for latency + poll as source of truth |
| Per-call tenacity around OpenAI requests | Double-retries on top of the SDK's built-in backoff → request storms against the user's endpoint | SDK `max_retries` for requests; tenacity only at pipeline-step level |
| Firing all line-translation coroutines at once | Will trip rate limits on user-provided endpoints (often low-tier/local) | `asyncio.Semaphore`-bounded concurrency (4–8) |
| nginx in the container | Unneeded second process for a single-user SPA | FastAPI static-file serving of the Vite `dist/` |
| Sync `requests`/`openai` (sync) client in the FastAPI loop | Blocks the event loop; kills throughput on an I/O-bound app | `AsyncOpenAI` + async SQLAlchemy + httpx |
| Running container as root | Sidecar files get root ownership, breaking the shared *arr filesystem | PUID/PGID drop-privilege (s6-overlay / LSIO base) |
## Stack Patterns by Variant
- Detect at config-test time; fall back from `chat.completions.parse()` to `response_format={"type": "json_object"}` + manual Pydantic validation.
- Because the quality bar is "replace a human translator," prefer instructing the user toward a frontier model that supports strict structured outputs for the Series Bible pass.
- Lower the `asyncio.Semaphore` ceiling (configurable, default 4) and raise SDK `max_retries`. Batch fewer lines per request.
- Translate only the dialogue event text, never the style/format blocks; pysubs2 keeps styles intact on round-trip. Validate that inline override tags (`{\\...}`) inside dialogue are preserved/repositioned, not translated.
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pyarr 6.6.x | Python >=3.12 | This sets the minimum Python version for the whole project. |
| FastAPI 0.136.x | Pydantic 2.13.x, Uvicorn 0.48.x | All Pydantic v2; do not mix any Pydantic v1 deps. |
| SQLAlchemy 2.0.x (async) | aiosqlite 0.22.x | Use the `sqlalchemy[asyncio]` extra + `sqlite+aiosqlite://` URL. |
| openai 2.38.x | httpx 0.28.x | SDK bundles httpx; `.parse()` structured outputs require a json_schema-capable endpoint. |
| SQLModel 0.0.38 | SQLAlchemy 2.0.x, Pydantic 2.x | Optional convenience to unify ORM + Pydantic; pre-1.0, so accept some API churn if adopted. |
## Sources
- `/openai/openai-python` (Context7) — AsyncOpenAI base_url/api_key/max_retries config, `chat.completions.parse()` structured outputs, retry/backoff behavior — HIGH
- `/tkarabela/pysubs2` (Context7) + PyPI — SRT/ASS/SSA/VTT support, styling round-trip — HIGH
- PyPI JSON API (live, 2026-05-31) — current versions + requires_python for openai 2.38.0, pysubs2 1.8.1, fastapi 0.136.3, uvicorn 0.48.0, pydantic 2.13.4, sqlalchemy 2.0.50, aiosqlite 0.22.1, apscheduler 3.11.2, watchfiles 1.2.0, httpx 0.28.1, alembic 1.18.4, pydantic-settings 2.14.1, pyarr 6.6.0, tenacity 9.1.4, sqlmodel 0.0.38 — HIGH
- https://docs.linuxserver.io/general/understanding-puid-and-pgid/ — PUID/PGID, /config volume conventions — HIGH
- https://github.com/Radarr/Radarr/wiki/API + sonarr.tv/docs/api + Bazarr wiki — X-Api-Key auth, /api/v3 roots, Connect webhooks, Bazarr outgoing/incoming webhooks — MEDIUM (official docs, some via search summary)
- https://github.com/totaldebug/pyarr + PyPI — pyarr covers Sonarr/Radarr/Bazarr, sync+async, JSON results, maintained — MEDIUM
- https://hub.docker.com/r/linuxserver/bazarr + blog.miguelgrinberg.com (Dockerize React+Flask) — single-image multi-stage build, app-serves-static-SPA pattern — MEDIUM
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
