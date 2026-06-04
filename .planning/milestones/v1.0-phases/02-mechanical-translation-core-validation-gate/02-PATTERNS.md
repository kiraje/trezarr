# Phase 2: Mechanical Translation Core + Validation Gate - Pattern Map

**Mapped:** 2026-05-31
**Files analyzed:** 11 new/modified files
**Analogs found:** 11 / 11

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trezarr/translate/__init__.py` | package init | — | `trezarr/subtitles/__init__.py` | exact |
| `trezarr/translate/batching.py` | utility | transform | `trezarr/subtitles/srt.py` (`_parse_block`, `_TC_RE`) | role-match (pure-Python transform over SubDoc) |
| `trezarr/translate/sentinel.py` | utility | transform | `trezarr/subtitles/srt.py` (`_TC_RE` regex pattern) | partial (regex-extract-and-restore pattern) |
| `trezarr/translate/engine.py` | service | request-response (async) | `trezarr/llm/client.py` (`LLMClient.call()`) | role-match (async service calling `LLMClient`) |
| `trezarr/translate/validate.py` | utility | transform | `trezarr/subtitles/srt.py` (`_parse_block` assertion logic) | partial (pure-Python assertion chain) |
| `trezarr/output/__init__.py` | package init | — | `trezarr/llm/__init__.py` | exact |
| `trezarr/output/write.py` | utility | file-I/O | `trezarr/subtitles/srt.py` (`write_srt`) | role-match (file writer using SubDoc) |
| `trezarr/output/ledger.py` | service | file-I/O | `trezarr/subtitles/srt.py` (atomic read+write pattern) | partial (JSON ledger using same `os.replace` atomicity) |
| `trezarr/config.py` | config | — | `trezarr/config.py` (itself — extend, not replace) | exact |
| `tests/translate/test_batching.py` | test | — | `tests/llm/test_client_tiers.py` | role-match |
| `tests/translate/test_engine.py` | test | — | `tests/llm/test_client_concurrency.py` | exact (async mock + AsyncMock/patch pattern) |
| `tests/translate/test_validate.py` | test | — | `tests/codec/test_srt_model.py` | role-match (pure-Python unit assertions) |
| `tests/translate/test_sentinel.py` | test | — | `tests/codec/test_srt_model.py` | role-match |
| `tests/output/test_write.py` | test | — | `tests/codec/test_srt_roundtrip.py` | role-match (file I/O test with tmp paths) |
| `tests/output/test_ledger.py` | test | — | `tests/codec/test_srt_roundtrip.py` | role-match |

---

## Pattern Assignments

### `trezarr/translate/__init__.py` and `trezarr/output/__init__.py` (package inits)

**Analog:** `trezarr/subtitles/__init__.py` and `trezarr/llm/__init__.py`

Both existing package `__init__.py` files are empty (zero bytes). New packages follow the same convention — empty `__init__.py`, no re-exports.

```python
# Empty file — no imports, no __all__
```

---

### `trezarr/translate/batching.py` (utility, transform)

**Analog:** `trezarr/subtitles/srt.py`

**Imports pattern** (`srt.py` lines 31–38):
```python
from __future__ import annotations

import re
import warnings
from pathlib import Path

from .encoding import detect_encoding
from .model import SubDoc, SubLine
```
Phase-2 analog for `batching.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from trezarr.subtitles.model import SubDoc, SubLine

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
```

**Timecode-to-ms utility — reuse `_TC_RE` from `srt.py`** (`srt.py` lines 46–50):
```python
_TC_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d+)"  # start timecode
    r"\s*-->\s*"
    r"(\d{2}:\d{2}:\d{2}[,.]\d+)"  # end timecode
)
```
`batching.py` must replicate this pattern (or import it if `srt.py` exports it) to convert `SubLine.start_tc` / `end_tc` to milliseconds for scene-gap detection. Do NOT use `int(sl.start_tc[...])` — use the same regex approach that handles both comma and period separators.

**Core batch-pack pattern — greedy walk over `SubDoc.lines`:**
The analogy is `_parse_block` + `tokens = _SEP_RE.split(text)` in `srt.py` (lines 110–136): a linear scan with accumulated state. Phase-2 `batch_subdoc()` uses the same structure:
```python
@dataclass
class Batch:
    cues: list[SubLine] = field(default_factory=list)
    context_before: list[SubLine] = field(default_factory=list)  # read-only neighbor lines
    context_after: list[SubLine] = field(default_factory=list)

