# Phase 1: Codec & LLM Client Foundation - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers two **standalone, independently-testable** foundation components — no translation logic, no *arr integration, no Series Bible (those are later phases):

1. **Subtitle codec** — parses a real SRT file into an internal line model and serializes it back **byte-identical** (indices, timecodes, segmentation, encoding all preserved). Timecodes/indices are locally-owned data the LLM never touches; cue text is cleanly separable from timing.
2. **LLM client** — a thin wrapper over the user's OpenAI-SDK-compatible endpoint (configurable base URL / model / API key), with retries, a concurrency cap, and graceful degradation when the endpoint lacks strict structured-output support.

Requirements covered: **FMT-01** (SRT parse/write preserving timing+structure), **ENG-01** (user-provided OpenAI-compatible endpoint config).

In scope: SRT codec (lossless round-trip), internal line model, LLM client with config + retries + concurrency cap + structured-output fallback, the `pydantic-settings` config surface.
Out of scope: ASS/SSA + VTT (Phase 9), batching/chunking + actual translation (Phase 2), validation gate (Phase 2), *arr integration (Phase 3), Series Bible (Phase 4+), any web UI (Phase 7).

</domain>

<decisions>
## Implementation Decisions

All four discussed gray areas were delegated to Claude's discretion ("you decide all"). Decisions are research-grounded defaults; the user may override any in planning.

### Language / Stack (carried forward from research — flag if rejected)
- **D-01:** Python **3.12** is the project floor (pyarr 6.x requires it; pin in scaffolding). This is the whole-project language commitment.
- **D-02:** Subtitle codec built on **`pysubs2`** (one API for SRT now, ASS/VTT in Phase 9) — BUT see D-08: byte-identical round-trip is the hard contract and must be validated; wrap/replace pysubs2 if it normalizes output.
- **D-03:** LLM access via **OpenAI SDK v2** (`AsyncOpenAI`, `base_url`/`api_key`/`model` configurable).

### Endpoint Capabilities (ENG-01)
- **D-04:** **Auto-detect with progressive degradation** — no assumption about what the user's endpoint supports. Client attempts strict `response_format={json_schema, strict}` → on unsupported/4xx falls back to `json_object` (JSON mode) → falls back to a robust delimited-text protocol that is parsed and validated. A `structured_output_mode: auto|json_schema|json_object|text` setting (default `auto`) lets the user pin behavior.
- **D-05:** Model, base URL, API key, and **context-window size** are all config values (no hard-coded model). Context-window is configurable so Phase 2 batching can size chunks against it; default conservatively (e.g. 32k) until the user sets it.

### Concurrency & Rate Limits (ENG-01)
- **D-06:** Bound concurrent calls with an **`asyncio.Semaphore`**, default cap **4** (safe for self-hosted/single-GPU endpoints), configurable via `max_concurrency`.
- **D-07:** Use the **OpenAI SDK's built-in `max_retries` + exponential backoff**; respect `Retry-After`. **Do NOT** stack `tenacity`/custom retry on top of the SDK's retries (research-flagged double-retry bug). `request_timeout` and `max_retries` configurable.

### SRT Fidelity Policy (FMT-01)
- **D-08:** **Byte-identical round-trip is the contract.** Preserve original encoding, BOM, and line endings exactly. ⚠️ RESEARCH MUST VALIDATE that `pysubs2` round-trips SRT byte-identically on real files; if it normalizes timestamps/whitespace/formatting, the codec wraps it with a thin purpose-built SRT reader/writer that guarantees byte-identity. This is the riskiest assumption in the phase.
- **D-09:** Inline formatting tags (`<i>`, `<b>`, `<font ...>`, occasional `{\anX}`) stay **intact as part of the cue text** in Phase 1 — no tag-stripping or tag/text separation (that's a translation-phase concern). The internal model separates *timing from text*, not *tags from text*.
- **D-10:** Malformed/non-standard cues are **preserved-and-flagged**, never silently dropped — lenient parse, retain original content for faithful round-trip.

### Config Surface
- **D-11:** **Layered config via `pydantic-settings`** — a `config.yaml` (destined for the eventual Docker `/config` volume) with **environment-variable overrides** (12-factor, *arr convention). Validated settings model. Secrets (API key) supplied via env or config and **never logged**.

### Claude's Discretion
The user explicitly delegated all four gray areas ("you decide all"). Planner/researcher retain full latitude on: internal line-model shape, module/package layout, test structure, exact default values (concurrency cap, timeouts, context-window default), and the delimited-text fallback protocol format — provided the decisions above and the phase success criteria hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` §Subtitle Formats (FMT-01), §Translation Engine (ENG-01) — the two requirements this phase delivers
- `.planning/ROADMAP.md` §"Phase 1: Codec & LLM Client Foundation" — goal + 4 success criteria (byte-identical SRT round-trip; timing separable from text; configured endpoint produces a successful test call with retries + concurrency cap; graceful JSON-mode fallback)

### Research (stack & risk grounding)
- `.planning/research/STACK.md` — prescriptive stack: Python 3.12, `pysubs2` 1.8.x, OpenAI SDK v2 (`AsyncOpenAI`, `.parse()`, retry/semaphore patterns), `pydantic-settings`. **Read before choosing libraries/versions.**
- `.planning/research/PITFALLS.md` — structural/format failure modes (byte-identity, encoding/UTF-8 vs CP1258, double-retry anti-pattern); the validation-gate context (gate itself is Phase 2)
- `.planning/research/ARCHITECTURE.md` — codec-as-isolated-LLM-agnostic-module boundary; "API for knowledge, filesystem for action" (informs why codec & client are standalone)
- `.planning/research/SUMMARY.md` — overall synthesis and phase sequencing rationale

### Project context
- `.planning/PROJECT.md` §Constraints, §Key Decisions — user-provided OpenAI-compatible endpoint constraint; Dockerized-service constraint

No external ADRs/specs exist yet (greenfield, first phase) — requirements are fully captured in REQUIREMENTS.md + the decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

Greenfield project — no existing code, no codebase maps. Phase 1 scaffolds the repository.

### Reusable Assets
- None yet (this phase creates the first modules).

### Established Patterns
- None yet. Phase 1 *establishes* the foundational patterns (config via `pydantic-settings`, async LLM client, LLM-agnostic codec module boundary) that all later phases build on.

### Integration Points
- The codec and the LLM client are deliberately decoupled in Phase 1 (no integration between them yet). Phase 2 is the first consumer that wires codec → batching → LLM client → validation → write.

</code_context>

<specifics>
## Specific Ideas

- The codec's separation of **timing (LLM never touches) from text** is the spine of the project's correctness guarantee — every later phase relies on it. Treat timecodes/indices as immutable, locally-owned data.
- The LLM client's **graceful degradation** matters specifically because the user runs their *own* endpoint, whose structured-output support is unknown and may be a non-OpenAI proxy — the client must not assume OpenAI-exact behavior.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (The user delegated decisions rather than expanding scope.)

</deferred>

---

*Phase: 1-Codec & LLM Client Foundation*
*Context gathered: 2026-05-31*
