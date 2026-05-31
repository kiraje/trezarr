# Phase 3: *arr Integration + First Vertical Slice - Research

**Researched:** 2026-05-31
**Domain:** pyarr *arr API client, path-mapping layer, filesystem source-sub discovery, PUID/PGID/UMASK permission application, one-shot CLI wiring
**Confidence:** HIGH (pyarr API shape: MEDIUM-HIGH from official docs; Sonarr/Radarr response fields: HIGH from golift/starr Go library cross-reference; permissions mechanics: HIGH from Python stdlib; path-mapping algorithm: MEDIUM-HIGH from TRaSH guide description)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-21:** One-shot CLI run (`trezarr run --once`). No daemon, scheduler, webhook, or watcher — Phase 7.
- **D-22:** Discover via pyarr, Sonarr + Radarr both. X-Api-Key auth, `/api/v3`. Never scan disk to discover. Drop to httpx only for a specific endpoint pyarr lacks.
- **D-23:** Path mapping = ordered remote→local find/replace pairs. Longest-prefix / first-match applied to every API-returned path before filesystem use.
- **D-24:** Fail-fast startup readability probe. Any unreadable configured local media root → refuse to start (exit non-zero), clear actionable error.
- **D-25:** Filesystem source-sub scan with source-language priority list, default `["en"]` (configurable). First match in priority order wins. No Bazarr dep.
- **D-26:** Gap detection = source sub exists AND no honored `vi` sidecar. Foreign `vi` sub → skip + log, never clobber.
- **D-27:** Extend ledger with source-subtitle content hash. Schema additive only, stays Phase-4 `processed_file`-compatible.
- **D-28:** Self-output exclusion via ledger provenance.
- **D-29:** Apply configured PUID/PGID/UMASK in-process via `os.chown`/`os.chmod` after each write. Constrain writes to media roots (path-traversal guard). Real s6/container init is Phase 7.
- **D-30:** Batch-run semantics: per-item quarantine on failure, run continues, end summary (translated/skipped/quarantined/failed counts), non-zero exit if any failed.

### Claude's Discretion

- Exact module/package layout (`trezarr/arr/`, `trezarr/discover/`, `trezarr/cli.py`, `trezarr/paths.py`)
- CLI framework (argparse / typer / click)
- Sequential vs bounded-concurrency per-item translate (respecting the existing LLM semaphore)
- Hash algorithm for source sub (reuse Phase-2 `Ledger.content_hash`)
- Exact new `TrezarrSettings` field names for *arr URLs/keys, path mappings, source-lang priority, PUID/PGID/UMASK
- Ledger-extension storage shape (JSON field add vs. tiny SQLite seam)
- chown failure degrade strategy (log-and-continue vs. surface)

### Deferred Ideas (OUT OF SCOPE)

- Daemon / APScheduler poll loop, FastAPI webhook receiver, `watchfiles` watcher → Phase 7
- Bazarr API source-sub discovery → INTG-02 / Phase 10
- Docker image, s6-overlay, true drop-privileges → Phase 7
- Tag/monitored-status/series include-exclude filtering UI → Phase 10
- Qualitative "is the existing vi sub good enough" judgement → later
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTG-01 | Trezarr connects to Sonarr and Radarr via REST APIs (API-key auth) to discover media identity, file paths, and metadata | pyarr 6.x `Sonarr`/`Radarr` composition API; golift struct cross-reference for `path` field shapes |
| INTG-03 | User can configure container↔host path mapping | TRaSH-guide find/replace model; longest-prefix algorithm; startup readability probe (D-23, D-24) |
| INTG-04 | Read source subtitle files and write Vietnamese sidecar files with correct permissions | `os.chown`/`os.chmod`/umask mechanics; wrap existing `write_vi_sidecar()`; constrain to media roots |
| AUTO-01 | Automatically detect media with source sub but no good Vietnamese sub and queue for translation | Filesystem glob of source-lang sidecars; gap detection using `derive_vi_sidecar_path()` + ledger provenance |
| AUTO-03 | Idempotency — track per-item state including source-sub hash, skip items already up to date | Extend `LedgerEntry` with `source_sub_hash` field; reuse `Ledger.content_hash()` |
| AUTO-04 | Exclude own output from re-triggering (no self-reprocessing loop) | Ledger provenance already exists in Phase 2; gap detection checks ledger before selecting eligible items |
</phase_requirements>

---

## Summary

Phase 3 wraps the Phase-2 `translate_file()` pipeline with the real discovery and I/O shell that makes Trezarr an *arr companion: pyarr fetches the media library, a path-mapping layer resolves API-reported paths to local filesystem paths, a gap-detection scan finds eligible items (source sub present, no honored vi sidecar), and each item is translated and written with correct PUID/PGID/UMASK ownership. The whole flow is driven by a one-shot CLI entry point (`trezarr run --once`).

