---
phase: 14-new-library-pages-nav-badge-wiring
verified: 2026-06-04T00:00:00Z
status: human_needed
score: 13/13 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open /series in the running UI; confirm the series table renders rows, the progress bar is visually correct (bg-muted container, bg-primary fill), and clicking a row navigates to /series/:id"
    expected: "Table visible with progress bars; row click navigates to detail page"
    why_human: "Visual rendering of CSS classes and client-side navigation cannot be confirmed by static grep"
  - test: "Open /series in the running UI; type in the search box and confirm results filter after ~250ms debounce; change filter dropdown to 'Needs VI' and sort to 'Progress'; confirm results update"
    expected: "Search, filter, and sort all update the table client-side with no full page reload"
    why_human: "Debounce timing and reactive state behavior require a live browser"
  - test: "Open /movies in the running UI; confirm the SOURCE badge (amber) appears for movies with a source subtitle, the progress bar renders, and the Translate button is disabled with tooltip 'Source path unavailable' on hover"
    expected: "Amber SOURCE badge visible; Translate button disabled; tooltip text correct on hover"
    why_human: "Badge color rendering and tooltip hover behavior require a browser"
  - test: "Open /series/:id for a real series (e.g. the one in the live Sonarr instance); confirm the season Accordion renders with the latest season auto-expanded, audio badges (blue, Volume2 icon) and subtitle badges (amber/purple dot) visible per episode row, and the subtitle column is absent when Bazarr is unavailable"
    expected: "Accordion seasons present; latest expanded; badges colored correctly; subtitle column suppressed if Bazarr down"
    why_human: "Accordion expand/collapse, badge color rendering, and Bazarr-availability suppression are visual/runtime behaviors"
  - test: "On /series/:id, click 'Translate' on an eligible episode (has_file=true, source_path present, status=has_source); confirm navigation to /queue occurs and job appears in the queue"
    expected: "POST /api/translate enqueues the episode; page navigates to /queue; job visible in queue list"
    why_human: "Network request and page navigation require a live browser; job enqueue needs a live backend"
  - test: "On /series/:id, click 'Translate season' on a season with eligible episodes; confirm all eligible episodes are enqueued sequentially and the page navigates to /queue"
    expected: "Multiple POST /api/translate calls fire for eligible episodes; page navigates to /queue after all"
    why_human: "Sequential batch enqueue behavior and navigation require a live browser + backend"
  - test: "Open the sidebar; confirm the Series and Movies nav rows show LIVE badge (emerald) and count badge (purple, count > 0) after navigating to /series or /movies; confirm badges hide when sidebar is collapsed to icon rail"
    expected: "LIVE and count badges visible in expanded sidebar; both disappear in icon-rail mode (Cmd+B)"
    why_human: "Badge auto-hide on sidebar collapse requires live browser interaction; CSS group-data selector cannot be verified statically"
  - test: "Navigate to /nonexistent (or /library) in the running UI; confirm 'Page not found' heading and 'Go to Series' button are rendered; click the button and confirm navigation to /series"
    expected: "NotFound page renders; button navigates to /series"
    why_human: "Client-side routing catch-all behavior and button navigation require a browser"
---

# Phase 14: New Library Pages + Nav Badge Wiring Verification Report

