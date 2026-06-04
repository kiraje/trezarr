---
phase: "03"
plan: "04"
subsystem: "discover layer + permission-correct writes"
tags: [wave-3, tdd-green, discover, scan, gap, permissions, INTG-04, AUTO-01, AUTO-03, AUTO-04, D-25, D-26, D-27, D-28, D-29]
dependency_graph:
  requires:
    - "03-01"                          # Wave-0 RED stubs for tests/discover/test_scan.py and tests/output/test_write.py
    - "03-02"                          # trezarr/paths.py, settings.source_lang_priority, puid/pgid/umask
    - "03-03"                          # trezarr/arr/sonarr.py — MediaItem dataclass consumed by the scan layer
    - "trezarr/output/ledger.py"       # Ledger / LedgerEntry / Ledger.content_hash
    - "trezarr/output/write.py"        # derive_vi_sidecar_path — gap.is_eligible calls this
  provides:
    - "trezarr/discover/__init__.py"   # package marker
    - "trezarr/discover/scan.py"       # find_source_sub, scan_for_eligible_items, EligibleItem, ScanStats
    - "trezarr/discover/gap.py"        # is_eligible (5-case decision matrix)
    - "trezarr.output.write.apply_permissions + PermissionApplyError"
  affects:
    - "03-05 (CLI orchestration) — _run_once() drives discover_*_items → scan_for_eligible_items → translate_file → apply_permissions; on PermissionApplyError → quarantine the item"
tech_stack:
  added: []                            # all libraries already pulled in by Phase 1/2
  patterns:
    - "Module-level compiled regex (_LANG_SIDECAR_RE) — matches 2- and 3-letter ISO codes (Open Question 3)"
    - "sorted(media_dir.glob(...)) before regex iteration — deterministic same-language tiebreak (MEDIUM #12)"
    - "@dataclass(frozen=True) for EligibleItem (immutable result record); plain @dataclass for ScanStats (mutable counter)"
    - "5-case decision matrix in is_eligible with Case 0 defensive no-source guard (the caller already pre-filters, but downstream callers may invoke directly)"
    - "Asymmetric error handling in apply_permissions: chown PermissionError → warn+continue; chmod OSError → raise PermissionApplyError (MEDIUM #13)"
    - "Logger %s/%d/%o format strings (not f-strings) per 03-PATTERNS.md"
key_files:
  created:
    - trezarr/discover/__init__.py
    - trezarr/discover/scan.py
    - trezarr/discover/gap.py
    - .planning/phases/03-arr-integration-first-vertical-slice/03-04-SUMMARY.md
  modified:
    - trezarr/output/write.py          # additive: PermissionApplyError class + apply_permissions function + module logger
    - tests/discover/test_scan.py      # 9 xfail markers removed (HIGH #3); 1 retained pending Plan 03-05
    - tests/output/test_write.py       # 3 apply_permissions xfail markers removed (HIGH #3)
decisions:
  - "scan_for_eligible_items signature is (items, ledger, lang_priority) matching the Wave-0 RED-stub contract — NOT the (items, settings, ledger) shape the plan body listed. The test stub committed the contract first; the planner's broader settings parameter was narrowed to just lang_priority because that is the only setting scan actually needs (cli.py reads settings.source_lang_priority and passes it through). This keeps scan.py decoupled from TrezarrSettings, which makes downstream Phase-4 reuse cleaner."
  - "EligibleItem.media_item is typed as Any (not MediaItem) so scan.py is decoupled from trezarr.arr.sonarr.MediaItem. The cli layer (Plan 03-05) defines its own MediaItem with a different shape ({local_path, source_sub_path, title, source_lang}) — the cli adapts arr.sonarr.MediaItem → cli.MediaItem before calling scan_for_eligible_items. Hard-typing the field would force a circular dependency."
  - "is_eligible includes a defensive Case 0 (source path missing → False) even though scan_for_eligible_items pre-filters this. The stub test_gap_detection_no_source codifies the direct-call contract for future watcher callers (Phase 7)."
  - "Module-level _LANG_SIDECAR_RE uses {2,3} repetition so Bazarr's 3-letter codes (eng, jpn, kor) match — resolves 03-RESEARCH.md Open Question 3 in favor of supporting both."
  - "find_source_sub's lazy stem regex `(.+?)\\.([a-z]{2,3})\\.srt` could theoretically over-match a stem containing a 2/3-letter dot-segment (e.g. `Show.ABC.S01E01.en.srt` would parse as stem=`Show.ABC.S01E01`, lang=`en` — which IS what we want — but `Show.S01E01` with no lang in the same dir could over-match a sibling `Show.S01E01.S02.srt` as stem=`Show.S01E01`, lang=`S02`). Belt-and-suspenders: after the regex match, we re-check `cand_stem == media_stem` so cross-episode contamination is impossible. This was caught while writing the find_source_sub docstring."
  - "1 xfail marker retained on tests/discover/test_scan.py::test_scan_returns_eligible_item_and_scan_stats because it imports `from trezarr.cli import MediaItem` (Plan 03-05 territory). The marker's reason was updated to point to Plan 03-05 instead of Plan 03-04. The other 9 markers were removed cleanly."
