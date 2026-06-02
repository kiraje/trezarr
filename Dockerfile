# ─────────────────────────────────────────────────────────────────────────────
# Trezarr — multi-stage Docker image (D-64)
#
# Stage 1 (node-builder): builds the React/Vite SPA
# Stage 2 (runtime):      Python 3.12-slim + uv; installs Trezarr, copies
#                         built SPA, drops to PUID:PGID via gosu, runs
#                         `trezarr serve` on port 6868.
#
# PUID/PGID drop-privilege (INTG-04): the entrypoint.sh script reads PUID and
# PGID environment variables (default 1000:1000), creates a matching user/group
# inside the container, chown-s /config to that user, then gosu-execs the
# process.  This ensures any .vi.srt sidecars written to the media volume carry
# the same host ownership as the rest of the *arr stack output.
#
# Volumes:
#   /config  — SQLite Series Bible DB, config.yaml, quarantine, logs
#   /media   — media tree; MUST match the paths Sonarr/Radarr/Bazarr see
#              (see docker-compose.example.yml §IMPORTANT comment)
#
# Port: 6868 (web UI + REST API)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build the React/Vite SPA ────────────────────────────────────────
FROM node:20-slim AS node-builder

WORKDIR /app

# Copy package manifests first for layer-cache efficiency
COPY frontend/package.json frontend/package-lock.json ./frontend/

# Install dependencies from lockfile for reproducibility (T-07-06-04)
RUN cd frontend && npm ci --prefer-offline

# Copy full frontend source and build
COPY frontend/ ./frontend/
RUN cd frontend && npm run build
# Output lands at /app/trezarr/web/static (vite.config.ts outDir: ../trezarr/web/static)
# The path is relative to the frontend/ CWD so the resulting tree is:
#   /app/trezarr/web/static/index.html
#   /app/trezarr/web/static/assets/...


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim

# Install gosu (privilege drop) and curl (HEALTHCHECK).
# gosu is the canonical Docker privilege-drop utility used by official
# Postgres and Redis images — see T-07-06-SC in the threat model.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gosu \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast, lockfile-based dependency manager)
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency manifests first (layer cache)
COPY pyproject.toml uv.lock ./

# Phase 1 — install ONLY third-party dependencies (NOT the project itself), so
# this expensive layer stays cached when only app source changes. The trezarr
# package is installed in phase 2 below, once its source has been copied in.
RUN uv sync --frozen --no-dev --no-install-project

# Put the uv-created virtualenv on PATH so the `trezarr` console script
# (created by the phase-2 sync at /app/.venv/bin/trezarr) is resolvable. Without
# this the entrypoint's `gosu … trezarr serve` fails with
# `exec: "trezarr": executable file not found in $PATH`.
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source
COPY trezarr/ ./trezarr/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy built SPA from node-builder stage (FastAPI serves via StaticFiles).
# Copied BEFORE the phase-2 sync so the SPA ships inside the package tree.
COPY --from=node-builder /app/trezarr/web/static ./trezarr/web/static

# Phase 2 — now that the source (and built SPA) are present, install the trezarr
# project itself into the venv. This creates the `trezarr` console script and
# makes `import trezarr` resolve at runtime; without it the daemon dies with
# `ModuleNotFoundError: No module named 'trezarr'`. The editable install points
# at /app/trezarr, so the SPA is served from the real tree (StaticFiles resolves
# static/ relative to trezarr/web/app.py's __file__) — no wheel-data or
# gitignore packaging surprises.
RUN uv sync --frozen --no-dev

# Normalize permissions: the entrypoint drops to an ARBITRARY runtime UID/GID
# (PUID/PGID, default 1000) via gosu, so every file under /app must be readable
# and every directory traversable by that user. COPY preserves the build
# context's source modes — on some hosts a package dir lands mode 700/root,
# which makes the non-root runtime fail with `ModuleNotFoundError` when it
# can't traverse it. `a+rX` adds read for all + traverse on directories (app
# code is not secret), keeping the privilege-drop design intact.
RUN chmod -R a+rX /app

# Copy PUID/PGID entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# /config holds the SQLite DB, config.yaml, quarantine, and logs.
# Declare as a VOLUME so Docker creates it if not bind-mounted.
VOLUME ["/config"]

# Web UI + REST API port (D-76, D-78)
EXPOSE 6868

# Default: use /config/config.yaml (the *arr volume convention).
# Override at runtime via TREZARR_CONFIG_PATH env var if needed.
ENV TREZARR_CONFIG_PATH=/config/config.yaml

# HEALTHCHECK hits the FastAPI health endpoint that is always present.
# --start-period gives the lifespan (DB migration + scheduler startup) time
# to complete before the first check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD curl -f http://localhost:6868/api/health || exit 1

# entrypoint.sh drops to PUID:PGID then exec-s the CMD.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["trezarr", "serve"]
