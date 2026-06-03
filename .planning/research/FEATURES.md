# Feature Landscape: Trezarr v1.1 Dashboard UX

**Domain:** *arr-companion self-hosted dashboard — library browser, subtitle-status display, translation trigger
**Researched:** 2026-06-03
**Sources:** Bazarr source (github.com/morpheus65535/bazarr, Navbar.tsx + Router/index.tsx + Episodes/table.tsx + Episodes/components.tsx + Language.tsx + AudioList.tsx), Sonarr source (EpisodeRow.js), shadcn/ui sidebar docs, WCAG 1.4.1 accessibility spec

---

## Executive Summary

The reference product (Bazarr) and its sibling (Sonarr) have converged on a stable, well-understood UX playbook for *arr-companion dashboards. That playbook is fully observable from their source code:

- Dense table (not poster grid) as the list-page default, with a progress bar in the series list summarizing subtitle completeness
- Full-height sidebar with icon + label nav rows, badge counts in muted rounded pill (auto-hidden when zero), active state = left 2px accent border + darkened background
- Episode detail grouped by season via a collapsible accordion; latest season auto-expanded, older seasons collapsed; columns are fixed (not user-configurable in Bazarr's implementation)
- Badge system: one badge component per subtitle track; short ISO-639-1 code2 uppercase as text; `:HI` and `:Forced` suffixes appended inline; missing subtitles get a warning (amber) variant; present subtitles get default/brand variant; audio language badges use a distinct blue color to differentiate them semantically from subtitle badges
- Accessibility: color alone is never sufficient per WCAG 1.4.1. Bazarr adds tooltips and variant labels to disambiguate. For a single-user tool the bar is lower but the pattern should be followed for the badge system.

Trezarr v1.1 departs from Bazarr in two meaningful ways: (1) the nav gains Series and Movies as top-level routes (Bazarr uses them as primary items too; this is correct), and (2) the subtitle badge row needs to encode both source/foreign-language subs (amber) and Vietnamese subs (purple, brand color), whereas Bazarr encodes only a single desired-vs-missing dimension per profile. The two-color semantic distinction (amber = source/input, purple = output) is a differentiator unique to Trezarr's translator role.

---

## 1. Sidebar Navigation

### Table Stakes (must-have — matches user expectation set by Bazarr/Sonarr)

| Feature | Why Expected | Complexity | Backend Dependency |
|---------|--------------|------------|-------------------|
| Full-height sidebar, not a top-nav | Every *arr tool uses left sidebar; top nav is a mobile-app pattern, not a dashboard pattern | Low — layout CSS only | None |
| Icon + label nav rows | Bazarr: FontAwesome icon + text label in every row | Low | None |
| Active row = left 2px accent border + slight bg | Bazarr: `border-left: 2px solid bazarr.$color-brand-4; background-color: dark-8` (verified in Navbar.module.scss) | Low | None |
| Badge count on right, auto-hidden when zero | Bazarr: Badge with `margin-left: auto`; badge suppressed when value is 0 or undefined (useBadgeValue hook in Navbar.tsx) | Low | Count endpoints or derived from library fetch |
| Series and Movies as distinct top-level nav items | Bazarr Router: Series and Movies are the first two routes, visible = sonarr/radarr enabled; Trezarr replaces the old combined /library | Low | None (routing only) |
| Settings at bottom or clearly grouped | Bazarr: Settings is 5th item; Sonarr: Settings in sidebar. Convention is "content items first, config last" | Low | None |

### Differentiators (nice-to-have — not expected, but add value)

| Feature | Value Proposition | Complexity | Backend Dependency |
|---------|-------------------|------------|-------------------|
| "LIVE" badge or animated dot on Queue nav item | Shows user the daemon is actively translating without navigating | Medium — requires SSE or polling for daemon state | `GET /api/queue` returning in-progress count |
| Service status dot moves to sidebar footer | Current TopBar dot is fine, but sidebar footer (like Bazarr's donate/theme row) is a cleaner home | Low | Existing `/api/health` |
| Collapsible nav sections | Bazarr uses Collapse to group Settings sub-routes under the Settings header. Not needed for Trezarr's flatter nav | Medium | None |

### Anti-Features (deliberately do NOT build)

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Hamburger/collapsible sidebar | Single-user desktop dashboard; never needs mobile collapse. Adds complexity, breaks nav discoverability | Fixed-width sidebar (192-220px), always visible |
| Search bar in sidebar | Global search is a Bazarr header feature. Not needed for a single-user library of tens-not-thousands of items | Inline column filter on the list page table |
| Nested sub-nav groups | Bazarr has them for Settings with 10 sub-pages. Trezarr's Settings is one page. Nesting adds complexity without benefit | Flat nav; sub-page tabs on the destination page |

### Exact Nav Order (from Bazarr convention + milestone spec)

1. Series (icon: Tv, badge: untranslated count from library)
2. Movies (icon: Film, badge: untranslated count from library)
3. Queue (icon: List, badge: in-progress or pending count)
4. History (icon: History)
5. Bible (icon: BookOpen)
6. Settings (icon: Settings)

---

## 2. Library List Pages (Series and Movies)

### Table Stakes

| Feature | Why Expected | Complexity | Backend Dependency |
|---------|--------------|------------|-------------------|
| Dense table, not poster grid | Bazarr Series page: dense tanstack/react-table table, no posters. Sonarr has both views but defaults to table for monitoring-focused users. Trezarr is a monitoring/action tool, not a media browser. Poster grids imply browsing for content to watch — wrong mental model. | Low | None |
| Columns: Status icons · Title · Year · Episodes progress | Bazarr: monitored-bookmark + ended/continuing icons, title (clickable link), language profile, progress bar. For Trezarr: monitored icon · Title · Year · "X/Y translated" progress bar | Medium | Library endpoint must return episodeFileCount + translatedCount per series |
| Progress bar in series row (translated / total) | Bazarr uses a Progress component with brand color when fully translated, yellow when missing. This is the primary at-a-glance status for a library of series. | Medium | Backend must aggregate per-series translated counts |
| Clickable title row navigates to detail | Bazarr: Link to /series/:id. Standard row-click drill-in. | Low | Existing series endpoint |
| Empty state with helpful text | When Sonarr/Radarr unreachable: "No items found. Check Sonarr/Radarr are connected in Settings." Current Library.tsx already does this correctly. | Low | None |
| Loading spinner | Current Library.tsx shows "Loading library..." text. Acceptable minimum. | Low | None |
| Partial-results warning banner | When one of Sonarr/Radarr fails: show amber banner per failing source. Current Library.tsx already does this. | Low | Existing `errors[]` in library response |

### Differentiators

| Feature | Value Proposition | Complexity | Backend Dependency |
|---------|-------------------|------------|-------------------|
| Per-series "Translate All" button | Trigger a full-series translation job from the list. Useful for initial library ingestion. | Medium | `POST /api/translate` per series, or a new series-level bulk endpoint |
| Column: "Bible" badge | Shows whether a Series Bible exists for this series. Encourages users to verify the Bible exists before trusting translated output. | Low | `GET /api/bible/series` to check existence |
| Table-level text filter / search box | Filter the visible series/movies by title without a server round-trip. Standard feature; Bazarr doesn't have inline table filter on list pages. | Low | None (client-side filter on already-loaded data) |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Poster/card grid view | Wrong mental model for a translation monitoring tool; high complexity, adds image fetching from Sonarr/Radarr, no monitoring value. Bazarr does not implement it. | Dense table |
| Sort/filter by genre, network, or rating | Content-browsing features. Users come here to find untranslated items, not to browse. | Sort by title or untranslated count only |
| Server-side pagination | For a single user with fewer than 1000 series, client-side data is fine. Bazarr uses server-side pagination only because it is a public tool with large deployments. | Load all, client-filter |

---

## 3. Series Detail View (Season-Grouped Episode Table)

### Table Stakes

| Feature | Why Expected | Complexity | Backend Dependency |
|---------|--------------|------------|-------------------|
| Season-grouped accordion | Bazarr Episodes/table.tsx: GroupTable with `initialState.grouping: ["season"]`. Sonarr: SeriesDetailsSeason.js. Both use group-by-season as the primary organization. The alternative (flat list) makes large multi-season series (30+ eps) unusable. | Medium — shadcn Accordion or headless group | `GET /api/library/series/{id}/episodes` returns `season_number` per row |
| Latest season auto-expanded, older collapsed | Bazarr: `tableRef.current?.setExpanded({ season:${maxSeason}: true })` (Episodes/table.tsx line ~170). This is the universal pattern — latest season is what the user cares about. | Low — derive maxSeason client-side | Season number in episode response |
| Toggle all expand/collapse | Bazarr: a toolbar button calls `tableRef.current?.toggleAllRowsExpanded()` with a chevron icon that flips. Sonarr has the same. | Low | None |
| Season header shows: season number + subtitle progress | Bazarr: SeasonInfo.tsx shows episode count + missing count in the season row. Trezarr: "Season N · X/Y translated" | Medium | Derived from episode rows |
| Episode columns: Action · Ep# · Title · Audio · Subtitle badges | Bazarr: monitored/episode/title/audio/subtitles/actions. Sonarr: monitored/episodeNumber/title/airDate/runtime/languages/audioInfo/status/actions. Trezarr target matches milestone spec. | Low — column layout | Audio languages and subtitle inventory from enriched endpoint |
| Per-row translate action | Current Library.tsx: "Translate" button per row, disabled if no source sub. Keep this. | Low | Existing `POST /api/translate` |
| Per-row subtitle badge row | Core visual — the point of this view. See Section 4 for badge details. | Medium | Subtitle inventory per episode from Bazarr client |
| Empty episode state | "No episode files found for this series." Existing Library.tsx has this. | Low | None |

### Differentiators

| Feature | Value Proposition | Complexity | Backend Dependency |
|---------|-------------------|------------|-------------------|
| Per-season "translate all in this season" action | Batch-translate an entire season (anime workflow — translate as each season downloads). | Medium | Needs a season-scoped bulk translate endpoint or client-side loop |
| Episode air date column | Sonarr shows relative dates ("3 days ago"). Useful for knowing which episodes are new. Low implementation cost. | Low | Sonarr episode metadata already fetched in enriched endpoint |
| Jump to latest season button on series header | If the user has 10 seasons and arrives scrolled to the top, a jump-link saves scroll time. | Low | None (JS scroll) |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Manual search / provider-picker per episode | Bazarr has this because it downloads from subtitle providers. Trezarr translates — the source selection is already configured in Settings/Bible overrides. | Per-row "Translate" button using configured source |
| Edit series / rename / quality profile columns | *arr-management features. Trezarr is read-only from Sonarr/Radarr's perspective. | None |
| Drag-to-reorder episodes | No user value. Episodes are canonical from Sonarr. | None |
| User-configurable column visibility | Bazarr does not have per-user column config in its Episodes table. Adds settings surface for no gain in a single-user tool. | Fixed columns |

---

## 4. Language / Status Badge System

This is the most Trezarr-specific feature domain. Bazarr's badge system is the closest reference but Trezarr has a two-role system (source/input langs vs. Vietnamese output) that Bazarr does not have.

### Authoritative Bazarr Badge Behavior (from source)

From Language.tsx:
- Short form: `value.code2` (ISO-639-1, 2-letter). Append `:HI` if `value.hi` is true, `:Forced` if `value.forced` is true (and not HI). Long form: `value.name` + ` HI` or ` Forced`.
- The Badge gets a `variant` prop: `"warning"` (amber) for missing subtitles, `"disabled"` (muted) for embedded (non-file) subtitles, `"highlight"` when the menu is open, and `undefined` (default brand color) for present subtitles.
- Audio badges (AudioList.tsx): always `color="blue"` regardless of status. This creates a clear visual separation: blue = audio track, default/brand = subtitle track.

### Trezarr Badge Conventions (derived from Bazarr + milestone spec)

**Label format:**
- Code: ISO-639-1 uppercase 2-letter: `ZH`, `KO`, `JA`, `EN`, `VI`
- HI suffix: `:HI` appended directly (no space) — matches Bazarr's short form. Result: `VI:HI`
- Forced suffix: `:Forced` — not expected in Trezarr's primary use case but follow the same pattern
- Audio badges: show the audio language code only, styled distinctly from subtitle badges

**Color semantics (two-role system):**

| Badge Type | Color | Rationale |
|-----------|-------|-----------|
| Audio track badge | Blue (e.g. `bg-blue-800 text-blue-200`) | Matches Bazarr's `color="blue"` for AudioList; visually distinct from subtitle badges |
| Source/foreign subtitle present | Amber (e.g. `bg-amber-900 text-amber-200`) | "Input" material — matches Bazarr's warning color but repurposed: means "this is a translatable source" in Trezarr's context |
| Vietnamese subtitle present | Purple/brand (e.g. `bg-violet-800 text-violet-200`) | Output material — the product of Trezarr's work; distinguishes the target from the source |
| Missing Vietnamese (wanted but not yet translated) | Dim purple outline (e.g. `border border-violet-700 text-violet-500 bg-transparent`) | "Needed but absent" — visually quieter than the present variant, shape dimension (outline vs. filled) provides non-color cue |
| Missing source (no translatable input) | Muted gray (`bg-gray-800 text-gray-400`) | Nothing to do; not an error state |
| In-progress (translation queued/running) | Animated orange or spinning indicator | Provides feedback during active translation |

**Badge ordering convention:**
Show audio badges first, then source/foreign subtitle badges (in relational-richness tier order: ZH, KO, JA, TH, then others, then EN), then VI last. This mirrors the translation pipeline's direction: audio → source → output.

**Accessibility (WCAG 1.4.1 — Level A):**
Color alone cannot convey the meaning of missing vs. present. Required mitigations:
- Text labels are inherent in the badges (the code text itself is meaningful). Do not use color-only dots.
- Add `title` or `aria-label` to each badge: `aria-label="Vietnamese subtitle, hearing-impaired version, present"` / `aria-label="Vietnamese subtitle, missing — translate to create"`.
- The outline-vs-filled treatment for missing vs. present badges adds a shape dimension beyond color, satisfying the "not color alone" requirement.
- Tooltip on hover is a differentiator (Bazarr does this for embedded subs via Tooltip.Floating).

### Complexity and Dependencies

| Badge type | Implementation complexity | Backend field required |
|-----------|--------------------------|----------------------|
| Audio language | Low — `audio_languages: string[]` from Sonarr mediaInfo | `audio_languages` array in enriched episode endpoint |
| Source subtitle present | Low — derived from `subtitles[]` filtering out vi/vie codes | `subtitles[]` from Bazarr BazarrInventoryItem |
| VI present / VI:HI | Low — `subtitles[]` entry with `code2="vi"` and `hi` field | Same; `hi` bool from BazarrInventoryItem |
| Trezarr translation status | Low — already exists as `status` field in episode row | Existing `processed_file` ledger |
| In-progress state | Medium — requires live state (WebSocket or polling) | Queue state from `/api/queue` |

---

## 5. Empty and Loading States

### Table Stakes

| State | Pattern | Complexity |
|-------|---------|------------|
| Library loading | Spinner or "Loading library..." text; current Library.tsx is minimum viable | Low |
| Library error (Sonarr/Radarr unreachable) | Amber banner per source, with link to Settings. Current Library.tsx already implements this correctly. | Low |
| Library empty (connected but no media) | "No items found. Check Sonarr and/or Radarr are connected in Settings." Already implemented. | Low |
| Series episodes loading | Spinner in the episode table area while fetching enriched episodes | Low |
| Series episodes empty | "No episode files found for this series." Already implemented. | Low |
| Series episodes error | Amber inline error. Already implemented in Library.tsx. | Low |

### Differentiators

| State | Pattern | Complexity |
|-------|---------|------------|
| Skeleton rows during load | Shimmering placeholder rows instead of spinner text; perceived performance improvement | Medium |
| Optimistic badge update after translate trigger | Immediately show "in-progress" badge after clicking Translate, before server confirms | Medium |

### Anti-Features

| Anti-Feature | Why Avoid |
|--------------|-----------|
| Full-page loading overlay | Blocks interaction with already-loaded content (e.g. nav). Use per-section spinners. |
| Error modals | Use inline banners; modals interrupt flow and require dismissal for non-fatal errors. |

---

## 6. Per-Row and Per-Season Actions

### Table Stakes

| Action | Trigger | Complexity | Backend |
|--------|---------|------------|---------|
| Per-episode Translate | Button in Actions column; disabled when no source sub; shows "Queuing..." during pending | Low — already implemented in Library.tsx | Existing `POST /api/translate` |
| Navigate to Queue after translate | After POST /api/translate, navigate to /queue. Already implemented. | Low | None |

### Differentiators

| Action | Trigger | Complexity | Backend |
|--------|---------|------------|---------|
| Per-season Translate All | Button in season header row; translates all has_source episodes in that season | Medium | Needs a batch translate API or client-side loop with per-item POST |
| Re-translate (overwrite) | Button for already-translated episodes; requires confirmation | Medium | Existing POST with force=true param or equivalent |
| Open in Bible | Link from series detail page to the Bible editor for that series | Low | Route exists |

### Anti-Features

| Anti-Feature | Why Avoid |
|--------------|-----------|
| Manual source selection per row | Source selection is configured in Bible/Settings; per-row override is a power-user feature for v2+ |
| Bulk-select checkboxes | For Trezarr's single-user workflow, per-season "translate all" covers the bulk case. Checkboxes add UI complexity. |

---

## 7. Feature Dependencies on Backend Data

The v1.1 milestone includes a backend enrichment task for `GET /api/library/series/{id}/episodes`. This is the critical dependency gating most of the new visual features.

| UI Feature | Required Backend Field | Current State |
|-----------|----------------------|---------------|
| Audio language badges | `audio_languages: string[]` (from Sonarr mediaInfo) | Not yet in episode endpoint |
| Source subtitle badges (ZH/KO/JA/EN etc.) | `subtitles: [{code2, hi, forced, path}]` from Bazarr BazarrInventoryItem | Bazarr client exists (Phase 10); not yet in episode endpoint |
| VI subtitle badge | Same `subtitles[]` — filter for code2 == "vi" or "vie" | Same |
| VI:HI badge | `subtitles[]` entry with `hi=True` | Same |
| Trezarr status per episode | `status: "translated" | "has_source" | "no_source" | "in_progress"` | Already in EpisodeRow |
| Season grouping | `season_number: int` per episode | Must be added to enriched episode response |
| Episode title | `title: str` | Already in EpisodeRow |
| Progress bar in series list | `translated_count / total_count` per series | Must be added to library series response |

Backend fail-soft requirement: Bazarr unavailability must degrade gracefully (partial result, amber banner) rather than failing the whole episode load. Phase 10 established this as D-104 — the enriched endpoint must honor the same pattern.

---

## 8. Feature Categorization Summary

### Table Stakes — Must Ship (v1.1 blocking)

- Full-height sidebar with Series/Movies/Queue/History/Bible/Settings, active state, badge counts (zero-hidden)
- Series list page: dense table with progress bar per series, clickable title drill-in
- Movies list page: dense table with per-movie Translate button (source-sub-gated)
- Season-grouped accordion on series detail: latest auto-expanded, toggle-all button
- Episode table columns: Action · Ep# · Title · Audio badge · Subtitle badges
- Badge system: blue audio, amber source/foreign, purple VI, dim/outline missing-VI
- Empty/loading/error states (already largely implemented — keep and adapt)
- Per-episode Translate button (already implemented — adapt to new column layout)

### Differentiators — High Value, Implement in v1.1 if Low Friction

- Per-season "Translate All" action in season header
- Episode air date column (low cost, helpful for new-episode workflows)
- Tooltip on badge with full human-readable label (accessibility + UX win)
- Jump to latest season anchor
- Animated indicator on Queue nav item when jobs are running

### Anti-Features — Explicitly Out of Scope for v1.1

- Poster/card grid view for list pages
- Hamburger/collapsible sidebar
- Manual subtitle source selection per episode
- Bulk-select checkboxes / Mass Edit mode
- User-configurable column visibility
- Full-page loading overlays
- Error modals for non-fatal errors
- Per-call tenacity / aggressive polling for real-time queue state (use simple interval, less than 30s)

---

## Sources

- Bazarr Router/index.tsx (github.com/morpheus65535/bazarr) — exact nav order, badge data shape, conditional visibility — HIGH confidence (source code, read directly)
- Bazarr App/Navbar.tsx — badge auto-hide logic (useBadgeValue), Collapse for sub-nav — HIGH
- Bazarr App/Navbar.module.scss — active state: `border-left: 2px solid`, `background-color: dark-8` — HIGH
- Bazarr pages/Episodes/table.tsx — GroupTable grouping, maxSeason auto-expand, column definitions — HIGH
- Bazarr pages/Episodes/components.tsx — Badge variants (warning/disabled/highlight), SubtitleToolsMenu — HIGH
- Bazarr components/bazarr/Language.tsx — code2 label, `:HI`/`:Forced` suffix pattern — HIGH
- Bazarr components/bazarr/AudioList.tsx — `color="blue"` for audio badges, distinct from subtitle badges — HIGH
- Bazarr pages/Series/index.tsx — dense table, Progress bar (brand/yellow), monitored bookmark + ended/continuing icon columns — HIGH
- Sonarr frontend/src/Series/Details/EpisodeRow.js — columns: monitored/episodeNumber/title/airDate/runtime/languages/audioLanguages/audioInfo/status/actions — HIGH (source code)
- shadcn/ui Sidebar docs (ui.shadcn.com) — SidebarMenuBadge, isActive prop, dark mode CSS vars — HIGH
- WCAG 1.4.1 Use of Color (w3.org/WAI) — "color cannot be the only visual means"; 1 in 12 men color-vision deficiency — HIGH (official standard)
- Trezarr PROJECT.md v1.1 milestone spec — badge color semantics (amber=source, purple=VI, VI:HI), shadcn foundation, route structure — HIGH (project source of truth)
