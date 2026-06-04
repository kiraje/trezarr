# Phase 10: Source Selection & Per-Series Overrides - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 10-source-selection-per-series-overrides
**Mode:** `--auto` — no interactive prompts; Claude auto-selected the recommended default for every gray area. Each selection below is the auto-picked default the planner/researcher may override with rationale.
**Areas discussed:** Bazarr inventory client, Bazarr-vs-filesystem authority, Relational-fidelity ranking, original_language signal, Graceful fallback chain, Per-series override storage, Override flow into pipeline, Per-series override UI

---

## Bazarr inventory client (INTG-02)

| Option | Description | Selected |
|--------|-------------|----------|
| httpx client mirroring `test_bazarr` | `trezarr/arr/bazarr.py` via httpx + X-Api-Key, typed `BazarrError` | ✓ |
| Add a pyarr Bazarr dependency | Use pyarr's Bazarr client | |

**Auto-selected:** httpx client (D-103).
**Notes:** Phase 7 already proved pyarr's Bazarr coverage is thin and reached Bazarr with raw httpx (`GET /api/system/status`). Reuse `_normalize_arr_host` + the `DiscoveryError`-style typed error.

---

## Bazarr-vs-filesystem authority (INTG-02 / SRC-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Bazarr authoritative, filesystem fallback + byte source | Bazarr tells what languages exist; filesystem reads bytes; degrade to glob when Bazarr off/down | ✓ |
| Replace filesystem scan entirely with Bazarr | Bazarr becomes a hard dependency | |
| Filesystem only, ignore Bazarr inventory | Keep Phase-3 behavior | |

**Auto-selected:** Bazarr authoritative + filesystem fallback (D-104, D-105).
**Notes:** Keeps SRC-01 working through a Bazarr outage; "never re-download" satisfied by reading inventory only. Path reconciliation via `apply_path_mapping` (D-23).

---

## Relational-fidelity ranking heuristic (SRC-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Static richness tier biased by original_language | zh/ko/ja/th > others > en, prefer original when rich; algorithm research-flagged | ✓ |
| Fixed language priority list only | Rank by a static list regardless of content | |
| Prefer-original-language only | Always pick the content's original language | |

**Auto-selected:** richness tier biased by original_language (D-107).
**Notes:** Avoids displacing a native English source with a fan foreign sub for English-original content. The exact weighting + language table is delegated to research (the novel heuristic STATE.md flagged).

---

## original_language signal source (SRC-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Capture *arr `originalLanguage` into snapshot | Add to MediaItem + Series.arr_metadata | ✓ |
| Infer from genre/country | Use genres already captured | |
| Infer from the available-sub set | Treat available langs as the signal | |

**Auto-selected:** capture `originalLanguage` (D-108).
**Notes:** Not captured today (confirmed in `arr/sonarr.py`). Genre/country are secondary; unknown original-language falls back to ranking over the available set.

---

## Graceful fallback chain (SRC-02 "whatever is available")

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit chain: override → ranking → global → first-available | Never skip if any source exists | ✓ |
| Skip when ideal source missing | Only translate the preferred language | |

**Auto-selected:** explicit fallback chain (D-109). Idempotency across source change handled by D-110.
**Notes:** Only "zero sources" stays no_source/skip. D-110 flags the "preferred source appeared later" transition as the top regression risk (preserve D-26/27/28).

---

## Per-series override storage (SVC-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Nullable columns on `series` + Alembic 0003; register override reuses Phase-8 lock | source_lang_override JSON, model_override str; register = locked field | ✓ |
| Separate `series_override` table | New table joined to series | |
| config.yaml series map | Keyed-by-series YAML section | |

**Auto-selected:** columns on `series` (D-111).
**Notes:** The per-series row is already the home; register override needs no new mechanism (BIBLE-08/09 lock already survives + propagates). YAML rejected (referential integrity, writer races).

---

## Override flow into the pipeline (model / register / source-pref)

| Option | Description | Selected |
|--------|-------------|----------|
| Single `resolve_effective_settings()`; model per-call; preserve D-06 | Pure resolution fn; thread model into each LLM request | ✓ |
| Per-series LLMClient instance | Build a client per series | |

**Auto-selected:** resolve_effective_settings + per-call model (D-112, D-113).
**Notes:** Preserves the single `LLMClient._semaphore` (D-06, Pitfall 1) — no second client, no second cap. Register already read in `build_translate_prompt`.

---

## Per-series override UI (SVC-05, UI hint: yes)

| Option | Description | Selected |
|--------|-------------|----------|
| Overrides section in the Phase-8 BibleEditor + `/api/bible/series/{id}/overrides` | Extend the existing per-series surface | ✓ |
| New top-level per-series settings page | Separate page | |

**Auto-selected:** extend BibleEditor (D-114).
**Notes:** BibleList → BibleEditor is already the per-series surface; register edit already lives in that router. Reuse api/client.ts, Toast, LockBadge; behind the D-39 Pydantic-only boundary.

---

## Claude's Discretion

- Exact Bazarr inventory endpoints/response shapes; per-item vs bulk-and-index fetch.
- The precise SRC-02 ranking algorithm + relational-richness language table + original_language bias strength (research-flagged).
- Whether selection extends `scan_for_eligible_items` or adds a `select_source` step; how chosen source_lang + override provenance reach `EligibleItem`/`job` for History.
- Override column names/types; the overrides DTO/route shape; model_override validation depth.
- Whether genre/country augment the original_language signal.
- Phase-10 settings defaults.

## Deferred Ideas

- Style-based sign/OP/ED skipping as a per-series toggle (carried from Phase 9 deferred).
- Manual per-series "re-translate all episodes" action (Phase 10 applies overrides forward-only).
- Per-series enable/disable, per-series concurrency, per-series glossary import (COMM-01 v2).
- Auto-detecting original_language from dialogue when *arr/TMDB lacks it.
- Multi-instance Sonarr/Radarr/Bazarr (SCALE-01); notifications / confidence-flagging (OBS-01/02) → v2.
