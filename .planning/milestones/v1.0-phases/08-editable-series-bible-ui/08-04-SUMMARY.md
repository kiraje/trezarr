---
phase: 08-editable-series-bible-ui
plan: "04"
subsystem: ui
tags: [react, vite, typescript, series-bible, lock, pronouns, address-map, terms, register]

# Dependency graph
requires:
  - phase: 08-03
    provides: REST API for all Bible entity types (characters, address-map, terms, register), /api/pronouns endpoint with KINSHIP_RECIPROCAL, /api/series/{id}/bible aggregate, field-history endpoint
provides:
  - Full React SPA layer for the Series Bible: /bible list page + /bible/:id editor with Characters/Address Map/Terms/Register tabs
  - LockBadge, LockToggleButton, PronounCombo, FieldHistoryPanel, ReciprocalSuggestionPanel reusable components
  - Bible API client types + wrappers (all CRUD + lock + history)
  - BIBLE-08 criterion 1 UI surface (view + edit + provenance visible for all four entity types)
affects:
  - Phase 09 (ASS/SSA) — no dependency; Phase 08 parallel track
  - Phase 10 (source selection) — no dependency

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PronounCombo: select-first combo with __custom__ escape hatch (D-86 typo guard)"
    - "FieldHistoryPanel: inline expansion below table row, not a modal (UI-SPEC note 9)"
    - "ReciprocalSuggestionPanel: auto-suggested via KINSHIP_RECIPROCAL; confirm fires two PATCH calls in sequence"
    - "LockBadge uses STATUS_CONFIG palette from StatusBadge (locked=done colors, inference=queued colors)"
    - "D-87 client-side hard-block: LockToggleButton disabled + aria-live error when term is empty"
    - "CR-02 alias: SPA interfaces use register (not register_value); register_value never appears in TS interfaces"

key-files:
  created:
    - frontend/src/api/client.ts (bible section added)
    - frontend/src/pages/BibleList.tsx
    - frontend/src/pages/BibleEditor.tsx
    - frontend/src/components/LockBadge.tsx
    - frontend/src/components/LockToggleButton.tsx
    - frontend/src/components/PronounCombo.tsx
    - frontend/src/components/FieldHistoryPanel.tsx
    - frontend/src/components/ReciprocalSuggestionPanel.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/components/AppShell.tsx

key-decisions:
  - "CR-02: SPA uses register field alias (not register_value); locked_fields check also must not include register_value — auto-fixed in fix commit 29a66b8"
  - "Visual/interaction UAT (lock toggles, PronounCombo, ReciprocalSuggestionPanel, D-87 empty-term block, history drawer) was auto-approved under --auto/yolo mode; remains PENDING explicit human UAT in browser"

patterns-established:
  - "Bible components follow cancellation-guard useEffect pattern from Phase-07 Settings.tsx"
  - "PronounCombo is the standard pronoun input (not free-text) anywhere pronoun terms appear in the SPA"
  - "LockBadge + LockToggleButton are the canonical pair for any lockable field row"

requirements-completed:
  - BIBLE-08
  - BIBLE-09

# Metrics
duration: continuation (verify + summary)
completed: 2026-06-02
---

# Phase 8 Plan 04: Editable Series Bible UI Summary

**Full React SPA for the Series Bible: /bible list + /bible/:id editor with Characters/Address Map/Terms/Register tabs, LockBadge provenance, PronounCombo (API-sourced terms), inline FieldHistoryPanel, and ReciprocalSuggestionPanel — BIBLE-08 criterion 1 UI surface complete (visual UAT auto-approved, pending human walkthrough)**

## Performance

- **Duration:** Continuation finalization (prior auto tasks ~30 min)
- **Started:** 2026-06-02 (prior session)
- **Completed:** 2026-06-02
- **Tasks:** 4 auto tasks + 1 checkpoint (auto-approved)
- **Files modified:** 10

## Accomplishments

