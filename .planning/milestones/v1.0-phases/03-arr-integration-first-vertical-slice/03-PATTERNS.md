# Phase 3: *arr Integration + First Vertical Slice - Pattern Map

**Mapped:** 2026-05-31
**Files analyzed:** 11 new/modified files
**Analogs found:** 11 / 11

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trezarr/arr/__init__.py` | package init | — | `trezarr/output/__init__.py` | exact |
| `trezarr/arr/sonarr.py` | service (API client) | request-response | `trezarr/llm/client.py` | role-match |
| `trezarr/arr/radarr.py` | service (API client) | request-response | `trezarr/llm/client.py` | role-match |
| `trezarr/paths.py` | utility | transform | `trezarr/output/write.py` | data-flow-match |
| `trezarr/discover/__init__.py` | package init | — | `trezarr/output/__init__.py` | exact |
| `trezarr/discover/scan.py` | utility | file-I/O | `trezarr/output/write.py` | role-match |
| `trezarr/discover/gap.py` | utility | CRUD | `trezarr/output/ledger.py` | role-match |
| `trezarr/cli.py` | entry point | request-response | `trezarr/translate/engine.py` | data-flow-match |
| `trezarr/config.py` (extend) | config | — | `trezarr/config.py` | exact (self) |
| `trezarr/output/write.py` (extend) | utility | file-I/O | `trezarr/output/write.py` | exact (self) |
| `trezarr/output/ledger.py` (extend) | utility | CRUD | `trezarr/output/ledger.py` | exact (self) |

**Test files:**

| New/Modified Test File | Role | Closest Analog | Match Quality |
|------------------------|------|----------------|---------------|
| `tests/arr/__init__.py` | package init | `tests/output/__init__.py` | exact |
| `tests/arr/test_arr_discovery.py` | test (unit, httpx_mock) | `tests/llm/test_client_tiers.py` | role-match |
| `tests/discover/__init__.py` | package init | `tests/output/__init__.py` | exact |
| `tests/discover/test_scan.py` | test (unit, tmp_path) | `tests/output/test_write.py` | role-match |
| `tests/test_paths.py` | test (unit, tmp_path) | `tests/output/test_write.py` | role-match |
| `tests/test_cli.py` | test (integration) | `tests/translate/test_engine.py` | role-match |
| `tests/output/test_write.py` (extend) | test (unit) | `tests/output/test_write.py` | exact (self) |
| `tests/config/test_settings.py` (extend) | test (unit) | `tests/config/test_settings.py` | exact (self) |

---

## Pattern Assignments

### `trezarr/arr/__init__.py` and `trezarr/discover/__init__.py`

**Analog:** `trezarr/output/__init__.py` (empty package marker)

These are empty `__init__.py` files. The existing sub-packages (`trezarr/output/`, `trezarr/llm/`, `trezarr/subtitles/`, `trezarr/translate/`) all use empty `__init__.py` files with no re-exports. Follow the same pattern: create the file empty or with a single docstring comment.

---

### `trezarr/arr/sonarr.py` (service, request-response)

**Analog:** `trezarr/llm/client.py`

**Imports pattern** (lines 1-17 of client.py):
```python
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING
import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

if TYPE_CHECKING:
    from ..config import TrezarrSettings
```
Mirror this for arr/sonarr.py:
```python
from __future__ import annotations
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pyarr import Sonarr

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)
```

**Constructor pattern — SecretStr unwrap at init only** (client.py lines 40-57):
The sole place where `.get_secret_value()` is called is inside `__init__`. The key is passed directly into the external client and never stored as a plain string on `self`. Apply the same pattern to pyarr:
```python
def build_sonarr_client(settings: "TrezarrSettings") -> Sonarr:
    return Sonarr(
        host=settings.sonarr_host,
        api_key=settings.sonarr_api_key.get_secret_value(),  # SecretStr — resolve only here
        port=settings.sonarr_port,
        tls=False,
    )
