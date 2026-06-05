---
phase: quick-260605-dur
plan: 01
subsystem: deployment-docs
tags: [docker-compose, env-vars, arr-integration, documentation]
dependency_graph:
  requires: []
  provides: [full-arr-env-var-surface-documented]
  affects: [docker-compose.yml, .env.example]
tech_stack:
  added: []
  patterns: [env-override-path, config-yaml-path]
key_files:
  created: []
  modified:
    - docker-compose.yml
    - .env.example
decisions:
  - "Combined both file edits into one commit — logically one doc change"
  - "docker compose config fails on TREZARR_LLM_API_KEY :? constraint (pre-existing, not introduced) — used Python yaml.safe_load as the YAML validity gate"
metrics:
  duration: "~5 min"
  completed: 2026-06-05
---

# Phase quick-260605-dur Plan 01: Document full *arr env-var surface Summary

Expanded docker-compose.yml and .env.example to surface all 12 *arr connection env vars (host/port/api_key/enabled x Sonarr/Radarr/Bazarr) with a clear ENABLED=true footgun warning, replacing the previous 3-key-only partial documentation.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Correct docker-compose.yml header comment + expand *arr env block | 0c5a677 | docker-compose.yml |
| 2 | Expand .env.example with full *arr vars + footgun warning | 0c5a677 | .env.example |

## Verification

```
grep -c 'TREZARR_SONARR_HOST\|TREZARR_RADARR_HOST\|TREZARR_BAZARR_HOST' docker-compose.yml
→ 3

grep -c 'TREZARR_SONARR_HOST\|TREZARR_RADARR_HOST\|TREZARR_BAZARR_HOST' .env.example
→ 3

grep 'ENABLED' docker-compose.yml  → footgun warning present (ENABLED flag section in header + 3 _ENABLED vars)
grep 'ENABLED' .env.example        → footgun warning present + 3 _ENABLED=true vars

YAML parse: python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" → PASSED
(docker compose config fails on pre-existing TREZARR_LLM_API_KEY :? constraint — not introduced by this change)
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. This is a documentation-only change.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundaries introduced. .env.example API key entries remain blank placeholders (T-dur-01: accepted).

## Self-Check: PASSED

- docker-compose.yml modified: FOUND
- .env.example modified: FOUND
- Commit 0c5a677 exists: CONFIRMED
- All 12 *arr vars present in both files: CONFIRMED
- All new entries commented out: CONFIRMED
- No Python source files modified: CONFIRMED
