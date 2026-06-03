# Architecture: v1.1 UI Rework Integration

**Project:** Trezarr v1.1 — shadcn/jolly-ui dashboard
**Researched:** 2026-06-03
**Scope:** How the new UI foundation (shadcn + jolly-ui sidebar shell) and the enriched
episodes backend integrate with the existing React 19 + FastAPI architecture.

---

## Summary

The v1.1 rework layers a shadcn/ui component foundation onto an existing Vite/React 19 SPA
without rebuilding the backend. Four integration seams require careful handling:

1. **Theme migration** — existing flat hex tokens in `tailwind.config.js` must be bridged to
   shadcn CSS variables without breaking the ~15 pages that use those tokens today.
2. **Shell replacement** — the current `AppShell` (TopBar + flat `<nav>`) becomes a
   `SidebarProvider` context tree wrapping a `<Sidebar>` + `<main>` layout; react-router
   route structure needs a layout-route for the outlet.
3. **Route split** — `/library` becomes `/series` + `/movies` + `/series/:id`; the existing
   `SPAStaticFiles` fallback handles all three extensionless paths already.
4. **Backend enrichment** — `GET /api/library/series/{id}/episodes` is modified (not
   replaced) to call `client.episode.get()` for episode *records* (not just episode files),
   cross-reference them with Sonarr `mediaInfo.audioLanguages`, and optionally merge Bazarr
   `BazarrInventoryItem.subtitles`; Bazarr failure must degrade to HTTP 200 with empty
   subtitle badges, matching the existing partial-results pattern.

Build order: foundation first, shell second, backend third, pages last. Each phase must leave
the SPA in a compilable state.

---

## 1. Component / Folder Architecture

### Current layout (before v1.1)

```
frontend/src/
  api/client.ts               <- fetch wrappers + TypeScript interfaces
  components/
    AppShell.tsx              <- TopBar + 192px sidebar + <main>
    ConnectionTestButton.tsx
    FieldHistoryPanel.tsx
    JobTable.tsx
    LockBadge.tsx / LockToggleButton.tsx
    LogViewer.tsx
    MaskedSecretInput.tsx
    PronounCombo.tsx
    ReciprocalSuggestionPanel.tsx
    RetryButton.tsx
    StatusBadge.tsx
    Toast.tsx
  pages/
    BibleEditor.tsx / BibleList.tsx
    History.tsx / Queue.tsx / JobLogs.tsx
    Library.tsx               <- split in v1.1
    Settings.tsx
  App.tsx                     <- route table (BrowserRouter)
  index.css                   <- @tailwind base/components/utilities (3 lines)
  main.tsx
tailwind.config.js            <- hex token extensions under theme.extend.colors
vite.config.ts                <- outDir ../trezarr/web/static, no @ alias yet
```

### v1.1 target layout (additive — do not delete before new code is working)

```
frontend/src/
  api/client.ts               <- MODIFIED: add EpisodeEnrichedRow type, update getSeriesEpisodes
  components/
    ui/                       <- NEW: shadcn generated components land here
      sidebar.tsx             <- npx shadcn@latest add sidebar
      accordion.tsx           <- npx shadcn@latest add accordion
      badge.tsx               <- npx shadcn@latest add badge
      button.tsx              <- npx shadcn@latest add button
      ...                     <- add others as needed per page (table, input, select...)
    app-sidebar.tsx           <- NEW: Trezarr-specific sidebar (nav items, logo, badges)
    AppShell.tsx              <- REPLACED: becomes thin wrapper around SidebarProvider + Outlet
    ConnectionTestButton.tsx  <- RESKIN in place (shadcn Button primitive)
    FieldHistoryPanel.tsx     <- RESKIN in place
    JobTable.tsx              <- RESKIN in place (shadcn Table primitives)
    LockBadge.tsx             <- RESKIN in place (shadcn Badge)
    LockToggleButton.tsx      <- RESKIN in place
    LogViewer.tsx             <- RESKIN in place
    MaskedSecretInput.tsx     <- RESKIN in place (shadcn Input)
    PronounCombo.tsx          <- RESKIN in place (shadcn Select/Combobox)
    ReciprocalSuggestionPanel.tsx <- RESKIN in place
    RetryButton.tsx           <- RESKIN in place
    StatusBadge.tsx           <- RESKIN in place (shadcn Badge)
    Toast.tsx                 <- RESKIN in place (or replace with shadcn Sonner/Toast)
  lib/
    utils.ts                  <- NEW: cn() utility (clsx + tailwind-merge)
  pages/
    Series.tsx                <- NEW: replaces Library series list view
    SeriesDetail.tsx          <- NEW: season-grouped episode table (was drill-in in Library.tsx)
    Movies.tsx                <- NEW: replaces Library movies view
    BibleEditor.tsx           <- RESKIN in place
    BibleList.tsx             <- RESKIN in place
    History.tsx               <- RESKIN in place
    Queue.tsx                 <- RESKIN in place
    JobLogs.tsx               <- RESKIN in place
    Settings.tsx              <- RESKIN in place
  App.tsx                     <- MODIFIED: layout route pattern, new route table
  index.css                   <- MODIFIED: shadcn CSS variable block added
  main.tsx                    <- unchanged
components.json               <- NEW: shadcn config (lives at frontend/components.json)
tailwind.config.js            <- MODIFIED: keep hex tokens as bridge, add CSS-var entries
vite.config.ts                <- MODIFIED: add @ alias (resolve.alias)
```

