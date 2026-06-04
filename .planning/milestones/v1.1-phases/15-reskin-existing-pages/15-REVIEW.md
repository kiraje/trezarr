---
phase: 15-reskin-existing-pages
reviewed: 2026-06-04T00:00:00Z
depth: deep
files_reviewed: 14
files_reviewed_list:
  - frontend/src/pages/BibleEditor.tsx
  - frontend/src/components/LockBadge.tsx
  - frontend/src/components/LockToggleButton.tsx
  - frontend/src/components/FieldHistoryPanel.tsx
  - frontend/src/components/PronounCombo.tsx
  - frontend/src/components/ReciprocalSuggestionPanel.tsx
  - frontend/src/pages/History.tsx
  - frontend/src/pages/Queue.tsx
  - frontend/src/pages/JobLogs.tsx
  - frontend/src/pages/BibleList.tsx
  - frontend/src/pages/Settings.tsx
  - frontend/src/components/StatusBadge.tsx
  - frontend/src/components/RetryButton.tsx
  - frontend/src/components/ConnectionTestButton.tsx
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-06-04
**Depth:** deep
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 15 is a presentation-only reskin of 8 pages and 6 shared components onto shadcn primitives and CSS-variable tokens. The primary objective — proving BibleEditor behavioral preservation — is satisfied. All critical logic paths (lock-with-empty-term hard-block, provenance badge derivation, PronounCombo select/custom-mode logic, ReciprocalSuggestionPanel accept/dismiss callbacks, dirty-tracking, optimistic updates, useEffect/useMemo/useCallback dependency arrays) are unchanged.

The hex-color purge is complete: `grep -rnE "bg-\[#|text-\[#" frontend/src` returns zero matches (confirmed). The Sonner migration is correct: `Toast.tsx` is deleted, `<Toaster/>` is mounted once in `AppShell`, `toast.success/error` is wired in every site that previously used the bespoke `Toast` component. No dangling import of the old `Toast` component was found.

The two warnings below are pre-existing bugs surfaced by inspection during the reskin review — neither was introduced by Phase 15. They are flagged here because they are correctness defects that will affect users.

---

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: `handleConfirmReciprocal` fires a premature "Pair saved." toast and closes the edit row before the reverse-pair write completes

**File:** `frontend/src/pages/BibleEditor.tsx:869`

**Pre-existing:** Yes — present before 9b8aaa6. Phase 15 did not introduce or worsen it.

**Issue:** `handleConfirmReciprocal` calls `savePair(pair)` (line 869), which unconditionally calls `setEditingId(null)`, `setShowReciprocalForId(null)`, and `showToast({ message: "Pair saved.", variant: "success" })` on success. Control then returns to `handleConfirmReciprocal` which may still need to write the reverse pair (lines 878–921) or create it (lines 902–921). If that second write fails, the user sees a success toast followed immediately by an error toast — the UX implies the overall operation succeeded when the reverse pair was never updated. There is also a silent continuation: if `savePair` itself throws (its catch block shows an error toast but does not re-throw), `handleConfirmReciprocal` continues past line 869 and attempts the reverse-pair write even when the forward save failed.

**Fix:** Extract a private `savePairSilent` variant that does not fire the success toast or close the editing row. Use it from `handleConfirmReciprocal`, which can then fire a single composite toast after both writes resolve:

```typescript
// Private helper — no toast, no editingId reset
async function savePairCore(pair: AddressMapDTO, lock?: boolean): Promise<AddressMapDTO> {
  const updated = await patchAddressMapPair(seriesId, pair.id, {
    self_term: editFields.selfTerm,
    address_term: editFields.addressTerm,
    ...(lock !== undefined ? { lock } : {}),
  });
  setBible((prev) => {
    if (!prev) return prev;
    return { ...prev, address_map: prev.address_map.map((p) => p.id === pair.id ? updated : p) };
  });
  return updated;
}

async function handleConfirmReciprocal(pair: AddressMapDTO, rec: { self_term: string; address_term: string }) {
  setSaving(true);
  try {
    await savePairCore(pair);
    // ... reverse pair logic ...
    setEditingId(null);
    setShowReciprocalForId(null);
    showToast({ message: "Both pairs saved.", variant: "success" });
  } catch {
    showToast({ message: "Failed to save changes. Check the server logs.", variant: "error" });
  } finally {
    setSaving(false);
  }
}
```

