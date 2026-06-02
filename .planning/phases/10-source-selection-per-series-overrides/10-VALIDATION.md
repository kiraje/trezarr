---
phase: 10
slug: source-selection-per-series-overrides
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-02
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Drawn from 10-RESEARCH.md §"Validation Architecture". The planner fills the
> Per-Task Verification Map; the Nyquist auditor signs off.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (asyncio_mode=auto) + pytest-httpx |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30–60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Populated by the planner from RESEARCH.md §Validation Architecture. Key targets:
> - Bazarr inventory parsing against recorded response fixtures (INTG-02)
> - Ranking heuristic against a table of (available langs, original_language) → expected pick (SRC-02)
> - Source-language-change idempotency transition / Case 1.5 (D-110 — no loop, no foreign-vi clobber)
> - Migration 0003 up/down (SVC-05 storage)
> - Per-series override resolution precedence (SVC-05)
> - Model-override-per-call preserving the single LLMClient semaphore (D-06/D-113)
> - Bazarr-disabled graceful degradation to filesystem glob (SRC-01)

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 0 | INTG-02, SRC-01/02, SVC-05 | — | N/A | unit | `uv run pytest -q` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 1 | INTG-02, SRC-01, SRC-02, D-108 | T-10-02, T-10-04, T-10-05 | BazarrClient redacts api_key; rank_sources deterministic | unit | `uv run pytest tests/arr/test_bazarr.py tests/source_selection/test_rank.py tests/source_selection/test_resolve.py tests/arr/test_arr_discovery.py -v` | ✅ green | ✅ green |
| 10-02-02 | 02 | 1 | SRC-01, SRC-02, SVC-05, D-110 | T-10-03 | Bazarr paths traversal-guarded; D-26/D-27/D-28 non-regression | unit | `uv run pytest tests/discover/test_gap.py -v` | ✅ green | ✅ green |
| 10-03-01 | 03 | 1 | SVC-05, D-111, D-114, D-39 | T-10-06, T-10-07 | 2-letter code validation; store returns DTO not ORM row | unit | `uv run pytest tests/db/test_migration_0003.py tests/web/test_bible_api.py -v` | ❌ pre-impl | ⬜ pending |
| 10-03-02 | 03 | 1 | SVC-05, D-113, D-112, D-06 | T-10-08 | Single semaphore; BazarrClient degrades on error | unit | `uv run pytest tests/llm/test_client.py -v` | ❌ pre-impl | ⬜ pending |
| 10-04-01 | 04 | 2 | SVC-05, D-114 | T-10-10, T-10-11, T-10-12 | Save Overrides excludes register; client validates 2-letter codes | build | `cd frontend && npm run build` | ❌ pre-impl | ⬜ pending |
| 10-04-02 | 04 | 2 | SVC-05 | — | End-to-end Overrides tab functional | human-UAT | (checkpoint in 10-04) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Note: RESEARCH.md referenced tests/arr/test_sonarr.py and tests/arr/test_radarr.py as separate
> D-108 Wave-0 files. These are NOT created. D-108 stubs live in the existing
> tests/arr/test_arr_discovery.py (two appended stubs: test_sonarr_captures_original_language,
> test_radarr_captures_original_language). This is the authoritative D-108 coverage location.

- [ ] `tests/arr/test_bazarr.py` — Bazarr inventory client stubs (INTG-02) + recorded response fixtures
- [ ] `tests/source_selection/test_rank.py` — ranking heuristic + fallback chain stubs (SRC-01/02)
- [ ] `tests/source_selection/test_resolve.py` — resolve_effective_settings stubs (SVC-05, D-112)
- [ ] `tests/discover/test_gap.py` — D-110 source-change/Case-1.5 stubs (re-translate from richer source, no clobber)
- [ ] `tests/arr/test_arr_discovery.py` — D-108 original_language capture stubs (test_sonarr_captures_original_language, test_radarr_captures_original_language appended to existing file)
- [ ] `tests/db/test_migration_0003.py` — migration 0003 up/down stubs (SVC-05 storage)
- [ ] `tests/llm/test_client.py` — D-113 per-call model override stubs
- [ ] `tests/web/test_bible_api.py` — PATCH /series/{id}/overrides stubs (D-114)
- [ ] shared fixtures in the relevant `conftest.py`

*Existing pytest infrastructure covers the framework; Wave 0 adds the new test files.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Bazarr inventory read returns real source-language sets | INTG-02 | Needs a live Bazarr instance with real items | Configure Bazarr connection, run discovery, confirm inventory matches Bazarr UI |
| Relationally-richer source visibly chosen for an East-Asian title | SRC-02 | Needs real multi-source media | Place a title with both `ko` and `en` source subs; confirm Trezarr translates from `ko` |
| Per-series override visibly changes a translation | SVC-05 | Needs a browser walkthrough + a real translation | Set a per-series source/register/model override in the Bible editor; confirm next translation honors it |

*These live/visual items belong in 10-HUMAN-UAT.md (consistent with the project's hold-at-human-gate pattern).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