### Key placement rules

- **`src/components/ui/`** — shadcn-owned; generated by the CLI. Never hand-edit these
  files; re-run `npx shadcn@latest add <component>` to regenerate. Treat as vendor code.
- **`src/lib/utils.ts`** — `cn()` function only. Shadcn's CLI generates this automatically
  on `npx shadcn@latest init`.
- **`src/components/app-sidebar.tsx`** — Trezarr-specific sidebar composition (nav items,
  active-accent logic, series/movies counts). This IS hand-edited.
- **`components.json`** — lives at `frontend/components.json` (same level as `package.json`).
  The CLI uses it to know where to write `ui/` components and where `utils.ts` lives.

---

## 2. App-Shell Architecture: SidebarProvider + React Router

### shadcn sidebar model

shadcn's Sidebar block is a CSS-variable-driven layout that requires a `SidebarProvider`
context. The context manages open/collapsed state and injects `--sidebar-width` and
`--sidebar-width-mobile` custom properties. The Sidebar component uses these variables to set
its own width — do not use fixed `w-48` hardcoded widths alongside it.

The `SidebarProvider` wraps the entire page body. `Sidebar` goes inside it. The `<main>`
content sits as a sibling to `<Sidebar>` inside `SidebarProvider`. This is a
**whole-document** context — not per-route.

### Route restructure

#### Before (v1.0)

```tsx
// App.tsx — AppShell wraps all routes directly via children
<BrowserRouter>
  <AppShell>
    <Routes>
      <Route path="/" element={<Navigate to="/queue" replace />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/queue" element={<Queue />} />
      <Route path="/history" element={<History />} />
      <Route path="/jobs/:id/logs" element={<JobLogs />} />
      <Route path="/library" element={<Library />} />
      <Route path="/bible" element={<BibleList />} />
      <Route path="/bible/:seriesId" element={<BibleEditor />} />
    </Routes>
  </AppShell>
</BrowserRouter>
```

#### After (v1.1)

```tsx
// App.tsx — layout route pattern; AppShell renders <Outlet/>
<BrowserRouter>
  <Routes>
    <Route path="/" element={<AppShell />}>
      <Route index element={<Navigate to="/series" replace />} />
      <Route path="series" element={<Series />} />
      <Route path="series/:seriesId" element={<SeriesDetail />} />
      <Route path="movies" element={<Movies />} />
      <Route path="queue" element={<Queue />} />
      <Route path="history" element={<History />} />
      <Route path="jobs/:id/logs" element={<JobLogs />} />
      <Route path="settings" element={<Settings />} />
      <Route path="bible" element={<BibleList />} />
      <Route path="bible/:seriesId" element={<BibleEditor />} />
    </Route>
  </Routes>
</BrowserRouter>
```

#### AppShell.tsx — v1.1 shape

```tsx
// components/AppShell.tsx
import { SidebarProvider } from "./ui/sidebar";
import { AppSidebar } from "./app-sidebar";
import { Outlet } from "react-router-dom";

export default function AppShell() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="flex-1 overflow-auto bg-background p-6">
        <Outlet />
      </main>
    </SidebarProvider>
  );
}
```

The `<Outlet />` renders the matched child route element. This replaces the `{children}`
prop pattern. The `SidebarProvider` + `Sidebar` handle open/collapsed state internally.

### Nav items and active accent

The left purple active-accent bar is implemented via shadcn's
`data-[active=true]` attribute on `SidebarMenuButton`. Map the active state from
react-router `useLocation` inside `app-sidebar.tsx`, not via NavLink's `isActive` class
(NavLink cannot easily set data attributes on arbitrary shadcn sub-components).

```tsx
// components/app-sidebar.tsx (sketch)
import { useLocation, useNavigate } from "react-router-dom";
import {
  Sidebar, SidebarContent, SidebarMenu, SidebarMenuItem,
  SidebarMenuButton, SidebarGroup, SidebarGroupLabel,
} from "./ui/sidebar";
import { Tv, Film, List, History, BookOpen, Settings } from "lucide-react";

const NAV_ITEMS = [
  { to: "/series",   label: "Series",   icon: Tv },
  { to: "/movies",   label: "Movies",   icon: Film },
  { to: "/queue",    label: "Queue",    icon: List },
  { to: "/history",  label: "History",  icon: History },
  { to: "/bible",    label: "Bible",    icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppSidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  return (
    <Sidebar>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Trezarr</SidebarGroupLabel>
          <SidebarMenu>
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <SidebarMenuItem key={to}>
                <SidebarMenuButton
                  isActive={pathname === to || pathname.startsWith(to + "/")}
                  onClick={() => navigate(to)}
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
```

Use `onClick={() => navigate(to)}` on `SidebarMenuButton` rather than `asChild` + `<a>` to
preserve react-router client-side navigation without fighting the shadcn Radix slot model.

### SPAStaticFiles impact

The existing `SPAStaticFiles` fallback returns `index.html` for any extensionless path not
under `/api` or `/webhook`. The new routes `/series`, `/series/:seriesId`, `/movies` are all
extensionless paths — they are served `index.html` on hard-refresh already. No backend
changes needed for deep-link routing.

