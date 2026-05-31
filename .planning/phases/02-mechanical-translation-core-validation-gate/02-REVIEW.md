---
phase: 02-mechanical-translation-core-validation-gate
reviewed: 2026-05-31T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - trezarr/translate/sentinel.py
  - trezarr/translate/batching.py
  - trezarr/translate/validate.py
  - trezarr/translate/engine.py
  - trezarr/translate/__init__.py
  - trezarr/output/write.py
  - trezarr/output/ledger.py
  - trezarr/output/__init__.py
  - trezarr/config.py
  - pyproject.toml
  - tests/translate/test_sentinel.py
  - tests/translate/test_batching.py
  - tests/translate/test_validate.py
  - tests/translate/test_engine.py
  - tests/output/test_write.py
  - tests/output/test_ledger.py
findings:
  critical: 1
  warning: 7
  info: 4
  total: 12
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-05-31T00:00:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Reviewed the mechanical translation core: sentinel protection, token-budget
batching, the 7-check validation gate, the end-to-end `translate_file()` engine,
atomic sidecar writes, and the idempotency ledger. The atomic-write pattern
(`NamedTemporaryFile` + `os.replace`, forced UTF-8) is correct in all three call
sites (`write.py`, `ledger.py`, engine quarantine). The asyncio.Semaphore is NOT
doubled — the engine correctly defers all concurrency control to
`LLMClient._semaphore` and never creates its own. Tenacity retry is correctly
scoped to `BatchValidationError` only at the decorator level.

However, the engine's top-level dispatch handler **violates the phase's explicit
Pitfall-5 constraint** by catching `Exception` (including `openai.APIError`) and
permanently quarantining on it — the single BLOCKER. Several robustness gaps in
the validation gate ("monotonic" check does not detect backward jumps), the
numbered-line parser (silent acceptance of over-count and duplicate line numbers),
and the engine's error-handling contract (uncaught `read_srt`/`batch_subdoc`
failures leave files stuck `in_progress`) are documented as warnings.

## Critical Issues

### CR-01: Engine quarantines on `openai.APIError` and swallows all exceptions — violates Pitfall 5 / D-18

**File:** `trezarr/translate/engine.py:448`
**Issue:**
The module's own header (lines 16-18) declares as a *critical constraint*:
"retry_if_exception_type(BatchValidationError) — never includes openai.APIError
(Pitfall 5). … the SDK handles transport failures." But the gather handler is:

```python
except (BatchValidationError, Exception) as exc:
    ...
    quarantine_path = _write_quarantine(path, reason, [], settings)
    ledger.record(LedgerEntry(... status="quarantined" ...))
    return TranslationResult(status="quarantined", ...)
```

`except (BatchValidationError, Exception)` is equivalent to `except Exception`
(the first tuple element is redundant). Consequences:

1. A transient endpoint error that survives the SDK's own `max_retries` (a 503,
   a connection drop, a timeout) is treated as a permanent translation failure:
   it writes a quarantine artifact and records `status="quarantined"` in the
   ledger. This is exactly the failure mode Pitfall 5 forbids — a momentary
   endpoint blip should not produce a quarantine.
2. Genuine programming bugs (`TypeError`, `AttributeError`, `KeyError` from a
   future refactor) are silently converted into a "quarantined" result with the
   exception text as `reason`, instead of surfacing for a fix.

**Fix:** Catch only the batch-level failure type. Let SDK/transport errors and
programming errors propagate (or handle `openai.APIError` distinctly as a
*retryable run failure*, not a quarantine):

```python
from tenacity import RetryError  # if reraise=False were used; here reraise=True

try:
    batch_results = await asyncio.gather(
        *[_translate_batch(b, llm_client, settings) for b in batches]
    )
except BatchValidationError as exc:
    # Retry-exhausted batch gate failure → quarantine (intended path)
    reason = str(exc)
    quarantine_path = _write_quarantine(path, reason, [], settings)
    ledger.record(LedgerEntry(
        source_path=str(path), output_path=None, status="quarantined",
        content_hash=content_hash, quarantine_path=str(quarantine_path),
    ))
    return TranslationResult(status="quarantined", quarantine_path=quarantine_path, reason=reason)
# openai.APIError and any other exception propagate: the file stays out of
# "done" and is retried on the next poll; it is NOT permanently quarantined.
```

