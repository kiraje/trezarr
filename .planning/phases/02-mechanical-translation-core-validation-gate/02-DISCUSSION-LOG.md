# Phase 2: Mechanical Translation Core + Validation Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 2-Mechanical Translation Core + Validation Gate
**Areas discussed:** Inline tag handling, Gate-failure handling, Untranslated detection, Re-run / idempotency (all delegated to Claude)

---

## Gray-area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Inline tag handling | Strip+reinsert vs send tags to LLM | (delegated) |
| Gate-failure handling | Quarantine location + per-batch retry vs outright reject | (delegated) |
| Untranslated detection | Exact-match-to-source vs Vietnamese heuristic vs both | (delegated) |
| Re-run / idempotency | Skip vs overwrite vs content-hash guard | (delegated) |

**User's choice:** Free text — "you think then decide."
**Notes:** User delegated all four gray areas to Claude's discretion (mirrors the Phase 1 "you decide all" pattern). Decisions were made as research-grounded defaults corroborated against `.planning/research/PITFALLS.md`, and recorded in CONTEXT.md as D-12…D-20, all explicitly overridable in planning.

---

## Claude's Discretion

All decisions were made by Claude under explicit user delegation:
- **D-12** Placeholder-protect inline tags (never translate tags; sentinel round-trip is gated).
- **D-13** Guarantee 1:1 cue mapping by numbered structured output, reassembled by index.
- **D-14** Batch by token budget at safe (scene-gap) boundaries; never split a cue; tokenizer-agnostic estimate.
- **D-15** Read-only surrounding-line context window (K neighbors, not re-emitted).
- **D-16** Hard gate: cue count, no empty, no untranslated, byte-identical timing, monotonic timestamps, tag integrity, valid SRT/UTF-8.
- **D-17** Untranslated detection: per-line exact-match-to-source (with allowlist) + file-level Vietnamese-diacritic ratio; no heavy per-line langdetect.
- **D-18** Bounded per-batch retry (default 2) → whole-file reject; quarantine artifact under `/config`, never write on failure.
- **D-19** Atomic UTF-8 sidecar via temp + `os.replace()`; name = video basename + `.vi.srt`.
- **D-20** `/config` processed-files ledger (Phase-4 `processed_file`-compatible): skip if ours+unchanged, regenerate if source changed, never clobber a foreign `.vi.srt` (Bazarr-collision safety), retry quarantined files.

Planner/researcher retain latitude on module layout, exact thresholds/counts, token-estimation mechanism, sentinel format, and ledger storage format.

## Deferred Ideas

- Series Bible / pronoun + relationship consistency — Phases 4–5.
- Two-pass analyze→translate and LLM self-review — Phases 4 and 6.
- File-watcher / re-processing-loop prevention — Phase 3/7 (Phase 2 only lays the provenance ledger).
- Configurable "take over a foreign `.vi.srt`" override — likely Phase 7 (Web UI), unless trivially added.