The four areas that need concrete prescriptions are:
1. **pyarr 6.x composition API** — the class and access pattern changed significantly from the older `SonarrAPI` style. The new API is `Sonarr(host, api_key, port)` with submodule access (`client.series.get()`, `client.episode_file.get(series_id=X)`). The response JSON field names (`path`, `seriesId`, `monitored`, `hasFile`) are verified against the golift/starr Go struct cross-reference (the most complete response schema available publicly).
2. **Path-mapping algorithm** — TRaSH guides describe it as a simple find/replace with no sophisticated matching; applying longest-prefix-first is the safe, deterministic choice. Trailing-slash normalization and path-traversal guard (resolved path must be inside a configured media root) are essential defensive layers.
3. **Permissions** — `os.chown` raises `PermissionError` (errno EPERM) when the process UID has no privilege to set ownership to a different user; the prescribed degrade strategy is log-and-continue (write still succeeds, just not with correct ownership) since the write itself is what matters for correctness and s6 init will fix ownership in Phase 7.
4. **CLI framework** — argparse is the right choice here: it is already in the stdlib (zero new dep), adequate for a single `run --once` command with a handful of flags, and Phase 3 is not building a rich multi-command tool (that is Phase 7's FastAPI + CLI).

**Primary recommendation:** New modules `trezarr/arr/` (pyarr wrappers), `trezarr/paths.py` (path-mapping layer + startup probe), `trezarr/discover/` (source-sub scan + gap detection), `trezarr/cli.py` (argparse entry point). Extend `LedgerEntry` with `source_sub_hash: str | None = None`. Add ~7 new settings fields to `TrezarrSettings`. Test with `pytest-httpx` for pyarr HTTP mocking; parametrize path-mapping and gap-detection tests deterministically with `tmp_path`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Media library discovery (series/episodes/movies) | API client (`trezarr/arr/`) | — | "API for knowledge" — Sonarr/Radarr own the media manifest; never scan disk |
| Path resolution (API path → local filesystem path) | Path-mapping layer (`trezarr/paths.py`) | — | Single choke-point; every API path must pass through this before any filesystem op |
| Startup readability probe | Path-mapping layer (`trezarr/paths.py`) | CLI entry point | Probe at startup; CLI calls it before entering the main loop |
| Source-sub filesystem scan | Discovery layer (`trezarr/discover/`) | — | Filesystem for action — find the actual sidecar files next to the resolved media path |
| Gap detection (eligible item decision) | Discovery layer (`trezarr/discover/`) | Ledger | Reads ledger provenance + filesystem state; pure decision function |
| Per-item translation | Phase-2 engine (`trezarr/translate/engine.py`) | — | Reuse unchanged; CLI calls `translate_file()` per eligible item |
| Permission-correct write (chown/chmod/umask) | Write layer (`trezarr/output/write.py`) | — | Wrap `write_vi_sidecar()` with a `apply_permissions()` post-write step |
| Batch orchestration + summary + exit code | CLI entry point (`trezarr/cli.py`) | — | One-shot loop; accumulates counts; non-zero exit on any failure |
| Idempotency state | Ledger (`trezarr/output/ledger.py`) | — | Extend with `source_sub_hash`; Phase-2's existing contract carries forward |
| Configuration | `trezarr/config.py` (`TrezarrSettings`) | — | Add *arr URLs/keys, path_mappings, source_lang_priority, PUID/PGID/UMASK fields |

---

## Standard Stack

### Core (already in pyproject.toml — no new installs required for runtime)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `argparse` | 3.12 | CLI entry point (`trezarr run --once`) | Zero dependency; adequate for a single command; richer CLI frameworks deferred to Phase 7 FastAPI |
| Python stdlib `os`, `pathlib` | 3.12 | `os.chown`, `os.chmod`, `os.umask`, `Path.glob` | Direct stdlib for permissions and filesystem ops; no extra dep needed |
| `pydantic-settings` | 2.14.x (already installed) | New config fields (arr URLs/keys, path mappings, source-lang priority, PUID/PGID/UMASK) | Consistent with existing `TrezarrSettings` layered config |

### New Runtime Dependency

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyarr` | 6.6.0 | Sonarr + Radarr API client; `Sonarr`/`Radarr` classes with composition API | Canonical *arr Python client; X-Api-Key auth, JSON results, Python >=3.12 required; both sync and async variants |

**Version verification (live 2026-05-31):** `pyarr 6.6.0` on PyPI, `requires_python: >=3.12`. [VERIFIED: PyPI JSON API]

### New Dev Dependency

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-httpx` | 0.36.2 | Mock pyarr's underlying httpx requests in unit tests | Testing pyarr discovery calls without a live Sonarr/Radarr |

**Version verification (live 2026-05-31):** `pytest-httpx 0.36.2` on PyPI. [VERIFIED: PyPI JSON API]

`respx` (0.23.1) is an alternative to `pytest-httpx` — either works. `pytest-httpx` is prescribed because pyarr uses `httpx` internally and `pytest-httpx` integrates at the httpx transport layer without needing to know pyarr internals.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `argparse` | `typer` (type-hint-driven CLI) | Typer is cleaner but adds a dep and is overkill for one command; save for Phase 7 FastAPI CLI |
| `argparse` | `click` | Well-established, but same overkill argument; stdlib is enough here |
| `pytest-httpx` | `respx` | Functionally equivalent; `pytest-httpx` is slightly more automatic for httpx-backed clients |

**Installation (new packages only):**
```bash
uv add pyarr
uv add --dev pytest-httpx
```

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pyarr` | PyPI | ~4+ yrs | moderate (self-hosted tools niche) | github.com/totaldebug/pyarr | [OK] | Approved |
| `pytest-httpx` | PyPI | ~5+ yrs | 7.5M/month | github.com/Colin-b/pytest_httpx | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

slopcheck confirmed `[OK]` for all three candidates (`pyarr`, `pytest-httpx`, `respx`) via `~/.local/bin/slopcheck install pyarr pytest-httpx respx`. All packages verified on PyPI with legitimate source repositories. [VERIFIED: slopcheck, PyPI JSON API, github.com/totaldebug/pyarr, github.com/Colin-b/pytest_httpx]

---

## Architecture Patterns

### System Architecture Diagram

```
trezarr run --once
        │
        ▼ 1. Load TrezarrSettings (env / YAML)
        │
        ▼ 2. Startup probe: verify each local media root is readable
        │    → unreadable root → exit(1) + clear error (D-24)
        │
        ▼ 3. arr Discovery (trezarr/arr/)
        │    Sonarr.series.get() → all monitored series
        │    Sonarr.episode_file.get(series_id=X) → episode file paths
        │    Radarr.movie.get() → all monitored movies with movie_file.path
        │
        ▼ 4. Path mapping (trezarr/paths.py)
        │    For each API-returned path:
        │      apply_path_mapping(api_path, settings.path_mappings) → local_path
        │
        ▼ 5. Source-sub scan + Gap detection (trezarr/discover/)
        │    next to resolved media dir:
        │      find_source_sub(media_stem, lang_priority) → source_sub_path | None
        │    gap check:
        │      has_source AND NOT honored_vi → eligible
        │
        ▼ 6. Per-item translate (for each eligible item)
        │    translate_file(source_sub_path, settings, llm_client, ledger)
        │    → TranslationResult(status, output_path, ...)
        │    → apply_permissions(output_path, puid, pgid, umask) [D-29]
        │
        ▼ 7. End summary + exit code (D-30)
             print(f"Translated: {n_done}, Skipped: {n_skip}, Quarantined: {n_quar}, Failed: {n_fail}")
             sys.exit(0 if n_fail == 0 and n_quar == 0 else 1)
```

### Recommended Project Structure (new modules only)

```
trezarr/
├── arr/                        # pyarr wrappers — *arr API clients
│   ├── __init__.py
│   ├── sonarr.py               # build_sonarr_client(), discover_sonarr_items()
│   └── radarr.py               # build_radarr_client(), discover_radarr_items()
├── discover/                   # Source-sub discovery + gap detection
│   ├── __init__.py
│   ├── scan.py                 # find_source_sub(), scan_for_eligible_items()
│   └── gap.py                  # is_eligible(), classify_vi_sidecar() (foreign/ours/absent)
├── paths.py                    # Path-mapping layer + startup probe + traversal guard
├── cli.py                      # argparse entry point: trezarr run --once
└── config.py                   # (extend) new TrezarrSettings fields
```

Tests:
```
tests/
├── arr/
│   ├── __init__.py
│   └── test_arr_discovery.py   # pytest-httpx mocked Sonarr/Radarr
├── discover/
│   ├── __init__.py
│   └── test_scan.py            # tmp_path filesystem stubs
└── test_paths.py               # path-mapping algorithm + traversal guard
```

### Pattern 1: pyarr 6.x Composition API

**What:** pyarr 6.x uses a composition-based design — a `Sonarr(host, api_key, port)` client with submodule attributes rather than a flat class with all methods. The old `SonarrAPI` class documented in some older references does not exist in 6.x.

**Key change from 5.x:** `SonarrAPI(host_url, api_key)` → `Sonarr(host, api_key, port=8989)` with access via `client.series.get()`, `client.episode_file.get(series_id=X)`.

**Example — Sonarr discovery:**
```python
# Source: docs.totaldebug.uk/pyarr/modules/sonarr.html [VERIFIED: official pyarr docs]
from pyarr import Sonarr

sonarr = Sonarr(
    host=settings.sonarr_host,    # e.g. "192.168.1.10"
    api_key=settings.sonarr_api_key.get_secret_value(),
    port=settings.sonarr_port,    # default 8989
    tls=False,                     # set True if using https
)

# All monitored series — returns list[dict]
all_series: list[dict] = sonarr.series.get()
# Each dict has keys: id, title, path, monitored, tvdbId, ...

# Episode files for one series — returns list[dict]
ep_files: list[dict] = sonarr.episode_file.get(series_id=series["id"])
# Each dict has keys: id, seriesId, seasonNumber, path, relativePath, ...
```

**Example — Radarr discovery:**
```python
# Source: docs.totaldebug.uk/pyarr/modules/radarr.html [VERIFIED: official pyarr docs]
from pyarr import Radarr

radarr = Radarr(
    host=settings.radarr_host,
    api_key=settings.radarr_api_key.get_secret_value(),
    port=settings.radarr_port,   # default 7878
)

# All movies — returns list[dict]
# Each dict has keys: id, title, path, monitored, movieFileId, movieFile (nested), ...
all_movies: list[dict] = radarr.movie.get()

# A movie dict looks like:
# { "id": 1, "title": "Parasite", "path": "/movies/Parasite (2019)",
#   "monitored": True, "movieFileId": 42,
#   "movieFile": { "id": 42, "movieId": 1, "path": "/movies/Parasite (2019)/Parasite.mkv",
#                  "relativePath": "Parasite.mkv", ... } }
```

**Async variant:** `AsyncSonarr` / `AsyncRadarr` — identical API, all methods are coroutines. For Phase 3's one-shot CLI, sync variants are fine (no event loop overhead). Phase 7's FastAPI lifespan should use the async variants.

**Error handling:** pyarr raises `httpx.HTTPStatusError` on 4xx/5xx. Wrap in try/except at the client-construction/probe call layer. Timeout behavior is controlled by `request_timeout` constructor parameter. [ASSUMED — not explicitly documented in the pyarr 6.x docs page retrieved]

### Pattern 2: Sonarr/Radarr Response Field Shapes

**Sonarr EpisodeFile response** (from golift/starr Go struct cross-reference): [VERIFIED: pkg.go.dev/golift.io/starr/sonarr]

```json
{
  "id": 123,
  "seriesId": 1,
  "seasonNumber": 1,
  "relativePath": "Season 1/Show.S01E01.mkv",
  "path": "/tv/Show/Season 1/Show.S01E01.mkv",
  "size": 2147483648,
  "dateAdded": "2023-01-01T00:00:00Z",
  "language": {"id": 1, "name": "English"},
  "quality": {...},
  "qualityCutoffNotMet": false
}
```

The `path` field is the **full absolute path as Sonarr sees it** — this is what path-mapping is applied to.

**Sonarr Series response** key fields:
- `id` (int) — Sonarr internal ID
- `title` (str) — series title
- `path` (str) — series directory (e.g. `/tv/Breaking Bad`)
- `monitored` (bool) — filter to only process monitored series
- `tvdbId` (int) — TVDB ID for metadata lookups

**Radarr Movie response** key fields:
- `id` (int) — Radarr internal ID
- `title` (str)
- `path` (str) — movie directory (e.g. `/movies/Parasite (2019)`)
- `monitored` (bool)
- `movieFileId` (int) — 0 if no file exists
- `movieFile` (nested object, present only when file exists):
  - `path` (str) — full path to the video file
  - `relativePath` (str) — relative to movie directory [VERIFIED: golift/starr Go struct]

**Discovery strategy:** For Sonarr, iterate series → for each monitored series, get `episode_file.get(series_id=X)` to get individual episode paths. For Radarr, `movie.get()` returns the `movieFile.path` embedded in each movie dict.

### Pattern 3: Path-Mapping Algorithm

**What:** An ordered list of `{remote: str, local: str}` pairs. For each API-returned path, find the first pair whose `remote` is a prefix of the path, strip it, prepend `local`.

**Algorithm (prescriptive):**
```python
# Source: TRaSH guides description + standard *arr community pattern [CITED: trash-guides.info]
# trezarr/paths.py

from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from typing import Sequence

@dataclass
class PathMapping:
    remote: str   # e.g. "/tv"
    local: str    # e.g. "/data/media/tv"


def apply_path_mapping(api_path: str, mappings: Sequence[PathMapping]) -> Path:
    """Apply ordered remote→local path mappings to an API-returned path.

    Tries each mapping in order (longest-remote-prefix wins among equally long
    leading matches by iteration order). Returns the path unchanged (as Path)
    if no mapping matches — the startup probe will have already surfaced
    unresolvable paths.

    Path-traversal guard: caller must verify the resolved path is inside a
    configured media root.
    """
    # Normalize: ensure both use forward slashes, strip trailing slashes
    normalized = api_path.rstrip("/")
    for mapping in mappings:
        remote = mapping.remote.rstrip("/")
        if normalized.startswith(remote):
            suffix = normalized[len(remote):]
            local_root = mapping.local.rstrip("/")
            return Path(local_root + suffix)
    return Path(api_path)   # no mapping matched — may be already local
```

**Longest-prefix matching:** The TRaSH guide describes the mapping as a "dumb find/replace" — it applies the first matching prefix. To get longest-prefix semantics, sort mappings by descending `len(remote)` before the loop, or trust the user to order them correctly (the *arr convention is user-ordered). **Recommendation:** Sort by descending length at settings load time so shorter prefixes can never shadow longer ones. [ASSUMED — TRaSH guide does not specify sorting; this is the safe defensive choice]

**Normalization rules:**
- Strip trailing slashes on both `remote` and the API path before comparison (the *arr APIs sometimes include them, sometimes don't)
- Do not lowercase (Linux filesystems are case-sensitive; don't normalize case)
- Windows UNC paths (`\\server\share\`) are out of scope for Phase 3 (self-hosted Linux containers)

**Path-traversal guard (D-29):**
```python
def assert_within_media_roots(resolved: Path, media_roots: Sequence[Path]) -> None:
    """Raise ValueError if resolved path escapes all configured media roots."""
    resolved_abs = resolved.resolve()
    for root in media_roots:
        try:
            resolved_abs.relative_to(root.resolve())
            return  # inside this root — OK
        except ValueError:
            continue
    raise ValueError(
        f"Resolved path {resolved_abs} is outside all configured media roots {media_roots}. "
        "This may indicate a path-mapping misconfiguration or path-traversal attempt."
    )
```

### Pattern 4: Startup Readability Probe (D-24)

**What:** At startup, before any discovery API call, verify each configured local media root exists and is readable.

```python
# trezarr/paths.py — called from cli.py before main loop
def probe_media_roots(media_roots: Sequence[Path]) -> None:
    """Verify each configured media root is readable. Raises SystemExit on failure."""
    import sys
    errors = []
    for root in media_roots:
        if not root.exists():
            errors.append(f"  {root}: does not exist")
        elif not root.is_dir():
            errors.append(f"  {root}: not a directory")
        elif not os.access(root, os.R_OK):
            errors.append(f"  {root}: not readable (check PUID/PGID or volume mount)")
    if errors:
        sys.exit(
            "ERROR: Trezarr cannot start — unreadable media root(s):\n"
            + "\n".join(errors)
            + "\nVerify your path_mappings and volume mounts match the *arr stack."
        )
```

**Media roots derivation:** The media roots to probe are the `local` side of every path mapping plus any explicitly configured `media_roots` setting. [ASSUMED — exact field name is Claude's discretion]

### Pattern 5: Source-Sub Discovery (D-25, D-26)

**What:** Given a resolved media file path (e.g. `/data/tv/Show/S1/Show.S01E01.mkv`), derive the media stem (`Show.S01E01`) and look for language-specific subtitle sidecars next to it.

**Sidecar naming convention** (from Plex naming rules and Phase-2 `write_vi_sidecar()`):
- Pattern: `{media_stem}.{lang}.srt` — e.g. `Show.S01E01.en.srt`
- Also handles no-lang-code variant: `Show.S01E01.srt` (treated as first-priority match if source_lang_priority includes "")

```python
# trezarr/discover/scan.py
import re
from pathlib import Path

_LANG_SIDECAR_RE = re.compile(r'^(.+?)\.([a-z]{2,3})\.srt$', re.IGNORECASE)

def find_source_sub(
    media_path: Path,
    lang_priority: list[str],  # e.g. ["en", "zh", "ko"]
) -> tuple[Path, str] | None:
    """Find best source subtitle next to a media file per language priority.

    Returns (sub_path, lang_code) for the highest-priority language match,
    or None if no matching subtitle is found.
    """
    media_dir = media_path.parent
    # Derive stem: strip the video extension from the media filename
    # e.g. "Show.S01E01.mkv" → "Show.S01E01"
    media_stem = media_path.stem

    # Build a lookup: lang_code → path
    found: dict[str, Path] = {}
    for candidate in media_dir.glob(f"{media_stem}.*.srt"):
        m = _LANG_SIDECAR_RE.match(candidate.name)
        if m and m.group(1) == media_stem:
            lang = m.group(2).lower()
            found[lang] = candidate

    # Apply priority order: first match in lang_priority wins
    for lang in lang_priority:
        if lang in found:
            return found[lang], lang

    return None
```

**Gap detection (D-26):**
```python
# trezarr/discover/gap.py
from pathlib import Path
from trezarr.output.ledger import Ledger
from trezarr.output.write import derive_vi_sidecar_path

def is_eligible(
    source_sub_path: Path,
    media_path: Path,   # resolved video path (used to derive vi sidecar path)
    ledger: Ledger,
) -> tuple[bool, str]:
    """Return (eligible, reason) for a candidate source subtitle.

    Logic (D-26, D-20):
      - source sub NOT found → not eligible
      - vi sidecar absent AND not in ledger → eligible
      - vi sidecar present AND in ledger as 'done' with matching source hash → skip (already done)
      - vi sidecar present AND NOT in ledger → foreign vi sub → skip + log (never clobber)
      - ledger entry present with status 'quarantined' → eligible (retry)
    """
    vi_path = derive_vi_sidecar_path(source_sub_path)
    entry = ledger.check(str(source_sub_path))

    if vi_path.exists() and entry is None:
        # Foreign vi sidecar — not ours; D-26 "never clobber"
        return False, f"foreign vi sidecar at {vi_path} — not ours, skipping"

    if entry is not None and entry.status == "done" and vi_path.exists():
        # Already done — check source hash
        source_bytes = source_sub_path.read_bytes()
        source_hash = Ledger.content_hash(source_bytes)
        if entry.content_hash == source_hash:
            return False, "already translated (source unchanged)"
        # Source changed → re-translate
        return True, "source subtitle changed — re-translating"

    if entry is not None and entry.status == "quarantined":
        return True, "retrying previously quarantined item"

    # Not in ledger (or in_progress from crashed run) → eligible
    return True, "new item"
```

**Note on derive_vi_sidecar_path vs media_path:** Phase 2's `derive_vi_sidecar_path()` takes a source SRT path and derives the `vi` output path. For gap detection, pass the `source_sub_path`, not the media video path. The derived vi path will be next to the subtitle, which is next to the media — correct.

### Pattern 6: Ledger Extension for D-27 (Source-Sub Hash)

The Phase-2 `LedgerEntry` already has `content_hash` — this is the **source subtitle content hash** (SHA-256[:16] of source bytes). The decision (D-27) is to explicitly ensure this is populated and documented as the source-sub hash (not the vi-sidecar hash).

**Current `LedgerEntry` field `content_hash`** already serves as the source-sub hash — `translate_file()` computes it from `source_bytes = path.read_bytes()` where `path` is the source sub. No new field is strictly required.

**However, D-27 says "extend the ledger"** — the extension needed is a semantics clarification + ensuring the hash is populated in the discovery path's gap-detection call (before `translate_file()` is called). The gap-detection code in Pattern 5 already reads and hashes the source sub for comparison.

**Recommendation (Claude's discretion):** Add `source_sub_hash: str | None = None` as an alias/explicit field on `LedgerEntry` to make the intent clear in Phase-4 schema-compatible form, even if it duplicates `content_hash` initially. Alternatively, just document that `content_hash` IS the source-sub hash and requires no new field — cleaner. Either works; planner should pick one and stay consistent.

### Pattern 7: Permission Application (D-29)

**What:** After `write_vi_sidecar()` returns successfully, apply PUID/PGID/UMASK.

```python
# trezarr/output/write.py — new helper to add after write_vi_sidecar()
import os
import logging
import stat

logger = logging.getLogger(__name__)

def apply_permissions(path: Path, puid: int, pgid: int, umask: int) -> None:
    """Apply PUID/PGID ownership and UMASK-derived permissions to a written sidecar.

    os.chown raises PermissionError (EPERM) when the process does not have CAP_CHOWN
    (i.e. running as non-root without capability). This is expected in Phase 3 (no
    container init yet) — log a warning and continue. The write succeeded; s6-overlay
    in Phase 7 will fix ownership at container startup.

    umask is applied as: file_mode = 0o666 & ~umask  (standard POSIX convention)
    e.g. umask=0o022 → file_mode=0o644 (owner rw, group r, world r)
    """
    # Apply ownership
    try:
        os.chown(path, puid, pgid)
    except PermissionError:
        logger.warning(
            "chown(%s, %d, %d) failed — process lacks CAP_CHOWN. "
            "File was written but ownership is not yet corrected. "
            "Phase 7 container init (s6-overlay) will fix this.",
            path, puid, pgid,
        )
    except OSError as exc:
        logger.warning("chown(%s) failed with unexpected error: %s", path, exc)

    # Apply permissions (chmod)
    file_mode = 0o666 & ~umask
    try:
        os.chmod(path, file_mode)
    except OSError as exc:
        logger.warning("chmod(%s, %o) failed: %s", path, file_mode, exc)
```

**UMASK note:** Standard POSIX umask convention: `file_mode = 0o666 & ~umask`. For umask `0o022`, result is `0o644` (rw-r--r--). The umask is NOT applied to the process via `os.umask()` (that would be process-global and race-prone in async code); instead compute the desired mode explicitly and pass to `chmod`. [ASSUMED — best practice; Python docs confirm `os.chmod` with explicit mode is the correct approach]

**PUID/PGID values of -1:** `os.chown(path, -1, -1)` is a no-op (POSIX convention for "leave unchanged"). When `puid` or `pgid` is not configured (settings default), use -1 to skip chown without error. [CITED: Python docs `os.chown`]

### Pattern 8: CLI Entry Point (D-21, D-30)

**What:** `trezarr run --once` — single argparse command, minimal flags.

```python
# trezarr/cli.py
import argparse
import asyncio
import logging
import sys

from trezarr.config import TrezarrSettings
from trezarr.llm.client import LLMClient
from trezarr.output.ledger import Ledger
from trezarr.paths import probe_media_roots, build_media_roots
from trezarr.arr.sonarr import discover_sonarr_items
from trezarr.arr.radarr import discover_radarr_items
from trezarr.discover.scan import find_eligible_items
from trezarr.translate.engine import translate_file
from trezarr.output.write import apply_permissions

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="trezarr", description="Automated Vietnamese subtitle translator")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Run translation pass")
    run_parser.add_argument("--once", action="store_true", required=True, help="One-shot scan and exit")
    run_parser.add_argument("--config", default=None, help="Path to config YAML (overrides TREZARR_CONFIG_PATH)")
    args = parser.parse_args()

    if args.command == "run" and args.once:
        asyncio.run(_run_once(args.config))