**Phase Goal:** The Series list, Series detail (season-grouped Accordion with audio and subtitle-language badges, translate actions, search/filter/sort), and Movies list pages are built and fully functional; the sidebar count and LIVE badges are wired to live API data; Library.tsx is deleted.
**Verified:** 2026-06-04T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | client.ts exports SeriesItem, MovieItem (with translated_count/total_count), SeriesEpisodesResponse, SeasonGroup, EpisodeEnrichedRow, SubtitleEntry — matching Phase-13 library.py shapes | VERIFIED | `frontend/src/api/client.ts` lines 473–549: all six interfaces present with correct field names; `getLibrary()` returns `LibraryResponse`, `getSeriesEpisodes()` returns `SeriesEpisodesResponse` |
| 2 | getLibrary() returns LibraryResponse; getSeriesEpisodes(id) returns SeriesEpisodesResponse; postTranslate() signature unchanged | VERIFIED | `client.ts` lines 566–592: wrappers use `fetchWithLongTimeout`; `postTranslate(kind, arrSeriesId, sourcePath)` present at line 580 |
| 3 | LibraryContext exports LibraryProvider, useLibraryContext, and four derived helpers (getSeriesLiveBadge, getMoviesLiveBadge, getSeriesNeedsViCount, getMoviesNeedsViCount) | VERIFIED | `frontend/src/contexts/LibraryContext.tsx` lines 36–100: all six exports confirmed with correct derivation logic matching D-09/D-10 rules |
| 4 | LibraryProvider wraps App.tsx router so sidebar and pages share the context | VERIFIED | `frontend/src/App.tsx` lines 39, 43–64: `<LibraryProvider>` wraps `<BrowserRouter>` |
| 5 | app-sidebar.tsx: SidebarMenu wrapped in SidebarGroup (WR-01); LIVE badge (emerald) and count badge (purple hsl token) for /series and /movies rows; both hidden via group-data-[collapsible=icon]:hidden | VERIFIED | `frontend/src/components/app-sidebar.tsx` lines 92–143: `SidebarGroup` wraps `SidebarMenu`; LIVE badge uses `bg-emerald-600`; count badge uses `bg-[hsl(var(--primary))]`; both have `group-data-[collapsible=icon]:hidden` |
| 6 | app-sidebar.tsx reads counts and LIVE state from useLibraryContext() — no additional fetch | VERIFIED | `app-sidebar.tsx` lines 70–74: `const { libraryData } = useLibraryContext()` followed by four derived values from context helpers |
| 7 | NotFound.tsx exists with "Page not found" heading and "Go to Series" button; App.tsx has Route path="*" as last child of layout route | VERIFIED | `frontend/src/pages/NotFound.tsx` lines 12–19: heading and button present; `App.tsx` line 60: `<Route path="*" element={<NotFound />} />` is last child |
| 8 | Series.tsx is a real list page: fetches getLibrary(), calls setLibraryData(), renders table with progress bars, row→/series/:id navigation, 250ms-debounced search, filter dropdown, sort buttons, all error/loading/empty states | VERIFIED | `frontend/src/pages/Series.tsx`: 324 lines; `setLibraryData(result)` at line 82; `ProgressBar` component at lines 37–55; `navigate('/series/' + s.id)` at line 299; `timerRef`/`setTimeout` debounce at lines 96–102; filter/sort derived at lines 156–185; Skeleton loading, error, Sonarr-down, empty states all present |
| 9 | Movies.tsx is a real list page: fetches getLibrary(), calls setLibraryData(), renders table with amber SOURCE badge, progress bars, disabled Translate button with tooltip, search/filter/sort, all error/loading/empty states | VERIFIED | `frontend/src/pages/Movies.tsx`: 419 lines; `setLibraryData(result)` at line 96; SOURCE badge at lines 356–362; Translate button disabled with `TooltipContent>Source path unavailable` at lines 383–401; debounce at lines 110–116 |
| 10 | SubtitleBadge.tsx: audio=blue (bg-blue-700/80), source=amber (bg-amber-600/80), vi=purple CSS token (bg-[hsl(var(--primary))]/80); Volume2 icon for audio, dot for source/vi; aria-label per type; no raw hex | VERIFIED | `frontend/src/components/SubtitleBadge.tsx` lines 53–57: COLOR_CLASSES map uses only Tailwind/CSS-var tokens; Volume2 at line 97; dot at lines 100–103; aria-label construction at lines 78–91; no raw hex colors in file |
| 11 | SeriesDetail.tsx: season Accordion (type=multiple); Season 0 last; latest non-zero season auto-expanded via defaultValue; bazarr_available=false suppresses subtitle column entirely; SubtitleBadge used for audio and subtitle rows; Translate episode + season buttons; useParams guard after all hooks | VERIFIED | `frontend/src/pages/SeriesDetail.tsx`: Accordion at line 365; sort with Season 0 last at lines 220–225; defaultValue from latestSeason at lines 229–233; subtitle column conditional at lines 63–65 and 97–118; SubtitleBadge imports at line 35; translate handlers at lines 236–268; guard at lines 212–217 |
| 12 | Library.tsx is DELETED; no Library import and no path="library" route in App.tsx | VERIFIED | `test ! -f frontend/src/pages/Library.tsx` → DELETED; `grep "import.*Library\b" App.tsx` → only LibraryProvider import (context); `grep 'path="library"' App.tsx` → no match |
| 13 | No @deprecated types (EpisodeRow, LibrarySeriesItem, LibraryMovieItem, old LibraryResponse) remain in client.ts | VERIFIED | `grep "LibrarySeriesItem\|LibraryMovieItem\|EpisodeRow\|@deprecated" client.ts` → no output; only new Phase-13 types present |

**Score:** 13/13 truths verified

### Build Gate

