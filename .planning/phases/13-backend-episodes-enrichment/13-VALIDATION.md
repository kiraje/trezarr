---
phase: 13
slug: backend-episodes-enrichment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-03
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from 13-RESEARCH.md §Validation Architecture. Unlike the frontend
> phases, Phase 13 is backend Python with a real **pytest + pytest-asyncio**
> harness (`asyncio_mode = "auto"`), so every requirement is automatable.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pyproject.toml` → `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`, `testpaths = ["tests"]`) |
| **Quick run command** | `uv run pytest tests/web/test_library_api.py -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | quick ~3–8s; full suite ~30–60s |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/web/test_library_api.py -q` (plus `tests/translate/test_engine.py` for the D-06 fix task)
- **After every plan wave:** `uv run pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite green
- **Max feedback latency:** ~60 seconds (full suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-W0-tests | (planner) | 0 | API-01/02 | — | N/A | unit (RED stubs) | `uv run pytest tests/web/test_library_api.py -q` | ❌ Wave 0 | ⬜ pending |
| 13-engine-seriesid | (planner) | 0/1 | D-06 fix | — | N/A | unit | `uv run pytest tests/translate/test_engine.py::test_ledger_records_series_id_on_success -xq` | ❌ Wave 0 | ⬜ pending |
| 13-count-helper | (planner) | 1 | API-02 | T-13-02 (parameterized query) | series_id `.in_()` always parameterized | unit | `uv run pytest tests/web/test_library_api.py::test_translated_counts_for_series -xq` | ❌ Wave 0 | ⬜ pending |
| 13-episodes-endpoint | (planner) | 1 | API-01 | T-13-01 (strip sub paths) | only code2/code3/hi/forced returned | unit | `uv run pytest tests/web/test_library_api.py -q` | ❌ Wave 0 | ⬜ pending |
| 13-list-counts | (planner) | 1 | API-02 | — | N/A | unit | `uv run pytest tests/web/test_library_api.py::test_get_library_series_count_fields -xq` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Requirement → Test detail (from RESEARCH §Phase Requirements → Test Map)

| Req | Behavior | Test |
|-----|----------|------|
| API-01 | Bazarr disabled → `bazarr_available:false`, HTTP 200, no errors[] entry | `test_get_series_episodes_bazarr_disabled` |
| API-01 | Bazarr enabled-but-unreachable → `bazarr_available:false`, HTTP 200, errors[] entry | `test_get_series_episodes_bazarr_error` |
| API-01 | Join by `episode.id` (NOT `episodeFile.id`) | `test_get_series_episodes_bazarr_join_key` |
| API-01 | `audio_languages` normalizes "Korean/English" → ["ko","en"] | `test_audio_language_normalization` |
| API-01 | Envelope: `seasons` grouped by `season_number`, each ep has `episode_id`/`episode_key` | `test_get_series_episodes_envelope_shape` |
| API-02 | `translated_count`/`total_count` present on series list items | `test_get_library_series_count_fields` |
| API-02 | `translated_counts_for_series` correct given mock ProcessedFile rows | `test_translated_counts_for_series` |
| D-06 | engine records `series_id` on the success path | `test_ledger_records_series_id_on_success` |

---

## Wave 0 Requirements

- [ ] `tests/web/test_library_api.py` — 8 new test functions (Bazarr disabled, Bazarr error, join key, audio normalization, envelope shape, list count fields, count-helper unit). The **4 existing** status-code tests must remain green; update shape assertions where `get_series_episodes` changed from a flat list to the season-grouped envelope.
- [ ] `tests/translate/test_engine.py` — 1 new test: `series_id` populated on the success-path `ledger.record` (D-06).
- [ ] No new framework or conftest needed — existing fixtures + `pytest-httpx`/monkeypatch patterns suffice (patch at `trezarr.arr.sonarr.build_sonarr_client`; mock `episode.get` and `episode_file.get` independently).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sonarr `statistics.episodeFileCount` present in the live `/api/v3/series` payload | API-02 (A2) | Live-data shape; mock can't prove the real instance includes it | Hit live Sonarr at 192.168.5.42; confirm series objects carry `statistics.episodeFileCount` (code already defaults to 0 if absent) |
| Bazarr `fetch_episode_inventory` `seriesid[]` param returns data | API-01 (Open Q2) | Live Bazarr behavior; ARCHITECTURE §8 flags the bracketed form may return empty | Call against live Bazarr; if empty, fall back to unbracketed `{"seriesid": N}` |
| `translated_count` reflects real translations after the D-06 fix | API-02 (Open Q3) | Existing ProcessedFile rows have `series_id = NULL` (no backfill); counts reflect future translations only | After fix, translate an episode; confirm its series' `translated_count` increments |

---

## Validation Sign-Off

- [ ] Every task `<verify>` has an `<automated>` pytest command
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING test references (8 endpoint/count tests + 1 engine test)
- [ ] No watch-mode flags (one-shot `pytest -q`)
- [ ] Feedback latency < 60s (full suite)
- [ ] 4 existing `test_library_api.py` tests remain green after the rewrite
- [ ] `nyquist_compliant: true` set in frontmatter after plan-checker/Nyquist sign-off

**Approval:** pending
