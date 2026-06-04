# Phase 16: Docker Rebuild + Live Smoke Test - Discussion Log

> **Audit trail only.** Decisions captured in CONTEXT.md. `--auto` run: Claude
> auto-selected from locked research (ARCHITECTURE.md §7 Phase F), REQUIREMENTS
> (RSK-03), Phase-7 Docker packaging, and live-deployment memory. No AskUserQuestion.

**Date:** 2026-06-04
**Phase:** 16-docker-rebuild-live-smoke-test
**Mode:** auto (no user prompts)
**Areas auto-decided:** Build, Smoke-test scope, Deployment safety, Release gate, Failure handling

| Area | Auto-selected decision | Rationale |
|------|------------------------|-----------|
| Build (D-01) | `docker build --no-cache` of existing multi-stage Dockerfile; verify :6868 + /api/health 200 | Phase-7 Dockerfile expected to work; rebuild verifies the new SPA builds in-container. |
| Smoke scope (D-02) | Live browser checklist of the 4 ROADMAP success criteria (6 routes, live badges, translate→Queue, deep-link + redirect + Settings save) | Directly mirrors roadmap SC1–4. |
| Deployment safety (D-03) | Tag/keep current image (`:prev`) before rebuild; preserve /config volume; roll back on failure | Live deployment is real (memory); must be recoverable. |
| Release gate (D-04) | Human visual smoke-UAT; `--auto`/`--chain` HOLDS — do not auto-close phase/milestone | Matches Phase-11 D-09 / the hold-at-human-verify rule. |
| Failure handling (D-05) | No silent pass; build break fixable in-phase, feature defect → follow-up vs Phases 12–15; roll back if service left broken | Trustworthiness; this is the de-facto v1.1 integration test. |

## Claude's Discretion
Smoke-checklist ordering, which real series/episode to test, image tag naming, whether to script health/route checks vs purely manual.

## Deferred Ideas
Automated E2E/browser harness for the smoke checklist (out of scope; gate is human UAT); feature defects traced to Phases 12–15 → follow-ups, not new scope.
