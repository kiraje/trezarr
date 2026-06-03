---
phase: quick-260603-mc3
plan: "01"
subsystem: web
tags: [spa, staticfiles, deeplink, react-router, starlette]
dependency_graph:
  requires: []
  provides: [SPAStaticFiles, _spa_dir test injection]
  affects: [trezarr/web/app.py]
tech_stack:
  added: []
  patterns: [StaticFiles subclass override, get_response() selective fallback]
key_files:
  created:
    - tests/web/test_spa_fallback.py
  modified:
    - trezarr/web/app.py
decisions:
  - "SPAStaticFiles placed at module scope (not inside create_app) so imports are clean"
  - "_spa_dir param on create_app allows test injection without building the frontend"
  - "self.directory confirmed as the correct Starlette attribute (verified from source)"
  - "path arg to get_response is unslashed (verified from Starlette get_path() source)"
metrics:
  duration: "8 min"
  completed: "2026-06-03"
  tasks: 2
  files: 2
---

# Quick Task 260603-mc3: Selective SPA Fallback for Deep-Link Refresh — Summary

**One-liner:** SPAStaticFiles subclass falls back to index.html for extensionless React-Router routes while preserving honest 404s for missing assets and unknown /api paths.

## What Was Done

### Task 1 — SPAStaticFiles + mount swap (`trezarr/web/app.py`)

**Commit:** `0c0b084`

Three changes made to `trezarr/web/app.py`:

1. **New module-level imports** (moved `StaticFiles` import from inside `create_app` to module scope; added `StarletteHTTPException`, `FileResponse`, `Scope`):

   ```python
   from fastapi.staticfiles import StaticFiles
   from starlette.exceptions import HTTPException as StarletteHTTPException
   from starlette.responses import FileResponse
   from starlette.types import Scope
   ```

2. **`SPAStaticFiles` class** added at module level before `create_app` (lines ~47–83 after format):

   ```python
   class SPAStaticFiles(StaticFiles):
       async def get_response(self, path: str, scope: Scope) -> FileResponse:
           try:
               return await super().get_response(path, scope)
           except StarletteHTTPException as exc:
               if exc.status_code != 404:
                   raise
               last_segment = path.rstrip("/").rsplit("/", 1)[-1]
               has_extension = "." in last_segment
               is_api = path.startswith("api/") or path == "api"
               is_webhook = path.startswith("webhook/") or path == "webhook"
               if has_extension or is_api or is_webhook:
                   raise
               index_path = os.path.join(self.directory, "index.html")
               if not os.path.exists(index_path):
                   raise
               return FileResponse(index_path, media_type="text/html")
   ```

3. **`create_app` signature** updated to accept `_spa_dir: str | None = None`.

4. **`_static_dir` assignment** updated:
   ```python
   _static_dir = _spa_dir if _spa_dir is not None else os.path.join(
       os.path.dirname(__file__), "static"
   )
   ```

5. **Mount line** swapped from `StaticFiles(...)` to `SPAStaticFiles(...)`.  
   The `if os.path.exists(_static_dir):` guard, else-branch `logger.info`, and Pitfall-E ordering (mount last) are all preserved unchanged.

### Task 2 — Pytest coverage (`tests/web/test_spa_fallback.py`)

**Commit:** `cbf1ad3`

Six self-contained async test functions, each calling `create_app(_spa_dir=str(tmp_path))` and using `AsyncClient + ASGITransport`. The `_make_spa_dir` helper writes `index.html` (sentinel) and `asset.js` to `tmp_path`.

## Assumption Verification

### Assumption 1: `self.directory` attribute

**Confirmed.** From installed Starlette source (`staticfiles.py`, line 49):
```python
self.directory = directory
```
`StaticFiles.__init__` stores the constructor `directory` arg directly as `self.directory`. The `SPAStaticFiles.get_response` override uses `os.path.join(self.directory, "index.html")` — no adaptation needed.

### Assumption 2: `path` has NO leading slash

**Confirmed.** `StaticFiles.get_path()` (lines 101–107 of Starlette source) does:
```python
route_path = get_route_path(scope)
return os.path.normpath(os.path.join(*route_path.split("/")))
```
For `/library` → `os.path.normpath(os.path.join("", "library"))` → `"library"`.  
For `/api/nope` → `"api/nope"`.  
For `/` → `os.path.normpath(".")` → `"."`.

The `is_api` and `is_webhook` checks use the unslashed form (`path.startswith("api/")`, `path == "api"`, etc.). Correct.

One consequence: `path = "."` for root (`/`). The dot has no extension so `"." in "."` is True — BUT the root directory IS found by the parent's html=True directory-index logic, so `super().get_response()` succeeds and the except block is never reached for `/`. Verified by `test_root_still_serves_index` passing.

## Pytest Tail (all 6 cases)

```
tests/web/test_spa_fallback.py::test_spa_deep_link_library PASSED        [ 16%]
tests/web/test_spa_fallback.py::test_spa_nested_route_bible PASSED       [ 33%]
tests/web/test_spa_fallback.py::test_missing_asset_with_extension_returns_404 PASSED [ 50%]
tests/web/test_spa_fallback.py::test_unknown_api_path_returns_404_json PASSED [ 66%]
tests/web/test_spa_fallback.py::test_root_still_serves_index PASSED      [ 83%]
tests/web/test_spa_fallback.py::test_real_static_file_served_directly PASSED [100%]

============================== 6 passed in 0.37s ===============================
```

## Full Web Test Suite (no regressions)

```
53 passed, 2 xfailed in 1.13s
```

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 — app.py | `0c0b084` | `fix(web): selective SPA fallback for deep-link refresh (260603-mc3)` |
| 2 — test file | `cbf1ad3` | `test(web): coverage for SPAStaticFiles fallback (260603-mc3)` |

## Deviations from Plan

None — plan executed exactly as written. The `self.directory` and unslashed `path` assumptions were both confirmed correct; no adaptation was needed.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The SPA fallback only affects paths that already fell through to the StaticFiles mount. Extension and prefix checks (T-mc3-01 mitigations) are present as specified.

## Self-Check

- [x] `trezarr/web/app.py` — `SPAStaticFiles` class exists at module level
- [x] `trezarr/web/app.py` — `create_app` accepts `_spa_dir` param
- [x] `trezarr/web/app.py` — mount uses `SPAStaticFiles`
- [x] `tests/web/test_spa_fallback.py` — 6 test functions, all pass
- [x] Commits `0c0b084` and `cbf1ad3` exist in git log
- [x] ruff clean on both files

## Self-Check: PASSED
