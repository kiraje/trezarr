# Deploying Trezarr

A practical guide to running Trezarr as a Dockerized companion to your
Sonarr / Radarr / Bazarr stack. Trezarr watches for media that has a source-language
subtitle but no good Vietnamese one, translates it with **your** LLM endpoint, and writes a
`Show.S01E01.vi.srt` sidecar next to the media — fully automated.

> **TL;DR (Linux + Docker, build on the server):**
> ```bash
> git clone <your-origin-url> trezarr && cd trezarr
> id <your-media-user>                 # note uid=/gid= → PUID/PGID
> cp .env.example .env && $EDITOR .env # set LLM key, PUID/PGID, host paths
> docker compose up -d --build
> docker compose logs -f trezarr       # wait for healthcheck → healthy
> ```
> Then finish setup in the web UI at `http://<server>:6868` → **Settings** (see [First-boot setup](#5-first-boot-setup-web-ui)).

---

## 1. What gets deployed

| Aspect | Value |
|--------|-------|
| **Image** | `trezarr:local`, built locally from a multi-stage `Dockerfile` (Node builds the SPA → `python:3.12-slim` runtime). No registry required. |
| **Port** | `6868` (web UI + REST API) |
| **Process user** | Drops privileges to `PUID:PGID` via `gosu` (entrypoint.sh) so `.vi.srt` sidecars are owned like the rest of your *arr output |
| **`/config` volume** | All persistent state: SQLite Series Bible DB (`trezarr.db`), `config.yaml`, quarantine, ledger, logs. **Back this up.** |
| **`/data/media` volume** | Your media tree, mounted at the **container** path `/data/media` |
| **Restart policy** | `unless-stopped` |
| **Healthcheck** | `curl /api/health` every 30s (30s start grace for DB migration + scheduler) |

State lives in `/config`, so you can rebuild/upgrade the image freely without losing the
Series Bible, your locks, or your settings.

---

## 2. Prerequisites

- **Docker Engine + Docker Compose v2** on the target host.
- **A running *arr stack** (at least Sonarr and/or Radarr; Bazarr optional) reachable from the
  Trezarr container over your LAN or a shared Docker network.
- **An OpenAI-SDK-compatible LLM endpoint** + API key (OpenAI, a proxy, Ollama, LM Studio, etc.).
  The quality bar is "replace a human translator" — a capable model is recommended, though the
  pipeline runs end-to-end on `ds/deepseek-v4-pro`.
- **The media must be visible to the Trezarr host** at a real path you can bind-mount, and you
  must know the path Sonarr/Radarr report for that same media (for `path_mappings` — see §4).
- **The UID:GID that owns your media** (so sidecars get correct ownership): run `id <user>`.

---

## 3. Quick start (Generic Linux, build on the server)

This is the recommended path: the server builds the image natively, so there is no
amd64/arm64 cross-architecture concern.

```bash
# 1. Get the code (build context = working tree; build only from a fully pushed commit)
git clone <your-origin-url> trezarr
cd trezarr

# 2. Find the media-owning user's UID:GID
id <your-media-user>
#   → uid=1000(media) gid=1000(media)  → PUID=1000 PGID=1000

# 3. Configure environment (secrets never live in git)
cp .env.example .env
$EDITOR .env

# 4. Build + run
docker compose up -d --build

# 5. Watch startup: Alembic migration → scheduler → healthcheck
docker compose logs -f trezarr
docker compose ps          # STATUS should reach "healthy"
```

> **Note on `--build`:** `docker compose up --build` builds from the **working tree**, not from
> git history. Build only from a commit that is fully pushed and checked out, or you risk shipping
> an image that differs from `origin/main`.

---

## 4. Configuration

Precedence (highest wins): **environment variable** → `/config/config.yaml` → built-in default.
Any setting can be overridden by an env var named `TREZARR_<FIELD>` (uppercase).

### 4.1 `.env` (read by docker-compose)

Copy `.env.example` → `.env` (gitignored). Only the LLM key is strictly required; the rest
override the defaults baked into `docker-compose.yml`.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `TREZARR_LLM_API_KEY` | **yes** | — | LLM endpoint key. Never committed. |
| `TREZARR_LLM_BASE_URL` | no | `https://api.tlemons.com/v1` | OpenAI-compatible base URL |
| `TREZARR_LLM_MODEL` | no | `ds/deepseek-v4-pro` | Model id passed on every call |
| `PUID` | recommended | `501` | UID that owns your media (from `id`) |
| `PGID` | recommended | `20` | GID that owns your media (from `id`) |
| `TREZARR_MEDIA_DIR` | recommended | `/Users/dustin/trezarr-uat-media` | **Host** media path (container side stays `/data/media`) |
| `TREZARR_CONFIG_DIR` | recommended | `/Users/dustin/trezarr-config` | **Host** path for the persistent `/config` volume |

> The shipped defaults are macOS dev values (`PUID 501:20`, `/Users/dustin/...`). On a Linux
> server you **must** override `PUID`/`PGID` and both host paths.

**LLM tuning — REQUIRED for DeepSeek-style endpoints.** DeepSeek (and many local/proxy
endpoints) reject strict `json_schema` and run slow with reasoning on. If your endpoint is one,
set these in `.env` or the daemon's first translation will fail:

| Variable | Value | Why |
|----------|-------|-----|
| `TREZARR_LLM_STRUCTURED_OUTPUT_MODE` | `json_object` | endpoint rejects `json_schema` strict mode |
| `TREZARR_LLM_REQUEST_TIMEOUT` | `600` | default `120` is too low for deepseek |
| `TREZARR_LLM_DISABLE_THINKING` | `true` | turn off the reasoning pass (latency/cost) |

**Full *arr connection via `.env` (no UI step needed).** Every *arr field and the tuning
settings are listed as **bare pass-through keys** in `docker-compose.yml`'s `environment:` block
(e.g. `- TREZARR_SONARR_HOST` with no `=value`). docker compose omits each from the container
when it is unset in `.env` — so `config.yaml`/defaults still win — and passes it through when you
set it. So you can configure the entire stack from `.env`:

```bash
# *arr (set ENABLED=true explicitly — the env path does NOT auto-enable)
TREZARR_SONARR_HOST=192.168.1.10
TREZARR_SONARR_PORT=8989
TREZARR_SONARR_API_KEY=<key>
TREZARR_SONARR_ENABLED=true
#  …same for TREZARR_RADARR_* and TREZARR_BAZARR_*
TREZARR_SOURCE_LANG_PRIORITY=["en"]
TREZARR_PATH_MAPPINGS=[{"remote":"/tv","local":"/data/media"}]
```

### 4.2 Path mapping — the critical step

Sonarr/Radarr return file paths **as they see them** (e.g. `/tv/Show/S01E01.en.srt`). Trezarr
sees that same file at **its** mount (`/data/media/...`). `path_mappings` is the dictionary
between the two. There are two independent layers:

```
 Sonarr API says:  /tv/Show/S01E01.en.srt
                        │
   path_mappings  {remote: /tv, local: /data/media}   ← translates the *arr path
                        ▼
 Trezarr opens:    /data/media/Show/S01E01.en.srt
                        ▲
   volume mount    <host media>:/data/media           ← makes the bytes visible in-container
                        │
 On disk (host):   /volume1/data/media/Show/S01E01.en.srt
```

- **`remote`** = the path prefix Sonarr/Radarr report (their view of the media).
- **`local`** = the path prefix Trezarr sees = the **container** side of your media mount (under `/data/media`).

> ⚠️ **Trezarr refuses to start** if any *arr is enabled and `path_mappings` is empty
> (`trezarr/paths.py`). If `remote`/`local` are wrong, source-subtitle lookup fails and **no
> sidecars are written** — the job appears to run but produces nothing.

Set mappings in the UI (Settings) or directly:

```yaml
# /config/config.yaml
path_mappings:
  - { remote: /tv,     local: /data/media }     # Sonarr's TV root
  - { remote: /movies, local: /data/media }     # Radarr's movie root
```
…or via env: `TREZARR_PATH_MAPPINGS='[{"remote":"/tv","local":"/data/media"}]'`

### 4.3 PUID / PGID ownership

The container entrypoint reads `PUID`/`PGID`, creates a matching user, `chown`s `/config`, then
`gosu`-drops to that user. Files Trezarr writes (the SQLite DB, and `.vi.srt` sidecars on the
media volume) are therefore owned by `PUID:PGID`. Set these to the **same user that owns the rest
of your *arr media** so players and Bazarr can read the sidecars.

Common conventions: bare Linux → output of `id <user>` (often `1000:1000`); unRAID → `99:100`.

---

## 5. First-boot setup (web UI)

> **Configured everything via `.env` (§4.1)?** Then this UI step is **optional** — env vars
> already fully configure the stack (and env-set fields show as read-only "set by environment"
> in the UI). Use the UI below only if you prefer storing config in `config.yaml`, or to edit
> settings that aren't in your `.env`.

On a fresh `/config` volume there is no `config.yaml` yet, so finish setup in the browser at
`http://<server>:6868` → **Settings**. This writes `config.yaml` into the persistent volume, so
it survives redeploys.

1. **LLM** — confirm base URL / model / key; use **Test Connection**. (DeepSeek users: the
   `llm_disable_thinking` toggle cuts latency/cost.)
2. **Sonarr / Radarr** — host, port (`8989`/`7878`), API key (Settings → General → Security in
   each app), and **enable** the ones you use.
3. **Bazarr** (optional) — host, port (`6767`), API key; enables subtitle-inventory source
   selection.
4. **Path mappings** — add one row per *arr media root (see §4.2). **Do this before enabling an
   *arr**, or startup will refuse.
5. **(Optional) Webhooks** for low-latency reaction — in Sonarr/Radarr → *Settings → Connect*,
   add a **Webhook** posting to `http://<trezarr-host>:6868/webhook` on **On Import / On Download
   / On Upgrade**. Polling (every 15 min by default) is the source of truth, so webhooks are a
   bonus, not a requirement.

---

## 6. Verifying the deployment

```bash
docker compose ps                          # STATUS = healthy
curl -fsS http://localhost:6868/api/health # 200 OK
```

- Open `http://<server>:6868` → the dashboard loads (purple shadcn UI).
- Open a **series → Bible view** — confirms the API serves DTOs with datetime fields without a
  500 (the `model_dump(mode="json")` guard).
- **Trigger one translation** (a single episode with a source sub via the library UI), then:
  ```bash
  ls -l /path/to/media/Show/      # a Show.S01E01.vi.srt appears, owned by PUID:PGID
  docker compose logs trezarr     # the three-pass pipeline + validation gate ran
  ```
- If a translation fails the pre-write validation gate, the partial output is quarantined under
  `/config/quarantine` rather than written next to the media.

---

## 7. Updating / redeploying

```bash
cd trezarr
git pull                       # fast-forward to the latest pushed main
docker compose up -d --build   # rebuild + recreate; /config volume is untouched
docker compose logs -f trezarr # Alembic auto-migrates the DB on startup
```

DB schema migrations run automatically on startup (`bible_db_run_migrations_on_startup`). Your
Series Bible, locks, and settings persist across rebuilds via the `/config` volume.

---

## 8. Backups & persistence

Everything that matters is in the **`/config`** host directory (`TREZARR_CONFIG_DIR`):

- `trezarr.db` — the Series Bible (characters, address map, locked terms, processed-file ledger)
- `config.yaml` — your settings
- `quarantine/`, `processed_files.json`, logs

Back up that directory. **Stop the container before copying `trezarr.db`** (or copy WAL files
too) to get a consistent SQLite snapshot:

```bash
docker compose stop trezarr
cp -a "$TREZARR_CONFIG_DIR" "$TREZARR_CONFIG_DIR.bak-$(date +%F)"
docker compose start trezarr
```

> Never write to the live `trezarr.db` from the host while the container is running — concurrent
> SQLite writes across a bind mount can corrupt it. For read-only inspection use
> `sqlite3 "file:trezarr.db?mode=ro"`.

---

## 9. Security

Trezarr has **no built-in authentication** (single-user / trusted-LAN design). To expose it
beyond a trusted network:

- In `docker-compose.yml`, bind to localhost only: `"127.0.0.1:6868:6868"`.
- Front it with an authenticating reverse proxy (Caddy, nginx, Traefik) terminating TLS + auth.

API keys (LLM and *arr) are stored as masked secrets and kept out of logs/API responses; prefer
injecting them via env vars over committing them to `config.yaml`.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Container exits immediately; log says `cannot start — no path_mappings configured` | An *arr is enabled but `path_mappings` is empty | Add path mappings (§4.2) **before** enabling Sonarr/Radarr |
| Job "completes" but no `.vi.srt` appears | `path_mappings` `remote`/`local` wrong, or media mount path mismatch | Verify the *arr-reported path prefix == `remote`, and that prefix resolves under `/data/media` in-container |
| `.vi.srt` written but owned by `root`/wrong user | `PUID`/`PGID` not set or wrong | Set `PUID`/`PGID` from `id <media-user>`, recreate the container |
| `ModuleNotFoundError: trezarr` at startup | Source dir copied mode-700 on an unusual host | Already handled (`chmod -R a+rX /app`); if customized, ensure `/app` is world-readable |
| Healthcheck never goes healthy | App crashed during lifespan (DB migrate / scheduler) | `docker compose logs trezarr`; check `/config` is writable by `PUID:PGID` |
| Bible view returns HTTP 500 | Pre-`c02ed94` image (datetime serialization) | Rebuild from current `main` |
| `Test Connection` fails on a local/DeepSeek endpoint | Endpoint rejects `json_schema` strict mode | Set `llm_structured_output_mode: json_object` (or `auto`) and raise `llm_request_timeout` |
| `401` from Sonarr/Radarr/Bazarr | Wrong API key or host/port | Re-copy the key from each app's *Settings → General → Security*; confirm reachability from the container |

To inspect inside the running container:
```bash
docker compose exec trezarr sh
cat /config/config.yaml
```

---

## Appendix: selected `config.yaml` fields

`config.yaml.example` documents the LLM/runtime/Bazarr block. The full set also includes:

```yaml
# ── *arr connection ──
sonarr_host: "192.168.1.10"     # TREZARR_SONARR_HOST
sonarr_port: 8989
sonarr_enabled: true            # TREZARR_SONARR_ENABLED
radarr_host: "192.168.1.10"
radarr_port: 7878
radarr_enabled: true
# API keys: prefer TREZARR_SONARR_API_KEY / TREZARR_RADARR_API_KEY env vars

# ── Path mapping (required when an *arr is enabled) ──
path_mappings:
  - { remote: /tv,     local: /data/media }
  - { remote: /movies, local: /data/media }

# ── Source-language priority for picking which sub to translate from ──
source_lang_priority: ["en"]

# ── Output ownership (usually leave at defaults; PUID/PGID env handles process user) ──
puid: -1        # -1 = leave unchanged (process already runs as PUID via gosu)
pgid: -1
umask: 18       # 0o022

# ── Series Bible DB (the moat — lives in /config) ──
bible_db_url: "sqlite+aiosqlite:////config/trezarr.db"
bible_db_run_migrations_on_startup: true
```

Every field above is overridable via `TREZARR_<FIELD>` env vars; list/object fields take a JSON
string (e.g. `TREZARR_PATH_MAPPINGS='[{"remote":"/tv","local":"/data/media"}]'`).
