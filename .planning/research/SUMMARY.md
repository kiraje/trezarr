# Project Research Summary

**Project:** Trezarr v1.1 — UI v2 (shadcn dashboard)
**Domain:** Self-hosted *arr-companion dashboard — big-bang shadcn/jolly-ui migration
**Researched:** 2026-06-03
**Confidence:** HIGH

---

## Executive Summary

Trezarr v1.1 is a full dashboard reskin onto shadcn/ui + jolly-ui, built atop an already-shipped React 19 / Tailwind v3.4 / Vite 7 / FastAPI stack. The migration adds no new backend translation features — it restructures the UI into a Bazarr-style sidebar shell, splits the `/library` monolith into `/series` + `/movies`, adds a season-grouped episode detail view with audio and subtitle-language badges, and reskins all existing pages in-place. The backend gains one enrichment: `GET /api/library/series/{id}/episodes` is rewritten to return episode records (not files) grouped by season, with audio languages from Sonarr mediaInfo and subtitle inventory from Bazarr, maintaining the existing fail-soft HTTP-200 contract.

The recommended approach is dependency-forced: Foundation first (path alias + shadcn@2.10.0 init + bridge theme + darkMode class), then the App Shell (SidebarProvider + layout route), then Backend enrichment (asyncio.to_thread + asyncio.gather + Bazarr fail-soft + server-side season grouping), then new Library pages (Series list, SeriesDetail accordion, Movies), then reskin-in-place of existing pages (Queue through BibleEditor), then Docker rebuild and live smoke test. Shell and Backend can run in parallel after Foundation. The BibleEditor is last and must be reskin-in-place only — never rebuild, because 5 critical locking bugs were found and fixed in prior phases and a rebuild risks reintroducing them.

The sharpest risk is the shadcn@2.x vs shadcn@4.x CLI version split: `shadcn@latest` (4.x) emits Tailwind v4 config that breaks the existing Tailwind v3.4 setup on first run. Every other risk — HSL channel-triple format, bridge-theme token collisions, dark mode wiring, Bazarr fail-soft, stale Docker image — has a clear prevention strategy. One open question remains: the exact purple HSL values for `--primary` / `--sidebar-primary` (visually tune in Phase 1 before any page work starts), and whether jolly-ui Table beta is stable enough (fall back to shadcn plain `<table>` if not).

---

## Key Findings

### Recommended Stack

The existing stack (React 19, Tailwind v3.4, Vite 7, lucide-react) is unchanged. Six new runtime packages are added: `class-variance-authority@^0.7.1`, `clsx@^2.1.1`, `tailwind-merge@^3.6.0`, `tailwindcss-animate@^1.0.7`, `react-aria-components@^1.18.0`, `sonner@^2.0.7`. One dev package: `@types/node@^22.x`. All Radix primitives are installed per-component by the shadcn CLI — do not pre-install them. jolly-ui has no npm package; it is a copy-paste registry at `https://jollyui.dev/r` consumed via the shadcn CLI registry feature.

**Critical version lock — the single most important stack constraint:**

`npx shadcn@2.10.0 init` — not `shadcn@latest`. The `latest` (4.x) CLI emits Tailwind v4 config (`@tailwindcss/vite`, `tw-animate-css`, OKLCH variables) which breaks the existing Tailwind v3.4 + PostCSS pipeline on first run. The `add` command (for individual components and jolly-ui via registry URL) can safely use `shadcn@latest` — only `init` must be pinned to `2.10.0`.

**Core technologies:**

| Package | Version | Purpose |
|---------|---------|---------|
| `shadcn@2.10.0` | 2.10.0 (CLI pin) | Component scaffolding; Tailwind v3 line |
| `class-variance-authority` | ^0.7.1 | CVA variant system used by all shadcn components |
| `clsx` + `tailwind-merge` | ^2.1.1 / ^3.6.0 | `cn()` utility — conditional + deduplicated class strings |
| `tailwindcss-animate` | ^1.0.7 | Tailwind v3 animation plugin; required for Accordion, Dialog, Sheet |
| `react-aria-components` | ^1.18.0 | jolly-ui primitive layer (Table, Disclosure); React 19 compatible |
| `sonner` | ^2.0.7 | Toast system; React 19 explicitly listed in peer deps |

