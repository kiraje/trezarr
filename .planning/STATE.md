---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 05-01-PLAN.md (Wave-0 xfail stubs)
last_updated: "2026-06-01T13:58:19.255Z"
last_activity: 2026-06-01
progress:
  total_phases: 10
  completed_phases: 4
  total_plans: 21
  completed_plans: 16
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-31)

**Core value:** Vietnamese subtitles that stay consistent and relationally correct (right pronoun pair, stable names/terms) across an entire series — produced automatically.
**Current focus:** Phase 05 — three-pass-pronoun-engine

## Current Position

Phase: 05 (three-pass-pronoun-engine) — EXECUTING
Plan: 2 of 6
Status: Ready to execute
Last activity: 2026-06-01

Progress: [████████░░] 76%

## Performance Metrics

**Velocity:**

- Total plans completed: 16
- Average duration: 6 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 03 | 5 | - | - |
| 04 | 4 | - | - |

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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 5 (Three-Pass Pronoun Engine) is the novel core and flagged for deeper research during planning: prompt design, Bible merge/lock semantics, speaker-inference reliability, Vietnamese pronoun-pair rules, and a cross-episode consistency harness.
- Phase 9 (ASS/SSA) and Phase 10 (source selection) are also research-flagged (intricate ASS tag grammar; novel relational-fidelity ranking heuristic).

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-01T13:58:19.248Z
Stopped at: Completed 05-01-PLAN.md (Wave-0 xfail stubs)
Resume file: None
