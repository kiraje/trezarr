---
phase: 10-source-selection-per-series-overrides
reviewed: 2026-06-02T00:00:00Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - trezarr/arr/bazarr.py
  - trezarr/arr/sonarr.py
  - trezarr/arr/radarr.py
  - trezarr/source_selection/__init__.py
  - trezarr/source_selection/rank.py
  - trezarr/source_selection/resolve.py
  - trezarr/discover/gap.py
  - trezarr/discover/scan.py
  - trezarr/output/ledger_sqla.py
  - trezarr/output/ledger.py
  - trezarr/output/_ledger_protocol.py
  - trezarr/output/write.py
  - trezarr/bible/models.py
  - trezarr/bible/dto.py
  - trezarr/bible/store.py
  - trezarr/web/routes/bible.py
  - trezarr/llm/client.py
  - trezarr/translate/engine.py
  - trezarr/cli.py
  - trezarr/config.py
  - alembic/versions/0003_per_series_overrides.py
  - frontend/src/pages/BibleEditor.tsx
  - frontend/src/api/client.ts
findings:
  critical: 3
  warning: 6
  info: 2
  total: 11
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-02
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

Phase 10 adds source-language selection (Bazarr inventory, relational-richness ranking, per-series `source_lang_override`/`model_override`) and wires it end-to-end from discovery through the CLI into the Bible UI. The architecture is sound and most design decisions are correctly implemented. Three critical bugs were found: one in the filesystem source-discovery logic that causes `select_source_for_item` to only see one language regardless of what is on disk; one that allows the Bazarr API key to appear in error messages under a specific error path; and one in the `BibleEditor` term-save flow that silently discards the `category` update from the UI on partial state. Six warnings cover correctness/robustness gaps in the ranking algorithm, the D-26 foreign-vi check inside `translate_file`, the BibleEditor `saveTerm` race condition, and validation boundary conditions.

---

## Critical Issues

### CR-01: `select_source_for_item` filesystem fallback only discovers one language, making ranking useless

**File:** `trezarr/discover/scan.py:441`

**Issue:** `select_source_for_item` calls `find_source_sub(media_path, ["ko","ja","zh","th","en",...])` to populate `available_langs`. `find_source_sub` returns the **first match in priority order** — it returns a single `(path, lang)` tuple and stops. So `available_langs` is always a set of at most **one** language code from the filesystem, regardless of how many subtitle sidecars actually exist next to the media file. `rank_sources` then ranks a set of size ≤ 1, making the entire SRC-02 richness ranking over filesystem sources a no-op: the function always returns the single language that happened to appear first in the hard-coded probe list rather than the richest one present on disk.

For a K-drama with both `Show.S01E01.ko.srt` and `Show.S01E01.en.srt` on disk and no Bazarr inventory, the probe list places `ko` before `en`, so `ko` is returned — coincidentally correct in that case. But if the probe list order differs from the actual ranking for any content (e.g. a Thai drama where `th` and `en` exist but `zh` appears earlier in the probe list and only `en` is present), the filesystem path contributes only the wrong single language and ranking is still bypassed.

The fix is to scan for **all** languages present on disk by iterating the glob directly instead of calling `find_source_sub` with a priority list:

```python
# Replace the find_source_sub call at line 441 with a full scan:
if media_path is not None:
    try:
        candidates = sorted(media_path.parent.glob(
            f"{_glob.escape(media_path.stem)}.*.srt"
        ))
    except OSError:
        candidates = []
    for candidate in candidates:
        m = _LANG_SIDECAR_RE.match(candidate.name)
        if m and m.group(1) == media_path.stem:
            available_langs.add(m.group(2).lower())
```

**Fix:** Replace the single-result `find_source_sub` probe with a glob + regex scan that adds all discovered language codes to `available_langs`.

---

### CR-02: Bazarr API key leaks into error message when `httpx.RequestError` carries it as part of the URL

**File:** `trezarr/arr/bazarr.py:196-199`

**Issue:** The `except httpx.RequestError as exc:` handler formats the exception directly into the error message:

```python
raise BazarrError(
    f"Bazarr inventory fetch failed at {display_host}: "
    f"{type(exc).__name__}: {exc}"         # ← exc.__str__() can include URL + query params
) from exc
```