```

**Guard-and-continue pattern** (client.py lines 83-88 for validation before API call):
The LLM client validates inputs at the boundary (`if not messages: raise ValueError`). Apply the same fail-fast pattern for the discovery guard: check `settings.sonarr_enabled` before constructing the pyarr client, return an empty list if disabled rather than crashing.

**Error handling pattern** (client.py lines 144-155):
Catch specific error types, not the base exception class. For pyarr, catch `httpx.HTTPStatusError` at the pyarr call boundary; let it propagate to the CLI batch loop (D-30 quarantine logic handles per-item failures there). Do not suppress it silently.

---

### `trezarr/arr/radarr.py` (service, request-response)

**Analog:** `trezarr/arr/sonarr.py` (same pattern, different pyarr class)

`radarr.py` is structurally identical to `sonarr.py` — replace `Sonarr` with `Radarr`, `series.get()` with `movie.get()`, and adjust the response-field access (`movie['movieFile']['path']` instead of `ep_file['path']`). The imports, guard, SecretStr pattern, and error handling are identical.

Key difference: Radarr `movie.get()` embeds `movieFile` inline; guard with `movie.get('movieFile') is not None` before accessing `movie['movieFile']['path']`. If absent, call `radarr.movie_file.get(movie_id=X)` as a fallback (RESEARCH.md Open Question 1).

---

### `trezarr/paths.py` (utility, transform)

**Analog:** `trezarr/output/write.py`

**Module docstring + imports pattern** (write.py lines 1-28):
```python
"""Atomic UTF-8 sidecar write with correct naming convention (D-19).

Design decisions honoured:
  D-19  ...
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
```
Mirror for paths.py — cite the relevant decisions (D-23, D-24, D-29):
```python
"""Path-mapping layer: remote→local prefix substitution, startup probe, traversal guard (D-23, D-24, D-29)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
```

**Pure function pattern** (write.py lines 31-51 — `derive_vi_sidecar_path`):
write.py exports small, focused pure functions with docstrings that cite the decision they implement. paths.py should follow the same pattern for `apply_path_mapping()`, `assert_within_media_roots()`, and `probe_media_roots()` — each is a small function with a docstring linking back to the decision (D-23/D-24/D-29).

**Defensive normalization** (write.py lines 46-51 — `_LANG_CODE_RE`, stem stripping):
write.py normalizes the stem before appending the output extension. paths.py normalizes both the mapping `remote` and the incoming API path with `.rstrip("/")` before prefix matching — same defensive approach, same test-for-edge-cases expectation.

---

### `trezarr/discover/scan.py` (utility, file-I/O)

**Analog:** `trezarr/output/write.py`

**Regex at module level** (write.py line 28):
```python
_LANG_CODE_RE = re.compile(r'\.[a-z]{2}$', re.IGNORECASE)
```
scan.py uses a similar module-level compiled regex for matching sidecar language codes:
```python
_LANG_SIDECAR_RE = re.compile(r'^(.+?)\.([a-z]{2,3})\.srt$', re.IGNORECASE)
```
Note the 2-or-3-letter lang code (`{2,3}`) to handle Bazarr's 3-letter ISO codes (RESEARCH.md Open Question 3).

**Path manipulation pattern** (write.py lines 46-51):
```python
media_path = Path(media_path).resolve()
stem = media_path.stem
if _LANG_CODE_RE.search(stem):
    stem = stem.rsplit('.', 1)[0]
return media_path.parent / (stem + '.vi.srt')
```
scan.py's `find_source_sub()` does the inverse: given a resolved media path, derive `media_stem = media_path.stem`, glob `media_dir.glob(f"{media_stem}.*.srt")`, and match against the sidecar regex. Same `Path(media_path).resolve()` → `.parent` / `.stem` idiom.

**Return type annotation** (write.py line 54):
write.py uses `-> Path`. scan.py's `find_source_sub` returns `tuple[Path, str] | None` — use the same `from __future__ import annotations` plus modern union syntax (`X | None`).

---

### `trezarr/discover/gap.py` (utility, CRUD)

**Analog:** `trezarr/output/ledger.py`

**Ledger interaction pattern** (ledger.py lines 116-125 — `check()`):
```python
def check(self, source_path: str | Path) -> LedgerEntry | None:
    return self._data.get(str(source_path))
