# Phase 14: New Library Pages + Nav Badge Wiring - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** auto (decisions auto-selected from locked research/requirements; no user prompts)

<domain>
## Phase Boundary

Build the three new library pages on the Phase-12 shell, consuming the Phase-13
enriched API: a **Series list**, a **Series detail** (season-grouped Accordion
with audio + subtitle-language badges, translate actions), and a **Movies list** —
with search/filter/sort on the lists, per-item translation-progress indicators, and
the sidebar **count + LIVE** badges (NAV-03) wired to live API data. `Library.tsx`
and the transitional `/library` route are deleted once Series/Movies are functional.

**In scope (LIB-01..07, NAV-03):**
- NEW `frontend/src/pages/Series.tsx` (replaces the series view of Library.tsx) — LIB-01, LIB-06, LIB-07
- NEW `frontend/src/pages/SeriesDetail.tsx` (season Accordion, badges, translate) — LIB-03, LIB-04, LIB-05
- NEW `frontend/src/pages/Movies.tsx` — LIB-02, LIB-06, LIB-07
- `frontend/src/api/client.ts` — consume the P13 `SeriesEpisodesResponse` + list `translated_count`/`total_count`; add the new fetch wrappers/types; remove the old `EpisodeRow` after Library.tsx deletion
- `frontend/src/components/app-sidebar.tsx` (from P12) — wire the right-side count badge + LIVE badge (NAV-03)
- DELETE `frontend/src/pages/Library.tsx` + remove the transitional `/library` route (P12 D-03 handoff) + its route in `App.tsx`
- Shared badge rendering (audio + subtitle) reused by SeriesDetail (and available to P15 reskin)

**Out of scope (later phases — do NOT touch):**
- Backend endpoint changes → done in Phase 13 (consume only; do not modify `library.py`)
- Reskinning the EXISTING pages (Queue/History/Settings/Bible/JobLogs) + bridge-token removal → Phase 15
- Docker rebuild + live smoke test → Phase 16
- The app shell / routes themselves → done in Phase 12 (Series/SeriesDetail/Movies stubs already exist and are replaced here)

</domain>

<decisions>
## Implementation Decisions

### Table & Layout
- **D-01:** Series and Movies lists use the **shadcn plain `<Table>`** (vendored
  Phase 11), NOT the jolly-ui Table beta. Phase 11 deferred the "jolly-ui Table
  beta stability evaluation (with shadcn plain Table fallback)" to this phase;
  given the blind-trust quality bar, default to the stable shadcn Table and
  implement sorting in component state. jolly-ui Table is installed and MAY be
  adopted only if a concrete React-Aria affordance (e.g. resizable/sortable
  columns) proves clearly better — otherwise do not introduce beta risk.
- **D-02:** Dense table rows (not cards) for both lists. Each row: title, year,
  a `translated/total` progress indicator (LIB-07), and (Series) a row click →
  `navigate('/series/:id')`; (Movies) source-sub + vi status + Translate.

### Data Fetching
- **D-03:** Keep the existing **raw `fetch` + useState/useEffect** pattern —
  `research/ARCHITECTURE.md §5` explicitly rejects React Query/SWR for v1.1.
  Series/Movies lists ← `GET /api/library` (now carrying `translated_count`/
  `total_count` from P13). Series detail ← `GET /api/library/series/:id/episodes`
  (the P13 `SeriesEpisodesResponse` envelope). Reuse `fetchWithLongTimeout` for
  the *arr-backed calls.

### Search / Filter / Sort (LIB-06)
- **D-04:** **Client-side, in-memory** over the fetched list (consistent with the
  no-query-lib decision). Search = case-insensitive title substring (debounced).
  Filter by subtitle status (e.g. All / Needs Vietnamese / Fully translated /
  No source). Sort by title (default) and by translation progress. Applies to the
  Series and Movies LISTS; the Series detail uses the season Accordion (no list
  search there).

### Series Detail (LIB-03)
- **D-05:** shadcn **Accordion** grouped by `season_number`; the **latest season
  auto-expanded** (highest season with episodes; Season 0 "Specials" rendered
  last). Episodes with `has_file=false` render greyed with no Translate button.
  When the P13 envelope has `bazarr_available=false`, **suppress the subtitle-badge
  column** and show a small "Bazarr unavailable" note rather than all-empty badges.

### Badges (LIB-04)
- **D-06:** Subtitle badge = `CODE2` **uppercase** with `:HI` / `:Forced`
  markers; color-coded **amber = source / purple = Vietnamese (VI)**; audio badge =
  **blue**. Built on the shadcn `<Badge>` primitive with token-based colors
  (NOT raw hex). Source = amber; VI = purple — per the Phase-11 UI-SPEC accent reservations.