def batch_subdoc(doc: SubDoc, settings: "TrezarrSettings") -> list[Batch]:
    """Pack SubDoc into LLM-sized batches respecting scene gaps and token budget."""
    budget_chars = _compute_budget_chars(settings)
    batches: list[Batch] = []
    current: list[SubLine] = []
    current_chars = 0

    for i, cue in enumerate(doc.lines):
        gap_ms = _gap_ms(doc.lines[i - 1], cue) if i > 0 else 0
        at_scene_gap = gap_ms >= settings.translate_scene_gap_ms

        would_overflow = (
            current_chars + len(cue.text) > budget_chars
            or len(current) >= settings.translate_max_cues_per_batch
        )

        if current and (at_scene_gap or would_overflow):
            batches.append(_make_batch(current, doc.lines, i, settings))
            current = []
            current_chars = 0

        current.append(cue)
        current_chars += len(cue.text)

    if current:
        batches.append(_make_batch(current, doc.lines, len(doc.lines), settings))

    return batches
```

**Warning pattern — match `srt.py` `warnings.warn`** (`srt.py` lines 171–176):
```python
warnings.warn(
    f"batch_subdoc: single cue at index {i} exceeds token budget — "
    f"treating as one-cue batch (configure a larger llm_context_window)",
    UserWarning,
    stacklevel=2,
)
```

---

### `trezarr/translate/sentinel.py` (utility, transform)

**Analog:** `trezarr/subtitles/srt.py` (regex-extract pattern from `_TC_RE` + `_INDEX_RE`)

**Imports pattern:**
```python
from __future__ import annotations

import re
```

**Core sentinel pattern** (from RESEARCH.md Q4 code example):
```python
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\})')

def extract_sentinels(text: str) -> tuple[str, dict[str, str]]:
    """Replace inline tags with opaque <<TN>> tokens. Returns (cleaned_text, sentinel_map)."""
    sentinel_map: dict[str, str] = {}
    counter = 0

    def replacer(m: re.Match) -> str:
        nonlocal counter
        key = f"<<T{counter}>>"
        sentinel_map[key] = m.group(0)
        counter += 1
        return key

    cleaned = TAG_RE.sub(replacer, text)
    return cleaned, sentinel_map

def reinsert_sentinels(text: str, sentinel_map: dict[str, str]) -> tuple[str, bool]:
    """Restore tags from sentinel tokens. Returns (restored_text, integrity_ok)."""
    for key, original in sentinel_map.items():
        if key not in text:
            return text, False  # sentinel lost — gate will catch this
        text = text.replace(key, original, 1)
    # No orphan sentinels must remain
    if re.search(r'<<T\d+>>', text):
        return text, False
    return text, True
```

**Error handling pattern — return a boolean flag, not an exception** (mirrors `_parse_block`'s `raw=block` fallback in `srt.py` lines 176–189): integrity failures return `(text, False)` rather than raising, so the caller (engine.py's batch-level gate) decides whether to retry or quarantine. This matches the codec's philosophy of "flag and let the caller decide."

---

### `trezarr/translate/engine.py` (service, request-response async)

**Analog:** `trezarr/llm/client.py`

**Imports pattern** (`client.py` lines 17–27):
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
Phase-2 analog for `engine.py`:
```python
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from trezarr.llm.client import LLMClient
from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.subtitles.srt import read_srt
from trezarr.translate.batching import Batch, batch_subdoc
from trezarr.translate.sentinel import extract_sentinels, reinsert_sentinels
from trezarr.translate.validate import validate_subdoc
from trezarr.output.write import write_vi_sidecar
from trezarr.output.ledger import Ledger

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)
```

**Critical constraint: no second Semaphore** (`client.py` lines 55 and 88):
```python
# In LLMClient.__init__:
self._semaphore: asyncio.Semaphore = asyncio.Semaphore(settings.llm_max_concurrency)

