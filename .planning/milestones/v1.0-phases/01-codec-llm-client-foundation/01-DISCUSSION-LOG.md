# Phase 1: Codec & LLM Client Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 1-Codec & LLM Client Foundation
**Areas discussed:** Endpoint capabilities, Concurrency & rate limits, SRT fidelity policy, Config surface (all delegated to Claude)

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Endpoint capabilities | What the OpenAI-compatible endpoint supports (json_schema strict / JSON mode / model / context window) | (delegated) |
| Concurrency & rate limits | Parallel-call cap / RPM defaults for the user's endpoint | (delegated) |
| SRT fidelity policy | Verbatim vs normalize; inline-tag handling for messy real-world SRT | (delegated) |
| Config surface | env vars / .env / YAML config file | (delegated) |

**User's choice:** "you decide all" — all four areas delegated to Claude's discretion.
**Notes:** User opted not to discuss specifics and delegated all implementation decisions. Decisions were made as research-grounded defaults and recorded in CONTEXT.md (D-01 … D-11), with the byte-identical SRT round-trip (pysubs2 validation) explicitly flagged as the riskiest assumption for the researcher.

---

## Claude's Discretion

All four gray areas were delegated. Key decisions made on the user's behalf:
- Endpoint capability handling → auto-detect with progressive degradation (`structured_output_mode: auto` default).
- Concurrency → `asyncio.Semaphore` default cap 4, configurable; rely on SDK retries (no stacked tenacity).
- SRT fidelity → byte-identical verbatim contract; inline tags kept in cue text; malformed cues preserved-and-flagged.
- Config → `pydantic-settings`, layered `config.yaml` + env overrides; secrets never logged.

Language/stack carried forward from research (Python 3.12, pysubs2, OpenAI SDK v2) — surfaced for veto, not rejected.

## Deferred Ideas

None — discussion stayed within phase scope.