**React 19 compatibility:** All `@radix-ui/*` packages have had full React 19 support since June 2024. `react-aria-components@1.18.0` runs correctly on React 19 stable despite the peer dep literal showing `^19.0.0-rc.1`. Add `legacy-peer-deps=true` to `.npmrc` before the first `npx shadcn@latest add` to prevent `ERESOLVE` from `cmdk` and `react-day-picker` — do not use `--force`.

**jolly-ui install pattern:**

```bash
# init: pinned to 2.x (Tailwind v3 line)
npx shadcn@2.10.0 init

# add shadcn components in bulk:
npx shadcn@2.10.0 add sidebar button badge card tabs accordion collapsible tooltip skeleton sonner dropdown-menu

# add jolly-ui Table via registry URL (shadcn@latest is fine for add-only):
REGISTRY_URL=https://jollyui.dev/r npx shadcn@latest add table
```

### Expected Features

The nav, badge system, and episode table structure are modeled on Bazarr source (read directly from github.com/morpheus65535/bazarr). The two-role badge color encoding (amber = source/input, purple = Vietnamese output) is Trezarr-specific with no Bazarr equivalent.

**Must have (table stakes):**

- Full-height sidebar with icon + label rows, right-side zero-hidden badge counts, left 2px purple active-accent bar
- Nav order: Series (Tv) → Movies (Film) → Queue (List) → History (History) → Bible (BookOpen) → Settings (Settings)
- Series list page: dense table with "X/Y translated" progress bar per series, clickable title drill-in
- Movies list page: dense table with per-movie Translate button (source-sub-gated)
- Season-grouped accordion on series detail: latest season auto-expanded, toggle-all button
- Episode table columns (fixed): Action · Ep# · Title · Audio badge (blue) · Subtitle badges
- Badge label format: ISO-639-1 UPPERCASE code2 + `:HI` or `:Forced` suffix directly appended (e.g. `VI:HI`, `ZH`, `KO`)
- Badge color semantics: blue = audio track, amber = source/foreign subtitle present, purple = VI present, dim outline = missing VI, muted gray = no source
- Badge WCAG 1.4.1 compliance: outline-vs-filled shape dimension for missing/present; `aria-label` on each badge
- Empty/loading/error states (mostly already implemented in Library.tsx — carry forward)
- Per-episode Translate button (already implemented — adapt to new column layout)
- BibleEditor: reskin-in-place only (all logic, state, and API calls unchanged)

**Should have (high value, implement in v1.1 if low friction):**

- Per-season "Translate All" action in season header row
- Episode air date column (low cost, from Sonarr episode records already fetched)
- Tooltip on badge with full human-readable label (accessibility + UX win)
- Animated dot or "LIVE" badge on Queue nav item when jobs are running
- Jump-to-latest-season anchor on series header for long multi-season series

**Explicitly out of scope (anti-features, do not build):**

- Poster/card grid view for list pages (wrong mental model for a translation monitoring tool)
- Hamburger/collapsible sidebar (single-user desktop dashboard; fixed-width always visible)
- Manual subtitle source selection per episode (configured in Settings/Bible)
- Bulk-select checkboxes (per-season Translate All covers the bulk use case)
- User-configurable column visibility
- Full-page loading overlays or error modals (use per-section spinners and inline amber banners)
- React Query / SWR (do not introduce a data-fetching library mid-milestone)

### Architecture Approach

The migration layers shadcn on the existing architecture at four seams: (1) Tailwind token system (hex to CSS variables, bridged simultaneously to avoid build breakage), (2) App shell (AppShell children prop to SidebarProvider + Outlet layout route), (3) route table (`/library` to `/series` + `/movies` + `/series/:id`), and (4) the episodes API response shape. No new backend infrastructure is added. The existing `SPAStaticFiles` deep-link fallback already handles the new extensionless routes — no backend routing changes needed.

**Key artifact changes:**