- Built complete Bible SPA surface: BibleList (/bible) + BibleEditor (/bible/:id) with all four tab sections fully implemented
- Delivered 5 new reusable components (LockBadge, LockToggleButton, PronounCombo, FieldHistoryPanel, ReciprocalSuggestionPanel) following Phase-07 AppShell/StatusBadge patterns
- Extended api/client.ts with Bible types and 11 async wrappers (getSeriesBible, patchCharacter, patchAddressMapPair, addTerm, deleteTerm, getPronouns, getFieldHistory, etc.)
- AppShell Bible NavItem activated (D-84: disabled prop removed); /bible pages show accent nav highlight
- D-85 reciprocal flow: confirms two PATCH calls (forward + reverse) with graceful toast when reverse pair not found
- D-86 PronounCombo: dropdown terms sourced from /api/pronouns (not hardcoded TypeScript); custom escape hatch available
- D-87 lock guard: LockToggleButton disabled + aria-live error when self_term or address_term is empty
- CR-02 alias correct in all TS interfaces (register field, not register_value); fix commit 29a66b8 removed a defensive locked_fields check that also referenced register_value

## Task Commits

1. **Task 1: Bible API client types + LockBadge/LockToggleButton/PronounCombo/FieldHistoryPanel/ReciprocalSuggestionPanel** - `d087d3c` (feat)
2. **Task 2a: BibleList + App.tsx routes + AppShell Bible nav enable** - `7cca14a` (feat)
3. **Task 2b+2c: BibleEditor — Characters/Address Map/Terms/Register sections** - `36bc509` (feat)
4. **Fix: CR-02 — remove register_value from locked_fields check** - `29a66b8` (fix)

**Plan metadata:** (this summary commit — see below)

## Files Created/Modified

- `frontend/src/api/client.ts` — Bible interfaces (SeriesListItem, CharacterDTO, AddressMapDTO, TermDTO, BibleEventDTO, SeriesBibleDTO, PronounsResponse) + 11 async wrappers
- `frontend/src/pages/BibleList.tsx` — Series list page: fetch-on-mount, table with Name/Characters/Terms/Register columns, row-click nav to /bible/:id, empty/error/loading states
- `frontend/src/pages/BibleEditor.tsx` — Full Bible editor: Characters/Address Map/Terms/Register tabs, inline row edit, save/discard/lock/unlock flows, toast feedback (73.9 KB)
- `frontend/src/components/LockBadge.tsx` — Locked/Inference provenance badge using StatusBadge palette
- `frontend/src/components/LockToggleButton.tsx` — 32x32 icon-only Lock/Unlock button with aria-label and disabled state
- `frontend/src/components/PronounCombo.tsx` — select-first combo with API-sourced terms + custom escape hatch
- `frontend/src/components/FieldHistoryPanel.tsx` — Inline history expansion panel (max-h 320px, not modal)
- `frontend/src/components/ReciprocalSuggestionPanel.tsx` — Inline reciprocal suggestion with KINSHIP_RECIPROCAL lookup; confirm/skip flow
- `frontend/src/App.tsx` — /bible and /bible/:seriesId routes added (placeholder replaced)
- `frontend/src/components/AppShell.tsx` — disabled prop removed from Bible NavItem

## Decisions Made

- **CR-02 alias enforcement:** A defensive `register_value` string appeared in the locked_fields lookup inside BibleEditor — auto-fixed in commit 29a66b8 since CR-02 mandates the SPA field alias is `register` (not `register_value`) throughout
- **Visual UAT auto-approved:** The checkpoint:human-verify was auto-approved under --auto/yolo mode. The visual/interaction walkthrough (see "Pending Human UAT" section below) remains PENDING explicit human UAT

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CR-02: register_value in locked_fields check removed (fix commit)**
- **Found during:** Task 2b/2c (BibleEditor implementation)
- **Issue:** The BibleEditor's locked_fields derivation included `"register_value"` in a defensive check. CR-02 mandates the SPA uses `register` (the alias), not `register_value`. Having `register_value` in the locked_fields predicate caused the Register LockBadge to never show "Locked" state even when the field was locked on the server.
- **Fix:** Removed `register_value` from the locked_fields check; the correct key is the ORM alias `register` used in the SeriesListItem interface
- **Files modified:** `frontend/src/pages/BibleEditor.tsx`
- **Verification:** `grep -c "register_value" frontend/src/pages/BibleEditor.tsx` returns 0; `npm run build` clean
- **Committed in:** `29a66b8` (fix(08-04))

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Essential correctness fix. No scope creep.