```
gap.py calls `ledger.check(str(source_sub_path))` and branches on the returned entry's `.status` and `.content_hash`. Follow the same `str(path)` coercion convention when passing paths to `ledger.check()` — always stringify the `Path` object.

**Status-based branching** (ledger.py `LedgerEntry.status` field — line 57):
The existing status literals are `"done" | "quarantined" | "in_progress"`. gap.py's `is_eligible()` branches on these exact strings — no new status values in Phase 3.

**Hash computation pattern** (ledger.py lines 164-178):
```python
@staticmethod
def content_hash(source_bytes: bytes) -> str:
    return hashlib.sha256(source_bytes).hexdigest()[:16]
```
gap.py calls `Ledger.content_hash(source_sub_path.read_bytes())` to compare against `entry.content_hash`. Never reimplement the hash — always call this static method.

**Import pattern** (ledger.py lines 22-32):
```python
from __future__ import annotations
import dataclasses
import hashlib
import json
import logging
...
from pathlib import Path
from typing import Literal
```
gap.py imports from the existing modules:
```python
from trezarr.output.ledger import Ledger
from trezarr.output.write import derive_vi_sidecar_path
```
Use relative imports (from `trezarr.` not `..`) to match the pattern used in engine.py lines 36-43.

---

### `trezarr/cli.py` (entry point, request-response)

**Analog:** `trezarr/translate/engine.py`

**Module-level logger pattern** (engine.py line 48):
```python
logger = logging.getLogger(__name__)
```
cli.py uses the same pattern: `logger = logging.getLogger(__name__)` at module level.

**Import block structure** (engine.py lines 21-47):
```python
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from tenacity import retry, ...

from trezarr.llm.client import LLMClient
from trezarr.output.ledger import Ledger, LedgerEntry
from trezarr.output.write import derive_vi_sidecar_path, write_vi_sidecar
...
```
cli.py follows the same import ordering: stdlib first (argparse, asyncio, logging, sys), then third-party, then intra-project `trezarr.*` imports.

**`asyncio.run()` entry pattern** (engine.py dispatches async work from a sync boundary via `asyncio.gather()`):
cli.py's `main()` is synchronous (called by the console_script entry point), and it calls `asyncio.run(_run_once(args.config))` to execute the async pipeline. This is the established pattern for bridging the sync CLI entry to async work.

**Exception-per-item pattern** (engine.py lines 449-465 — read/batch failure quarantine):
```python
try:
    source_doc = read_srt(path)
    batches = batch_subdoc(source_doc, settings)
except Exception as exc:
    reason = f"read/batch failure: {exc}"
    quarantine_path = _write_quarantine(path, reason, [], settings)
    ledger.record(LedgerEntry(..., status="quarantined", ...))
    return TranslationResult(status="quarantined", ...)
```
cli.py applies the same per-item try/except in the batch loop (D-30): catch `Exception` per item, log the error, increment `n_fail`, continue the loop. Never let one item abort the batch.

**Dataclass result pattern** (engine.py lines 72-84 — `TranslationResult`):
```python
@dataclass
class TranslationResult:
    status: str  # "done" | "skipped" | "quarantined"
    output_path: Path | None = None
    quarantine_path: Path | None = None
    reason: str | None = None