---

## 3. Theme Migration: Hex Tokens to shadcn CSS Variables

### The problem

Current state: `tailwind.config.js` defines custom hex tokens under `theme.extend.colors`:
`bg-base`, `bg-surface`, `bg-stripe`, `border`, `text-primary`, `text-muted`, `accent`,
`destructive`. These are referenced both as hardcoded hex strings (e.g., `text-[#e2e6f0]`,
`bg-[#1a1d27]`) AND as semantic class names (e.g., `bg-bg-surface`, `text-text-muted`,
`text-accent`) throughout the ~15 existing pages.

shadcn components expect CSS variables: `bg-background`, `text-foreground`, `bg-sidebar`,
`text-sidebar-foreground`, `bg-primary`, etc., expressed as HSL values in `:root` / `.dark`.

The Trezarr theme is dark-only. The current accent is blue (`#3b82f6`); v1.1 changes it to
purple.

### Migration strategy: bridge period (avoid a broken build)

The safe path is a **bridge**: keep the existing hex tokens AND add the shadcn CSS variable
block simultaneously in `index.css`. Both live side-by-side during the reskin. This means:
- Existing pages continue to compile and render using the old hex tokens.
- New shadcn `ui/` components use CSS variables.
- Reskinned pages migrate from hardcoded hex to semantic CSS-variable class names.
- After all pages are reskinned, remove the bridge (dead hex tokens in `tailwind.config.js`).

### Step 1: Add the `@` path alias (required for shadcn CLI)

`vite.config.ts` must gain a resolve alias before `npx shadcn@latest init` can write
components correctly. The CLI generates imports like `import { cn } from "@/lib/utils"`.

```ts
// vite.config.ts
import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: "../trezarr/web/static",
    emptyOutDir: true,
  },
});
```

Also add to `tsconfig.app.json` (or `tsconfig.json`):
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  }
}
```

### Step 2: `npx shadcn@latest init` in the `frontend/` directory

The CLI writes:
- `frontend/components.json` — project config
- `frontend/src/lib/utils.ts` — the `cn()` function (`clsx` + `tailwind-merge`)
- CSS variable block prepended to `src/index.css`

Run with `cssVariables: true` (required for the sidebar and most shadcn components to work).
Select Tailwind v3 mode — the project uses Tailwind 3.4. Do not upgrade to Tailwind v4 as
part of this milestone (v4 uses `@tailwindcss/vite` plugin instead of `postcss`, which is a
separate migration).

### Step 3: Map Trezarr hex tokens to shadcn CSS variable names

The purple theme replaces the current blue accent. In `src/index.css`, customize the
shadcn-generated CSS variable block for Trezarr's dark-only palette:

```css
/* src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Trezarr is dark-only; all values defined here are dark values */
    --background: 222 47% 7%;          /* #0f1117 ~ bg-base */
    --foreground: 220 20% 91%;         /* #e2e6f0 ~ text-primary */
    --card: 228 28% 12%;               /* #1a1d27 ~ bg-surface */
    --card-foreground: 220 20% 91%;
    --popover: 228 28% 12%;
    --popover-foreground: 220 20% 91%;
    --primary: 271 71% 58%;            /* purple accent */
    --primary-foreground: 0 0% 100%;
    --secondary: 229 24% 15%;          /* #1e2130 ~ bg-stripe */
    --secondary-foreground: 220 20% 91%;
    --muted: 229 24% 15%;
    --muted-foreground: 220 9% 46%;    /* #6b7280 ~ text-muted */
    --accent: 271 71% 58%;             /* purple */
    --accent-foreground: 0 0% 100%;
    --destructive: 0 84% 60%;          /* #ef4444 */
    --destructive-foreground: 0 0% 100%;
    --border: 231 27% 22%;             /* #2d3148 */
    --input: 231 27% 22%;
    --ring: 271 71% 58%;
    /* sidebar-specific vars — shadcn sidebar reads these */
    --sidebar-background: 228 28% 12%;
    --sidebar-foreground: 220 20% 91%;
    --sidebar-primary: 271 71% 58%;    /* active item highlight */
    --sidebar-primary-foreground: 0 0% 100%;
    --sidebar-accent: 229 24% 15%;     /* hover state */
    --sidebar-accent-foreground: 220 20% 91%;
    --sidebar-border: 231 27% 22%;
    --sidebar-ring: 271 71% 58%;
    --radius: 0.375rem;
  }
}
```

Keep the existing `tailwind.config.js` hex token extensions untouched during the bridge
period. The new CSS variables are purely additive.

### Step 4: `tailwind.config.js` — add CSS-variable-backed color names

shadcn components use classes like `bg-background`, `text-foreground`, `bg-primary`, etc.
For Tailwind v3, these must be registered in `tailwind.config.js` under `theme.extend.colors`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],          // shadcn uses .dark class; add class="dark" to <html>
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Legacy bridge tokens (keep until ALL pages reskinned, then remove) ──
        "bg-base":      "#0f1117",
        "bg-surface":   "#1a1d27",
        "bg-stripe":    "#1e2130",
        "text-primary": "#e2e6f0",
        "text-muted":   "#6b7280",
        // NOTE: "border" and "accent" below shadow the legacy plain names
        // but the values are now CSS-variable-backed and render identically in dark mode

        // ── shadcn CSS-variable-backed tokens ──
        background:   "hsl(var(--background))",
        foreground:   "hsl(var(--foreground))",
        card: {
          DEFAULT:    "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        primary: {
          DEFAULT:    "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT:    "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT:    "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT:    "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT:    "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input:  "hsl(var(--input))",
        ring:   "hsl(var(--ring))",
        sidebar: {
          DEFAULT:    "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: {
            DEFAULT:    "hsl(var(--sidebar-primary))",
            foreground: "hsl(var(--sidebar-primary-foreground))",
          },
          accent: {
            DEFAULT:    "hsl(var(--sidebar-accent))",
            foreground: "hsl(var(--sidebar-accent-foreground))",
          },
          border: "hsl(var(--sidebar-border))",
          ring:   "hsl(var(--sidebar-ring))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
```

