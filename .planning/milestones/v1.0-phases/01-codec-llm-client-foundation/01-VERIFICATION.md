---
phase: 01-codec-llm-client-foundation
verified: 2026-05-31T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 1: Codec + LLM Client Foundation Verification Report

**Phase Goal:** A standalone subtitle codec that round-trips SRT losslessly and a standalone LLM
client wrapping the user's OpenAI-compatible endpoint — both fully testable without each other.
**Verified:** 2026-05-31
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A real SRT file parses into an internal line model and serializes back byte-identical (indices, timecodes, segmentation preserved exactly) | VERIFIED | 10-fixture parametrized test suite passes green; manual edge-case checks (single trailing newline, extra blank lines, mixed LF-in-CRLF, malformed pass-through) all byte-identical |
| 2 | The codec exposes timecodes/indices as locally-owned data the LLM never touches (text is separable from timing) | VERIFIED | SubLine.text is the sole mutable field; SubLine.index/start_tc/end_tc stored as verbatim strings; `crlf_indices.srt` yields indices ['5','10'] — no normalization; mutating `.text` does not affect other fields |
| 3 | A configured base URL / model / API key produces a successful test call against the user's endpoint, with retries and a concurrency cap | VERIFIED | LLMClient wraps AsyncOpenAI with `max_retries=settings.llm_max_retries` (default 4); asyncio.Semaphore cap confirmed by concurrency test (peak=2 under cap=2 with 5 concurrent callers); all 7 LLM tests pass |
| 4 | The LLM client degrades gracefully (JSON mode fallback) when an endpoint lacks strict structured-output support | VERIFIED | Three-tier degradation: json_schema → json_object → plain text; `test_falls_back_to_json_object_on_400` and `test_falls_back_to_text_on_second_400` pass; pinned mode raises without fallback |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/subtitles/model.py` | SubLine and SubDoc dataclasses | VERIFIED | SubLine(index, start_tc, end_tc, text, raw); SubDoc(lines, encoding, line_ending, separators, leading, trailer); pure dataclasses, no Pydantic |
| `trezarr/subtitles/encoding.py` | detect_encoding(data: bytes) -> str | VERIFIED | BOM-first (utf-8-sig, utf-16-le, utf-16-be) → strict UTF-8 → charset-normalizer with CJK guard; never raises |
| `trezarr/subtitles/srt.py` | read_srt + write_srt, byte-identical | VERIFIED | Rewrote after code review to preserve raw structural bytes (separators, leading, trailer, raw pass-through); 10 fixture files all byte-identical |
| `trezarr/config.py` | TrezarrSettings with YAML+env, SecretStr | VERIFIED | settings_customise_sources override wired; SecretStr llm_api_key confirmed masked in str/repr/model_dump; YAML load verified by test |
| `trezarr/llm/client.py` | LLMClient with Semaphore, tier fallback | VERIFIED | asyncio.Semaphore(max_concurrency); three-tier degradation; tenacity NOT imported; get_secret_value called exactly once in __init__ |
| `tests/fixtures/` (10 files) | SRT fixture files including 4 edge-case fixtures added post-review | VERIFIED | minimal, crlf_indices, period_timecodes, utf8bom, inline_bold, malformed_index, single_trailing_newline, extra_blank_lines, mixed_lf_in_crlf, tc_trailing_data |
| `pyproject.toml` | Python >=3.12, asyncio_mode=auto, all deps | VERIFIED | requires-python=">=3.12", asyncio_mode="auto", openai/pydantic/pydantic-settings/charset-normalizer deps declared; pysubs2 absent |
| `tests/codec/test_srt_roundtrip.py` | Byte-identity golden file tests | VERIFIED | 10 parametrized + 1 malformed pass-through test; all PASS; no xfail markers |
| `tests/llm/test_client_tiers.py` | Tier fallback mocked tests | VERIFIED | 7 LLM tests pass including tier1_returns_parsed_object, tier1_refusal_raises, empty_messages_raises added post-review |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `trezarr/subtitles/srt.py` | `trezarr/subtitles/encoding.py` | `from .encoding import detect_encoding` | VERIFIED | Called at top of read_srt() |
| `trezarr/subtitles/srt.py` | `trezarr/subtitles/model.py` | `from .model import SubDoc, SubLine` | VERIFIED | SubLine constructed in _parse_block, SubDoc returned by read_srt |
| `tests/codec/test_srt_roundtrip.py` | `tests/fixtures/*.srt` | `FIXTURES / fixture` | VERIFIED | FIXTURES path constant in conftest; 10 fixture names in parametrize list |
| `trezarr/llm/client.py` | `trezarr/config.py` | `TrezarrSettings` accepted as settings arg | VERIFIED | `from ..config import TrezarrSettings` (TYPE_CHECKING); runtime duck-typed |
| `trezarr/llm/client.py` | `openai.AsyncOpenAI` | `self._client = AsyncOpenAI(base_url=..., api_key=settings.llm_api_key.get_secret_value(), max_retries=...)` | VERIFIED | get_secret_value count=1 confirmed |
| `tests/config/test_settings.py` | `trezarr.config.TrezarrSettings` | `from trezarr.config import TrezarrSettings` | VERIFIED | All 4 settings tests pass |
| `tests/llm/test_client_tiers.py` | `trezarr.llm.client.LLMClient` | `from trezarr.llm.client import LLMClient` | VERIFIED | All 7 LLM tests pass |

---

### Data-Flow Trace (Level 4)

Not applicable — phase delivers a codec and a client wrapper, not a data-rendering component. The data-flow is verified by the byte-identical round-trip tests and the mocked LLM tier tests.

---

### Behavioral Spot-Checks

| Behavior | Command / Check | Result | Status |
|----------|-----------------|--------|--------|
| Single trailing newline round-trips byte-identical | `read_srt` → `write_srt` on `single_trailing_newline.srt` (b'1\n...\nHello\n') | Exact bytes preserved | PASS |
| Extra blank lines between cues preserved | `read_srt` → `write_srt` on `extra_blank_lines.srt` (b'...Hello\n\n\n2\n...') | Three-blank-line gap preserved | PASS |
| Mixed LF inside a CRLF file preserved | `read_srt` → `write_srt` on `mixed_lf_in_crlf.srt` (Line1\nLine2 in CRLF file) | \n inside CRLF block unchanged | PASS |
| Malformed block emits UserWarning AND is preserved verbatim | `pytest.warns(UserWarning, match='malformed SRT block')` on `malformed_index.srt` | Warning emitted; 2 lines kept; round-trip byte-identical | PASS |
| SecretStr never leaks in str/repr/model_dump | TrezarrSettings(llm_api_key='super-secret') assertions | 'super-secret' absent from all output surfaces | PASS |
| Semaphore caps concurrency | 5 concurrent calls under cap=2, direct asyncio measurement | Peak concurrency = 2 | PASS |
| No tenacity import in client.py | `inspect.getsource(c)` scan | 'tenacity' not in source | PASS |
| pysubs2 not imported | `sys.modules` check after importing srt module | 'pysubs2' not in sys.modules | PASS |
| Full suite is genuinely green (no xfail masking) | `uv run python -m pytest -v` | 27 passed, 1 skipped (live endpoint); zero xfail/xpass | PASS |

---

### Probe Execution

No phase-declared probes found. No conventional `scripts/*/tests/probe-*.sh` files exist. Step skipped.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FMT-01 | Plans 01-01, 01-02 | Trezarr parses and writes SRT, preserving indices, timecodes, and line segmentation exactly (translates text only, never timestamps) | SATISFIED | 10-fixture byte-identical parametrized test suite; SubLine.index/start_tc/end_tc verbatim strings; text is the sole mutable field; no normalization of any timing data |
| ENG-01 | Plans 01-01, 01-03 | User can configure a user-provided OpenAI-SDK-compatible endpoint (base URL, model, API key) that powers all translation | SATISFIED | TrezarrSettings with llm_base_url/llm_model/llm_api_key; LLMClient(settings) wires them to AsyncOpenAI; test_yaml_load + test_env_override + test_settings_loads_defaults all pass |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/conftest.py` | 31 | `pytest.skip("trezarr.config not yet implemented (Plan 03)")` in dead try/except ImportError branch | Info | Dead code — TrezarrSettings is implemented; the guard is never triggered because the import succeeds. Not a regression risk; the skip only activates if the module is deleted. |

