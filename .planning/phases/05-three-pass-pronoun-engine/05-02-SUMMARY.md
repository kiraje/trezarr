---
phase: 05-three-pass-pronoun-engine
plan: 02
subsystem: bible-store
tags: [orm, dto, store, address-map, config, bible-03, eng-04]
dependency_graph:
  requires: [05-01]
  provides: [AddressMapDTO, upsert_address_pair, load_address_map, load_series_bible-address_map, Phase5Settings]
  affects: [trezarr/bible/models.py, trezarr/bible/dto.py, trezarr/bible/store.py, trezarr/config.py]
tech_stack:
  added: []
  patterns: [selectinload-relationship, upsert-in-session-helper, D-32-transaction-ownership, D-34-lock-precedence]
key_files:
  created: []
  modified:
    - trezarr/bible/models.py
    - trezarr/bible/dto.py
    - trezarr/bible/store.py
    - trezarr/config.py
    - tests/bible/test_address_map.py
decisions:
  - "upsert_address_pair is self-contained (not routed through merge_inferred) per Pitfall G / PATTERNS.md — merge_inferred's isinstance chain only handles CharacterDTO/TermDTO/SeriesDTO"
  - "locked_fields check reads directly from SQLA row (not DTO) inside the transaction, matching WR-01 / HIGH finding pattern from _upsert_character_in_session"
  - "pronoun_safe_default uses Field(default=None) — not default_factory — because None is immutable and matches PATTERNS.md note on mutable default convention"
metrics:
  duration: "4 minutes"
  completed: "2026-06-01"
  tasks: 2
  files: 5
---

# Phase 5 Plan 02: Address Map Store Foundation Summary

**One-liner:** ORM relationship + AddressMapDTO + upsert_address_pair with D-34 lock precedence + Phase-5 TrezarrSettings fields.

## What Was Built

### Task 1: ORM relationship + DTO extension (models.py + dto.py)

Added `Series.address_maps` ORM relationship and `AddressMap.series` back-reference to `trezarr/bible/models.py`. No Alembic migration needed — the `address_map` table and FK already exist from the Phase-4 baseline migration (D-31). Only ORM relationship metadata was added.

Added `AddressMapDTO` class to `trezarr/bible/dto.py` following the exact `CharacterDTO` pattern (`ConfigDict(from_attributes=True)`, docstring format, field order matching ORM model columns 1:1). Extended `SeriesBibleDTO` with `address_map: list[AddressMapDTO] = []` field placed after `terms`.

### Task 2: Address Map store functions + Phase-5 config fields (store.py + config.py)

Extended `trezarr/bible/store.py`:
- `MERGEABLE_FIELDS["address_map"] = frozenset({"self_term", "address_term", "valid_from_episode"})`
- `AddressMap` and `AddressMapDTO` added to model/DTO imports
- `_upsert_address_pair_in_session`: self-contained private helper (NOT routed through `merge_inferred` per Pitfall G). Identity key is `(series_id, speaker_character_id, addressee_character_id)`. On INSERT: constructs `AddressMap` row with `locked_fields=[]` (WR-05), flushes, emits one `BibleEvent` per non-None field. On UPDATE: iterates mergeable fields, skips locked fields (D-34), skips no-op values, writes `BibleEvent` for each genuine change. Reads `locked_fields` from SQLA row (not from DTO — WR-01 / HIGH finding pattern).
- `upsert_address_pair`: public async wrapper owning the transaction (`async with session_factory() as session: async with session.begin():`), returns `(AddressMapDTO, list[BibleEventDTO])` via `model_validate`.
- `load_address_map`: SELECT all `AddressMap` rows WHERE `series_id == series_id`, returns `list[AddressMapDTO]`.
- `load_series_bible`: extended with `selectinload(Series.address_maps)` and `address_map=[AddressMapDTO.model_validate(a, from_attributes=True) for a in row.address_maps]` in the `SeriesBibleDTO` constructor.

Extended `trezarr/config.py` with Phase-5 `TrezarrSettings` fields block under `# ── Phase 5: Three-Pass Pronoun Engine (D-40…D-50) ──────────────────────────`:
- `enable_pass1_analysis: bool = True`
- `pass1_max_cues_per_chunk: int = 400`
- `enable_attribution: bool = True`
- `attribute_context_lines_k: int = 8`
- `attribute_max_cues_per_batch: int = 30`
- `pronoun_confidence_threshold: str = "medium"`
- `pronoun_safe_default: tuple[str, str] | None = Field(default=None)`

Replaced test stubs in `tests/bible/test_address_map.py` with real assertions:
- `test_upsert_address_pair`: creates series + character rows, calls `upsert_address_pair`, asserts `dto.self_term == "anh"`, `dto.address_term == "em"`, correct IDs, events emitted for new fields.
- `test_locked_pair_not_overwritten`: inserts row, manually sets `locked_fields=["self_term"]`, attempts overwrite, asserts original `self_term == "anh"` survives, no event emitted for locked field.

## Verification Results

```
uv run pytest tests/bible/test_address_map.py -v   → 2 PASSED (not xfail)
uv run pytest tests/bible/ tests/db/ -x -q        → 63 passed
uv run python -c "from trezarr.config import TrezarrSettings; s = TrezarrSettings(); print(s.pronoun_confidence_threshold, s.enable_pass1_analysis)"
  → medium True
```

## Deviations from Plan

None — plan executed exactly as written. The `_upsert_address_pair_in_session` implementation follows the prescribed pattern exactly, including the self-contained lock-precedence logic (not delegating to `_merge_inferred_in_session`).

## Known Stubs

None — all plan goals fully implemented. `address_map` table rows are now writable via `upsert_address_pair` and readable via `load_series_bible` and `load_address_map`. Test stubs replaced with real passing assertions.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes beyond those in the plan's threat model. T-05-02-01 (locked_fields bypass) and T-05-02-02 (SQL injection) are both mitigated as planned: lock check reads from SQLA row inside transaction; all writes use ORM parameterized queries.

## Self-Check: PASSED

Files confirmed present:
- trezarr/bible/models.py: `address_maps` relationship in Series + `series` back-ref in AddressMap
- trezarr/bible/dto.py: `class AddressMapDTO` + `address_map: list[AddressMapDTO] = []` in SeriesBibleDTO
- trezarr/bible/store.py: `async def upsert_address_pair` + `selectinload.*address_maps` + `pronoun_confidence_threshold` in config.py

Commits confirmed:
- 5c39be0: feat(05-02): add Series.address_maps ORM relationship + AddressMapDTO
- 0251ce7: feat(05-02): add upsert_address_pair store functions + Phase-5 config fields