NOTE: the old `border` was a single hex string under `theme.extend.colors`. Replacing it
with `"hsl(var(--border))"` changes the semantic value — during the bridge period, existing
uses of `border-border` continue to work because the CSS variable resolves to the same color.
Existing `border-[#2d3148]` arbitrary values are unaffected.

### Step 5: Apply `.dark` class to `<html>`

shadcn `darkMode: ["class"]` requires the `.dark` class on the `<html>` element:

```html
<!-- frontend/index.html -->
<html lang="en" class="dark">
```

Without this, all shadcn components render in light mode (white backgrounds on dark page).

### Step 6: Page reskin migration order (safe sequence)

The build never breaks because old hex tokens remain valid throughout.

Recommended order:
1. `components/ui/*` — generated by shadcn CLI (never hand-written)
2. `components/AppShell.tsx` — new shell (the layout route migration)
3. New pages: `Series.tsx`, `SeriesDetail.tsx`, `Movies.tsx` (new code, uses CSS vars natively)
4. Reskin-in-place: `Queue.tsx`, `History.tsx`, `JobLogs.tsx`, `Settings.tsx`, `BibleList.tsx`
5. Reskin-in-place: `BibleEditor.tsx` (largest; defer to last)
6. Shared components: `StatusBadge`, `JobTable`, `LockBadge`, `Toast`, etc.
7. After all pages migrated: remove legacy bridge tokens from `tailwind.config.js`

---

## 4. Backend: Enriched Episodes Endpoint

### Current endpoint (modified in-place)

`GET /api/library/series/{series_id}/episodes` currently calls
`client.episode_file.get(series_id=N)`, which returns episode *file* records. These lack:
authoritative episode number, episode title (only scene name or relative path), `monitored`,
`hasFile`, `mediaInfo.audioLanguages`, and Bazarr subtitle inventory.

### What Sonarr exposes (pyarr)

- `client.episode.get(series_id=N)` — episode RECORDS (one per episode in the series,
  regardless of whether a file exists). Fields: `id` (sonarr episode ID), `seasonNumber`,
  `episodeNumber`, `title`, `monitored`, `hasFile`, `episodeFileId`, `airDateUtc`.
- `client.episode_file.get(series_id=N)` — episode FILE records. Fields: `id`, `seriesId`,
  `seasonNumber`, `relativePath`, `path`, `size`, `mediaInfo.audioLanguages`.
- Join key: `episode.episodeFileId == episodeFile.id`.

### Proposed enrichment strategy

Group-by-season on the **server**. The client renders a season-grouped Accordion; it needs
data pre-grouped. Server-side grouping is the cleaner contract — the season count is a
server-level fact, not something the client should derive.

### Bazarr inventory merge

`BazarrClient.fetch_episode_inventory(sonarr_series_id)` (already exists in `bazarr.py`)
returns `list[BazarrInventoryItem]`. Each item's `arr_id` field is `sonarrEpisodeId` —
the direct join key to `episode.id` from Sonarr's episode record endpoint.

Build a lookup dict: `{bazarr_item.arr_id: bazarr_item.subtitles}`. For each episode, look
up its Bazarr subtitles by `episode.id`. Episodes not in Bazarr's inventory get an empty
`subtitles` list.

### Fail-soft contract

The existing library endpoint pattern: `try/except` with per-source errors in an `errors[]`
list, always HTTP 200. The enriched endpoint must follow the same pattern:
- Sonarr unavailable: HTTP 400 (`sonarr_disabled`) or 502 (PyarrError) — same as today.
- Bazarr unavailable or `bazarr_enabled=False`: HTTP 200, all episodes have `subtitles: []`,
  set `bazarr_available: false` on the response envelope so the UI can suppress the
  subtitle-badge column entirely rather than showing all-empty badges.

### Proposed JSON response contract

```json
{
  "series_id": 42,
  "bazarr_available": true,
  "seasons": [
    {
      "season_number": 1,
      "episodes": [
        {
          "episode_id": 1001,
          "episode_file_id": 5001,
          "season_number": 1,
          "episode_number": 3,
          "episode_key": "S01E03",
          "title": "Episode Title",
          "monitored": true,
          "has_file": true,
          "local_path": "/data/media/Show/Season 1/Show.S01E03.mkv",
          "source_path": "/data/media/Show/Season 1/Show.S01E03.ko.srt",
          "source_lang": "ko",
          "status": "has_source",
          "audio_languages": ["Korean"],
          "subtitles": [
            { "code2": "ko", "code3": "kor", "hi": false },
            { "code2": "vi", "code3": "vie", "hi": false }
          ]
        }
      ]
    }
  ],
  "errors": []
}
```

