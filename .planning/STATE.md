---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: "UI v2: shadcn dashboard"
status: planning
stopped_at: Phase 11 context gathered
last_updated: "2026-06-03T10:49:30.471Z"
last_activity: 2026-06-03 — v1.1 roadmap created (Phases 11–16)
progress:
  total_phases: 16
  completed_phases: 10
  total_plans: 44
  completed_plans: 44
  percent: 63
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-03)

**Core value:** Vietnamese subtitles that stay consistent and relationally correct (right pronoun pair, stable names/terms) across an entire series — produced automatically.
**Current focus:** Milestone v1.1 — UI v2 shadcn dashboard. Roadmap created; ready to plan Phase 11.

## Current Position

Phase: 11 (shadcn Foundation & Purple Theme) — Not started
Plan: —
Status: Roadmap defined; awaiting phase planning
Last activity: 2026-06-03 — v1.1 roadmap created (Phases 11–16)

```
v1.1 Progress: [          ] 0% (0/6 phases)
Phase 11: [ ] Foundation   Phase 12: [ ] Shell
Phase 13: [ ] Backend API  Phase 14: [ ] Library Pages
Phase 15: [ ] Reskin       Phase 16: [ ] Docker/Smoke
```

## Performance Metrics

**Velocity:**

- Total plans completed: 39 (v1.0)
- Average duration: 6 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 03 | 5 | - | - |
| 04 | 4 | - | - |
| 05 | 6 | - | - |
| 6 | 3 | - | - |
| 7 | 6 | - | - |
| 08 | 4 | - | - |
| 10 | 4 | - | - |

**Recent Trend:**

- Last 5 plans: 6 min
- Trend: establishing baseline

