# Phase 11: shadcn Foundation & Purple Theme - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-03
**Phase:** 11-shadcn-foundation-purple-theme
**Mode:** `--auto` (manager-dispatched; all gray areas auto-resolved to research-backed defaults)
**Areas discussed:** Purple identity, Background tint, Component install scope, Phase-end verification

---

## Purple Identity

| Option | Description | Selected |
|--------|-------------|----------|
| `270 70% 60%` (STACK.md vivid violet) | Brighter, slightly bluer violet | ✓ |
| `271 71% 58%` (ARCHITECTURE.md) | Marginally redder + darker | |

**Auto choice:** `270 70% 60%` (recommended default; first-listed in research SUMMARY).
**Notes:** Exact per-token values are visually tuned in-browser at the Phase-11 human-verify gate (D-09); `270 70% 60%` is the starting anchor, not frozen. Channel-triple format (no `hsl()` wrapper) locked to protect opacity modifiers.

---

## Background Tint

| Option | Description | Selected |
|--------|-------------|----------|
| Purple-tinted dark `--background` | Whole app root reads purple | ✓ |
| Keep blue-black `#0f1117` | Lower visual change | |

**Auto choice:** Purple-tinted dark.
**Notes:** Success Criterion 2 explicitly requires a "dark purple background." Legacy `bg-base`/`bg-surface` panels stay blue-black via bridge tokens (zero regression on existing pages); the purple shows at the app root.

---

## Component Install Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Bulk-install full set now | All shadcn components + jolly-ui Table in one foundation commit | ✓ |
| Install per-phase | Button now, others as later phases need them | |

**Auto choice:** Bulk-install (research-specified list).
**Notes:** One clean vendor-code commit, no per-phase churn. `init` pinned to `2.10.0`; `add` may use `@latest`. `legacy-peer-deps=true` before first `add`; treat `src/components/ui/` as vendor code.

---

## Phase-End Verification

| Option | Description | Selected |
|--------|-------------|----------|
| Human visual-UAT checkpoint | Browser screenshot review of theme + Button + opacity | ✓ |
| Automated build-only | Green `npm run build` + Button render smoke check | |

**Auto choice:** Human visual-UAT checkpoint.
**Notes:** UI hint: yes; consistent with phases 08/09/10. The `--auto` chain HOLDS at this gate rather than auto-closing with pending UAT (per the auto-chain-hold-for-human-UAT preference).

## Claude's Discretion

- Exact non-anchor token shades (secondary/accent/popover/input), precise `--background` lightness, and `components.json` style/baseColor — finalized at the D-09 gate.

## Deferred Ideas

- jolly-ui Table beta stability evaluation → Phase 14.
- Removing legacy bridge tokens from `tailwind.config.js` → Phase 15.
