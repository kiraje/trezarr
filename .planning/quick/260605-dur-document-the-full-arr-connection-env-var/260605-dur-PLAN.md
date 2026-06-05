---
phase: quick-260605-dur
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docker-compose.yml
  - .env.example
autonomous: true
requirements: [DOCS-01]
must_haves:
  truths:
    - "docker-compose.yml environment section contains commented-out TREZARR_SONARR_HOST/PORT/API_KEY/ENABLED, TREZARR_RADARR_HOST/PORT/API_KEY/ENABLED, and TREZARR_BAZARR_HOST/PORT/API_KEY/ENABLED lines (all 12 vars)"
    - "docker-compose.yml header comment no longer implies env vars are limited to API keys only — it describes the full host/port/key/enabled surface and the ENABLED=true footgun"
    - ".env.example contains commented-out entries for all 12 *arr env vars (host/port/api_key/enabled for each service) with a warning that TREZARR_<SVC>_ENABLED=true must be set explicitly"
    - "All new entries in both files are commented out by default so existing deployments that use config.yaml continue to work without any changes"
    - "API key vars in docker-compose.yml still use ${VAR:-} interpolation (never inline values)"
  artifacts:
    - path: "docker-compose.yml"
      provides: "Full *arr env-var surface documented and referenced"
    - path: ".env.example"
      provides: "Complete *arr connection vars documented with footgun warning"
  key_links: []
---

<objective>
Surface the full *arr (Sonarr / Radarr / Bazarr) connection env vars in docker-compose.yml
and .env.example so a user can configure every *arr connection entirely from docker-compose /
.env without touching the web UI.

Purpose: The pydantic-settings fields already accept env vars; only the documentation
surfaces are missing/incomplete. The existing comment in docker-compose.yml
says *arr config "is stored in /config/config.yaml … not as env vars" and only exposes
three API-key vars — this undersells the capability and misleads users who want pure-env
deployment.

Output:
- docker-compose.yml: corrected header comment + full 12-var commented block for all three services
- .env.example: full 12-var commented block with footgun warning about ENABLED=true
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@docker-compose.yml
@.env.example
</context>

<tasks>

<task type="auto">
  <name>Task 1: Correct docker-compose.yml header comment and expand the *arr env block</name>
  <files>docker-compose.yml</files>
  <action>
Make two targeted edits to docker-compose.yml — do NOT alter any other content.

Edit 1 — Header comment (lines 17-20): Replace the current misleading paragraph:

  # *arr connection (Sonarr/Radarr/Bazarr URLs + API keys) for THIS deployment is
  # stored in /config/config.yaml (written via the web UI), not as env vars, so it
  # survives redeploys via the config volume. Uncomment the TREZARR_*_API_KEY lines
  # below only if you prefer to inject them at runtime instead.

with:

  # *arr connection (Sonarr/Radarr/Bazarr) — two config paths (either works):
  #
  #   PATH A — Web UI (default): configure host/port/key in the Trezarr Settings page.
  #     The UI writes /config/config.yaml, which persists across redeploys via the
  #     config volume. No env vars needed; the UI marks env-overridden fields read-only.
  #
  #   PATH B — Pure-env (override): uncomment the TREZARR_*_HOST / _PORT / _API_KEY /
  #     _ENABLED vars below and supply values in .env. Env vars take precedence over
  #     config.yaml (env > YAML > code defaults).
  #
  #   IMPORTANT — ENABLED flag: the web UI auto-enables a service when host+key are
  #     set, but the env path does NOT. TREZARR_*_ENABLED defaults to false and is
  #     never set automatically. You MUST set TREZARR_<SVC>_ENABLED=true explicitly or
  #     discovery will silently return nothing (the client is never built).

Edit 2 — *arr env block (lines 56-59): Replace the current three-line block:

  # Optional: override *arr keys via env instead of config.yaml.
  # - TREZARR_SONARR_API_KEY=${TREZARR_SONARR_API_KEY:-}
  # - TREZARR_RADARR_API_KEY=${TREZARR_RADARR_API_KEY:-}
  # - TREZARR_BAZARR_API_KEY=${TREZARR_BAZARR_API_KEY:-}