| Artifact | Status | Key Note |
|----------|--------|----------|
| `src/components/ui/` | NEW (shadcn CLI) | Treat as vendor code; never hand-edit |
| `src/components/app-sidebar.tsx` | NEW (hand-written) | Nav items, active logic via `useLocation`, badge counts |
| `src/components/AppShell.tsx` | REPLACED | `SidebarProvider` + `<AppSidebar>` + `<Outlet>` |
| `src/App.tsx` | MODIFIED | Layout route pattern; `/` to `/series`; `/library` removed |
| `src/pages/Series.tsx` | NEW | Series list with progress bar per series |
| `src/pages/SeriesDetail.tsx` | NEW | Season-grouped Accordion; episode badge row |
| `src/pages/Movies.tsx` | NEW | Movies list |
| `src/pages/Library.tsx` | DELETED | Only after Series + Movies are complete and tested |
| `src/pages/BibleEditor.tsx` | RESKIN-IN-PLACE | Largest page (88KB); highest regression risk; do last |
| `trezarr/web/routes/library.py` | MODIFIED | Enriched `get_series_episodes`; new response shape |
| `src/api/client.ts` | MODIFIED | New `EpisodeEnrichedRow`, `SeriesEpisodesResponse`, `SeasonGroup` types |

**Backend enrichment — `GET /api/library/series/{id}/episodes` rewrite:**