```
cli.py should define a `MediaItem` dataclass (or named tuple) to carry a discovered item through the pipeline: `local_path: Path`, `source_sub_path: Path`, `series_title: str`, `source_lang: str`. Follow the same `@dataclass` pattern with `from dataclasses import dataclass`.

**Exit code pattern** (engine.py does not set exit codes — this is new to cli.py):
Use `sys.exit(1)` when `n_fail > 0 or n_quar > 0`, `sys.exit(0)` otherwise (D-30). Call `sys.exit()` only at the outermost scope of `main()`, after `asyncio.run()` returns.

---

### `trezarr/config.py` (extend existing, config)

**Analog:** `trezarr/config.py` itself (additive extension)

**SecretStr field pattern** (config.py lines 48-49):
```python
llm_api_key: SecretStr = SecretStr("not-set")  # NEVER logged; SecretStr masks in repr/str
```
New arr API key fields must follow the same pattern:
```python
sonarr_api_key: SecretStr = SecretStr("")
radarr_api_key: SecretStr = SecretStr("")
```
Add the same inline comment: `# NEVER logged; SecretStr masks in repr/str`.

**Field group comment pattern** (config.py lines 46-82 — section comments):
```python
# ── LLM endpoint (D-03, D-05) ──────────────────────────────────────────────
llm_base_url: str = "http://localhost:1234/v1"
```
New fields must follow the same `# ── Section Name (D-XX) ──` section-divider comment style:
```python
# ── *arr connection (D-22) ─────────────────────────────────────────────────
sonarr_host: str = ""
sonarr_port: int = 8989
sonarr_api_key: SecretStr = SecretStr("")
sonarr_enabled: bool = False

radarr_host: str = ""
radarr_port: int = 7878
radarr_api_key: SecretStr = SecretStr("")
radarr_enabled: bool = False

# ── Path mapping (D-23) ────────────────────────────────────────────────────
path_mappings: list["PathMapping"] = []

# ── Source-language priority (D-25) ───────────────────────────────────────
source_lang_priority: list[str] = ["en"]

# ── Permissions (D-29) ────────────────────────────────────────────────────
puid: int = -1
pgid: int = -1
umask: int = 0o022
```

**`env_nested_delimiter="__"` already set** (config.py line 43):
The `PathMapping` Pydantic model for `path_mappings` will be parsed from env via JSON array string (e.g. `TREZARR_PATH_MAPPINGS='[{"remote":"/tv","local":"/data/tv"}]'`). This works because `env_nested_delimiter="__"` is already configured. Define `PathMapping` as a `BaseModel` (not a dataclass) so pydantic-settings can deserialize the JSON array correctly.

---

### `trezarr/output/write.py` (extend — add `apply_permissions`)

**Analog:** `trezarr/output/write.py` itself (additive extension)

**Module-level imports to extend** (write.py lines 16-24):
```python
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from trezarr.subtitles.model import SubDoc
from trezarr.subtitles.srt import write_srt
```
Add `import logging` and `import stat` to the existing import block (after `import os`).

**Logger pattern** (not yet present in write.py — add per engine.py line 48):
```python
logger = logging.getLogger(__name__)
```
Add this at module level, after the existing `_LANG_CODE_RE` constant.

**New function position**: `apply_permissions()` goes at the bottom of write.py, after `write_vi_sidecar()`, following the existing "helpers first, main function last" ordering.

**Error-continue pattern** (engine.py lines 452-464 — quarantine on `except Exception`):
```python
except PermissionError:
    logger.warning(
        "chown(%s, %d, %d) failed — process lacks CAP_CHOWN. "
        "File was written but ownership is not yet corrected. "
        "Phase 7 container init (s6-overlay) will fix this.",
        path, puid, pgid,
    )
except OSError as exc:
    logger.warning("chown(%s) failed with unexpected error: %s", path, exc)
```
Follow the existing project convention: `logger.warning(...)` with `%s`/`%d` formatting (not f-strings) to match the logger calls in `ledger.py` lines 102-103 and `engine.py` lines 425, 453.

---

### `trezarr/output/ledger.py` (extend — `LedgerEntry` docstring clarification)

**Analog:** `trezarr/output/ledger.py` itself

Per RESEARCH.md Pattern 6 and Pitfall 7: `LedgerEntry.content_hash` IS the source-sub hash (computed from source file bytes in `translate_file()`). The cleanest Phase-3 change is a docstring clarification on the `content_hash` field (lines 46-47) plus ensuring `source_lang` is populated by the CLI when recording entries.

