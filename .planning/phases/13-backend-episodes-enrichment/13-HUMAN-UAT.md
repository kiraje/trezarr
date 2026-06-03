---
status: partial
phase: 13-backend-episodes-enrichment
source: [13-VERIFICATION.md, 13-REVIEW.md]
started: 2026-06-04
updated: 2026-06-04
---

## Current Test

[awaiting human testing — deferred to Phase 16 live smoke test]

## Tests

### 1. Live Bazarr subtitle inventory param format
expected: Against the live Bazarr at 192.168.5.42, `GET /api/library/series/{id}/episodes` returns non-empty `subtitles[]` for episodes that actually have subtitles in Bazarr. The code uses the bracketed `seriesid[]` query param (see `trezarr/arr/bazarr.py:305`, `TODO(phase-16)` in `library.py`). If the live Bazarr ignores `seriesid[]` and expects plain `seriesid`, `bazarr_available=true` but all `subtitles[]` come back empty — verify which form the live instance honors and adjust if needed. No runtime fallback is implemented (documented).
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
