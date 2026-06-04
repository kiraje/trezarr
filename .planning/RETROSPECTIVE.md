# Retrospective: Trezarr

Living retrospective. One section per milestone, newest first, followed by cross-milestone trends.

---

## Milestone: v1.1 — UI v2: shadcn Dashboard

**Shipped:** 2026-06-04
**Phases:** 6 | **Plans:** 21

### What Was Built
A full dashboard rework on shadcn/ui + jolly-ui (purple dark theme), a sidebar shell with six
routes and live badges, backend episode enrichment (season-grouped, Bazarr fail-soft), new
Series/Series-detail/Movies pages, an in-place reskin of every existing page, and a Docker
rebuild verified live on :6868. Core engine untouched.

### What Worked
- **Dependency-forced build order** (foundation → shell → backend → pages → reskin → docker) meant each phase had a green build to stand on; no phase blocked on a sibling's churn.
- **Pinning `shadcn@2.10.0 init`** pre-empted the Tailwind v4 / v3 break that @latest would have caused — a decision captured at roadmap time, not discovered painfully mid-build.
- **Bridge-period dual tokens** let pages migrate one at a time while staying shippable; the atomic token removal in Phase 15 (gated on `grep "bg-[#"` returning zero) closed it cleanly.
- **BibleEditor reskinned last**, reskin-in-place only, with the existing test suite as the regression net — the highest-risk 88KB file with 5 prior locking bugs survived untouched in behavior.
- The **live operator smoke test (8/8)** as the release gate caught what unit tests can't — real *arr data, real badges, real deep-link refresh.

### What Was Inefficient
- A cluster of small warnings (reciprocal double-toast, resetKey, Fragment keys, close button) surfaced only in the Phase-15 review and had to be swept up just before close — could have been caught per-plan.
- Type-contract drift (`series_title` optional-vs-nullable) slipped through to the audit as W2 — the API client type and the backend emitter weren't cross-read at the boundary.

### Patterns Established
- shadcn primitive + CVA token system as the single styling vocabulary; `cn()` everywhere.
- LibraryContext as the shared `/api/library` state with derived LIVE/count badge helpers.
- Sonner (single `<Toaster>`) as the toast system, migrated call-site by call-site.

### Key Lessons
- Cross-read producer and consumer at every API boundary during the phase, not at the audit — W2/W3 are both boundary-contract drift the integration checker found late.
- A "LIVE" signal inferred from absence-of-error (W1) is a false-positive trap; positive enabled/connected flags belong in the API contract.

### Cost Observations
- Model mix: predominantly opus for planning/execution; the rework was UI-heavy and benefited from a strong model on the reskin diffs.
- Notable: the big-bang rollout kept context coherent — one component system, one theme, migrated in dependency order.

---

## Milestone: v1.0 — MVP: Automated Vietnamese Subtitle Translator

**Shipped:** 2026-06-03
**Phases:** 10 | **Plans:** 44

### What Was Built
The whole vertical product: SRT/ASS/SSA/VTT codecs, an OpenAI-compatible LLM client, a hard
validation gate, *arr discovery + path mapping + permissions, a persistent lockable Series
Bible, the three-pass pronoun engine, relationship evolution + self-review, an editable Bible
UI, a Dockerized crash-safe service, and relational-fidelity source selection.

### What Worked
- **Leaves-first ordering** — codec + LLM client as isolated tested leaves before any novel logic — gave a solid base; the validation gate built in from day one meant nothing untrustworthy could ever be written.
- **First vertical slice at Phase 3** de-risked the ecosystem's worst friction (path mapping, PUID/PGID) before investing in the Bible moat.
- **Deterministic reconciliation** for per-episode pronoun consistency turned the core promise from "an LLM gamble" into a code-guaranteed property (one pair per ordered pair per episode, reciprocal-coherent).
- **Post-execution code review per phase** repeatedly caught silent-failure bugs that tests missed — most importantly Phase 6's "self-review ran blind" (dominant_pair never populated) and Phase 10's "selection chain was dead code in the production path."

### What Was Inefficient
- Several critical bugs were *structural* (dead code in the production path, blind self-review, daemon crash on a missing `media_item`) — they passed unit tests because the tests exercised the units, not the wired production path. Live/integration testing surfaced them late.
- The Series Bible's behavioral correctness was never confirmed end-to-end against a capable model during the milestone — the live test (post-close) revealed the configured `deepseek-v4-pro` endpoint is insufficient, leaving the core value unverified.
- Human-UAT scenarios accumulated unticked across phases 04–07 because they require a real run; they were deferred rather than resolved.

### Patterns Established
- Wave-0 RED test scaffold (xfail stubs) per phase, promoted to passing as modules land.
- Pydantic-only store boundary (no SQLAlchemy in routes), contract-tested.
- Single `LLMClient._semaphore` as the only global LLM concurrency cap; per-series `asyncio.Lock` for ordering.
- `merge_inferred` lock precedence `human lock > prior value > new inference` as the Bible's spine.
- Case-insensitive name matching (`.strip().lower()`) across modules — a cross-module contract (a missing `.strip()` silently dropped pronoun pairs).

### Key Lessons
- Unit-green ≠ production-wired. The recurring failure mode was code that worked in isolation but wasn't actually called (or was called blind) on the real path. Add a thin integration/live check per phase that exercises the wired flow.
- For an LLM-dependent core value, verify against a capable model *early* — the engine can be perfect and still produce wrong output if the configured endpoint can't do structured output or relational reasoning.

### Cost Observations
- 44 plans across 10 phases; heavy use of the Trezarr domain-correctness harness (bible-consistency-auditor, vietnamese-linguist, finding-verifier) for the novel logic.
- Notable: the validation gate + idempotency ledger meant re-runs were cheap and safe during iteration.

---

## Cross-Milestone Trends

### Recurring strengths
- Leaves-first / dependency-forced ordering both milestones — never blocked on sibling churn.
- Post-execution code review consistently catches silent-failure and dead-code bugs unit tests miss.
- Decisions captured at roadmap/planning time (shadcn pin, deterministic reconciliation, validation gate) prevented painful mid-build discoveries.

### Recurring weaknesses
- **Boundary-contract drift** — producer/consumer type mismatches (v1.0 wiring bugs, v1.1 W2/W3) surface at audit, not during the phase. Standing fix: cross-read both sides at the seam.
- **Verification debt accumulates** — live/human-UAT scenarios get deferred because they need a real run; v1.0 closed with the core value still unverified. Standing fix: a thin live check per phase.

### Velocity
| Milestone | Phases | Plans | Shipped |
|-----------|--------|-------|---------|
| v1.0 | 10 | 44 | 2026-06-03 |
| v1.1 | 6 | 21 | 2026-06-04 |
