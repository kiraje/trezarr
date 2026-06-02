# Trezarr

**Automated Vietnamese subtitle translator for the Bazarr / Sonarr / Radarr self-hosted media stack.**

Trezarr runs as a companion daemon to your *arr stack. It watches for media that has a
source-language subtitle but no high-quality Vietnamese one, translates it with **your own
OpenAI-compatible LLM endpoint**, and writes a Vietnamese sidecar subtitle
(`Show.S01E01.vi.srt`) next to the media — fully automated, no human in the loop.

Its mission is to produce Vietnamese subtitles good enough to **replace a human translator** —
with the glossary, pronoun, and relationship consistency that ordinary machine translation
destroys.

---

## Why Trezarr?

Machine translation handles a single line well and an entire series badly. Vietnamese is
**relational**: the correct pronoun pair (`anh/em`, `chị/em`, `ông/bà`, …) depends on who is
speaking to whom and how that relationship evolves across the show. Generic MT picks a
different pronoun every episode, renames characters, and re-translates the same term three
ways.

Trezarr's core value is **consistency that holds across a whole series**:

- the **right directed pronoun pair** for every relationship, episode 1 to the finale;
- the **same character names and terms** everywhere, via a per-series **Series Bible**;
- produced **automatically**, so the output is trustworthy enough to use blind.

If everything else fails, this consistency is the thing that must still work.

---

## Features

- **Brings-its-own-LLM** — any OpenAI-SDK-compatible endpoint (OpenAI, Ollama, LM Studio,
  vLLM, a proxy…). You configure `base_url`, `model`, and `api_key`.
- **Series Bible** — a persistent, per-series store of characters, a directed Address Map
  (speaker → addressee pronoun pairs), a term dictionary, and relationship-evolution markers.
  Human-editable, with per-field **locks** that propagate corrections forward.
- **Three-pass pronoun engine** — attribute → reconcile → translate, with a self-review pass
  and a 7-check pre-write validation gate, so a single bad line can never silently ship.
- **\*arr-native integration** — discovers work from Sonarr/Radarr via `pyarr`, respects the
  shared *arr filesystem and sidecar conventions, and writes output with correct PUID/PGID
  ownership.
- **Hybrid discovery** — APScheduler polling as the source of truth, with optional inbound
  webhooks and a filesystem watcher for low-latency reaction.
- **Idempotent + resilient** — a processed-file ledger prevents re-translation; per-item
  quarantine means one bad episode never aborts the run.
- **Web UI + REST API** — a React dashboard (served by FastAPI on a single port) for config,
  job status, and editing the Series Bible.
- **Player-compatible output** — sidecar `.vi.srt` files auto-detected by Plex / Jellyfin / Emby.

---

## How it works

```
Sonarr / Radarr ──▶ discover ──▶ scan (eligible?) ──▶ translate ──▶ write .vi.srt
   (pyarr)          media items   has source sub,      3-pass +       PUID/PGID
                                  lacks good vi-sub     validation     sidecar
                                                        gate
                                        │                                  │
                                        └──────────── Series Bible ────────┘
                                            (pronouns · names · terms · locks)
```

1. **Discover** — poll Sonarr/Radarr for the library and file paths (per-service resilient:
   one *arr being down does not abort the run).
2. **Scan** — identify items that have a source-language subtitle but no acceptable
   Vietnamese one; the ledger skips anything already processed.
3. **Translate** — run the three-pass pronoun engine against the Series Bible, then a
   self-review pass and the validation gate.
4. **Write** — emit the `.vi.srt` sidecar next to the media, owned by your configured
   `PUID:PGID` so it matches the rest of the *arr output.

---

## Quick start (Docker Compose)

The fastest path is alongside your existing *arr stack.

```bash
# 1. Get the example files
cp docker-compose.example.yml docker-compose.yml
cp config.yaml.example config/config.yaml   # edit llm_base_url / llm_model

# 2. Set required secrets (do NOT hardcode keys in compose/config)
export PUID=$(id -u) PGID=$(id -g)
export TREZARR_LLM_API_KEY=sk-...
export TREZARR_SONARR_API_KEY=...            # Sonarr → Settings → General → API Key
export TREZARR_RADARR_API_KEY=...

# 3. Launch
docker compose up -d
```

Then open the web UI at **http://localhost:6868**.

> **Path alignment (important):** Trezarr must mount your media at the **same path**
> Sonarr/Radarr/Bazarr see it inside their containers (e.g. `/media`). A mismatch means
> Trezarr can't locate source subtitles or write output. See `docker-compose.example.yml`.

> **Security:** Trezarr has **no built-in authentication** — it's designed for a private,
> trusted LAN next to your *arr stack. For external access, bind to `127.0.0.1` and put an
> authenticating reverse proxy (nginx / Caddy / Traefik) in front. Provide API keys via
> `TREZARR_*_API_KEY` environment variables, never in committed config.

---

## Local development

