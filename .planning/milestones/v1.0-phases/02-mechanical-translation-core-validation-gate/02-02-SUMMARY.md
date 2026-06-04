---
phase: "02"
plan: "02"
subsystem: "translate + output"
tags: [tdd, green-phase, sentinel, batching, validation-gate, atomic-write, ENG-02, ENG-03, ENG-06, FMT-05, D-12, D-14, D-15, D-16, D-17, D-19]
dependency_graph:
  requires:
    - "02-01"  # RED test suite (all 36 stubs must be in place)
    - "trezarr/subtitles/model.py"  # SubDoc, SubLine
    - "trezarr/subtitles/srt.py"    # write_srt() reused in write_vi_sidecar
    - "trezarr/config.py"           # TrezarrSettings extended with Phase-2 fields
  provides:
    - "trezarr/translate/__init__.py"
    - "trezarr/translate/sentinel.py"
    - "trezarr/translate/batching.py"
    - "trezarr/translate/validate.py"
    - "trezarr/output/__init__.py"
    - "trezarr/output/write.py"
    - "trezarr/config.py (Phase-2 fields)"
  affects:
    - "Phase 02 Plan 03 (engine.py wires LLM calls on top of these primitives)"
tech_stack:
  added: []
  patterns:
    - "TAG_RE = re.compile(r'(<[^>]+>|{\\[^}]+})') — SRT + ASS inline tag sentinel extraction"
    - "NamedTemporaryFile(dir=dest.parent, delete=False) + os.replace() — POSIX-atomic sidecar write"
    - "_LANG_CODE_RE = re.compile(r'\\.[a-z]{2}$', re.IGNORECASE) — 2-letter lang-code stem stripping"
    - "VN_DIACRITIC_RE covers U+1E00-U+1EFF plus Ơ/ơ and Ư/ư (U+01A0-B0) — full Vietnamese range"
    - "ALLOWLIST_RE = re.compile(r'^[\\W\\d\\s♪♫…\\.]+$') — punctuation/symbol lines exempt from VI ratio"
    - "TYPE_CHECKING guard for TrezarrSettings — avoids circular import at runtime"
key_files:
  created:
    - trezarr/translate/__init__.py
    - trezarr/translate/sentinel.py
    - trezarr/translate/batching.py
    - trezarr/translate/validate.py
    - trezarr/output/__init__.py
    - trezarr/output/write.py
  modified:
    - trezarr/config.py
decisions:
  - "VN_DIACRITIC_RE extended to include Ơ/ơ (U+01A0/U+01A1) and Ư/ư (U+01AF/U+01B0) in addition to U+1E00-U+1EFF — basic Vietnamese text without full tonal diacritics (e.g. 'Xin chào tôi ơi') uses ơ but not U+1E00+ chars"
  - "Check 5 monotonic gate allows simultaneous-start cues (start_ms[i] == start_ms[i-1]) — real-world SRTs with concurrent display lines are accepted; only TRUE overlaps (start_ms[i] > prev_start and start_ms[i] < prev_end) are rejected"
  - "_LANG_CODE_RE strips only the last 2-letter segment from the stem — covers .en/.ja/.fr patterns without mishandling show titles"
metrics:
  duration: "10 min"
  completed: "2026-05-31"
  tasks_completed: 2
  files_created: 6
  files_modified: 1
---

# Phase 02 Plan 02: Mechanical Translation Core — Transform Layer Summary

Pure-Python transformation layer implemented: sentinel protection (D-12), token-budget batch packing with scene-gap detection (D-14/D-15), the 7-check validation gate (D-16/D-17), and atomic UTF-8 sidecar write (D-19). TrezarrSettings extended with 9 Phase-2 configuration fields. All 25 RED stubs in test_batching, test_sentinel, test_validate, and test_write are now GREEN.

## What Was Built

7 files created/modified:

| File | Exports | Requirements |
|------|---------|-------------|
| `trezarr/translate/__init__.py` | — (package marker) | — |
| `trezarr/translate/sentinel.py` | `TAG_RE`, `extract_sentinels`, `reinsert_sentinels` | D-12 |
| `trezarr/translate/batching.py` | `Batch`, `batch_subdoc` | ENG-02, D-14, D-15 |
| `trezarr/translate/validate.py` | `GateFailure`, `GateError`, `validate_subdoc` | ENG-06, D-16, D-17 |
| `trezarr/output/__init__.py` | — (package marker) | — |
| `trezarr/output/write.py` | `write_vi_sidecar` | FMT-05, D-19 |
| `trezarr/config.py` | 9 new `translate_*` fields | ENG-02, ENG-03, ENG-06 |