# In LLMClient.call():
async with self._semaphore:  # D-06: enforce concurrency cap
    return await self._call_with_fallback(messages, response_model)
```
`engine.py` calls `await llm_client.call(messages)` directly. It must NOT create its own `asyncio.Semaphore` — the one inside `LLMClient` is the sole concurrency gate (Pitfall 1 in RESEARCH.md).

**Async gather pattern over batches** (mirrors `test_client_concurrency.py` lines 57):
```python
results = await asyncio.gather(
    *[_translate_batch(batch, llm_client, settings) for batch in batches]
)
```

**Tenacity retry pattern — ONLY on `BatchValidationError`, NOT on `openai.APIError`** (D-18, Pitfall 5):
```python
class BatchValidationError(Exception):
    """Raised when a translated batch fails the batch-level gate checks."""

@retry(
    retry=retry_if_exception_type(BatchValidationError),
    stop=stop_after_attempt(3),  # settings.translate_batch_retry_attempts + 1
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)
async def _translate_batch_with_retry(
    batch: Batch, llm_client: LLMClient, settings: "TrezarrSettings"
) -> list[str]:
    ...
```
The `retry_if_exception_type(BatchValidationError)` selector is the critical constraint — SDK transport errors (`openai.APIError`) must NOT be caught by tenacity; the SDK's own `max_retries` handles them (CLAUDE.md: "Do NOT wrap individual `create`/`parse` calls in tenacity").

**Entry point signature** (clean callable for Phase 3):
```python
@dataclass
class TranslationResult:
    status: str  # "done" | "skipped" | "quarantined"
    output_path: Path | None = None
    quarantine_path: Path | None = None
    reason: str | None = None

async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: Ledger,
) -> TranslationResult:
    ...
```

**Exception hierarchy — define at module top, match `client.py` clarity:**
```python
class BatchValidationError(Exception):
    """Batch-level gate failure — triggers tenacity retry."""

class TranslationError(Exception):
    """Whole-file translation failure — triggers quarantine."""
```

---

### `trezarr/translate/validate.py` (utility, transform)

**Analog:** `trezarr/subtitles/srt.py` (`_parse_block` assertion pattern + `UserWarning`)

**Imports pattern:**
```python
from __future__ import annotations

import re
from dataclasses import dataclass

from trezarr.subtitles.model import SubDoc
```

**Error class pattern — match `client.py` custom exceptions:**
```python
@dataclass
class GateFailure:
    check: int        # 1–7
    reason: str
    failing_indices: list[int] = None  # cue indices that failed, if applicable

class GateError(Exception):
    def __init__(self, failure: GateFailure) -> None:
        self.failure = failure
        super().__init__(failure.reason)
```

**Core 7-check gate pattern** (fail-fast, each check raises `GateError`):
```python
VN_DIACRITIC_RE = re.compile(r'[Ḁ-ỿ]')   # U+1E00-U+1EFF Latin Extended Additional
ALLOWLIST_RE = re.compile(r'^[\W\d\s♪♫…\.]+$')
SENTINEL_RE = re.compile(r'<<T\d+>>')

