# Phase 6: Relationship Evolution + Self-Review - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 6-relationship-evolution-self-review
**Mode:** `--auto` (recommended defaults auto-selected; no interactive prompts)
**Areas discussed:** Transition detection, Active-pair evolution semantics, Drift guard / precedence, Self-review insertion & granularity, Correction protocol, Review failure semantics, Settings/toggles

---

## Transition detection source (D-51)

| Option | Description | Selected |
|--------|-------------|----------|
| Extend Pass-1 holistic analysis | `BibleAnalysis` gains `relationship_events`; reuses the one full-file call that already reads the carried-forward Bible | ✓ |
| Dedicated transition-detection pass | A separate LLM call just to find relationship shifts | |
| Deterministic address-pair diff | Compare this episode's address pairs to the prior Bible state, no LLM | |

**Auto-selected:** Extend Pass-1 holistic analysis (recommended default)
**Notes:** No extra LLM round-trip; the analyzer already has full-file + Bible context. The deterministic diff can't read narrative intent ("they fell in love" precedes any term change). Dedicated pass rejected on cost (out of v1 scope).

---

## Active-pair evolution semantics (D-53)

| Option | Description | Selected |
|--------|-------------|----------|
| Mutable-current row + `valid_from_episode` marker | The single current Address Map row is the active pair; a transition updates its terms and bumps `valid_from_episode` | ✓ |
| Multiple rows per pair, latest `valid_from` ≤ N wins | Keep a version history of rows and resolve by episode | |

**Auto-selected:** Mutable-current row (recommended default)
**Notes:** Matches Phase 4 D-32 (mutable current + append-only audit) and Phase 5 D-42/D-49 (`valid_from_episode` reserved for this). History lives in `bible_event` + `relationship_event`; no schema change. The UNIQUE identity on the Address Map already enforces one current row per ordered pair.

---

## Drift guard / reconciliation precedence (D-54)

| Option | Description | Selected |
|--------|-------------|----------|
| `lock > logged transition > carried-forward > new inference` | An established pair's pronouns change ONLY via a lock or a logged transition this episode | ✓ |
| Highest-confidence attribution always wins | Let each episode's inference set the pair freely | |

**Auto-selected:** Strict precedence with transition as the only change authorization (recommended default)
**Notes:** This is the structural realization of success criterion #1 ("intentional, not by silent drift"). Without an event, BIBLE-06 carry-forward keeps the prior pair.

---

## Self-review insertion & granularity (D-55, D-56)

| Option | Description | Selected |
|--------|-------------|----------|
| Pass 4 after Pass-3 assembly, before the gate; batched via `batch_subdoc` | Concurrent over batches through the single semaphore; compact Bible context per batch | ✓ |
| Whole-file single-call review | One holistic review call over the entire translated file | |

**Auto-selected:** Batched Pass 4, before `validate_subdoc` (recommended default)
**Notes:** Roadmap success #2 mandates "before the validation gate." Whole-file review rejected on token blow-up for long files; batching reuses the Pass-2/Pass-3 cue grouping. No new `asyncio.Semaphore` (Pitfall 1).

---

## Correction protocol (D-57, D-58)

| Option | Description | Selected |
|--------|-------------|----------|
| Numbered-line corrected output + sentinel reuse | Reviewer returns corrected Vietnamese per numbered line; unchanged lines pass through; 1:1 mapping preserved | ✓ |
| Structured diff / patch model | LLM returns a list of edits to apply | |

**Auto-selected:** Numbered-line corrected output (recommended default)
**Notes:** Reuses `parse_numbered_response` + `extract_sentinels`/`reinsert_sentinels`, preserving D-12/D-13. Scope limited to Bible adherence (pronouns, terms, register) — the reviewer is told NOT to paraphrase adherent lines, avoiding translation drift. No `response_model` (mirrors Pass 3, D-47).

---

## Review failure semantics (D-59)

| Option | Description | Selected |
|--------|-------------|----------|
| Best-effort: fall back to pre-review output on any failure | Review never quarantines; `validate_subdoc` stays sole arbiter | ✓ |
| Treat review failure as a quarantine trigger | A failed review blocks the file | |

**Auto-selected:** Best-effort, can only improve (recommended default)
**Notes:** Consistency is non-negotiable — a flaky/low-tier endpoint must not convert a passing translation into a quarantine (Pitfall 5). On `openai.APIError`, parse/sentinel failure, or Tier-3-only endpoints, keep the Pass-3 line.

---

## Settings / toggles (D-60)

| Option | Description | Selected |
|--------|-------------|----------|
| Phase-6 settings group with independent toggles | `enable_relationship_events`, `enable_self_review` + review batch/context knobs | ✓ |
| Single combined toggle | One flag for both capabilities | |

**Auto-selected:** Independent Phase-6 toggles (recommended default)
**Notes:** Mirrors the Phase-5 D-50 grouping; lets each capability be staged/tested independently.

---

## Claude's Discretion

- Module layout (new `trezarr/translate/review.py` vs folding Pass 4 into `engine.py`; `analyze.py` extension vs a `relationship.py` helper).
- Exact Pydantic shapes (`RelationshipEventInference`, `RelationshipEventDTO`, any `ReviewCorrection`).
- Whether a transition re-derives terms from attribution or trusts LLM-suggested terms (prefer suggested-then-fallback).
- Self-review prompt content and how much Bible context each batch carries; whether it reads a fresh Bible or the in-memory `resolved_map`.
- New setting names and numeric defaults; the relationship-event writer name and its `(series_id, character_a, character_b, episode_marker)` dedup key.
- Whether `load_series_bible` eager-loads relationship events or a sibling loader is added.

## Deferred Ideas

- Retroactive re-translation of earlier episodes on a later relationship change → out of scope (forward-only).
- Editable / lockable relationship events → Phase 8 (override valve).
- Relationship timeline + self-review corrections in the UI → Phase 7/8.
- Iterative / multi-round self-review → out of scope for v1.
- Confidence-flagging self-review corrections in UI (OBS-01) → v2.
- Source selection, ASS/SSA + VTT → Phases 9/10.
