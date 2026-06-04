# Milestones: Trezarr

Shipped versions, newest first. Full per-milestone detail in `.planning/milestones/`.

---

## v1.1 — UI v2: shadcn Dashboard

**Shipped:** 2026-06-04
**Phases:** 11–16 (6 phases, 21 plans)
**Git range:** `467b5f4` (v1.0) → `b719e15` (HEAD)
**Tag:** `v1.1`

Big-bang dashboard rework on a shadcn/ui + jolly-ui foundation. The core translation engine
is unchanged — this is a UI/UX and library-browsing milestone.

**Key accomplishments:**

1. shadcn/ui + jolly-ui foundation installed on Tailwind v3 with a purple CSS-variable dark theme replacing every legacy hex token (UI-01/02).
2. Full-height sidebar shell with brand, six nav routes, left purple active-accent bar, and live count + LIVE badges; `/library` split into `/series` + `/movies`, `/` → `/series` (NAV-01/02/03).
3. Backend `GET /api/library/series/{id}/episodes` rewritten to season-grouped Sonarr records with audio languages + Bazarr subtitle inventory (fail-soft HTTP 200); list endpoints expose `translated_count`/`total_count` (API-01/02).
4. New Series list, season-grouped Series detail (Accordion, audio + subtitle-language badges, per-episode/per-season translate, search/filter/sort), and Movies list; `Library.tsx` deleted (LIB-01..07).
5. Every existing page (Queue, History, Settings, Bible List, JobLogs, Bible Editor) reskinned in-place onto shadcn primitives with legacy bridge tokens removed; test suite green throughout (RSK-01/02).
6. Multi-stage Docker image rebuilt `--no-cache` and live-smoke-tested 8/8 on :6868 against the real *arr stack; SPA deep-link fallback intact (RSK-03).

**Verification:** Milestone audit PASSED — 17/17 requirements (3-source cross-reference), 6/6 phases, integration CLEAN, 8/8 live smoke test. See `milestones/v1.1-MILESTONE-AUDIT.md`.

**Tech debt carried forward (non-blocking):** W1 LIVE-badge false-positive for a disabled *arr service (cosmetic); W2 `series_title` optional-vs-nullable type drift (runtime-safe); W3 Bazarr `seriesid[]` confirmed-by-smoke, not code-guaranteed (fail-soft). Follow-up tickets.

Archive: `milestones/v1.1-ROADMAP.md` · `milestones/v1.1-REQUIREMENTS.md` · `milestones/v1.1-MILESTONE-AUDIT.md`

---

## v1.0 — MVP: Automated Vietnamese Subtitle Translator

**Shipped:** 2026-06-03
**Phases:** 1–10 (10 phases, 44 plans)
**Git range:** project start → `467b5f4` (last commit before v1.1)
**Tag:** `v1.0`

The complete vertical product: discover media via the *arr stack, translate a source subtitle
to Vietnamese with a Bible-backed three-pass pronoun engine, validate, and write a sidecar —
fully automated, running as a Dockerized service.

**Key accomplishments:**

1. Byte-identical SRT codec (text separable from timing) + a configurable OpenAI-compatible LLM client (semaphore-capped, json_schema→json_object→text tier fallback) (FMT-01, ENG-01).
2. Mechanical translation core with a hard 7-check pre-write validation gate, atomic UTF-8 sidecars, and content-hash idempotency (ENG-02/03/06/07, FMT-05).
3. End-to-end *arr vertical slice — Sonarr/Radarr discovery, container↔host path mapping with traversal guard, PUID/PGID/UMASK sidecar permissions (INTG-01/03/04, AUTO-01/03/04).
4. Persistent, lockable, carry-forward Series Bible on SQLite (7-table schema, `merge_inferred` lock precedence `human > prior > inference`, audit trail) (BIBLE-01/02/04/05/06).
5. The core differentiator: three-pass pronoun engine — full-file Bible analysis → speaker/addressee attribution → deterministic reconciliation (one pronoun pair per ordered pair per episode, reciprocal-coherent) → translation with pronoun hints; low-confidence → safe default (ENG-04, BIBLE-03, PRON-01/02/03).
6. Relationship evolution (episode-marked transitions) + best-effort LLM self-review pass (BIBLE-07, ENG-05); editable+lockable Bible UI as the human override valve (BIBLE-08/09).
7. Dockerized crash-safe service (FastAPI lifespan, APScheduler poll + `/webhook`, per-series-serialized worker) with config/queue/history/logs/retry UI (SVC-01..04, AUTO-02/05).
8. ASS/SSA + VTT codecs (styling/tags/karaoke/cue-settings byte-identical) (FMT-02/03/04); Bazarr-inventory source selection ranked by relational fidelity + per-series overrides (INTG-02, SRC-01/02, SVC-05).

**Coverage:** 40/40 v1 requirements mapped and shipped. Five Bible requirements (BIBLE-01/02/04/05/06) are structurally complete + unit-verified; behavioral end-to-end verification deferred (see below).

**Known gaps / deferred at close (acknowledged 2026-06-04):**

- **Translation core-value UNVERIFIED** — end-to-end pronoun/relationship consistency on a real series not yet confirmed against a frontier model (`ds/deepseek-v4-pro` insufficient). The project's core value; top open item. See `milestones/v1.0-TRANSLATION-VERIFICATION-FINDINGS.md` (5 pipeline bugs from the live test; 4 fixed, orphan-sentinel #5 open).
- **Human-verify debt** (live-LLM / live-deployment walkthroughs not yet run): Phase 04 (1 UAT + VERIFICATION human_needed), Phase 05 (2 UAT), Phase 06 (2 UAT), Phase 07 (12 UAT), Phase 09 (09-06 positioned-sign visual UAT not executed). Verification status `human_needed` on phases 04–07.
- These items are recorded in STATE.md → Deferred Items.

Archive: `milestones/v1.0-ROADMAP.md` · `milestones/v1.0-REQUIREMENTS.md` · `milestones/v1.0-SMOKE-TEST.md` · `milestones/v1.0-TRANSLATION-VERIFICATION-FINDINGS.md`
