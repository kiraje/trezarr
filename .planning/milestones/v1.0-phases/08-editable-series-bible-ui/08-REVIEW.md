---
phase: 08-editable-series-bible-ui
reviewed: 2026-06-02T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - trezarr/bible/store.py
  - trezarr/translate/reconcile.py
  - trezarr/web/worker.py
  - trezarr/web/routes/bible.py
  - trezarr/web/app.py
  - tests/bible/test_human_edit.py
  - tests/web/test_bible_api.py
  - tests/translate/test_reconcile.py
  - frontend/src/api/client.ts
  - frontend/src/App.tsx
  - frontend/src/components/AppShell.tsx
  - frontend/src/components/LockBadge.tsx
  - frontend/src/components/LockToggleButton.tsx
  - frontend/src/components/FieldHistoryPanel.tsx
  - frontend/src/components/PronounCombo.tsx
  - frontend/src/components/ReciprocalSuggestionPanel.tsx
  - frontend/src/pages/BibleList.tsx
  - frontend/src/pages/BibleEditor.tsx
findings:
  critical: 5
  warning: 6
  info: 3
  total: 14
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-06-02
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 8 ships the human-override valve: the Bible editor UI + the `apply_human_edit_*` store writers that are the only production code that ever sets `locked_fields`. The domain correctness bar is very high — a silent lock-write failure means a user's human correction silently reverts on the next inference pass, violating the product's core promise.

The new `apply_human_edit_*` write path (`store.py`), the `bible.py` router, and the `reconcile.py` D-90 additions are largely correct. However, five blockers were found:

1. `apply_human_edit_term` silently loses the value set on a `new_row` path — the `setattr` call that would update the field is never reached when the row was just created (logic error in the new-row branch).
2. The `patch_term` route uses the URL path `term_id` parameter but passes `source_term` from the body — creating a mismatch where the route parameter is entirely unused; any term in the series can be patched from a single valid URL.
3. The `isHardBlocked` helper in `BibleEditor.tsx` reads `editFields.selfTerm`/`editFields.addressTerm` but compares them against the _current pair's locked state_, not the pair being actively edited — it can show a hard-block error for the wrong pair or silently allow an empty-term lock through.
4. `apply_human_edit_address_pair` allows unlocking (`lock=False`) but never removes `self_term`/`address_term` from `locked_fields`, so "Unlock" at the store level is a no-op; the D-87 invariant states both fields lock/unlock as a unit but the unlock path is not implemented.
5. The D-90 `KINSHIP_RECIPROCAL` stub test (`test_kinship_reciprocal_bac_chau`) is marked `@pytest.mark.xfail` but the implementation has already been shipped — the xfail annotation is wrong and masks that the test actually passes, hiding regressions if the entries are accidentally removed.

---

## Critical Issues

### CR-01: `apply_human_edit_term` new-row path never sets the field value

**File:** `trezarr/bible/store.py:1191-1211`
**Issue:** When `apply_human_edit_term` creates a new `TermDictionary` row (the `row is None` branch, lines 1191-1208), it correctly sets `vietnamese_rendering=vr` on the new row (line 1201). However, the subsequent `setattr(row, field, new_value)` call at line 1211 is in the `else` branch — it only executes when the row _already existed_. For the new-row path, `old_value` is set to `None` (line 1208) but the field value is never set on the row beyond the initial constructor (which only handles `vietnamese_rendering`). If the caller passes `field="category"` on a new row, the `field != "vietnamese_rendering"` check raises `ValueError` (correct). But if `field="vietnamese_rendering"` and `new_value` differs from `str(new_value)` after coercion, the stored value uses the coerced `vr = str(new_value)` while the audit event uses the raw `new_value` — an inconsistency, and the `lock` path that follows uses `new_value` not `vr` in the event. More critically, the `BibleEvent.new_value` (line 1229) uses `new_value` (the raw input) while the DB row stores `vr` (the str-coerced value). These can differ when `new_value` is not a string (e.g. integer). The audit log lies.

**Fix:**
```python
if row is None:
    if field == "vietnamese_rendering":
        vr = str(new_value)
    else:
        raise ValueError(...)
    row = TermDictionary(
        series_id=series_id,
        source_term=source_term,
        vietnamese_rendering=vr,
        locked_fields=[],
    )
    session.add(row)
    await session.flush()
    old_value = None
    new_value = vr  # normalize so the audit event matches what was stored
else:
    old_value = getattr(row, field)
    setattr(row, field, new_value)
```

