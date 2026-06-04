---
status: partial
phase: 06-relationship-evolution-self-review
source: [06-VERIFICATION.md]
started: 2026-06-02
updated: 2026-06-02
---

## Current Test

[awaiting human testing — requires a real series with a known relationship arc + a live OpenAI-compatible endpoint]

## Tests

### 1. Real-episode relationship shift produces a correct, intentional pronoun change
expected: Translate two episodes of a series with a known relationship arc (e.g. strangers→lovers). A `relationship_event` row is written at the transition episode; the active pronoun pair for that ordered character pair changes ONLY from the transition episode forward (the prior episode keeps the old pair); the change is auditable via `relationship_event` + `bible_event`. Specifically validates the post-review fix (commit a5c37c5): a logged transition now adopts THIS episode's attribution-confirmed terms via `_derive_transition_terms`' D-54 3-step order, rather than collapsing to the safe default. (BIBLE-07, success criteria #1 + #3)
result: [pending]

### 2. Self-review measurably improves Bible adherence on real output
expected: Translate one file with `enable_self_review=False`, then `True`; diff the outputs. With self-review on, Pass 4 only corrects genuine Bible violations (wrong pronoun pair vs the resolved Address Map, wrong Term-Dictionary rendering, wrong register) and does NOT paraphrase already-adherent lines (D-58). Confirm the reviewer prompt actually carries the pronoun pair (post-review fix commit cf320e6 — `dominant_pair` is now stamped). Confirm a flaky/low-tier endpoint never turns a passing translation into a quarantine (D-59 best-effort). (ENG-05, success criterion #2)
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