Field-by-field notes:

| Field | Source | Notes |
|-------|--------|-------|
| `episode_id` | `episode.id` | Bazarr join key |
| `episode_file_id` | `episode.episodeFileId` | null when `has_file=false` |
| `season_number` | `episode.seasonNumber` | Authoritative from Sonarr record, not parsed from filename |
| `episode_number` | `episode.episodeNumber` | Authoritative from Sonarr record |
| `episode_key` | derived | `f"S{season_number:02d}E{episode_number:02d}"` — no regex needed since ints are authoritative |
| `title` | `episode.title` | Episode title, not file scene name |
| `monitored` | `episode.monitored` | UI dims un-monitored episodes |
| `has_file` | `episode.hasFile` | Episodes without files: greyed rows, no Translate button |
| `local_path` | `episodeFile.path` via `apply_path_mapping` | Only present when `has_file=True` |
| `source_path` / `source_lang` / `status` | filesystem glob via `find_source_sub` | Same logic as current endpoint |
| `audio_languages` | `episodeFile.mediaInfo.audioLanguages` | List of strings; empty when no file or no mediaInfo |
| `subtitles` | `BazarrInventoryItem.subtitles` keyed by `sonarrEpisodeId` | Path field omitted — UI only needs `code2` and `hi` for badges; do not expose container paths |
| `bazarr_available` | top-level flag | When false, UI suppresses subtitle badge column |
| `errors` | per-source error list | Matches pattern from `GET /api/library` |

### Backend implementation notes

The current handler calls pyarr synchronously inside an `async def` — this blocks the
event loop. The enriched version calls two Sonarr pyarr methods and one optional Bazarr
httpx method. All pyarr calls (sync) must be wrapped in `asyncio.to_thread()`.

Parallel fetch pattern:

```python
import asyncio
from collections import defaultdict

sonarr_client = build_sonarr_client(settings)

episodes_coro  = asyncio.to_thread(sonarr_client.episode.get, series_id=series_id)
ep_files_coro  = asyncio.to_thread(sonarr_client.episode_file.get, series_id=series_id)
episodes_raw, ep_files_raw = await asyncio.gather(episodes_coro, ep_files_coro)

# Normalize dict responses (pyarr returns a single dict on single-item series)
if isinstance(episodes_raw, dict): episodes_raw = [episodes_raw]
if isinstance(ep_files_raw, dict): ep_files_raw = [ep_files_raw]

# Build episodeFile lookup: episodeFile.id -> episodeFile
ep_file_by_id = {ef["id"]: ef for ef in ep_files_raw}
```

Bazarr merge (fail-soft):

```python
bazarr_by_ep_id: dict[int, list] = {}
bazarr_available = False
if settings.bazarr_enabled:
    try:
        bazarr_client = BazarrClient.from_settings(settings)
        bazarr_items = await bazarr_client.fetch_episode_inventory(series_id)
        bazarr_by_ep_id = {
            item.arr_id: [
                {"code2": s.code2, "code3": s.code3, "hi": s.hi}
                for s in item.subtitles
            ]
            for item in bazarr_items
        }
        bazarr_available = True
    except BazarrError as exc:
        logger.warning("get_series_episodes: Bazarr unavailable — %s", exc)
        errors.append({"source": "bazarr", "error": str(exc)})
```

Season grouping:

```python
seasons: dict[int, list[dict]] = defaultdict(list)
for ep in episodes_raw:
    ep_id = ep.get("id")
    ep_file_id = ep.get("episodeFileId")
    has_file = bool(ep.get("hasFile", False))
    ep_file = ep_file_by_id.get(ep_file_id) if ep_file_id else None

    raw_path = ep_file.get("path", "") if ep_file else ""
    local_path = str(apply_path_mapping(raw_path, settings.path_mappings)) if raw_path else None
    media_info = (ep_file or {}).get("mediaInfo") or {}
    audio_languages = media_info.get("audioLanguages") or []

    season_number = ep.get("seasonNumber", 0)
    episode_number = ep.get("episodeNumber", 0)
    episode_key = f"S{season_number:02d}E{episode_number:02d}"

    source_path = None
    source_lang = None
    status = "nothing"
    if local_path:
        lp = Path(local_path)
        src = find_source_sub(lp, settings.source_lang_priority) if lp.exists() else None
        if src:
            source_path = str(src[0])
            source_lang = src[1]
            vi_found = any(
                (lp.parent / (lp.stem + ext)).exists()
                for ext in (".vi.srt", ".vi.ass", ".vi.vtt")
            )
            status = "translated" if vi_found else "has_source"

    seasons[season_number].append({
        "episode_id": ep_id,
        "episode_file_id": ep_file_id,
        "season_number": season_number,
        "episode_number": episode_number,
        "episode_key": episode_key,
        "title": ep.get("title", ""),
        "monitored": ep.get("monitored", False),
        "has_file": has_file,
        "local_path": local_path,
        "source_path": source_path,
        "source_lang": source_lang,
        "status": status,
        "audio_languages": audio_languages,
        "subtitles": bazarr_by_ep_id.get(ep_id, []),
    })

result = {
    "series_id": series_id,
    "bazarr_available": bazarr_available,
    "seasons": [
        {"season_number": sn, "episodes": seasons[sn]}
        for sn in sorted(seasons)
    ],
    "errors": errors,
}
return JSONResponse(result)
```