with:

  # ── *arr connection (PATH B: pure-env override) ──────────────────────────────
  # Uncomment all four vars per service. ENABLED=true is mandatory (see header).
  # Sonarr (default port 8989)
  # - TREZARR_SONARR_HOST=${TREZARR_SONARR_HOST:-}
  # - TREZARR_SONARR_PORT=${TREZARR_SONARR_PORT:-8989}
  # - TREZARR_SONARR_API_KEY=${TREZARR_SONARR_API_KEY:-}
  # - TREZARR_SONARR_ENABLED=${TREZARR_SONARR_ENABLED:-false}
  # Radarr (default port 7878)
  # - TREZARR_RADARR_HOST=${TREZARR_RADARR_HOST:-}
  # - TREZARR_RADARR_PORT=${TREZARR_RADARR_PORT:-7878}
  # - TREZARR_RADARR_API_KEY=${TREZARR_RADARR_API_KEY:-}
  # - TREZARR_RADARR_ENABLED=${TREZARR_RADARR_ENABLED:-false}
  # Bazarr (default port 6767)
  # - TREZARR_BAZARR_HOST=${TREZARR_BAZARR_HOST:-}
  # - TREZARR_BAZARR_PORT=${TREZARR_BAZARR_PORT:-6767}
  # - TREZARR_BAZARR_API_KEY=${TREZARR_BAZARR_API_KEY:-}
  # - TREZARR_BAZARR_ENABLED=${TREZARR_BAZARR_ENABLED:-false}

All vars remain commented out. API keys use ${VAR:-} (never inline values). Do not
change any other line in the file.
  </action>
  <verify>
    <automated>grep -c 'TREZARR_SONARR_HOST\|TREZARR_RADARR_HOST\|TREZARR_BAZARR_HOST' /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr/docker-compose.yml</automated>
  </verify>
  <done>docker-compose.yml contains at least 3 lines referencing *_HOST vars (one per service); header no longer says "not as env vars"; ENABLED footgun warning is present; all new lines are commented out.</done>
</task>

<task type="auto">
  <name>Task 2: Expand .env.example with full *arr connection vars and footgun warning</name>
  <files>.env.example</files>
  <action>
Make one targeted edit to .env.example — do NOT alter any other content.

Replace the current three-line *arr block (lines 25-28):

  # Optional: inject *arr API keys via env instead of config.yaml.
  # TREZARR_SONARR_API_KEY=
  # TREZARR_RADARR_API_KEY=
  # TREZARR_BAZARR_API_KEY=

with:

  # ── *arr connection (pure-env PATH B — opt-in, all commented out by default) ──
  # Leave commented to use the web UI / config.yaml path (default behavior).
  # Uncomment ALL four vars per service when configuring via env.
  #
  # IMPORTANT: TREZARR_<SVC>_ENABLED=true must be set explicitly — the env path has
  # no auto-enable. Without it, discovery silently returns nothing.
  # The web UI will show env-configured fields as read-only ("set by environment").
  #
  # Sonarr (default port 8989)
  # TREZARR_SONARR_HOST=
  # TREZARR_SONARR_PORT=8989
  # TREZARR_SONARR_API_KEY=
  # TREZARR_SONARR_ENABLED=true
  #
  # Radarr (default port 7878)
  # TREZARR_RADARR_HOST=
  # TREZARR_RADARR_PORT=7878
  # TREZARR_RADARR_API_KEY=
  # TREZARR_RADARR_ENABLED=true
  #
  # Bazarr (default port 6767)
  # TREZARR_BAZARR_HOST=
  # TREZARR_BAZARR_PORT=6767
  # TREZARR_BAZARR_API_KEY=
  # TREZARR_BAZARR_ENABLED=true

All entries remain commented out. Do not change any other line in the file.
  </action>
  <verify>
    <automated>grep -c 'TREZARR_SONARR_HOST\|TREZARR_RADARR_HOST\|TREZARR_BAZARR_HOST' /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr/.env.example</automated>
  </verify>
  <done>.env.example contains all 12 *arr vars (host/port/api_key/enabled × 3 services), all commented out, with ENABLED footgun warning visible before the blocks.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| .env → container | API keys flow from gitignored .env into container env — never committed to VCS |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-dur-01 | Information Disclosure | .env.example | accept | File is intentionally empty/placeholder; API keys are never assigned, only documented as blank |
| T-dur-SC | Tampering | docker-compose.yml | accept | Documentation-only change; no new package installs or executable paths introduced |
</threat_model>

<verification>
After both tasks complete:
1. grep -c 'TREZARR_SONARR_HOST' docker-compose.yml returns >= 1
2. grep -c 'TREZARR_SONARR_HOST' .env.example returns >= 1
3. grep 'ENABLED' docker-compose.yml shows the footgun warning comment
4. grep 'ENABLED' .env.example shows the footgun warning comment
5. docker compose config (dry-run parse) succeeds — no YAML errors introduced
</verification>

<success_criteria>
- All 12 *arr env vars (host/port/api_key/enabled × 3 services) are documented in both docker-compose.yml and .env.example
- The ENABLED=true footgun is prominently called out in both files
- All new entries are commented out — existing config.yaml-based deployments are unaffected
- No Python source files were modified
- docker-compose.yml parses cleanly (docker compose config succeeds)
</success_criteria>

<output>
Create `.planning/quick/260605-dur-document-the-full-arr-connection-env-var/260605-dur-SUMMARY.md` when done.
</output>