def validate_subdoc(
    translated: SubDoc,
    source: SubDoc,
    settings: "TrezarrSettings",
) -> None:
    """Run all 7 gate checks. Raises GateError on the first failure."""

    # Check 1: cue count
    if len(translated.lines) != len(source.lines):
        raise GateError(GateFailure(1, f"Cue count mismatch: {len(translated.lines)} != {len(source.lines)}"))

    # Check 2: no empty translated lines
    for i, sl in enumerate(translated.lines):
        if not sl.text.strip():
            raise GateError(GateFailure(2, f"Empty translated cue at index {i}", [i]))

    # Check 3: untranslated-line detection (two-tier)
    _check_untranslated(translated, source, settings)

    # Check 4: timecodes/indices byte-identical to source
    for i, (src, trn) in enumerate(zip(source.lines, translated.lines)):
        if src.index != trn.index or src.start_tc != trn.start_tc or src.end_tc != trn.end_tc:
            raise GateError(GateFailure(4, f"Timecode/index mutation at cue {i}", [i]))

    # Check 5: monotonic, non-overlapping timestamps
    _check_monotonic(translated)

    # Check 6: no orphan sentinel tokens
    for i, sl in enumerate(translated.lines):
        if SENTINEL_RE.search(sl.text):
            raise GateError(GateFailure(6, f"Orphan sentinel in cue {i}", [i]))

    # Check 7: all texts encode as valid UTF-8
    for i, sl in enumerate(translated.lines):
        try:
            sl.text.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise GateError(GateFailure(7, f"UTF-8 encode error at cue {i}: {exc}", [i]))
```

---

### `trezarr/output/write.py` (utility, file-I/O)

**Analog:** `trezarr/subtitles/srt.py` (`write_srt`, lines 218–248)

**Imports pattern** (`write_srt` analog):
```python
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from trezarr.subtitles.model import SubDoc
from trezarr.subtitles.srt import write_srt
```

**Core atomic-write pattern** — mirrors `write_srt`'s `Path(path).write_bytes(result.encode(doc.encoding))` but adds `NamedTemporaryFile` + `os.replace()`:
```python
_LANG_CODE_RE = re.compile(r'\.[a-z]{2}$', re.IGNORECASE)  # matches .en .ja .fr etc.

def write_vi_sidecar(doc: SubDoc, media_path: str | Path) -> Path:
    media_path = Path(media_path)
    stem = media_path.stem  # e.g. "Show.S01E01.en" from "Show.S01E01.en.srt"
    if _LANG_CODE_RE.search(stem):
        stem = stem.rsplit('.', 1)[0]  # strip language code suffix
    dest = media_path.parent / (stem + '.vi.srt')

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix='.tmp',
            dir=dest.parent,    # MUST be same filesystem as dest (Pitfall 3)
            delete=False,
        ) as f:
            tmp_path = Path(f.name)
        # Force UTF-8 output regardless of source encoding (D-19)
        doc_out = SubDoc(
            lines=doc.lines,
            encoding='utf-8',
            line_ending=doc.line_ending,
            separators=doc.separators,
            leading=doc.leading,
            trailer=doc.trailer,
        )
        write_srt(doc_out, tmp_path)          # reuse Phase-1 serialiser
        os.replace(tmp_path, dest)            # POSIX-atomic rename
        tmp_path = None
        return dest
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()                 # cleanup on any failure before os.replace
```

**Key constraint:** `dir=dest.parent` is mandatory. The `write_srt` call reuses the Phase-1 serialiser unchanged — the only difference is `encoding='utf-8'` is forced.

---

### `trezarr/output/ledger.py` (service, file-I/O)

**Analog:** `trezarr/subtitles/srt.py` (read_bytes + write_bytes pattern) + `trezarr/output/write.py` (same `os.replace` atomic pattern)

**Imports pattern:**
```python
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)
```

**Schema — Phase-4-compatible fields** (Q7 from RESEARCH.md):
```python
@dataclass
class LedgerEntry:
    source_path: str
    output_path: str | None
    status: Literal["done", "quarantined", "in_progress"]
    content_hash: str          # sha256[:16] of source bytes
    series_id: str | None = None
    source_lang: str | None = None
    episode_key: str | None = None
    translated_at: str | None = None
    quarantine_path: str | None = None
