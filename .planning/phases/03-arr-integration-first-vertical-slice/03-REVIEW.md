---
phase: 03-arr-integration-first-vertical-slice
reviewed: 2026-06-01T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - trezarr/cli.py
  - trezarr/config.py
  - trezarr/paths.py
  - trezarr/arr/__init__.py
  - trezarr/arr/sonarr.py
  - trezarr/arr/radarr.py
  - trezarr/discover/__init__.py
  - trezarr/discover/scan.py
  - trezarr/discover/gap.py
  - trezarr/output/ledger.py
  - tests/arr/__init__.py
  - tests/arr/test_arr_discovery.py
  - tests/config/test_settings.py
  - tests/discover/__init__.py
  - tests/discover/test_scan.py
  - tests/output/test_write.py
  - tests/test_cli.py
  - tests/test_paths.py
findings:
  critical: 3
  warning: 8
  info: 6
  total: 17
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-01
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

The Phase-3 vertical slice is **structurally sound** — D-21 through D-30 are honoured, sequencing of `assert_media_roots_configured → build_media_roots → probe_media_roots → discover → scan → translate → permission-apply` is correct, SecretStr discipline is maintained (no API-key leakage in str/repr/model_dump), and the three documented deviations from the plan are largely defensible. Per-service `DiscoveryError` resilience, conditional LLMClient construction (HIGH #7), the chmod-quarantine escalation (MEDIUM #13), and the widened summary (MEDIUM #14) are all wired correctly.

However, this review surfaces **3 Critical bugs** that *will* misbehave in production with realistic *arr libraries:

1. **`apply_path_mapping` uses naked `str.startswith`** — a `/tv` prefix shadows `/tvshow` paths and produces a wrong-directory write target. This is a real *arr scenario (e.g. `/tv` + `/tvshow-anime` roots).
2. **`find_source_sub` calls `Path.glob` with the unescaped media stem** — any media filename containing glob meta-characters (`[`, `*`, `?`) — extremely common in TV show names like `Show [2024]` — silently matches nothing and the source sub is never found. Items will be reported as `no_source` and never translated.
3. **`Ledger._load` catches `(TypeError, KeyError)` but not `AttributeError`** — a malformed JSON value (e.g. a stray scalar or list at a key) raises `AttributeError: 'list' object has no attribute 'items'`, which escapes the per-entry try/except and aborts ledger load. The "never raises" Pitfall-4 contract is violated.

The remaining issues are quality/robustness: a Sonarr/Radarr discovery error log path that can echo embedded URL credentials, a tier-misalignment between `is_eligible` Case 0 and the `scan_stats` classifier (silently un-counted), the cli MediaItem / arr MediaItem fork (documented but still a real hazard), gaps in test coverage for is_eligible's `quarantined` and `in_progress` branches, and the Rule-2 / Rule-3 deviations being weaker than the SUMMARY claims.

Three documented deviations re-evaluated:
- **Rule-1 `if media_roots:` guard**: defensible. `assert_within_media_roots` does raise on empty roots (paths.py line 135 — the for-loop is skipped on `[]` and falls through to `raise ValueError(...)`), and `assert_media_roots_configured` already gates *arr-enabled runs upstream. Acceptable as belt-and-suspenders.
- **Rule-2 `all_arr_failed` exit-1**: defensible but redundant. With `enabled_arr > 0 and len(discovery_failures) == enabled_arr`, `all_items` is empty, `n_eligible` is 0, no loop body runs, `n_fail=0`, `n_quar=0`. Adding `all_arr_failed` to the disjunction is the only way the operator gets a non-zero exit. Correct, but the surrounding log at lines 202-207 says "fatal for the run" yet the code does **not** return early — it continues to print the same empty-summary line. See WR-04.
- **Rule-3 `[tool.uv] package=true` + hatchling**: defensible — without this, `uv sync` would not install the `[project.scripts]` entry. Verified manually. No defect.

## Critical Issues

### CR-01: `apply_path_mapping` uses `str.startswith` without a path-boundary check — `/tv` shadows `/tvshow`

**File:** `trezarr/paths.py:88-93`
**Issue:**
```python
for mapping in sorted_mappings:
    remote = mapping.remote.rstrip("/")
    if normalized.startswith(remote):
        suffix = normalized[len(remote):]
        local_root = mapping.local.rstrip("/")
        return Path(local_root + suffix)
```

`normalized.startswith(remote)` is true for `normalized="/tvshow/Foo/bar.mkv"` and `remote="/tv"`. The suffix becomes `"show/Foo/bar.mkv"` and the function returns `/data/media/tvshow/Foo/bar.mkv` (or whatever `local_root + "show/Foo/bar.mkv"` produces — could be `/data/tvshow/Foo/bar.mkv` if `local="/data/tv"`). This is wrong and can route real *arr paths to a non-existent directory or, worse, into the wrong root (a `/tv` mapping silently accepting a `/tvshow` path).

This is not theoretical — TRaSH-Guides setups regularly have neighbouring roots like `/tv` and `/tvshow-anime`, or `/data/movies` and `/data/movies-4k`. The "longest-prefix wins" sort does not fix this when only the *shorter* prefix is configured. D-23 explicitly mirrors *arr's "remote path mapping" convention, and *arr enforces path-boundary semantics.

The traversal guard `assert_within_media_roots` does **not** catch this because the mapped path is still inside the configured `local` root by accident of substring overlap.

**Fix:**
```python
for mapping in sorted_mappings:
    remote = mapping.remote.rstrip("/")
    # Path-boundary check: only match if normalized == remote, OR
    # normalized has remote as a true prefix terminated by "/".
    if normalized == remote or normalized.startswith(remote + "/"):
        suffix = normalized[len(remote):]
        local_root = mapping.local.rstrip("/")
        return Path(local_root + suffix)
```

Add a regression test in `tests/test_paths.py`:
```python
def test_path_mapping_prefix_is_path_boundary():
    mappings = [PathMapping(remote="/tv", local="/data/tv")]
    # /tvshow must NOT match /tv
    result = apply_path_mapping("/tvshow/Foo.mkv", mappings)
    assert str(result) == "/tvshow/Foo.mkv", (
        f"Expected passthrough (no path-boundary match), got {result}"
    )
```

---

### CR-02: `find_source_sub` glob fails for media stems containing glob meta-characters (`[`, `*`, `?`)

**File:** `trezarr/discover/scan.py:143`
**Issue:**
```python
candidates = sorted(media_dir.glob(f"{media_stem}.*.srt"))
```

`Path.glob` interprets `[`, `]`, `*`, `?` as glob meta-characters. Real *arr libraries routinely have filenames like:
- `Show [2024].S01E01.mkv` (square brackets — common Sonarr naming)
- `Movie (2019) [1080p].mkv`
- `Show.S01E01.[HDTV-720p].mkv`

For `media_stem = "Show [2024].S01E01"`, the glob pattern becomes `Show [2024].S01E01.*.srt`. The `[2024]` is interpreted as a character class matching one of the characters `2`, `0`, `2`, `4`. Result: the glob matches nothing (or matches the wrong filename), `find_source_sub` returns `None`, and `scan_for_eligible_items` bumps `stats.no_source` — the file is silently never translated.

This is a **silent correctness failure** — there is no warning, no log, no quarantine. The CLI summary will show `no_source=N` and the operator will think their `.en.srt` simply isn't where it should be.

**Fix:** Use `Path.glob` with an escaped stem, or use directory iteration + filename prefix-check:
```python
# Option A — escape glob meta-characters using glob.escape (stdlib):
import glob as _glob
escaped_stem = _glob.escape(media_stem)
candidates = sorted(media_dir.glob(f"{escaped_stem}.*.srt"))

# Option B — iterate and filter (more robust):
candidates = sorted(
    p for p in media_dir.iterdir()
    if p.is_file()
    and p.name.startswith(media_stem + ".")
    and p.name.endswith(".srt")
)
```

Add a regression test:
```python
def test_find_source_sub_stem_with_brackets(tmp_path):
    media = tmp_path / "Show [2024].S01E01.mkv"
    media.write_bytes(b"\x00")
    sub = tmp_path / "Show [2024].S01E01.en.srt"
    sub.write_text("en")
    result = find_source_sub(media, ["en"])
    assert result is not None, "find_source_sub must match stems with glob meta-chars"
    assert result[0] == sub
```

---

### CR-03: `Ledger._load` crashes on malformed JSON values (uncaught `AttributeError`)

**File:** `trezarr/output/ledger.py:114-119`
**Issue:**
```python
for k, v in raw.items():
    try:
        out[k] = LedgerEntry(**{kk: vv for kk, vv in v.items() if kk in valid_keys})
    except (TypeError, KeyError):
        logger.warning("Ledger entry %r is malformed — skipping that entry", k)
```

The handler catches `TypeError` and `KeyError` but not `AttributeError`. If the on-disk ledger has been tampered with, hand-edited, partially written from a Phase-4 schema migration, or otherwise has a non-dict at a key (e.g. a scalar `"done"`, a list `[...]`, `null`), then `v.items()` raises `AttributeError: 'NoneType' object has no attribute 'items'` (or similar). The error escapes `_load` and the entire `Ledger.__init__` aborts.

The module's stated contract (line 19 — "JSONDecodeError on load falls back to an empty ledger with a loud warning — never raises (Pitfall 4)") is violated by this gap. A single bad entry crashes the whole CLI, defeating the idempotency guarantee. The docstring at line 111 even claims "a single malformed/extended record only skips that entry rather than dropping the entire ledger" — which is exactly what this gap breaks.

A second adjacent issue: if the top-level `raw` itself is not a dict (e.g. a list `[...]`), then `raw.items()` at line 114 raises `AttributeError` outside any try/except. Same outcome — `Ledger.__init__` crashes.

**Fix:**
```python
def _load(self) -> dict[str, LedgerEntry]:
    if not self._path.exists():
        return {}
    try:
        raw = json.loads(self._path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        logger.warning("Ledger at %s is corrupt JSON — starting fresh", self._path)
        return {}

    if not isinstance(raw, dict):
        logger.warning(
            "Ledger at %s is not a JSON object (got %s) — starting fresh",
            self._path, type(raw).__name__,
        )
        return {}

    valid_keys = {f.name for f in dataclasses.fields(LedgerEntry)}
    out: dict[str, LedgerEntry] = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            logger.warning(
                "Ledger entry %r is not an object (got %s) — skipping",
                k, type(v).__name__,
            )
            continue
        try:
            out[k] = LedgerEntry(**{kk: vv for kk, vv in v.items() if kk in valid_keys})
        except (TypeError, KeyError, AttributeError):
            logger.warning("Ledger entry %r is malformed — skipping that entry", k)
    return out
```

Add a regression test (e.g. in `tests/output/test_ledger.py`):
```python
def test_ledger_load_with_non_object_top_level(tmp_path):
    p = tmp_path / "processed_files.json"
    p.write_text("[1, 2, 3]")  # legal JSON, wrong shape
    ledger = Ledger(p)  # must not raise
    assert ledger.check("anything") is None

def test_ledger_load_with_non_object_entry(tmp_path):
    p = tmp_path / "processed_files.json"
    p.write_text('{"a/b/c.srt": "broken-scalar"}')
    ledger = Ledger(p)  # must not raise
    assert ledger.check("a/b/c.srt") is None
```

---

## Warnings

### WR-01: Sonarr/Radarr error log can leak credentials embedded in `sonarr_host` / `radarr_host`

**File:** `trezarr/arr/sonarr.py:173-179` (and symmetrically `trezarr/arr/radarr.py:172-176`)
**Issue:**
```python
logger.error(
    "Sonarr discovery failed at %s:%d — %s: %s",
    settings.sonarr_host,           # <-- raw, unnormalized
    settings.sonarr_port,
    type(exc).__name__,
    exc,
)
raise DiscoveryError(
    f"Sonarr discovery failed at {settings.sonarr_host}:{settings.sonarr_port}: "
    ...
)
```

`_normalize_arr_host` exists specifically because users sometimes paste full URLs into the host field (`test_normalize_arr_host_full_url_with_scheme`). If a user pastes `http://admin:hunter2@sonarr.local:8989/api`, `_normalize_arr_host` strips it to `sonarr.local` — but the **error logger and DiscoveryError message both use `settings.sonarr_host` (raw)**. On the first 401/connect-refused, the embedded credentials are written to logs and into the cli.py summary's `partial-discovery-failures=[...]` suffix.

The SecretStr discipline for `sonarr_api_key`/`radarr_api_key` is correct, but the host field is a plain `str` and an attacker who reviews logs sees the credential in plaintext.

**Fix:** Normalize before logging:
```python
display_host = _normalize_arr_host(settings.sonarr_host)
logger.error(
    "Sonarr discovery failed at %s:%d — %s: %s",
    display_host, settings.sonarr_port, type(exc).__name__, exc,
)
raise DiscoveryError(
    f"Sonarr discovery failed at {display_host}:{settings.sonarr_port}: ..."
) from exc
```

Optionally promote `sonarr_host` to `SecretStr` if there's any concern users will paste credential-bearing URLs.

---

### WR-02: `_normalize_arr_host` does not strip a port from a bare `host:port` input

**File:** `trezarr/arr/__init__.py:52-58`
**Issue:**
```python
if "://" not in host:
    return host
parsed = urlparse(host)
return parsed.hostname or parsed.netloc.split(":")[0]
```

Input forms covered:
- `"192.168.1.10"` → `"192.168.1.10"` (bare IP — OK)
- `"http://192.168.1.10:8989"` → `"192.168.1.10"` (full URL — OK)
- `"sonarr.lan:8989"` → `"sonarr.lan:8989"` **wrong** — no scheme, so the early-return path returns it verbatim, port and all. pyarr's `Sonarr(host="sonarr.lan:8989", port=8989, tls=False)` will produce a malformed URL `http://sonarr.lan:8989:8989/api/v3/...`.

The docstring claims this shape is handled implicitly (`"sonarr.lan" → "sonarr.lan"`), but a user pasting `sonarr.lan:8989` (the most common Docker-compose convention) gets a broken client without any warning at startup.

**Fix:**
```python
def _normalize_arr_host(host: str) -> str:
    if "://" in host:
        parsed = urlparse(host)
        return parsed.hostname or parsed.netloc.split(":")[0]
    # Bare host, possibly with embedded port — strip any ":NNN" suffix.
    if ":" in host:
        return host.split(":")[0]
    return host
```

Add a test:
```python
def test_normalize_arr_host_bare_with_port():
    assert _normalize_arr_host("sonarr.lan:8989") == "sonarr.lan"
```

---

### WR-03: `is_eligible` Case 0 (`"no source subtitle at ..."`) is silently un-counted by scan_stats

**File:** `trezarr/discover/scan.py:251-262` and `trezarr/discover/gap.py:98-99`
**Issue:**
`gap.is_eligible` Case 0 returns `(False, f"no source subtitle at {source_sub_path}")` when the source file is missing on disk (e.g. TOCTOU between `find_source_sub` and `is_eligible`).

`scan_for_eligible_items` then classifies:
```python
if not ok:
    reason_lower = reason.lower()
    if "foreign" in reason_lower:
        stats.foreign_vi += 1
    elif "already translated" in reason_lower:
        stats.already_done += 1
    else:
        # Unrecognised non-eligible reason — log but do not crash.
        logger.info("scan skip for %s — unclassified reason: %s", ...)
    continue
```

`"no source subtitle at ..."` contains neither `"foreign"` nor `"already translated"`, so it falls into the `else` branch — logged at INFO and **not counted in any `ScanStats` field**. The summary line will show this as missing from all counters. The same problem applies to Case 0's second message `"source subtitle unreadable: ..."` (line 120 of gap.py).

In addition, the same `else` branch silently drops any future reason string drift (e.g. if Case 3/4 strings change). String-matching for control flow is fragile and the `not in any bucket` outcome silently hides items from the summary.

**Fix:** Return a typed reason enum from `is_eligible`, or at minimum add an explicit substring check for `"no source"` / `"unreadable"`:
```python
elif "no source" in reason_lower or "unreadable" in reason_lower:
    stats.no_source += 1
else:
    # ... unclassified
```

Better: refactor `is_eligible` to return `(bool, ReasonEnum, str)` so the classifier is type-safe.

---

### WR-04: `_run_once` logs "All enabled *arr services failed" as fatal but does not return — continues with scan+summary

**File:** `trezarr/cli.py:201-210`
**Issue:**
```python
enabled_arr = (1 if settings.sonarr_enabled else 0) + (1 if settings.radarr_enabled else 0)
if enabled_arr > 0 and len(discovery_failures) == enabled_arr:
    # All enabled *arr services failed → fatal for the run.
    logger.error(
        "All enabled *arr services failed discovery: %s",
        "; ".join(discovery_failures),
    )

n_discovered = len(all_items)
logger.info("Discovered %d total media items", n_discovered)
```

The comment says **"fatal for the run"**, but the code does **not** return or short-circuit. The function continues into `ledger = Ledger(...)`, `scan_for_eligible_items([], ...)`, and prints the same summary line. The only observable effect of `all_arr_failed` is the final exit-code disjunction at line 327. This produces a misleading message — the operator sees the loud error log followed by the standard "Run complete: discovered=0, eligible=0, ..." summary and may not realise the discovery total is zero because of failure, not because the library is empty.

The `partial-discovery-failures=[...]` suffix is appended only when `discovery_failures` is non-empty, but it does NOT visually distinguish "1 of 2 failed" from "2 of 2 failed".

**Fix:** Either (a) early-return after the fatal log with a distinct exit code, or (b) make the summary line carry an explicit `discovery_status=` flag:
```python
if enabled_arr > 0 and len(discovery_failures) == enabled_arr:
    logger.error(
        "All enabled *arr services failed discovery: %s",
        "; ".join(discovery_failures),
    )
    print(
        f"Run aborted: all_arr_failed=True, "
        f"discovery_failures=[{'; '.join(discovery_failures)}]"
    )
    return 1
```

Or update the summary line:
```python
all_arr_failed = enabled_arr > 0 and len(discovery_failures) == enabled_arr
status_str = "all_arr_failed" if all_arr_failed else "ok"
summary = f"Run complete (discovery_status={status_str}): ..."
```

---

### WR-05: `_run_once` broad `except Exception` swallows `asyncio.CancelledError` semantics indirectly

**File:** `trezarr/cli.py:300-306`
**Issue:**
```python
except Exception as exc:
    # D-30 batch resilience — one bad item never aborts the slice.
    logger.error("unhandled error translating %s: %s", source_sub_path, exc)
    n_fail += 1
```

In Python 3.12 `asyncio.CancelledError` is a subclass of `BaseException`, not `Exception`, so this catch is OK on that front. But the broad `except Exception` will also swallow:
- `SystemExit` propagated from a nested call (BaseException subclass — OK, not caught)
- `MemoryError` (Exception subclass — caught and merely logged, then loop continues — bad signal)
- `OSError` from disk-full when writing the quarantine artifact inside `translate_file` (caught — but the partial state of the ledger is now uncertain)

More importantly: `exc.__traceback__` is not logged. With only `logger.error("... %s: %s", path, exc)` the operator has no stack trace and no way to root-cause an unexpected failure mode. The "D-30 batch resilience" intent is correct, but failures should be loggable with full context.

**Fix:**
```python
except Exception as exc:
    logger.exception(
        "unhandled error translating %s",   # logger.exception adds traceback
        source_sub_path,
    )
    n_fail += 1
```

(`logger.exception` includes the traceback and exc-info automatically.)

---

### WR-06: `cli.MediaItem` and `arr.sonarr.MediaItem` are forked dataclasses with overlapping fields

**File:** `trezarr/cli.py:76-95` vs `trezarr/arr/sonarr.py:49-72`
**Issue:**
The codebase has two distinct dataclasses both named `MediaItem`:

- `cli.MediaItem`: `(local_path, source_sub_path, title, source_lang)` — the cli-layer DTO that test stubs construct directly.
- `arr.sonarr.MediaItem`: `(local_path, title, source_type, series_id, season_number)` — the discovery-layer dataclass returned by `discover_sonarr_items` / `discover_radarr_items`.

The cli's `_run_once` extends `all_items` with `arr.sonarr.MediaItem` instances (line 185, 194), then passes them to `scan_for_eligible_items` (line 214). The scan layer types `media_item: Any` (scan.py:70) precisely to avoid hard-coupling to either shape — but this also disables type-checking entirely along this seam.

The SUMMARY documents this as "intentional per Plan-03-01 test contract" and "a candidate cleanup but not a Phase-3 blocker." That is fair, but the actual cli flow **never constructs `cli.MediaItem`** — it only constructs `arr.sonarr.MediaItem` (via discover_*_items). `cli.MediaItem` exists *solely* for the test stubs in `tests/test_cli.py::_make_media_item`. The production code path never instantiates it. So the dataclass is essentially dead code in the production path.

This is a maintainability hazard: the next reviewer/contributor will see `cli.MediaItem` imported in `tests/discover/test_scan.py:314` and assume the cli flow uses it. The `source_sub_path` field on `cli.MediaItem` is never populated by `scan_for_eligible_items` (which writes to `EligibleItem.source_sub_path`, not back to the input).

**Fix:** Either (a) remove `cli.MediaItem` and update tests to instantiate `arr.sonarr.MediaItem` directly, or (b) move `cli.MediaItem` to a `tests/_factories.py` test-helper module to make it obvious it's not production code. The current placement (`trezarr.cli`) implies it's part of the production contract.

---

### WR-07: `test_cli.py` tests mock so much that they do not exercise the orchestration's actual call sites

**File:** `tests/test_cli.py:74-91, 110-127, 142-159, 184-198, 230-249, 275-295, 320-339`
**Issue:**
Every test in this file uses a `with` block that patches **all** of: `TrezarrSettings`, `discover_sonarr_items`, `discover_radarr_items`, `scan_for_eligible_items`, `translate_file`, `apply_permissions`, `probe_media_roots`, `assert_media_roots_configured`, `LLMClient`. The tests therefore prove only:

1. `_run_once` calls things in the right order (orchestration).
2. The exit code logic produces 0 vs 1 under controlled mocks.
3. The summary line contains the expected tokens.

None of the tests exercise:
- The `if media_roots:` traversal guard (Rule-1 deviation) — `probe_media_roots` is mocked, so `build_media_roots` is never tested in conjunction with `assert_within_media_roots`.
- Real path-mapping happening before scan.
- The `all_arr_failed` short-circuit through to exit code 1 when both *arr fail.
- The interaction between `result.status="done" + output_path=None` defensive branch (cli.py:238-244).

Specifically: the Rule-1 deviation's defense ("the guard is conditional purely as a belt-and-suspenders for tests that hand-craft eligible items without configuring media roots") is **not tested**. There is no test where `media_roots` is non-empty AND `result.output_path` is **outside** those roots — the path-traversal guard's positive-and-negative branches in cli.py:253-262 are uncovered.

Compounding this, `test_one_arr_failure_does_not_kill_other_arr` uses `MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=1)` for scan_stats, but the assertion only checks `exit_code == 0`. The summary line tokens, the `partial-discovery-failures` suffix presence, and the log error for sonarr failure are not asserted.

**Fix:** Add at least these test cases:
1. A test where `path_mappings=[PathMapping(remote="/tv", local=str(tmp_path / "media"))]` is real (no mock), the translated output_path is inside `tmp_path / "media"`, and `assert_within_media_roots` passes.
2. A test where the translated output_path is *outside* the configured media roots (e.g. via a mocked translate_file returning a path in `tmp_path`), and the cli logs the rejection + bumps `n_fail`.
3. A test where both `discover_sonarr_items` and `discover_radarr_items` raise `DiscoveryError`, both `sonarr_enabled=True` and `radarr_enabled=True`, and the exit code is 1 *and* the summary mentions `partial-discovery-failures=`.

---

### WR-08: Missing tests for `is_eligible` Case 3 (`quarantined` retry) and Case 4 (`in_progress` resume)

**File:** `tests/discover/test_scan.py` (entire file)
**Issue:**
`gap.is_eligible` documents 5 decision branches (Case 0-4) at lines 49-75. The tests cover:
- Case 0 (no source) — `test_gap_detection_no_source`
- Case 1 (foreign vi) — `test_gap_detection_foreign_vi_skip`
- Case 2 hash match — `test_idempotency_skip_unchanged`
- Case 2 hash mismatch — `test_idempotency_retranslate_on_change`
- Default (new item) — `test_gap_detection_eligible_new`, `test_foreign_vi` (the latter is mis-named — it actually tests the "our own output" / hash-match skip, NOT a foreign vi)

But there is **no test** for:
- Case 3: `entry.status == "quarantined"` → `(True, "retrying previously quarantined item")` — D-30 quarantine retry on re-run.
- Case 4: `entry.status == "in_progress"` → `(True, "resuming in-progress item (possibly crashed run)")` — defensive recovery from a crashed run.

These are non-trivial behaviours (a crash recovery path and the entire D-30 quarantine-retry promise) and they are completely untested. If a future refactor accidentally turns either case into a skip, the regression slips through.

**Fix:** Add two tests:
```python
def test_is_eligible_retries_quarantined(tmp_path):
    src = tmp_path / "Show.S01E14.en.srt"
    src.write_text("...")
    ledger = _make_minimal_ledger(tmp_path, entries=[dict(
        source_path=str(src), output_path=None,
        status="quarantined", content_hash="x",
    )])
    ok, reason = is_eligible(src, ledger)
    assert ok is True
    assert "quarantin" in reason.lower()

def test_is_eligible_resumes_in_progress(tmp_path):
    src = tmp_path / "Show.S01E15.en.srt"
    src.write_text("...")
    ledger = _make_minimal_ledger(tmp_path, entries=[dict(
        source_path=str(src), output_path=None,
        status="in_progress", content_hash="x",
    )])
    ok, reason = is_eligible(src, ledger)
    assert ok is True
    assert "in_progress" in reason.lower() or "resuming" in reason.lower()
```

---

## Info

### IN-01: `tests/test_scan.py::test_foreign_vi` is misnamed — it tests "skip our own done output", not "skip foreign vi"

**File:** `tests/discover/test_scan.py:255-288`
**Issue:** The test docstring says "AUTO-04: never re-process our own output." The body sets up a ledger entry with `status="done"` and a matching `content_hash`, then asserts `eligible is False`. That is Case 2 (hash match), not Case 1 (foreign vi — no ledger entry). The actual "foreign vi" test is `test_gap_detection_foreign_vi_skip` above it. Two tests targeting different cases share a confusing name.

**Fix:** Rename to `test_self_output_skipped_when_hash_matches` (or similar) and adjust the docstring.

---

### IN-02: `radarr.py` defensive branch on `movie["movieFileId"] is None` is never exercised by tests

**File:** `trezarr/arr/radarr.py:116-120` and `tests/arr/test_arr_discovery.py`
**Issue:**
```python
has_file_id = movie.get("movieFileId", 0) != 0
has_inline_movie_file = movie.get("movieFile") is not None
if not has_file_id and not has_inline_movie_file:
    continue
```

If Radarr returns `movieFileId: null` in the JSON (which it does in some corner cases — newly-imported movie awaiting refresh), `movie.get("movieFileId", 0)` returns `None`, and `None != 0` is `True`, so `has_file_id` is set True. Then we proceed to the `movie_file` resolution path. If `movieFile` is also absent, `client.movie_file.get(movie_id=...)` is called — which on an actually-empty-file movie returns `[]`, and the warning log fires. Acceptable, but the logic is non-obvious.

The test `test_radarr_skips_missing_file` only covers `movieFileId: 0` and `movieFile` absent — it does NOT cover `movieFileId: null`. A minor test gap, but not load-bearing.

**Fix:** Tighten the predicate to `has_file_id = bool(movie.get("movieFileId"))` (truthy check) so `0`, `None`, and missing all behave identically. Add a test case for `movieFileId: None`.

---

### IN-03: `scan_for_eligible_items` import of `gap.is_eligible` inside the function body is described as "module-load-order cycle" prevention, but no cycle exists

**File:** `trezarr/discover/scan.py:228-231`
**Issue:**
```python
# Lazy import to keep module-load-time dependency graph minimal — gap
# imports from output.write and output.ledger; scan does not need to
# carry that surface at import time.
from trezarr.discover.gap import is_eligible
```

`gap.py` imports `Ledger` from `trezarr.output.ledger` and `derive_vi_sidecar_path` from `trezarr.output.write`. Neither imports from `scan.py`. There is no actual import cycle — the comment is misleading. The "module-load-time dependency graph" argument is also weak: `scan.py` already imports `Ledger` via `TYPE_CHECKING` only, so `output.write` would be a new module surface at import time, but that is a 50-line module with stdlib deps.

This isn't a bug; it's a documentation-vs-reality drift. Future readers will look for a cycle that doesn't exist.

**Fix:** Either move the import to the top of the module, or update the comment to reflect the actual reason (e.g. "kept lazy to avoid pulling write.py's pysubs2 deps until scan is actually called").

---

### IN-04: `apply_permissions` second-tier `OSError` catch on `os.chown` is dead code in practice

**File:** `trezarr/output/write.py:177-193`
**Issue:**
```python
try:
    os.chown(path, puid, pgid)
except PermissionError:
    logger.warning(...)
except OSError as exc:
    logger.warning("chown(%s) failed with unexpected error: %s", path, exc)
```

`PermissionError` is a subclass of `OSError`. The first `except` handles it. The second `except OSError` catches everything else (ENOENT, EROFS, etc.). On the Phase-3 happy path the file always exists by here (it was just written), and the only realistic non-EPERM cases are essentially "shouldn't happen." The second `except` exists for defense, but the log message says "unexpected" which is confusing — the caller of cli.py will see a chown failure warning that is technically *expected* on macOS with a read-only mount.

Not a bug. Minor noise hazard.

**Fix:** Inline a comment or downgrade the second `except` to log at DEBUG level.

---

### IN-05: `Ledger.content_hash` truncates SHA-256 to 16 hex chars (64 bits)

**File:** `trezarr/output/ledger.py:170-183`
**Issue:**
```python
return hashlib.sha256(source_bytes).hexdigest()[:16]
```

64 bits is sufficient for collision-resistance against accidental collisions in a single library (≤2^32 items before a 50% birthday-collision probability — i.e. ~4 billion subtitles). For Trezarr's per-user library this is essentially impossible. So this is not a security or correctness issue.

But the comment in `ledger.py:50-53` says this hash is "schema-compatible with the Phase-4 `processed_file` table" — Phase 4 may want the full hash for cross-system reconciliation or for forensic provenance after a corruption incident. 16 hex chars is a one-way ratchet: once we commit to it in the ledger format, Phase 4 can't widen it without a migration.

Not a Phase-3 defect. Flagging for Phase-4 awareness.

**Fix:** Consider storing the full 64-char SHA-256 hexdigest now. The size delta is negligible (~50 bytes per ledger entry).

---

### IN-06: `cli.py` Step-1 setting load swallows all `_yaml_file=None` cases into the default branch

**File:** `trezarr/cli.py:164`
**Issue:**
```python
settings = TrezarrSettings(_yaml_file=config_path) if config_path else TrezarrSettings()
```

This ternary is unnecessary — `TrezarrSettings(_yaml_file=None)` is equivalent to `TrezarrSettings()` per `config.py:117-126` (the `__init__` accepts `_yaml_file=None`). The defensive ternary suggests confusion at the call site about whether `None` is honoured. It also means future readers must check both branches to reason about settings loading.

**Fix:**
```python
settings = TrezarrSettings(_yaml_file=config_path)  # config_path may be None
```

---

_Reviewed: 2026-06-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