Season 0 (Specials) is included — do not filter it. The UI renders it last or with a
"Specials" label.

### Path-mapping for subtitle paths in Bazarr inventory

The existing `_parse_subtitle_entry` in `BazarrClient` already applies `apply_path_mapping`
to subtitle paths (D-105). However, the enriched endpoint strips subtitle paths entirely —
it only returns `code2`, `code3`, and `hi` for badge display. This avoids exposing internal
container paths and is correct: the badge renderer does not need to read any subtitle file.

---

## 5. Data-Fetching Pattern on the Frontend

### Current pattern

`api/client.ts` uses raw `fetch` with `AbortController` timeouts (5s default, 30s for
library endpoints). All wrappers are typed TypeScript interfaces. State management is
`useState` + `useEffect` inside each page component. No cache, no deduplication, no
background refetch.

### Recommendation: keep the fetch layer unchanged; add new types

Do not introduce React Query, SWR, or any other data-fetching library in v1.1. Rationale:
- The existing pattern works consistently across all existing pages.
- SeriesDetail has one data dependency (the enriched episodes endpoint) with no cross-route
  cache sharing requirement. `useState+useEffect` is sufficient.
- Adding a query library mid-milestone requires migrating all existing pages for consistency,
  or accepting two fetch patterns — both are worse than the status quo.
- The 30-second `fetchWithLongTimeout` already handles slow *arr APIs.

**What changes in `client.ts`:** Add new types, update `getSeriesEpisodes` return type.

```typescript
// api/client.ts — new types for enriched episodes endpoint

export interface SubtitleBadge {
  code2: string;
  code3: string;
  hi: boolean;
}

export interface EpisodeEnrichedRow {
  episode_id: number;
  episode_file_id: number | null;
  season_number: number;
  episode_number: number;
  episode_key: string;
  title: string;
  monitored: boolean;
  has_file: boolean;
  local_path: string | null;
  source_path: string | null;
  source_lang: string | null;
  status: "translated" | "has_source" | "nothing";
  audio_languages: string[];
  subtitles: SubtitleBadge[];
}

export interface SeasonGroup {
  season_number: number;
  episodes: EpisodeEnrichedRow[];
}

export interface SeriesEpisodesResponse {
  series_id: number;
  bazarr_available: boolean;
  seasons: SeasonGroup[];
  errors: { source: string; error: string }[];
}

/** GET /api/library/series/{id}/episodes — enriched episode rows, grouped by season. */
export async function getSeriesEpisodes(id: number): Promise<SeriesEpisodesResponse> {
  const resp = await fetchWithLongTimeout(`/api/library/series/${id}/episodes`);
  if (!resp.ok) throw new Error(`GET /api/library/series/${id}/episodes: ${resp.status}`);
  return resp.json();
}
```

Keep the old `EpisodeRow` type until `Library.tsx` is deleted. After deletion, remove
`EpisodeRow` from the file.

---

## 6. Integration Points: New vs. Modified

| Artifact | Status | What Changes |
|----------|--------|-------------|
| `frontend/vite.config.ts` | MODIFIED | Add `resolve.alias` for `@` |
| `frontend/tsconfig.app.json` | MODIFIED | Add `paths: { "@/*": ["./src/*"] }` |
| `frontend/index.html` | MODIFIED | Add `class="dark"` to `<html>` |
| `frontend/tailwind.config.js` | MODIFIED | Add `darkMode: ["class"]`, shadcn CSS-var color entries, `tailwindcss-animate` plugin; keep legacy hex tokens as bridge |
| `frontend/src/index.css` | MODIFIED | Add shadcn `@layer base { :root { ... } }` CSS variable block |
| `frontend/components.json` | NEW | shadcn project config; written by CLI, committed to git |
| `frontend/src/lib/utils.ts` | NEW | `cn()` utility; written by CLI |
| `frontend/src/components/ui/` | NEW | shadcn components; written by CLI per component |
| `frontend/src/components/app-sidebar.tsx` | NEW | Trezarr nav; hand-written |
| `frontend/src/components/AppShell.tsx` | REPLACED | Children prop -> Outlet pattern; wraps SidebarProvider |
| `frontend/src/App.tsx` | MODIFIED | Layout route wrapping; route table (/ -> /series; /library removed; /series, /series/:id, /movies added) |
| `frontend/src/pages/Library.tsx` | DELETED | After Series.tsx + Movies.tsx are complete and tested |
| `frontend/src/pages/Series.tsx` | NEW | Series list view |
| `frontend/src/pages/SeriesDetail.tsx` | NEW | Season-grouped episode Accordion |
| `frontend/src/pages/Movies.tsx` | NEW | Movies list view |
| `frontend/src/pages/Queue.tsx` | MODIFIED | Reskin in place (shadcn primitives) |
| `frontend/src/pages/History.tsx` | MODIFIED | Reskin in place |
| `frontend/src/pages/JobLogs.tsx` | MODIFIED | Reskin in place |
| `frontend/src/pages/Settings.tsx` | MODIFIED | Reskin in place |
| `frontend/src/pages/BibleList.tsx` | MODIFIED | Reskin in place |
| `frontend/src/pages/BibleEditor.tsx` | MODIFIED | Reskin in place (largest; defer to last) |
| `frontend/src/api/client.ts` | MODIFIED | Add new types; update `getSeriesEpisodes` return type |
| `trezarr/web/routes/library.py` | MODIFIED | Enrich `get_series_episodes`; new response shape |
| `trezarr/web/app.py` | UNCHANGED | Router registration order preserved; Pitfall E already handled |
| `trezarr/arr/bazarr.py` | UNCHANGED | `fetch_episode_inventory` already exists and works |
| `trezarr/arr/sonarr.py` | UNCHANGED | `client.episode.get()` already available via pyarr |