`httpx.RequestError.__str__()` may include the full request URL. While the API key is sent as a header (`X-API-KEY`) and not a query parameter, some `httpx` versions include the full URL in the request error string. More concretely: if the caller constructs `BazarrClient` directly (not via `from_settings`) and passes the API key in the `base_url` string (e.g. `http://user:APIKEY@bazarr:6767`), the URL will be embedded in the `httpx.RequestError` string and will appear in the `BazarrError` message even though `display_host` is safe. The same pattern applies to `fetch_episode_inventory` (line 315) and `fetch_movie_inventory` (line 349).

The fix is to format the exception type only, not the exception body, matching the pattern used in `sonarr.py` and `radarr.py` where the `DiscoveryError` message ends before the exception body:

```python
raise BazarrError(
    f"Bazarr inventory fetch failed at {display_host}: "
    f"{type(exc).__name__}"   # ← omit str(exc) to prevent URL leakage
) from exc
```

**Fix:** In all three `except httpx.RequestError` blocks in `bazarr.py` (lines 196-199, 237-240, 313-317, 347-351), change `{type(exc).__name__}: {exc}` to `{type(exc).__name__}` so the exception body never appears in the error string.

---

### CR-03: `saveTerm` in `BibleEditor.tsx` loses the `category` field update when `vietnamese_rendering` patch fails

**File:** `frontend/src/pages/BibleEditor.tsx:1493`

**Issue:** `saveTerm` sends `vietnamese_rendering` first, then — only if `editFields.category !== term.category` — sends a second PATCH for `category` (lines 1512-1543). The second PATCH uses a separate `fetch` call that is NOT wired through `fetchWithTimeout`. More critically, if the second PATCH call at line 1513 fails (non-`ok` response), the code falls through to the `setBible` update at line 1536 using the stale `updated` from the *first* PATCH, silently discarding the `category` change from the UI state. The user sees "Term saved." toast with no indication that `category` was not persisted, and the UI state reflects the old `category`.

Additionally, the second `fetch` call on line 1513 bypasses `fetchWithTimeout`, meaning it has no timeout and will hang indefinitely on network issues.

```tsx
// Current at line 1525 — resp2.ok check drops category silently on failure:
if (resp2.ok) {
  const updated2: TermDTO = await resp2.json();
  setBible(...)  // sets category from updated2
}
// No else — failure silently falls through to old state
```

**Fix:** (1) Use `fetchWithTimeout` for the second PATCH, (2) handle non-`ok` from the second PATCH with a toast and `throw` to reach the outer `catch`, and (3) ensure `setEditingId(null)` and the success toast are only called if both patches succeed:

