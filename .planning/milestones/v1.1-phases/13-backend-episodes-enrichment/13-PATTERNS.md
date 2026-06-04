# Phase 13: Backend Episodes Enrichment - Pattern Map

**Mapped:** 2026-06-03
**Files analyzed:** 5 (3 source modifications + 2 test modifications)
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trezarr/web/routes/library.py` (rewrite `get_series_episodes`) | route handler | request-response | `get_library` in same file (lines 70–147) | exact — same file, same fail-soft envelope, same *arr client pattern |
| `trezarr/web/routes/library.py` (extend `get_library`) | route handler | request-response | existing `get_library` series/movies loop (lines 97–147) | exact — additive fields to existing dict |
| `trezarr/output/ledger_sqla.py` (new count helper) | data store / utility | CRUD (aggregate read) | `check` + `check_by_output_path` in same file (lines 68–113) | role-match — same file, same `async_sessionmaker` session pattern, same `select()` style |
| `trezarr/translate/engine.py` (D-06 series_id fix) | engine / pipeline | batch transform | the existing `LedgerEntry(...)` at lines 1097–1103 in same file | exact — one-line addition to the call site being fixed |
| `tests/web/test_library_api.py` (8 new tests) | test | request-response | existing 4 tests in same file (lines 10–75) | exact — same `AsyncClient + ASGITransport + create_app()` fixture pattern |
| `tests/translate/test_engine.py` (1 new test) | test | batch transform | existing engine tests in same file (lines 20–80+) | role-match — same `pytest.importorskip` pattern, same `async def` convention |

---

## Pattern Assignments

---

### `trezarr/web/routes/library.py` — rewrite `get_series_episodes`

**Analog:** `get_library` in `trezarr/web/routes/library.py` lines 70–147

**Imports pattern** (lines 17–28, 77–84):
```python
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# All heavy imports are deferred inside route bodies (PLC0415 project pattern)
from trezarr.arr import DiscoveryError          # noqa: PLC0415
from trezarr.arr.sonarr import build_sonarr_client  # noqa: PLC0415
from trezarr.config import TrezarrSettings      # noqa: PLC0415
from pyarr.exceptions import PyarrError         # noqa: PLC0415
```

**Settings access pattern** (line 85):
```python
settings: TrezarrSettings = getattr(request.app.state, "settings", None) or TrezarrSettings()
```

**Fail-soft errors-list / always-HTTP-200 pattern** (lines 87–112):
```python
errors: list[dict] = []

# Sonarr errors are caught and appended; the endpoint still returns 200
try:
    client = build_sonarr_client(settings)
    raw_series = client.series.get()
    if isinstance(raw_series, dict):          # pyarr single-dict normalization
        raw_series = [raw_series]
    for s in raw_series:
        ...
except (PyarrError, DiscoveryError, Exception) as exc:   # noqa: BLE001
    logger.warning("get_library: Sonarr error — %s", exc)
    series_list = []
    errors.append({"source": "sonarr", "error": str(exc)})
```

**sonarr_enabled guard / 400 pattern** (lines 162–163 in current `get_series_episodes`):
```python
if not settings.sonarr_enabled:
    return JSONResponse({"error": "sonarr_disabled"}, status_code=400)