Trezarr uses [`uv`](https://github.com/astral-sh/uv) for dependency and venv management.

```bash
# Backend
uv sync                       # install deps into .venv
uv run trezarr run --once     # one-shot: discover → translate → write, then exit
uv run trezarr serve          # long-running daemon + web UI on :6868

# Tests / lint
uv run pytest
uv run ruff check .

# Frontend (React 19 + Vite 7 + Tailwind)
cd frontend
npm install
npm run dev                   # dev server
npm run build                 # production build -> served by FastAPI in the image
```

### CLI

| Command | What it does |
|---------|--------------|
| `trezarr run --once` | Runs a single discover → translate → write pass and exits. Non-zero exit on any per-item failure/quarantine. |
| `trezarr serve`      | Starts the daemon: web UI, REST API, scheduler/poller, and queue worker. |

Both accept `--config <path>` to point at a YAML config file.

---

## Configuration

All settings live in `config.yaml` (default `/config/config.yaml` in Docker), and **every
field can be overridden** by a `TREZARR_<FIELD>` environment variable. See
[`config.yaml.example`](./config.yaml.example) for the fully annotated reference. Highlights:

| Setting | Purpose | Default |
|---------|---------|---------|
| `llm_base_url` | OpenAI-compatible endpoint base URL | `http://localhost:1234/v1` |
| `llm_model` | Model name passed on every call | `gpt-4o` |
| `llm_api_key` | LLM key — **prefer `TREZARR_LLM_API_KEY` env var** | `not-set` |
| `llm_max_concurrency` | Max in-flight LLM calls (rate-limit knob) | `4` |
| `llm_structured_output_mode` | `auto` / `json_schema` / `json_object` / `text` | `auto` |
| `web_host` / `web_port` | Bind address / port for UI + API | `0.0.0.0` / `6868` |
| `poll_interval_seconds` | How often to poll Sonarr/Radarr | `900` |
| `enable_webhooks` | Inbound `/webhook` low-latency trigger | `true` |
| `bazarr_enabled` | Bazarr webhook integration | `false` |

The container persists all state — the SQLite Series Bible DB, `config.yaml`, logs, and the
quarantine — under the `/config` volume, following the standard *arr convention.

---

## Architecture

A single Python package, served as one container on one port.

```
trezarr/
├── cli.py            # `run --once` / `serve` entry points; the per-item pipeline
├── config.py         # pydantic-settings: env + YAML config
├── arr/              # Sonarr / Radarr discovery (pyarr), path-mapped
├── discover/         # scan + gap detection (what's eligible for translation)
├── subtitles/        # SRT parse/serialize, encoding/BOM fidelity (codec layer)
├── translate/        # 3-pass engine: attribute · reconcile · engine · batching
│                     # + sentinel + validate (the pre-write gate)
├── bible/            # Series Bible: models · store · merge · analyze (the moat)
├── llm/              # AsyncOpenAI client: semaphore concurrency, tiered structured output
├── output/           # processed-file ledger (idempotency) + permission-correct writes
├── paths.py          # container↔host path mapping + traversal guards
├── db/               # SQLAlchemy 2.0 async + Alembic migrations
├── jobs/             # job models
└── web/              # FastAPI app + APScheduler scheduler + queue worker
frontend/             # React 19 + Vite 7 + Tailwind SPA (built into the image)
```

**Stack:** Python 3.12 · FastAPI · Uvicorn · `openai` (AsyncOpenAI) · `pysubs2`-class codec
handling · `pyarr` · SQLAlchemy 2.0 + aiosqlite + Alembic · APScheduler · React 19 / Vite 7.

---

## Project status

Trezarr is **under active development** (`v0.1.0`). Of a 10-phase milestone, **8 phases are
complete (~80%)**.

| Phase | Area | Status |
|------:|------|:------:|
| 1 | Codec & LLM client foundation | ✅ |
| 2 | Mechanical translation core + validation gate | ✅ |
| 3 | \*arr integration + first vertical slice | ✅ |
| 4 | Series Bible store & schema | ✅ |
| 5 | Three-pass pronoun engine | ✅ |
| 6 | Relationship evolution + self-review | ✅ |
| 7 | Web UI & service hardening | ✅ |
| 8 | Editable Series Bible UI | ✅ |
| 9 | Multi-format — **ASS/SSA + VTT** styling preservation | 🚧 in progress |
| 10 | Source selection & per-series overrides | 🚧 in progress |

**What works today:** SRT translation with the full cross-series consistency engine, the
Series Bible, the web UI, and Sonarr/Radarr-driven discovery. **ASS/SSA and VTT** styling
preservation and **per-series source selection** are the remaining roadmap items — treat the
"preserve original styling for ASS/SSA" goal as *coming*, not *shipped*.

---

## License

No license has been declared for this repository yet. Until a `LICENSE` file is added, all
rights are reserved by the author. (Choosing and adding a license is a planned follow-up.)