async def _run_once(config_path: str | None) -> None:
    settings = TrezarrSettings(_yaml_file=config_path)
    logging.basicConfig(level=logging.INFO)

    # Startup probe (D-24)
    media_roots = build_media_roots(settings)
    probe_media_roots(media_roots)

    # Discovery
    items = []
    items.extend(await discover_sonarr_items(settings))
    items.extend(await discover_radarr_items(settings))

    ledger = Ledger(settings.translate_ledger_path)
    llm_client = LLMClient(settings)

    # Per-item translate with per-item quarantine (D-30)
    n_done = n_skip = n_quar = n_fail = 0
    for item in items:
        try:
            result = await translate_file(item.source_sub_path, settings, llm_client, ledger)
            if result.status == "done":
                apply_permissions(result.output_path, settings.puid, settings.pgid, settings.umask)
                n_done += 1
            elif result.status == "skipped":
                n_skip += 1
            elif result.status == "quarantined":
                n_quar += 1
        except Exception as exc:
            logger.error("Unhandled error for %s: %s", item.source_sub_path, exc)
            n_fail += 1

    # End summary (D-30)
    print(f"Run complete: translated={n_done}, skipped={n_skip}, quarantined={n_quar}, failed={n_fail}")
    if n_fail > 0 or n_quar > 0:
        sys.exit(1)