```tsx
async function saveTerm(term: TermDTO, lock?: boolean) {
  setSaving(true);
  try {
    // ... first PATCH unchanged ...
    if (resp.ok) {
      const updated: TermDTO = await resp.json();
      // category PATCH — use fetchWithTimeout, throw on failure
      if (editFields.category !== (term.category ?? "")) {
        const resp2 = await fetchWithTimeout(`/api/series/${seriesId}/terms/${term.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ field: "category", value: editFields.category }),
        });
        if (!resp2.ok) throw new Error(`PATCH term category: ${resp2.status}`);
        const updated2: TermDTO = await resp2.json();
        setBible(prev => prev ? { ...prev, terms: prev.terms.map(t => t.id === term.id ? updated2 : t) } : prev);
      } else {
        setBible(prev => prev ? { ...prev, terms: prev.terms.map(t => t.id === term.id ? updated : t) } : prev);
      }
      setEditingId(null);
      showToast({ message: "Term saved.", variant: "success" });
    }
  } catch { ... }
}
```

---

## Warnings

### WR-01: `sort_key` native-Tier-3 bias produces wrong result for content with a Tier-3 original language that also has a Tier-1 fansub available

**File:** `trezarr/source_selection/rank.py:133-143`

**Issue:** Per the docstring and algorithm comment, the intent for `sort_key` when `lang == original_language` and `tier == 3` (e.g. en for a US show) is `return 0.0` so "native flat-relational wins over any fansub". This is correct for the case `available = ["en", "ko"]` for a US show (en gets 0.0, ko gets 1.0 → en wins).

However the algorithm fails for a show with `original_language = "en"` but no English subtitle available, and Korean available. In that scenario `rank_sources(["ko"], "en")` returns `["ko"]` (correct). But if a `ko` sub exists AND an `en` sub also exists, the Tier-1 korean (native non-English) gets `sort_key("ko", "en") = 1.0`, while English gets `0.0` — English wins, which is correct. This case is fine.

The actual bug is in the RESEARCH note's claim about "Tier-3 native" being the absolute top because of the `0.0` value. A Spanish drama (`original_language = "es"`) where `es` is unlisted in `_TIER` (defaults `_DEFAULT_TIER = 2`, Tier 2) would get `sort_key("es", "es") = 2 - 0.5 = 1.5`, while Korean gets `sort_key("ko", "es") = 1.0`. This means Korean beats the native Spanish — the opposite of what is intended for native-language bias.

The `_TIER` dict does not include `es`, `fr`, `de`, etc. as Tier-3 (they are missing entirely, defaulting to `_DEFAULT_TIER = 2`). So for content originally in Spanish (or any unregistered language), the native language is never given the Tier-3 `0.0` boost. `_DEFAULT_TIER = 2` means unlisted native languages get `2 - 0.5 = 1.5`, which is worse than a Korean fansub's `1.0`.

**Fix:** Either add all non-relational European languages as explicit Tier-3 entries, or change the native-bias formula to apply `return 0.0` whenever `lang == original_language` regardless of tier (not just for Tier-3). The simpler fix:

```python
if original_language and lang.lower() == original_language.lower():
    return 0.0  # native language always wins, regardless of tier
```

This correctly preserves the invariant "native source always preferred" without the tier-check complexity.

---

### WR-02: `translate_file` foreign-vi skip does not call `check_by_output_path` — Case 1.5 logic is bypassed for the engine's own idempotency path

**File:** `trezarr/translate/engine.py:655-657`

**Issue:** `translate_file` has its own inline D-20 ledger check for the foreign-vi skip at line 655:

```python
if entry is None and dest.exists():
    logger.info("foreign vi sidecar at %s, not ours — skipping %s", dest, path)
    return TranslationResult(status="skipped")
```

This check does **not** call `ledger.check_by_output_path(str(dest))`. The D-110 Case 1.5 logic (re-translate from a richer source when Trezarr owns the vi sidecar but wrote it from a different/lower-priority source path) was added to `gap.is_eligible` in `discover/gap.py`, but the parallel check inside `translate_file` was not updated to match.

Result: if `scan_for_eligible_items` correctly identifies a Case 1.5 richer-source eligible item and adds it to the eligible list (because `gap.is_eligible` fires Case 1.5 → `(True, "richer source...")`), `translate_file` is called with the richer source path. But `entry = await ledger.check(str(path))` uses the *new* richer source path as key, which is not in the ledger (`entry is None`). `dest.exists()` is True (Trezarr wrote it previously from the old source). The translate_file-level check at line 655 fires and returns `"skipped"` — overriding the Case 1.5 decision made by `gap.is_eligible`. The source upgrade never actually executes.

**Fix:** Mirror the `check_by_output_path` guard from `gap.is_eligible` into `translate_file`:

```python
if entry is None and dest.exists():
    prior_entry = await ledger.check_by_output_path(str(dest))
    if prior_entry is not None:
        # Trezarr owns this vi from a different source — proceed with upgrade (D-110)
        pass
    else:
        logger.info("foreign vi sidecar at %s, not ours — skipping %s", dest, path)
        return TranslationResult(status="skipped")
