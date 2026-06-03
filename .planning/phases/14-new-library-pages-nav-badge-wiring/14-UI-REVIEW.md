# Phase 14 — UI Review

**Audited:** 2026-06-04
**Baseline:** 14-UI-SPEC.md (authoritative) + 12-UI-SPEC.md design language
**Screenshots:** Not captured — no dev server running on localhost:3000/5173/8080

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Empty-state headings use `font-medium` (500) not `font-normal` (400) per spec; series detail page always falls back to "Series #ID" — series title never shown |
| 2. Visuals | 3/4 | Series table has a separate Year column instead of an inline sub-label in the Title cell per spec; two sort buttons instead of one cycling button deviates from spec pattern |
| 3. Color | 4/4 | All badge tokens correct: blue-700/80 audio, amber-600/80 source, hsl(var(--primary))/80 VI, emerald-600 LIVE, hsl(var(--primary)) count — no raw hex in component code except the sanctioned footer dot (#22c55e from Phase-12) |
| 4. Typography | 3/4 | Three weights in use (font-normal / font-medium / font-semibold); contract allows only 2 (400/600); font-medium (500) appears in empty-state headings and table title cells |
| 5. Spacing | 4/4 | Controls bar gap-3 / mb-4, table cells py-2 px-4, touch targets min-h-[44px] — all match spec; column widths deviate slightly (Progress 220px vs spec 180px) but are functionally fine |
| 6. Experience Design | 4/4 | All six state branches covered: loading (Skeleton), fetch error (Retry), service down (Go to Settings), empty after filter (Clear filters), episode empty, inline translate error; bazarr_available suppression implemented; carryforward WR-01/WR-03/IN-01 addressed |

**Overall: 21/24**

---

## Top 3 Priority Fixes

1. **SeriesDetail heading never shows the series title** — The `SeriesEpisodesResponse` type in `client.ts` has no `title` field (only `series_id`), so the heading always renders `Series #ID` instead of the real series name. The spec contract states `{seriesTitle || 'Series #' + seriesId}`. Either add a `series_title` field to the API response shape (backend + client type), or fetch the series name from LibraryContext when a matching `SeriesItem` is available there. User impact: every series detail page shows a meaningless ID instead of the show name.

2. **Series table Year column should be an inline sub-label in the Title cell** — `Series.tsx` renders a standalone `w-[80px]` Year column. The spec table-column contract explicitly defines only three columns: Title (with year as a sub-label), Progress, Translated. This wastes 80px of width and breaks spec layout. Move `{s.year}` inside the Title `<td>` as a muted `text-xs` sub-label, matching the Movies.tsx pattern which already implements this correctly.

3. **Empty-state heading weight violates the 2-weight typography contract** — Both `Series.tsx:264` and `Movies.tsx:303` render the "No series/movies found" heading as `text-base font-medium text-muted-foreground`. The spec states this heading is `16px / 400 / muted` (font-normal). `font-medium` (500) is a third weight not in the 2-weight contract and visually over-emphasises a secondary state. Change to `font-normal`.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

**PASS — Copywriting is substantially correct across all required strings.**

All spec-mandated copy strings are implemented verbatim or within acceptable paraphrase:

- Series heading: "Series" (`text-xl font-semibold`) — correct
- Movies heading: "Movies" (`text-xl font-semibold`) — correct
- Search placeholders: "Search series..." / "Search movies..." — correct
- Filter dropdown: "Filter: {All|Needs VI|Translated|No source}" — correct
- Sort buttons: "Sort by Title / Sort by Progress" — present (see Visuals for the two-button vs. one-button pattern deviation)
- Translate buttons: "Translate" (episode), "Translate season" (season header), "Translate" (movie row) — all correct
- Progress fraction: "{N}/{M} translated" (muted, 14px) — correct
- Bazarr unavailable note: "Bazarr unavailable — subtitle data suppressed" in `text-amber-500` — correct
- LIVE badge: "LIVE" (emerald) — correct
- Status chip: "Translated" (emerald) — correct
- Clear filters CTA: "Clear filters" — correct
- 404 heading/body/CTA: "Page not found" / "The page you're looking for doesn't exist." / "Go to Series" — exact match

**WARNING findings:**

- `SeriesDetail.tsx:340` — heading always renders `Series #{numericId}`. The spec contract is `{seriesTitle || 'Series #' + seriesId}`. The API response type (`SeriesEpisodesResponse`) has no `title` field; the fallback fires 100% of the time. This is both a copywriting and data-flow gap.

- `Series.tsx:264-265` — empty-state heading uses `text-base font-medium text-muted-foreground`. Spec says "Heading (16px/400/muted)". The copy ("No series found") is correct; the weight is not (font-medium = 500 ≠ 400).

- `Movies.tsx:303` — same pattern: `text-base font-medium text-muted-foreground` on "No movies found" heading.

- `SeriesDetail.tsx:354-360` — empty state renders two `<p>` tags for the heading and body rather than the spec's distinct heading/body role split (`<p className="font-medium">No episodes found</p>`). The copy is correct but the heading role uses a plain `<p>` not an `<h2>` or equivalent semantic element.

No generic labels (Submit / Click Here / OK / Cancel / Save), no spurious "No data / Nothing" patterns outside spec-defined states.

---

### Pillar 2: Visuals (3/4)

**PASS with two layout deviations from the spec column contract.**

**What works:**
- Visual hierarchy: page headings (`text-xl font-semibold`) clearly dominate column headers (`text-muted-foreground font-normal`) and cell content — correct three-level hierarchy
- Accordion season grouping: vendor AccordionTrigger provides chevron; "Translate season" ghost button is placed inside trigger children before the auto-chevron — correct D-05 composition
- Row hover states: `hover:bg-accent/50 transition-colors` on both Series and Movies rows — correct
- `has_file === false` dimming: `opacity-50` on episode rows without files — correct per spec
- Loading skeleton: three layers (heading, search bar, 6 row placeholders) — matches spec exactly
- NotFound page: `flex flex-col items-center justify-center h-64 gap-4` centering — matches spec layout

**WARNING findings:**

- **Year column layout deviation** (`Series.tsx:289`): The spec column table defines Title (with year sub-label), Progress (180px), Translated (120px). The implementation adds a standalone `w-[80px]` Year column as the second column. Movies.tsx correctly implements year as an inline sub-label inside the Title cell (`<span className="text-muted-foreground text-xs ml-1.5">({m.year})</span>`). Series.tsx should use the same pattern. User impact: unnecessary visual clutter, 80px of wasted table width, inconsistency with Movies page.

- **Two sort buttons instead of one** (`Series.tsx:229-258`, `Movies.tsx:267-296`): The spec describes a single "Sort by {Title|Progress}" button (outline, small) that cycles or a column-header-click mechanism. The implementation renders two separate outline buttons ("Sort by Title ↑" and "Sort by Progress ↑"). This is functionally equivalent and arguably clearer for users, but it deviates from the spec's described pattern and adds a second outline button to the controls bar that the spec did not account for.

- **WR-02 advisory not addressed** (`app-sidebar.tsx:86`): `SidebarTrigger` is hidden in collapsed icon mode via `group-data-[collapsible=icon]:hidden`. The carryforward WR-02 note acknowledges this leaves no keyboard-reachable expand affordance other than Cmd/Ctrl+B. The advisory recommends surfacing `aria-keyshortcuts` on `<Sidebar>`. This was marked low-priority; acceptable to carry forward again.

- **Clickable Series table rows lack keyboard affordance** (`Series.tsx:298-299`): The `<tr onClick={() => navigate(...)}>` has no `tabIndex`, `role="button"`, or `onKeyDown` handler. Keyboard users cannot activate row navigation without a mouse. The spec's interaction contract specifies `onClick` but does not explicitly require keyboard support on the `<tr>`. This is a mild a11y gap — adding `tabIndex={0}` and `onKeyDown` to handle Enter/Space would fully close it.

---

### Pillar 3: Color (4/4)

**PASS — Badge token mapping is fully correct per D-06. No unauthorized hex values in component code.**

Token verification against spec:

| Badge | Spec class | Implemented class | Match |
|-------|-----------|------------------|-------|
| Audio | `bg-blue-700/80 text-white border-transparent` | `bg-blue-700/80 text-white border-transparent` | EXACT |
| Source | `bg-amber-600/80 text-white border-transparent` | `bg-amber-600/80 text-white border-transparent` | EXACT |
| VI | `bg-[hsl(var(--primary))]/80 text-primary-foreground border-transparent` | `bg-[hsl(var(--primary))]/80 text-primary-foreground border-transparent` | EXACT |
| LIVE (sidebar) | `bg-emerald-600 text-white border-transparent` | `bg-emerald-600 text-white border-transparent` | EXACT |
| Count (sidebar) | `bg-[hsl(var(--primary))] text-primary-foreground border-transparent` | `bg-[hsl(var(--primary))] text-primary-foreground border-transparent` | EXACT |
| Translated (status chip) | "emerald badge" | `bg-emerald-600/80 text-white border-transparent` | ACCEPTABLE — /80 opacity not spec-locked for status chip |
| Progress fill | `bg-primary` | `bg-primary` | EXACT |

Raw hex audit: `#22c55e` appears only in `app-sidebar.tsx:149` for the footer running dot. This is explicitly sanctioned by Phase-12 spec ("footer dot keeps its existing literal value `bg-[#22c55e]`") and Phase-14 wiring invariants ("Bridge hex tokens stay"). Not a violation.

`index.css:21` contains `#0f1117` in a comment only — no functional hex. Clean.

The `--primary` accent is used only on spec-reserved elements: VI badge, nav count badge, progress fill, `<Button variant="default">` — no accent overuse. 60/30/10 distribution is maintained through CSS variable system.

---

### Pillar 4: Typography (3/4)

**WARNING — Three font weights in use; the contract allows exactly two (400/600).**

Font sizes in use (from grep across all audited files):
- `text-xs` (12px) — badge labels, error inline text, progress fraction, episode key, muted sub-labels
- `text-sm` (14px) — table cell text, column headers, muted Running label
- `text-base` (16px) — empty state headings (wrong role; see below)
- `text-xl` (20px) — page headings

Four sizes. The spec permits: xs, sm, base, xl across Phase-14 elements — technically within the inherited scale. No unauthorized sizes (2xl, 3xl, etc.).

Font weights in use:
- `font-normal` (400) — table column headers (`EpisodeTable:59-66`)
- `font-medium` (500) — empty-state headings (`Series.tsx:264`, `Movies.tsx:303`), table title cells (`Series.tsx:302`), season label in AccordionTrigger (`SeriesDetail.tsx:387`)
- `font-semibold` (600) — all page `<h1>` headings, brand pill, count badge

**The 2-weight contract (400/600) is violated.** `font-medium` (500) appears in four locations:

1. `Series.tsx:264` — `h2.text-base.font-medium` — empty state "No series found" heading (spec: 400)
2. `Movies.tsx:303` — same pattern for "No movies found"
3. `Series.tsx:302` — `span.font-medium` for series title in table rows (acceptable as visual emphasis for data cells — not strictly a typography role violation)
4. `SeriesDetail.tsx:387` — `span.font-medium` for season label in AccordionTrigger (the vendor AccordionTrigger itself applies `font-medium` to its children via `[data-state=open]:font-medium`; the hand-written span duplicates this)

The most clearcut violation is items 1 and 2 — the spec explicitly states "Heading (16px/400/muted)" for the search-empty state. Using weight 500 here introduces a third weight into hand-written app code in defiance of the contract. Item 4 is partially a vendor artifact.

---

### Pillar 5: Spacing (4/4)

**PASS — All named spacing values match the spec scale. No off-grid arbitrary values.**

Spacing verification:

| Contract | Spec value | Implementation | Match |
|----------|-----------|----------------|-------|
| Table cell vertical | `py-2` (8px) | `py-2` on all `<th>` and `<td>` | EXACT |
| Table cell horizontal | `px-4` (16px) | `px-4` on all `<th>` and `<td>` | EXACT |
| Controls bar gap | `gap-3` (12px) | `gap-3` in controls bar divs | EXACT |
| Controls bar → table | `mb-4` (16px) | `mb-4` on controls bar div | EXACT |
| Page content padding | `p-6` from AppShell | Inherited from AppShell `<main>` | CORRECT |
| Translate touch target | `min-h-[44px]` | `min-h-[44px]` on Translate buttons | EXACT |
| Badge gap in cluster | `gap-1` | `gap-1` on badge flex wrapper | EXACT |
| Page sections | `space-y-4` | `space-y-4` on all page roots | EXACT |

Arbitrary width values (`w-[60px]`, `w-[80px]`, `w-[110px]`, `w-[120px]`, `w-[220px]`) are column constraints, not spacing, and are within reasonable bounds. The progress column width is 220px vs. spec's 180px — a 40px overage that gives the progress fraction more breathing room. Not a grid violation.

`text-[8px]` on the dot prefix in SubtitleBadge is an intentional micro-sizing for the decorative dot glyph (not a layout spacing value). Acceptable.

---

### Pillar 6: Experience Design (4/4)

**PASS — All required states are implemented across all three pages. Carryforward items WR-01, WR-03, IN-01 addressed.**

State coverage audit:

**Series.tsx:**
- Loading: Skeleton (heading + search bar + 6 row placeholders) — correct shape
- Fetch error: "Failed to load Series" + Retry button (re-triggers `load()`) — correct
- Sonarr down: "Sonarr unavailable" + "Go to Settings" — correct (uses `data.series.length === 0 && data.errors.some(e => e.source === "sonarr")`)
- Empty after filter: "No series found" + body + "Clear filters" — correct
- Normal: table with progress bars — correct

**Movies.tsx:**
- Loading, Radarr down, fetch error, empty after filter — symmetric with Series, all correct
- Disabled Translate button with tooltip "Source path unavailable" — correct per spec limitation note
- Inline translate error handling present (dead code currently since button is always disabled, but the error display infrastructure is wired)

**SeriesDetail.tsx:**
- Loading: 3-accordion-placeholder Skeletons — correct shape
- 400 (Sonarr disabled): "Sonarr is disabled" + Go to Settings — correct
- 502 / generic error: "Could not load episodes" + Retry + "Back to Series" — correct
- IN-01 guard: `useParams<{ seriesId: string }>()` + `parseInt` + `isNaN` guard — correct; placed after all hooks per React rules
- Episode has_file=false dimming: `opacity-50` — correct
- Episode status=translated: emerald "Translated" badge, no Translate button — correct
- bazarr_available=false: Subtitle column header removed, subtitle cells conditionally absent — correct; verified at `EpisodeTable:63` and `EpisodeTable:98`
- Season-0 "Specials" label and placement last — implemented at `sortedSeasons:221-225`
- Latest season auto-expanded (`defaultValue` array) — correct

**app-sidebar.tsx (NAV-03):**
- WR-01 SidebarGroup wrapper added — correct
- Count badge auto-hides at zero (`{count > 0 && ...}`) — correct
- LIVE badge derivation from `errors[]` — correct; implemented in `LibraryContext.tsx:72-83`
- Both badges hidden in icon mode (`group-data-[collapsible=icon]:hidden`) — correct
- Badge count aria-labels: `"Service connected"` / `"{N} items need Vietnamese translation"` — correct

**WR-02 advisory (not addressed):** SidebarTrigger is hidden in icon mode — no keyboard-operable expand other than Cmd/Ctrl+B. Carried forward per CARRYFORWARD-REVIEW.md; advisory status unchanged.

**Minor note:** The Retry handler in `SeriesDetail.tsx:308-322` duplicates the fetch logic inline (the initial fetch is handled in `useEffect`). This is a minor code-quality issue, not a UX failure — the user can still retry successfully.

---

## Registry Audit

`components.json` is present. UI-SPEC.md lists jolly-ui as pre-vetted (Phase-11 gate). No new third-party registry blocks added in Phase 14. The jolly-ui `table` component was not used (executor chose plain HTML table per D-01 decision gate). No re-vet required since the jolly-ui component was not consumed.

Registry audit: 0 third-party blocks used in Phase 14 implementation, no flags.

---

## Files Audited

- `frontend/src/pages/Series.tsx`
- `frontend/src/pages/Movies.tsx`
- `frontend/src/pages/SeriesDetail.tsx`
- `frontend/src/pages/NotFound.tsx`
- `frontend/src/components/SubtitleBadge.tsx`
- `frontend/src/components/app-sidebar.tsx`
- `frontend/src/contexts/LibraryContext.tsx`
- `frontend/src/index.css`
- `frontend/tailwind.config.js`
- `frontend/src/api/client.ts` (types for SeriesEpisodesResponse)
- `frontend/components.json`
- `.planning/phases/14-new-library-pages-nav-badge-wiring/14-UI-SPEC.md`
- `.planning/phases/12-app-shell-route-restructure/12-UI-SPEC.md`
- `.planning/phases/14-new-library-pages-nav-badge-wiring/14-CARRYFORWARD-REVIEW.md`