*Updated after each plan completion*
| Phase 01 P02 | 2 | 3 tasks | 4 files |
| Phase 01-codec-llm-client-foundation P03 | 9 | 2 tasks | 3 files |
| Phase 02 P01 | 8 | 2 tasks | 8 files |
| Phase 02 P02 | 10 | 2 tasks | 7 files |
| Phase 02 P03 | 12 | 2 tasks | 4 files |
| Phase 03 P01 | 25 min | 2 tasks | 11 files |
| Phase 03 P03 | 20min | 2 tasks | 4 files |
| Phase 3 P04 | 35min | 2 tasks | 4 files |
| Phase 3 P05 | 50min | 2 tasks | 5 files |
| Phase 05-three-pass-pronoun-engine P01 | 2min | 2 tasks | 5 files |
| Phase 05-three-pass-pronoun-engine P02 | 4 min | 2 tasks | 5 files |
| Phase 05-three-pass-pronoun-engine P03 | 4 min | 1 tasks | 3 files |
| Phase 05 P04 | 3 min | 1 tasks | 2 files |
| Phase 05 P06 | 15min | 2 tasks | 5 files |
| Phase 06 P06-02 | 25 min | 2 tasks | 5 files |
| Phase 06 P06-03 | 15min | 2 tasks | 4 files |
| Phase 07-web-ui-service-hardening P01 | 3 minutes | 2 tasks | 9 files |
| Phase 07 P02 | 13min | 2 tasks | 13 files |
| Phase 07-web-ui-service-hardening P06 | 12 | 3 tasks | 6 files |
| Phase 08 P01 | 5 | 2 tasks | 3 files |
| Phase 08 P02 | 4 min | 2 tasks | 4 files |
| Phase 08 P03 | 8 minutes | 2 tasks | 3 files |
| Phase 08 P04 | continuation | 5 tasks | 10 files |
| Phase 09 P01 | 8 minutes | 2 tasks | 26 files |
| Phase 09-multi-format-ass-ssa-vtt P03 | 25 | 2 tasks | 7 files |
| Phase 09 P04 | 12 | 1 tasks | 2 files |
| Phase 10 P01 | 6min | 2 tasks | 9 files |
| Phase 09-multi-format-ass-ssa-vtt P05 | 35m | 2 tasks | 5 files |
| Phase 10-source-selection-per-series-overrides P02 | 25 | 2 tasks | 12 files |
| Phase 10 P03 | 12min | 2 tasks | 11 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Leaves-first ordering — codec + LLM client (Phase 1) before any novel logic; validation gate is foundational (Phase 2), not polish.
- Roadmap: First vertical slice (Phase 3) de-risks \*arr path-mapping/permissions before investing in the Series Bible moat.
- Roadmap: Address Map (BIBLE-03) and attribution (PRON) ship together in Phase 5 — they are co-dependent and neither delivers value alone.
- Plan 01: pysubs2 excluded from Phase 1 — thin custom SRT parser built in Plan 02 for byte-identity (D-08)
- Plan 01: asyncio_mode=auto eliminates per-test @pytest.mark.asyncio boilerplate
- Plan 01: xfail(strict=False) stub pattern chosen for Nyquist-compliant pre-implementation test surface
- [Phase ?]: avoids mutating class-level state in multi-threaded scenarios
- [Phase ?]: aligns with test expectations and allows endpoint-level tier probing
- [Phase ?]: _make_translate_batch_fn factory: tenacity stop_after_attempt bound at runtime from settings.translate_batch_retry_attempts
- [Phase 03-03]: Catch pyarr.exceptions.PyarrError (parent) in *arr discovery — pyarr abstracts httpx errors — pyarr wraps httpx.RequestError into PyarrConnectionError and 4xx/5xx into typed Pyarr*Error; raw httpx exceptions never escape pyarr's request layer (Rule 3 deviation from plan)
- [Phase 03-03]: Pass api_ver=v3 to pyarr Sonarr/Radarr constructors — Skips pyarr's GET /api auto-detect probe. Sonarr/Radarr v3 is stable per CLAUDE.md + D-22; test fixtures only mock typed endpoints, not the version probe (Rule 3 deviation)
- [Phase 03-03]: MediaItem dataclass owned by trezarr.arr.sonarr; re-imported by radarr.py — Field 'title' (not series_title) carries both episode and movie titles per 03-REVIEWS.md LOW #17 — defined once to avoid drift
- [Phase ?]: Plan 03-04: scan_for_eligible_items signature is (items, ledger, lang_priority) matching Wave-0 test contract — narrower than the plan body's (items, settings, ledger) so scan decouples from TrezarrSettings
- [Phase ?]: Plan 03-04: apply_permissions asymmetric error handling — chown PermissionError warn-and-continue; chmod OSError raises PermissionApplyError (MEDIUM #13) so cli.py can quarantine
- [Phase ?]: Plan 03-04: 1 xfail marker retained on test_scan_returns_eligible_item_and_scan_stats — it imports trezarr.cli.MediaItem (Plan 03-05 territory); reason updated to point to next wave
- [Phase 03-05]: Rule 1 deviation — `if media_roots:` guard around assert_within_media_roots in cli's translate loop. Architectural invariant preserved via assert_media_roots_configured at startup; the guard inside the loop honors passthrough mode (no *arr + no path_mappings) without changing arr-enabled behaviour.
- [Phase 03-05]: Rule 2 deviation — `all_arr_failed` (enabled_arr > 0 AND len(discovery_failures) == enabled_arr) added to the exit-1 disjunction. Without this, the "both *arrs raised DiscoveryError → 0 items → exit 0" path violated the plan's stated success criterion.
- [Phase 03-05]: Rule 3 deviation — Added `[tool.uv] package = true` + `[build-system] hatchling` + `[tool.hatch.build.targets.wheel] packages = ["trezarr"]` so `uv sync` actually installs `[project.scripts] trezarr = "trezarr.cli:main"`. Without `package = true`, uv silently skips the entry point and `uv run trezarr` does not resolve.
- [Phase 03-05]: Soft observation — `trezarr.cli.MediaItem` and `trezarr.arr.sonarr.MediaItem` are two separate dataclasses. cli.MediaItem carries source_sub_path (post-scan); arr.sonarr.MediaItem carries raw discovery payload. Intentional per Plan-03-01 test contract; future-cleanup candidate (consolidate to EligibleItem) but not a Phase-3 blocker.
- [Phase ?]: xfail raises=(ImportError, AssertionError, TypeError) for stubs in existing modules — trezarr.translate.engine exists from Phase 3, so raises=ImportError alone would cause FAILED not XFAIL for test_pronoun_engine.py stubs
- [Phase ?]: [Phase 05-03]: D-44 threshold gate: confirmed pair uses Address Map entry terms; below-threshold unlocked entry skipped → safe default
- [Phase ?]: translate_file three-pass flow: Pass 1 BARRIER + Pass 2 gather + reconcile + Pass 3 pronoun hints; BibleAnalysisError quarantines; openai.APIError propagates (D-40 D-48 Pitfall B)
- [Phase ?]: derive_episode_key parses SxxExx from subtitle filename stem not episode_number field (D-49 Pitfall F confirmed)
- [Phase ?]: xfail(strict=False) with raises=(ImportError, AssertionError, TypeError) for Wave-0 stubs targeting not-yet-created modules
- [Phase ?]: D-67 ProcessedFile arm uses separate reconcile_in_progress_from_ledger function for independent testability
- [Phase ?]: D-62 process_one_item shared callable extracted from CLI loop body; ItemResult dataclass; worker._execute_job calls same function
- [Phase ?]: D-67 two-arm crash-resume: reconcile_in_progress (Job rows) + reconcile_in_progress_from_ledger (ProcessedFile rows with no matching Job) as separate functions
- [Phase ?]: D-68 per-series asyncio.Lock (not Semaphore) serializes same-series episodes; distinct series run concurrently; zero asyncio.Semaphore in worker.py
- [Phase ?]: Starlette ASGITransport passes inner Router app to lifespan not outer FastAPI instance; engine stored in mutable cell closure for test accessibility
- [Phase ?]: Phase 08-01: xfail(strict=False) with raises=(ImportError, AssertionError, TypeError) for new-module stubs prevents FAILED when module not yet created
- [Phase 09-01]: validate_allowlist xfail stubs use xfail(strict=False) without raises= restriction — raises= is too narrow because pytest.fail() inside try/except raises _pytest.outcomes.Failed, not AssertionError
- [Phase 09-01]: Wave 0 xfail stubs for non-existent modules use pytest.importorskip — tests SKIP cleanly when module absent, go GREEN when module lands (established Trezarr pattern)
- [Phase ?]: no separate test_sonarr.py/test_radarr.py created
- [v1.1 Roadmap]: Phase 11 pins `shadcn@2.10.0 init` (not @latest) — shadcn@latest (4.x) emits Tailwind v4 config that breaks the existing Tailwind v3.4 PostCSS pipeline on first run. The `add` command for components can use @latest safely.
- [v1.1 Roadmap]: NAV-03 (count/LIVE badges) assigned to Phase 14 — badge data requires API-02 `translated_count`/`total_count` from Phase 13; the Phase 12 shell delivers placeholder/zero badges; full badge wiring lands with Phase 14 library pages.
- [v1.1 Roadmap]: Phase 13 (backend enrichment) is parallel-eligible with Phase 12 (shell) — no shared code; but Phase 14 (SeriesDetail) blocks on both Phase 12 (layout route / Outlet) and Phase 13 (stable API contract).
- [v1.1 Roadmap]: BibleEditor reskin is Phase 15 (last page) — 88KB, 5 previously-fixed critical locking bugs; reskin-in-place only (token substitution, no logic changes); test suite must stay green after each of the four sections.
- [v1.1 Roadmap]: Bridge period dual-token strategy — legacy hex tokens kept in tailwind.config.js until all pages are reskinned; removed atomically in Phase 15 (single commit after grep for `bg-[#` returns zero results).

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 5 (Three-Pass Pronoun Engine) is the novel core and flagged for deeper research during planning: prompt design, Bible merge/lock semantics, speaker-inference reliability, Vietnamese pronoun-pair rules, and a cross-episode consistency harness.
- Phase 9 (ASS/SSA) and Phase 10 (source selection) are also research-flagged (intricate ASS tag grammar; novel relational-fidelity ranking heuristic).
- [v1.1] Phase 13 runtime validation needed: Bazarr `fetch_episode_inventory` param format (`seriesid[]` vs `seriesid`) must be verified against the live instance at 192.168.5.42 during Phase 13 — known ambiguity from production observation.
- [v1.1] Phase 14 jolly-ui Table beta stability: evaluate within the first day of Phase 14 implementation; have the shadcn plain `<Table>` fallback ready to swap if Table beta is unstable.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260602-3zg | Fix Phase-5 review findings B1 (reconcile.py name match missing .strip) and M1 (character identity key normalization) | 2026-06-01 | 754292f | [260602-3zg-fix-phase-5-review-findings-b1-reconcile](./quick/260602-3zg-fix-phase-5-review-findings-b1-reconcile/) |
| 260602-g9z | Create README.md for Trezarr | 2026-06-02 | 09890e3 | [260602-g9z-create-readme-md-for-trezarr](./quick/260602-g9z-create-readme-md-for-trezarr/) |
| 260603-laj | Fix CJK character-name resolution in Series Bible analyze (dual-key name_to_id on original_script_name + prompt tightening + CJK regression test) | 2026-06-03 | 66a47ba | [260603-laj-fix-cjk-character-name-resolution-in-ser](./quick/260603-laj-fix-cjk-character-name-resolution-in-ser/) |
| 260603-l8g | Library browser UI + manual single-item translate (arr-themed) + auto_translate poller safety gate; Bug 2 (alembic loggers) + Bug 3 (auto-enable *_enabled on save) | 2026-06-03 | 2fd17c7 | [260603-l8g-library-browser-manual-translate](./quick/260603-l8g-library-browser-manual-translate/) |
| 260603-mc3 | Selective SPA fallback — deep-link/refresh on client-side routes (/library, /bible/:id) now serves index.html instead of {"detail":"Not Found"}; missing assets + unknown /api paths still 404 honestly | 2026-06-03 | cbf1ad3 | [260603-mc3-selective-spa-fallback-for-deep-link-ref](./quick/260603-mc3-selective-spa-fallback-for-deep-link-ref/) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-03T10:49:30.465Z
Stopped at: Phase 11 context gathered
Resume file: .planning/phases/11-shadcn-foundation-purple-theme/11-CONTEXT.md