```

**Class interface — swap-compatible with Phase-4 SQLAlchemy backend:**
```python
class Ledger:
    def __init__(self, ledger_path: str | Path) -> None:
        self._path = Path(ledger_path)
        self._data: dict[str, LedgerEntry] = self._load()

    def _load(self) -> dict[str, LedgerEntry]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding='utf-8'))
            return {k: LedgerEntry(**v) for k, v in raw.items()}
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Ledger at %s is corrupt — starting fresh", self._path)
            return {}

    def check(self, source_path: str | Path) -> LedgerEntry | None:
        return self._data.get(str(source_path))

    def record(self, entry: LedgerEntry) -> None:
        self._data[entry.source_path] = entry
        self._write()

    def _write(self) -> None:
        # Same atomic write pattern as write_vi_sidecar
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', suffix='.tmp',
                dir=self._path.parent, delete=False,
            ) as f:
                tmp_path = Path(f.name)
                json.dump({k: asdict(v) for k, v in self._data.items()}, f, indent=2)
            os.replace(tmp_path, self._path)
            tmp_path = None
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    @staticmethod
    def content_hash(source_bytes: bytes) -> str:
        return hashlib.sha256(source_bytes).hexdigest()[:16]
```

---

### `trezarr/config.py` (extend existing — add Phase-2 fields)

**Analog:** Itself (`trezarr/config.py` lines 46–63 — existing field block pattern)

**Pattern for adding Phase-2 fields** — insert a new named section after `llm_context_window`, following the `# ── Section header (D-NN) ──` comment style already established:

```python
    # ── Context window (D-05 — used by Phase 2 batching) ──────────────────
    llm_context_window: int = 32768

    # ── Phase 2: Batching (D-14) ───────────────────────────────────────────
    translate_chars_per_token: float = 3.5
    translate_overhead_fraction: float = 0.30
    translate_output_expansion: float = 1.40
    translate_max_cues_per_batch: int = 50
    translate_scene_gap_ms: int = 2000

    # ── Phase 2: Context window (D-15) ─────────────────────────────────────
    translate_context_lines_k: int = 3

    # ── Phase 2: Retry + quarantine (D-18) ─────────────────────────────────
    translate_batch_retry_attempts: int = 2

    # ── Phase 2: Validation gate (D-17) ────────────────────────────────────
    translate_vi_diacritic_ratio: float = 0.70

    # ── Phase 2: Output paths (D-18, D-20) ─────────────────────────────────
    translate_quarantine_dir: str = "/config/quarantine"
    translate_ledger_path: str = "/config/processed_files.json"
```

No other changes to `config.py`. The `__init__`, `settings_customise_sources`, and `model_config` block are untouched.

---

## Shared Patterns

### `from __future__ import annotations` header
**Source:** Every Phase-1 source file (first line of `model.py`, `srt.py`, `client.py`, `config.py`)
**Apply to:** All Phase-2 source files (`batching.py`, `sentinel.py`, `engine.py`, `validate.py`, `write.py`, `ledger.py`)

```python
from __future__ import annotations
```

### Module docstring with design-decision references
**Source:** `trezarr/llm/client.py` lines 1–16 (lists `D-03`, `D-04`, etc.)
**Apply to:** All Phase-2 source files

```python
"""Short module description.

Design decisions honoured:
  D-12  <one line per decision implemented in this module>
  D-14  ...
"""
```

### Deferred imports in `if TYPE_CHECKING:` block
**Source:** `trezarr/llm/client.py` lines 25–27:
```python
if TYPE_CHECKING:
    from ..config import TrezarrSettings
```
**Apply to:** `batching.py`, `engine.py`, `validate.py` — any module that accepts `TrezarrSettings` as a type annotation but doesn't need it at runtime.

### Deferred imports inside test functions
**Source:** All test files (e.g. `test_client_tiers.py` line 29: `from trezarr.llm.client import LLMClient`; `test_srt_model.py` line 9: `from trezarr.subtitles.model import SubLine`)
**Apply to:** All Phase-2 test files — every `from trezarr.translate...` import goes inside the test function body, not at module top. This prevents collection errors when Phase-2 modules don't exist yet.

