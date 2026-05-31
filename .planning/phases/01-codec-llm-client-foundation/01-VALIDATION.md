---
phase: 1
slug: codec-llm-client-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-31
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` § Validation Architecture (empirically verified test map).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.x + pytest-asyncio 1.2.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) — created in Wave 0 |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds (all unit tests; no live LLM calls) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q` (< 5s; all unit tests, no network)
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds
- **Live endpoint test:** manual only — `pytest tests/llm/test_client_live.py -v -s` with real `TREZARR_LLM_*` env set (marked `@pytest.mark.live`, excluded from CI)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| FMT-01 | codec | 1 | FMT-01 | T-V5 | Malformed cues preserved-and-flagged, never crash | unit (golden-file) | `pytest tests/codec/test_srt_roundtrip.py -x` | ❌ W0 | ⬜ pending |
| FMT-01 | codec | 1 | FMT-01 | — | Non-sequential indices preserved verbatim | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[crlf_indices.srt]` | ❌ W0 | ⬜ pending |
| FMT-01 | codec | 1 | FMT-01 | — | Period timecodes not normalized to comma | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[period_timecodes.srt]` | ❌ W0 | ⬜ pending |
| FMT-01 | codec | 1 | FMT-01 | — | Inline tags preserved (`<b>`, `<font>`, `{\an8}`) | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[inline_bold.srt]` | ❌ W0 | ⬜ pending |
| FMT-01 | codec | 1 | FMT-01 | — | UTF-8 BOM round-trips byte-identical | unit | `pytest tests/codec/test_srt_roundtrip.py::test_byte_identical_roundtrip[utf8bom.srt]` | ❌ W0 | ⬜ pending |
| FMT-01 | codec | 1 | FMT-01 | — | `SubLine.text` mutable; index/start_tc/end_tc not exposed to LLM | unit | `pytest tests/codec/test_srt_model.py -x` | ❌ W0 | ⬜ pending |
| ENG-01 | config | 1 | ENG-01 | — | Settings load from YAML + env override | unit | `pytest tests/config/test_settings.py -x` | ❌ W0 | ⬜ pending |
| ENG-01 | config | 1 | ENG-01 | T-V6 | API key never in `str(settings)` / `model_dump()` (SecretStr) | unit | `pytest tests/config/test_settings.py::test_api_key_not_logged` | ❌ W0 | ⬜ pending |
| ENG-01 | llm | 1 | ENG-01 | — | Tier 1 `json_schema` used by default | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_uses_json_schema_by_default` | ❌ W0 | ⬜ pending |
| ENG-01 | llm | 1 | ENG-01 | — | Falls back to `json_object` on 400 | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_falls_back_to_json_object_on_400` | ❌ W0 | ⬜ pending |
| ENG-01 | llm | 1 | ENG-01 | — | Falls back to text on second 400 | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_falls_back_to_text_on_second_400` | ❌ W0 | ⬜ pending |
| ENG-01 | llm | 1 | ENG-01 | — | Pinned `mode=json_schema` raises on 400 (no fallback) | unit (mock) | `pytest tests/llm/test_client_tiers.py::test_pinned_mode_raises` | ❌ W0 | ⬜ pending |
| ENG-01 | llm | 1 | ENG-01 | — | Semaphore limits concurrent calls to `max_concurrency` | unit (mock+asyncio) | `pytest tests/llm/test_client_concurrency.py -x` | ❌ W0 | ⬜ pending |
| ENG-01 | llm | 1 | ENG-01 | — | SDK `max_retries` used; no tenacity stacking | unit (mock) | `pytest tests/llm/test_client_no_double_retry.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`; dev deps `pytest`, `pytest-asyncio`
- [ ] `tests/conftest.py` — shared fixtures (settings factory, tmp_path helpers, `live` marker registration)
- [ ] `tests/fixtures/*.srt` — 6 golden SRT files (crlf_indices, period_timecodes, inline_bold, utf8bom, plus baseline + malformed)
- [ ] `tests/codec/test_srt_roundtrip.py` — golden-file byte-identity parametrized tests (FMT-01)
- [ ] `tests/codec/test_srt_model.py` — SubLine field-separation test (FMT-01)
- [ ] `tests/config/test_settings.py` — YAML+env load + SecretStr masking (ENG-01)
- [ ] `tests/llm/test_client_tiers.py` — structured-output tier fallback, mocked (ENG-01)
- [ ] `tests/llm/test_client_concurrency.py` — semaphore cap (ENG-01)
- [ ] `tests/llm/test_client_no_double_retry.py` — no tenacity stacking (ENG-01)
- [ ] `tests/llm/test_client_live.py` — real endpoint smoke test, `@pytest.mark.live`, excluded from CI (ENG-01)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLMClient produces a successful response against the user's real endpoint | ENG-01 | Requires the user's live OpenAI-compatible endpoint + credentials; cannot run in CI | Set `TREZARR_LLM_BASE_URL`, `TREZARR_LLM_MODEL`, `TREZARR_LLM_API_KEY`; run `pytest tests/llm/test_client_live.py -v -s`; confirm a non-empty completion returns |
| Endpoint structured-output capability tier (`auto` detection) | ENG-01 | Real tier behavior depends on the specific endpoint implementation | With live endpoint configured, observe which tier (`json_schema`/`json_object`/`text`) the `auto` path settles on; confirm no error |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