---

### WR-02: `ConnectionTestButton` accepts a `resetKey` prop that is never consumed — result chip does not auto-clear on field edit

**File:** `frontend/src/components/ConnectionTestButton.tsx:20`

**Pre-existing:** Yes — present before Phase 15 reskin.

**Issue:** The component interface declares `resetKey?: string | number` (line 20), and the JSDoc comment at line 19 says "Reset key — changes when form fields change, clears the result chip." However, the component body never reads `resetKey` — it is destructured out and discarded (`svc, params` only appear in the function signature at line 23–26). The `Settings.tsx` callers do not pass `resetKey` either (they pass only `svc` and `params`). The result chip (ok/error state) therefore never clears automatically when form fields change, contrary to the spec contract.

**Fix:** Add a `useEffect` that resets status to `"idle"` when `resetKey` changes, and wire a composite `resetKey` from each Settings section:

```typescript
// In ConnectionTestButton:
useEffect(() => {
  setStatus("idle");
  setErrorMsg("");
}, [resetKey]);

// In Settings.tsx, pass resetKey per section, e.g.:
<ConnectionTestButton
  svc="sonarr"
  params={sonarrFields}
  resetKey={JSON.stringify(sonarrFields)}
/>
```

---

## Info

### IN-01: React Fragment wrapper in table maps lacks a key — React will emit console warnings in development

**File:** `frontend/src/pages/BibleEditor.tsx:538, 1125, 1709`

**Pre-existing:** Yes — identical pattern was present before 9b8aaa6.

**Issue:** In all three data-row table sections (characters, address_map, terms), `map()` returns a bare `<>...</>` Fragment whose `key` is placed on the inner `<tr>` instead of the Fragment. React requires the `key` on the outermost element returned from a map callback; placing it on a child silently suppresses the key and will produce "Each child in a list should have a unique key" warnings in the React DevTools console. The multiple sub-rows (history, hardblock strip, lockstrip, reciprocal) rely on these fragments — miskeyed fragments degrade reconciliation performance and can cause subtle reorder bugs when rows are added or deleted.

**Fix:** Replace bare fragments with keyed `<React.Fragment>`:

```tsx
// characters section (line 537):
{bible.characters.map((char) => (
  <React.Fragment key={char.id}>
    <tr className="h-10 border-b border-border">
      {/* ... no key needed here anymore ... */}
    </tr>
    {historyOpenId === char.id && (
      <tr>...</tr>
    )}
  </React.Fragment>
))}
```

Apply the same pattern to address_map (line 1106) and terms (line 1703).

---

### IN-02: `FieldHistoryPanel` accepts but never uses the `onClose` callback — no close affordance rendered

**File:** `frontend/src/components/FieldHistoryPanel.tsx:20`

**Pre-existing:** Yes — `onClose` was already unused before Phase 15.

**Issue:** The `onClose: () => void` prop is declared in the interface and accepted in every call site, but no close button or keyboard escape handler is rendered inside the component. Closing is entirely controlled externally (the caller toggles `historyOpenId`). This is functionally correct but creates a misleading interface: callers assume the panel manages its own close affordance, which it does not. The comment in the spec says "Not a modal — inline expansion below the triggering row," so external control is intentional, but the dead prop should either be removed or documented.

**Fix (preferred):** Remove `onClose` from the interface and all call sites. The Clock button in each row already toggles the panel externally; the prop adds no value. Alternatively, add a small "×" close button inside the panel body that calls `onClose()`.

---

_Reviewed: 2026-06-04_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
