# Phase 15: Reskin Existing Pages - Discussion Log

> **Audit trail only.** Decisions captured in CONTEXT.md. `--auto` run: Claude
> auto-selected from locked research (ARCHITECTURE.md §3/§6/§7), REQUIREMENTS
> (RSK-01, RSK-02), and the Phase-11/12 token + shell contracts. No AskUserQuestion.

**Date:** 2026-06-04
**Phase:** 15-reskin-existing-pages
**Mode:** auto (no user prompts)
**Areas auto-decided:** Reskin order, Reskin approach, Toast→Sonner, Loading/empty/error states, Bridge-token removal, Validation reality

| Area | Auto-selected decision | Rationale / alternative rejected |
|------|------------------------|----------------------------------|
| Reskin order (D-01) | JobLogs→Queue→History→Settings→BibleList→BibleEditor (last) | ARCHITECTURE.md §7 easiest→hardest; prove the system on low-risk pages before the high-risk editor. |
| Approach (D-02) | In-place primitive/token swap, faithful (not rebuild) | RSK-02 demands BibleEditor behaves identically; rebuild risks regressions. |
| Toast (D-03) | Replace Toast.tsx with shadcn Sonner; `<Toaster/>` in AppShell | Sonner vendored Phase 11; idiomatic; removes bespoke code. Alt: reskin Toast.tsx in place (rejected — more custom code). |
| States (D-04) | Skeleton loading + empty + error per page | Explicit RSK-01 requirement. |
| Bridge-token removal (D-05) | Remove 5 legacy tokens from tailwind.config.js LAST; grep bg-[#/text-[# clean + build green | ARCHITECTURE.md §3 step 6; safe only after all pages migrated. |
| Validation reality (D-06) | Reinterpret "tests green" = build-gate + backend pytest + manual UAT | **No frontend test harness exists** (P12 research). Don't plan around a phantom suite; don't introduce vitest mid-reskin (out of scope). Flagged for the planner. |

## Claude's Discretion
Per-page primitive choices/markup, shared-component internal structure (behavior preserved), empty/error copy, shared-component migration order within D-01, where Sonner replaces vs inline messaging.

## Deferred Ideas
Standing up a frontend test harness (out of scope — would be its own initiative); Docker rebuild + smoke test → Phase 16.
