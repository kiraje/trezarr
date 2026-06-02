---
phase: 09-multi-format-ass-ssa-vtt
plan: "02"
subsystem: subtitles/translate
tags:
  - timecode
  - sentinel
  - model
  - ASS
  - VTT
  - D-92
  - D-98
  - D-101
dependency_graph:
  requires:
    - 09-01
  provides:
    - SubDoc.envelope carrier for ASS/VTT codecs
    - tc_to_ms extended for ASS centiseconds and VTT hourless timecodes
    - sentinel TAG_RE protecting ASS \\N/\\n/\\h hard breaks
  affects:
    - trezarr/subtitles/model.py
    - trezarr/translate/_timecode.py
    - trezarr/translate/sentinel.py
    - All downstream codecs that set SubDoc.envelope
    - All consumers of tc_to_ms (batching.py, validate.py)
tech_stack:
  added: []
  patterns:
    - Cascaded-regex match chain in tc_to_ms (SRT first, ASS second, VTT-hours third, VTT-hourless last)
    - object-typed envelope field avoids circular import between model.py and codec modules
    - TAG_RE extended with fixed two-character arm (no quantifiers, ASVS L1 compliant)
key_files:
  created: []
  modified:
    - trezarr/subtitles/model.py
    - trezarr/translate/_timecode.py
    - trezarr/translate/sentinel.py
decisions:
  - "tc_to_ms try-order: SRT first (variable-digit ms group would shadow VTT fixed-digit groups if tried after); ASS second (2-digit centiseconds distinguishable from VTT 3-digit ms by group width + anchor $)"
  - "envelope field typed as object (not Any) to avoid importing typing and to make the intent explicit — pipeline must not introspect it"
  - "sentinel \\[Nnh] arm added only (Extension C entity refs deferred per RESEARCH §5.2 low-priority rating)"
metrics:
  duration: "6 min"
  completed: "2026-06-02"
  tasks: 2
  files: 3
---

# Phase 9 Plan 02: Shared Foundation — envelope, tc_to_ms extension, sentinel hard-breaks

One-liner: Three targeted file extensions (SubDoc.envelope, tc_to_ms ASS/VTT regexes, TAG_RE \\[Nnh] arm) unblocking every downstream ASS/VTT codec plan without touching the SRT pipeline.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | SubDoc.envelope field + tc_to_ms extension (D-92, D-101) | 79c6f67 | model.py, _timecode.py |
| 2 | sentinel.py TAG_RE extension for ASS \\N/\\n/\\h (D-98) | 14e96d0 | sentinel.py |

## What Was Built

### Task 1 — SubDoc.envelope + tc_to_ms extension

**model.py (D-92):** Added `envelope: object = None` as the last field of `SubDoc`. The field is typed `object` to avoid circular imports between model.py and the codec modules (ass.py, vtt.py) that will set it. The pipeline (batching, sentinel, gate, engine) never reads this field — only the codec that set it reads it back at write time.

**_timecode.py (D-101):** Replaced the single-regex module body with a four-regex cascaded match chain:
- `_TC_PARSE_RE` — existing SRT pattern, unchanged, tried first (variable-digit ms group would shadow the fixed-digit VTT patterns if tried later)
- `_ASS_TC_RE` — `(\d+):(\d{2}):(\d{2})\.(\d{2})$` — 1+ hour digits, exactly 2 centisecond digits, period only, anchored; cc * 10 = ms
- `_VTT_HOURS_TC_RE` — `(\d+):(\d{2}):(\d{2})\.(\d{3})$` — 2+ hour digits, exactly 3 ms digits
- `_VTT_HOURLESS_TC_RE` — `(\d+):(\d{2})\.(\d{3})$` — no hours, exactly 3 ms digits

The malformed→0 contract is preserved unchanged. The function signature is unchanged.

### Task 2 — sentinel.py TAG_RE extension (D-98)

Changed one line in sentinel.py:

```python
# Before:
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\})')

# After:
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\}|\\[Nnh])')
```

The new `\\[Nnh]` arm matches literal backslash + N, n, or h — the ASS hard-break sequences that appear as raw text in the cue Text field (not inside `{}`). The replacer closure and reinsertion loop pick up the new arm automatically via `TAG_RE.sub`. No other lines changed.

## Verification

```
tests/translate/test_timecode.py          4 passed, 4 xpassed (all ASS/VTT stubs now pass)
tests/translate/test_sentinel_ass_vtt.py  5 xpassed (\\N, \\n, \\h, <v>, inline timestamp stubs pass)
tests/translate/test_sentinel.py          7 passed (no regression)
tests/translate/test_validate.py          all passed
tests/translate/test_batching.py          all passed
Full suite (pytest tests/):               302 passed, 35 skipped, 8 xfailed, 10 xpassed, 0 failed
```

## Success Criteria Check

- [x] SubDoc.envelope field exists as `object = None` at end of SubDoc dataclass
- [x] tc_to_ms("0:01:23.45") == 83450 (ASS centiseconds)
- [x] tc_to_ms("01:23.456") == 83456 (VTT hourless)
- [x] tc_to_ms SRT regression: tc_to_ms("00:00:01,000") == 1000, tc_to_ms("garbage") == 0
- [x] sentinel.py TAG_RE contains \\[Nnh] arm
- [x] pytest tests/ -x -q passes (full suite green)

## Deviations from Plan

None — plan executed exactly as written. Both tasks matched the PATTERNS.md and RESEARCH §5.2/§6.2 specs verbatim.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The three modified files are pure in-process utilities. All three threat register items (T-09-02-A, T-09-02-B, T-09-02-C) are mitigated or accepted per the plan's threat model — all new regex patterns use anchored, fixed-width groups with no nested quantifiers.

## Known Stubs

None. All three changes are complete implementations, not stubs.

## Self-Check: PASSED

- trezarr/subtitles/model.py — FOUND (contains `envelope: object = None`)
- trezarr/translate/_timecode.py — FOUND (contains `_ASS_TC_RE`, `_VTT_HOURS_TC_RE`, `_VTT_HOURLESS_TC_RE`)
- trezarr/translate/sentinel.py — FOUND (TAG_RE contains `\\[Nnh]`)
- Commit 79c6f67 — FOUND in git log
- Commit 14e96d0 — FOUND in git log
- Full suite: 302 passed, 0 failed — CONFIRMED
