---
phase: 05
slug: three-pass-pronoun-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-01
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `05-RESEARCH.md` § Validation Architecture. The Per-Task map is
> seeded at the requirement level; the planner/nyquist pass fills concrete Task IDs.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| **Quick run command** | `uv run pytest tests/translate/test_reconcile.py tests/bible/test_address_map.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~30 seconds (mocked LLM; no live endpoint) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/translate/test_reconcile.py tests/bible/test_address_map.py -x -q`
- **After every plan wave:** `uv run pytest tests/translate/ tests/bible/ -x -q`
- **Before `/gsd-verify-work`:** `uv run pytest -x -q` must be green
- **Max feedback latency:** ~30 seconds

**Determinism rule (core to this phase):** LLM nondeterminism must NOT flake tests. Pass 1 and
Pass 2 are tested with mocked LLM responses returning deterministic `BibleAnalysis` /
`LineAttribution` objects. Pronoun consistency (success #3) is tested as a *pure algorithm
property* at the reconciliation layer — never against a live LLM.

---

## Per-Task Verification Map

> Requirement-level scaffold. Plan + Wave + Task ID columns are filled once `gsd-planner`
> produces PLAN.md files. Every row below MUST map to at least one task's `<automated>` verify.

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| ENG-04 | Pass 1 runs and Bible updated BEFORE any line translated | integration (mocked LLM) | `uv run pytest tests/translate/test_pronoun_engine.py::test_pass1_runs_before_pass3 -x` | ❌ W0 | ⬜ pending |
| ENG-04 | Pass 1 failure quarantines file, writes no translation | unit | `uv run pytest tests/translate/test_pronoun_engine.py::test_pass1_failure_quarantines -x` | ❌ W0 | ⬜ pending |
| BIBLE-03 | Address Map populated with directed pairs after Pass 1 | unit+integration | `uv run pytest tests/bible/test_address_map.py::test_upsert_address_pair -x` | ❌ W0 | ⬜ pending |
| BIBLE-03 | Locked Address Map entry never overwritten | unit | `uv run pytest tests/bible/test_address_map.py::test_locked_pair_not_overwritten -x` | ❌ W0 | ⬜ pending |
| PRON-01 | `LineAttribution` parsed from mock LLM response | unit | `uv run pytest tests/translate/test_attribute.py::test_attribution_parsing -x` | ❌ W0 | ⬜ pending |
| PRON-01 | Unknown speaker/addressee → safe default (no crash) | unit | `uv run pytest tests/translate/test_attribute.py::test_unmatched_name_safe_default -x` | ❌ W0 | ⬜ pending |
| PRON-02 | Reconciled pronoun pair injected as hint in Pass-3 prompt | unit | `uv run pytest tests/translate/test_engine.py::test_pronoun_hint_in_prompt -x` | ❌ W0 | ⬜ pending |
| PRON-02 | Same pair → identical pronouns across all batches in one episode | integration | `uv run pytest tests/translate/test_pronoun_engine.py::test_pronoun_consistency_within_episode -x` | ❌ W0 | ⬜ pending |
| PRON-03 | Low-confidence attribution → safe default, not intimate pronoun | unit | `uv run pytest tests/translate/test_reconcile.py::test_low_confidence_safe_default -x` | ❌ W0 | ⬜ pending |
| PRON-03 | `confidence=HIGH` above threshold → Address Map pair | unit | `uv run pytest tests/translate/test_reconcile.py::test_high_confidence_uses_address_map -x` | ❌ W0 | ⬜ pending |
| Success #3 | Reciprocal directions coherent (A→B "anh/em" ⇒ B→A "em/anh") | unit | `uv run pytest tests/translate/test_reconcile.py::test_reciprocal_coherence -x` | ❌ W0 | ⬜ pending |
| Success #4 | Below threshold → safe pair regardless of Address Map content | unit | `uv run pytest tests/translate/test_reconcile.py::test_below_threshold_ignores_address_map -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/translate/test_analyze.py` — ENG-04 Pass-1 prompt construction + merge orchestration
- [ ] `tests/translate/test_attribute.py` — PRON-01 attribution parsing + name matching
- [ ] `tests/translate/test_reconcile.py` — D-44 deterministic reconciliation + D-45 confidence gate
- [ ] `tests/translate/test_pronoun_engine.py` — end-to-end 3-pass integration (mocked LLM, golden-file episode)
- [ ] `tests/bible/test_address_map.py` — BIBLE-03 `upsert_address_pair` + `load_address_map`
- [ ] `tests/bible/conftest.py` — extend session_factory fixtures for `AddressMap` (character/term fixtures already exist)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Vietnamese pronoun *quality* on a real episode | PRON-02/03 | Subjective linguistic correctness can't be asserted programmatically | Run against a known fixture episode with a live endpoint; spot-check that anh/em, chị/em pairs read naturally and stay consistent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
