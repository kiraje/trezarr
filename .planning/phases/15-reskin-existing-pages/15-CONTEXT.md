# Phase 15: Reskin Existing Pages - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** auto (decisions auto-selected from locked research/requirements; no user prompts)

<domain>
## Phase Boundary

Reskin the six **existing** pages — Queue, History, Settings, Bible List, JobLogs,
and the Bible Editor — **in place** onto shadcn primitives, swapping the legacy
hex/bridge-token styling for the Phase-11 CSS-variable purple system, then remove
the legacy bridge tokens from `tailwind.config.js` once every page is clean. The
Bible Editor (highest regression risk) is reskinned last and must behave
identically. No behavior or route changes — visual/token migration only.

**In scope (RSK-01, RSK-02):**
- Reskin pages: `Queue.tsx`, `History.tsx`, `Settings.tsx`, `BibleList.tsx`,
  `JobLogs.tsx`, `BibleEditor.tsx` — onto shadcn `Card`/`Button`/`Input`/`Table`/
  `Tabs`/`Badge`/`Select`/`Skeleton` + CSS-var tokens (RSK-01, RSK-02)
- Reskin the shared components they use: `StatusBadge`, `JobTable`, `LockBadge`,
  `LockToggleButton`, `PronounCombo`, `FieldHistoryPanel`, `ReciprocalSuggestionPanel`,
  `RetryButton`, `ConnectionTestButton`, `MaskedSecretInput`, `LogViewer`, `Toast`
- Each page shows loading / empty / error states (RSK-01)
- Remove the 5 legacy bridge tokens from `tailwind.config.js` after all pages pass;
  `grep 'bg-[#' / 'text-[#'` in `src/` returns nothing

**Out of scope (later phase / done):**
- New library pages (Series/SeriesDetail/Movies) + nav badges → done in Phase 14
- The shell / routes / theme tokens → done in Phases 11–12 (consume only)
- Docker rebuild + live smoke test → Phase 16
- Any backend change, any behavior/route change to the reskinned pages

</domain>

<decisions>
## Implementation Decisions

### Reskin Order (risk-sequenced)
- **D-01:** Reskin easiest → hardest per `research/ARCHITECTURE.md §3 step 6 / §7
  Phase E`: **JobLogs → Queue → History → Settings → BibleList → BibleEditor
  (last)**. Shared components are reskinned alongside the first page that uses
  them. BibleEditor is the largest/highest-risk surface (5 tabs, locks, pronoun
  combos, address map, overrides) — defer to last so the badge/token system is
  proven on lower-risk pages first.

### Reskin Approach
- **D-02:** **In-place primitive swap (faithful reskin), NOT a rebuild.** Replace
  hardcoded hex (`bg-[#…]`, `text-[#…]`) and legacy semantic classes
  (`bg-bg-surface`, `text-text-muted`, etc.) with shadcn primitives + CSS-var
  tokens (`bg-card`, `text-foreground`, `bg-primary`, `border-border`…). Preserve
  every behavior, prop, and DOM contract. The BibleEditor must render and behave
  **identically** to pre-reskin (RSK-02).

### Toast → Sonner
- **D-03:** Replace the custom `Toast.tsx` with the shadcn **Sonner** toast
  (`sonner.tsx` vendored in Phase 11). Mount `<Toaster />` once in `AppShell`
  (P12) and migrate existing toast call-sites to sonner's `toast()` API. Rationale:
  Sonner is the shadcn-idiomatic toast, already installed, and removes bespoke code.

### Loading / Empty / Error States (RSK-01)
- **D-04:** Every reskinned page renders three states: **loading** (shadcn
  `Skeleton`), **empty** (muted message), and **error** (a card with a retry
  affordance where the page already supports refetch). This is an explicit RSK-01
  requirement, not optional polish.

### Bridge-Token Removal (final task)
- **D-05:** Only **after all six pages + shared components are reskinned**, remove
  the 5 legacy bridge tokens (`bg-base`, `bg-surface`, `bg-stripe`, `text-primary`,
  `text-muted`) from `tailwind.config.js`. Verify with `grep -rn 'bg-\[#\|text-\[#'
  frontend/src/` returning nothing AND a green `npm run build`. This is the last
  task of the phase (and of the v1.1 token migration).

### Validation Reality (RSK-02 — IMPORTANT discrepancy)
- **D-06:** RSK-02 and the ROADMAP SC2 say the Bible Editor reskin is "confirmed by
  the existing test suite (all tests green)" — but **there is NO frontend test
  harness** in this project (Phase-12 research verified: no vitest/jest/
  @testing-library, no `test` script). Do NOT plan around a non-existent frontend
  suite and do NOT introduce one mid-reskin (out of scope; risky; no requirement
  asks for it). Reinterpret "tests green" as the project's established posture:
  **(a)** `cd frontend && npm run build` green (strict `tsc -b` + `vite build`)
  after every page, **(b)** the **backend** pytest suite (`uv run pytest tests/ -q`)
  — which covers the Bible API the editor calls — stays green, and **(c)** manual
  browser UAT that the BibleEditor's 5 tabs, lock badges/provenance, field-history
  panels, and pronoun combos behave identically. Flag this discrepancy to the
  planner so the BibleEditor task's acceptance criteria are build-gate + backend
  tests + manual UAT, not a phantom frontend suite.