---

### CR-02: `patch_term` route uses `term_id` URL param but calls `apply_human_edit_term` with `source_term` from body — `term_id` is ignored

**File:** `trezarr/web/routes/bible.py:249-289`
**Issue:** The route is `PATCH /api/series/{series_id}/terms/{term_id}`, but `apply_human_edit_term` is called with `source_term=source_term` (from the request body, line 281) — the `term_id` path parameter declared on line 249 is never used in the function body. Any caller can pass an arbitrary `source_term` in the body and target _any_ term in the series regardless of which `term_id` appears in the URL. This is both a security issue (unexpected cross-term writes) and a logic error: if the body's `source_term` does not correspond to `term_id`, the route silently operates on a different term than the one the URL indicates. The DELETE route correctly uses `term_id`, so this is an inconsistency.

This also means the frontend's `TermsSection.saveTerm()` — which calls `PATCH /api/series/{seriesId}/terms/${term.id}` with `source_term: term.source_term` in the body — happens to produce the right result only because the body's `source_term` matches the term being edited. But a malicious or buggy caller can inject a different `source_term`.

**Fix:** Rewrite `apply_human_edit_term` to look up by `term_id` (PK) rather than `source_term`, mirroring `apply_human_edit_character` which uses `character_id`. The `source_term` body field should be removed from the route contract.

```python
# store.py: replace the SELECT by source_term with session.get by id
row = await session.get(TermDictionary, term_id)
if row is None or row.series_id != series_id:
    raise ValueError(f"TermDictionary {term_id} not found in series {series_id}")
```

```python
# bible.py: remove source_term from the route signature
@router.patch("/series/{series_id}/terms/{term_id}")
async def patch_term(series_id: int, term_id: int, request: Request):
    ...
    dto, _evt = await apply_human_edit_term(
        session_factory,
        series_id=series_id,
        term_id=term_id,   # use PK
        field=field,
        new_value=body.get("value"),
        lock=body.get("lock", False),
    )
```

---

### CR-03: `apply_human_edit_address_pair` unlock path does not remove fields from `locked_fields`

**File:** `trezarr/bible/store.py:1128-1134`
**Issue:** The lock-toggle code at lines 1128-1134 handles `lock=True` (adds `self_term` and `address_term` to `locked_fields`) but has no `elif not lock` branch to remove them. The complete code is:

```python
if lock:
    locked_list = list(row.locked_fields or [])
    for f in ("self_term", "address_term"):
        if f not in locked_list:
            locked_list.append(f)
    row.locked_fields = locked_list
```

When `lock=False` (explicit unlock), the store function leaves `locked_fields` unchanged. The UI calls `savePair(pair, !isLocked)` — so toggling from locked to unlocked sends `lock=False` — but the store silently no-ops the unlock. After the round-trip, the pair remains locked in the database. The user sees a success toast, the UI optimistically updates, but on next page load the pair shows as still locked.

`apply_human_edit_character` and `apply_human_edit_series` both have the correct symmetric pattern (lines 1016-1018 and 1294-1297 respectively) — this omission is specific to the address-pair writer.

**Fix:**
```python
if lock:
    locked_list = list(row.locked_fields or [])
    for f in ("self_term", "address_term"):
        if f not in locked_list:
            locked_list.append(f)
    row.locked_fields = locked_list
elif not lock:  # explicit unlock
    locked_list = list(row.locked_fields or [])
    for f in ("self_term", "address_term"):
        if f in locked_list:
            locked_list.remove(f)
    row.locked_fields = locked_list
```

---

### CR-04: `isHardBlocked` helper in `BibleEditor.tsx` is evaluated against `editFields` from the currently-editing pair but the check is inside `bible.address_map.map()` — it reads stale edit state for non-editing rows