No TBD, FIXME, or XXX markers found in any implementation or test file.

The `xfail` string in `tests/codec/test_srt_roundtrip.py` line 7 is inside a docstring comment explaining that xfail markers were removed (per CR-03) — no actual `@pytest.mark.xfail` decorator is present anywhere in the test suite.

---

### Human Verification Required

None. All four success criteria are verifiable programmatically and confirmed green.

---

### Code Review Fix Verification

The phase underwent a mandatory code-review fix pass (01-REVIEW.md → 01-REVIEW-FIX.md) addressing 3 BLOCKER-level and 6 WARNING-level findings before this verification:

- **CR-01** (SRT byte-identity failures): Codec fully rewritten. Verbatim raw structural pieces stored (separators, leading, trailer, SubLine.raw pass-through). All four previously-broken edge cases now byte-identical GREEN.
- **CR-02** (Tier-1 discards parsed object, can return None): Fixed. Tier 1 returns typed Pydantic object when response_model provided; refusal raises RuntimeError; all tiers guard content is not None.
- **CR-03** (stale xfail markers masking real failure): Fixed. All xfail markers removed; the previously-swallowed malformed_index.srt failure is now a real PASS via CR-01 fix.
- **WR-01** (UTF-16 endianness): Fixed. utf-16-le/utf-16-be mapped explicitly.
- **WR-02** (global strip corrupting text): Fixed as part of CR-01 rewrite.
- **WR-03** (timecode fullmatch): Fixed; tc_trailing_data.srt fixture added and passes.
- **WR-04** (bare except Exception): Narrowed to `openai.APIError` subclass.
- **WR-05** (unvalidated messages): Fixed; ValueError raised on empty messages.
- **WR-06** (CJK guard unsafe fallback): Fixed; decode uses errors="replace" in srt.py.

The four Info findings (IN-01 through IN-04) were explicitly out of scope for the fix pass and are not blockers.

---

### Gaps Summary

No gaps. All four observable truths are verified, all required artifacts are substantive and wired, all key links hold, both requirement IDs are satisfied, no debt markers, and the test suite is genuinely green with no xfail masking.

---

_Verified: 2026-05-31_
_Verifier: Claude (gsd-verifier)_