Note that `test_quarantine_on_retry_exhaustion` asserts `pytest.raises((TranslationError, Exception))`
on `_translate_batch` directly, so it does not currently pin the `translate_file`
catch behaviour and will not catch this regression.

## Warnings

### WR-01: Check 5 ("monotonic timestamps") does not detect backward jumps

**File:** `trezarr/translate/validate.py:148-158`
**Issue:** The overlap condition requires `start_ms > prev_start_ms AND start_ms < prev_end_ms`.
A cue that starts *before* the previous cue (`start_ms < prev_start_ms`) — a true
non-monotonic ordering violation — passes silently because the first conjunct is
false. Example: cue0 = [5000ms, 10000ms], cue1 = [3000ms, 4000ms]. cue1 starts
3000ms < cue0's 5000ms start, yet `3000 > 5000` is false, so no GateError is
raised. The check is named "monotonic" but only enforces forward non-overlap.
**Fix:** Add an explicit monotonic-start check before the overlap check:

```python
if prev_start_ms is not None and start_ms < prev_start_ms:
    raise GateError(GateFailure(
        5,
        f"Cue {i} starts before previous cue: start={start_ms}ms < prev_start={prev_start_ms}ms",
        failing_indices=[i],
    ))
```

### WR-02: Numbered-line parser silently accepts over-count responses

**File:** `trezarr/translate/engine.py:170-186`
**Issue:** If the LLM returns *more* numbered lines than `expected_count` (e.g.
`[1] [2] [3]` for a 2-cue batch), the validation loop only checks lines
`1..expected_count`, and `len(parsed) < expected_count` is false (it is
*greater*). The extra hallucinated line is dropped silently and no
`BatchValidationError` is raised. A hallucinated extra line is a strong signal of
batch misalignment that should trigger a retry.
**Fix:** Flag any parsed line number outside the expected range:

```python
extra = [n for n in parsed if n < 1 or n > expected_count]
if extra:
    raise BatchValidationError(
        f"LLM response contains unexpected line numbers {extra} (expected 1..{expected_count})"
    )
```

### WR-03: Numbered-line parser silently overwrites duplicate line numbers

**File:** `trezarr/translate/engine.py:162-168`
**Issue:** `parsed[line_num] = text` overwrites on a repeated `[N]`. If the LLM
emits `[1]` twice (common when it restates a line), the later value silently wins
with no detection. Combined with the numbered-line protocol being the sole
guarantee of 1:1 cue mapping (D-13), a duplicate can mask a real off-by-one in the
response without any retry.
**Fix:** Detect duplicates before assignment:

```python
if line_num in parsed:
    raise BatchValidationError(f"Duplicate line number [{line_num}] in LLM response")
parsed[line_num] = text
```

### WR-04: `read_srt` / `batch_subdoc` failures leave file stuck `in_progress`, contract violated

**File:** `trezarr/translate/engine.py:437-441`
**Issue:** Step 4 records `status="in_progress"` (line 430), then Steps 5-6 call
`read_srt(path)` and `batch_subdoc(source_doc, settings)` *outside any try/except*.
`read_srt` can raise (`PermissionError`, decode edge cases) and `batch_subdoc`
can raise on unexpected input. If either does, the exception propagates uncaught
out of `translate_file`, and the ledger is left at `in_progress` forever. The
function docstring (lines 385-388) promises "On any failure … Return
TranslationResult(status='quarantined')." This guarantee is not met for read/batch
failures.
**Fix:** Wrap Steps 5-9 in the same quarantine handler, or at minimum catch
read/batch errors and route them to `_write_quarantine` + a `quarantined` ledger
record so a poisoned source file does not wedge the ledger.

### WR-05: `datetime.utcnow()` is deprecated in Python 3.12 and produces a mislabeled timestamp

**File:** `trezarr/translate/engine.py:329, 516`
**Issue:** `datetime.utcnow()` is deprecated as of Python 3.12 (the project's
pinned runtime, `requires-python = ">=3.12"`). It returns a *naive* datetime, to
which the code appends a literal `"Z"` (`datetime.utcnow().isoformat() + "Z"`),
falsely advertising an offset-aware UTC timestamp. This affects both the
quarantine artifact `timestamp` and the ledger `translated_at`.
**Fix:** Use timezone-aware UTC and let `isoformat()` emit the offset:

```python
from datetime import datetime, timezone
datetime.now(timezone.utc).isoformat()  # -> "...+00:00"
```