### Claude's Discretion
- Exact per-page primitive choices and markup; whether to keep or replace each
  shared component's internal structure (must preserve behavior); empty/error copy;
  the order shared components are migrated within D-01; whether Sonner replaces or
  the page keeps inline status messaging where a toast wasn't used.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 Research & inherited system
- `.planning/research/ARCHITECTURE.md` §3 step 6 (safe reskin order, bridge removal
  last), §7 Phase E (easiest→hardest sequence, BibleEditor last), §6 (per-file
  RESKIN-in-place artifact table for all existing pages + shared components).
- `.planning/phases/11-shadcn-foundation-purple-theme/11-CONTEXT.md` + `11-UI-SPEC.md`
  — the bridge-token policy (the 5 legacy hex tokens removed HERE), the CSS-var
  token system replacing them, installed primitives, "vendor `ui/` never hand-edit".
- `.planning/phases/12-app-shell-route-restructure/12-CONTEXT.md` — `AppShell`
  (where the Sonner `<Toaster/>` mounts); the shell is done, pages reskin inside it.

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — RSK-01 (5 pages reskinned w/ loading/empty/error),
  RSK-02 (BibleEditor in-place; locking semantics + behavior unchanged; existing
  tests stay green — see D-06 discrepancy).
- `.planning/ROADMAP.md` §"Phase 15" — goal + 3 success criteria (no visible legacy
  hex; BibleEditor identical with all 5 tabs/locks/history/combos; `grep bg-[#`/
  `text-[#` clean + bridge tokens removed from tailwind.config.js).

### Existing code baseline (every file reskinned in place)
- `frontend/src/pages/`: `Queue.tsx`, `History.tsx`, `Settings.tsx`, `BibleList.tsx`,
  `JobLogs.tsx`, `BibleEditor.tsx`.
- `frontend/src/components/`: `StatusBadge.tsx`, `JobTable.tsx`, `LockBadge.tsx`,
  `LockToggleButton.tsx`, `PronounCombo.tsx`, `FieldHistoryPanel.tsx`,
  `ReciprocalSuggestionPanel.tsx`, `RetryButton.tsx`, `ConnectionTestButton.tsx`,
  `MaskedSecretInput.tsx`, `LogViewer.tsx`, `Toast.tsx` (→ Sonner).
- `frontend/tailwind.config.js` — the 5 bridge tokens to remove in the final task.
- `frontend/src/components/ui/` — vendor primitives to compose onto (never edit).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- All shadcn primitives needed are vendored (Phase 11): Card, Button, Input, Table,
  Tabs, Badge, Select(dropdown-menu), Skeleton, Sonner, Tooltip, Separator, Sheet.
- The Phase-14 badge renderer (amber/purple/blue + a11y) can be reused where these
  pages show status/subtitle badges (e.g. StatusBadge).

### Established Patterns
- Bridge period (Phase 11): legacy hex tokens still valid until THIS phase removes
  them — so pages compile throughout; reskin one page at a time, build after each.
- No frontend test harness (Phase-12 research) → validation = `npm run build` +
  manual UAT + the backend pytest suite (D-06). Backend Bible API tests under
  `tests/web/` cover the editor's data contract.
- Strict TS; build = `tsc -b && vite build`; vendor `ui/` is never hand-edited.

### Integration Points
- BibleEditor is the deepest surface — it consumes the Bible API (Phase 8) via
  `client.ts`; reskin must not alter any request/lock/provenance behavior.
- Sonner `<Toaster/>` mounts in `AppShell` (P12); toast call-sites across pages
  migrate to `toast()`.

</code_context>

<specifics>
## Specific Ideas

- The bridge-token removal + `grep bg-[#`/`text-[#` clean is the phase's definition
  of done for the token migration — make it the explicit final task with a build gate.
- BibleEditor last, and its acceptance must be build + backend-tests + manual UAT
  (NOT a frontend test suite — it doesn't exist; see D-06).
- Reskin is token/primitive swap only — resist any "while we're here" behavior change.

</specifics>

<deferred>
## Deferred Ideas

- Standing up a frontend test harness (vitest/@testing-library) — explicitly out of
  scope; would be its own initiative, not a reskin task (D-06).
- Docker rebuild + live smoke test → Phase 16.

None outside the roadmapped phases — discussion stayed within phase scope.

</deferred>

---

*Phase: 15-reskin-existing-pages*
*Context gathered: 2026-06-04 (auto mode)*
