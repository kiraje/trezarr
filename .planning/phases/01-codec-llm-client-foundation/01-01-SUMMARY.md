---
phase: 01-codec-llm-client-foundation
plan: 01
subsystem: scaffold
tags: [scaffold, testing, pytest, fixtures, configuration]
dependency_graph:
  requires: []
  provides:
    - pyproject.toml uv project manifest with Python 3.12 requirement and asyncio_mode=auto
    - Six golden SRT fixture files covering all round-trip properties (FMT-01)
    - Complete test stub surface for FMT-01 and ENG-01 (20 tests, all xfail pending Plan 02/03)
    - conftest.py with settings_factory fixture and live mark registration
  affects:
    - plans/01-02 (SRT codec implementation targets these fixtures and stubs)
    - plans/01-03 (LLM client + config implementation targets these stubs)
tech_stack:
  added:
    - "Python 3.12 (uv-managed, pyproject.toml requires-python=>=3.12)"
    - "openai 2.38.0 — async LLM client"
    - "pydantic 2.13.4 — model layer"
    - "pydantic-settings[yaml] 2.14.1 — layered config"
    - "charset-normalizer 3.4.7 — encoding detection"
    - "pytest 9.0.3 + pytest-asyncio 1.4.0 — test framework"
    - "ruff 0.15.15 — lint + format"
  patterns:
    - "asyncio_mode=auto in pyproject.toml (removes per-test @pytest.mark.asyncio boilerplate)"
    - "xfail(strict=False) stub pattern for Nyquist-compliant pre-implementation test surface"
    - "Deferred imports inside test functions to avoid collection errors on missing modules"
key_files:
  created:
    - pyproject.toml
    - config.yaml.example
    - trezarr/__init__.py
    - uv.lock
    - tests/conftest.py
    - tests/fixtures/minimal.srt
    - tests/fixtures/crlf_indices.srt
    - tests/fixtures/period_timecodes.srt
    - tests/fixtures/utf8bom.srt
    - tests/fixtures/inline_bold.srt
    - tests/fixtures/malformed_index.srt
    - tests/codec/test_srt_roundtrip.py
    - tests/codec/test_srt_model.py
    - tests/config/test_settings.py
    - tests/llm/test_client_tiers.py
    - tests/llm/test_client_concurrency.py
    - tests/llm/test_client_no_double_retry.py
    - tests/llm/test_client_live.py
  modified: []
decisions:
  - "pysubs2 excluded from Phase 1 per D-08: thin custom SRT parser will be built in Plan 02 for byte-identity"
  - "asyncio_mode=auto chosen to eliminate per-test @pytest.mark.asyncio boilerplate"
  - "xfail(strict=False) used for stubs: tests collected but non-blocking until implementation lands"
  - "Deferred imports inside test functions guard against collection errors before Plan 02/03 ship"
  - "SecretStr API key value 'test-key' is a meaningless literal in conftest (T-01-W0-01 mitigation)"
metrics:
  duration_minutes: 6
  completed_date: "2026-05-31"
  tasks_completed: 3
  tasks_total: 3
  files_created: 18
  files_modified: 0
---

# Phase 01 Plan 01: Project Scaffold & Test Harness Summary

**One-liner:** uv-managed Python 3.12 project with pytest asyncio_mode=auto, 6 golden SRT fixture files, and 20 xfail test stubs covering FMT-01 (codec) and ENG-01 (config + LLM client).

## What Was Built

### Task 1: Project Scaffold

Created the uv-managed project manifest (`pyproject.toml`) with:
- `requires-python = ">=3.12"` (D-01 floor)
- Runtime deps: `openai>=2.38.0`, `pydantic>=2.13.4`, `pydantic-settings[yaml]>=2.14.1`, `charset-normalizer>=3.4.7`
- Dev deps: `pytest>=8.4.2`, `pytest-asyncio>=1.2.0`, `ruff>=0.0.1`
- `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`
- pysubs2 intentionally excluded (reserved for Phase 9 per D-08)

Created `config.yaml.example` documenting all 8 `TrezarrSettings` fields with defaults and comments:
`llm_base_url`, `llm_api_key`, `llm_model`, `llm_max_retries` (4), `llm_request_timeout` (120.0),
`llm_max_concurrency` (4), `llm_structured_output_mode` ("auto"), `llm_context_window` (32768).

Ran `uv sync --all-groups` — installed 27 packages; `uv.lock` committed.

### Task 2: Golden SRT Fixture Files

Six byte-exact SRT fixtures, each exercising a distinct round-trip property:

| File | Property Exercised |
|------|--------------------|
| `minimal.srt` | Single-cue baseline, LF line endings, comma timecodes, trailing `\n\n` |
| `crlf_indices.srt` | CRLF (`\r\n`) throughout, non-sequential indices (5, 10) |
| `period_timecodes.srt` | Period separator timecodes (`00:00:01.000`), 2-digit milliseconds (`00:00:05.50`) |
| `utf8bom.srt` | UTF-8 BOM (bytes `EF BB BF`) at offset 0, Vietnamese text (`Xin chào`) |
| `inline_bold.srt` | `<b>`, `<font color=...>`, `{\an8}` inline tags verbatim |
| `malformed_index.srt` | Well-formed cue (index "1") + malformed cue (index "abc") for D-10 preserve-and-flag |

### Task 3: Test Stubs

Created complete test surface: 20 tests across 7 test files, all `xfail(strict=False)` pending Plan 02/03 implementation.

**conftest.py:** `live` mark registered, `FIXTURES` path constant, `settings_factory` fixture with test-safe defaults (`llm_api_key="test-key"` — meaningless literal, never a real credential).

**Test file mapping:**

| File | Tests | Requirement |
|------|-------|-------------|
| `test_srt_roundtrip.py` | 6 parametrized byte-identical round-trip | FMT-01 |
| `test_srt_model.py` | SubLine text mutability + timing field preservation | FMT-01 |
| `test_settings.py` | Defaults, env override, YAML load, SecretStr masking | ENG-01 |
| `test_client_tiers.py` | json_schema default, json_object fallback, text fallback, pinned mode | ENG-01 |
| `test_client_concurrency.py` | Semaphore cap at max_concurrency=2 under 5 concurrent callers | ENG-01 |
| `test_client_no_double_retry.py` | No tenacity import, max_retries passed to AsyncOpenAI | ENG-01 |
| `test_client_live.py` | Live endpoint smoke test, `@pytest.mark.live`, CI-excluded | ENG-01 |

Suite result: **20 collected, 19 xfailed, 1 skipped** (live test without `TREZARR_LLM_BASE_URL`). No collection errors. No `PytestUnknownMarkWarning`.

## Deviations from Plan

None — plan executed exactly as written.

The installed package versions are slightly higher than the minimum bounds in pyproject.toml (pytest 9.0.3 vs >=8.4.2, pytest-asyncio 1.4.0 vs >=1.2.0) — this is expected uv behavior and not a deviation.

## Self-Check

**Files verified:**
- [x] `pyproject.toml` exists and valid TOML (`requires-python = ">=3.12"`, `asyncio_mode = "auto"`)
- [x] `config.yaml.example` exists with all 8 fields
- [x] `trezarr/__init__.py` exists
- [x] All 6 fixture files exist with correct byte properties (BOM, CRLF, period timecodes, tags, malformed index)
- [x] All 12 test files exist

**Commits verified:**
- [x] 98725d5 — chore(01-01): project scaffold
- [x] dfc8942 — feat(01-01): golden SRT fixtures
- [x] c5c62d5 — feat(01-01): test stubs

## Self-Check: PASSED