### WR-06: Sidecar/dest naming logic is duplicated and can mis-strip non-language 2-letter stems

**File:** `trezarr/output/write.py:53-56` and `trezarr/translate/engine.py:405-410`
**Issue:** The 2-letter-suffix stripping regex `\.[a-z]{2}$` and dest derivation
are copy-pasted into both `write_vi_sidecar` and `translate_file`. Two problems:
(1) Duplication means the two can drift — the engine's skip/idempotency `dest`
must always equal what `write_vi_sidecar` actually writes, or the ledger check and
the written file diverge. (2) The regex strips *any* trailing two lowercase
letters, including non-ISO-639 tokens, e.g. a file ending `.S01E01.tv` or a stem
ending in an unrelated `.io`/`.ts`-style token would be mangled. For Trezarr's
naming this is low-probability, but the shared logic should live in one function.
**Fix:** Export a single `derive_vi_sidecar_path(media_path) -> Path` from
`output/write.py` and call it from both sites so the dest can never diverge.

### WR-07: Corrupt-ledger fallback silently discards the entire ledger on any schema drift

**File:** `trezarr/output/ledger.py:99-103`
**Issue:** `LedgerEntry(**v)` is called for every entry. If a single stored entry
contains an unexpected key (forward-compat schema drift, or a Phase-4 migration
that adds a column), `LedgerEntry(**v)` raises `TypeError`, which the `except`
catches and the code logs "corrupt — starting fresh" and **drops every entry**.
For an idempotency ledger this means re-translating the entire library after a
single malformed/extended record. The handler treats a recoverable per-entry
problem as total loss.
**Fix:** Parse entries individually and skip only the bad ones, and filter unknown
keys before construction:

```python
import dataclasses
valid_keys = {f.name for f in dataclasses.fields(LedgerEntry)}
out = {}
for k, v in raw.items():
    try:
        out[k] = LedgerEntry(**{kk: vv for kk, vv in v.items() if kk in valid_keys})
    except (TypeError, KeyError):
        logger.warning("Ledger entry %s is malformed — skipping that entry", k)
return out
```

## Info

### IN-01: Dead variable `cue_idx` in translated-doc assembly

**File:** `trezarr/translate/engine.py:466, 476`
**Issue:** `cue_idx` is initialised to 0 and incremented in the inner loop but
never read. Dead code.
**Fix:** Remove `cue_idx = 0` and `cue_idx += 1`.

### IN-02: Local `import re` statements scattered inside function bodies

**File:** `trezarr/translate/engine.py:141, 405` (`import re as _re`, `import re as _re2`)
**Issue:** `re` is imported lazily under two different aliases mid-module/mid-
function rather than once at the top. The module already imports `json`, `os`,
`tempfile`, etc. at the top; the `re` imports should join them. Minor consistency
/ readability issue.
**Fix:** Add `import re` to the top-level imports and drop the `_re`/`_re2`
aliases.

### IN-03: `extract_sentinels` uses positional `counter` keys — fragile if reused across cues

**File:** `trezarr/translate/sentinel.py:32-43`
**Issue:** The sentinel counter resets per `extract_sentinels` call, so keys are
`<<T0>>`, `<<T1>>`, … per cue. The engine builds a separate `sentinel_map` per
cue and reinserts per cue (engine.py:255-265), so there is no cross-cue collision
today. This is correct but undocumented — a future change that flattened all cue
texts into one prompt with shared sentinels would silently collide. Worth a
comment noting the per-cue isolation invariant.
**Fix:** Add a docstring note that callers must keep one `sentinel_map` per cue
and never merge maps across cues.

### IN-04: `_tc_to_ms` truncates sub-millisecond precision and silently returns 0 on malformed input

**File:** `trezarr/translate/batching.py:33-40` and `trezarr/translate/validate.py:72-79`
**Issue:** Both copies map a malformed timecode to `0ms`. In batching this can
fabricate a spurious large gap or none; in the gate's check 5 a malformed timecode
becomes `start=0, end=0` → `0 >= 0` → raises check 5 (acceptable, fails closed).
The `0`-on-malformed behaviour is defensible but undocumented at the batching call
site, and the `_tc_to_ms` helper is duplicated verbatim across two modules.
**Fix:** Extract a single shared `_tc_to_ms` (e.g. into `subtitles/` or a small
`translate/_timecode.py`) imported by both, and document the malformed→0 contract.

---

_Reviewed: 2026-05-31T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