---

## 7. Suggested Build Order / Phase Sequencing

Phases are ordered so each ends with a compilable, running SPA. The Docker smoke test comes
last.

### Phase A — Foundation (prerequisite for everything else)

1. Add `@` alias to `vite.config.ts` and `tsconfig.app.json`.
2. Add `tailwindcss-animate`, `class-variance-authority`, `clsx`, `tailwind-merge` to `package.json`.
3. Run `npx shadcn@latest init` inside `frontend/` — produces `components.json`, `src/lib/utils.ts`, CSS variable block in `index.css`.
4. Customize CSS variables in `index.css` for Trezarr's dark purple theme.
5. Update `tailwind.config.js` with `darkMode: ["class"]`, CSS-var color entries, animate plugin. Keep legacy hex tokens.
6. Add `.dark` class to `<html>` in `index.html`.
7. Add core shadcn components: `npx shadcn@latest add sidebar accordion badge button table input select`.
8. Add jolly-ui components as needed via their CLI URL pattern.
9. Verify `npm run build` passes. No page content changes yet — just infrastructure.

Integration point: `src/lib/utils.ts` and `src/components/ui/` are now available. No
existing page references them yet. The SPA still loads and navigates correctly.

### Phase B — App Shell (blocks all subsequent page work)

1. Write `src/components/app-sidebar.tsx`.
2. Rewrite `src/components/AppShell.tsx` — `SidebarProvider` + `<AppSidebar>` + `<Outlet>`.
3. Update `src/App.tsx`:
   - Migrate to layout route pattern.
   - Add `/series`, `/series/:seriesId`, `/movies` routes pointing to stub pages initially.
   - Keep `/library` pointing to `Library.tsx` temporarily (or redirect `/library` -> `/series` to preserve existing direct links).
   - Change `/` redirect from `/queue` to `/series`.
4. Write stub `Series.tsx`, `SeriesDetail.tsx`, `Movies.tsx` (minimal placeholders that render a heading only).
5. Verify `npm run build` passes. All existing pages still load inside the new shell.

Integration point: react-router layout route is the joining seam. After this phase, all
subsequent page changes are isolated.

### Phase C — Backend Enrichment (can run in parallel with Phase B)

1. Modify `get_series_episodes` in `library.py`:
   - Wrap pyarr calls in `asyncio.to_thread()`.
   - Add `client.episode.get(series_id=N)` call alongside existing `client.episode_file.get()`.
   - Build episode-file lookup by ID.
   - Optionally fetch Bazarr inventory (fail-soft).
   - Join, filesystem-check source subs, build season groups.
   - Return new JSON shape as specified above.
2. Update `EpisodeRow` -> `EpisodeEnrichedRow` + `SeriesEpisodesResponse` types in `client.ts`.
3. Update `getSeriesEpisodes` return type.
4. Run backend tests; update test fixtures for the new response shape.

Integration point: the API contract (section 4) must be stable before `SeriesDetail.tsx`
is fully implemented. Phase B stub and Phase C can proceed in parallel; `SeriesDetail.tsx`
only needs the real contract when it moves from stub to full implementation.

### Phase D — New Library Pages

1. Implement `Series.tsx` — series list, card or table layout, each item navigates to `/series/:id`.
2. Implement `SeriesDetail.tsx`:
   - Calls `getSeriesEpisodes(seriesId)` where `seriesId` comes from `useParams()`.
   - Renders shadcn Accordion grouped by season (`season_number`).
   - Each episode row: Translate action, episode number, title, audio badge, subtitle-language badges (amber for non-VI source langs, purple for VI, VI:HI when `hi=true`).
   - When `bazarr_available=false`, suppresses the subtitle badge column.
3. Implement `Movies.tsx` — movies list with Translate buttons.
4. Delete `Library.tsx` and remove the `/library` route. Remove old `EpisodeRow` type.
5. Verify `npm run build` and smoke test these pages against the live deployment.

Integration point: `SeriesDetail.tsx` navigates from `Series.tsx` via `useNavigate` (not
the old `setSelectedSeries` internal state). The episode URL is bookmarkable.

### Phase E — Reskin Existing Pages

Reskin-in-place in any order. Each file change is isolated.

Recommended sequence (easiest to hardest):
1. `JobLogs.tsx` — simple log viewer
2. `Queue.tsx` / `History.tsx` — table + status badges
3. `Settings.tsx` — form inputs + connection-test buttons
4. `BibleList.tsx` — series list with nav
5. `BibleEditor.tsx` — largest; four-section editor with locks, address map, pronouns, overrides

