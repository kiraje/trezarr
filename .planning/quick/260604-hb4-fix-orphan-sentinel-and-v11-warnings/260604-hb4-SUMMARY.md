---
quick_id: 260604-hb4
slug: fix-orphan-sentinel-and-v11-warnings
status: complete
date: 2026-06-04
commits: 730f062, 30d6b6b
---

# Summary — Orphan-sentinel + v1.1 warnings W1/W2/W3

## Orphan-sentinel (v1.0 #5) — `730f062`
`reinsert_sentinels` now strips hallucinated orphan `<<TN>>` tokens (those not in
`sentinel_map`) instead of letting them quarantine the whole file. Orphans are computed and
stripped BEFORE reinsertion — a codec-fidelity-guardian review caught that a post-strip would
delete a real tag VALUE containing a `<<TN>>`-shaped substring (TAG_RE over-matches a literal
`<<T1000>>` from source); the before-reinsert ordering avoids that. A LOST REAL sentinel still
returns `integrity_ok=False` (quarantine). Engine Pass-3 and Pass-4 now always call reinsert
(dropped the `if smap:` guard) so untagged cues get stripped. Specialist review: **PASS** after
the BLOCKER fix.

## W1 — `30d6b6b`
`GET /api/library` returns a positive `services: {sonarr,radarr,bazarr}` map (from
`settings.*_enabled`). `getSeriesLiveBadge`/`getMoviesLiveBadge` now require `services.<svc> ===
true` AND no error — a disabled service is no longer a false-positive LIVE.

## W2 — `30d6b6b`
`SeriesEpisodesResponse.series_title` typed `string | null` (backend always emits the key,
value nullable) instead of optional `string?`.

## W3 — `30d6b6b`
Shared `BazarrClient._fetch_inventory_data` tries the bracketed `seriesid[]`/`radarrid[]` form
then falls back to the plain key when the bracketed form returns empty. Fallback fires only on
empty (no extra request for an item with subtitles). Host-only redaction, D-105 path mapping,
and INTG-02 read-only preserved; malformed-JSON body now wrapped as `BazarrError`.
arr-integration-specialist review: **PASS**.

## Verification
- Full suite: **387 passed, 1 skipped, 3 xfailed, 52 xpassed**. Frontend `tsc -b && vite build`: green.
- New tests: sentinel orphan-strip / real-coexist / lost-real / source-lookalike; library `services` flags; Bazarr episode+movie fallback + no-fallback.
- Two specialist reviews (codec-fidelity-guardian, arr-integration-specialist): PASS.

## Files
- `trezarr/translate/sentinel.py`, `trezarr/translate/engine.py`
- `trezarr/arr/bazarr.py`, `trezarr/web/routes/library.py`
- `frontend/src/api/client.ts`, `frontend/src/contexts/LibraryContext.tsx`
- tests: `tests/translate/test_sentinel.py`, `tests/arr/test_bazarr.py`, `tests/web/test_library_api.py`