## Checkpoint: Auto-Approved Visual UAT

The plan's `checkpoint:human-verify` (Task 5) was auto-approved under `--auto/yolo` mode. The checkpoint requires a browser walkthrough that is **PENDING explicit human UAT**.

### Pending Human UAT Items (browser walkthrough)

The following verification steps from the plan were not executed by a human and should be confirmed before closing BIBLE-08 criterion 1:

1. Navigate to `http://localhost:6868/bible` — confirm "Series Bible" heading + Bible NavItem active (accent color, not grayed)
2. Confirm empty state "No series in Bible" + helper body text when no series exist (not blank/error page)
3. With a seeded series:
   a. Click series row → `/bible/:id` opens with Characters tab active; "← Bible" breadcrumb visible
   b. BibleTabBar: Characters / Address Map / Terms / Register tabs — each switches sections on click
   c. Characters tab: Name/Gender/Age/Role columns + LockBadge "Inference" + Clock icon; no Delete icon on character rows
   d. Edit a character → inputs appear; change Gender; click "Save character" → toast "Changes saved." + row exits edit mode
   e. LockToggleButton → LockBadge changes to "Locked" + toast "Field locked."
   f. Clock icon → FieldHistoryPanel expands inline below row (not modal); history entry with "lock" source badge visible; click again → collapses
   g. Address Map tab: Speaker/Addressee/Self term/Address term columns; PronounCombo-style view; LockBadge + rel-event count badge
   h. Edit an address pair → PronounCombo dropdowns populated from API (not static TS); change both terms → ReciprocalSuggestionPanel appears below row
   i. Clear address_term → LockToggleButton disabled (opacity-50) + "Both terms must be non-empty before locking a pair." error visible (D-87)
   j. Fill both terms → Lock succeeds; toast "Pair saved."
   k. Terms tab: Source term/Vietnamese rendering/Category/LockBadge/History/Delete columns; case-sensitivity note below heading; Delete → inline confirm "Delete this term? [Delete term] [Keep term]"; "Keep term" → no action (safety)
   l. Register tab: SectionCard with "Register value" TextField, LockBadge, LockToggleButton, "Save Register" button; "This value may be overwritten…" note when not locked
4. Navigate away and back to `/bible/:id` → data reloads correctly
5. `/bible` page: Bible NavItem highlighted (accent border-b) in sidebar

### Verification Commands (already re-confirmed in this session)

```
npm run build  →  0 errors (1654 modules, 295.61 kB JS, 13.44 kB CSS)
uv run pytest -q  →  290 passed, 1 skipped, 1 xpassed
```

## Known Stubs

None — all four tabs (Characters, Address Map, Terms, Register) are fully implemented. The Address Map and Terms tabs were stubbed during Task 2b and replaced with full implementations in Task 2c. No stub divs, TODO comments, or placeholder text remain in BibleEditor.tsx.

## Threat Flags

No new trust boundaries introduced beyond what the plan's threat model already registered (T-08-08 through T-08-SC). No new network endpoints, auth paths, or schema changes added by this plan — all calls route through the existing /api/series/{id}/* REST surface established in Phase 08-03.

## Issues Encountered

None beyond the CR-02 auto-fix documented above.

## User Setup Required

None — no external service configuration required. The UI runs on the same port as the existing Trezarr service (6868).

## Next Phase Readiness

- BIBLE-08 criterion 1 UI surface is complete (view + edit + provenance for all four entity types); visual UAT in browser is the remaining gate before criterion 1 is formally closed
- Phase 09 (ASS/SSA) and Phase 10 (source selection) are independent of Phase 08's completion; no blocking dependencies
- The human-override valve (lock/unlock via UI) is fully wired end-to-end: browser LockToggleButton → PATCH /api/series/{id}/* → store writer → locked_fields column → returned DTO → LockBadge update without page reload

---
*Phase: 08-editable-series-bible-ui*
*Completed: 2026-06-02*