```

### Pattern 9: New TrezarrSettings Fields

```python
# trezarr/config.py — additions to TrezarrSettings
from pydantic import BaseModel, SecretStr
from typing import Any

class PathMapping(BaseModel):
    """A remote→local path prefix substitution pair (D-23)."""
    remote: str   # prefix as seen in *arr API paths
    local: str    # corresponding local path in this container/host

# ── *arr connection (D-22) ─────────────────────────────────────────────────
sonarr_host: str = ""
sonarr_port: int = 8989
sonarr_api_key: SecretStr = SecretStr("")
sonarr_enabled: bool = False   # skip Sonarr discovery if not configured

radarr_host: str = ""
radarr_port: int = 7878
radarr_api_key: SecretStr = SecretStr("")
radarr_enabled: bool = False   # skip Radarr discovery if not configured

# ── Path mapping (D-23) ────────────────────────────────────────────────────
# Env var: TREZARR_PATH_MAPPINGS='[{"remote":"/tv","local":"/data/tv"}]'
# YAML:    path_mappings: [{remote: /tv, local: /data/tv}]
path_mappings: list[PathMapping] = []

# ── Source-language priority (D-25) ───────────────────────────────────────
source_lang_priority: list[str] = ["en"]

# ── Permissions (D-29) ────────────────────────────────────────────────────
puid: int = -1    # -1 = leave as-is (no chown)
pgid: int = -1    # -1 = leave as-is
umask: int = 0o022  # standard *arr default: rw-r--r-- on files
```

**Pydantic-settings env var for `path_mappings` (list of objects):** Use `env_nested_delimiter="__"` (already set in `model_config`) and JSON-encoded env var. pydantic-settings can parse a JSON array string for a `list[PathMapping]` field. [CITED: pydantic-settings docs on JSON env vars]

**`umask` stored as int:** YAML `umask: 18` (decimal) or `umask: 0o022` (Python). The YAML config example should document octal notation with a decimal fallback. [ASSUMED — pydantic int field reads YAML int; octal syntax `0o022` is valid in Python but not standard YAML]

### Anti-Patterns to Avoid

- **Globbing the disk to discover what needs translating.** Always use the Sonarr/Radarr API as the media manifest. Only touch the filesystem to read a known subtitle path or write a sidecar.
- **Calling `os.umask()` globally before each write.** `os.umask()` is process-global and not thread-safe. Compute the target mode explicitly: `mode = 0o666 & ~umask_value`, then call `os.chmod(path, mode)`.
- **Applying path mapping once per series, not per file.** Every individual episode file path from `episode_file.get()` must be mapped independently; the series-level `path` field is the directory, not the file.
- **Using `movie.path` instead of `movie['movieFile']['path']` for Radarr.** `movie['path']` is the directory; the actual video file is `movie['movieFile']['path']`. Subtract the directory to derive the subtitle search base.
- **Trusting `has_file=True` on an Episode without fetching the EpisodeFile.** `Episode.hasFile` is a flag; the actual file path is only in the `EpisodeFile` resource. Always use `episode_file.get(series_id=X)` to get real paths.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| *arr REST client (X-Api-Key auth, JSON parsing, pagination) | Custom httpx client for Sonarr/Radarr | `pyarr` 6.x | Covers both Sonarr + Radarr, handles auth header, returns parsed JSON — saves writing and testing REST plumbing for two services |
| httpx mocking in tests | Custom fixture | `pytest-httpx` | Integrates at the httpx transport layer; works transparently with pyarr's underlying httpx client |
| Source-sub hash | Custom hash algorithm | Reuse `Ledger.content_hash()` from Phase 2 | SHA-256[:16] already defined, tested, and Phase-4-schema-compatible |
| vi sidecar path derivation | Custom path logic | Reuse `derive_vi_sidecar_path()` from Phase 2 | Single source of truth for naming; gap detection must use the same function translate_file() will write to |
| Atomic sidecar write | Custom temp+rename | Reuse `write_vi_sidecar()` from Phase 2 | Already implemented, tested, and correct |

**Key insight:** Phase 3 is the wrapper phase — the translation core is Phase 2. The new code volume is primarily glue: API calls, path-string transforms, filesystem glob, argparse wiring, and a permissions call. The heavy lifting (chunking, validation gate, ledger, atomic write) is already done.

---

## Common Pitfalls

### Pitfall 1: pyarr 6.x API class name mismatch
**What goes wrong:** Code written using the old `SonarrAPI(host_url, api_key)` pattern from older pyarr docs or training data silently imports nothing (the class doesn't exist) or imports a non-existent symbol and crashes at startup.
**Why it happens:** pyarr 5.x used flat `SonarrAPI` / `RadarrAPI`; pyarr 6.x uses composition `Sonarr` / `Radarr` with submodule access.
**How to avoid:** Import `from pyarr import Sonarr, Radarr` (not `SonarrAPI`, `RadarrAPI`). Instantiate with `Sonarr(host="...", api_key="...", port=8989)`. Access via `client.series.get()`, `client.episode_file.get(series_id=X)`.
**Warning signs:** `ImportError: cannot import name 'SonarrAPI' from 'pyarr'`

### Pitfall 2: Using `movie['path']` for the video file in Radarr
**What goes wrong:** `movie['path']` is the movie *directory* (e.g. `/movies/Parasite (2019)`), not the video file. Using it as the subtitle target places sidecars one level too high.
**Why it happens:** Series in Sonarr have a series-level `path` field (directory) while the video is in `episode_file['path']`. Radarr mirrors this: `movie['path']` is directory, `movie['movieFile']['path']` is the actual video.
**How to avoid:** For Radarr, always access `movie['movieFile']['path']` for the video file path. Check `movie['movieFileId'] != 0` (or `movie.get('movieFile')` is not None) before accessing it.

### Pitfall 3: Path-mapping trailing slash mismatch
**What goes wrong:** API returns `/tv/Show/...`, mapping has `remote: "/tv/"` (trailing slash). The `startswith("/tv/")` check fails because the path starts with `/tv/S` not `/tv//S`.
**Why it happens:** The *arr UIs and APIs are inconsistent about trailing slashes in paths.
**How to avoid:** Strip trailing slashes from BOTH the mapping `remote` AND the API-returned path before prefix comparison. Apply consistently in `apply_path_mapping()`.