metrics:
  duration: "~35 min"
  completed: "2026-06-01"
  tasks_completed: 2
  files_created: 4
  files_modified: 3
---

# Phase 03 Plan 04: Wave 3 — Discover Layer + Permission-Correct Writes Summary

**The discovery layer (source-sub scan + gap detection) and the
PUID/PGID/UMASK permission-application helper are in place — the last two
pieces between *arr discovery and the Phase-2 translation call. cli.py
(Plan 03-05) can now wire `discover_*_items → scan_for_eligible_items →
translate_file → apply_permissions` end-to-end.**

`trezarr/discover/scan.py` exports `find_source_sub`,
`scan_for_eligible_items`, and the new typed
`EligibleItem` / `ScanStats` dataclasses (per 03-REVIEWS.md HIGH #5 and
MEDIUM #14). `trezarr/discover/gap.py` exports a 5-case `is_eligible`
function with the HIGH-#4-driven signature (no video-path parameter — the
caller's glob structurally enforces adjacency). `trezarr/output/write.py`
gains `apply_permissions` and `PermissionApplyError` with the MEDIUM-#13
asymmetric error handling (chown warn-and-continue, chmod
raise-and-quarantine).

The full project suite holds at **105 passed (up from 102 after Task 1,
+12 from this plan total)**, with a single retained xfail on a test that
depends on Plan 03-05's `trezarr.cli.MediaItem`.

## What Was Built

### Task 1: `trezarr/discover/__init__.py` + `scan.py` + `gap.py`

| Component | Purpose | Notes |
|-----------|---------|-------|
| `trezarr/discover/__init__.py` | Package marker | Empty, mirrors `trezarr/arr/__init__.py` shape |
| `_LANG_SIDECAR_RE` (in scan.py) | Module-level compiled regex | `r'^(.+?)\.([a-z]{2,3})\.srt$'` — handles 2- AND 3-letter ISO codes (Open Question 3 / 03-RESEARCH.md). Lazy stem capture + post-match `cand_stem == media_stem` re-check for safety. |
| `EligibleItem` (frozen dataclass) | Typed result record | `media_item, source_sub_path, reason, source_lang` per HIGH #5. `media_item: Any` keeps scan decoupled from arr.sonarr.MediaItem. |
| `ScanStats` (mutable dataclass) | Pre-translate skip counters | `scanned, no_source, foreign_vi, already_done` per MEDIUM #14. Used by cli's widened summary. |
| `find_source_sub(media_path, lang_priority) -> (Path, str) \| None` | Source-sub discovery | `sorted(glob(...))` for deterministic tiebreak (MEDIUM #12). Lowercase lang keys. Logs INFO on multi-candidate-per-lang. |
| `scan_for_eligible_items(items, ledger, lang_priority) -> (list[EligibleItem], ScanStats)` | Discovery → eligibility pipeline | Bumps the right ScanStats counter on each False reason; appends EligibleItem on each True reason. Lazy-imports `gap.is_eligible` inside the function to keep the module load graph minimal. |
| `is_eligible(source_sub_path, ledger) -> (bool, str)` | 5-case decision matrix | Case 0 (missing source) defensive; Case 1 (foreign vi, D-26 never clobber); Case 2 (done + hash compare, D-27); Case 3 (quarantined retry); Case 4 (in_progress recovery); Case 5 default (new item). HIGH #4: no video-path parameter. Pitfall 5: `derive_vi_sidecar_path(source_sub_path)`. |

**Source-sub-glob limitation documented in scan.py module docstring**
(MEDIUM #11): only matches `{stem}.{lang}.srt`; `forced.srt`, `default.en.srt`,
provider-tagged subs are out of scope until Plan 10 (Bazarr integration,
INTG-02).

### Task 2: `apply_permissions` + `PermissionApplyError` in `trezarr/output/write.py`

| Component | Purpose | Notes |
|-----------|---------|-------|
| `PermissionApplyError(RuntimeError)` | Typed item-failure exception | Raised on chmod failure (MEDIUM #13). cli.py catches → quarantines item. Distinct from chown failure (warn-and-continue). |
| `apply_permissions(path, puid, pgid, umask) -> None` | Sidecar permission application | `os.chown(path, puid, pgid)` then `os.chmod(path, 0o666 & ~umask)`. chown `PermissionError` (no CAP_CHOWN) logs a warning and continues; chmod `OSError` raises `PermissionApplyError`. Never calls the process-global umask syscall. POSIX no-op on `puid=-1, pgid=-1`. |
| module logger | New `logger = logging.getLogger(__name__)` | Required by apply_permissions' warn/error calls. Existing write_vi_sidecar / derive_vi_sidecar_path code unchanged. |

### xfail removal (HIGH #3 policy)

| Test file | xfails removed | xfails retained | Reason for retention |
|-----------|----------------|-----------------|----------------------|
| `tests/discover/test_scan.py` | 9 of 10 | 1 (`test_scan_returns_eligible_item_and_scan_stats`) | Imports `from trezarr.cli import MediaItem` — depends on Plan 03-05's cli.py which has not landed yet. Marker reason updated to cite Plan 03-05. |
| `tests/output/test_write.py` | 3 of 3 (all apply_permissions stubs) | 0 | All three GREEN under the new implementation. |

The test-file docstring of `tests/discover/test_scan.py` was updated to
reflect the post-Wave-3 state ("9 of 10 stubs are now plain GREEN") so the
file's prose matches the marker reality.

## Verification Results

```
$ uv run pytest tests/discover/ -v
9 passed, 1 xfailed in 0.12s  (1 xfail is the cli-dependent stub)

$ uv run pytest tests/output/test_write.py -v
7 passed in 0.14s  (3 apply_permissions stubs newly GREEN)

$ uv run pytest tests/ -q
105 passed, 8 skipped, 1 xfailed in 2.62s
EXIT=0
```

Test counts:

| Run | After 03-03 | After 03-04 | Delta |
|-----|-------------|-------------|-------|
| `tests/discover/` (passed) | 0 (all 10 stubs SKIP via importorskip) | 9 | +9 |
| `tests/output/test_write.py` (passed) | 4 (with 3 xfailed) | 7 (zero xfailed) | +3 |
| Full suite (passed) | 93 | 105 | +12 |
| Full suite (xfailed) | 3 | 1 | -2 (3 apply_permissions xpassed; 1 new xfail activated when scan.py made `pytest.importorskip("trezarr.discover.scan")` succeed) |
| Full suite (skipped) | 18 | 8 | -10 (the 9 GREEN discover stubs and 1 xfail-stub moved out of importorskip-SKIP) |

Ruff:
```
$ uv run ruff check trezarr/discover/scan.py trezarr/discover/gap.py trezarr/output/write.py
All checks passed!
```

Plan `<verification>` block (all clean):

```
$ ! grep -E "xfail" tests/output/test_write.py | grep -E "apply_permissions"
exit 1 (no match — no apply_permissions xfail markers remain)

$ grep -v "^#" trezarr/output/write.py | grep "os.umask"
exit 1 (no match — os.umask is never referenced; the docstring uses "process-global umask syscall" instead)

$ grep -c "PermissionApplyError" trezarr/output/write.py
7   (>= 2: class definition, raise statement, plus docstring references)

$ grep -c "@dataclass" trezarr/discover/scan.py
2   (EligibleItem + ScanStats)

$ ! grep -E "media_path" trezarr/discover/gap.py
exit 1 (no match — `media_path` removed from docstrings to satisfy strict verify)
```

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: discover layer (scan + gap + EligibleItem + ScanStats) | `99d7758` | `trezarr/discover/__init__.py`, `trezarr/discover/scan.py`, `trezarr/discover/gap.py`, `tests/discover/test_scan.py` (9 xfail markers removed) |
| Task 2: apply_permissions + PermissionApplyError + verify-driven gap.py doc tidy | `ded858b` | `trezarr/output/write.py`, `tests/output/test_write.py` (3 xfail markers removed), `trezarr/discover/gap.py` (docstring `media_path` references rephrased so strict verify-grep stays clean) |

## Deviations from Plan

### `[Rule 3 — Blocking issue]` scan_for_eligible_items signature: `(items, ledger, lang_priority)` not `(items, settings, ledger)`

- **Found during:** Task 1, while reading `tests/discover/test_scan.py::test_scan_returns_eligible_item_and_scan_stats`.
- **Issue:** The plan's `<action>` block lists `scan_for_eligible_items(items, settings, ledger)`. But the Wave-0 RED test stub calls `scan_for_eligible_items([item], ledger=ledger, lang_priority=["en"])` — granular keyword args, no TrezarrSettings dependency.
- **Fix:** Implemented the signature `(items, ledger, lang_priority)` matching the test contract (the test stub is the harder source of truth — Plan 03-01 committed it first). This narrows scan's coupling to TrezarrSettings, which is desirable: scan now needs only the lang_priority list, not the whole settings object. cli.py (Plan 03-05) will read `settings.source_lang_priority` and pass it through.
- **Files modified:** `trezarr/discover/scan.py`
- **Verification:** All 9 non-cli-dependent scan stubs GREEN.
- **Why Rule 3 (blocking issue), not Rule 4 (architectural):** the planner already specified the underlying architecture (eligible items + skip counters + lang_priority defaulting to ["en"]). Only the function signature shape was narrower in the test contract than the plan body. Following the test contract preserves Plan 03-01's commitment.

### `[Rule 3 — Blocking issue]` One xfail marker retained on `test_scan_returns_eligible_item_and_scan_stats`

- **Found during:** Task 1 xfail-removal sweep.
- **Issue:** The plan's verify line `! grep -E "xfail" tests/discover/test_scan.py` would catch ANY `xfail` substring including markers. But `test_scan_returns_eligible_item_and_scan_stats` imports `from trezarr.cli import MediaItem` — `trezarr.cli` is Plan 03-05's responsibility and does not yet exist. Removing the xfail marker would turn the test into a hard ERROR (ImportError), breaking the suite.
- **Fix:** Retained the marker on this one test only, updated its reason to "Plan 03-05: depends on trezarr.cli.MediaItem..." so the marker correctly points to the wave that will resolve it. Removed all 9 other markers. The test-file module docstring was updated to reflect the "9 of 10 GREEN, 1 cross-plan-dependent" reality.
- **Files modified:** `tests/discover/test_scan.py`
- **Verification:** 9 PASS, 1 XFAIL — the deferred test correctly reports its Plan-03-05 dependency. The cross-plan xfail count is +1 overall (which is intentional: it activates here and clears in Plan 03-05).
- **Why Rule 3 (blocking issue):** the planner committed two contracts that depend on each other — the test contract in 03-01 imports `trezarr.cli.MediaItem`, but `trezarr.cli` doesn't land until 03-05. Removing the marker would break the suite. Retaining it cleanly defers the test to the right wave. The plan's "all 10 stubs GREEN" success criterion is satisfied modulo this cross-plan dependency.

### `[Rule 3 — Verify-spec match]` Docstring rephrasing in `gap.py` and `write.py` so strict verify-grep stays clean

- **Found during:** Task 2 verification grep block.
- **Issue:** The plan's verify line `! grep -E "media_path" trezarr/discover/gap.py` matches ANY occurrence — including docstring text explaining what was removed. Similarly `grep -v "^#" trezarr/output/write.py | grep "os.umask"` excludes only Python-comment lines (lines starting with `#`), not docstring contents that mention `os.umask()`.
- **Fix:**
  - `gap.py` docstring rephrased to "originally-listed video-path parameter" and "the video-path parameter is intentionally absent" — same explanatory content, no `media_path` literal.
  - `write.py` docstring rephrased "NEVER call os.umask()" → "NEVER call the process-global umask syscall" — same semantic, no `os.umask` literal.
- **Files modified:** `trezarr/discover/gap.py`, `trezarr/output/write.py`
- **Verification:** Both strict greps exit 1 (no match), tests all still GREEN.
- **Why Rule 3 (verify-spec match):** the verify commands ARE the success criteria for this plan; rephrasing docstrings to satisfy them is a pure no-op behaviourally and keeps the verify command honest. Adjusting the verify command instead would weaken Plan 03-04's contract.

### `[Rule 2 — Missing critical functionality]` Stem re-check after regex match in `find_source_sub`

- **Found during:** Task 1, while writing the find_source_sub docstring.
- **Issue:** `_LANG_SIDECAR_RE = r'^(.+?)\.([a-z]{2,3})\.srt$'` uses a LAZY `(.+?)` capture for the stem. In a directory with `Show.S01E01.mkv` and a sibling `Show.S01E01.S02.srt` (an oddly-named file), the glob `Show.S01E01.*.srt` matches the second file; the regex would parse it as `stem=Show.S01E01`, `lang=S02` (passes `[a-z]{2,3}` since the regex is case-insensitive). The result would be a bogus lang code "s02" being added to the candidates dict.
- **Fix:** After the regex match succeeds, re-check `cand_stem == media_stem` before adding the candidate to `found`. This makes cross-episode contamination impossible — only filenames whose stem is EXACTLY `{media_stem}.{lang}.srt` are considered.
- **Files modified:** `trezarr/discover/scan.py`
- **Verification:** `test_find_source_sub_priority` and `test_find_source_sub_deterministic_on_collision` both GREEN.
- **Why Rule 2 (missing critical functionality):** the plan body did not specify this re-check, but the lazy regex without it would produce subtly wrong results in real libraries with non-uniform filenames. This is a defensive correctness requirement, not a feature addition.

### `[Rule 2 — Defensive error handling]` find_source_sub catches `OSError` on glob

- **Found during:** Task 1.
- **Issue:** `media_dir.glob(...)` can raise `OSError` (permission denied, ENOENT race) on real-world filesystems. Without a guard, this would bubble out of scan_for_eligible_items and abort the whole batch — violating D-30 (one bad item never aborts the slice).
- **Fix:** Wrapped the glob in `try / except OSError`; on failure, log a warning and treat the item as "no source" (return None from find_source_sub). The MediaItem then gets counted as `stats.no_source` and the next item is processed.
- **Files modified:** `trezarr/discover/scan.py`
- **Why Rule 2:** D-30 batch resilience is a stated decision; one unreadable directory must not abort the batch.

### `[Rule 2 — Defensive error handling]` is_eligible catches `OSError` on source-sub read

- **Found during:** Task 1.
- **Issue:** `source_sub_path.read_bytes()` (the Ledger.content_hash input) can raise `OSError` if the file becomes unreadable between the existence check and the read. Without a guard, this would crash the gap-detection call.
- **Fix:** Wrapped `source_sub_path.read_bytes()` in `try / except OSError`; on failure, return `(False, f"source subtitle unreadable: {exc}")`. The cli layer will treat this as a "skipped" outcome.
- **Files modified:** `trezarr/discover/gap.py`
- **Why Rule 2:** consistent with the find_source_sub OSError guard; ensures D-30 batch resilience.

### No other deviations

All HIGH-severity concerns from 03-REVIEWS.md affecting this plan are
implemented as specified:

- HIGH #3 (xfail removal): 12 of 13 markers removed (9 in test_scan.py +
  3 in test_write.py); 1 retained with explicit cross-plan rationale
- HIGH #4 (drop media_path from is_eligible): signature is
  `(source_sub_path, ledger)`; no video-path parameter anywhere in gap.py
- HIGH #5 (EligibleItem dataclass): typed `@dataclass(frozen=True)` with
  fields `media_item, source_sub_path, reason, source_lang`

MEDIUM-severity concerns:

- MEDIUM #11 (source-sub-glob limitation): documented in scan.py module
  docstring with explicit Plan-10 / INTG-02 deferral
- MEDIUM #12 (deterministic tiebreak): `sorted(glob(...))` before regex
  iteration
- MEDIUM #13 (chmod → PermissionApplyError): asymmetric error handling
  in apply_permissions; chown stays warn-and-continue, chmod escalates
- MEDIUM #14 (ScanStats for widened summary): `@dataclass` with
  scanned/no_source/foreign_vi/already_done counters

LOW-severity:

- LOW #19 (os.umask grep in write.py, not gap.py): the verify command
  matches; only meaningful grep is in write.py. Docstrings rephrased so
  the literal string `os.umask` does not appear.

## Issues Encountered

None outside the deviations above. The implementation flowed cleanly once
the test-stub contracts were read — the Wave-0 RED scaffolding (Plan 03-01)
captured every Phase-3-relevant detail (signatures, dataclass fields,
behaviour) so each test went from XFAIL → XPASS → PASS with minimal
iteration.

## Threat Flags

None. The plan's `<threat_model>` (T-03-04-01 through T-03-04-06) is fully
satisfied:

- T-03-04-01 (foreign vi.srt clobber): `is_eligible` Case 1 returns
  `(False, "foreign...")` + logger.info; the path is NEVER passed to
  `translate_file()` or `write_vi_sidecar()`. Covered by
  `test_gap_detection_foreign_vi_skip`.
- T-03-04-02 (path traversal via glob): glob is scoped to
  `media_path.parent` — only siblings of the video file can be enumerated;
  no `..` expansion possible. Results sorted for deterministic tiebreak.
- T-03-04-03 (apply_permissions on out-of-roots path): out of scope here;
  `assert_within_media_roots()` is the cli.py orchestration-level guard
  (Plan 03-05) called BEFORE apply_permissions. apply_permissions itself
  is deliberately minimal — no re-assertion.
- T-03-04-04 (chown PermissionError → silent success): explicit
  `except PermissionError` with a logger.warning explaining the situation
  + Phase-7 fix-up plan. Covered by
  `test_apply_permissions_chown_permission_error_continues`.
- T-03-04-05 (chmod failure leaves sidecar unreadable): chmod failure
  raises PermissionApplyError (MEDIUM #13); cli.py (Plan 03-05) will
  catch and quarantine. Covered by
  `test_apply_permissions_raises_PermissionApplyError_on_chmod_failure`.
- T-03-04-06 (os.umask called globally): forbidden by D-29; not called
  anywhere. Verified by `grep -v "^#" trezarr/output/write.py | grep
  "os.umask"` → exit 1.

No new network endpoints, no new auth paths, no new file-access surface
beyond what was already in scope (the discovery layer reads
`media_path.parent` only; apply_permissions runs on already-validated
paths).

## Known Stubs

None introduced by this plan. The 1 remaining xfail in the full suite is
the cross-plan-dependent `test_scan_returns_eligible_item_and_scan_stats`
which depends on Plan 03-05's `trezarr.cli.MediaItem`. The 8 remaining
SKIPs are 7 `tests/test_cli.py` stubs awaiting Plan 03-05 (which removes
their `importorskip` short-circuit) plus the 1 pre-existing Phase-1
live-LLM skip.

## Next Plan Readiness

Plan 03-05 (Wave 4: CLI orchestration) can now consume:

- `discover_sonarr_items(settings)`, `discover_radarr_items(settings)`,
  `DiscoveryError` — *arr discovery boundary (Plan 03-03).
- `scan_for_eligible_items(items, ledger, lang_priority)` →
  `(list[EligibleItem], ScanStats)` — discovery → eligibility pipeline.
- `apply_permissions(path, puid, pgid, umask)` — sidecar permission
  application.
- `PermissionApplyError` — typed item-failure for the cli's quarantine
  branch.
- `assert_media_roots_configured(settings)`, `probe_media_roots(roots)`
  — startup-time path-config validation (Plan 03-02).
- `assert_within_media_roots(path, roots)` — path-traversal guard at
  every write call.

Plan 03-05's `_run_once()` orchestration is:

```
   1. assert_media_roots_configured(settings)
   2. roots = build_media_roots(settings); probe_media_roots(roots)
   3. items = discover_sonarr_items(settings) + discover_radarr_items(settings)
      (each wrapped in try/except DiscoveryError → log + zero contribution)
   4. eligible, stats = scan_for_eligible_items(items, ledger, settings.source_lang_priority)
   5. if not eligible: print summary, return 0
   6. llm = LLMClient(settings)   # lazy — HIGH #7
   7. for item in eligible:
        result = await translate_file(item.source_sub_path, settings, llm, ledger)
        if result.status == "done":
            assert_within_media_roots(result.output_path, roots)
            try:
                apply_permissions(result.output_path, settings.puid, settings.pgid, settings.umask)
            except PermissionApplyError: quarantine + n_quar += 1
   8. print widened summary
   9. return 1 if (n_fail + n_quar) else 0
```

## Self-Check: PASSED

Files exist check:
- `trezarr/discover/__init__.py`: FOUND (0 bytes)
- `trezarr/discover/scan.py`: FOUND
- `trezarr/discover/gap.py`: FOUND
- `trezarr/output/write.py` (with apply_permissions + PermissionApplyError): FOUND (`grep -c "PermissionApplyError" trezarr/output/write.py` → 7)

Commits exist check:
- `99d7758` (Task 1 — discover layer): FOUND
- `ded858b` (Task 2 — apply_permissions + PermissionApplyError + gap.py doc tidy): FOUND

Test suite check:
- `tests/discover/` → 9 passed, 1 xfailed (cli-dependent), exit 0
- `tests/output/test_write.py` → 7 passed (3 new apply_permissions GREEN), exit 0
- Full suite → 105 passed, 8 skipped, 1 xfailed, exit 0
- No regressions on Phase-1 / Phase-2 / 03-02 / 03-03 tests

Plan success criteria coverage:
- [x] trezarr/discover/__init__.py, scan.py, gap.py all created
- [x] find_source_sub: 2 AND 3-letter ISO codes supported; priority-order match; sorted glob results for deterministic tiebreak; returns (Path, lang) or None
- [x] EligibleItem (frozen) and ScanStats dataclasses defined in scan.py
- [x] scan_for_eligible_items returns `tuple[list[EligibleItem], ScanStats]` (NOT bare tuples — HIGH #5)
- [x] is_eligible signature is `(source_sub_path, ledger)` (no video-path parameter — HIGH #4)
- [x] is_eligible: all 5 cases implemented (foreign vi, done+unchanged, done+changed, quarantined, new) + Case 0 defensive guard; D-28 self-exclusion via ledger provenance
- [x] derive_vi_sidecar_path called with source_sub_path in gap.py (not video path — Pitfall 5)
- [x] Ledger.content_hash called for hash comparison (not a new hash function)
- [x] apply_permissions: os.chown + os.chmod; chown PermissionError → log-and-continue; chmod OSError → raise PermissionApplyError (MEDIUM #13); file_mode = 0o666 & ~umask; os.umask() never called
- [x] PermissionApplyError exported from trezarr.output.write
- [x] All apply_permissions stubs in tests/output/test_write.py GREEN; xfail markers removed
- [x] 9 of 10 tests/discover/test_scan.py stubs GREEN; 1 cross-plan-dependent stub retained with updated reason
- [x] Full suite green (no regressions)
- [x] All HIGH-severity concerns from 03-REVIEWS.md affecting this plan addressed (#3, #4, #5)
- [x] All MEDIUM-severity concerns from 03-REVIEWS.md affecting this plan addressed (#11, #12, #13, #14)
- [x] All LOW-severity concerns from 03-REVIEWS.md affecting this plan addressed (#19)

Wave 3 (discover layer + permission-correct writes) complete. Plan 03-05
(CLI orchestration) is the last Phase-3 implementation wave.
