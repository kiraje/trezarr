---
status: pending
phase: 07-web-ui-service-hardening
plan: 07-05, 07-06
source:
  - "07-05-PLAN.md Task 4 — checkpoint:human-verify (visual UI-SPEC conformance)"
  - "07-06-PLAN.md Task 2 — checkpoint:human-verify (Docker build + PUID/PGID ownership)"
auto_deferred: true
deferred_reason: "Auto-mode run — no Docker daemon + no browser available; deferred to human UAT"
started: 2026-06-02
updated: 2026-06-02
---

## Context

Task 4 of Plan 07-05 is a `checkpoint:human-verify` gate for visual UI-SPEC conformance.
This was auto-deferred (autonomous run with no interactive browser) and recorded here per
the auto_mode_checkpoint_handling directive.

To start the service for verification:
1. `cd frontend && npm run build` (builds SPA to trezarr/web/static/)
2. `uv run trezarr serve` (starts service on port 6868)
3. Open http://localhost:6868 in a browser

## Tests

### 1. Default route redirects to Queue
expected: Open http://localhost:6868 — browser redirects to /queue; shows "Queue" heading with Trezarr wordmark in the TopBar; sidebar shows Settings / Queue (active) / History / Bible (muted) nav items.
result: [pending]

### 2. Settings page renders correctly
expected: Navigate to /settings — 6 connection sections visible (LLM Endpoint, Sonarr, Radarr, Bazarr, Path Mappings, Service Settings); API key fields render as password inputs with "set" chip if previously configured; Save button present per section (disabled when no unsaved changes); Test Connection button present for Sonarr/Radarr/Bazarr/LLM sections.
result: [pending]

### 3. Queue page renders with correct column headers
expected: Navigate to /queue — page heading "Queue" with item count; JobTable renders with column headers: Series, Episode, File, Status, Queued, Logs; if no jobs: empty state text "No jobs in queue" with body "Trezarr will enqueue episodes automatically when a source subtitle is found with no Vietnamese output." ; last-updated timestamp visible.
result: [pending]

### 4. History page renders with correct column headers and Retry action
expected: Navigate to /history — page heading "History" with item count; JobTable renders with column headers: Series, Episode, File, Status, Finished, Reason, Actions; if no history: empty state text "No history yet" / "Completed and failed jobs will appear here."; if failed/quarantined rows exist: Retry button renders inline (not in a modal), clicking shows "Re-queue this item? [Re-queue] [Cancel]" inline confirmation.
result: [pending]

### 5. Per-job Logs navigation and LogViewer
expected: If a job exists in history, click its Logs icon (FileText icon in Actions column) — navigates to /jobs/{id}/logs; page shows "← History" breadcrumb; job summary strip (source_path, StatusBadge, trigger); LogViewer renders log entries with timestamp HH:MM:SS prefix and colored level prefixes ([INFO], [ERROR], etc.); empty state "No log entries recorded for this job." if no logs.
result: [pending]

### 6. API calls return 200 in DevTools
expected: Open browser DevTools → Network tab; navigate between pages — confirm API calls to /api/queue, /api/jobs, /api/settings all return 200 (not 404 or 500). Confirm /api/health also returns 200.
result: [pending]

## Design Token Verification

The following UI-SPEC.md §Color tokens should be visually apparent:
- [ ] Dark background (#0f1117 base, #1a1d27 surface for sidebar/topbar/cards)
- [ ] Alternating table rows (every other row slightly lighter, #1e2130)
- [ ] Accent color (#3b82f6 blue) on active nav item left border and Save/Test buttons
- [ ] Status badge colors: Queued=slate, Running=blue, Done=green, Failed=red, Quarantined=orange
- [ ] Text hierarchy: headings 18px semibold, body 14px regular, muted 12px regular

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps

---

## Wave 6 — Plan 07-06: Docker packaging (Task 2 checkpoint:human-verify)

Source: 07-06-PLAN.md Task 2 (auto-deferred — Docker daemon unavailable in autonomous run)

### Prerequisites

Build the image locally:
```
cd /path/to/trezarr
docker build -t trezarr:dev .
```

### 7. Docker build succeeds
expected: `docker build -t trezarr:dev .` exits 0; image is created successfully with no errors.
Both stages must complete: Node 20-slim compiles the SPA (npm ci + npm run build); Python 3.12-slim installs uv + syncs deps + copies static assets.
result: [pending]

### 8. trezarr serve command is reachable inside image
expected:
```
docker run --rm trezarr:dev trezarr --help
```
Exits 0 and output includes "serve" as a subcommand.
result: [pending]

### 9. Container starts and health endpoint responds
expected:
```
mkdir -p /tmp/trezarr-config
docker run -d --name trezarr-smoke \
  -p 6868:6868 \
  -v /tmp/trezarr-config:/config \
  -e PUID=$(id -u) -e PGID=$(id -g) \
  -e TREZARR_LLM_API_KEY=test-key \
  trezarr:dev
sleep 8
curl -s http://localhost:6868/api/health
docker rm -f trezarr-smoke
```
Expected: `{"status":"ok"}` returned from health endpoint. Docker logs should show lifespan startup sequence (scheduler started, worker started).
result: [pending]

### 10. SPA loads inside container
expected: While trezarr-smoke container is running (from test 9), open http://localhost:6868 in a browser.
The Trezarr React SPA should load: wordmark in TopBar, sidebar with Settings/Queue/History, redirects to /queue.
result: [pending]

### 11. PUID/PGID ownership is correct in /config volume
expected: After running test 9, inspect the host-side config directory:
```
ls -la /tmp/trezarr-config/
```
Files written by the container (trezarr.db, config.yaml if created) should be owned by your UID:GID (matching PUID=$(id -u) PGID=$(id -g)), NOT root.
result: [pending]

### 12. docker-compose.example.yml is valid
expected:
```
docker compose -f docker-compose.example.yml config
```
(This validates the compose file syntax and interpolates env vars.)
If TREZARR_LLM_API_KEY is not set in the shell, expect a "required variable TREZARR_LLM_API_KEY is not set" error (expected — the compose file uses `:?` for required keys). Otherwise exits 0.
result: [pending]

## Wave 6 Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