```

**vi-sidecar status check pattern** (lines 199–203, current `get_series_episodes`):
```python
vi_found = any(
    (local_path.parent / (local_path.stem + ext)).exists()
    for ext in (".vi.srt", ".vi.ass", ".vi.vtt")
)
status = "translated" if vi_found else "has_source"
```

**session_factory access pattern** (line 265, `post_translate`):
```python
session_factory = getattr(request.app.state, "session_factory", None)
```

**Delta to apply — get_series_episodes:**

Replace the entire `get_series_episodes` function (lines 152–220) with the enriched version that:

1. Adds deferred imports for `asyncio`, `collections.defaultdict`, `BazarrClient`, `BazarrError`, `_ORIG_LANG_NAME_TO_CODE2`.
2. Wraps the two pyarr calls in `asyncio.to_thread` and runs them with `asyncio.gather`:
   ```python
   episodes_raw, ep_files_raw = await asyncio.gather(
       asyncio.to_thread(client.episode.get, series_id=series_id),
       asyncio.to_thread(client.episode_file.get, series_id=series_id),
   )
   ep_file_by_id = {ef["id"]: ef for ef in ep_files_raw}
   ```
3. Adds Bazarr fail-soft block (D-08): `bazarr_enabled` → try `fetch_episode_inventory` → on `BazarrError` append to `errors[]`, set `bazarr_available=False`; on disabled set `bazarr_available=False` with no error entry.
4. Builds season groups via `defaultdict(list)` keyed on `ep["seasonNumber"]`.
5. Constructs `episode_key = f"S{season_number:02d}E{episode_number:02d}"` from episode record ints (retiring `_episode_key_from_file` for this endpoint).
6. Returns `{ series_id, bazarr_available, seasons: [...], errors: [] }` envelope.
7. Keeps `PyarrError → 502` for the Sonarr call (D-08).

**Delta to apply — get_library (counts extension):**

Inside the existing Sonarr series loop (after line 108), add:
```python
# After the Sonarr series loop, add one bulk query:
from trezarr.output.ledger_sqla import translated_counts_for_series  # noqa: PLC0415
series_ids = [s.get("id") for s in raw_series if s.get("id") is not None]
t_counts = await translated_counts_for_series(session_factory, series_ids)
```
Then within the per-series dict construction:
```python
series_list.append({
    ...existing fields...,
    "translated_count": t_counts.get(str(s.get("id")), 0),
    "total_count": s.get("statistics", {}).get("episodeFileCount", 0),
})
```
For movies, inside the existing Radarr loop after the `find_source_sub` call:
```python
local_path_obj = local_path if raw_path else None
vi_found = False
if local_path_obj and source_sub_found:
    vi_found = any(
        (local_path_obj.parent / (local_path_obj.stem + ext)).exists()
        for ext in (".vi.srt", ".vi.ass", ".vi.vtt")
    )
movies_list.append({
    ...existing fields...,
    "translated_count": 1 if vi_found else 0,
    "total_count": 1 if m.get("hasFile", False) else 0,
})
```
Note: `session_factory` is already fetched at line 265 inside `post_translate`; the `get_library` handler must fetch it the same way: `session_factory = getattr(request.app.state, "session_factory", None)`.

---

### `trezarr/output/ledger_sqla.py` — new `translated_counts_for_series` function

**Analog:** `check` and `check_by_output_path` in `trezarr/output/ledger_sqla.py` lines 68–113

**Session open pattern** (lines 79–86, `check`):
```python
async with self._session_factory() as session:
    result = await session.execute(
        select(ProcessedFile).where(ProcessedFile.source_path == key)
    )
    row = result.scalar_one_or_none()
```

**select() + where() style** (lines 109–112, `check_by_output_path`):
```python
async with self._session_factory() as session:
    result = await session.execute(
        select(ProcessedFile).where(ProcessedFile.output_path == key)
    )
    row = result.scalar_one_or_none()
    return _row_to_entry(row) if row is not None else None
```

**Imports already present in file** (lines 30–37):
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from trezarr.bible.models import ProcessedFile
from trezarr.output.ledger import LedgerEntry
```

**Delta to apply:**

Add one new **module-level async function** (not a method on `LedgerSQLA`) after line 198 (after `_row_to_entry`). New import `func` must be added to the existing `from sqlalchemy import select` line:

```python
# Change line 31:
from sqlalchemy import func, select
```

New function to append at module bottom:

```python
async def translated_counts_for_series(
    session_factory: async_sessionmaker,
    series_ids: list[int],
) -> dict[str, int]:
    """Return {str(series_id): count} of status='done' ProcessedFile rows.

    One GROUP BY aggregate query — O(1) DB roundtrips regardless of library size.
    Keys are str because ProcessedFile.series_id is Mapped[str | None].
    Returns 0 (via missing key) for any series_id with no done records.

    Args:
        session_factory: async_sessionmaker from request.app.state.session_factory.
        series_ids: List of integer Sonarr series IDs to query.

    Returns:
        Dict mapping str(series_id) → count of done rows.
    """
    if not series_ids:
        return {}
    str_ids = [str(sid) for sid in series_ids]
    async with session_factory() as session:
        result = await session.execute(
            select(ProcessedFile.series_id, func.count().label("n"))
            .where(
                ProcessedFile.series_id.in_(str_ids),
                ProcessedFile.status == "done",
            )
            .group_by(ProcessedFile.series_id)
        )
        return {row.series_id: row.n for row in result}
```

Session pattern matches `check`/`check_by_output_path` exactly: `async with session_factory() as session:` (note: module-level helper takes `session_factory` as a parameter, unlike the method which uses `self._session_factory`).

---

### `trezarr/translate/engine.py` — D-06 series_id fix

**Analog:** The existing `LedgerEntry(...)` call at lines 1097–1103 in the same file

**Current code at lines 1097–1103:**
```python
await ledger.record(LedgerEntry(
    source_path=str(path),
    output_path=str(output_path),
    status="done",
    content_hash=content_hash,
    translated_at=datetime.now(timezone.utc).isoformat(),
))
```

**`arr_series_id` in scope at line 786:**
```python
arr_series_id = getattr(media_item, "series_id", None) or 0
```

**`eligible_item` in scope** — it is the argument that carries `media_item`; it is `None` on the mechanical (no-Bible) path, non-None on the eligible-item path.

**Delta to apply — one-line addition immediately before the `ledger.record` call:**

```python
# Step 11: Record completion in ledger
_ledger_series_id: str | None = (
    str(arr_series_id) if eligible_item is not None and arr_series_id else None
)
await ledger.record(LedgerEntry(
    source_path=str(path),
    output_path=str(output_path),
    status="done",
    content_hash=content_hash,
    translated_at=datetime.now(timezone.utc).isoformat(),
    series_id=_ledger_series_id,          # D-06 fix: was omitted, defaults to None
))
```

No import changes needed. `LedgerEntry.series_id: str | None = None` already exists (ledger.py:81). This is the only change to engine.py for this phase — the three quarantine paths (lines ~812, ~911, ~1080) intentionally remain without `series_id` (they have no eligible_item context or the series may not be resolved).

---

### `trezarr/source_selection/rank.py` — audio language map (READ-ONLY)

**Source for D-07 normalization:** `_ORIG_LANG_NAME_TO_CODE2` at lines 55–105

**Concrete constant** (lines 55–105):
```python
_ORIG_LANG_NAME_TO_CODE2: dict[str, str] = {
    "english": "en",
    "korean": "ko",
    "japanese": "ja",
    "chinese": "zh",
    "thai": "th",
    "vietnamese": "vi",
    "cantonese": "zh",
    "mandarin": "zh",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "portuguese": "pt",
    "italian": "it",
    "russian": "ru",
    "arabic": "ar",
    "hindi": "hi",
    "indonesian": "id",
    # ... 20+ more entries through line 105
}
```

**Usage pattern in the new route handler** (D-07, to be added to `library.py`):

```python
from trezarr.source_selection.rank import _ORIG_LANG_NAME_TO_CODE2  # noqa: PLC0415

def _normalize_audio_languages(raw: list | str | None) -> list[str]:
    """Full-name → ISO-639-1 code2. Dedupes, preserves order."""
    if not raw:
        return []
    if isinstance(raw, str):
        names = [n.strip() for n in raw.split("/") if n.strip()]
    else:
        names = []
        for item in raw:
            names.extend(n.strip() for n in str(item).split("/") if n.strip())
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        code = _ORIG_LANG_NAME_TO_CODE2.get(name.lower(), name.lower())
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result
```

