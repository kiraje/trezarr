---
phase: 11
slug: shadcn-foundation-purple-theme
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-03
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> **Phase 11 is infrastructure-only.** No business logic is introduced, so there
> are no unit tests to write. The validation gate is the **build-green + browser
> UAT** combination required by CONTEXT.md decision D-09. Nyquist sampling here
> means: build after every file change; full build + browser UAT before close.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None — no testable business logic introduced this phase |
| **Config file** | none — `frontend/` uses `tsc -b && vite build` as the gate |
| **Quick run command** | `cd frontend && npm run build` |
| **Full suite command** | `cd frontend && npm run build` (= `tsc -b && vite build`) + manual browser UAT (D-09) |
| **Estimated runtime** | ~15–40s for the build; browser UAT is human-paced |

---

## Sampling Rate

- **After every task commit:** Run `cd frontend && npm run build` — it must exit 0 before proceeding to the next file change.
- **After every plan wave:** Full `npm run build` green.
- **Before `/gsd-verify-work`:** Build green AND all D-09 browser-UAT criteria met.
- **Max feedback latency:** ~40 seconds (the build).
- **D-09 gate:** Human visual review — the `--auto` chain HOLDS until human confirmation.

---

## Per-Task Verification Map

| Task | Requirement | Validation Type | Observable Signal | Status |
|------|-------------|-----------------|-------------------|--------|
| `@/` alias + `cn()` + `components.json` | UI-01 | Build gate | `tsc -b` exits 0 resolving `@/lib/utils`; `src/lib/utils.ts` + `components.json` present | ⬜ pending |
| Bulk component install | UI-01 | Build gate | `src/components/ui/` populated (all installed shadcn components + jolly-ui Table); `npm run build` exits 0 | ⬜ pending |
| Existing pages unchanged | UI-01 | Visual inspection | `/queue`, `/settings`, `/bible` render identical to pre-Phase-11 (bridge tokens carry them) | ⬜ pending |
| Purple HSL theme active | UI-02 | Visual inspection | `<html class="dark">` in DevTools; body background resolves to dark **purple** (not `#0f1117`) | ⬜ pending |
| Channel-triple opacity proof | UI-02 | Browser UAT (D-09) | `bg-primary/50` renders half-opacity purple; computed value is a valid `color-mix()`/`rgb()` with 50% alpha | ⬜ pending |
| Purple Button renders | UI-02 | Browser UAT (D-09) | `<Button variant="default">` displays with purple background | ⬜ pending |
| No broken pages | UI-02 | Visual inspection | All existing pages load with no white/unstyled content | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- None — Phase 11 requires no test-file creation. The validation is build + browser UAT.

*Existing infrastructure (the Vite/tsc build) covers all phase requirements that are machine-checkable; the rest are intentional manual visual checks.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dark purple background renders | UI-02 | Color perception is visual; no automated pixel assertion in scope | Open the app in a browser; confirm a dark purple (not blue-black) background with `.dark` active on `<html>` |
| `bg-primary/50` half-opacity | UI-02 | Proves the HSL channel-triple format (the silent-failure guard); visual + DevTools check | Render an element with `bg-primary/50`; confirm it is visibly half-opacity purple and DevTools shows a 50%-alpha computed color |
| Purple `<Button variant="default">` | UI-02 | Confirms the shadcn primary token wiring end-to-end | Render a default Button; confirm purple background |
| Existing pages intact | UI-01 | Regression check is visual across multiple pages | Navigate `/queue`, `/history`, `/settings`, `/bible`; confirm no unstyled/broken content |

These four are the **D-09 human visual-UAT checkpoint** — the `--auto` chain stops here for human sign-off.

---

## Validation Sign-Off

- [x] All tasks have an automated build-gate verify or are explicitly manual-only (D-09)
- [x] Sampling continuity: build runs after every file change (no 3-task gap)
- [x] Wave 0 covers all MISSING references (none required)
- [x] No watch-mode flags (`npm run build` is one-shot)
- [x] Feedback latency < ~40s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
