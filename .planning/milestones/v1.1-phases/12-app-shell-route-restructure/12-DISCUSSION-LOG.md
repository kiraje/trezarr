# Phase 12: App Shell + Route Restructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-03
**Phase:** 12-app-shell-route-restructure
**Areas discussed:** Sidebar behavior, Top bar & status dot, /library during transition, Brand glyph

---

## Sidebar behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Icon-rail collapsible | `collapsible="icon"`: shrinks to a ~48px icon-only rail (nav stays visible), reclaims width for P14 tables/accordions; cookie-persisted; Cmd/Ctrl+B + rail toggle; mobile auto-Sheet. | ✓ |
| Fixed always-open | `collapsible="none"`: permanent ~256px column, no toggle/hidden state; closest to today's fixed 192px nav; lowest-regression. | |
| Offcanvas (shadcn default) | Slides fully off-screen behind a trigger; max content width but nav hidden when closed; mobile-oriented. | |

**User's choice:** Icon-rail collapsible (recommended).
**Notes:** Default expanded, cookie persistence, keep rail + Cmd/Ctrl+B (no top-bar trigger since the TopBar is removed). Mobile is not a primary target but must not break.

---

## Top bar & status dot

| Option | Description | Selected |
|--------|-------------|----------|
| Drop TopBar; dot → sidebar footer | Remove the 48px header (sidebar owns the brand per NAV-01); relocate the green "service running" dot into a `SidebarFooter` row. | ✓ |
| Keep a slim top bar | Retain a short header strip for the status dot / collapse trigger; brand still moves to sidebar. More chrome. | |
| Drop TopBar and the dot | Remove both; rely on Settings connection tests for status. Loses the at-a-glance signal. | |

**User's choice:** Drop TopBar; dot → sidebar footer (recommended).
**Notes:** In Phase 12 the dot keeps its current generic "server is serving" semantics — NOT the NAV-03 LIVE/connection-aware badge (Phase 14). Collapsed state shows just the dot.

---

## /library during transition

| Option | Description | Selected |
|--------|-------------|----------|
| Keep /library → Library.tsx reachable | Leave the working library page mounted at /library (removed from nav) through P12–13; Phase 14 deletes it. Live app never loses a working library mid-milestone. | ✓ |
| Redirect /library → /series now | /library becomes an alias to the /series stub; cleaner table but real library goes dark until P14. | |
| Drop /library entirely | Remove the route; old bookmarks fall through SPA fallback to /series. | |

**User's choice:** Keep /library → Library.tsx reachable (recommended).
**Notes:** Does not violate NAV-02 — nav no longer exposes /library; this is a transitional alias removed in Phase 14. Library.tsx is untouched (no reskin) this phase.

---

## Brand glyph

| Option | Description | Selected |
|--------|-------------|----------|
| lucide Captions glyph + TREZARR pill | lucide icon glyph in `--sidebar-primary` purple beside an uppercase "TREZARR" pill; zero new assets; satisfies NAV-01. | ✓ |
| Text-only TREZARR pill | No glyph — just the styled pill; simplest, but NAV-01 wants a glyph. | |
| You decide the icon at build | Glyph + pill, Claude picks the icon at implementation, finalized at the UI gate. | |

**User's choice:** lucide Captions glyph + TREZARR pill (recommended).
**Notes:** `Captions` preferred; `Languages` acceptable fallback if it reads poorly small. Collapsed rail shows just the glyph. Final glyph choice finalized at the UI verify gate.

---

## Claude's Discretion

- Exact stub-page content for Series/SeriesDetail/Movies (single heading sufficient; optional muted "Coming in Phase 14" subline).
- Exact SidebarHeader/SidebarFooter markup, spacing, and pill styling within the Phase-11 purple token system.
- Whether to also render a `SidebarTrigger` in the header in addition to the rail.
- Final glyph choice between `Captions` and `Languages`.

## Deferred Ideas

- NAV-03 nav-row count badges + LIVE *arr-connection badge → Phase 14.
- Deleting Library.tsx and removing the /library route → Phase 14.
- Reskinning existing pages onto shadcn + removing legacy bridge tokens → Phase 15.
