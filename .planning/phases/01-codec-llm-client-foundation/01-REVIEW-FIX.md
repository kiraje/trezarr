---
phase: 01-codec-llm-client-foundation
fixed_at: 2026-05-31T00:00:00Z
review_path: .planning/phases/01-codec-llm-client-foundation/01-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 1: Code Review Fix Report

**Fixed at:** 2026-05-31
**Source review:** .planning/phases/01-codec-llm-client-foundation/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 9
- Fixed: 9
- Skipped: 0

**Final test run (`uv run python -m pytest -q`):**

```
27 passed, 1 skipped in 0.61s
```

No xfail / xpass remain — the suite is genuinely green (no strict-xfail masking).
The previously-masked `malformed_index.srt` round-trip now passes for real, and the
four newly added edge-case fixtures (single trailing newline, extra blank lines,
mixed LF-in-CRLF, trailing timecode data) are exercised and GREEN. The single skip
is `test_client_live.py` (requires a live LLM endpoint — intentional).

## Fixed Issues

### CR-01: SRT codec is not byte-identical on common real-world inputs (FMT-01 / D-08)

**Files modified:** `trezarr/subtitles/model.py`, `trezarr/subtitles/srt.py`,
`tests/codec/test_srt_roundtrip.py`, plus 4 new fixtures
(`tests/fixtures/single_trailing_newline.srt`, `extra_blank_lines.srt`,
`mixed_lf_in_crlf.srt`, `tc_trailing_data.srt`)
**Commit:** b7096c2
**Applied fix:** Rewrote the codec to preserve raw byte structure instead of
reconstructing from normalised fields.

- `SubDoc` now stores `separators` (verbatim inter-cue bytes), `leading`, and
  `trailer` strings instead of a boolean `trailing_newline`. The file is
  reconstructed exactly as `leading + block[0] + sep[0] + ... + block[n-1] + trailer`.
