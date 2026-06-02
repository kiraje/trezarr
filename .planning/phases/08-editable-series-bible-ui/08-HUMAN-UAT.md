---
status: passed
phase: 08-editable-series-bible-ui
source: [08-VERIFICATION.md]
started: 2026-06-02
updated: 2026-06-02
verified_by: agent-driven browser walkthrough (Playwright MCP) against the live full stack
---

## Current Test

Complete — all 10 walkthrough steps verified in a real browser against the live FastAPI + SQLite + SPA stack (a seeded series: 3 characters, 3 directed address pairs, 2 terms).

## Tests

### 1. Full Series Bible UI walkthrough (BIBLE-08 criterion 1)

expected: all 10 steps produce the described visual/interaction behavior; LockBadge reflects locked-vs-inference provenance for all four entity types.
result: **PASS** (1 bug found + fixed mid-walkthrough; 1 pre-existing caveat; details in Gaps)

1. `/bible` — Bible nav active (accent), "Series Bible" heading, series table. ✅
2. Click series row → `/bible/1`, Characters tab active, "← Bible" breadcrumb. ✅
3. Tabs (Characters / Address Map / Terms / Register) switch sections. ✅
4. Edit a character (Gender male→female) → "Save character" → row updates; **persisted to DB** (verified via API + survived a server restart). ✅
5. Lock toggle → LockBadge "Inference" → "Locked", button → "Unlock this field" (no reload). ✅
6. Clock icon → FieldHistoryPanel expands **inline** (not modal) with the full provenance timeline (inference → import edit → lock events, timestamps + source badges). ✅ *(required the fix below)*
7. Address Map: edit a pair → **PronounCombo dropdowns populated from `/api/pronouns`** (incl. bố/mẹ/thầy… + `custom…`); change a term → **ReciprocalSuggestionPanel** appears (pre-filled from kinship table, Confirm/Skip). ✅
8. Clear address term (via `custom…` → empty) → **LockToggleButton `disabled` + `role="alert"`: "Both terms must be non-empty before locking a pair."** (D-87); reciprocal panel switched to "No known reciprocal — set the reverse pair manually." ✅
9. Terms: Delete → inline confirm "Delete this term? [Delete term] [Keep term]"; "Keep term" → no deletion. ✅
10. Register: edit → "Save Register" → Lock → reloaded (`/` → Bible → row → Register) → **"intimate" + Locked persisted**; list also shows Register="intimate". ✅

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

**Found + FIXED during the walkthrough (commit `7aaf2ff`):**
- **History endpoint 500.** `GET /api/series/{id}/bible/{entity_type}/{entity_id}/history` returned HTTP 500 whenever real events existed: the handler used `model_dump(by_alias=True)`, leaving `BibleEventDTO.created_at` as a `datetime` that Starlette's `JSONResponse` cannot encode. The FieldHistoryPanel silently showed "No history" instead. Fixed with `model_dump(mode="json", by_alias=True)` + a regression test (`test_field_history_dto_is_json_serializable`). The prior `test_get_field_history` only hit the empty-DB branch, so it never exercised datetime serialization — that gap is now closed.

**Pre-existing caveat (not Phase-8-specific; not fixed):**
- **SPA deep-link / refresh 404.** Loading or refreshing a client-side route directly (e.g. `http://host:6868/bible`) returns FastAPI `{"detail":"Not Found"}` — there is no SPA history-fallback serving `index.html` for non-`/api` routes. All Phase-7 routes (`/queue`, `/history`, `/settings`) share this. In-app navigation works fine. Worth a follow-up (a catch-all `index.html` fallback in `app.py`), likely as its own small task since it affects the whole SPA, not just the Bible editor.

**Known cosmetic (WR-02, still not fixed):**
- `FieldHistoryPanel` declares an unused `onClose` prop (3 call sites pass it; component ignores it). No functional impact; the `08-REVIEW-FIX.md` frontmatter inaccurately counts it fixed.

_Verification was agent-driven (Playwright). A human glance is still welcome but not required — every step was confirmed against the live stack with DB-level persistence checks._
