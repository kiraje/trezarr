---
phase: 01-codec-llm-client-foundation
reviewed: 2026-05-31T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - trezarr/config.py
  - trezarr/llm/client.py
  - trezarr/subtitles/encoding.py
  - trezarr/subtitles/model.py
  - trezarr/subtitles/srt.py
  - tests/conftest.py
  - tests/codec/test_srt_model.py
  - tests/codec/test_srt_roundtrip.py
  - tests/config/test_settings.py
  - tests/llm/test_client_concurrency.py
  - tests/llm/test_client_no_double_retry.py
  - tests/llm/test_client_tiers.py
findings:
  critical: 3
  warning: 6
  info: 4
  total: 13
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-05-31
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 1 delivers the SRT codec (`encoding.py`, `model.py`, `srt.py`), the layered
`TrezarrSettings` config, and the async `LLMClient` with three-tier structured-output
fallback. The config layer and SecretStr handling are sound, the encoding-detection guard
is well reasoned, and the no-double-retry / semaphore designs are correct.

However, adversarial testing surfaced **three BLOCKER-level correctness defects** that
directly undermine the phase's stated contracts:

1. The SRT codec **fails byte-identical round-trip** on several real-world inputs — files
   ending in a single newline, files with extra blank lines between cues, malformed cues
   (the project's own `malformed_index.srt` fixture), and cues whose text mixes LF inside a
   CRLF file. The byte-exactness contract (FMT-01 / D-08) is the headline deliverable and it
   is not met. I reproduced every failure by running the shipped `read_srt`/`write_srt`
   against crafted and fixture inputs.
2. The LLM Tier-1 (`json_schema`) path **discards the parsed Pydantic object** and returns
   only the raw JSON string, defeating the purpose of structured outputs and returning
   `None` (violating the `-> str` contract) on a model refusal.
3. The test suite still carries stale `xfail(strict=False)` markers on **fully implemented**
   code, so 18 tests report XPASS and — critically — the one genuinely failing test
   (`malformed_index.srt` round-trip) is silently swallowed as XFAIL. The suite cannot catch
   regressions in this phase's core contract.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: SRT codec is not byte-identical on common real-world inputs (FMT-01 / D-08 violation)

**File:** `trezarr/subtitles/srt.py:69,72,137-139`
**Issue:** The headline contract of this phase is byte-exact round-trip. It fails on at least
four input classes. I confirmed each by running the shipped `read_srt`/`write_srt`:

1. **Single trailing newline** — `b'1\n00:00:01,000 --> 00:00:03,000\nHello\n'` round-trips to
   `...Hello` (the trailing `\n` is lost). `trailing_newline` is a *boolean* that only records
   whether a *blank line* (`le+le`) terminated the file; a single terminating newline (the most
   common SRT shape) cannot be represented, so `write_srt` drops it. This is not an edge case —
   most editors save a final newline.
2. **Extra blank lines between cues** — `...Hello\n\n\n2\n...` collapses to `...Hello\n\n2...`.
   `re.split(r"\r?\n\r?\n", text.strip())` plus `(le+le).join(...)` normalises any run of blank
   lines to exactly one, mutating bytes.
3. **Mixed line endings inside a CRLF file** — `b'...\r\nLine1\nLine2\r\n\r\n'` becomes
   `...\r\nLine1\r\nLine2\r\n\r\n`. `block.splitlines()` splits on the inner `\n`, then
   `le.join(...)` rejoins with `\r\n`, rewriting cue text. This also violates D-09 ("text
   preserved verbatim, the only LLM-mutable field").
4. **Malformed cue (the project's own fixture)** — `malformed_index.srt` contains a valid cue
   followed by an `abc`-indexed cue. `read_srt` *skips* the malformed block (D-10), so
   `write_srt` emits only the first cue and the round-trip is not byte-identical. The shipped
   test `test_byte_identical_roundtrip[malformed_index.srt]` actually FAILS today (it only
   reports XFAIL because of the stale marker — see CR-03). D-10 ("preserve-and-flag") and
   FMT-01 ("byte-identical") are in direct conflict: a skipped block cannot be written back.

**Fix:** The byte-exact guarantee requires preserving raw structure rather than reconstructing
it from normalised fields. Concretely:
- Replace the boolean `trailing_newline` with the captured trailing byte sequence (e.g. store
  `trailer: str` = whatever followed the last cue: `""`, `le`, or `le+le`).
- Preserve inter-cue separators instead of normalising via `(le+le).join`.
- Store each cue's original text bytes/separators verbatim (do not `splitlines()`+`join`).
- For malformed blocks, either (a) keep them as opaque pass-through blocks so write-back
  re-emits them unchanged, or (b) explicitly amend FMT-01 to exclude malformed files and add a
  test asserting the *documented* lossy behaviour. Do not leave the contract claiming
  byte-identity while the fixture proves otherwise.

```python
# Example: opaque pass-through for malformed blocks preserves byte identity
@dataclass
class SubLine:
    index: str; start_tc: str; end_tc: str; text: str
    raw: str | None = None      # original block text, used verbatim on write if set
# write_srt emits sl.raw when present, else reconstructs from fields.
```

### CR-02: Tier-1 structured output discards the parsed object and can return None

**File:** `trezarr/llm/client.py:111-116,63`
**Issue:** `call()` is annotated `-> str` and the docstring promises typed structured outputs
("the Series Bible ... come back as typed Pydantic objects"). But the Tier-1 path does:

```python
parsed = await self._client.chat.completions.parse(...)
return parsed.choices[0].message.content   # raw JSON string, NOT the parsed object
```

`ParsedChatCompletionMessage` (openai 2.38.0, confirmed) carries the typed object in
`.parsed`; `.content` is just the raw JSON string and is **`None` on a refusal**. Two bugs:
1. The whole value of Tier 1 is thrown away — callers receive the same untyped JSON string they
   would get from Tier 2, so the Series Bible structured-output promise is unfulfilled.
2. On a model refusal, `.content` is `None`, silently violating the `-> str` contract and
   pushing a `None` into downstream parsing (which will raise far from the source).

**Fix:** Return the parsed object from Tier 1 (and update the signature), and guard against
`None` content on every tier:

```python
parsed = await self._client.chat.completions.parse(...)
msg = parsed.choices[0].message
if getattr(msg, "refusal", None):
    raise RuntimeError(f"LLM refused structured output: {msg.refusal}")
if response_model is not None and msg.parsed is not None:
    return msg.parsed            # typed Pydantic object — change return type to BaseModel | str
content = msg.content
if content is None:
    raise RuntimeError("LLM returned empty content")
return content
```
Apply the same `None`-content guard to the Tier-2 and Tier-3 returns at lines 136 and 147.

### CR-03: Stale xfail markers mask a real test failure and disable regression detection

**File:** `tests/codec/test_srt_roundtrip.py:23`, `tests/codec/test_srt_model.py:10,25`, `tests/config/test_settings.py:11,24,34,46`, `tests/llm/test_client_concurrency.py:13`, `tests/llm/test_client_no_double_retry.py:13,30`, `tests/llm/test_client_tiers.py:25,46,84,124`
**Issue:** Every test is still marked `@pytest.mark.xfail(strict=False, reason="... not yet
implemented")`, but the implementation has shipped. Running the suite yields **18 XPASS, 1
XFAIL, 1 skip**. With `strict=False`:
- The 18 XPASS tests do not assert anything enforceably — a future regression that breaks them
  would flip XPASS→XFAIL and the suite would still report green.
- The single XFAIL (`test_byte_identical_roundtrip[malformed_index.srt]`) is a **genuine
  failure** (see CR-01) being silently absorbed. The codec's most important contract has a
  failing test and CI is green.

**Fix:** Remove the `xfail` markers from all implemented tests so they assert for real, then
either fix the `malformed_index.srt` round-trip (CR-01) or change that specific test to assert
the documented lossy behaviour. Leaving `strict=False` xfails on shipped code makes the suite
unable to detect regressions in this phase's core deliverable.

## Warnings

### WR-01: Encoding detected on raw bytes but line-ending/trailing logic ignores BOM/encoding nuances

**File:** `trezarr/subtitles/srt.py:60-69`
**Issue:** For `utf-16` (detected from a `\xff\xfe`/`\xfe\xff` BOM), `text = raw_bytes.decode("utf-16")`
yields a str without the BOM, and `write_bytes(result.encode("utf-16"))` re-adds a BOM but with
the platform's native endianness — which may differ from the source (`utf-16-le` vs `utf-16-be`).
A big-endian source file will not round-trip byte-identically. The `utf-8-sig` case happens to
work (round-trips the BOM) but UTF-16 endianness is unhandled.
**Fix:** Map the BOM to the explicit codec: `\xff\xfe` → `utf-16-le` (re-add `\xff\xfe`),
`\xfe\xff` → `utf-16-be`, and preserve the BOM on write. Add a UTF-16 fixture to the round-trip
parametrize list — there is currently zero UTF-16 coverage.

### WR-02: `text.strip()` before block split can corrupt leading-whitespace cue text

**File:** `trezarr/subtitles/srt.py:72,76`
**Issue:** `re.split(..., text.strip())` and `block.strip()` strip leading/trailing whitespace.
If the file legitimately begins with blank lines, or a cue's first text line is intentionally
indented and the block boundary detection interacts with it, the stripped characters are not
recoverable on write-back, breaking byte identity. Combined with CR-01 this is part of the
"reconstruct from normalised fields" anti-pattern.
**Fix:** Avoid global `strip()`; capture leading/trailing file bytes explicitly as part of the
preserved structure (see CR-01 fix).

### WR-03: Timecode regex uses `.match`, silently tolerating trailing garbage on the timecode line

**File:** `trezarr/subtitles/srt.py:32-36,92`
**Issue:** `_TC_RE.match(block_lines[1])` matches a prefix and ignores anything after the end
timecode (e.g. `00:00:01,000 --> 00:00:03,000 X1:Y1:... position data`). Such trailing data
(legal in some SRT variants for coordinates) is parsed away into nothing and lost on write-back,
silently breaking byte identity without even a warning.
**Fix:** Either anchor with `$` and treat trailing data as malformed (warn), or capture the full
timecode line verbatim and re-emit it unchanged. Given the byte-exact goal, capturing the raw
timecode line verbatim is the correct choice.

### WR-04: `_call_with_fallback` bare `except Exception` in Tier 1 can swallow programming errors

**File:** `trezarr/llm/client.py:121-126`
**Issue:** In `auto` mode, the Tier-1 block catches `except Exception:` and falls through to
Tier 2 for *any* error, including `TypeError`/`AttributeError`/`KeyError` from a genuine bug in
the call construction or a malformed `messages` argument. A real coding error would be masked as
a silent tier downgrade, and the comment admits this branch exists mainly for "test injection."
This contradicts the file's own Pitfall-7 policy of catching only typed OpenAI exceptions.
**Fix:** Narrow the catch to the transport/SDK exception families that should trigger fallback
(e.g. `openai.APIError` subclasses that are not retryable, or specifically the not-supported
signals), and let `TypeError`/`AttributeError` propagate. If test injection needs a broad error,
have the test raise an `openai` exception type instead of bare `Exception`.

### WR-05: `messages: list[dict]` parameter is mutable and untyped; no validation

**File:** `trezarr/llm/client.py:60-61`
**Issue:** `call(messages: list[dict], ...)` accepts any list of dicts with no validation. An
empty list, or dicts missing `role`/`content`, will only fail deep inside the SDK with an opaque
error. For a "replace a human translator / trustworthy blind" quality bar, malformed input
should fail fast and clearly at the boundary.
**Fix:** Validate non-empty and required keys at entry, or type as
`list[ChatCompletionMessageParam]` and add an explicit guard:
`if not messages: raise ValueError("messages must be non-empty")`.

### WR-06: `_CJK_CODECS` guard returns "utf-8" even when the bytes are NOT valid UTF-8

**File:** `trezarr/subtitles/encoding.py:84-93`
**Issue:** Tier 3 is only reached when the bytes already failed a strict UTF-8 decode (Tier 2).
When charset-normalizer guesses a CJK codec, the function returns `"utf-8"` anyway — but the
subsequent `raw_bytes.decode("utf-8")` in `read_srt` (srt.py:60) will then raise
`UnicodeDecodeError`, crashing the read of exactly the CP1258 files this guard claims to handle
gracefully. The "safe fallback" is not safe; it converts a recoverable mis-detection into a hard
crash.
**Fix:** Decode defensively in `read_srt` (`raw_bytes.decode(encoding, errors="replace")`) or
have the guard fall back to a codec that cannot raise (e.g. `cp1258` itself, or `latin-1`), not
`utf-8`. At minimum, document that the returned codec may not successfully decode and ensure the
caller handles `UnicodeDecodeError`.

## Info

### IN-01: Thread-local YAML override is correct but fragile across async boundaries

**File:** `trezarr/config.py:28,64-77,94`
**Issue:** `_tl.yaml_file` is set/cleared around `super().__init__`, which is synchronous, so it
is currently safe. But the pattern is brittle: any future async work inside settings
construction, or nested `TrezarrSettings()` construction, would interleave the thread-local.
**Fix:** Document that construction must remain synchronous, or pass the path via a
`SettingsConfigDict` extra / contextvar instead of `threading.local`.

### IN-02: `detect_encoding` accesses `data[:3]` / `data[:2]` — fine for empty, but no explicit empty-file path

**File:** `trezarr/subtitles/encoding.py:66-73`
**Issue:** Empty `b""` returns `"utf-8"` correctly (slicing empty bytes is safe and the UTF-8
decode of `b""` succeeds). Behaviour is correct but undocumented; an explicit early return would
make intent clear.
**Fix:** Add `if not data: return "utf-8"` at the top with a comment, or add an empty-bytes unit
test to lock the behaviour.

### IN-03: Live test default api_key "not-set" and dummy keys are fine, but `model_dump()` exposure note

**File:** `tests/llm/test_client_live.py:42`, `trezarr/config.py:48`
**Issue:** Default `llm_api_key=SecretStr("not-set")` and the live test's `"not-set"` default are
harmless placeholders. No real secret is committed. Confirmed SecretStr masks str/repr/model_dump.
This is informational confirmation that secret handling passes, not a defect.
**Fix:** None required. Optionally assert in a test that `get_secret_value()` is the *only* call
site (already true: only `client.py:51`).

### IN-04: `test_semaphore_caps_concurrent_calls` relies on `asyncio.sleep(0)` single yield — weak concurrency proof

**File:** `tests/llm/test_client_concurrency.py:38`
**Issue:** A single `await asyncio.sleep(0)` yields exactly once. The test happens to observe
peak<=2 with 5 tasks and cap 2, but a single yield is a thin guarantee — it does not robustly
force maximal interleaving. The test is not wrong, but it could pass even if the semaphore were
mis-sized in some scheduling orders.
**Fix:** Use an `asyncio.Event` or a small real sleep that all in-flight tasks block on, so peak
concurrency is deterministically observed before any task releases the semaphore.

---

_Reviewed: 2026-05-31_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