Remove legacy hex bridge tokens from `tailwind.config.js` only after ALL pages are reskinned
(verify with Tailwind's unused-class scan or by grepping for `bg-[#`, `text-[#`).

### Phase F — Docker Rebuild and Smoke Test

1. Multi-stage Docker build (node -> python:3.12-slim), `npm run build` writes to `trezarr/web/static/`.
2. Run container on port 6868 against the live deployment (Sonarr/Radarr/Bazarr at 192.168.5.42).
3. Verify: SPA loads, sidebar navigates, `/series` shows real Sonarr data, episode detail shows season-grouped rows with audio + subtitle badges, Translate button enqueues and navigates to `/queue`.

---

## 8. Critical Path and Risks

### Blocker: `@` alias missing before `npx shadcn@latest init`

Must be done in Phase A. If the alias is missing, all shadcn-generated component imports
(`import { cn } from "@/lib/utils"`) break at TypeScript compile time and the Vite build
fails immediately.

### Risk: Tailwind v4 vs v3 — do not upgrade

shadcn's Context7 docs show v4 patterns (`@tailwindcss/vite`, `@import "tailwindcss"`,
`@theme inline`). The project uses Tailwind 3.4 with `postcss` and `tailwind.config.js`.
When running `npx shadcn@latest init`, explicitly select or confirm Tailwind v3 mode. If
the init incorrectly adds v4-style imports, the PostCSS pipeline will fail.

### Risk: pyarr `episode.get()` blocks the event loop

The current handler calls pyarr synchronously in an `async def` — this is a latent bug.
The enriched version adds two more synchronous calls. All three must be wrapped in
`asyncio.to_thread()`. Failure to do this causes noticeable event-loop blocking under load
(visible as the UI becoming unresponsive during library loads).

### Risk: `darkMode: ["class"]` without `.dark` on `<html>`

If `.dark` is missing from `<html>`, all shadcn components render light-mode colors (white
card backgrounds, black text). This is the most visually obvious failure mode and easy to
miss in a headless build check. Verify in a browser after Phase A.

### Risk: AppShell `children` -> `Outlet` breaks any tests that render AppShell

Check whether any test file mounts `<AppShell><SomePage/></AppShell>`. The children prop
no longer exists after Phase B. Frontend tests (if any) that render the full shell need
updating. Backend tests are unaffected.

### Risk: Bazarr `fetch_episode_inventory` param format

The existing `fetch_episode_inventory` uses `params=[("seriesid[]", sonarr_series_id)]`
(list-form). This differs from `fetch_episodes` which uses `params={"seriesid": N}`. If
the real Bazarr instance returns empty data with the `seriesid[]` form, try the unbracketed
form. Verify against the live Bazarr at 192.168.5.42 during Phase C integration testing.

### Risk: `components.json` `tailwind.config` path on Tailwind v3

When `cssVariables: true` is set in `components.json`, the shadcn CLI looks for
`tailwind.config.js` at the path specified in `components.json`. Ensure the path matches
exactly: `"tailwind": { "config": "tailwind.config.js" }`.

---

## Sources

- Context7 `/shadcn-ui/ui` — `SidebarProvider`, `SidebarMenuButton`, `Collapsible`,
  `Accordion`, `components.json` shape, CSS variable names, `--sidebar-*` CSS variables,
  Tailwind v3 theming, `cssVariables: true` config, Vite installation via
  `npx shadcn@latest init -t vite`, `resolve.alias` requirement — HIGH confidence
- [jollyui.dev/docs/installation](https://www.jollyui.dev/docs/installation) — jolly-ui
  requires same shadcn init prerequisites (`clsx`, `tailwind-merge`, `class-variance-authority`,
  `tailwindcss-animate`), installs via `npx shadcn@latest add <jolly-ui-url>` — MEDIUM confidence
- [github.com/jolbol1/jolly-ui](https://github.com/jolbol1/jolly-ui) — jolly-ui uses
  React Aria (not Radix), is shadcn-compatible, copy-paste component model — MEDIUM confidence
- Trezarr source: `trezarr/arr/bazarr.py` — `fetch_episode_inventory` exists, uses
  `sonarrEpisodeId` as join key, already applies `apply_path_mapping` (D-105) — HIGH confidence
- Trezarr source: `trezarr/web/routes/library.py` — current endpoint uses episode FILE
  records only; Bazarr not integrated; latent sync-in-async pyarr call — HIGH confidence
- Trezarr source: `trezarr/web/app.py` — `SPAStaticFiles` fallback handles all extensionless
  paths not under `/api` or `/webhook`; no backend changes needed for new frontend routes — HIGH confidence
- Trezarr source: `frontend/src/App.tsx` — current route table, `children` prop pattern on
  AppShell — HIGH confidence
- Trezarr source: `frontend/tailwind.config.js` — current hex tokens, no `darkMode`, no CSS
  variable entries — HIGH confidence
- react-router-dom v6 layout route pattern — `<Route element={<Layout/>}><Route .../></Route>`
  with `<Outlet>` replacing `{children}` — HIGH confidence (well-established RRv6 pattern)
