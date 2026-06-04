---
phase: 8
slug: editable-series-bible-ui
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-02
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `08-RESEARCH.md` §Validation Architecture (HIGH confidence).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode=auto`) |
| **Config file** | `pyproject.toml` (`asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/bible/test_human_edit.py tests/web/test_bible_api.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~quick <10s · full ~60–90s (274+ tests today) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/bible/test_human_edit.py tests/web/test_bible_api.py -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds (quick), ~90 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-XX | — | 1 | BIBLE-08 c1 | — | series list bounded (LIMIT 500) | integration | `pytest tests/web/test_bible_api.py::test_get_series_list` | ❌ W0 | ⬜ pending |
| 08-XX | — | 1 | BIBLE-08 c1 | — | full Bible read w/ characters/address_map/terms/register | integration | `pytest tests/web/test_bible_api.py::test_get_series_bible` | ❌ W0 | ⬜ pending |
| 08-XX | — | 1 | BIBLE-08 c1 | — | lock/provenance state visible in DTO | unit | `pytest tests/bible/test_human_edit.py::test_lock_state_in_dto` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | BIBLE-08 c2 | — | locked field survives contradicting `merge_inferred` | integration | `pytest tests/bible/test_human_edit.py::test_locked_field_survives_merge` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | BIBLE-08 c2 | T-08-01 (V5) | lock w/ missing term → HTTP 422 (reconcile.py:275 non-None guard) | integration | `pytest tests/web/test_bible_api.py::test_lock_address_map_missing_term_rejected` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | BIBLE-08 c2 | — | JSON `locked_fields` persisted (reassign-not-append) | unit | `pytest tests/bible/test_human_edit.py::test_locked_fields_persisted` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | BIBLE-08 c2 | — | `BibleEvent(source="lock")` emitted in same txn | unit | `pytest tests/bible/test_human_edit.py::test_bible_event_emitted_on_lock` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | BIBLE-09 c3 | — | edit→lock→re-analyze: pair survives `reconcile_attributions` | integration | `pytest tests/bible/test_human_edit.py::test_locked_pair_survives_reconcile` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | BIBLE-09 c3 | — | edit→lock→next episode: pair still applied (carry-forward + lock) | integration | `pytest tests/bible/test_human_edit.py::test_locked_pair_propagates_to_next_episode` | ❌ W0 | ⬜ pending |
| 08-XX | — | 1 | D-90 (H1) | — | junior-only `bác/cháu` attribution does not overwrite locked pair | unit | `pytest tests/translate/test_reconcile.py::test_kinship_reciprocal_bac_chau` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | D-81 | — | UI write acquires per-series lock (no interleave with Pass-1) | integration | `pytest tests/web/test_bible_api.py::test_write_acquires_series_lock` | ❌ W0 | ⬜ pending |
| 08-XX | — | 2 | D-82 | T-08-02 (DoS) | history endpoint returns `BibleEventDTO`s (LIMIT 100) | integration | `pytest tests/web/test_bible_api.py::test_get_field_history` | ❌ W0 | ⬜ pending |
| 08-XX | — | 1 | D-39 | — | bible route does NOT import SQLAlchemy models | unit | `pytest tests/bible/test_dto_boundary.py::test_bible_route_does_not_import_sqla` | ❌ W0 | ⬜ pending |

*Task IDs are placeholders (`08-XX`) until the planner assigns plan/wave numbers. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/bible/test_human_edit.py` — BIBLE-08 c2 (locked field survives merge; BibleEvent emitted; JSON dirty-tracking; lock-state in DTO) + BIBLE-09 c3 (locked pair survives reconcile; propagates to next episode)
- [ ] `tests/web/test_bible_api.py` — BIBLE-08 c1 (series list; full Bible read; history) + BIBLE-08 c2 (missing-term-on-lock → 422; series lock acquired) + D-39 boundary
- [ ] `tests/translate/test_reconcile.py` additions — D-90 H1 regression (bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày round-trip)
- [ ] `tests/bible/conftest.py` re-export of `session_factory` — **already exists** (temp-file SQLite + Alembic migration); no new fixture infra needed

*No new framework installation needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SPA Bible editor renders + edit/lock round-trips in a real browser | BIBLE-08 c1 | Visual/interaction; outside pytest | Load the SPA, open a series, edit a character field, lock it, confirm badge + history drill-down render; reload and confirm persistence |
| Locked pronoun pair visibly changes a real translated `.vi.srt` on the next episode | BIBLE-09 c3 | Requires a live LLM endpoint + real episode | Lock an Address-Map pair, run the next episode through `trezarr serve` worker, inspect the emitted `.vi.srt` for the locked pronouns |

*These mirror the live/visual UAT pattern from Phases 5–7 (`*-HUMAN-UAT.md`).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`test_human_edit.py`, `test_bible_api.py`, reconcile additions)
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s (full suite)
- [ ] `nyquist_compliant: true` set in frontmatter (set by planner once Wave 0 tasks are assigned)

**Approval:** pending