**File:** `frontend/src/pages/BibleEditor.tsx:847-855`
**Issue:** The `isHardBlocked` function (lines 847-855) is defined at the `AddressMapSection` component level and closes over `editFields`, which tracks the currently-edited pair's state. Inside `bible.address_map.map()` at line 1133, `hardBlocked = isEditing && isHardBlocked(pair)` is evaluated for every row in the table. For non-editing rows (`isEditing === false`), `hardBlocked` is correctly gated by `isEditing`. However the logic inside `isHardBlocked` itself checks whether the _pair_ has locked fields AND `editFields` has empty terms. Since `editFields` always belongs to the currently-editing pair, `isHardBlocked(pair)` for a non-editing pair with locked fields will evaluate `editFields.selfTerm.trim() === ""` — which is the _other_ pair's state, not this row's state. This can produce incorrect `hardBlocked=true` on non-editing rows when `editingId` is set.

The deeper consequence: when the user IS editing a locked pair, `isHardBlocked` is:
```js
isLocked && (editFields.selfTerm.trim() === "" || editFields.addressTerm.trim() === "")
```
This correctly blocks locking when an empty term is present. But it checks `pair.locked_fields` to determine `isLocked` — meaning even if the user is trying to _unlock_ a pair (by calling `savePair(pair, false)`), the `LockToggleButton` will be `disabled={hardBlocked}` and prevent the unlock if `editFields` happen to have an empty term. Unlocking should never be blocked by an empty-term check (D-87 only blocks locking, not unlocking).

**Fix:** The empty-term hard-block should apply only when the user is _locking_, not unlocking:
```tsx
const isHardBlocked = (pair: AddressMapDTO) => {
  // Only block if user is trying to lock (current state is unlocked → toggling to locked)
  const wouldLock = !pair.locked_fields.includes("self_term") && !pair.locked_fields.includes("address_term");
  return (
    wouldLock &&
    (editFields.selfTerm.trim() === "" || editFields.addressTerm.trim() === "")
  );
};
```

---

### CR-05: D-90 regression test `test_kinship_reciprocal_bac_chau` is marked `@pytest.mark.xfail` but the implementation is already shipped — stale xfail masks real regressions

**File:** `tests/translate/test_reconcile.py:1026-1034`
**Issue:** The test at lines 1026-1034 carries `@pytest.mark.xfail(raises=(AssertionError,), strict=False, reason="KINSHIP_RECIPROCAL bác/cháu gaps not yet filled — Plan 08-02 D-90")`. The D-90 additive fill is implemented in `reconcile.py:58-69`. With `strict=False`, if the test now _passes_, pytest will neither fail nor warn — it silently becomes an xpass and contributes no regression protection. With the entries present, the assertion `("bác", "cháu") in KINSHIP_RECIPROCAL` succeeds, making this a passing xfail. A future accidental deletion of those entries would revert to a failing xfail — also silent with `strict=False`. Effectively the test provides zero regression coverage in the shipped state.

**Fix:** Remove the `@pytest.mark.xfail` decorator since the implementation is complete:
```python
async def test_kinship_reciprocal_bac_chau():
    """D-90 H1 fix: bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày round-trip in KINSHIP_RECIPROCAL."""
    from trezarr.translate.reconcile import KINSHIP_RECIPROCAL
    assert ("bác", "cháu") in KINSHIP_RECIPROCAL and ("cháu", "bác") in KINSHIP_RECIPROCAL
    # Add all D-90 pairs:
    for pair in [("chú","cháu"),("cháu","chú"),("cô","cháu"),("cháu","cô"),
                 ("thầy","em"),("em","thầy"),("tao","mày"),("mày","tao")]:
        assert pair in KINSHIP_RECIPROCAL, f"Missing D-90 pair: {pair}"
```

---

## Warnings

### WR-01: `apply_human_edit_term` emits `BibleEvent(source="lock")` unconditionally — even when `lock=False`

**File:** `trezarr/bible/store.py:1222-1233`
**Issue:** All three scalar `apply_human_edit_*` functions (`character`, `term`, `series`) emit a `BibleEvent(source="lock", ...)` unconditionally in every call (lines 1021-1031, 1222-1233, 1299-1311). The `source="lock"` value is hardcoded regardless of whether `lock=True` or `lock=False`. A UI "Save without locking" action (value change, `lock=False`) produces an event with `source="lock"` in the audit log, which is misleading — it will appear in the field history panel labeled as a "lock" event when it was actually a plain edit. The context doc (D-32) specifies `source="lock"` for the lock path; an edit-without-lock should arguably use `source="import"` or a new `"human"` source. The existing `VALID_SOURCES` does not include `"human"`, but using `"lock"` for all human edits is a misuse of the audit trail.