No new field is added. The ledger extension is:
1. Update the `content_hash` docstring to explicitly state "source-subtitle content hash" (not vi-sidecar hash).
2. Ensure `source_lang` is populated in all new `LedgerEntry` constructions in cli.py (it exists as an optional field already on line 59).

---

## Test Pattern Assignments

### `tests/arr/test_arr_discovery.py` (unit, httpx_mock)

**Analog:** `tests/llm/test_client_tiers.py`

**Import deferral pattern** (test_client_tiers.py lines 24-29):
```python
async def test_uses_json_schema_by_default():
    from trezarr.llm.client import LLMClient  # deferred import
    from trezarr.config import TrezarrSettings  # deferred import
```
All imports from `trezarr.arr.*` are deferred inside each test function body. Use `pytest.importorskip("trezarr.arr.sonarr")` to skip cleanly when pyarr is not yet installed.

**Mock injection pattern** (test_client_tiers.py lines 38-44 — `patch.object`):
test_client_tiers.py patches via `unittest.mock.patch.object`. For arr tests, use the `pytest-httpx` `httpx_mock` fixture instead — it intercepts at the httpx transport layer transparently. The fixture is injected as a test argument:
```python
def test_sonarr_discovers_monitored_series(httpx_mock):
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[{"id": 1, "title": "Show A", "path": "/tv/Show A", "monitored": True}],
    )
    ...
```

**`async def` without `@pytest.mark.asyncio`** (test_client_tiers.py line 24):
```python
async def test_uses_json_schema_by_default():
```
Because `asyncio_mode = "auto"` is set in `pyproject.toml`, all `async def` tests run automatically without the `@pytest.mark.asyncio` decorator. Sync tests for arr discovery (using sync `Sonarr` client) use `def`, not `async def`.

**`settings_factory` fixture** (conftest.py lines 18-43):
tests/arr/ tests that need settings should use the `settings_factory` conftest fixture for test-safe settings (sets `llm_max_concurrency=1` etc.). New arr fields will need to be added to the factory defaults or passed as overrides.

---

### `tests/discover/test_scan.py` (unit, tmp_path)

**Analog:** `tests/output/test_write.py`

**`tmp_path` fixture pattern** (test_write.py lines 37-51):
```python
def test_sidecar_naming(tmp_path):
    write_mod = pytest.importorskip("trezarr.output.write")
    write_vi_sidecar = write_mod.write_vi_sidecar

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    ...
```
test_scan.py follows the same structure: `pytest.importorskip("trezarr.discover.scan")`, create files in `tmp_path`, assert on return values. No live filesystem or external service needed.

**Gap detection tests pattern** (test_ledger.py lines 93-117 — `test_foreign_srt_not_clobbered`):
```python
def test_foreign_srt_not_clobbered(tmp_path):
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    Ledger = ledger_mod.Ledger

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)  # empty ledger

    src = tmp_path / "Show.S01E03.en.srt"
    src.write_text("...", encoding="utf-8")
    dest = tmp_path / "Show.S01E03.vi.srt"
    dest.write_text("...", encoding="utf-8")

    found = ledger.check(str(src))
    assert found is None  # foreign file check
    assert dest.exists()  # not clobbered
```
gap detection tests use the same pattern: construct a `Ledger` from `tmp_path`, write stub SRT files, assert `is_eligible()` returns the expected `(bool, str)` tuple.

**Helper function** (test_write.py lines 18-34 — `_make_minimal_doc`):
test_scan.py should have a `_make_minimal_ledger(tmp_path, entries)` helper to build pre-populated `Ledger` instances for the skip/retry/foreign-vi test cases — mirrors the `_make_minimal_doc` helper pattern.

---

### `tests/test_paths.py` (unit, tmp_path)

**Analog:** `tests/output/test_write.py`

