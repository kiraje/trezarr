# Phase 5: Three-Pass Pronoun Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 5-three-pass-pronoun-engine
**Mode:** `--auto` (recommended defaults auto-selected; no interactive prompts)
**Areas discussed:** Pass architecture, Address Map population, Attribution output, Consistency enforcement, Low-confidence fallback, Pronoun application, Structured output strategy, Pipeline wiring

---

## Pass architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Three distinct passes (Analyze → Attribute → Translate) | Matches the phase title; lets reconciliation + low-confidence gates sit between inference and output | ✓ |
| Two passes (attribution folded into translation) | Fewer LLM calls; literal reading of the ROADMAP goal's "Pass 2" wording | |
| Two passes (attribution folded into Pass 1) | Pass 1 emits a per-line map for the whole file; large structured output | |

**Auto-selected:** Three distinct passes (D-40).
**Notes:** Honors the "Three-Pass" title and makes success criteria #3/#4 structural. Folding Pass 2 into Pass 3 documented as the fallback if call cost becomes a concern (cost is out of v1 scope).

---

## Address Map population

| Option | Description | Selected |
|--------|-------------|----------|
| Observed/exchanging ordered pairs only | Emit Address-Map rows only for pairs that actually exchange dialogue (+ carried-forward) | ✓ |
| Full N² enumeration | Enumerate every ordered character pair | |

**Auto-selected:** Observed pairs only (D-42).
**Notes:** Avoids N² blow-up; each pair grounded in real evidence. Reciprocal inferred from the Vietnamese kinship-pair table when only one direction is seen (unlocked, lower-confidence).

---

## Attribution output

| Option | Description | Selected |
|--------|-------------|----------|
| Batched per-cue `(speaker, addressee, confidence)` via Pydantic structured output | Reuses batch packing; wider context window for turn-taking | ✓ |
| Free-text attribution parsed heuristically | No structured contract | |

**Auto-selected:** Structured per-cue attribution (D-43).
**Notes:** `attribute_context_lines_k` larger than the translation context K; unmatched names degrade to the safe default, never crash the file.

---

## Consistency enforcement (success criterion #3)

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic per-episode reconciliation into the Address Map; Pass 3 looks it up | One pronoun pair per ordered pair; structural guarantee | ✓ |
| Rely on the LLM to stay consistent | Fragile, prompt-quality dependent | |

**Auto-selected:** Deterministic reconciliation (D-44).
**Notes:** The Address-Map row is the single source of truth the model is *told*, not *asked*.

---

## Low-confidence fallback (PRON-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable threshold → safe neutral/polite default pair | Never risk a wrong intimate pronoun | ✓ |
| Skip pronoun application, translate neutrally | Loses relational signal entirely | |
| Reuse most-recent confident pair in the exchange | Can propagate an error | |

**Auto-selected:** Safe neutral/polite default (D-45).
**Notes:** `pronoun_confidence_threshold` (~0.6) + `pronoun_safe_default`; v1 substitute for confidence-flag UI (OBS-01, v2).

---

## Pronoun application

| Option | Description | Selected |
|--------|-------------|----------|
| Per-line pronoun hints in the translation prompt | Model renders natural Vietnamese around the given terms | ✓ |
| Mechanical post-hoc pronoun replacement | Brittle; Vietnamese placement is context-sensitive | |

**Auto-selected:** Per-line pronoun hints (D-46).
**Notes:** Numbered-line 1:1 protocol, sentinels, and the document gate all preserved.

---

## Structured output strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Pydantic `response_model` for Pass 1 & 2; Pass 3 stays numbered-line text | Reuses the three-tier client; Tier-3-only endpoints degrade attribution to safe-default | ✓ |
| Hand-rolled JSON parsing for all passes | Reinvents the existing client fallback | |

**Auto-selected:** Pydantic for Pass 1 & 2, text for Pass 3 (D-47).

---

## Pipeline wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Extend `translate_file` to accept media_item + session_factory; lazy `get_or_create_series`; whole-Bible failure → quarantine | Bible-aware in one place; consistency > guessing | ✓ |
| New orchestrator wrapping `translate_file` | More indirection for an mvp slice | |

**Auto-selected:** Extend `translate_file` (D-48).
**Notes:** Sole concurrency gate stays in `LLMClient`; CLI passes the `eligible_item` + `session_factory` it already holds.

---

## Claude's Discretion

Module layout; exact Pydantic shapes (`BibleAnalysis` / `LineAttribution` / `AddressMapDTO`); confidence as float vs enum; pronoun-hint prompt syntax; the kinship-pair reciprocal table contents; Pass-1 chunking/merge of long files; reconciliation tie-break; movie episode-key string; Address-Map store API shape; default values for all new settings. (D-49, D-50 and the Claude's Discretion block in CONTEXT.md.)

## Deferred Ideas

- Relationship evolution across episodes → Phase 6 (BIBLE-07)
- LLM self-review pass → Phase 6 (ENG-05)
- Confidence-flag low-certainty lines in UI → v2 (OBS-01)
- Source-language selection / multi-source → Phase 10 (SRC-01/02)
- Bible editor UI + lock-setting → Phase 8 (BIBLE-08/09)
- `arr_metadata` refresh policy → Phase 10
- Folding Pass 2 into Pass 3 to cut calls → revisit only on cost pressure