**Fix:** Pass `source="lock" if lock else "import"` to `BibleEvent` (or add `"human"` to `VALID_SOURCES` and use it). The `apply_human_edit_address_pair` function (correctly named as a "human edit") at minimum should not emit `source="lock"` when `lock=False`.

---

### WR-02: `FieldHistoryPanel` receives an `onClose` prop that is never used internally — dead prop

**File:** `frontend/src/components/FieldHistoryPanel.tsx:49-54`
**Issue:** The `FieldHistoryPanel` component signature at line 49 declares `onClose: () => void` in `FieldHistoryPanelProps`. The component body never calls `onClose` — there is no close button and no keyboard handler. Every call site (`BibleEditor.tsx` lines 728-735, 1401-1408, 1900-1907, 2033-2040) passes an `onClose` callback that is silently ignored. The close functionality works by the _caller_ conditionally rendering the panel (`historyOpenId === pair.id`), so `onClose` is unnecessary. However, the presence of the unused prop is deceptive and may cause downstream contributors to assume the panel self-closes.

**Fix:** Remove `onClose` from `FieldHistoryPanelProps` and from all call sites.

---

### WR-03: `add_character` route in `bible.py` does not acquire the per-series lock before writing

**File:** `trezarr/web/routes/bible.py:120-139`
**Issue:** `add_address_pair` (line 197), `add_term` (line 295), and `patch_*` routes all acquire `get_series_lock(series_id)` before writing (D-81). But `add_character` (lines 120-139) calls `upsert_character` directly without acquiring the lock. If Pass-1 inference is mid-flight for the same series, an `add_character` call can interleave between two inference commits — at minimum it can insert a character row that a concurrent `_upsert_character_in_session` then detects as non-existent and re-inserts (the SELECT-before-INSERT safety in `_upsert_character_in_session` runs per-session, not cross-session). Given there is no DB UNIQUE constraint on character identity (verified C3 in context), this can produce duplicate character rows.

**Fix:**
```python
@router.post("/series/{series_id}/characters")
async def add_character(series_id: int, request: Request) -> JSONResponse:
    ...
    from trezarr.web.worker import get_series_lock
    async with get_series_lock(series_id):
        dto, _events = await upsert_character(...)
    return JSONResponse(dto.model_dump(by_alias=True))
```

---

### WR-04: `patch_series_register` route (`/api/series/{series_id}/register`) does not validate that `body.get("value")` is non-None before passing it to the store

**File:** `trezarr/web/routes/bible.py:345-371`
**Issue:** `apply_human_edit_series` is called with `new_value=body.get("value")` (line 365). If the request body omits the `"value"` key, `new_value=None` is passed to `setattr(row, "register", None)` — silently NULLing out the series register. The `patch_character` and `patch_term` routes have the same pattern but are less dangerous because character fields are nullable by design. For the register this is a data quality issue: a malformed PATCH request silently erases the register and emits a `BibleEvent(source="lock", new_value=None)` — if locked, that None propagates to all subsequent translations.

**Fix:**
```python
value = body.get("value")
if value is None:
    raise HTTPException(status_code=422, detail="'value' is required")
dto, _evt = await apply_human_edit_series(..., new_value=value, ...)
```

---

### WR-05: `BibleEditor.tsx` `CharactersSection.saveCharacter` sends individual `patchCharacter` calls in a loop without lock coordination — multiple in-flight requests per save

**File:** `frontend/src/pages/BibleEditor.tsx:310-343`
**Issue:** `saveCharacter` iterates over `editFields` and for each changed field makes a separate `await patchCharacter(...)` call (lines 315-322). This issues up to 3 sequential PATCH requests per save. Each PATCH acquires the per-series lock independently on the server (`get_series_lock`). Between the first and second request, another actor (inference pass or UI) could interleave and overwrite the partially-applied edit. The last `patchCharacter` result is used to update the local state (`updatedChar = result`), so only the last field's response (typically `role`) drives the optimistic UI update, potentially showing stale values for earlier fields. Additionally, if the second PATCH fails after the first succeeds, the local state reflects neither the original nor the intended final state.