### Pitfall 4: Path-traversal via crafted path mapping
**What goes wrong:** A misconfigured `local` path (or an attacker-controlled config) causes sidecar writes outside the media volume (e.g. `local: /` maps everything to root).
**Why it happens:** Path mapping is a find/replace with no inherent boundary check.
**How to avoid:** After resolving a path via mapping, call `assert_within_media_roots()` before any write or read. The set of allowed roots is the union of all `local` values from configured mappings. This is explicitly required by D-29 (see PITFALLS.md §Security).
**Warning signs:** `write_vi_sidecar()` called with a path outside `/data/media/` or equivalent.

### Pitfall 5: Gap detection derives the vi sidecar path from the video path, not the source sub path
**What goes wrong:** `derive_vi_sidecar_path("/movies/Parasite.mkv")` → `/movies/Parasite.vi.srt`. But the source sub is `/movies/Parasite.en.srt` and `derive_vi_sidecar_path("/movies/Parasite.en.srt")` → same `/movies/Parasite.vi.srt`. These coincide here, but the function signature takes the source SRT path, not the video path. If called with the video path, it still works for SRT-only; but when the video has no extension overlap this could diverge.
**How to avoid:** Always call `derive_vi_sidecar_path(source_sub_path)` in gap detection, not the video path. The Phase-2 function signature is explicit about this.

