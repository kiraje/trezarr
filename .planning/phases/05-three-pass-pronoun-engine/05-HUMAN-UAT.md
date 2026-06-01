---
status: partial
phase: 05-three-pass-pronoun-engine
source: [05-VERIFICATION.md]
started: 2026-06-02T00:00:00Z
updated: 2026-06-02T00:00:00Z
---

## Current Test

[awaiting human testing — requires a live OpenAI-compatible endpoint]

## Tests

### 1. Live-LLM pronoun consistency end-to-end
expected: Run `trezarr translate` on a real episode SRT against a live OpenAI-compatible endpoint (ideally a series episode with recurring characters, source in en/ja/ko). The same directed character pair (e.g. John→Mary) consistently receives the same Vietnamese pronoun pair (e.g. `anh`/`em`) across all dialogue lines throughout the episode — no intimate-pronoun flip between scenes; the Address Map DB row is visible. (Automated `test_pronoun_consistency_within_episode` proves the hint-injection plumbing with a mock; only a live model confirms it actually follows the pronoun-pair instruction in Vietnamese output.)
result: [pending]

### 2. Independent toggle: `enable_pass1_analysis=False` with `enable_attribution=True`
expected: Set `TREZARR_ENABLE_PASS1_ANALYSIS=false` while keeping `enable_attribution=True`; run a translate job with `eligible_item` + `session_factory` supplied. Pass 1 is skipped (empty `BibleAnalysis`, no analysis LLM call), but Pass 2 `attribute_batch` and `reconcile_attributions` still run, and translation completes `status="done"` (WR-02 fix — the engine gate no longer checks `enable_pass1_analysis`).
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
