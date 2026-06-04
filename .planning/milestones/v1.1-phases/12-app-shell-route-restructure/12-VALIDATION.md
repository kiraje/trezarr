---
phase: 12
slug: app-shell-route-restructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-03
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from 12-RESEARCH.md §Validation Architecture. Phase 12 is a client-side
> shell/routing change; there is **no frontend test harness** in the project
> (verified: no vitest/jest/@testing-library, no `test` script in
> `frontend/package.json`). The automated gate is `npm run build` (strict
> `tsc -b` + `vite build`); behavioral and visual contracts are manual UAT,
> mirroring 12-UI-SPEC §Phase-End Verification Contract. Standing up a test
> framework is out of scope (no requirement asks for it; Phases 1–11 shipped on
> build-gate + manual UAT).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | **NONE (frontend)** — no vitest/jest/@testing-library installed; no `test` script |
| **Config file** | none |
| **Quick run command** | `cd frontend && npm run build` |
| **Full suite command** | `cd frontend && npm run build` |
| **Estimated runtime** | ~10–25 seconds (tsc -b + vite build) |

---

## Sampling Rate

- **After every task commit:** `cd frontend && npm run build` (must exit 0; `tsc -b` strict clean; `trezarr/web/static/` populated)
- **After every plan wave:** `cd frontend && npm run build`
- **Before `/gsd-verify-work`:** Build green **and** the full browser UAT checklist (below) confirmed
- **Max feedback latency:** ~25 seconds (build)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-routes | (planner) | 1 | NAV-02 | — | N/A (literal `/series` redirect target; no open redirect) | build (proxy) | `cd frontend && npm run build` | ✅ build script | ⬜ pending |
| 12-shell | (planner) | 1 | NAV-01 | T-XSS | `:seriesId` echoed only via auto-escaped JSX text node | build (proxy) | `cd frontend && npm run build` | ✅ build script | ⬜ pending |
| 12-sidebar | (planner) | 1 | NAV-01 | — | N/A | build (proxy) + manual UAT | `cd frontend && npm run build` | ✅ build script | ⬜ pending |
| 12-stubs | (planner) | 1 | NAV-02 (SC-4) | — | N/A | build (proxy) + manual UAT | `cd frontend && npm run build` | ✅ build script | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Build is a **compile-correctness proxy** (strict TS catches the integration/wiring class of failures). All behavioral + visual acceptance is captured under Manual-Only Verifications below. The planner should keep task granularity such that no more than the build-gate runs automatically — there is no unit layer to sample.

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.* No test framework is required or expected for this phase; introducing vitest is out of scope. The automated gate is the existing `npm run build`; behavioral/visual verification is the documented manual UAT checklist.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `/` redirects to `/series` | NAV-02 | No frontend test harness; router behavior | Visit `/`, observe redirect to `/series` |
| Deep-link refresh on all 6 routes + `/series/:id` | NAV-02 | SPA fallback is a runtime/server behavior | Hard-refresh each of `/series`, `/movies`, `/queue`, `/history`, `/bible`, `/settings`, `/series/1` → correct page renders |
| Nav exposes exactly the 6 items in order; `/library` NOT in nav but reachable | NAV-02 | Visual + route reachability | Inspect sidebar order; visit `/library` directly → existing Library page still renders |
| Full-height sidebar with brand (Captions glyph + "TREZARR" pill) on every page | NAV-01 | Visual contract | Observe sidebar header on each route |
| **Active item shows a left 2px purple accent bar** (headline check — vendor provides filled bg only) | NAV-01 | Visual; vendor `data-[active]` lacks the bar — must be added via className | Navigate sections; confirm a purple **left border bar** on the active item, not merely a background tint |
| Existing pages (Queue/History/Settings/BibleList/BibleEditor/JobLogs) functional inside the shell | SC-3 | No regressions; interactive behavior | Navigate each; verify it loads and core actions work |
| Stub pages `/series`, `/series/:id`, `/movies` render a heading with no console errors | SC-4 | Visual + console | Visit each; DevTools console clean |
| Cmd/Ctrl+B and `SidebarRail` collapse to a 48px icon rail; accent bar still shows; `sidebar_state` cookie persists across reload | D-01 | Interaction + persistence | Toggle collapse; reload; confirm persisted collapsed/expanded state |
| Green "Running" dot in `SidebarFooter`; label hidden when collapsed | D-02 | Visual | Observe footer expanded and collapsed |

---

## Validation Sign-Off

- [ ] Build-gate (`npm run build`) is the automated verify for every code task (no unit layer exists)
- [ ] Sampling continuity: build runs after every task commit (no 3-task automated gap)
- [ ] Wave 0 covers all MISSING references — N/A (no test infra required)
- [ ] No watch-mode flags (build is one-shot)
- [ ] Feedback latency < 25s
- [ ] `nyquist_compliant: true` set in frontmatter after plan-checker/Nyquist sign-off

**Approval:** pending
