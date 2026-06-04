---
phase: 14-new-library-pages-nav-badge-wiring
reviewed: 2026-06-04T00:00:00Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - frontend/src/api/client.ts
  - frontend/src/contexts/LibraryContext.tsx
  - frontend/src/components/app-sidebar.tsx
  - frontend/src/components/SubtitleBadge.tsx
  - frontend/src/pages/Series.tsx
  - frontend/src/pages/Movies.tsx
  - frontend/src/pages/SeriesDetail.tsx
  - frontend/src/pages/NotFound.tsx
  - frontend/src/App.tsx
findings:
  critical: 0
  warning: 8
  info: 1
  total: 9
status: issues_found
---

# Phase 14: Code Review Report

**Reviewed:** 2026-06-04
**Depth:** deep
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 14 delivers the Series list page, Movies list page, SeriesDetail accordion, SubtitleBadge component, LibraryContext for sidebar badge wiring, NotFound page, and Library.tsx deletion. The overall structure is sound: hooks rules are followed in SeriesDetail (guard placed after all hooks), the LibraryContext sharing strategy is correct, and the Phase-13 API envelope is consumed correctly. The `tsc -b && vite build` build passes.

Eight warnings are found. None are blockers. The most impactful are two fetch effects in Series.tsx and Movies.tsx that lack abort/cancellation cleanup, which can cause stale `setLibraryData` calls after navigation; a floating-promise Retry handler in SeriesDetail that bypasses the existing `cancelled` guard; duplicate-key risk when an episode's audio track list contains repeat language codes; and a block of dead code in the Movies `handleTranslate` handler that posts an empty string as `source_path`. Several palette-color hardcodes violate the project's D-06 CSS-variable-only token convention. One info finding flags a misleading filter label.

No security issues were found. The `seriesId` param is parsed with `parseInt` + `isNaN` before any API call; no URL/pathname is reflected into the DOM; navigate targets are hardcoded literals.

---

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: Series.tsx and Movies.tsx fetch effects return no cleanup — stale `setLibraryData` after navigation

**File:** `frontend/src/pages/Series.tsx:90-92`, `frontend/src/pages/Movies.tsx:104-106`

**Issue:** Both pages wrap their fetch in a `useCallback` (`load`) and call it from a `useEffect` with no cleanup function:

```tsx
// Series.tsx:90
useEffect(() => {
  void load();
}, [load]);
```

If the user navigates away while the 30-second `fetchWithLongTimeout` is in-flight, the promise settles on the unmounted component. React 18 silently ignores `setData`/`setError`/`setLoading` calls on unmounted components, but `setLibraryData(result)` is a _context setter_ — it updates the global `LibraryProvider` state, which is not unmounted. This means the context can be written with data from a stale or wrong fetch (e.g., the Movies page overwrites context with its own response mid-navigation to an unrelated page).

In practice, since both pages call the same `getLibrary()` endpoint, the race is mostly harmless today. However, if the endpoints ever diverge or if rapid navigation is added, this pattern will silently corrupt the sidebar badge counts.

**Fix:** Add a `cancelled` flag in the effect (matching the SeriesDetail pattern) and guard `setLibraryData`:

```tsx
// Series.tsx
useEffect(() => {
  let cancelled = false;
  async function run() {
    setLoading(true);
    setError(null);
    try {
      const result = await getLibrary();
      if (cancelled) return;
      setData(result);
      setLibraryData(result);
    } catch (err) {
      if (cancelled) return;
      setError(String(err));
    } finally {
      if (!cancelled) setLoading(false);
    }
  }
  void run();
  return () => { cancelled = true; };
}, []); // load no longer needed as dep; setLibraryData is stable
```

Apply the same pattern to `Movies.tsx`.

---

### WR-02: SeriesDetail inline Retry handler is a floating promise with no mount guard

**File:** `frontend/src/pages/SeriesDetail.tsx:307-323`

**Issue:** The Retry button's `onClick` uses `.then()/.catch()` on a raw `getSeriesEpisodes` call with no cancellation guard:

```tsx
onClick={() => {
  setError(null);
  setLoading(true);
  getSeriesEpisodes(numericId)
    .then((result) => {
      setData(result);      // no mount guard
      setLoading(false);
    })
    .catch((err: unknown) => {
      setError(msg);        // no mount guard
      setLoading(false);
    });
}}
```

If the user clicks Retry and then immediately clicks "Back to Series", the in-flight promise settles and calls `setState` on the unmounted `SeriesDetail`. The `useEffect` fetch guard uses a `cancelled` closure variable, but the inline Retry handler bypasses that pattern entirely.

**Fix:** Extract the retry logic into a reusable function that uses the same `cancelled` pattern, or use a `useRef<boolean>` mount flag:

```tsx
// At component level:
const mountedRef = React.useRef(true);
useEffect(() => () => { mountedRef.current = false; }, []);

// In retry onClick:
onClick={async () => {
  setError(null);
  setLoading(true);
  try {
    const result = await getSeriesEpisodes(numericId);
    if (!mountedRef.current) return;
    setData(result);
    setLoading(false);
  } catch (err: unknown) {
    if (!mountedRef.current) return;
    const msg = String(err);
    if (msg.includes(" 400")) setErrorStatus(400);
    else if (msg.includes(" 502")) setErrorStatus(502);
    setError(msg);
    setLoading(false);
  }
}}
```

---

### WR-03: Duplicate `key` prop when `audio_languages` contains repeated language codes

**File:** `frontend/src/pages/SeriesDetail.tsx:90-92`

**Issue:** Audio badges are rendered with `key={lang}` where `lang` is the ISO-639-1 code string:

```tsx
{episode.audio_languages.map((lang) => (
  <SubtitleBadge key={lang} code2={lang} type="audio" />
))}
```

If the backend returns a duplicate code (e.g., `["ko", "en", "ko"]` for a dual-channel audio track), React will emit a "duplicate key" warning and may render the list incorrectly (two tracks with `key="ko"` — only one reconciled).

**Fix:** Use the array index as a secondary key discriminator:

```tsx
{episode.audio_languages.map((lang, idx) => (
  <SubtitleBadge key={`${lang}-${idx}`} code2={lang} type="audio" />
))}
```

This matches the pattern already used correctly for the subtitle list at line 107: `` key={`${sub.code2}-${idx}`} ``.

---

### WR-04: `errorStatus === 502` is tracked in state but never used in the render path

**File:** `frontend/src/pages/SeriesDetail.tsx:171, 198, 319`

**Issue:** `errorStatus` is set to `502` in both the `useEffect` catch block (line 198) and the Retry handler (line 319), but the render logic only branches on `errorStatus === 400`:

```tsx
if (errorStatus === 400) {
  return <div>Sonarr is disabled…</div>;
}
// Falls through to generic error for 502 or any other status
```

The 502 case (Sonarr/Bazarr gateway error) shows the identical generic error UI as a timeout or unknown error. Users get no actionable distinction. The state variable is written but its value is never read, making the 502-tracking code dead.

**Fix:** Either add a distinct 502 error UI or remove the `502` branch from the error-status detection to keep the code honest:

```tsx
// Option A: add a 502 branch
if (errorStatus === 502) {
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Sonarr gateway error (502)</h1>
      <p className="text-muted-foreground">
        Sonarr returned a bad gateway. It may be restarting.
      </p>
      …
    </div>
  );
}

// Option B: remove dead tracking (simpler)
// Delete: else if (msg.includes(" 502")) setErrorStatus(502);
// Delete: else if (msg.includes(" 502")) setErrorStatus(502); (in retry handler)
```

---

### WR-05: `handleTranslateSeason` always navigates to `/queue` even when all enqueues fail silently

**File:** `frontend/src/pages/SeriesDetail.tsx:256-269`

**Issue:** The season-level translate loop catches individual errors and continues to the next episode, then unconditionally calls `navigate("/queue")` after the loop:

```tsx
async function handleTranslateSeason(season: SeasonGroup) {
  const eligible = season.episodes.filter(/* … */);
  for (const ep of eligible) {
    try {
      await postTranslate("series", numericId, ep.source_path!);
    } catch {
      // Continue to next episode — user sees results in Queue
    }
  }
  navigate("/queue"); // always fires, even if eligible.length=0 or all failed
}
```

If `eligible` is empty (which cannot currently happen because the button is hidden when `hasEligible=false`, but is possible if the button visibility and filter logic drift) or if every single `postTranslate` call throws, the user is navigated to `/queue` where nothing new appears. There is no feedback that all enqueues failed.

This also means the per-episode `translateErrors` state accumulated for individual-episode failures is never shown in the season-translate path — errors are silently swallowed.

**Fix:** Count successes and only navigate if at least one succeeded, or surface failures:

```tsx
async function handleTranslateSeason(season: SeasonGroup) {
  const eligible = season.episodes.filter(
    (e) => e.has_file && e.source_path !== null && e.status !== "translated",
  );
  let enqueued = 0;
  const failures: string[] = [];
  for (const ep of eligible) {
    if (!ep.source_path) continue;
    try {
      await postTranslate("series", numericId, ep.source_path);
      enqueued++;
    } catch {
      failures.push(ep.episode_key);
    }
  }
  if (enqueued > 0) {
    navigate("/queue");
  } else {
    setTranslateErrors(
      Object.fromEntries(failures.map((k) => [k, "Could not enqueue."])),
    );
  }
}
```

---

### WR-06: Raw hex color `bg-[#22c55e]` in sidebar footer violates D-06 CSS-variable-only rule

**File:** `frontend/src/components/app-sidebar.tsx:149`

**Issue:** The running-status dot uses a literal hex value:

```tsx
<span className="h-2 w-2 rounded-full bg-[#22c55e]" … />
```