**Fix:** The correct pattern is to send a single PATCH with all changed fields at once (backend already supports this since `apply_human_edit_character` takes one field per call — so the fix requires either batching at the API level or accepting the UX limitation and showing partial-save errors field by field). At minimum, if the backend must be called per-field, the UI should refresh the full character from the server after all patches complete rather than relying on the last partial response.

---

### WR-06: `KNOWN_PRONOUN_TERMS_SELF` is missing `"bố"` and `"mẹ"` which appear in `KINSHIP_RECIPROCAL` as self-reference terms

**File:** `trezarr/translate/reconcile.py:74-80`
**Issue:** `KNOWN_PRONOUN_TERMS_SELF` (lines 74-76) lists: `"tôi", "con", "em", "anh", "chị", "cháu", "mày", "tao", "bạn"`. But `KINSHIP_RECIPROCAL` includes `("bố", "con")` and `("mẹ", "con")` — where `"bố"` and `"mẹ"` are self-terms for the parent. If a user tries to set `self_term="bố"` or `self_term="mẹ"` for a parent→child pair using the `PronounCombo`, those terms are absent from the self-terms dropdown (the picker reads `KNOWN_PRONOUN_TERMS_SELF` via `/api/pronouns`). The user must use the "custom…" escape hatch, which defeats the D-86 typo guard for the most common parent pronouns. Similarly `"ông"`, `"bà"`, `"cha"` appear as self-terms in `KINSHIP_RECIPROCAL` but are absent from `KNOWN_PRONOUN_TERMS_SELF`.

**Fix:** Add the missing self-terms to `KNOWN_PRONOUN_TERMS_SELF`:
```python
KNOWN_PRONOUN_TERMS_SELF: list[str] = [
    "tôi", "con", "em", "anh", "chị", "cháu", "mày", "tao", "bạn",
    "bố", "mẹ", "cha", "ông", "bà", "bác", "chú", "cô", "thầy",
]
```

---

## Info

### IN-01: `reconcile_attributions` reciprocal-inference pass does not check whether an existing locked entry exists for the reverse pair before overwriting it

**File:** `trezarr/translate/reconcile.py:377-405`
**Issue:** The reciprocal coherence loop (lines 377-405) calls `upsert_address_pair(..., source="inference")` for inferred reverse pairs. `_upsert_address_pair_in_session` does respect `locked_fields` (lines 698-699) — so if the reverse pair is locked, the inference write is blocked at the field level. However, if the reverse pair has only `self_term` locked and `address_term` unlocked, the reciprocal inference will overwrite `address_term` even though the intent is coherence. This is an edge case but worth noting as a future refinement area.

---

### IN-02: `BibleEditor.tsx` `CharactersSection.toggleLock` uses `char.locked_fields.length > 0` as the lock-state indicator — coarse granularity

**File:** `frontend/src/pages/BibleEditor.tsx:345-379`
**Issue:** `toggleLock` determines the target lock state as `!isLocked` where `isLocked = char.locked_fields.length > 0` (line 346). It then sends `lock: lockState` for `gender`, `rough_age`, AND `role` unconditionally (lines 351-358). If a character has only `gender` locked (from a prior targeted lock), clicking "Unlock" sends `lock: false` for `gender`, `rough_age`, AND `role` — correctly unlocking `gender`. But clicking "Lock" on a character with mixed state sends `lock: true` for all three fields, which locks previously-unlocked fields the user never intended to lock. The UI treats lock state as a single per-character boolean rather than per-field, which doesn't match the DB model.

---

### IN-03: `FieldHistoryPanel.tsx` swallows the fetch error silently — no error state rendered

**File:** `frontend/src/components/FieldHistoryPanel.tsx:67-69`
**Issue:** The `catch` block in the `load` function (lines 67-69) sets `setLoading(false)` but leaves `events` as `[]`. The component renders "No history for this field." when events is empty — which is indistinguishable from a genuine network error. A user who sees "No history" may believe there are no events when the request actually failed. The other page-level error surfaces (e.g. `BibleList`, `BibleEditor`) use an `unreachable` state variable + banner.

---

_Reviewed: 2026-06-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
