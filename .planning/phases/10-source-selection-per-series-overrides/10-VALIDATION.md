---
phase: 10
slug: source-selection-per-series-overrides
status: draft
nyquist_compliant: false
wave_0_complete: false
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

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/arr/test_bazarr.py` — Bazarr inventory client stubs (INTG-02) + recorded response fixtures
- [ ] `tests/discover/test_source_select.py` — ranking heuristic + fallback chain stubs (SRC-01/02)
- [ ] `tests/discover/test_gap.py` — D-110 source-change/Case-1.5 stubs (re-translate from richer source, no clobber)
- [ ] `tests/bible/test_overrides.py` — per-series override store + resolution stubs (SVC-05)
- [ ] migration 0003 up/down test
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