- `SubLine` gained an opaque `raw` pass-through field. Malformed blocks (and any
  block whose mixed line endings can't be losslessly reconstructed) keep `raw` set
  and are re-emitted verbatim, reconciling D-10 (preserve-and-flag) with FMT-01
  (byte-identical). The malformed cue is no longer *skipped*.
- `read_srt` splits on a capturing blank-line separator regex (so extra blank lines
  survive), captures leading/trailing structural whitespace, and recovers each cue's
  text body by stripping the exact index+timecode prefix — never `splitlines()+join`,
  so mixed LF-in-CRLF text and a single terminating newline round-trip verbatim.
- New `test_byte_identical_roundtrip` parametrisation covers all four previously-broken
  input classes; new `test_malformed_block_preserved_and_flagged` asserts the
  preserve-and-flag (UserWarning + verbatim) behaviour explicitly.

All 6 original fixtures + 4 new fixtures + the malformed passthrough test are byte-identical GREEN.

### CR-02: Tier-1 structured output discards the parsed object and can return None

**Files modified:** `trezarr/llm/client.py`, `tests/llm/test_client_tiers.py`,
`tests/llm/test_client_concurrency.py`
**Commit:** 5e513bc
**Applied fix:** Tier 1 now returns the typed Pydantic object from
`message.parsed` when a `response_model` was requested, instead of the raw JSON
`message.content`. A model refusal raises `RuntimeError` rather than returning
`None`, and every tier (1/2/3) guards `content is None` and raises rather than
leaking `None` downstream. The `call()` / `_call_with_fallback()` return type
widened to `BaseModel | str`. Added `test_tier1_returns_parsed_object` and
`test_tier1_refusal_raises`.

_Note: this finding includes a typed-object/return-contract change — verified by the
two new tests asserting the parsed object is returned and refusal raises._

### CR-03: Stale xfail markers mask a real test failure and disable regression detection

**Files modified:** `tests/codec/test_srt_model.py`, `tests/config/test_settings.py`,
`tests/llm/test_client_no_double_retry.py`
**Commit:** aa5d7c7 (plus the round-trip/tier/concurrency test files de-xfailed in
b7096c2 and 5e513bc respectively)
**Applied fix:** Removed every `@pytest.mark.xfail(strict=False, reason="... not yet
implemented")` marker from the shipped tests and cleaned up the stale docstrings and
now-unused imports. The suite now asserts for real: 18 former XPASS → PASS, and the
former silently-swallowed XFAIL (`malformed_index.srt` round-trip) is GREEN for real
via CR-01. There is no remaining xfail/xpass in the suite.

### WR-01: UTF-16 BOM endianness not preserved on write-back

**Files modified:** `trezarr/subtitles/encoding.py`
**Commit:** 124f72d
**Applied fix:** `detect_encoding` now maps `\xff\xfe` → `"utf-16-le"` and
`\xfe\xff` → `"utf-16-be"` (explicit endianness) instead of the generic `"utf-16"`,
which re-encoded with platform-native endianness and stripped the BOM. Verified that
both LE and BE sources round-trip the BOM through decode→encode.

### WR-02: `text.strip()` before block split can corrupt leading-whitespace cue text

**Files modified:** `trezarr/subtitles/srt.py`
**Commit:** b7096c2 (folded into the CR-01 codec rewrite)
**Applied fix:** The global `text.strip()` / `block.strip()` anti-pattern was removed
as part of the CR-01 rewrite. Leading blank lines are captured verbatim into
`SubDoc.leading`; cue text bytes are preserved without stripping. The
`leading_blank_lines` edge case round-trips byte-identically.

### WR-03: Timecode regex uses `.match`, silently tolerating trailing garbage

**Files modified:** `trezarr/subtitles/srt.py`
**Commit:** b7096c2 (folded into the CR-01 codec rewrite)
**Applied fix:** `_TC_RE.match(...)` → `_TC_RE.fullmatch(timecode_line.strip())`, so a
timecode line with trailing coordinate data no longer parses to a lossy structured
form. Such a block is flagged (UserWarning) and preserved verbatim via the `raw`
pass-through. Covered by the new `tc_trailing_data.srt` fixture (byte-identical GREEN).

### WR-04: Bare `except Exception` in Tier 1 can swallow programming errors

**Files modified:** `trezarr/llm/client.py`, `tests/llm/test_client_concurrency.py`
**Commit:** 5e513bc
**Applied fix:** The Tier-1 fallback catch narrowed from bare `except Exception` to
`except openai.APIError`, so only SDK transport/API errors trigger a tier downgrade;
`TypeError`/`AttributeError`/`KeyError` from a genuine bug now propagate. The
concurrency test was updated to inject a typed `openai.BadRequestError` (instead of a
bare `Exception`) to drive the Tier-1 → Tier-2 fallback, per the finding's guidance.

### WR-05: `messages` parameter unvalidated; malformed input fails deep in the SDK

**Files modified:** `trezarr/llm/client.py`, `tests/llm/test_client_tiers.py`
**Commit:** 5e513bc
**Applied fix:** `call()` now raises `ValueError("messages must be a non-empty list ...")`
at the boundary when `messages` is empty, failing fast and clearly. Added
`test_empty_messages_raises`.

### WR-06: `_CJK_CODECS` guard returns "utf-8" even when bytes are NOT valid UTF-8

**Files modified:** `trezarr/subtitles/encoding.py`, `trezarr/subtitles/srt.py`
**Commit:** 124f72d (encoding.py), b7096c2 (the defensive-decode line in srt.py, folded
into the CR-01 rewrite)
**Applied fix:** `read_srt` now decodes with `errors="replace"` so a CP1258 file the
CJK guard mis-detects as `"utf-8"` degrades to replacement characters instead of a hard
`UnicodeDecodeError` — the read of exactly the files the guard claims to handle no
longer crashes. The encoding.py comment documents that the returned codec may not
strictly decode and the caller compensates.

## Skipped Issues

None — all 9 in-scope (Critical + Warning) findings were fixed.

The 4 Info findings (IN-01 thread-local YAML, IN-02 empty-file path, IN-03 SecretStr
confirmation, IN-04 weak concurrency proof) were out of scope for this
`critical_warning` run and were not addressed.

---

_Fixed: 2026-05-31_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