This file is NOT modified. The import crosses from `web/routes/library.py` into `source_selection/rank.py`. No `__all__` alias is needed (intra-project private import is acceptable per D-07 discretion).

---

### `tests/web/test_library_api.py` — 8 new tests

**Analog:** Existing 4 tests in `tests/web/test_library_api.py` lines 10–75

**Test structure pattern** (lines 10–24, `test_get_library_returns_200`):
```python
async def test_get_library_returns_200():
    """GET /api/library always returns 200 even when *arr disabled."""
    from trezarr.web.app import create_app           # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport     # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library")
    assert resp.status_code == 200
    data = resp.json()
    assert "series" in data
    assert isinstance(data["series"], list)
```

**Key conventions:**
- `asyncio_mode = "auto"` project-wide (pyproject.toml) — no `@pytest.mark.asyncio` decorator needed.
- All trezarr imports deferred inside test bodies (`# noqa: PLC0415`).
- `create_app()` with default settings → `sonarr_enabled=False`, `bazarr_enabled=False` (safe defaults).
- To inject enabled settings: set `app.state.settings = TrezarrSettings(sonarr_enabled=True, ...)` after `create_app()`, or patch `build_sonarr_client`.
- `pytest-httpx` or `unittest.mock.patch` for mocking pyarr calls — patch at `trezarr.arr.sonarr.build_sonarr_client`.

**Delta — 8 new test functions to append to the file:**

| Test name | What it asserts |
|---|---|
| `test_get_series_episodes_bazarr_disabled` | `bazarr_available=False`, HTTP 200, `errors=[]` (disabled, no error entry per D-08) |
| `test_get_series_episodes_bazarr_error` | `bazarr_available=False`, HTTP 200, `errors[0].source == "bazarr"` (enabled+unreachable per D-08) |
| `test_get_series_episodes_bazarr_join_key` | Bazarr inventory keyed on `episode.id` (not `episodeFile.id`) — subtitle appears in correct episode row |
| `test_audio_language_normalization` | `_normalize_audio_languages("Korean/English") == ["ko", "en"]`; unknown name falls back to lowercased original |
| `test_get_series_episodes_envelope_shape` | Response has `series_id`, `bazarr_available`, `seasons` list; each season has `season_number` + `episodes`; each episode has `episode_id`, `episode_key`, `audio_languages`, `subtitles` |
| `test_get_library_series_count_fields` | Each series item in `/api/library` response has `translated_count` and `total_count` integer fields |
| `test_translated_counts_for_series` | Unit test of `translated_counts_for_series(session_factory, [1, 2])` against an in-memory SQLite DB with mock ProcessedFile rows; returns correct `{str(id): n}` |
| `test_get_library_movies_count_fields` | Each movie item has `translated_count` (0 when no vi sidecar) and `total_count` (0 when no file) |

For tests requiring Sonarr mocking, patch pattern:
```python
from unittest.mock import patch, MagicMock       # noqa: PLC0415

mock_client = MagicMock()
mock_client.episode.get.return_value = [{"id": 10, "seasonNumber": 1, ...}]
mock_client.episode_file.get.return_value = [{"id": 5, "path": "/media/ep.mkv", ...}]

with patch("trezarr.arr.sonarr.build_sonarr_client", return_value=mock_client):
    ...
```

---

### `tests/translate/test_engine.py` — 1 new test

**Analog:** Existing tests in `tests/translate/test_engine.py` lines 1–80

**`pytest.importorskip` pattern** (lines 29–31):
```python
engine_mod = pytest.importorskip("trezarr.translate.engine")
build_translate_prompt = engine_mod.build_translate_prompt
```