```

---

### WR-03: `process_one_item` fetches Bazarr inventory but never passes it to `translate_file` or `select_source_for_item`

**File:** `trezarr/cli.py:158-171`

**Issue:** `process_one_item` fetches Bazarr inventory into `_bazarr_inventory` (line 162) and then passes `source_sub_path` directly to `translate_file` (line 174). The `_bazarr_inventory` variable is never passed anywhere — it has no downstream consumer. `translate_file` does not accept a `bazarr_inventory` parameter and does not call `select_source_for_item`. The entire `select_source_for_item` function defined in `scan.py` is similarly never called from `process_one_item` or `_run_pipeline_steps`.

The result is that `source_sub_path` passed to `translate_file` is always the one selected by `find_source_sub` in `scan_for_eligible_items` using `settings.source_lang_priority` — the Bazarr inventory and per-series `source_lang_override` from `resolve_effective_settings` are computed but neither is used to actually select the source subtitle before calling `translate_file`. The per-series override (`_source_priority`) resolved at line 153 is also discarded — `translate_file` is called with `source_sub_path = eligible_item.source_sub_path` which was already chosen by `scan_for_eligible_items` using global `settings.source_lang_priority`.

This means the entire D-109 fallback chain (Bazarr inventory + richness ranking + per-series override) is computed but its output is thrown away. The source subtitle passed to `translate_file` is always the one the global scan chose.

**Fix:** Either (1) use `select_source_for_item` (or the resolved `_source_priority`) before calling `translate_file` to re-select the best source path and pass it as `path`, or (2) wire `_bazarr_inventory` and `_source_priority` into `translate_file`'s signature so it can apply per-series source selection internally. Option (1) is simpler:

```python
# After resolving series_dto and _bazarr_inventory, call select_source_for_item:
from trezarr.discover.scan import select_source_for_item  # lazy import
best_lang = select_source_for_item(
    media_item,
    settings,
    bazarr_inventory=_bazarr_inventory,
    per_series_source_override=_source_priority if _source_priority != settings.source_lang_priority else None,
)
# If best_lang differs from eligible_item.source_lang, find the corresponding path
# via find_source_sub([best_lang]) or from the Bazarr inventory.
```

---

### WR-04: `set_series_overrides` audit event records stale `old_value=None` instead of the actual prior values

**File:** `trezarr/bible/store.py:1725-1738`

**Issue:** The `BibleEvent` emitted by `set_series_overrides` hard-codes `old_value=None` (line 1732):

```python
evt = BibleEvent(
    ...
    field="overrides",
    old_value=None,      # ← always None, never the prior values
    new_value={
        "source_lang_override": src_override,
        "model_override": mdl_override,
    },
    source="import",
)
```

The function re-reads the row from the DB at line 1714 (`row = await session.get(Series, series_id)`), so the old values are available as `row.source_lang_override` and `row.model_override` BEFORE the assignment at lines 1722-1723. The audit trail records every override change as coming from `old_value=None`, making the history useless for rollback or diff display.

**Fix:**

```python
# Capture old values before mutation (line 1722):
old_src = row.source_lang_override
old_mdl = row.model_override

row.source_lang_override = src_override
row.model_override = mdl_override

evt = BibleEvent(
    ...
    old_value={"source_lang_override": old_src, "model_override": old_mdl},
    new_value={"source_lang_override": src_override, "model_override": mdl_override},
    ...
)
```

---

### WR-05: `BazarrClient.from_settings` hardcodes `http://` — HTTPS Bazarr deployments silently fail

**File:** `trezarr/arr/bazarr.py:151`

**Issue:**

```python
base_url = f"http://{host}:{settings.bazarr_port}"
```

The scheme is hardcoded as `http`. If a user configures Bazarr behind HTTPS (a common self-hosted setup with a reverse proxy), all Bazarr inventory requests will fail with a transport-level SSL error (the server redirects or enforces TLS). `sonarr.py` and `radarr.py` pass `tls=False` explicitly but those clients use `pyarr` which handles the scheme. `BazarrClient` uses raw `httpx` and builds the URL itself.

While CLAUDE.md notes HTTPS support is "Phase 7", the Bazarr client was introduced in Phase 10 with no TLS capability whatsoever. Users who have Bazarr behind a reverse proxy will receive cryptic `RequestError` failures from the Bazarr client with no hint that the scheme is wrong.