## Verification Results

```
uv run pytest tests/translate/test_batching.py tests/translate/test_sentinel.py -x -q
→ 12 passed in 0.05s

uv run pytest tests/translate/test_validate.py tests/output/test_write.py -x -q
→ 13 passed in 0.13s

uv run pytest tests/translate/ tests/output/ -x -q
→ 25 passed, 11 skipped in 0.09s  (engine + ledger still skip — correct)

uv run pytest -q (full suite including Phase 1 tests)
→ 52 passed, 12 skipped in 0.55s
```

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: sentinel + batching + config | 8f167bc | trezarr/translate/__init__.py, sentinel.py, batching.py, config.py |
| Task 2: validate + write | a89f375 | trezarr/translate/validate.py, trezarr/output/__init__.py, output/write.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] VN_DIACRITIC_RE expanded to cover Ơ/ơ and Ư/ư (U+01A0/01A1/01AF/01B0)**
- **Found during:** Task 2 — test_gate_sentinel_orphan failed because "Xin chào <<T0>> tôi ơi" has no U+1E00+ chars
- **Issue:** RESEARCH.md specifies `[Ḁ-ỿ]` (U+1E00-U+1EFF), but basic Vietnamese text like "Xin chào tôi ơi" uses ơ (U+01A1) and similar chars from Latin Extended-B, which fall outside U+1E00+. Check 3 would falsely reject a valid translation containing an orphan sentinel because it first fires on the VI ratio.
- **Fix:** Extended to `[Ḁ-ỿƠơƯư]` — added the two uniquely Vietnamese "horn" vowels Ơ/ơ and Ư/ư. These are not used in French/Spanish/German, so the false-positive protection is maintained.
- **Files modified:** trezarr/translate/validate.py (VN_DIACRITIC_RE definition)
- **Commit:** a89f375

**2. [Rule 1 - Bug] Check 5 monotonic gate uses `start_ms > prev_start_ms` guard for overlap detection**
- **Found during:** Task 2 — test_gate_vi_ratio_allowlist_exempt failed; the allowlist test uses the same default timecode (00:00:01,000 → 00:00:03,000) for all 5 lines, making adjacent lines appear overlapping
- **Issue:** The RESEARCH.md implementation of check 5 (`start_ms[i] < end_ms[i-1]`) would reject simultaneous-start cues — a common pattern in real-world SRTs where two lines appear at the same time (e.g. two speakers).
- **Fix:** Added `start_ms > prev_start_ms` guard: overlap is only flagged when the current cue starts AFTER the previous cue started AND before the previous cue ends (true temporal overlap). Simultaneous-start cues (start_ms[i] == start_ms[i-1]) are allowed.
- **Files modified:** trezarr/translate/validate.py (_check_monotonic function)
- **Commit:** a89f375

## Known Stubs

None. All created files are full implementations, not stubs. The 11 still-skipping tests (test_engine.py x5, test_ledger.py x6) are for Plan 02-03 (engine.py) and Plan 02-02 (ledger.py, still future work).

## Threat Flags

None. This plan implements:
- validate_subdoc() as the V5 Input Validation control (T-02-02-01)
- NamedTemporaryFile(dir=dest.parent) + os.replace() for atomic write (T-02-02-03)
- Path(media_path).resolve() for absolute path validation at entry to write_vi_sidecar (T-02-02-04)

No new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

Files exist check:
- trezarr/translate/__init__.py: FOUND
- trezarr/translate/sentinel.py: FOUND
- trezarr/translate/batching.py: FOUND
- trezarr/translate/validate.py: FOUND
- trezarr/output/__init__.py: FOUND
- trezarr/output/write.py: FOUND

Commits exist check:
- 8f167bc (Task 1): FOUND
- a89f375 (Task 2): FOUND

Config fields check:
- translate_chars_per_token=3.5, translate_max_cues_per_batch=50, translate_vi_diacritic_ratio=0.7: VERIFIED (uv run python -c confirmed)