Same `tmp_path` + `pytest.importorskip` structure. Parametrize the path-mapping tests with `@pytest.mark.parametrize` over (api_path, mappings, expected) tuples — the path-mapping algorithm is a pure function with multiple input variants (prefix match, no match, trailing slash, longest-prefix priority), making parametrization the cleanest approach. test_write.py uses separate `def test_*` functions instead; either approach is fine, but parametrize is preferred for the 5+ path-mapping variants.

The startup probe tests (`test_probe_unreadable_root_exits`, etc.) use `tmp_path` to create real temp directories, then `pytest.raises(SystemExit)` to assert the fail-fast behaviour:
```python
def test_probe_unreadable_root_exits(tmp_path):
    paths_mod = pytest.importorskip("trezarr.paths")
    probe_media_roots = paths_mod.probe_media_roots

    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(SystemExit):
        probe_media_roots([nonexistent])
```

---

### `tests/test_cli.py` (integration)

**Analog:** `tests/translate/test_engine.py`

**`unittest.mock` patch pattern** (test_engine.py imports — uses `patch.object` via `from unittest.mock import AsyncMock, MagicMock, patch`):
test_cli.py patches `translate_file` (the Phase-2 engine) and `discover_sonarr_items` / `discover_radarr_items` via `unittest.mock.patch` (not `pytest-httpx`). The integration test verifies batch-loop semantics (D-30), not internal pyarr HTTP calls.

**`asyncio_mode = "auto"` pattern** (test_engine.py line 7 comment):
Async integration tests use `async def test_*():` without decorator, as confirmed by the existing test suite.

**Minimal settings** (test_engine.py — most tests use `settings_factory`):
Use `settings_factory(sonarr_enabled=False, radarr_enabled=False, ...)` with all arr hosts disabled, passing pre-built `MediaItem` lists directly to `_run_once()` to avoid real pyarr calls in the integration test.

---

### `tests/output/test_write.py` (extend — add `test_apply_permissions`)

**Analog:** `tests/output/test_write.py` itself (additive extension)

**`unittest.mock.patch` pattern** (test_client_tiers.py lines 110-116):
```python
with (
    patch.object(..., "parse", side_effect=_make_bad_request_error()),
    patch.object(..., "create", side_effect=_create_side_effect),
):
```
The `test_apply_permissions` test patches `os.chown` with a `PermissionError` side effect and verifies that `apply_permissions()` logs a warning and continues (does not raise). Same `with patch(...):` pattern.

**`pytest.importorskip` defer** (test_write.py line 39):
```python
write_mod = pytest.importorskip("trezarr.output.write")
```
Keep the same deferred import pattern for any new tests in this file.

---

### `tests/config/test_settings.py` (extend — new arr field tests)

**Analog:** `tests/config/test_settings.py` itself

**`test_env_override` pattern** (test_settings.py lines 16-21):
```python
def test_env_override(monkeypatch):
    from trezarr.config import TrezarrSettings
    monkeypatch.setenv("TREZARR_LLM_MODEL", "my-custom-model")
    settings = TrezarrSettings()
    assert settings.llm_model == "my-custom-model"
```
New tests for arr fields follow this exact pattern: `monkeypatch.setenv("TREZARR_SONARR_HOST", "192.168.1.10")`, then assert the parsed field value.

**`test_api_key_not_logged` pattern** (test_settings.py lines 36-50):
Add a similar test for `sonarr_api_key` and `radarr_api_key` — the secret must not appear in `str(settings)`, `repr(settings)`, or `model_dump()`.

**`test_yaml_load` pattern** (test_settings.py lines 25-32):
```python
def test_yaml_load(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("llm_model: yaml-model\nllm_max_retries: 7\n")
    settings = TrezarrSettings(_yaml_file=str(config_file))
```
New YAML test covers `path_mappings` list deserialization from YAML:
```python
config_file.write_text("path_mappings:\n  - remote: /tv\n    local: /data/tv\n")
settings = TrezarrSettings(_yaml_file=str(config_file))
assert len(settings.path_mappings) == 1
assert settings.path_mappings[0].remote == "/tv"
```

---

## Shared Patterns