| Command | Result | Status |
|---------|--------|--------|
| `cd frontend && npm run build` | tsc -b clean + vite build: 1754 modules, no errors, output to trezarr/web/static/ | PASS |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/api/client.ts` | Phase-13 types + fetch wrappers | VERIFIED | SeriesItem, MovieItem, LibraryResponse, SubtitleEntry, EpisodeEnrichedRow, SeasonGroup, SeriesEpisodesResponse all exported |
| `frontend/src/contexts/LibraryContext.tsx` | Shared library context + derived helpers | VERIFIED | LibraryProvider, useLibraryContext, four derived helpers exported |
| `frontend/src/components/app-sidebar.tsx` | SidebarGroup + LIVE/count badges from LibraryContext | VERIFIED | SidebarGroup wrapper present; both badge types with correct color tokens |
| `frontend/src/pages/NotFound.tsx` | 404 page with correct copy and button | VERIFIED | "Page not found" heading, "Go to Series" button |
| `frontend/src/pages/Series.tsx` | Real list page (not stub) | VERIFIED | 324-line real implementation |
| `frontend/src/pages/Movies.tsx` | Real list page (not stub) | VERIFIED | 419-line real implementation |
| `frontend/src/components/SubtitleBadge.tsx` | Audio/subtitle badges with aria + CSS tokens | VERIFIED | Correct color tokens, shape cues, aria-labels |
| `frontend/src/pages/SeriesDetail.tsx` | Season Accordion + episode table + translate | VERIFIED | Full implementation with all required behaviors |
| `frontend/src/App.tsx` | LibraryProvider wrapper + catch-all route + no /library | VERIFIED | Provider wraps BrowserRouter; Route path="*" last; no Library import |
| `frontend/src/pages/Library.tsx` | DELETED | VERIFIED | File does not exist |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| client.ts | trezarr/web/routes/library.py | TS interfaces mirror Python shapes | VERIFIED | SeriesEpisodesResponse, SeasonGroup, EpisodeEnrichedRow field names match API spec |
| LibraryContext.tsx | client.ts | imports LibraryResponse | VERIFIED | `import type { LibraryResponse } from "../api/client"` at line 22 |
| app-sidebar.tsx | LibraryContext.tsx | useLibraryContext() + four helpers | VERIFIED | All five imports confirmed at lines 47–52 |
| Series.tsx | /api/library | getLibrary() | VERIFIED | `getLibrary()` called at load(); return value passed to `setData()` and `setLibraryData()` |
| Series.tsx | LibraryContext.tsx | setLibraryData after fetch | VERIFIED | `setLibraryData(result)` at line 82 |
| Movies.tsx | /api/library | getLibrary() | VERIFIED | Same pattern as Series.tsx |
| Movies.tsx | /api/translate | postTranslate() | VERIFIED | `postTranslate("movie", null, "")` in handleTranslate |
| SeriesDetail.tsx | /api/library/series/:id/episodes | getSeriesEpisodes(id) | VERIFIED | `getSeriesEpisodes(numericId)` in useEffect |
| SeriesDetail.tsx | SubtitleBadge.tsx | SubtitleBadge renders audio + subtitle rows | VERIFIED | `import { SubtitleBadge }` at line 35; used in EpisodeTable for both audio and subtitle tracks |
| SeriesDetail.tsx | /api/translate | postTranslate('series', source_path, arr_series_id) | VERIFIED | `postTranslate("series", numericId, episode.source_path)` in handlers |
| App.tsx | NotFound.tsx | Route path="*" catch-all | VERIFIED | Line 60; import at line 38 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| app-sidebar.tsx | 149 | `bg-[#22c55e]` raw hex on status dot | INFO | Pre-existing from Phase 12 (D-02 static status dot, not a nav badge); does not violate D-06 which governs badge color tokens; the Phase 14 LIVE/count badges use correct CSS-var tokens |

No TBD, FIXME, or XXX markers found in any phase-modified file. No stub patterns (return null, empty implementations, placeholder text) found.

### Requirements Coverage

| Requirement | Phase | Description | Status | Evidence |
|-------------|-------|-------------|--------|----------|
| LIB-01 | 14 | User can browse all Sonarr series on a Series list page | SATISFIED | Series.tsx: real table with fetch, rows, navigation |
| LIB-02 | 14 | User can browse all Radarr movies on a Movies list page | SATISFIED | Movies.tsx: real table with SOURCE badge, progress, Translate |
| LIB-03 | 14 | Series detail with episodes grouped by season in collapsible sections | SATISFIED | SeriesDetail.tsx: Accordion type=multiple, Season 0 last, latest auto-expanded |
| LIB-04 | 14 | Audio and subtitle badges with CODE2, :HI/:Forced, color-coded, shape+aria accessibility | SATISFIED | SubtitleBadge.tsx: Volume2 icon for audio, dot for subtitle, aria-label, CSS-var tokens |
| LIB-05 | 14 | Translate single episode or season from SeriesDetail | SATISFIED | SeriesDetail.tsx: handleTranslateEpisode + handleTranslateSeason → postTranslate → navigate('/queue') |
| LIB-06 | 14 | Search, filter by subtitle status, sort Series and Movies lists | SATISFIED | Both pages: 250ms-debounced search, 4-option filter dropdown, two sort buttons |
| LIB-07 | 14 | Translation-progress indicator on Series and Movies list items | SATISFIED | ProgressBar component in both pages: bg-muted container, bg-primary fill, translated/total label |
| NAV-03 | 14 | Count badge (auto-hide at zero) and LIVE badge on nav rows | SATISFIED | app-sidebar.tsx: both badges wired to LibraryContext; auto-hide at count=0; LIVE from getSeriesLiveBadge/getMoviesLiveBadge |

All 8 required IDs (LIB-01 through LIB-07, NAV-03) are covered. No orphaned requirements.

### Behavioral Spot-Checks

Step 7b: SKIPPED for live-browser checks (require running server). The build gate (npm run build exits 0) is the available static spot-check; it passed.

### Probe Execution

Step 7c: No `probe-*.sh` files declared in any PLAN and no scripts/*/tests/ directory for this phase. SKIPPED.

### Human Verification Required

8 items require human testing in a running browser against the live deployment. These align with Phase 16's planned smoke test (RSK-03). All statically disprovable checks were VERIFIED above; no items here represent a failure — they are genuine UI/runtime behaviors.

#### 1. Series list visual + navigation

**Test:** Open `/series` in the running UI; confirm the table renders rows, the progress bar is visually correct (filled bar proportional to progress), and clicking a row navigates to `/series/:id`.
**Expected:** Table visible with progress bars; row click navigates to detail page.
**Why human:** Visual rendering of CSS classes and client-side navigation cannot be confirmed by static analysis.

#### 2. Series list search/filter/sort

**Test:** Type in the search box; confirm results filter after ~250ms debounce. Change filter to "Needs VI" and sort to "Progress"; confirm results update.
**Expected:** Search, filter, and sort update the table client-side with no full page reload.
**Why human:** Debounce timing and reactive state behavior require a live browser.

#### 3. Movies list SOURCE badge + disabled Translate tooltip

**Test:** Open `/movies`; confirm amber SOURCE badge for movies with source subtitles; hover the Translate button and confirm tooltip "Source path unavailable".
**Expected:** Amber badge visible; tooltip text correct on hover.
**Why human:** Badge color rendering and tooltip hover require a browser.

#### 4. SeriesDetail Accordion + badges + bazarr suppression

**Test:** Open `/series/:id` for a real series; confirm latest season is auto-expanded, audio badges (blue, Volume2 icon) and subtitle badges (amber dot / purple dot) visible per row; subtitle column absent if Bazarr unavailable.
**Expected:** Accordion seasons present; latest expanded; badges colored correctly; subtitle column suppressed if Bazarr down.
**Why human:** Accordion expand/collapse, badge rendering, and Bazarr-availability suppression are visual/runtime behaviors.

#### 5. Translate episode

**Test:** On `/series/:id`, click "Translate" on an eligible episode; confirm navigation to `/queue` and job appears.
**Expected:** POST /api/translate fires; page navigates to /queue; job visible.
**Why human:** Network request and page navigation require a live browser and backend.

#### 6. Translate season

**Test:** On `/series/:id`, click "Translate season"; confirm multiple episodes enqueued sequentially and page navigates to /queue.
**Expected:** Sequential POST calls for eligible episodes; navigation to /queue.
**Why human:** Sequential batch and navigation require live browser + backend.

#### 7. Sidebar badges with collapse behavior

**Test:** After loading `/series`, confirm the sidebar shows LIVE (emerald) and count (purple) badges for the Series row; collapse sidebar (Cmd/Ctrl+B) and confirm badges disappear.
**Expected:** Badges visible in expanded mode; disappear in icon-rail mode.
**Why human:** CSS `group-data-[collapsible=icon]:hidden` selector behavior requires browser interaction.

#### 8. NotFound catch-all routing

**Test:** Navigate to `/nonexistent` (or `/library`) in the running UI; confirm "Page not found" renders; click "Go to Series" and confirm navigation.
**Expected:** NotFound page renders; button navigates to /series.
**Why human:** Client-side routing catch-all requires a browser.

### Gaps Summary

No gaps. All 13 must-haves are VERIFIED. The `status: human_needed` is driven solely by the 8 browser-testable behaviors above — all of which are scheduled to be covered by Phase 16's live smoke test (RSK-03).

---

_Verified: 2026-06-04T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
