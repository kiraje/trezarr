---
phase: 2
slug: mechanical-translation-core-validation-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-31
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `02-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/translate/ tests/output/ -x -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~10–20 seconds (mocked LLM; no live endpoint calls) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/translate/ tests/output/ -x -q`
- **After every plan wave:** Run `uv run pytest -q` (full suite incl. Phase 1 codec + LLM client tests)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~20 seconds

---

## Per-Task Verification Map

> Filled in during planning — one row per task. Requirement → command map below is the source contract
> (from RESEARCH.md § Phase Requirements → Test Map); the planner maps these to concrete task IDs.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | 0 | — | — | pytest scaffolding installed | infra | `uv run pytest --collect-only -q` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-02 | — | Batching respects token budget, never splits a cue; scene-gap boundary preferred; max-cue fallback | unit | `uv run pytest tests/translate/test_batching.py -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-03 | — | K context lines attached read-only; model instructed not to re-emit | unit | `uv run pytest tests/translate/test_engine.py::test_context_window_prompt -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-06 | T-V5 | Gate rejects cue-count mismatch / empty line / low VI ratio / timecode mutation / non-monotonic / orphan sentinel / invalid UTF-8 | unit | `uv run pytest tests/translate/test_validate.py -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-06 | — | Batch retry passes on 2nd attempt; whole-file quarantine after retry exhaustion | unit | `uv run pytest tests/translate/test_engine.py -k "retry or quarantine" -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | ENG-07 | T-tamper | Ledger skip-unchanged / regenerate-on-hash-change / foreign-srt-not-clobbered / quarantine-retry | unit | `uv run pytest tests/output/test_ledger.py -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | FMT-05 | T-V12 | `.vi.srt` naming from source; atomic temp+os.replace crash safety; valid UTF-8 diacritic round-trip | unit | `uv run pytest tests/output/test_write.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Gate-bias priority (most critical property)

The gate's **"false reject over missed miss"** bias is the load-bearing property. For each of the 7 gate checks there must be both:
- a **true-failure** test proving the bad output is **always caught** (zero false negatives), and
- a **legitimate-edge-case** test (proper-noun-heavy line lowering VI ratio, multi-line cue) proving it is **not wrongly rejected** (low false positives).

---

## Wave 0 Requirements

- [ ] `tests/translate/__init__.py`
- [ ] `tests/translate/test_batching.py` — ENG-02 (batch packing, scene-gap, max-cue fallback)
- [ ] `tests/translate/test_engine.py` — ENG-03, ENG-06 retry/quarantine, D-13 numbered-line parse
- [ ] `tests/translate/test_validate.py` — all 7 gate checks (ENG-06)
- [ ] `tests/translate/test_sentinel.py` — D-12 sentinel extract/reinsert + integrity check
- [ ] `tests/output/__init__.py`
- [ ] `tests/output/test_write.py` — FMT-05 naming, atomic write, UTF-8
- [ ] `tests/output/test_ledger.py` — ENG-07 skip/regenerate/foreign/quarantine-retry
- [ ] pytest-asyncio install/config if not already present from Phase 1

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `<<T…>>` sentinel pass-through on the real DeepSeek-family proxy endpoint | ENG-06 / D-12 | Requires a live LLM call; unit tests mock the client | Run a real `translate_file()` against a short test SRT using `.env` endpoint; confirm sentinels round-trip and gate passes |
| VI diacritic ratio threshold (0.70 assumed) calibration | ENG-06 / D-17 | Needs a real translated corpus to tune false-reject rate | Translate several test episodes; inspect quarantine rate; tune threshold |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
