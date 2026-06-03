---
phase: 14
plan: 05
subsystem: frontend
tags: [subtitle-badge, series-detail, accordion, translate, react, typescript]
dependency_graph:
  requires: [14-01, 14-03]
  provides: [SubtitleBadge component, SeriesDetail page]
  affects: [frontend/src/components/SubtitleBadge.tsx, frontend/src/pages/SeriesDetail.tsx]
tech_stack:
  added: []
  patterns: [shadcn Accordion, shadcn Badge, SubtitleBadge custom component, season auto-expand]
key_files:
  created:
    - frontend/src/components/SubtitleBadge.tsx
  modified:
    - frontend/src/pages/SeriesDetail.tsx
decisions:
  - Volume2 lucide icon (size 10) for audio shape cue; filled dot (●) for source + vi (D-07)
  - useParams guard placed AFTER all hooks to comply with React rules-of-hooks (IN-01)
  - Inline EpisodeTable component inside SeriesDetail.tsx (no separate file — self-contained)
  - Season 0 sorted last via explicit sort comparator (not CSS, not API ordering assumption)
  - handleTranslateSeason iterates sequentially with for-of loop (not Promise.all) per D-08
metrics:
  duration: "2 minutes"
  completed: "2026-06-03"
  tasks: 2
  files: 2
---

# Phase 14 Plan 05: SubtitleBadge + SeriesDetail Summary

SubtitleBadge reusable component and full SeriesDetail page: season Accordion with audio/subtitle
language badges, bazarr_available suppression, per-episode and season Translate actions.

## What Was Built

### Task 1 — SubtitleBadge.tsx

New hand-written component at `frontend/src/components/SubtitleBadge.tsx` (NOT in `ui/` — vendor-only invariant).

- Three badge variants: `audio` (blue bg-blue-700/80 + Volume2 lucide icon), `source` (amber bg-amber-600/80 + filled dot), `vi` (purple bg-[hsl(var(--primary))]/80 + filled dot)
- Label construction: `code2.toUpperCase()` + optional `:HI` + optional `:Forced`
- Static LANG_NAMES map (ko, en, vi, zh, ja, fr, es, th, de, it, pt, ru, ar) → language names for aria-labels
- Shape cue: Volume2 icon for audio (non-color differentiation per D-07), filled dot for source/vi
- Tooltip wrapping each badge with the full aria-label text
- All color classes are CSS variable tokens only — no raw hex (D-06)

### Task 2 — SeriesDetail.tsx

Replaced the stub with the full implementation:

- `useParams<{ seriesId: string }>()` called unconditionally; guard (`!seriesId || isNaN(numericId)`) runs AFTER all hooks (IN-01 carry-forward)
- Season ordering: ascending by season_number; Season 0 always last; latest non-zero season auto-expanded via `defaultValue` array
- `bazarr_available === false` → Subtitles column header AND all subtitle `<td>` cells removed entirely — no empty column (D-05 critical SC)
- Episode rows: `opacity-50` when `has_file === false`; no badges, no Translate button
- `status === "translated"` → emerald Translated badge, no Translate button
- `status === "has_source"` with `source_path !== null` → Translate button
- Translate episode: calls `postTranslate("series", numericId, episode.source_path)` → `navigate("/queue")`; inline error text on failure
- Translate season: sequential `for-of` loop over eligible episodes (has_file + source_path + status !== "translated") → `navigate("/queue")`
- "Translate season" button absent when no eligible episodes in season
- Loading state: three Skeleton placeholders
- Error states: 400 (sonarr_disabled) → Go to Settings; 502/other → Retry + Back to Series
- Empty state: "No episodes found" message
- Bazarr error entries from `data.errors[]` shown as muted text below heading

## Verification

`cd frontend && npm run build` — EXIT 0

```
> tsc -b && vite build
vite v7.3.5 building client environment for production...
✓ 1755 modules transformed.
../trezarr/web/static/index.html                   0.88 kB │ gzip:   0.53 kB
../trezarr/web/static/assets/index-WX_1kEP0.css   44.03 kB │ gzip:   8.20 kB
../trezarr/web/static/assets/index-euf6ogKJ.js   484.76 kB │ gzip: 139.23 kB
✓ built in 1.11s
```

TypeScript strict mode: zero errors, no unused locals/parameters.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| 1 — SubtitleBadge component | 229f903 | frontend/src/components/SubtitleBadge.tsx |
| 2 — SeriesDetail page | dbf77ab | frontend/src/pages/SeriesDetail.tsx |

## Deviations from Plan

None — plan executed exactly as written.

The plan's IN-01 note explicitly described the correct hooks-first pattern; it was followed
verbatim (call all hooks unconditionally, guard AFTER hooks, not before).

## Known Stubs

None. All fields are wired to real API data. The series heading falls back to
`Series #{numericId}` because the episodes endpoint does not return a series title —
this is documented in the plan as an acceptable limitation per 14-UI-SPEC.md §Layout.

## Threat Flags

No new security surface beyond what the plan's threat model documented:
- T-14-05-01 mitigated: `parseInt + isNaN` guard before any API call; seriesId never in innerHTML
- T-14-05-02 mitigated: code2 rendered via JSX text node (React auto-escapes); toUpperCase() is safe
- T-14-05-03 accepted: source_path from API response, not user input

## Self-Check: PASSED

- FOUND: frontend/src/components/SubtitleBadge.tsx
- FOUND: frontend/src/pages/SeriesDetail.tsx
- FOUND: commit 229f903 (Task 1)
- FOUND: commit dbf77ab (Task 2)
- Build: EXIT 0 (tsc -b strict + vite build)
