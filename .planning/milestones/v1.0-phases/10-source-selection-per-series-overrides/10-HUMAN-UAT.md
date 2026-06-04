---
status: passed
phase: 10-source-selection-per-series-overrides
source: [10-04-PLAN.md checkpoint:human-verify]
started: 2026-06-02
updated: 2026-06-02
---

## Current Test

User approved the Overrides tab walkthrough on 2026-06-02. All 13 verification items confirmed passed.

## Tests

### 1. Overrides tab appears
expected: The "Overrides" tab renders as the fifth tab after "Register" in the BibleEditor for any series.
result: passed (approved by user)

### 2. Three sections render
expected: Clicking "Overrides" shows three sections — Source Language Preference, Model Override, Register.
result: passed (approved by user)

### 3. Add a valid source-language chip
expected: Typing "ko" + Enter in the source add-input creates a "ko" chip with an × remove button.
result: passed (approved by user)

### 4. Invalid code rejected inline
expected: Typing "xx" shows the inline error "Must be a 2-letter ISO-639-1 code (e.g. ko, zh, en)".
result: passed (approved by user)

### 5. Append a second chip in order
expected: Typing "en" + Enter appends "en" after "ko" (order preserved).
result: passed (approved by user)

### 6. Save Overrides
expected: "Save Overrides" shows "Saving…" then a success toast "Overrides saved."
result: passed (approved by user)

### 7. Source override persists across refresh
expected: After refresh + returning to the same series Overrides tab, the ko/en chips persist.
result: passed (approved by user)

### 8. Clear source override → inherit
expected: "Clear source override" clears the chips and the provenance badge shows "Inherited from global config: {codes}".
result: passed (approved by user)

### 9. Model override persists
expected: Typing a model id (e.g. "gpt-4o-mini") + Save shows a toast and persists across refresh; provenance badge toggles inherited↔override.
result: passed (approved by user)

### 10. Register save is independent (D-111)
expected: Editing register in the Overrides tab goes through PATCH /api/bible/series/{id}/register (its own "Save Register" control) — the "Save Overrides" button must NOT trigger any /register call. Confirm via server logs.
result: passed (approved by user)

### 11. Save Overrides payload excludes register
expected: Server log for "Save Overrides" shows PATCH /api/bible/series/{id}/overrides with only source_lang_override + model_override (no register field).
result: passed (approved by user)

### 12. Live Bazarr inventory read (INTG-02)
expected: With a real Bazarr instance configured + enabled, a discovery scan reads existing source-language subtitle inventory per item (never downloading).
result: passed (approved by user)

### 13. Relationally-richer source selected (SRC-02)
expected: For a series with both ko and en source subs (East-Asian original), server logs show the ko source selected over en; graceful fallback when the preferred source is absent (SRC-01).
result: passed (approved by user)

## Summary

total: 13
passed: 13
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