### SecretStr for API Keys
**Source:** `trezarr/config.py` lines 48-49; `trezarr/llm/client.py` lines 49-54
**Apply to:** `trezarr/arr/sonarr.py`, `trezarr/arr/radarr.py`, `trezarr/config.py` (new fields)

```python
# config.py — field declaration
sonarr_api_key: SecretStr = SecretStr("")  # NEVER logged; SecretStr masks in repr/str

# arr/sonarr.py — only unwrap inside the client constructor function
sonarr = Sonarr(
    host=settings.sonarr_host,
    api_key=settings.sonarr_api_key.get_secret_value(),  # resolved once, never stored
    port=settings.sonarr_port,
)
```

### Module-level Logger
**Source:** `trezarr/translate/engine.py` line 48; `trezarr/output/ledger.py` line 33
**Apply to:** `trezarr/arr/sonarr.py`, `trezarr/arr/radarr.py`, `trezarr/discover/scan.py`, `trezarr/discover/gap.py`, `trezarr/cli.py`, `trezarr/output/write.py` (extend)

```python
logger = logging.getLogger(__name__)
```

### Logger Call Format (% not f-string)
**Source:** `trezarr/output/ledger.py` lines 102, 113; `trezarr/translate/engine.py` line 425
**Apply to:** All new modules with logger calls

```python
# Correct — matches existing project convention
logger.warning("chown(%s, %d, %d) failed: %s", path, puid, pgid, exc)
logger.info("foreign vi.srt at %s, not ours — skipping %s", dest, path)

# Wrong — not used in this codebase
logger.warning(f"chown({path}, {puid}, {pgid}) failed: {exc}")
```

### `from __future__ import annotations`
**Source:** `trezarr/llm/client.py` line 17; `trezarr/translate/engine.py` line 21; `trezarr/output/ledger.py` line 22
**Apply to:** All new Python source files

All existing source modules start with `from __future__ import annotations`. Apply to every new `.py` file.

### TYPE_CHECKING import guard
**Source:** `trezarr/llm/client.py` lines 25-27; `trezarr/translate/engine.py` lines 44-46
**Apply to:** Any new module that references `TrezarrSettings` only in type annotations

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
```

### Atomic Temp-File Write
**Source:** `trezarr/output/write.py` lines 72-98; `trezarr/output/ledger.py` lines 139-162
**Apply to:** Any new code that writes files (none in Phase 3 beyond extending write.py; `apply_permissions` writes no new files — it only chmod/chowns an existing file)

The pattern: `NamedTemporaryFile(dir=dest.parent, delete=False)` + write + `os.replace()` + `finally` cleanup. Do not apply to `apply_permissions` (which modifies permissions on an already-written file, not creating a new one).

### pytest deferred import pattern
**Source:** `tests/output/test_write.py` line 39; `tests/output/test_ledger.py` lines 23-24
**Apply to:** All new test files

```python
def test_something(tmp_path):
    mod = pytest.importorskip("trezarr.arr.sonarr")  # skips if module absent
    discover_sonarr_items = mod.discover_sonarr_items
    ...
```

### Decision-citation docstrings
**Source:** `trezarr/output/write.py` lines 1-13; `trezarr/output/ledger.py` lines 1-20; `trezarr/translate/engine.py` lines 1-19
**Apply to:** All new modules

Every module docstring lists the decision numbers it honours:
```python
"""Path-mapping layer: remote→local prefix substitution, startup probe, traversal guard.

Design decisions honoured:
  D-23  Ordered remote→local find/replace pairs ...
  D-24  Fail-fast startup readability probe ...
  D-29  Path-traversal guard: constrain writes to configured media roots.
"""
```

---

## No Analog Found

All Phase 3 files have analogs in the codebase. No files require falling back to RESEARCH.md patterns only — every new file maps to an existing module for imports, error handling, and structural conventions.

---

## Metadata

**Analog search scope:** `trezarr/` (all 18 source files), `tests/` (all 20 test files)
**Files scanned:** 18 source + 20 test = 38 files
**Pattern extraction date:** 2026-05-31