D-06 specifies that colors must be expressed exclusively via CSS variable tokens. `#22c55e` is the Tailwind `emerald-500` palette value — it will not adapt to theming or dark-mode overrides.

**Fix:**

```tsx
<span className="h-2 w-2 rounded-full bg-emerald-500" … />
```

Or, if a CSS-var is preferred for theme consistency:

```tsx
<span className="h-2 w-2 rounded-full bg-[hsl(var(--success,142_71%_45%))]" … />
```

---

### WR-07: Multiple palette-color hardcodes across Phase 14 files violate D-06

**Files:**
- `frontend/src/components/SubtitleBadge.tsx:54-55`
- `frontend/src/components/app-sidebar.tsx:119`
- `frontend/src/pages/Movies.tsx:357, 373`
- `frontend/src/pages/SeriesDetail.tsx:125`

**Issue:** The following Tailwind palette classes are used directly instead of CSS-variable tokens (D-06: "colors expressed ONLY as CSS variable tokens + Tailwind utility classes; never raw hex"):

| File | Line | Class |
|------|------|-------|
| SubtitleBadge.tsx | 54 | `bg-blue-700/80` |
| SubtitleBadge.tsx | 55 | `bg-amber-600/80` |
| app-sidebar.tsx | 119 | `bg-emerald-600` |
| Movies.tsx | 357 | `bg-amber-600/80` |
| Movies.tsx | 373 | `bg-emerald-600/80` |
| SeriesDetail.tsx | 125 | `bg-emerald-600/80` |

These classes will not respond to theme customization and create an implicit coupling to specific palette shades. The `vi` badge correctly uses `bg-[hsl(var(--primary))]/80` as a model.

**Fix:** Define CSS variables for the semantic roles used, e.g. in `index.css`:

```css
--color-audio:    220 70% 50%;   /* blue */
--color-source:   25 90% 45%;    /* amber */
--color-success:  142 71% 45%;   /* emerald */
```

Then replace palette classes with:

```tsx
audio:   "bg-[hsl(var(--color-audio))]/80 text-white border-transparent",
source:  "bg-[hsl(var(--color-source))]/80 text-white border-transparent",
// success badge
"bg-[hsl(var(--color-success))]/80 text-white border-transparent"
```

---

### WR-08: `Movies.handleTranslate` posts an empty `source_path` — dead but incorrect code path

**File:** `frontend/src/pages/Movies.tsx:120-140`

**Issue:** `handleTranslate` is defined and wired to the Translate button's `onClick`, but the button is `disabled={true}` and the function posts `source_path: ""`:

```tsx
async function handleTranslate(movie: MovieItem) {
  // source_path not in API response — disabled with tooltip per 14-UI-SPEC.md.
  // This handler only fires if the API is updated to return source_path in the future.
  …
  await postTranslate("movie", null, "");  // empty source_path: always wrong
  …
}
```

The comment claims this is future-proof, but posting an empty string to `POST /api/translate` will produce a server-side validation error (empty `source_path`) or trigger a filesystem lookup with an empty path. The handler as written is not a valid stub — it would silently enqueue a broken job if the button were ever enabled. The button also carries both `disabled={true}` and `onClick` simultaneously, which is unconventional (though `disabled` prevents the click event from firing).

**Fix:** Remove `handleTranslate` and its `onClick` entirely while the button is disabled. When `source_path` becomes available in the API, add the handler then with the real value:

```tsx
// Remove: async function handleTranslate(movie: MovieItem) { … }
// Remove: import postTranslate from api/client (if only used here)

// Button becomes:
<Button size="sm" disabled className="min-h-[44px]">
  Translate
</Button>
```

Also remove `translatePending` and `translateErrors` state from `Movies` since they are only used in the dead handler.

---

## Info

### IN-01: "No source" filter label is semantically misleading in both Series and Movies pages

**Files:** `frontend/src/pages/Series.tsx:169-171`, `frontend/src/pages/Movies.tsx:207-209`

**Issue:** The "No source" filter matches items where `total_count === 0`:

```tsx
// Series.tsx:169
} else if (filterStatus === "no_source") {
  filtered = filtered.filter((s) => s.total_count === 0);
}
```

`total_count` for series is `episodeFileCount` from Sonarr statistics — the number of episode video files, not the number of source subtitles. An item with `total_count === 0` has no video files at all, which is a different concept from "has no source subtitle." The filter label suggests "no source subtitle found" to users, but it actually means "no episode files downloaded."

**Fix:** Rename the filter option to "No files" or "No video files" in both the `filterLabel` map and the `DropdownMenuItem` text, and update the `FilterStatus` type value accordingly:

```tsx
type FilterStatus = "all" | "needs_vi" | "translated" | "no_files";

const filterLabel: Record<FilterStatus, string> = {
  all: "All",
  needs_vi: "Needs VI",
  translated: "Translated",
  no_files: "No files",
};
```

---

_Reviewed: 2026-06-04_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