### Pitfall 6: Running the Sonarr discovery loop serially per-series at scale
**What goes wrong:** With 200 series, `episode_file.get(series_id=X)` is called 200 times sequentially — slow startup for the one-shot CLI.
**Why it happens:** Naive loop implementation.
**How to avoid:** Use `asyncio.gather()` over all `async_sonarr.episode_file.get(series_id=X)` calls with a concurrency cap (a `Semaphore(10)` is fine for API calls to a local service). For Phase 3 (one-shot CLI), this is an optimization but not correctness-critical; mention in plan as a preferred approach.

### Pitfall 7: source_sub_hash vs content_hash confusion
**What goes wrong:** D-27 says "extend ledger with source-sub content hash." The Phase-2 `LedgerEntry.content_hash` already IS the source-sub hash (computed in `translate_file()` from the source bytes). If a new field `source_sub_hash` is added but `content_hash` is still used in `translate_file()`'s skip logic, the two can diverge.
**How to avoid:** Either: (a) document that `content_hash` IS the source-sub hash and add no new field, OR (b) rename `content_hash` → `source_sub_hash` in `LedgerEntry` (breaking rename — avoid). Option (a) is cleaner and additive. The planner should make a definitive call here.

---

## Code Examples

### Fetch all Sonarr episode file paths
```python
# Source: docs.totaldebug.uk/pyarr/modules/sonarr.html [VERIFIED: official pyarr docs]
from pyarr import Sonarr
from trezarr.paths import apply_path_mapping

sonarr = Sonarr(host="192.168.1.100", api_key="abc123", port=8989, tls=False)

media_items = []
for series in sonarr.series.get():
    if not series.get("monitored", False):
        continue
    for ep_file in sonarr.episode_file.get(series_id=series["id"]):
        raw_path = ep_file["path"]          # e.g. "/tv/Show/Season 1/Show.S01E01.mkv"
        local_path = apply_path_mapping(raw_path, settings.path_mappings)
        media_items.append({
            "local_path": local_path,
            "series_title": series["title"],
            "series_id": series["id"],
            "season": ep_file["seasonNumber"],
        })
```

### Fetch all Radarr movie file paths
```python
# Source: docs.totaldebug.uk/pyarr/modules/radarr.html [VERIFIED: official pyarr docs]
from pyarr import Radarr

radarr = Radarr(host="192.168.1.100", api_key="xyz789", port=7878, tls=False)

for movie in radarr.movie.get():
    if not movie.get("monitored", False):
        continue
    movie_file = movie.get("movieFile")
    if movie_file is None:
        continue
    raw_path = movie_file["path"]           # full video file path
    local_path = apply_path_mapping(raw_path, settings.path_mappings)
    # ...
```

### Testing with pytest-httpx
```python
# Source: colin-b.github.io/pytest_httpx/ [CITED: official pytest-httpx docs]
# tests/arr/test_arr_discovery.py

import pytest
from pyarr import Sonarr

def test_sonarr_discovers_monitored_series(httpx_mock):
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[
            {"id": 1, "title": "Show A", "path": "/tv/Show A", "monitored": True},
            {"id": 2, "title": "Show B", "path": "/tv/Show B", "monitored": False},
        ],
    )
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/episodefile?seriesId=1",
        json=[{"id": 10, "seriesId": 1, "seasonNumber": 1,
               "path": "/tv/Show A/Season 1/Show.S01E01.mkv", "relativePath": "Season 1/Show.S01E01.mkv"}],
    )
    sonarr = Sonarr(host="192.168.1.100", api_key="test", port=8989, tls=False)
    series_list = sonarr.series.get()
    # Only monitored series id=1 should be in discovery result
    assert any(s["id"] == 1 for s in series_list)
    ep_files = sonarr.episode_file.get(series_id=1)
    assert ep_files[0]["path"] == "/tv/Show A/Season 1/Show.S01E01.mkv"
```