```python
async def test_something():
    from trezarr.translate.batching import batch_subdoc  # deferred import
    from trezarr.config import TrezarrSettings
    ...
```

### `pytest_configure` marker registration
**Source:** `tests/conftest.py` lines 10–15:
```python
def pytest_configure(config):
    config.addinivalue_line("markers", "live: ...")
```
**Apply to:** If Phase-2 tests add new markers (e.g. `slow`), register them in `tests/conftest.py` the same way.

### `settings_factory` fixture for test settings
**Source:** `tests/conftest.py` lines 18–43
**Apply to:** All Phase-2 async test functions that need `TrezarrSettings`. Use `settings_factory` from `conftest.py`; extend it with Phase-2 fields in the `defaults` dict override.

```python
async def test_batch_retry(settings_factory):
    from trezarr.translate.engine import translate_batch_with_retry

    settings = settings_factory(translate_batch_retry_attempts=1)
    ...
```

### `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed
**Source:** `pyproject.toml` line 21: `asyncio_mode = "auto"`
**Apply to:** All Phase-2 async test functions — `async def test_*()` functions are automatically collected. No decorator required (matches `test_client_tiers.py` which has no `@pytest.mark.asyncio`).

### `AsyncMock` + `patch.object` for LLMClient mocking
**Source:** `tests/llm/test_client_tiers.py` lines 40–43, 64–74:
```python
from unittest.mock import AsyncMock, MagicMock, patch

mock_parse = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=ok_msg)]))
with patch.object(client._client.chat.completions, "parse", mock_parse):
    await client.call([{"role": "user", "content": "test"}])
```
**Apply to:** `tests/translate/test_engine.py` — mock `LLMClient.call()` at the `engine.py` call site using `patch.object(llm_client, "call", AsyncMock(return_value="[1] Xin chào"))`.

### Atomic write: `NamedTemporaryFile(dir=dest.parent)` + `os.replace()`
**Source:** RESEARCH.md Q6 pattern; `write_srt` in `srt.py` line 248 (`Path(path).write_bytes(...)`)
**Apply to:** `trezarr/output/write.py` and `trezarr/output/ledger.py._write()` — both file writes use the same `NamedTemporaryFile(dir=dest.parent, delete=False)` + `os.replace()` + `finally: tmp_path.unlink()` structure.

### `UserWarning` for non-fatal anomalies (not exceptions)
**Source:** `trezarr/subtitles/srt.py` lines 171–176 and 182–189:
```python
warnings.warn(
    f"read_srt: malformed SRT block ... — preserving verbatim:\n{block!r}",
    UserWarning,
    stacklevel=3,
)
```
**Apply to:** `trezarr/translate/batching.py` — warn (not raise) when a single cue exceeds the token budget. The cue is emitted as a one-cue batch rather than crashing.

### New `SubLine` construction (never mutate source lines)
**Source:** RESEARCH.md Pitfall 8; `model.py` lines 17–45 (`@dataclass` with mutable `text`)
**Apply to:** `trezarr/translate/engine.py` — when assembling the translated `SubDoc`, always construct fresh `SubLine` objects:
```python
translated_line = SubLine(
    index=src.index,
    start_tc=src.start_tc,
    end_tc=src.end_tc,
    text=translated_text,
    # raw stays None — well-formed translated cue
)
```
Never write `src.text = translated_text` — that mutates the source `SubDoc` and breaks gate check 4.

---

## Test Patterns

### Test for pure-Python utilities (`test_batching.py`, `test_validate.py`, `test_sentinel.py`)
**Analog:** `tests/codec/test_srt_model.py`

Pattern: synchronous `def test_*()` functions; construct `SubLine`/`SubDoc` inline (no fixtures); assert on return values or caught exceptions.

