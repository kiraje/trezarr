---
status: pending
phase: 07-web-ui-service-hardening
plan: 07-05
source: [07-05-PLAN.md Task 4 — checkpoint:human-verify]
auto_deferred: true
deferred_reason: "Auto-mode run — no browser available for visual verification; deferred to human UAT"
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
