# Core Quality Campaign — Consistency + Throughput (measure-first)

**Date:** 2026-06-12
**Status:** Approved (design discussed and accepted in session)
**Baseline:** deployed image `814f370` (all 5 audit-l74 findings fixed, 548 tests green, MK Bible repaired)

## Problem

The user wants to improve Trezarr's two core qualities:

1. **Consistency** — cross-episode pronoun/name/term stability (the core moat) is still
   only single-episode-proven; the cross-episode proving runs on the fixed code are pending.
   Single-episode quality (pronoun correctness, leaks, naturalness) is also in scope.
2. **Performance** — translation feels slow. Constraint clarified: **overnight batch is
   acceptable**; the real goals are *throughput per night* and *run stability*, not latency.

Hard constraints:

- **Keep deepseek** (`api.deepseek.com`) as the endpoint. Optimize around it.
- **Concurrency stays at 4** — empirically the deepseek ceiling (8 degrades quality).
- Consistency is non-negotiable: no performance change may risk the moat.

## Approach (chosen: measure-first, sequential)

Rejected alternatives: parallel perf+proving tracks (contaminates the audit baseline);
pipeline re-architecture / pass merging (highest moat risk, unjustified when overnight
is acceptable).

Hard ordering rule: **no translation-affecting code changes until Steps 1–2 complete**,
so the audit baseline stays clean. One proving run serves both goals (consistency audit
+ performance profile from the same logs).

## Steps

### Step 0 — Instrumentation pre-requisite (NEW, from pre-check)

Pre-check finding (2026-06-12): the pipeline has **no per-pass timing and no token-usage
logging** (`trezarr/translate/`, `trezarr/llm/`, `trezarr/jobs/` contain no
`perf_counter`/`elapsed`/`usage` instrumentation). Without it, Step 3 cannot answer
"where does the time go."

Add lightweight observability **before** the proving runs, via `/gsd-quick`:

- Per-pass wall-clock duration (Pass 1–4) logged per file.
- Per-LLM-call: duration, retry count, and `usage` (prompt/completion tokens) from the
  OpenAI SDK response, aggregated per pass and logged at job completion.
- Log-only (structured log lines); no schema migration required. Must not change any
  prompt, batching, or translation behavior — verified by the existing 548-test suite.

### Step 1 — Proving runs on the instrumented image

- Build/deploy the instrumented image (CI → GHCR by SHA, manual deploy as usual).
- Reset artifacts correctly: delete target `.vi.srt` files + clear ledger entries **via
  API** (never host-write the live SQLite while the daemon runs).
- **Leg A:** E19 (single-episode regression check).
- **Leg B:** MK E01 → E02 → E03, run **sequentially in episode order** to exercise
  Bible carry-forward.
- Trigger and monitor via the openclaw homelab agent/API (no SSH). Mind the
  internal-id vs arr-id gotcha. Concurrency 4. Overnight is fine.

### Step 2 — Mode B consistency audit

Run the `trezarr-quality` harness output-consistency audit (Mode B) across the new
`.vi.srt` set. Every finding adversarially verified, as in prior audits.

**Pass criteria:** zero unjustified pronoun-pair changes across episodes; character
names and term renderings stable E01→E03; no register regressions in E19.

### Step 3 — Performance & stability profile

From the Step-1 logs: per-pass time share, call counts, token volumes, retry/error
rates, total wall-clock per episode and per night. Output: a short report ranking
**safe** optimization candidates by benefit/risk.

### Step 4 — Fix loop (ordered)

1. **Consistency defects first** — TDD + `trezarr-quality` code review, per current
   standard (each fix: RED test → fix → harness review → verifier).
2. **Throughput/stability second** — only items inside the safe boundary below.

Each fix wave ends with re-run + Mode B re-audit as the regression gate.

**Safe-optimization boundary (in scope):** retry/quarantine hardening, controlled
prompt slimming (e.g. glossary injection size), batch tuning within tested limits.
**Out of scope:** merging/removing passes, raising concurrency above 4, switching
models, weakening the 7-check pre-write validation gate.

### Step 5 — Gate

A clean Mode B audit unlocks **IMP-04** (context-carry summarizer), per the existing
deferred-learnings decision. IMP-04 itself is *not* part of this campaign.

## Success criteria

- Mode B audit on fresh proving output: **zero unjustified pronoun-pair changes**,
  stable names/terms across Leg B, clean Leg A.
- A written performance profile answering where time goes, with a ranked safe-fix list.
- All confirmed consistency defects fixed and re-audited clean.
- Test suite green throughout; no moat regressions introduced by perf work.

## Risks

- **Mid-run failures (deepseek errors/timeouts):** treated as stability *data* for
  Step 3/4, not as audit blockers; rerun the affected episode.
- **Instrumentation perturbs behavior:** mitigated by log-only design + full test suite
  + harness review before deploy.
- **Synology-synced repo:** background commits/rebases on `main` — fetch + verify
  fast-forward before any push; never force-push.

## Execution routing

Code changes go through GSD (`/gsd-quick` per scoped task); proving runs and audits are
operational (openclaw agent + `trezarr-quality` harness) and produce artifacts under
`.trezarr-harness/`.