Three concurrent async calls (all pyarr sync calls wrapped in `asyncio.to_thread()`), gathered with `asyncio.gather`:
1. `sonarr_client.episode.get(series_id=N)` — logical episode records (ep#, title, monitored, hasFile, episodeFileId)
2. `sonarr_client.episode_file.get(series_id=N)` — file records (path, mediaInfo.audioLanguages)
3. `bazarr_client.fetch_episode_inventory(series_id)` — subtitle inventory keyed by `sonarrEpisodeId` (fail-soft)

Join keys: `episode.episodeFileId == episodeFile.id` for audio languages; `episode.id == BazarrInventoryItem.arr_id` for subtitles. Server-side season grouping before serialization. Response includes `bazarr_available: bool` at envelope level — when false, the UI suppresses the subtitle badge column rather than showing all-empty badges.

**Dark mode wiring (dark-only app):**
- `tailwind.config.js`: `darkMode: ["class"]`
- `frontend/index.html`: `<html lang="en" class="dark">`
- No JS `classList.add("dark")` needed if set in HTML directly

### Critical Pitfalls

1. **HSL channel-triple format (silent opacity breakage).** CSS variables must be bare `H S% L%` triples (e.g. `--primary: 270 70% 60%`), not wrapped in `hsl()`. The `hsl()` wrapper lives only in `tailwind.config.js`. Writing `--primary: hsl(270 70% 60%)` silently breaks opacity modifiers (`bg-primary/50`) with no compile error. Verify one opacity modifier renders correctly in the browser immediately after theme setup.

2. **`shadcn@latest init` breaks Tailwind v3 — the #1 operator error.** `npx shadcn@latest` (4.x) emits `@tailwindcss/vite`, `tw-animate-css`, and OKLCH variables. Running it on this project silently produces a config that breaks the entire PostCSS pipeline. Pin every `init` to `npx shadcn@2.10.0 init`.

3. **Token namespace collisions during bridge period.** The existing config has `border`, `accent`, `destructive` as plain hex strings. shadcn uses the same keys as nested objects. Do a wholesale color block replacement in one commit. Keep `bg-base`, `bg-surface`, `bg-stripe`, `text-primary`, `text-muted` as bridge tokens (no shadcn collision) until all pages are reskinned.

4. **BibleEditor reskin-in-place — never rebuild.** BibleEditor.tsx is 88KB with 5 previously-fixed critical locking bugs. The reskin is purely mechanical token substitution. Never touch API call patterns, state shape, lock mechanics, or FieldHistoryPanel behavior. Run the 293-test suite after each of the four sections.

5. **Bazarr fail-soft on the enriched endpoint.** The enriched episodes endpoint must never return HTTP 502 because Bazarr is down. Wrap every Bazarr call in `try/except Exception` with a fallback to `{}` and return `bazarr_available: false`. This matches the existing partial-results pattern (D-104).

6. **`sonarrEpisodeId` vs `episodeFile.id` join.** `BazarrInventoryItem.arr_id` is the logical `episode.id`, not `episodeFile.id`. Build the Bazarr lookup dict keyed by `episode.id`. Joining on the file ID produces all-empty badges with no error.

7. **Docker stale-image on Synology.** After any `package.json` change, run `docker build --no-cache` early. Never skip the Docker smoke test on `:6868` — Tailwind purges classes in production that `vite dev` serves fine.

---

## Implications for Roadmap

Build order is dependency-forced. Shell and Backend are parallel-eligible after Foundation. BibleEditor is last due to highest regression risk.

### Phase 1 — Foundation

**Rationale:** Everything depends on this. Path alias, shadcn init, theme tokens, dark mode wiring, and the animate plugin must all be correct before any component is installed or any page is touched.

**Delivers:** `@/` alias in both `vite.config.ts` and `tsconfig.json`; `components.json`; `src/lib/utils.ts` (`cn()`); correct HSL CSS-variable block in `index.css` (purple dark theme); `darkMode: ["class"]` + `class="dark"` on `<html>`; bridge-period `tailwind.config.js` (old hex tokens preserved alongside new shadcn token block); all shadcn components installed; jolly-ui Table installed; `legacy-peer-deps=true` in `.npmrc`. `npm run build` passes with no page content changes.

**Pitfalls to prevent:** HSL channel-triple format, token namespace collisions (wholesale replacement), `darkMode: ["class"]`, tailwindcss-animate in plugins, `@/` alias in both config files simultaneously, `legacy-peer-deps` before first add, do not set `base` in vite.config.ts.

**Open question to resolve here:** Visually tune the purple HSL. STACK.md suggests `270 70% 60%`; ARCHITECTURE.md suggests `271 71% 58%`. Render both, pick one, commit before Phase 2.

**Research flag:** Standard patterns. No additional research needed.

---

### Phase 2 — App Shell + Route Restructure

**Rationale:** The shell wraps every page and must be correct before any page work begins. Route restructure is a prerequisite for new pages. Can start as soon as Phase 1 is complete; runs in parallel with Phase 3.

**Delivers:** `AppShell.tsx` rewritten as `SidebarProvider` + `<AppSidebar>` + `<Outlet>`; `app-sidebar.tsx` with 6 nav items, `useLocation`-based active state, badge count placeholders; `App.tsx` on layout-route pattern with stub `Series.tsx`, `SeriesDetail.tsx`, `Movies.tsx`; `/` redirects to `/series`. All existing pages still load inside the new shell.

**Pitfalls to prevent:** Dual-token mixed period is acceptable during bridge — do not remove bridge tokens yet. Any tests mounting `<AppShell><Page/></AppShell>` must be updated (children prop gone).

**Research flag:** Standard patterns (RRv6 layout route + shadcn SidebarProvider).

---

### Phase 3 — Backend Episodes Enrichment

**Rationale:** Can run in parallel with Phase 2 since Phase 2 only produces a stub SeriesDetail. API contract must be stable and live-verified before Phase 4 implements SeriesDetail fully.

**Delivers:** `get_series_episodes` in `library.py` rewritten with `asyncio.to_thread` + `asyncio.gather` for two Sonarr calls, Bazarr inventory fetch (fail-soft), server-side season grouping, new JSON response shape (`seasons[]`, `bazarr_available`, `errors[]`). Updated `client.ts` types. Backend tests updated. Live-verified against Bazarr at 192.168.5.42.

**Pitfalls to prevent:** Bazarr fail-soft (never 500), `sonarrEpisodeId` join key (use `episode.id` not `episodeFile.id`), `audioLanguages` absent/`"und"` handling with full-name to ISO code lookup table, one Bazarr call per page load (not per episode), subtitle paths display-only (no execution path), new routers registered before StaticFiles mount in `app.py`.

**Research flag:** Verify Bazarr `fetch_episode_inventory` param format (`seriesid[]` vs `seriesid`) against the live instance at 192.168.5.42 — known ambiguity, needs runtime validation.

---

### Phase 4 — New Library Pages

**Rationale:** Depends on Phase 2 (shell + stubs) and Phase 3 (stable API contract). These are the headline deliverables of the milestone.

**Delivers:** `Series.tsx` (dense table with progress bars); `SeriesDetail.tsx` (shadcn Accordion by season, latest auto-expanded, toggle-all, episode rows with all badge types, Translate button); `Movies.tsx` (dense table with Translate buttons); `Library.tsx` deleted; `/library` route removed; old `EpisodeRow` type removed from `client.ts`.

**Pitfalls to prevent:** Badge WCAG 1.4.1 (outline-vs-filled + `aria-label`); jolly-ui Table beta fallback (if unstable, substitute shadcn plain `<Table>` — same API surface, decide within first day of implementation).

**Research flag:** jolly-ui Table beta status is MEDIUM confidence. Evaluate stability at implementation start; have the fallback plan ready.

---

### Phase 5 — Reskin Existing Pages

**Rationale:** Big-bang commitment requires all pages on the new component system before shipping. Changes are isolated per file. Simplest to most complex, BibleEditor last.

**Delivers (in order):** `JobLogs.tsx` → `Queue.tsx` → `History.tsx` → `Settings.tsx` → `BibleList.tsx` → `BibleEditor.tsx` (four sections: Characters, Address Map, Term Dictionary, Register/Overrides) reskinned in-place. Shared components reskinned. Legacy bridge tokens removed from `tailwind.config.js` only after all pages pass grep for `bg-[#` and `text-[#`.

**BibleEditor constraint:** Reskin-in-place only. Mechanical token substitution. Never touch API calls, state shape, lock mechanics, or FieldHistoryPanel. Run the 293-test suite after each of the four sections. Gate on green before next section.

**Pitfalls to prevent:** BibleEditor rebuild reflex (if any PR says "rewrote BibleEditor", stop), forwardRef perf in address-map table rows (React.memo on the row, not its shadcn wrapper), visual regression (manual checklist per page, `npm run build` gate after each file).

**Research flag:** Mechanical substitution. No additional research needed.

---

### Phase 6 — Docker Rebuild + Live Smoke Test

**Rationale:** Production build catches what `vite dev` misses: Tailwind class purging, multi-stage COPY layer correctness, PUID/PGID behavior, `trezarr serve` lifespan assertions. This is the release gate.

**Delivers:** `docker build --no-cache` passes the full multi-stage build. Container runs on `:6868` against live deployment (Sonarr/Radarr/Bazarr at 192.168.5.42). Smoke test covers all 6 nav routes, episode accordion with badges, Translate flow, Settings save, BibleEditor all 5 tabs, toasts.

**Pitfalls to prevent:** Stale image on Synology (`git fetch` + fast-forward verify before build; `docker build --no-cache`), animation classes purged in production (grep `dist/assets/*.css` for `animate-in`), Vite `base` must remain unset.

**Research flag:** Standard ops patterns. No additional research needed.

---

### Phase Ordering Rationale

- Foundation before Shell: the `@/` alias, CSS variable block, and `darkMode: ["class"]` are prerequisites for shadcn component imports and SidebarProvider CSS variables.
- Shell before Pages: the layout-route pattern is required for `<Outlet>` in SeriesDetail. Without the Shell phase, new pages have no mount point.
- Backend parallel to Shell: enriched API contract does not depend on frontend work. Must be complete before Phase 4 implements SeriesDetail fully.
- New Pages before Reskin: prove the badge system and accordion work on net-new code before using them in the high-risk BibleEditor.
- BibleEditor last: highest regression risk. All other pages complete and tested before touching it, so it cannot block the rest of the milestone.
- Docker last: the production build is a gate, not a development loop.

---

### Research Flags

**Needs runtime validation (not more desk research):**
- Phase 3 (Backend): Verify Bazarr `fetch_episode_inventory` param format against live Bazarr at 192.168.5.42.
- Phase 4 (New Pages): Evaluate jolly-ui Table beta stability at implementation start.

**Standard patterns — skip additional research:**
- Phase 1 (Foundation): shadcn init, Tailwind v3 token migration, dark mode — verified against source.
- Phase 2 (Shell): RRv6 layout routes + shadcn SidebarProvider — canonical.
- Phase 5 (Reskin): Mechanical token substitution — no novel patterns.
- Phase 6 (Docker): Existing Dockerfile pattern is correct; `--no-cache` is sufficient.

---

## Watch Out For

These items span multiple phases and deserve explicit attention throughout:

**Purple HSL values — tune before committing.** STACK.md gives `270 70% 60%`; ARCHITECTURE.md gives `271 71% 58%`. Render both in the browser during Phase 1, pick one, commit, and use it everywhere. A mid-sprint change to `--primary` triggers visual regression across all already-migrated pages.

**`border-border` vs `border-[#2d3148]` dual sources of truth.** During the bridge period both exist. Remove bridge tokens atomically (single commit) after all pages are migrated. Use grep for `bg-[#` and `text-[#` as the cleanup gate.

**`asyncio.to_thread` on all pyarr calls.** The current endpoint calls pyarr synchronously inside `async def` — a latent event-loop blocking bug. The enrichment adds two more pyarr calls. All must be wrapped. Missing even one causes visible unresponsiveness under concurrent page loads.

**Synology multi-machine repo.** Per project memory: `main` can advance mid-session from another machine. Always `git fetch` + verify fast-forward before the Phase 6 Docker build push. Never force-push to `main`.

**`legacy-peer-deps=true` in `.npmrc` is intentional.** Document this in Phase 1 so future maintainers understand why it is there.

**`audioLanguages` is a string, not an array.** Sonarr returns `"Japanese / English"` (full names, slash-separated), not `["JA", "EN"]`. A lookup table mapping common full names to ISO codes is required in the backend enrichment. Return `audio_languages: []` when mediaInfo is absent or value is `"und"`.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | npm registry live-queried 2026-06-03; shadcn CLI source read directly; all peer dep ranges verified; v3/v4 split confirmed against official docs |
| Features | HIGH | Bazarr source code read directly (Navbar.tsx, Episodes/table.tsx, Language.tsx, AudioList.tsx, Navbar.module.scss); Sonarr EpisodeRow.js read directly; WCAG 1.4.1 official spec |
| Architecture | HIGH | Trezarr source code read directly (App.tsx, AppShell.tsx, tailwind.config.js, library.py, bazarr.py, app.py); RRv6 layout route pattern well-established |
| Pitfalls | HIGH (theme/alias/dark mode/backend) / MEDIUM (jolly-ui Table beta) | shadcn and React GitHub issues confirmed; jolly-ui Table beta has limited public track record |

**Overall confidence: HIGH**

### Gaps to Address During Implementation

- **jolly-ui Table beta stability:** No public incident report found. Evaluate within the first day of Phase 4; have the shadcn plain `<Table>` fallback ready to swap.
- **Bazarr `seriesid[]` param format:** Known ambiguity from production observation. Verify against 192.168.5.42 during Phase 3 before writing the episode join logic.
- **Purple HSL tuning:** Design decision, not a research question. Resolve visually during Phase 1.
- **`audioLanguages` full-name to ISO code mapping:** Common cases are known (JA, KO, ZH, TH, EN, VI); edge cases ("Mandarin", "Cantonese") need a truncate-to-3-chars fallback. Build the lookup table in Phase 3 and expand as needed.

---

## Sources

### Primary (HIGH confidence)

- npm registry live queries (2026-06-03) — all package versions and peer dep ranges
- `github.com/shadcn-ui/ui` source (`packages/shadcn/src/utils/templates.ts`) — exact HSL template, `cn()` function, v3 vs v4 config format
- `ui.shadcn.com/docs/tailwind-v4` — v3/v4 split; "use shadcn@2.3.0" minimum for v3 projects
- `github.com/morpheus65535/bazarr` source — Navbar.tsx, Navbar.module.scss, Episodes/table.tsx, Language.tsx, AudioList.tsx — nav conventions, badge system, episode table columns
- `Sonarr/frontend/src/Series/Details/EpisodeRow.js` — column definitions, audioLanguages field
- Trezarr codebase — `App.tsx`, `AppShell.tsx`, `tailwind.config.js`, `library.py`, `bazarr.py`, `app.py` — existing architecture baseline
- `radix-ui.com/primitives/docs/overview/releases` — React 19 full support confirmed June 2024
- WCAG 1.4.1 Use of Color (w3.org/WAI) — badge accessibility requirement
- `jollyui.dev/docs/installation` — registry URL, Tailwind v3 config confirmed, no npm package
- `ui.shadcn.com/docs` — SidebarProvider, SidebarMenuButton, CSS variable names, sidebar token list

### Secondary (MEDIUM confidence)

- `github.com/adobe/react-spectrum` issues #9267, #7756 — react-aria-components React 19 peer dep warning (cosmetic) and DatePicker ref bug (avoid DatePicker in v1.1)
- jollyui.dev Table component page — beta status noted; React Aria Table with keyboard nav
- Community reports (Sonarr issue #5602) — `audioLanguages` is a slash-separated string of full names, not an array of ISO codes; `"und"` for unanalyzed files

### Tertiary (LOW confidence — needs runtime validation)

- Bazarr `seriesid[]` vs `seriesid` param format — observed in production; verify against live instance
- jolly-ui Table beta runtime behavior under React 19 production builds — limited public track record

---

*Research completed: 2026-06-03*
*Ready for roadmap: yes*