**Fix:** Respect a `bazarr_tls: bool = False` setting (already used for Sonarr/Radarr implicitly via `pyarr`'s `tls=False`), or at minimum check if `settings.bazarr_host` starts with `https://` before building the URL:

```python
scheme = "https" if str(settings.bazarr_host).startswith("https://") else "http"
base_url = f"{scheme}://{host}:{settings.bazarr_port}"
```

---

### WR-06: `OverridesSection` in `BibleEditor.tsx` duplicates the register field, creating two independent save paths for the same data

**File:** `frontend/src/pages/BibleEditor.tsx:2223-2395`

**Issue:** `OverridesSection` contains its own independent copy of the Register editor (`registerValue` state at line 2224, `handleSaveRegister` at line 2347, `toggleRegisterLock` at line 2369). The `RegisterSection` component (lines 1955-2078) already provides the same functionality. As a result:

1. When the user edits the register in the `Overrides` tab and saves it, `setBible` updates `prev.register` (line 2354). When they then switch to the `Register` tab, `RegisterSection` initialises its `registerValue` from `useState(bible.register ?? "")` at mount. Because React only runs `useState` once at mount, if the `Register` tab was already mounted, its state does not reflect the new value — the two tabs show different register values.

2. If `bible` is updated from a different source (e.g. after `patchSeriesOverrides` returns the updated DTO), neither register editor syncs automatically because both use `useState` initialised at mount.

3. The `Overrides` tab calls `patchRegister` (the correct endpoint), while the `Save Overrides` button calls `patchSeriesOverrides`. A user who edits the register in the Overrides tab and then clicks "Save Overrides" will save the override fields but NOT the register change in the same operation — they must remember to also click "Save Register" to persist it.

**Fix:** Remove the register sub-section from `OverridesSection` entirely. The `Register` tab is the canonical location. Alternatively, drive the register display in `OverridesSection` from `bible.register` as a read-only display with a link/button to the Register tab, rather than duplicating the editable state.

---

## Info

### IN-01: `_LANG_CODE_RE` in `write.py` only strips 2-letter codes — 3-letter language code suffixes in source paths produce wrong sidecar names

**File:** `trezarr/output/write.py:66`

**Issue:**

```python
_LANG_CODE_RE = re.compile(r'\.[a-z]{2}$', re.IGNORECASE)
```

Bazarr regularly emits 3-letter ISO-639-2 codes (e.g. `Show.S01E01.kor.srt`, `Show.S01E01.eng.srt`). `derive_vi_sidecar_path` checks the stem against `_LANG_CODE_RE` which only matches 2-letter codes. For `Show.S01E01.kor.srt`, `stem = "Show.S01E01.kor"`, `_LANG_CODE_RE.search(stem)` returns `None`, so the sidecar is named `Show.S01E01.kor.vi.srt` instead of `Show.S01E01.vi.srt`. The `.kor` token remains in the sidecar name, which is non-standard and may prevent media players from auto-detecting the Vietnamese sidecar.

**Fix:** Extend the regex to match 2- or 3-letter codes:

```python
_LANG_CODE_RE = re.compile(r'\.[a-z]{2,3}$', re.IGNORECASE)
```

---

### IN-02: `BibleEditor.tsx` Characters table rows use array-index key on the outer fragment, not `char.id`

**File:** `frontend/src/pages/BibleEditor.tsx:586`

**Issue:**

```tsx
{bible.characters.map((char, idx) => (
  <>            // ← key missing on fragment; React reconciliation uses index
    <tr key={char.id} ...>
```

The outer `<>...</>` fragment that wraps the `<tr>` and its possible history-panel expansion row has no `key` prop. Only the inner `<tr>` carries `char.id`. React assigns an implicit integer key to the fragment. When characters are reordered or a character is deleted from the middle of the list, React reconciles by index and may incorrectly persist input focus and local state (e.g. `editingId`, `historyOpenId`) on the wrong row. The same pattern appears in `AddressMapSection` (around line 1370) and `TermsSection` (around line 1800).

**Fix:** Use `React.Fragment` with an explicit key:

```tsx
{bible.characters.map((char) => (
  <React.Fragment key={char.id}>
    <tr ...>...</tr>
    {historyOpenId === char.id && <tr key={`${char.id}-history`}>...</tr>}
  </React.Fragment>
))}
```

---

_Reviewed: 2026-06-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