```python
def test_gate_count_mismatch():
    from trezarr.subtitles.model import SubDoc, SubLine
    from trezarr.translate.validate import GateError, validate_subdoc
    from trezarr.config import TrezarrSettings

    src = SubDoc(lines=[_make_line(1), _make_line(2)], encoding='utf-8', line_ending='\n', separators=['\n\n'])
    trn = SubDoc(lines=[_make_line(1)], encoding='utf-8', line_ending='\n', separators=[])  # one line dropped

    with pytest.raises(GateError) as exc_info:
        validate_subdoc(trn, src, TrezarrSettings(llm_base_url="x", llm_api_key="k"))
    assert exc_info.value.failure.check == 1
```

### Test for async engine functions (`test_engine.py`)
**Analog:** `tests/llm/test_client_tiers.py` + `tests/llm/test_client_concurrency.py`

Pattern: `async def test_*()` with `AsyncMock` + `patch.object`; uses `settings_factory` fixture.

```python
async def test_batch_retry(settings_factory):
    from unittest.mock import AsyncMock, patch
    from trezarr.llm.client import LLMClient
    from trezarr.translate.engine import _translate_batch, BatchValidationError

    settings = settings_factory(translate_batch_retry_attempts=2)
    client = LLMClient(settings)

    call_count = 0
    async def _fake_call(messages):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return "[1] "  # empty line — triggers BatchValidationError
        return "[1] Xin chào\n[2] Tôi đến đây"

    with patch.object(client, "call", side_effect=_fake_call):
        result = await _translate_batch(batch, client, settings)

    assert call_count == 2
    assert result[0] == "Xin chào"
```

### Test for file I/O (`test_write.py`, `test_ledger.py`)
**Analog:** `tests/codec/test_srt_roundtrip.py` (uses `tmp_path` pytest fixture)

Pattern: use `tmp_path` (pytest built-in) for temp directories; assert on file existence, content, and naming.

```python
def test_sidecar_naming(tmp_path):
    from trezarr.output.write import write_vi_sidecar

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding='utf-8')
    doc = read_srt(src)
    # translate doc.lines[0].text ...
    dest = write_vi_sidecar(doc, src)
    assert dest == tmp_path / "Show.S01E01.vi.srt"
    assert dest.exists()
```

---

## No Analog Found

All Phase-2 files have analogs in the Phase-1 codebase. No file requires falling back to RESEARCH.md patterns exclusively.

| File | Closest Analog | Note |
|------|---------------|-------|
| `trezarr/translate/sentinel.py` | `trezarr/subtitles/srt.py` | Regex-extract pattern is analogous; `TAG_RE` mirrors `_TC_RE`/`_INDEX_RE` style |
| `trezarr/output/ledger.py` | `trezarr/subtitles/srt.py` + `write.py` | Atomic JSON write is structurally identical to atomic SRT write |

---

## Metadata

**Analog search scope:** `trezarr/` (all packages), `tests/` (all subdirectories)
**Files scanned:** 10 source files, 9 test files
**Pattern extraction date:** 2026-05-31

**Critical constraints carried forward from Phase-1 analogs:**
1. `_TC_RE` in `srt.py` — reuse this regex (or its pattern) in `batching.py` for timecode-to-ms conversion; do not re-invent
2. `LLMClient._semaphore` is the sole concurrency gate — `engine.py` must not create a second `asyncio.Semaphore`
3. `tenacity` at `engine.py` pipeline level only — `retry_if_exception_type(BatchValidationError)`, never `openai.APIError`
4. New `SubLine(index=src.index, start_tc=src.start_tc, end_tc=src.end_tc, text=...)` — never `src.text = ...`
5. `NamedTemporaryFile(dir=dest.parent, delete=False)` + `os.replace()` + `finally: unlink` — both `write.py` and `ledger.py`
6. `asyncio_mode = "auto"` is set — no `@pytest.mark.asyncio` in test functions
7. All imports inside test functions are deferred (`from trezarr... import ...` inside the `def test_*()` body)