### Path-mapping unit test
```python
# tests/test_paths.py
from trezarr.paths import apply_path_mapping, PathMapping

def test_path_mapping_replaces_prefix():
    mappings = [PathMapping(remote="/tv", local="/data/media/tv")]
    result = apply_path_mapping("/tv/Show/S1/ep.mkv", mappings)
    assert str(result) == "/data/media/tv/Show/S1/ep.mkv"

def test_path_mapping_no_match_passthrough():
    mappings = [PathMapping(remote="/tv", local="/data/media/tv")]
    result = apply_path_mapping("/movies/Film.mkv", mappings)
    assert str(result) == "/movies/Film.mkv"

def test_path_mapping_strips_trailing_slash():
    mappings = [PathMapping(remote="/tv/", local="/data/media/tv")]
    result = apply_path_mapping("/tv/Show/ep.mkv", mappings)
    assert str(result) == "/data/media/tv/Show/ep.mkv"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `SonarrAPI(host_url, api_key)` flat class (pyarr 5.x) | `Sonarr(host, api_key, port)` with composition submodule API (pyarr 6.x) | pyarr 6.0 (2024) | Import name changed; all method access now via submodules; `SonarrAPI` no longer exists |
| Setting `os.umask()` before writes | Compute explicit mode with `0o666 & ~umask_value`, then `os.chmod()` | Best practice evolution | Process-global `os.umask()` is unsafe in async code; explicit `chmod` is correct |
| Single `SonarrAPI` covering both sync and async | Separate `Sonarr` (sync) and `AsyncSonarr` (async) classes | pyarr 6.x | Phase 3 CLI uses sync; Phase 7 FastAPI lifespan should use `AsyncSonarr` |

**Deprecated/outdated:**
- `pyarr.SonarrAPI`, `pyarr.RadarrAPI` — these class names do not exist in pyarr 6.x. Any training data or old tutorials referencing them are wrong for the current package.
- `aiopyarr` — a separate async *arr client library; do NOT use alongside pyarr (different package, different maintainer). pyarr 6.x provides its own async variants.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `Sonarr.episode_file.get(series_id=X)` URL form is `GET /api/v3/episodefile?seriesId={X}` — assumed from HTTP convention and pyarr pattern | pyarr patterns | Test setup in `httpx_mock.add_response(url=...)` would use wrong URL; easy to fix by inspecting actual httpx call |
| A2 | Sorting path mappings by descending `len(remote)` gives longest-prefix semantics | Path-mapping algorithm | If TRaSH/arr use first-match (user-ordered), sorting changes semantics; safe default is to sort AND document the sort |
| A3 | `pyarr.Radarr.movie.get()` returns `movieFile` as a nested dict in the movie dict (not a separate call) | Radarr response shape | If `movieFile` is absent from the `movie.get()` response, a separate `movie_file.get(movie_id=X)` call is needed |
| A4 | `umask` stored as Python int in pydantic-settings supports YAML octal notation | Settings pattern | If YAML `022` is parsed as decimal 22 (not octal), users will get wrong permissions; document explicitly |
| A5 | pyarr raises `httpx.HTTPStatusError` on 4xx/5xx (not a custom pyarr exception) | Error handling | If pyarr wraps in its own exception class, the catch clause in `probe`/`discover` will miss it |
| A6 | `Sonarr.series.get()` called with no arguments returns ALL series (not paginated) | pyarr patterns | If pyarr paginates, only the first page would be discovered; verify against a real Sonarr instance |

---

## Open Questions

1. **Does `radarr.movie.get()` embed `movieFile` inline, or require a separate call?**
   - What we know: golift/starr Go struct has `Movie.MovieFile` as a nested struct; pyarr docs say `movie_file.get(movie_id=X)` exists as a separate submodule.
   - What's unclear: Whether the inline embed is present by default or only with a query parameter.
   - Recommendation: In `discover_radarr_items()`, call `radarr.movie_file.get(movie_id=X)` explicitly as a fallback if `movie['movieFile']` is None/absent.

2. **pyarr 6.x async context manager or regular instantiation?**
   - The quickstart doc shows `async with AsyncSonarr(...) as sonarr:` (context manager). The sync `Sonarr` may or may not require context manager. For Phase 3's one-shot CLI, using the sync client outside a context manager should be fine; for the async variant in Phase 7, always use `async with`.
   - Recommendation: Use sync `Sonarr`/`Radarr` for the Phase 3 CLI without context manager; test will confirm if cleanup is needed.

3. **Does source-sub glob need to handle 3-letter ISO-639-2 codes?**
   - Phase-2 `_LANG_CODE_RE = re.compile(r'\.[a-z]{2}$')` only matches 2-letter codes.
   - Source subs from Bazarr may use 3-letter codes (e.g. `eng`, `zho`).
   - Recommendation: Extend the discovery regex to `r'\.[a-z]{2,3}\.srt$'` and the `source_lang_priority` default to include both `["en", "eng"]` or normalize 3→2 at scan time.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 (via uv) | All runtime code | ✓ | 3.12.12 | — |
| `uv` | Dependency management | ✓ | 0.11.16 | — |
| `pytest` (via uv dev) | Test suite | ✓ | 9.0.3 | — |
| `pytest-asyncio` | Async tests | ✓ | installed | — |
| `pyarr` | *arr discovery | ✗ | — | Needs `uv add pyarr` |
| `pytest-httpx` | Test mocking | ✗ | — | Needs `uv add --dev pytest-httpx` |
| Live Sonarr / Radarr | Integration smoke test | ✗ | — | `pytest-httpx` mocks; mark live tests with `@pytest.mark.live` |

**Missing dependencies with no fallback:**
- `pyarr` is the only new runtime dependency and blocks the `trezarr/arr/` module. `uv add pyarr` as Wave 0 task.

**Missing dependencies with fallback:**
- `pytest-httpx` is dev-only; without it, pyarr tests can still use `unittest.mock.patch` on pyarr methods (less elegant but functional).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio (asyncio_mode=auto) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (existing) |
| Quick run command | `uv run pytest tests/arr/ tests/test_paths.py tests/discover/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTG-01 | Sonarr series + episode files returned and path-mapped | unit (httpx_mock) | `uv run pytest tests/arr/test_arr_discovery.py -x` | ❌ Wave 0 |
| INTG-01 | Radarr movies with movieFile paths returned and path-mapped | unit (httpx_mock) | `uv run pytest tests/arr/test_arr_discovery.py -x` | ❌ Wave 0 |
| INTG-03 | Path mapping: prefix replaced, no-match passthrough, trailing-slash normalization | unit | `uv run pytest tests/test_paths.py -x` | ❌ Wave 0 |
| INTG-03 | Startup probe: readable root passes, unreadable root → SystemExit | unit (tmp_path) | `uv run pytest tests/test_paths.py::test_probe -x` | ❌ Wave 0 |
| INTG-03 | Path-traversal guard: path outside media roots raises ValueError | unit | `uv run pytest tests/test_paths.py::test_traversal_guard -x` | ❌ Wave 0 |
| INTG-04 | apply_permissions: os.chown + os.chmod called; PermissionError → log-warn-continue | unit (mock os.chown) | `uv run pytest tests/output/test_write.py::test_apply_permissions -x` | ❌ Wave 0 |
| AUTO-01 | find_source_sub returns highest-priority lang sub, None when absent | unit (tmp_path) | `uv run pytest tests/discover/test_scan.py -x` | ❌ Wave 0 |
| AUTO-01 | is_eligible: no source → not eligible; no vi → eligible; foreign vi → skip+log | unit (tmp_path) | `uv run pytest tests/discover/test_scan.py::test_gap_detection -x` | ❌ Wave 0 |
| AUTO-03 | is_eligible: already done + hash unchanged → skip; changed hash → re-translate | unit | `uv run pytest tests/discover/test_scan.py::test_idempotency -x` | ❌ Wave 0 |
| AUTO-04 | Foreign vi sidecar (not in ledger, dest.exists()) → skip+log, not quarantined | unit | `uv run pytest tests/discover/test_scan.py::test_foreign_vi -x` | ❌ Wave 0 |
| D-30 | Batch run continues past per-item failure; exit code 1 on any failure | integration (tmp_path + mock LLM) | `uv run pytest tests/test_cli.py::test_batch_run_continues -x` | ❌ Wave 0 |
| D-30 | End-of-run summary printed; zero exit when all succeed | integration | `uv run pytest tests/test_cli.py::test_exit_code -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/arr/ tests/test_paths.py tests/discover/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/arr/__init__.py` and `tests/arr/test_arr_discovery.py` — covers INTG-01 (Sonarr + Radarr discovery with httpx_mock)
- [ ] `tests/discover/__init__.py` and `tests/discover/test_scan.py` — covers AUTO-01, AUTO-03, AUTO-04
- [ ] `tests/test_paths.py` — covers INTG-03 (path mapping, startup probe, traversal guard)
- [ ] `tests/test_cli.py` — covers D-30 (batch-run semantics, exit code, per-item quarantine)
- [ ] New method `test_apply_permissions` in `tests/output/test_write.py` (extend existing file) — covers INTG-04 permissions
- [ ] Framework install: `uv add pyarr && uv add --dev pytest-httpx` — Wave 0 task

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (API key to Sonarr/Radarr) | `SecretStr` for API keys in `TrezarrSettings`; never log `.get_secret_value()` output |
| V3 Session Management | no | Stateless CLI; no sessions |
| V4 Access Control | yes (path-traversal) | `assert_within_media_roots()` guard on all resolved paths before any write |
| V5 Input Validation | yes | Path mapping inputs validated via pydantic `PathMapping` model; API-returned paths treated as untrusted until mapped |
| V6 Cryptography | no | SHA-256 for idempotency hash is one-way, not encryption |