- **D-07 (accessibility — LIB-04, mandatory):** badges carry a **non-color
  distinction**: a shape/icon cue (e.g. a leading dot/outline-vs-filled or a small
  icon) PLUS a descriptive `aria-label` (e.g. "Vietnamese subtitle, hearing
  impaired"). Color is never the sole signal.

### Translate Actions (LIB-05)
- **D-08:** A **Translate** button on each eligible episode row (present only when
  `has_file=true` and a source sub exists) AND a **Translate season** action on the
  season header (enqueues every eligible episode in that season). Both call
  `POST /api/translate` with the episode's `source_path`; after enqueue, **navigate
  to `/queue`** (roadmap SC3). Absent for episodes with no file.

### Nav Badges (NAV-03)
- **D-09:** Wire the sidebar (P12 `app-sidebar.tsx`) **count badge** on the Series
  and Movies rows = number of items "needing a Vietnamese subtitle", **auto-hidden
  at zero**. Cheap proxy from the list endpoint: an item needs vi when
  `translated_count < total_count`; the Series-row count = number of such series,
  Movies-row = number of such movies. (Documented approximation — it can't see
  per-episode "has source but no vi" without the detail endpoint; acceptable for a
  nav indicator.)
- **D-10:** **LIVE** badge on a nav row when its backing *arr is connected. Derive
  from the `GET /api/library` response: Sonarr LIVE = `sonarr_enabled` AND no
  `errors[]` entry with `source=="sonarr"`; Radarr LIVE = same for radarr. Uses
  existing data — no new health endpoint.

### Library.tsx Removal
- **D-11:** Once `Series.tsx` + `Movies.tsx` are functional and verified, **delete
  `Library.tsx`**, remove the transitional `/library` route from `App.tsx` (added
  in P12 D-03), and remove the now-dead `EpisodeRow` type from `client.ts`. This
  completes the P12→P14 route-split handoff (NAV-02).

### Claude's Discretion
- Exact table column set + sort-field list; debounce interval; the precise badge
  shape cue (dot vs icon vs outline/filled); empty/loading (Skeleton)/error state
  copy; "Translate season" confirmation UX; whether the Movies row navigates
  anywhere (no movie-detail page is in scope).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 Research & inherited contracts
- `.planning/research/ARCHITECTURE.md` §3 (badge rendering rules, season Accordion,
  bazarr_available suppression), §5 (data-fetching: raw fetch, NO React Query;
  `EpisodeEnrichedRow`/`SeriesEpisodesResponse` types), §7 Phase D (build order:
  SeriesDetail navigates via useNavigate, episode URL bookmarkable).
- `.planning/phases/13-backend-episodes-enrichment/13-CONTEXT.md` + `13-RESEARCH.md`
  — the API contract this phase consumes (envelope shape, `bazarr_available`,
  `translated_count`/`total_count`, badge fields code2/code3/hi/forced).
- `.planning/phases/12-app-shell-route-restructure/12-CONTEXT.md` + `12-UI-SPEC.md`
  — the shell + `app-sidebar.tsx` where NAV-03 badges wire in; stub pages to replace.
- `.planning/phases/11-shadcn-foundation-purple-theme/11-UI-SPEC.md` — badge color
  contract (amber=source / purple=VI; uppercase 2-char ISO; accent reservations),
  installed primitives (Badge, Accordion, Collapsible, Tooltip, Skeleton, Table).

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — LIB-01..LIB-07, NAV-03 (count badge auto-hidden at
  zero + LIVE badge; badge accessibility shape+aria-label).
- `.planning/ROADMAP.md` §"Phase 14" — goal + 5 success criteria (dense Series table
  w/ progress bar; season Accordion w/ badges + auto-expand + bazarr suppression;
  Translate enqueue→Queue; Movies; search/filter/sort + sidebar count/LIVE badges).

### Existing code baseline
- `frontend/src/pages/Library.tsx` — current combined series/movies/drill-in view
  being SPLIT and DELETED here (source of the existing list/episode logic to port).
- `frontend/src/api/client.ts` — fetch wrappers + types (`fetchWithLongTimeout`);
  add new types, remove `EpisodeRow` after deletion.
- `frontend/src/components/app-sidebar.tsx` (P12) — NAV_ITEMS rows to augment with
  count + LIVE badges.
- `frontend/src/pages/Queue.tsx` — the enqueue→navigate('/queue') target + an analog
  for table/badge usage.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- All needed primitives installed Phase 11: `Badge`, `Accordion`, `Collapsible`,
  `Tooltip`, `Skeleton`, `Table` (shadcn) + jolly-ui `Table` (beta, fallback-only).
- `Library.tsx` already implements series listing + episode drill-in against the
  OLD flat endpoint — port its logic to Series/SeriesDetail/Movies against the new
  P13 envelope, then delete it.
- `POST /api/translate` + the Queue page already exist (Phase 7) — Translate just
  enqueues and navigates.

### Established Patterns
- Raw `fetch` + `useState`/`useEffect` per page; `fetchWithLongTimeout` (30s) for
  *arr-backed endpoints; typed TS interfaces in `client.ts`. Keep this — no new lib.
- Strict TS (`noUnusedLocals`/`noUnusedParameters`); build = `tsc -b && vite build`
  (the automated gate — no frontend test harness exists, per P12 research).
- Active-nav + sidebar composition already built in P12 `app-sidebar.tsx`; NAV-03 is
  additive (badge slots on existing rows).

### Integration Points
- Series row click → `navigate('/series/:id')` → SeriesDetail reads `useParams()`
  `seriesId` (stub already wired in P12).
- Nav count/LIVE badges read the same `GET /api/library` payload the Series/Movies
  lists fetch — compute once, or fetch in the sidebar; keep it cheap.

</code_context>

<specifics>
## Specific Ideas

- Badge accessibility (D-07) is a hard LIB-04 requirement, not polish — never ship
  color-only badges; always pair with shape/icon + aria-label.
- The nav count badge is a proxy (`translated_count < total_count`); document the
  approximation so it isn't mistaken for an exact "episodes with source-but-no-vi".
- Reuse the badge renderer between SeriesDetail (P14) and the future reskin (P15) so
  the amber/purple/blue system is defined once.

</specifics>

<deferred>
## Deferred Ideas

- A dedicated Movie detail page — not in scope (Movies list shows status + Translate
  inline); only add if a future requirement asks.
- jolly-ui Table adoption — only if shadcn Table sort UX proves insufficient
  (Claude's discretion, not a separate phase).
- Reskinning the existing pages + removing bridge tokens → Phase 15.

None outside the roadmapped phases — discussion stayed within phase scope.

</deferred>

---

*Phase: 14-new-library-pages-nav-badge-wiring*
*Context gathered: 2026-06-04 (auto mode)*
