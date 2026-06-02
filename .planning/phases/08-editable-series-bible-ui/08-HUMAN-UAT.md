---
status: partial
phase: 08-editable-series-bible-ui
source: [08-VERIFICATION.md]
started: 2026-06-02
updated: 2026-06-02
---

## Current Test

[awaiting human testing — SPA browser walkthrough for BIBLE-08 criterion 1]

## Tests

### 1. Full Series Bible UI walkthrough (BIBLE-08 criterion 1)

Run Trezarr and open `http://localhost:6868` (e.g. `uv run uvicorn trezarr.web.app:create_app --factory --port 6868`).

expected: all 10 steps produce the described visual/interaction behavior; LockBadge reflects locked-vs-inference provenance for all four entity types.
result: [pending]

1. Navigate to `/bible` — "Bible" NavItem in sidebar is active (accent color); empty state "No series in Bible" when empty.
2. Seeded series: click row → `/bible/:id` opens with Characters tab active; "← Bible" breadcrumb visible.
3. BibleTabBar: Characters / Address Map / Terms / Register — each tab switches sections.
4. Characters tab: Name/Gender/Age/Role + LockBadge "Inference" + Clock icon; edit a field → change Gender → "Save character" → toast "Changes saved." + row exits edit mode.
5. LockToggleButton → LockBadge → "Locked" + toast "Field locked." (no page reload).
6. Clock icon → FieldHistoryPanel expands inline below the row (not a modal); history entry with source badge; click again → collapses.
7. Address Map tab: edit a pair → PronounCombo dropdowns populated from `/api/pronouns` (not a static TS list); change both terms → ReciprocalSuggestionPanel appears.
8. Clear address_term → LockToggleButton disabled (opacity-50) + inline error "Both terms must be non-empty before locking a pair." (D-87).
9. Terms tab: Delete → inline confirm "Delete this term? [Delete term] [Keep term]"; "Keep term" → no action.
10. Register tab: SectionCard with LockBadge + "Save Register"; locking persists across page reload.

**Why human:** SPA rendering, CSS states, toast display, inline-vs-modal behavior, and API-populated dropdowns are not programmatically verifiable without a running browser. This was auto-approved under `--auto/yolo` and is explicitly pending human UAT.

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

_(none blocking — all automated checks passed; this is visual/interaction confirmation only)_

**Known cosmetic (non-blocking, WR-02):** `FieldHistoryPanel` still declares an unused `onClose` prop (3 call sites pass it; the component ignores it). Build passes; no functional impact. The `08-REVIEW-FIX.md` frontmatter inaccurately counts this as fixed — it was not. Safe to clean up opportunistically.
