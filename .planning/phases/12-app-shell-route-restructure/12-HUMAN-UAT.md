---
status: partial
phase: 12-app-shell-route-restructure
source: [12-VERIFICATION.md]
started: 2026-06-04
updated: 2026-06-04
---

## Current Test

[awaiting human testing — deferred to Phase 16 live smoke test]

## Tests

### 1. Active accent bar visual rendering
expected: The active nav item shows a visible purple left accent bar (`border-sidebar-primary`) in the `.dark` scope; inactive items show a transparent border.
result: [pending]

### 2. Sidebar collapse to icon rail + cookie persistence
expected: Cmd/Ctrl+B collapses the sidebar to the icon rail; the `sidebar_state` cookie persists the collapsed/expanded state across a full page reload.
result: [pending]

### 3. SPA deep-link hard navigation
expected: Typing `/series/1` directly in the address bar (hard navigation) loads SeriesDetail via the FastAPI SPAStaticFiles fallback rather than returning a 404.
result: [pending]

### 4. Legacy /library inside new shell
expected: The legacy `/library` route renders Library.tsx without runtime errors inside the new `SidebarProvider` shell context (Library.tsx is deleted in Phase 14, but must not crash before then).
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
