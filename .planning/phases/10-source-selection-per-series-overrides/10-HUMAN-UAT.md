---
status: partial
phase: 10-source-selection-per-series-overrides
source: [10-04-PLAN.md checkpoint:human-verify]
started: 2026-06-02
updated: 2026-06-02
---

## Current Test

[awaiting human testing — Overrides tab end-to-end + live Bazarr source selection]

## Tests

### 1. Overrides tab appears
expected: The "Overrides" tab renders as the fifth tab after "Register" in the BibleEditor for any series.
result: [pending]

### 2. Three sections render
expected: Clicking "Overrides" shows three sections — Source Language Preference, Model Override, Register.
result: [pending]

### 3. Add a valid source-language chip
expected: Typing "ko" + Enter in the source add-input creates a "ko" chip with an × remove button.
result: [pending]

### 4. Invalid code rejected inline
expected: Typing "xx" shows the inline error "Must be a 2-letter ISO-639-1 code (e.g. ko, zh, en)".
result: [pending]

### 5. Append a second chip in order
expected: Typing "en" + Enter appends "en" after "ko" (order preserved).
result: [pending]

### 6. Save Overrides
expected: "Save Overrides" shows "Saving…" then a success toast "Overrides saved."
result: [pending]

### 7. Source override persists across refresh
expected: After refresh + returning to the same series Overrides tab, the ko/en chips persist.
result: [pending]

### 8. Clear source override → inherit
expected: "Clear source override" clears the chips and the provenance badge shows "Inherited from global config: {codes}".
result: [pending]

### 9. Model override persists
expected: Typing a model id (e.g. "gpt-4o-mini") + Save shows a toast and persists across refresh; provenance badge toggles inherited↔override.
result: [pending]

### 10. Register save is independent (D-111)
expected: Editing register in the Overrides tab goes through PATCH /api/bible/series/{id}/register (its own "Save Register" control) — the "Save Overrides" button must NOT trigger any /register call. Confirm via server logs.
result: [pending]

### 11. Save Overrides payload excludes register
expected: Server log for "Save Overrides" shows PATCH /api/bible/series/{id}/overrides with only source_lang_override + model_override (no register field).
result: [pending]

### 12. Live Bazarr inventory read (INTG-02)
expected: With a real Bazarr instance configured + enabled, a discovery scan reads existing source-language subtitle inventory per item (never downloading).
result: [pending]

### 13. Relationally-richer source selected (SRC-02)
expected: For a series with both ko and en source subs (East-Asian original), server logs show the ko source selected over en; graceful fallback when the preferred source is absent (SRC-01).
result: [pending]

## Summary

total: 13
passed: 0
issues: 0
pending: 13
skipped: 0
blocked: 0

## Gaps