### Known Threat Patterns for *arr integration stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via crafted path mapping (`remote: /`, `local: /etc`) | Tampering | `assert_within_media_roots()` — resolved write path must be inside a configured media root |
| API key in logs or error messages | Information Disclosure | `SecretStr` on `sonarr_api_key`, `radarr_api_key`; never call `.get_secret_value()` outside the API client constructor |
| Arbitrary write via crafted API response path | Tampering | Path-mapping + traversal guard; do not trust raw API paths as write destinations |
| PermissionError chown silently interpreted as success | Elevation of Privilege | Log warning; the file exists but ownership may be wrong — Phase 7 s6 will correct |

---

## Sources

### Primary (HIGH confidence)
- `docs.totaldebug.uk/pyarr/modules/sonarr.html` — pyarr 6.x `Sonarr` class constructor, `series.get()`, `episode_file.get()` signatures [VERIFIED: official pyarr docs]
- `docs.totaldebug.uk/pyarr/modules/radarr.html` — pyarr 6.x `Radarr` class constructor, `movie.get()`, `movie_file.get()` signatures [VERIFIED: official pyarr docs]
- `pkg.go.dev/golift.io/starr/sonarr` — `EpisodeFile` Go struct with all JSON field tags (`path`, `seriesId`, `seasonNumber`, `relativePath`) [VERIFIED: authoritative API cross-reference library]
- `pypi.org/pypi/pyarr/json` — pyarr 6.6.0 version, `requires_python: >=3.12` [VERIFIED: PyPI JSON API, 2026-05-31]
- `pypi.org/pypi/pytest-httpx/json` — pytest-httpx 0.36.2, source repo `github.com/Colin-b/pytest_httpx` [VERIFIED: PyPI JSON API, 2026-05-31]
- slopcheck `~/.local/bin/slopcheck install pyarr pytest-httpx respx` — all three `[OK]` [VERIFIED: slopcheck 2026-05-31]
- `trezarr/output/ledger.py` — `LedgerEntry`, `Ledger.content_hash()` existing implementation [VERIFIED: codebase]
- `trezarr/output/write.py` — `derive_vi_sidecar_path()`, `write_vi_sidecar()` existing implementation [VERIFIED: codebase]
- `trezarr/config.py` — existing `TrezarrSettings` structure and `_yaml_file` override pattern [VERIFIED: codebase]
- Python docs `os.chown` — `-1` for UID/GID means "leave unchanged"; raises `PermissionError` (EPERM) when lacking capability [CITED: Python stdlib docs]

### Secondary (MEDIUM confidence)
- `docs.totaldebug.uk/pyarr/quickstart.html` — `AsyncSonarr` async context manager pattern; composition API overview [CITED: official pyarr docs]
- `trash-guides.info/Radarr/Tips/Radarr-remote-path-mapping/` — "dumb find/replace" path mapping model [CITED: TRaSH guides, canonical *arr community reference]
- `colin-b.github.io/pytest_httpx/` — `httpx_mock.add_response(url=..., json=...)` fixture pattern [CITED: official pytest-httpx docs]
- golift/starr Radarr package — `Movie.MovieFile` nested struct with `path`, `movieId` fields [VERIFIED: Go package cross-reference]

### Tertiary (LOW confidence, flag for validation)
- pyarr HTTP error type (`httpx.HTTPStatusError`) — inferred from pyarr using httpx internally; not explicitly documented [ASSUMED: A5]
- `radarr.movie.get()` embedding `movieFile` inline vs. requiring separate call [ASSUMED: A3]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pyarr 6.6.0 verified on PyPI + official docs; `pytest-httpx` slopcheck [OK] + 7.5M downloads/month
- Architecture: HIGH — patterns derived from reading existing Phase-2 code + pyarr official docs; path-mapping algorithm from TRaSH guides
- Pitfalls: HIGH — Pitfalls 8/9/10 from PITFALLS.md are authoritative; pyarr API mismatch pitfall is VERIFIED from docs

**Research date:** 2026-05-31
**Valid until:** 2026-08-31 (pyarr 6.x stable; Sonarr/Radarr /api/v3 is stable; pytest-httpx API is stable)

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 3 |
|-----------|-------------------|
| Tech stack: Python 3.12 | pyarr 6.x requires >=3.12 — satisfied |
| LLM via OpenAI-SDK-compatible endpoint | Phase 3 reuses Phase-2 `LLMClient` unchanged |
| pyarr 6.6.x, X-Api-Key, /api/v3 | Prescribed — use `Sonarr`/`Radarr` 6.x composition API |
| pydantic-settings 2.14.x | New fields added to `TrezarrSettings` follow existing pattern |
| No Celery/Redis/nginx | Confirmed: one-shot CLI with argparse, no extra services |
| Secrets via `SecretStr` | `sonarr_api_key`, `radarr_api_key` must be `SecretStr` |
| PUID/PGID/UMASK | In-process `os.chown`/`os.chmod`; degrade on `PermissionError` |
| GSD workflow enforcement | All code changes go through GSD commands; no direct edits outside workflow |