**`async def` convention** (file header lines 7–8):
```python
# asyncio_mode="auto" is configured in pyproject.toml — no @pytest.mark.asyncio needed
```

**Delta — 1 new async test to append:**

```python
async def test_ledger_records_series_id_on_success():
    """D-06 fix: engine success path must record series_id in LedgerEntry (Phase 13).

    Verifies that the LedgerEntry passed to ledger.record() at Step 11 carries
    series_id = str(arr_series_id) when eligible_item is not None.
    """
    from unittest.mock import AsyncMock, MagicMock, patch   # noqa: PLC0415
    from trezarr.output.ledger import LedgerEntry           # noqa: PLC0415

    recorded_entries: list[LedgerEntry] = []

    mock_ledger = MagicMock()
    mock_ledger.record = AsyncMock(side_effect=lambda e: recorded_entries.append(e))
    mock_ledger.check = AsyncMock(return_value=None)
    mock_ledger.content_hash = MagicMock(return_value="abc123")

    # ... set up minimal eligible_item with series_id=42 and invoke translate_file ...
    # Assert:
    assert len(recorded_entries) == 1
    assert recorded_entries[0].series_id == "42"
```

The exact test body depends on the engine's `translate_file` call signature (how to inject mock LLM, ledger, and eligible_item). Mirror whatever fixture approach the existing `ENG-07` test (translate_file skips when ledger says done) uses — likely a full mock of the LLM client and filesystem.

---

## Shared Patterns

### Deferred imports (PLC0415)
**Source:** Throughout `trezarr/web/routes/library.py` (lines 77–84, 158–170, 256–257)
**Apply to:** All route handlers in library.py; all test bodies in test files

All heavy imports (`from trezarr.*`, `from pyarr.*`, `from httpx import ...`) go inside function/method bodies, never at module top level, followed by `# noqa: PLC0415`.

### pyarr single-dict normalization
**Source:** `trezarr/web/routes/library.py` lines 96–97, 119–120, 174–175
```python
if isinstance(raw_series, dict):
    raw_series = [raw_series]
```
**Apply to:** Every `client.episode.get(...)` and `client.episode_file.get(...)` call in the rewritten handler.

### Fail-soft errors list + always-HTTP-200
**Source:** `trezarr/web/routes/library.py` lines 87–112
```python
errors: list[dict] = []
try:
    ...
except (PyarrError, DiscoveryError, Exception) as exc:  # noqa: BLE001
    logger.warning("...: source error — %s", exc)
    errors.append({"source": "bazarr", "error": str(exc)})
return JSONResponse({..., "errors": errors})
```
**Apply to:** The Bazarr branch in the rewritten `get_series_episodes` (D-08). The Sonarr branch keeps its existing `502` (not fail-soft for episode endpoint).

### async session open
**Source:** `trezarr/output/ledger_sqla.py` lines 79–86, 108–113
```python
async with self._session_factory() as session:
    result = await session.execute(select(...).where(...))
```
**Apply to:** `translated_counts_for_series` module-level function (uses `session_factory` parameter instead of `self._session_factory`, otherwise identical pattern).

### Test client + ASGITransport fixture
**Source:** `tests/web/test_library_api.py` lines 13–18
```python
from trezarr.web.app import create_app
from httpx import AsyncClient, ASGITransport

app = create_app()
async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
    resp = await client.get("/api/library")
```
**Apply to:** All 8 new HTTP-level tests in `test_library_api.py`.

---

## No Analog Found

None. All five modified files have close analogs within the same file or same test module.

---

## Metadata

**Analog search scope:** `trezarr/web/routes/`, `trezarr/output/`, `trezarr/translate/`, `trezarr/source_selection/`, `tests/web/`, `tests/translate/`
**Files read directly:** 6 source files + 2 planning docs
**Pattern extraction date:** 2026-06-03
