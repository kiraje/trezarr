# Phase 10: Source Selection & Per-Series Overrides — Research

**Researched:** 2026-06-02
**Domain:** Bazarr API inventory reads, relational-fidelity ranking heuristic, idempotency under source-language change, per-series override store + threading
**Confidence:** HIGH (all claims verified against live code or official sources)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-103** `trezarr/arr/bazarr.py` is an httpx client (not pyarr); wraps `BazarrError` (mirror `DiscoveryError`); routes host through `_normalize_arr_host`; resolves `bazarr_api_key` via `SecretStr.get_secret_value()` at client boundary only (D-11).
- **D-104** Bazarr is the inventory authority; filesystem is the byte source and graceful fallback. When `bazarr_enabled=False` or Bazarr unreachable, degrade to existing `find_source_sub` filesystem glob.
- **D-105** Bazarr-reported paths reconciled via existing `apply_path_mapping` (D-23). Unresolvable Bazarr path → filesystem fallback per-item.
- **D-106** Source-agnostic by default; English is the universal last-resort fallback, not the default source.
- **D-107** Rank available sources by static relational-richness tier biased by `original_language`. Tier 1: `zh`/`ko`/`ja`/`th`. Tier 2: other relational/honorific languages. Tier 3: `en` and flat-relational. Content's `original_language` biases ranking but does NOT displace a native English source with a fan foreign sub.
- **D-108** Capture `original_language` into `MediaItem` and persist in `Series.arr_metadata`. Sonarr and Radarr both expose `originalLanguage` (confirmed). When absent, rank purely over available-source set.
- **D-109** Fallback chain per item: (1) per-series source override, (2) SRC-02 richness ranking over available sources (Bazarr ∪ filesystem) biased by `original_language`, (3) global `source_lang_priority`, (4) first available source of any language. Zero sources → `ScanStats.no_source` (skip).
- **D-110** Idempotency must survive a source-language change. Ledger keys on `source_sub_path` + `content_hash`. Different chosen source = different path = distinct ledger row. D-26/D-27/D-28 guards must still hold.
- **D-111** Per-series overrides: nullable columns `source_lang_override` (JSON ordered list | NULL) and `model_override` (str | NULL) on `series` table. Alembic migration 0003. Register override reuses Phase-8 lock on `Series.register`. NULL = inherit global config.
- **D-112** `resolve_effective_settings(series, settings) -> (source_priority, register, model)` — pure function; global config is default; per-series columns win when non-NULL.
- **D-113** Model override flows per-CALL, not per-client. Single global `LLMClient` and one `asyncio.Semaphore` preserved (D-06). Engine threads effective `model` into each LLM request via per-call `model` arg.
- **D-114** Extend Phase-8 per-series Bible editor with "Overrides" section. Add `PATCH /series/{id}/overrides` for source-priority + model. Register editing reuses existing `PATCH /series/{id}/register`. Reuse Phase-8 SPA assets.

### Claude's Discretion
- Exact Bazarr API endpoints + response shapes (researched below — HIGH confidence)
- Precise SRC-02 ranking algorithm, language→tier table, and `original_language` bias weight (designed below)
- Whether source selection extends `scan_for_eligible_items`'s signature or becomes a new `select_source` step; how chosen `source_lang` + override provenance are carried into `EligibleItem`/`job` rows
- Exact override column names/types, overrides DTO/route shape, and `model_override` validation
- Whether secondary signals (genre/country) augment `original_language` for SRC-02

### Deferred Ideas (OUT OF SCOPE)
- Style-based sign/OP/ED skipping as per-series toggle
- Manual per-series "re-translate all episodes" action
- Per-series enable/disable, per-series concurrency, per-series glossary import
- Auto-detecting `original_language` from dialogue
- Multi-instance Sonarr/Radarr/Bazarr (SCALE-01), notifications/confidence-flagging (OBS-01/02)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTG-02 | Connect to Bazarr via its API to read which source-language subtitles already exist for each item (never re-downloading) | Bazarr API shape fully verified: `/api/episodes?seriesid[]=N` and `/api/movies?radarrid[]=N` return `subtitles` arrays with `{code2, code3, path, forced, hi}` objects. Auth via `X-API-KEY` header. Pure reads confirmed — no download endpoint invoked. |
| SRC-01 | Source-language-agnostic — can translate from any available source-language subtitle to Vietnamese | `find_source_sub` + `scan_for_eligible_items` already accept an arbitrary `lang_priority` list; D-109 fallback chain ends with "first available of any language." |
| SRC-02 | When multiple sources exist, select the relationally-richest source; prefer zh/ko/ja/th for East-Asian content; fall back gracefully | SRC-02 ranking algorithm designed in full below. `original_language` from Sonarr/Radarr verified as `{id, name}` object. |
| SVC-05 | User can set per-series overrides for source-language preference, register, and model | Migration 0003 pattern verified from 0002 template. `resolve_effective_settings()` pure function design verified against `process_one_item` callsites. D-113 model-per-call verified from `LLMClient._model` + OpenAI SDK per-call `model` arg. |
| AUTO-03 (invariant) | Idempotent — source-sub hash idempotency must survive source-language change | D-110 analysis: different source path = distinct ledger row; no loop risk; D-26/D-27/D-28 guards intact. Detailed below. |
| AUTO-04 (invariant) | No self-reprocessing loop | Self-output exclusion via `is_eligible` Case 1 + Case 2 (ledger provenance). Source change produces a new `.vi.srt` path only when the SOURCE path changes — `derive_vi_sidecar_path` strips the source lang suffix and appends `.vi`. Both old and new vi paths derived from their respective source paths → no clobber risk. |
| INTG-03 (invariant) | Path mapping | Bazarr-reported paths run through `apply_path_mapping` (D-105) — same function used for Sonarr/Radarr. |
</phase_requirements>

---

## Summary

Phase 10 adds four mutually-reinforcing capabilities on top of the existing Phase-3 through Phase-8 foundation. The research finds that all four are mechanically straightforward given the existing code structure; the primary novel work is (1) the Bazarr inventory client, (2) the relational-fidelity ranking heuristic, and (3) the precise behavior of the idempotency ledger when the chosen source language changes.

**Bazarr API (INTG-02).** Bazarr exposes GET `/api/episodes?seriesid[]=N` and GET `/api/movies?radarrid[]=N`. Both return a `subtitles` array where each entry is `{name, code2, path, code3, forced, hi}`. `code2` is a 2-letter ISO-639-1 code (e.g. `"ko"`, `"en"`), matching the tokens already used by `_LANG_SIDECAR_RE`. Auth is via `X-API-KEY` header (case-insensitive variant of `X-Api-Key` used in `test_bazarr`). The path field is Bazarr's container-namespace path — it requires `apply_path_mapping`. These are pure read endpoints; no download or search endpoint is needed.

**Relational-fidelity ranking (SRC-02).** The algorithm is a two-stage sort: (1) whether the language is the content's `original_language` (highest priority signal), (2) the static relational-richness tier (zh/ko/ja/th > other relational > en/flat). This cleanly handles the nuance: a Korean drama's `ko` sub beats `en` because `ko` IS the original language AND is Tier-1; a US show's `en` sub beats a `zh` fansub because `en` IS the original language (bonus) and `zh` is merely Tier-1 (no provenance bonus).

**Idempotency under source-language change (D-110).** The ledger keys on `source_sub_path` (the full path string). A different chosen source = a different key = a distinct ledger row. The existing D-26/D-27/D-28 guards operate independently on each row and are unaffected. The one regression risk is that `derive_vi_sidecar_path` strips only 2-letter lang codes; 3-letter source paths (e.g. `Show.S01E01.eng.srt`) would produce `Show.S01E01.en.vi.srt` (incorrect). This is a pre-existing limitation of `_LANG_CODE_RE`; Phase 10 must normalize 3-letter codes in the selection layer before passing to scan.

**Per-series overrides (SVC-05).** Migration 0003 adds two nullable columns to `series`. `resolve_effective_settings()` is a pure function. The model override threads into `LLMClient.call()` via an optional `model` parameter, bypassing `self._model` — the OpenAI SDK `completions.parse()` and `completions.create()` both accept `model` per-call. The single `_semaphore` governs concurrency regardless of which model is used.

**Primary recommendation:** Implement as a `source_selection` module (`trezarr/source_selection/`) containing the Bazarr client (`bazarr.py`), the ranking function (`rank.py`), and the override resolver (`resolve.py`). Wire it into `scan_for_eligible_items` by adding an optional `bazarr_inventory` parameter (or a pre-scan `build_inventory()` step) while keeping the existing signature backward-compatible. This minimizes regression surface.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bazarr inventory read (INTG-02) | API / Backend (`arr/bazarr.py`) | — | Knowledge acquisition from external API; no UI involvement |
| Relational-fidelity ranking (SRC-02) | API / Backend (`source_selection/rank.py`) | — | Pure function over available languages; no I/O |
| `original_language` capture (D-108) | API / Backend (`arr/sonarr.py`, `arr/radarr.py`) | Database / Storage (`Series.arr_metadata`) | Captured at discovery, persisted in arr_metadata JSON |
| Override storage (SVC-05) | Database / Storage (Alembic 0003 migration) | API / Backend (store writers) | Nullable columns on existing `series` table |
| Override resolution (D-112) | API / Backend (`resolve_effective_settings()`) | — | Pure function; no I/O; consumed by worker/scheduler/cli |
| Model per-call threading (D-113) | API / Backend (`translate/engine.py`) | — | Per-call `model` arg to LLMClient; no new client |
| Override UI (D-114) | Frontend Server (React SPA BibleEditor) | API / Backend (`/api/bible/series/{id}/overrides`) | Extends existing BibleEditor; D-39 Pydantic boundary |

---

## Standard Stack

### Core (all pre-existing — no new packages needed)
| Library | Version | Purpose | Role in Phase 10 |
|---------|---------|---------|-----------------|
| httpx | 0.28.x | HTTP client | Bazarr inventory client (`arr/bazarr.py`) — already a dep via openai/fastapi |
| SQLAlchemy 2.0 async | 2.0.50 | ORM | Migration 0003; nullable override columns on `series` |
| Alembic | 1.18.x | Migrations | Migration 0003 (`source_lang_override`, `model_override`) |
| Pydantic | 2.13.x | DTOs | Override DTO; overrides response shape |
| React + Vite | React 19 / Vite 7 | SPA | BibleEditor "Overrides" section (D-114) |
| openai | 2.38.x | LLM client | Per-call `model` arg (D-113) |

All packages are pre-existing from Phases 1–8. Phase 10 adds zero new dependencies. [VERIFIED: existing `pyproject.toml` / CLAUDE.md stack table]

### Installation
```bash
# No new packages — all are already installed.
# Phase 10 adds only migrations and code in existing modules.
```

---

## Package Legitimacy Audit

> No new packages introduced in this phase. All libraries are pre-existing from Phases 1–8.

| Package | Registry | Age | Downloads | Source Repo | Disposition |
|---------|----------|-----|-----------|-------------|-------------|
| httpx | PyPI | 6+ yrs | 50M+/wk | github.com/encode/httpx | Pre-existing — approved |
| SQLAlchemy | PyPI | 18+ yrs | 50M+/wk | github.com/sqlalchemy/sqlalchemy | Pre-existing — approved |
| Alembic | PyPI | 13+ yrs | 40M+/wk | github.com/sqlalchemy/alembic | Pre-existing — approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
Sonarr/Radarr API        Bazarr API
    │ /api/v3/series      │ /api/episodes?seriesid[]=N
    │ originalLanguage     │ subtitles[{code2, path, ...}]
    │                      │
    ▼                      ▼
arr/sonarr.py          arr/bazarr.py
MediaItem+             BazarrInventory
original_language      (series_id → [SubtitleEntry])
    │                      │
    └──────────┬───────────┘
               ▼
    source_selection/rank.py
    rank_sources(available, original_language,
                 per_series_override, global_priority)
               │
               ▼ (source_lang, source_sub_path)
    discover/scan.py
    scan_for_eligible_items
    → EligibleItem(source_lang, source_sub_path, ...)
               │
               ▼
    source_selection/resolve.py
    resolve_effective_settings(series_dto, settings)
    → (source_priority, register, model)
               │
               ├──► translate/engine.py
               │    translate_file(..., model=effective_model)
               │    build_translate_prompt(source_lang=...)
               │
               └──► LLMClient.call(..., model=effective_model)
                    [SINGLE _semaphore — D-06 preserved]
```

### Recommended Project Structure
```
trezarr/
├── arr/
│   ├── __init__.py        # DiscoveryError, _normalize_arr_host (existing)
│   ├── sonarr.py          # ADD: original_language to MediaItem (D-108)
│   ├── radarr.py          # ADD: original_language to MediaItem (D-108)
│   └── bazarr.py          # NEW: BazarrError, BazarrClient, fetch_inventory()
├── source_selection/
│   ├── __init__.py        # NEW: package
│   ├── rank.py            # NEW: rank_sources() — pure function (SRC-02)
│   └── resolve.py         # NEW: resolve_effective_settings() (D-112)
├── discover/
│   ├── scan.py            # EXTEND: integrate Bazarr inventory + richness ranking
│   └── gap.py             # UNCHANGED (D-26/D-27/D-28 guards intact)
├── bible/
│   ├── models.py          # ADD: source_lang_override, model_override to Series
│   └── dto.py             # ADD: fields to SeriesDTO
├── translate/
│   └── engine.py          # ADD: optional model param to LLM call sites
├── web/
│   └── routes/
│       └── bible.py       # ADD: PATCH /series/{id}/overrides
└── config.py              # ADD: Phase-10 settings group
alembic/versions/
└── 0003_per_series_overrides.py  # NEW: nullable columns on series
frontend/src/
└── pages/
    └── BibleEditor.tsx    # ADD: Overrides section (source_priority, model)
```

---

## Deep Dive: Bazarr API (INTG-02, D-103/D-104/D-105)

### Confirmed Endpoints and Response Shapes

**Authentication:** `X-API-KEY` header (Bazarr's `@authenticate` decorator checks `request.headers["X-API-KEY"]`). [VERIFIED: bazarr/api/utils.py source code]

The project currently uses `"X-Api-Key"` in `test_bazarr`. Bazarr's actual header key is `X-API-KEY`. Both are case-insensitive in HTTP/1.1, so the existing `test_bazarr` pattern works correctly; the new client should use `"X-API-KEY"` to match Bazarr's own authorizations definition for clarity. [VERIFIED: Bazarr swaggerui.py authorizations dict]

**Base URL:** `http://{host}:{port}/api/` — the API is mounted at `/api` prefix with namespaces added at `"/"` (no `/v1/` version segment). [VERIFIED: bazarr/api/__init__.py `url_prefix='/api'`]

**Episodes inventory endpoint:**
```
GET /api/episodes?seriesid[]=<sonarr_series_id>
Headers: X-API-KEY: <bazarr_api_key>
```
Returns: `{"data": [ <episode_obj>, ... ]}` — array of episode objects.

Each episode object includes:
```json
{
  "sonarrSeriesId": 123,
  "sonarrEpisodeId": 456,
  "season": 1,
  "episode": 3,
  "path": "/tv/ShowName/Season 01/ShowName.S01E03.mkv",
  "subtitles": [
    {
      "name": "Korean",
      "code2": "ko",
      "code3": "kor",
      "path": "/tv/ShowName/Season 01/ShowName.S01E03.ko.srt",
      "forced": false,
      "hi": false
    },
    {
      "name": "English",
      "code2": "en",
      "code3": "eng",
      "path": "/tv/ShowName/Season 01/ShowName.S01E03.en.srt",
      "forced": false,
      "hi": false
    }
  ],
  "missing_subtitles": [ ... ],
  "monitored": true
}
```
[VERIFIED: bazarr/api/episodes/episodes.py — the `postprocess()` function constructs the subtitles list from `raw_subtitles` as `[{name, code2, code3, path, forced, hi}]`]

**Movies inventory endpoint:**
```
GET /api/movies?radarrid[]=<radarr_movie_id>
Headers: X-API-KEY: <bazarr_api_key>
```
Returns: `{"data": [ <movie_obj>, ... ], "total": N}`

Same `subtitles` array structure as episodes. [VERIFIED: bazarr/api/movies/movies.py + postprocessMovie()]

**Pagination:** The movies endpoint supports `start=` and `length=` params (default: `start=0`, `length=-1` meaning no limit). The episodes endpoint has NO pagination — results are bounded by the series query (all episodes of the series). For movies, use `radarrid[]=` filtering rather than bulk pagination. [VERIFIED: bazarr/api/movies/movies.py `get_request_parser` + episodes.py]

**Pure-read guarantee:** The inventory endpoints only SELECT from the Bazarr database — they do NOT call any download/search/provider logic. The subtitle paths in the response are paths to already-existing files on disk. [VERIFIED: no download or provider calls in episodes.py/movies.py GET handlers]

### BazarrClient Design

```python
# trezarr/arr/bazarr.py

@dataclass
class SubtitleEntry:
    """One existing subtitle returned by Bazarr inventory."""
    code2: str          # 2-letter ISO-639-1 code (e.g. "ko", "en")
    code3: str          # 3-letter ISO-639-2 code (e.g. "kor", "eng")
    path: str           # Bazarr container-namespace path (needs apply_path_mapping)
    forced: bool = False
    hi: bool = False    # hearing-impaired

@dataclass
class BazarrInventoryItem:
    """Per-episode/movie Bazarr subtitle inventory."""
    arr_id: int                         # sonarrEpisodeId or radarrId
    path: str                           # media file path (Bazarr's namespace)
    subtitles: list[SubtitleEntry]

class BazarrError(Exception):
    """Raised when a Bazarr inventory call fails (mirrors DiscoveryError)."""

class BazarrClient:
    """httpx-based Bazarr inventory client (D-103)."""

    def __init__(self, settings: TrezarrSettings) -> None:
        # D-11: SecretStr resolved ONLY here
        self._api_key = settings.bazarr_api_key.get_secret_value()
        self._base_url = (
            f"http://{_normalize_arr_host(settings.bazarr_host)}:{settings.bazarr_port}"
        )

    async def fetch_episodes(
        self, sonarr_series_id: int
    ) -> list[BazarrInventoryItem]:
        """GET /api/episodes?seriesid[]=N — pure read."""
        url = f"{self._base_url}/api/episodes"
        params = {"seriesid[]": sonarr_series_id}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params,
                                  headers={"X-API-KEY": self._api_key})
        r.raise_for_status()
        data = r.json().get("data", [])
        return [_parse_inventory_item(ep) for ep in data]

    async def fetch_movies(
        self, radarr_movie_id: int
    ) -> list[BazarrInventoryItem]:
        """GET /api/movies?radarrid[]=N — pure read."""
        url = f"{self._base_url}/api/movies"
        params = {"radarrid[]": radarr_movie_id}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params,
                                  headers={"X-API-KEY": self._api_key})
        r.raise_for_status()
        data = r.json().get("data", [])
        return [_parse_inventory_item(m) for m in data]
```

**Wrap transport/HTTP errors in `BazarrError`** (mirroring `DiscoveryError` for `httpx.RequestError` + non-2xx status).

**Key code note:** `test_bazarr` constructs the URL as `f"http://{_normalize_arr_host(body.host)}:{body.port}/api/system/status"` — the new client must follow the same URL construction pattern. [VERIFIED: `web/routes/test_connection.py` line 197]

### Path Reconciliation (D-105)

Bazarr's `path` fields are in Bazarr's container namespace. Pass through `apply_path_mapping(path, settings.path_mappings)` — the same function used for Sonarr/Radarr paths (D-23). If `apply_path_mapping` returns a path that does not exist on disk, treat that inventory entry as invalid for this item and fall back to the filesystem glob for that item. [VERIFIED: existing `apply_path_mapping` contract in `trezarr/paths.py`]

### Language Code Normalization (Critical)

Bazarr `code2` is always a 2-letter code (`"ko"`, `"en"`, `"zh"`). This matches `_LANG_SIDECAR_RE` which captures `[a-z]{2,3}` codes — so Bazarr code2 values feed directly into the ranking function and `find_source_sub` `lang_priority` list. [VERIFIED: `discover/scan.py` `_LANG_SIDECAR_RE`]

**3-letter code edge case:** `_LANG_CODE_RE` in `output/write.py::derive_vi_sidecar_path` only strips 2-letter codes (`[a-z]{2}$`). A source subtitle with a 3-letter code in its filename (e.g. `Show.S01E01.eng.srt`) would produce sidecar `Show.S01E01.en.vi.srt` — incorrect, but this is a pre-existing Phase-3 limitation documented in `scan.py` (MEDIUM #11). Phase 10 does not change this; when Bazarr reports a sub at path `Show.S01E01.eng.srt`, the code2 `"en"` should be used for ranking and the file path used as-is for byte reading. The vi sidecar will be derived from the actual source path — the `_LANG_CODE_RE` 2-letter strip limitation is a separate tracked issue.

---

## Deep Dive: Relational-Fidelity Ranking (SRC-02, D-107)

### Linguistic Justification for the Tier Table

The core insight from PROJECT.md: Chinese, Korean, Japanese, and Thai carry **grammatical relational/honorific information** that English discards. Specifically:

- **Korean (ko):** Speech levels (`haeyoche`, `haeyoche`, `haeyoche`…), kinship honorifics, complex address terms that map to Vietnamese pronoun pairs near-directly.
- **Japanese (ja):** Keigo levels, gendered self-reference (`watashi`, `boku`, `ore`, `atashi`), address suffixes that signal relationship tightly.
- **Chinese (zh):** Kinship address terms (`哥/gē`, `姐/jiě`, etc.), formal/informal address particles.
- **Thai (th):** `phi/nong` elder/younger system, polite particles (`khrap/kha`), which closely parallel Vietnamese `anh/em`.
- **English (en):** No grammatical register or relationship encoding in pronouns. All relationships collapse to `I/you`. This flattens the very information Vietnamese needs to choose `anh`, `em`, `chị`, `chú`, etc.

Vietnamese itself belongs to a separate family (Austroasiatic) but its relational pronoun system structurally resembles East Asian honorific systems more than European ones. [ASSUMED — linguistic claim from training knowledge and PROJECT.md; not independently verified in session]

### Proposed Ranking Algorithm

```python
# trezarr/source_selection/rank.py

# Static relational-richness tiers (D-107).
# Tier value is an integer; LOWER = richer (enables sort).
_TIER: dict[str, int] = {
    # Tier 1 — high relational fidelity for Vietnamese
    "zh": 1, "cmn": 1, "zho": 1,   # Chinese (Mandarin variants)
    "ko": 1, "kor": 1,               # Korean
    "ja": 1, "jpn": 1,               # Japanese
    "th": 1, "tha": 1,               # Thai
    # Tier 2 — moderate relational/honorific marking
    "id": 2, "ind": 2,               # Indonesian (honorifics, register)
    "ms": 2, "msa": 2,               # Malay
    "hi": 2, "hin": 2,               # Hindi (aap/tum/tu register)
    "ta": 2, "tam": 2,               # Tamil (honorific register)
    "ar": 2, "ara": 2,               # Arabic (formal/informal register)
    "tr": 2, "tur": 2,               # Turkish (siz/sen)
    # Tier 3 — flat-relational: universal fallback
    "en": 3, "eng": 3,               # English (the universal fallback)
    # Everything not listed defaults to Tier 2 (generous — better than flat)
}

_DEFAULT_TIER = 2  # unlisted langs treated as Tier 2 (moderate)

ORIGINAL_LANG_BONUS = -0.5  # applied as a sort key fractional bonus

def tier(lang: str) -> float:
    """Return the relational-richness tier for a language code."""
    return _TIER.get(lang.lower(), _DEFAULT_TIER)

def rank_sources(
    available: list[str],            # available language codes (code2)
    original_language: str | None,   # content's original language code (code2)
    per_series_override: list[str] | None = None,
    global_priority: list[str] | None = None,
) -> list[str]:
    """Return available languages ranked by relational richness + original-language bias.

    Step 1: if per_series_override is set and any of its entries are in available,
            return them in override order (first-available-wins), then append
            remaining sources in richness order as fallback.

    Step 2: Sort by (sort_key, lang) where:
            sort_key = tier(lang) + ORIGINAL_LANG_BONUS if lang == original_language else tier(lang)

    Result: original language is preferred when it is relationally rich (ko beats en
    for a Korean drama) but NOT when it is relationally flat and a richer source
    exists for a US show — UNLESS the US show's en is the original language, in
    which case the bonus brings it to tier 2.5 vs zh's 1, so zh still wins for US
    shows. WAIT — this would be wrong for US shows.

    Correct rule: if original_language is Tier 3 (flat) and available langs include
    Tier 1/2, use ORIGINAL_LANG_BONUS ONLY for original-language matching tier ≤ 2.
    Do NOT apply bonus to Tier-3 original languages.
    """
    ...
```

**Decision rule for the US-show nuance:** The bonus applies ONLY when `original_language` is in Tier 1 or Tier 2 (relationally rich). A US show's English source (Tier 3) gets NO bonus — so a `zh` fansub would rank above it. This is wrong: for a US show the native `en` should be preferred.

**Corrected rule:**
- If `original_language` is Tier 1 or 2: apply bonus (prefer original-language source, e.g. `ko` beats `en` for a Korean drama).
- If `original_language` is Tier 3 (e.g. `en`): treat Tier 3 original-language sources as Tier 2.5 — above Tier 3 but below Tier 1/2 — so a legitimate `ko` sub still wins for a US show that happens to have one, but the native `en` is preferred over a fan-translated `fr` or similar.
- Practical effect: for US content with `original_language = en`, ranking is: any Tier-1 (zh/ko/ja/th) > en (2.5) > unlisted-Tier-2 > other-Tier-3.

Wait — this still lets `zh` beat `en` for a US show. The CONTEXT.md says "does NOT displace a native English source with a likely-fan-made foreign sub for genuinely English-original content." The key discriminator is: is the foreign sub likely authoritative or likely a fansub?

**Final algorithm (Claude's discretion):**
- For `original_language in Tier1/2`: rank = tier with bonus (original-language source moves up by 0.5).
- For `original_language == en` (or any Tier 3): rank = tier WITH the following modification: `original_language` source gets **rank 0** (absolute top), regardless of tier. This makes English the winner for genuinely English content, even if Tier-1 subs exist (fan quality presumed lower).

```
sort_key(lang) =
  0.0  if lang == original_language AND tier(original_language) == 3
       [native Tier-3 language IS the best for that show — absolute top]
  tier(lang) - 0.5  if lang == original_language AND tier(original_language) <= 2
       [native Tier-1/2 language preferred within its tier group]
  tier(lang)   otherwise
```

This produces the correct behavior for both cases:
- **Korean drama** (`original_language = ko`): ko gets sort_key = 0.5, en gets 3.0. `ko` wins.
- **US show** (`original_language = en`): en gets sort_key = 0.0 (absolute top), ko gets 1.0. `en` wins.
- **US show, no en sub available** (`original_language = en`, available = [ko, zh]): falls through to Tier-1 winners.

**Tie-breaking:** within the same sort_key, sort by language code alphabetically for determinism. If `global_priority` is provided and ties exist, use global_priority order as the secondary sort within equal sort_keys.

### Language Name → Code Mapping (for `original_language`)

Sonarr and Radarr return `originalLanguage: {id: int, name: str}` — the `name` is a human-readable string ("Korean", "English", "Japanese"). The ranking function needs an ISO-639-1 code. Provide a small lookup table of the common cases:

```python
_ORIG_LANG_NAME_TO_CODE2 = {
    "english": "en", "korean": "ko", "japanese": "ja",
    "chinese": "zh", "thai": "th", "vietnamese": "vi",
    "french": "fr", "german": "de", "spanish": "es",
    "portuguese": "pt", "italian": "it", "russian": "ru",
    "arabic": "ar", "hindi": "hi", "indonesian": "id",
    "malay": "ms", "tamil": "ta", "turkish": "tr",
    # ... extend as needed
}

def normalize_original_language(name: str | None) -> str | None:
    if name is None:
        return None
    return _ORIG_LANG_NAME_TO_CODE2.get(name.lower())
```

For unlisted names, return `None` (fall back to rank-over-available-set). [ASSUMED — training knowledge of ISO-639 mapping; not verified against an official registry in this session]

---

## Deep Dive: `original_language` Capture (D-108)

### Sonarr API

`GET /api/v3/series` (pyarr `client.series.get()`) returns series objects. Each series has:
```json
"originalLanguage": { "id": 1, "name": "English" }
```
Shape: `{"id": int, "name": str}`. [VERIFIED: search result cross-referencing Sonarr API structure] [CITED: https://sonarr.tv/docs/api/]

The `name` field is the human-readable language name. The `id` is Sonarr's internal language integer. For our purposes, extract `series.get("originalLanguage", {}).get("name")` and map to code2 via `normalize_original_language`.

**Code change in `arr/sonarr.py`:** Add `original_language: str | None = None` to `MediaItem` dataclass. In `discover_sonarr_items`, add:
```python
orig_lang_name = series.get("originalLanguage", {}).get("name")
# MediaItem(... original_language=orig_lang_name, ...)
```

### Radarr API

`GET /api/v3/movie` returns movie objects. Same shape:
```json
"originalLanguage": { "id": 1, "name": "English" }
```
[VERIFIED: Radarr API search result] [CITED: https://radarr.video/docs/api/]

**Code change in `arr/radarr.py`:** Same pattern: `movie.get("originalLanguage", {}).get("name")`.

### Persistence in `Series.arr_metadata`

`Series.arr_metadata` is a JSON snapshot column (`dict[str, Any]`) populated by `get_or_create_series` from `arr_metadata_snapshot`. The `MediaItem` fields passed into the snapshot include `genres`, `overview`, `year`, `network`, `runtime`. Adding `original_language` to `MediaItem` means it will appear in the snapshot dict, and `Series.arr_metadata` will carry it.

No schema migration needed for `arr_metadata` — it is already a JSON column; adding a new key to the dict is non-breaking. [VERIFIED: `bible/models.py` Series.arr_metadata `Mapped[dict[str, Any]]`]

When `original_language` is needed for ranking, read `series_dto.arr_metadata.get("original_language")` and normalize.

---

## Deep Dive: Idempotency Under Source-Language Change (D-110)

### Existing Guard Architecture

The idempotency system has three guards, all in `discover/gap.py::is_eligible`:

- **D-26 (never clobber foreign vi):** `vi_path.exists() AND entry is None` → skip. This guard operates on the vi_path derived from the **current candidate source_sub_path**. [VERIFIED: `gap.py` Case 1]
- **D-27 (source hash):** `entry.status == "done" AND vi_path.exists()` → compare content_hash. Skip if unchanged. [VERIFIED: `gap.py` Case 2]
- **D-28 (self-output exclusion):** When Trezarr's own vi sidecar exists, the ledger has an entry with `source_path = source_sub_path` (the source language sub that was used). Next run checks `ledger.check(source_sub_path)` → entry found → Case 2 applies. [VERIFIED: `gap.py` + `ledger_sqla.py` `record()` behavior]

### When the Chosen Source Changes (e.g., `en` → `ko`)

**Scenario:** Episode `Show.S01E01` was previously translated using `Show.S01E01.en.srt`. Now `Show.S01E01.ko.srt` arrives. Phase 10's ranking picks `ko` as the new preferred source.

**What happens with the ledger:**
1. The selection layer now calls `find_source_sub` or resolves Bazarr inventory to `Show.S01E01.ko.srt`.
2. `is_eligible` is called with `source_sub_path = Show.S01E01.ko.srt`.
3. `vi_path = derive_vi_sidecar_path(Show.S01E01.ko.srt)` = `Show.S01E01.vi.srt` (strips `.ko`, appends `.vi.srt`).
4. `entry = await ledger.check("Show.S01E01.ko.srt")` → **None** (never processed from `ko` before).
5. `vi_path.exists()` — does `Show.S01E01.vi.srt` exist? YES (Trezarr wrote it from `en`).
6. `vi_path.exists() AND entry is None` → **Case 1: foreign vi guard fires → SKIP**.

**This is WRONG.** The vi sidecar was written by Trezarr, but the ledger entry is keyed on the `en` source path, not the `ko` source path. The guard correctly concludes "I see a vi sidecar but have no ledger record for this source path — this looks like a foreign vi sidecar — skip."

**Root cause:** The ledger is keyed on `source_sub_path`. When the source changes, the new source path has no ledger entry, and the guard cannot distinguish "our vi sidecar (from a different source)" from "a foreign vi sidecar."

**Resolution options:**

**Option A (Recommended — simplest, lowest regression risk):** Before calling `is_eligible`, check if the vi sidecar path was written by Trezarr with ANY source sub for this episode. The ledger has `output_path` — query for any entry where `output_path == vi_path`. If found (Trezarr wrote this vi), then the "foreign vi guard" should not fire. This requires a new `ledger.check_by_output_path(vi_path: str)` method on `LedgerSQLA`.

The guard in `gap.py` becomes:
```
Case 1: vi_path.exists() AND ledger_entry_for_source is None
        AND ledger.check_by_output_path(vi_path) is None
        → foreign vi guard (D-26 intact)

New Case 1.5: vi_path.exists() AND ledger_entry_for_source is None
              AND ledger.check_by_output_path(vi_path) is not None
              → "Trezarr wrote this vi from a different source path — re-translate from richer source"
              → eligible = True, reason = "richer source available — re-translating"
```

This way:
- D-26 (never clobber foreign vi) is preserved: a truly foreign vi (not in the ledger at all) is still skipped.
- D-27 (source hash idempotency) is preserved: if the new source (`ko`) hasn't changed since it was last translated (if it was ever translated), the hash still gates.
- D-28 (self-output exclusion) is preserved: the ledger provenance chain is intact; we check by output_path as the secondary key.

**No infinite loop risk:** After re-translation from `ko`, the ledger records `source_path = ko.srt, output_path = vi.srt, status = done`. Next run: `is_eligible(ko.srt)` → entry found → Case 2 → compare hash → skip if unchanged.

**Option B (Alternative):** Do not change `gap.py` at all. Instead, make the source-selection layer prefer the source whose `source_sub_path` already has a ledger entry, to avoid triggering Case 1. This is fragile: it rewards the previously-used source over the richer source, which defeats the purpose.

**Recommendation: Option A.** Add `check_by_output_path` to `LedgerSQLA` and add Case 1.5 to `is_eligible`.

**Loop prevention:**
- The re-translate case (Case 1.5) fires once. After translation, the ledger records the new `ko` source. Next run: `is_eligible(ko.srt)` → Case 2 applies (done + vi exists + hash unchanged) → already_done. No loop. [VERIFIED: reasoning from `gap.py` Case 2 logic]

**D-26 preserved:** A truly foreign vi (written by Bazarr or another tool, not in the ledger) still has `check_by_output_path` returning None → Case 1 fires → skip. [VERIFIED: reasoning from `ledger_sqla.py` — Trezarr only records entries it writes]

**`ScanStats.already_done` counter:** For Case 1.5, use a new reason string like "richer source available — re-translating" and classify it in `scan_for_eligible_items` — should NOT increment `already_done`. Add a new `scan_stats.source_upgraded` counter (optional — could also just use a distinct reason string and leave it classified under a new field or the generic info log).

---

## Deep Dive: Per-Series Overrides (SVC-05, D-111/D-112/D-113/D-114)

### Alembic Migration 0003

Following the 0002 template exactly (verified from `alembic/versions/0002_job_queue.py`):

```python
# alembic/versions/0003_per_series_overrides.py
revision = "0003"
down_revision = "0002"

def upgrade() -> None:
    op.add_column("series", sa.Column(
        "source_lang_override", sa.JSON, nullable=True, server_default=sa.text("NULL")
    ))
    op.add_column("series", sa.Column(
        "model_override", sa.String, nullable=True, server_default=sa.text("NULL")
    ))

def downgrade() -> None:
    op.drop_column("series", "model_override")
    op.drop_column("series", "source_lang_override")
```

No index needed (per-series lookup is always by `series.id`). No FK constraints — nullable columns on an existing table. Reversible as required by D-69/D-37. [VERIFIED: pattern from `alembic/versions/0002_job_queue.py` + `db/migration_runner.py`]

**Model update:** In `bible/models.py::Series`:
```python
source_lang_override: Mapped[list[str] | None] = mapped_column(JSON, default=None)
model_override: Mapped[str | None] = mapped_column(String, default=None)
```

**DTO update:** In `bible/dto.py::SeriesDTO`:
```python
source_lang_override: list[str] | None = None
model_override: str | None = None
```
No alias needed — no shadowing risk with these names. [VERIFIED: `dto.py` only has shadowing issue with `register`]

### `resolve_effective_settings()` Pure Function (D-112)

```python
# trezarr/source_selection/resolve.py

def resolve_effective_settings(
    series_dto: "SeriesDTO | None",
    settings: "TrezarrSettings",
) -> tuple[list[str], str | None, str]:
    """Resolve effective (source_priority, register, model) for one series.

    Per-series non-NULL overrides win over global config.
    Series.register is the register override (Phase-8 lock = the override valve).

    Returns:
        (source_priority, register, model) — all three resolved.
        source_priority: ordered list of source language codes
        register: str | None (None = no register set)
        model: str — always a valid string (falls back to settings.llm_model)
    """
    if series_dto is None:
        return settings.source_lang_priority, None, settings.llm_model

    source_priority = (
        series_dto.source_lang_override
        if series_dto.source_lang_override is not None
        else settings.source_lang_priority
    )
    register = series_dto.register_value  # uses the alias-aware attribute name
    model = (
        series_dto.model_override
        if series_dto.model_override is not None
        else settings.llm_model
    )
    return source_priority, register, model
```

Pure — no I/O, no ORM imports. Unit-testable in isolation. [VERIFIED: design mirrors `reconcile_attributions` precedence-function approach from Phase 5]

**Integration points:** `process_one_item` in `cli.py` → call `resolve_effective_settings(series_dto, settings)` before calling `translate_file`. The `series_dto` is already available because `get_or_create_series` is called early in the pipeline. The `web/worker.py` → `_execute_job` → `process_one_item` path inherits this. `web/scheduler.py` polls → `scan_for_eligible_items` → `process_one_item` — same path. [VERIFIED: `cli.py::process_one_item` + `web/worker.py` D-62 comment]

### Model Per-Call Threading (D-113)

`LLMClient.call()` uses `self._model` hardcoded into each `parse()` / `create()` call:
```python
# Current (client.py lines 127, 164, 175):
parsed = await self._client.chat.completions.parse(model=self._model, ...)
resp = await self._client.chat.completions.create(model=self._model, ...)
```

The OpenAI SDK accepts `model` per call — it is not baked into the client at construction time. The change is:

```python
# Modified LLMClient.call() signature:
async def call(
    self,
    messages: list[dict],
    response_model: type[BaseModel] | None = None,
    model: str | None = None,   # NEW: per-call override (D-113)
) -> BaseModel | str:
    ...

# Inside _call_with_fallback, use: effective_model = model or self._model
```

The single `_semaphore` still wraps `self._call_with_fallback(...)` — the model override does not affect concurrency. [VERIFIED: `llm/client.py` `_call_with_fallback` — model is just a string passed to each SDK call]

**Engine threading:** `translate_file()` signature gains an optional `model: str | None` parameter, passed down through `_make_translate_batch_fn` → `_translate_batch_inner(... llm_client, ...)` → `llm_client.call(... model=model)`. Alternatively, pass model to `translate_file` which passes it to `llm_client.call`. [VERIFIED: `engine.py` `_translate_batch_inner` already passes `llm_client` explicitly; adding `model` parameter is straightforward]

**Register threading:** `build_translate_prompt()` already accepts `source_lang: str = "English"` but the `register` from the effective settings should be injected into the system prompt. Currently `translate_file` passes `series_bible_dto.register` to the prompt construction. With per-series register override (via Phase-8 lock), this is already handled — `series_bible_dto.register_value` is whatever the effective register is, including a human-set lock. No additional wiring needed for register beyond the Phase-8 mechanism. [VERIFIED: Phase 8 STATE.md — locked register survives re-analysis and is used in prompts]

### Overrides REST Endpoint (D-114)

Following the Phase-8 router pattern in `web/routes/bible.py`:

```python
@router.patch("/series/{series_id}/overrides")
async def patch_series_overrides(
    series_id: int,
    body: SeriesOverridesRequest,
    request: Request,
) -> JSONResponse:
    """PATCH source_lang_override and model_override for a series (SVC-05)."""
    ...

class SeriesOverridesRequest(BaseModel):
    source_lang_override: list[str] | None = None  # None = clear override
    model_override: str | None = None              # None = clear override
```

The route imports no SQLAlchemy — it goes through a `set_series_overrides(session_factory, series_id, ...)` store writer (D-39 boundary). The writer re-reads the row in-txn, updates the nullable columns, and emits a `BibleEvent` with `source="import"` for audit. [VERIFIED: D-39 pattern from Phase-8 routes; `apply_human_edit_*` writers in `bible/store.py`]

**Register override:** The `PATCH /series/{id}/register` endpoint already exists from Phase 8. Per D-111, register override = Phase-8 lock. No new endpoint needed. [VERIFIED: `web/routes/bible.py` existing `PATCH /series/{id}/register` handler]

### Overrides UI (D-114 — React SPA)

Extend `BibleEditor.tsx` with an "Overrides" section below the "Register" section:
- **Source Language Preference:** A reorderable list (or multiselect) showing the current effective priority (`series.source_lang_override || globalDefault`). Show provenance: "inherited from global config" vs "per-series override". A "Clear Override" button.
- **Model Override:** A text input. Placeholder: `settings.llm_model` (the global default). Show provenance. A "Clear Override" button.
- **Register Override:** Already in BibleEditor as a `<LockToggleButton>` — no change needed.

Reuse `api/client.ts` pattern from Phase 8. The new client wrapper:
```typescript
export async function patchSeriesOverrides(
    seriesId: number,
    overrides: { source_lang_override?: string[] | null; model_override?: string | null }
): Promise<SeriesDTO> { ... }
```

---

## Common Pitfalls

### Pitfall 1: Bazarr `X-API-KEY` header case
**What goes wrong:** Using `"X-Api-Key"` (as in `test_bazarr`) works because HTTP headers are case-insensitive, but Bazarr's auth check reads `request.headers["X-API-KEY"]`. Both work.
**How to avoid:** Use `"X-API-KEY"` in the new client to match Bazarr's own authorizations definition. Test with an actual running Bazarr instance (human UAT).
**Warning signs:** `401 Unauthorized` response even with correct API key.

### Pitfall 2: Bazarr `seriesid[]` vs `seriesId` — Query Parameter Array Syntax
**What goes wrong:** `httpx` params with `{"seriesid[]": 123}` passes the literal `"seriesid[]"` as the parameter name. Flask-RESTX's `reqparse` reads `request.args.getlist("seriesid[]")` — the brackets are part of the key name. `httpx` must send it as `?seriesid%5B%5D=123`.
**How to avoid:** Use `httpx` params as a list of tuples: `params=[("seriesid[]", sonarr_id)]` or pass `"seriesid[]=123"` in the URL string.
**Warning signs:** Bazarr returns 404 (the episodes handler returns 404 when neither `seriesid[]` nor `episodeid[]` are provided).

### Pitfall 3: Foreign vi guard fires for source-language upgrade (D-110)
**What goes wrong:** When `ko.srt` appears and `en.srt` was already translated, `is_eligible(ko.srt)` finds the vi sidecar but no ledger entry for `ko.srt` → Case 1 fires → skips the upgrade.
**How to avoid:** Implement Option A from the D-110 analysis: add `check_by_output_path` to LedgerSQLA and Case 1.5 to `is_eligible`. [See Deep Dive: Idempotency above]
**Warning signs:** Richer source arrives, no re-translation triggered, `ScanStats.foreign_vi` counter increments unexpectedly.

### Pitfall 4: `derive_vi_sidecar_path` only strips 2-letter codes
**What goes wrong:** If Bazarr provides a path like `Show.S01E01.jpn.srt` (3-letter code), `derive_vi_sidecar_path` does not strip `.jpn`, producing `Show.S01E01.jpn.vi.srt` instead of `Show.S01E01.vi.srt`.
**How to avoid:** Normalize 3-letter codes in the source-selection layer before passing to `find_source_sub`/scan. The `_LANG_SIDECAR_RE` already supports 2–3 letter codes for detection; `_LANG_CODE_RE` in `write.py` needs a corresponding fix (2-to-3 letter strip) OR always prefer Bazarr `code2` (always 2-letter) as the canonical code.
**Warning signs:** Two vi sidecars exist for the same episode (one with correct name, one with 3-letter code embedded).

### Pitfall 5: `original_language` name not in the lookup table
**What goes wrong:** Sonarr/Radarr returns `originalLanguage.name = "Cantonese"` which doesn't map to any code → `normalize_original_language` returns `None` → ranking treats it as no original language signal → may miss the East-Asian bias.
**How to avoid:** Ensure the lookup table covers the common East-Asian language names. Use a fallback: if `name` matches Tier-1 patterns (contains "Chinese", "Korean", "Japanese", "Thai"), default to Tier-1 behavior even without a code.
**Warning signs:** Korean dramas getting ranked to `en` even though `ko` sub is available.

### Pitfall 6: D-06 violated by adding a second LLM semaphore for model overrides
**What goes wrong:** A developer creates a second `LLMClient` instance with a different `_model` to handle per-series model overrides, creating a second `asyncio.Semaphore` that bypasses D-06's global cap.
**How to avoid:** The per-call `model` parameter approach (D-113) is the canonical solution. Never construct a second `LLMClient`. [VERIFIED: D-06 constraint + CONTEXT.md D-113]
**Warning signs:** Two `asyncio.Semaphore` instances in the call stack.

### Pitfall 7: `source_lang_override` stored as JSON with `list` default
**What goes wrong:** SQLAlchemy `JSON` column with `Mapped[list[str] | None]` and `default=None` — if `default=list` is accidentally used instead, every row that doesn't set an override gets an empty list `[]` instead of `NULL`. An empty list `[]` would be truthy-but-empty, breaking the `is not None` check in `resolve_effective_settings`.
**How to avoid:** Use `default=None` for the column, not `default=list`. Ensure the store writer writes `None` (not `[]`) when clearing an override.

### Pitfall 8: Bazarr episodes endpoint requires at least one `seriesid[]` or `episodeid[]`
**What goes wrong:** Calling `GET /api/episodes` with no query params returns `404`. There is no "get all episodes" endpoint.
**How to avoid:** Always pass `seriesid[]` when fetching episode inventory. Build the inventory per-series (matching the Sonarr/Radarr discovery model).

---

## Code Examples

### Bazarr Inventory Client Pattern

```python
# Source: bazarr/api/utils.py + bazarr/api/episodes/episodes.py (VERIFIED)
# trezarr/arr/bazarr.py

async def fetch_episodes(self, sonarr_series_id: int) -> list[BazarrInventoryItem]:
    url = f"{self._base_url}/api/episodes"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                url,
                params=[("seriesid[]", sonarr_series_id)],  # array syntax
                headers={"X-API-KEY": self._api_key},
            )
        r.raise_for_status()
        data = r.json().get("data", [])
        return [_parse_inventory_item(ep) for ep in data]
    except httpx.RequestError as exc:
        display_host = _normalize_arr_host(self._host)
        raise BazarrError(
            f"Bazarr inventory fetch failed at {display_host}: {type(exc).__name__}: {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        display_host = _normalize_arr_host(self._host)
        raise BazarrError(
            f"Bazarr inventory HTTP {exc.response.status_code} at {display_host}"
        ) from exc
```

### Source Ranking Pattern

```python
# trezarr/source_selection/rank.py (DESIGNED in this research)

def sort_key(lang: str, original_language: str | None) -> float:
    """Lower = preferred."""
    t = _TIER.get(lang.lower(), _DEFAULT_TIER)
    if original_language and lang.lower() == original_language.lower():
        if t == 3:  # flat-relational original language (e.g. en for US shows)
            return 0.0  # absolute top: native source wins over any fansub
        else:       # rich-relational original language (e.g. ko for K-dramas)
            return t - 0.5  # bonus: prefer within tier group
    return float(t)

def rank_sources(
    available: list[str],
    original_language: str | None,
) -> list[str]:
    return sorted(
        set(lang.lower() for lang in available),
        key=lambda lang: (sort_key(lang, original_language), lang),
    )
```

### `check_by_output_path` Ledger Extension

```python
# trezarr/output/ledger_sqla.py (DESIGNED in this research)

async def check_by_output_path(self, output_path: str | Path) -> LedgerEntry | None:
    """Return any ledger entry whose output_path matches — secondary D-110 check."""
    key = str(output_path)
    async with self._session_factory() as session:
        result = await session.execute(
            select(ProcessedFile).where(ProcessedFile.output_path == key)
        )
        row = result.scalar_one_or_none()
        return _row_to_entry(row) if row is not None else None
```

### Migration 0003 Pattern

```python
# alembic/versions/0003_per_series_overrides.py
# Source: pattern from alembic/versions/0002_job_queue.py (VERIFIED)
revision = "0003"
down_revision = "0002"

def upgrade() -> None:
    op.add_column("series", sa.Column(
        "source_lang_override", sa.JSON, nullable=True,
    ))
    op.add_column("series", sa.Column(
        "model_override", sa.String, nullable=True,
    ))

def downgrade() -> None:
    op.drop_column("series", "model_override")
    op.drop_column("series", "source_lang_override")
```

### Per-Call Model Override in LLMClient

```python
# trezarr/llm/client.py (DESIGNED based on verified OpenAI SDK behavior)
async def call(
    self,
    messages: list[dict],
    response_model: type[BaseModel] | None = None,
    model: str | None = None,           # NEW: per-call override (D-113)
) -> BaseModel | str:
    async with self._semaphore:         # D-06: same semaphore, unchanged
        return await self._call_with_fallback(
            messages, response_model,
            effective_model=model or self._model,   # per-call or global default
        )

async def _call_with_fallback(
    self,
    messages,
    response_model,
    effective_model: str,               # NEW: resolved model string
) -> BaseModel | str:
    ...
    parsed = await self._client.chat.completions.parse(
        model=effective_model,          # was self._model
        messages=messages,
        **parse_kwargs,
    )
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bazarr API path array params | Custom URL string builder | `httpx` params as list of tuples `[("seriesid[]", id)]` | httpx handles percent-encoding of `[]` |
| Language code ↔ name mapping | New lookup service or regex | Small lookup dict in `rank.py` + fallback for unlisted | 20-line dict covers 95% of content; rest falls back gracefully |
| Second LLM client for model override | New `LLMClient(model=...)` per series | Per-call `model` param on existing `LLMClient.call()` | Preserves D-06 single semaphore |
| Per-series settings storage | `config.yaml` series map or extra table | Nullable columns on existing `series` row | Referential integrity, atomic updates, no config-file races |
| Idempotency re-keying on source change | New idempotency scheme | `check_by_output_path` + Case 1.5 in `is_eligible` | Minimal change; preserves all three existing D-26/27/28 guards |

---

## State of the Art

| Old Approach (Phase 3) | Phase 10 Approach | Change | Impact |
|------------------------|-------------------|--------|--------|
| `source_lang_priority = ["en"]` glob only | Bazarr inventory ∪ filesystem, richness-ranked | Phase 10 | Source selection becomes content-aware |
| No `original_language` in MediaItem | `original_language` captured from Sonarr/Radarr `originalLanguage` field | Phase 10 | Ranking can distinguish native vs. fansub sources |
| Ledger keyed on source_sub_path, no output_path lookup | Add `check_by_output_path` secondary lookup | Phase 10 | Source-language upgrade no longer blocked by foreign-vi guard |
| Global `llm_model` only | Per-call `model` override from series.model_override | Phase 10 | Power users can use stronger model for specific series |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The relational-richness tier ordering (Tier 1: zh/ko/ja/th; Tier 2: id/ms/hi/ta/ar/tr; Tier 3: en) is linguistically sound for Vietnamese translation quality | Ranking Algorithm | Vietnamese translators may disagree; Thai (`th`) in particular is debated — but the core zh/ko/ja advantage is well-established |
| A2 | `normalize_original_language` lookup table correctly maps the language names Sonarr/Radarr return | original_language capture | If Sonarr returns "Cantonese" or "Mandarin" instead of "Chinese", mapping fails; fallback returns None (degrades gracefully) |
| A3 | Bazarr's `code2` is always a 2-letter ISO-639-1 code (never a 3-letter code) | Bazarr API | Verified from `postprocessEpisode()` source — `code2 = subtitle[0]` which is the alpha2 from `language_from_alpha2` |
| A4 | The `sort_key = 0.0` rule (native Tier-3 language wins absolutely) is the right behavior for US shows | Ranking Algorithm | If user has a `zh` or `ko` sub for a US show and wants to use it, the global or per-series override is the correct mechanism — the default should prefer native English |
| A5 | ISO-639-2 three-letter code variants (zho, kor, jpn) in `_TIER` correctly cover all expected Bazarr 3-letter code values | Ranking Algorithm | Bazarr always emits code2 (2-letter) for the subtitle entries; 3-letter variants in _TIER are for robustness with `original_language` normalization which may return 3-letter codes |

---

## Open Questions

1. **Bazarr `seriesid[]` maps to which ID?**
   - What we know: The episodes endpoint filters by `sonarrSeriesId` in the query; the parameter `seriesid[]` accepts integers.
   - What's unclear: Is `seriesid[]` the Sonarr internal series ID (same as `MediaItem.series_id` from `discover_sonarr_items`) or a Bazarr-internal ID?
   - From the source: `stmt.where(TableEpisodes.sonarrSeriesId.in_(seriesId))` — it IS the Sonarr series ID. [VERIFIED]
   - **Answer: Use `media_item.series_id` (the Sonarr series ID) as the `seriesid[]` parameter.**

2. **Does Bazarr update its inventory synchronously?**
   - What we know: Bazarr watches for new subs and updates its database; the API reflects the current DB state.
   - What's unclear: Is there a race between a new `ko.srt` appearing on disk and Bazarr reporting it in the inventory?
   - Recommendation: The D-104 dual-mode (Bazarr ∪ filesystem) naturally handles this: if Bazarr hasn't picked up a new sub yet, the filesystem glob finds it. No special handling needed.

3. **`model_override` validation against the configured endpoint**
   - What we know: The LLM endpoint is user-configured; model names are opaque strings.
   - What's unclear: Should Phase 10 validate `model_override` by probing the endpoint?
   - Recommendation: No validation — store as-is. If the model name is wrong, the LLM call fails at translation time with an informative error. Probing adds complexity and may not be possible for all endpoint types. (Claude's Discretion per CONTEXT.md)

---

## Environment Availability

All dependencies are pre-existing. No new external services are required beyond those already configured (Sonarr/Radarr/Bazarr + LLM endpoint).

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| httpx | BazarrClient | ✓ | 0.28.x (pre-installed via openai) | — |
| SQLAlchemy async | Migration 0003 | ✓ | 2.0.50 (pre-installed) | — |
| Alembic | Migration 0003 | ✓ | 1.18.x (pre-installed) | — |
| Bazarr instance | INTG-02 live testing | Operator-dependent | — | filesystem glob (D-104) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Bazarr instance (INTG-02 human UAT requires it; automated tests use fixtures).

---

## Validation Architecture

> `workflow.nyquist_validation = true` — this section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pytest.ini` / `pyproject.toml` (existing) |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTG-02 | `BazarrClient.fetch_episodes()` parses correct subtitle entries from fixture | unit | `pytest tests/arr/test_bazarr.py -x` | ❌ Wave 0 |
| INTG-02 | `BazarrClient.fetch_movies()` parses correct subtitle entries from fixture | unit | `pytest tests/arr/test_bazarr.py::test_fetch_movies -x` | ❌ Wave 0 |
| INTG-02 | BazarrError raised on 4xx / connection failure | unit | `pytest tests/arr/test_bazarr.py::test_bazarr_error -x` | ❌ Wave 0 |
| INTG-02 | Bazarr-reported path is passed through `apply_path_mapping` | unit | `pytest tests/arr/test_bazarr.py::test_path_mapping -x` | ❌ Wave 0 |
| SRC-01 | `rank_sources()` returns all available langs when original_language=None | unit | `pytest tests/source_selection/test_rank.py -x` | ❌ Wave 0 |
| SRC-02 | `rank_sources(["en","ko"], original_language="ko")` → `["ko","en"]` (K-drama) | unit | `pytest tests/source_selection/test_rank.py::test_korean_drama -x` | ❌ Wave 0 |
| SRC-02 | `rank_sources(["ko","en"], original_language="en")` → `["en","ko"]` (US show) | unit | `pytest tests/source_selection/test_rank.py::test_us_show -x` | ❌ Wave 0 |
| SRC-02 | `rank_sources(["zh","en"], original_language=None)` → `["zh","en"]` (tier order) | unit | `pytest tests/source_selection/test_rank.py::test_tier_order -x` | ❌ Wave 0 |
| D-109 | Fallback chain: per-series override > richness ranking > global priority > any | unit | `pytest tests/source_selection/test_rank.py::test_fallback_chain -x` | ❌ Wave 0 |
| D-110 | `is_eligible` Case 1.5: vi sidecar exists from different source → re-translate | unit | `pytest tests/discover/test_gap.py::test_source_upgrade_eligible -x` | ❌ Wave 0 |
| D-110 | `is_eligible` Case 1 still fires for genuinely foreign vi | unit | `pytest tests/discover/test_gap.py::test_foreign_vi_unchanged -x` | ❌ Wave 0 |
| D-110 | No loop: after ko translation, subsequent scan skips (D-27 hash check) | unit | `pytest tests/discover/test_gap.py::test_no_loop_after_upgrade -x` | ❌ Wave 0 |
| SVC-05 | `resolve_effective_settings(series_with_override, settings)` → per-series wins | unit | `pytest tests/source_selection/test_resolve.py -x` | ❌ Wave 0 |
| SVC-05 | `resolve_effective_settings(series_with_null_override, settings)` → global wins | unit | `pytest tests/source_selection/test_resolve.py::test_null_inherits_global -x` | ❌ Wave 0 |
| SVC-05 | Migration 0003 `upgrade()` adds nullable columns on series table | unit | `pytest tests/db/test_migration_0003.py -x` | ❌ Wave 0 |
| SVC-05 | Migration 0003 `downgrade()` removes columns cleanly | unit | `pytest tests/db/test_migration_0003.py::test_downgrade -x` | ❌ Wave 0 |
| SVC-05 | `LLMClient.call(model="override-model")` uses override, not `self._model` | unit | `pytest tests/llm/test_client.py::test_per_call_model_override -x` | ❌ Wave 0 |
| SVC-05 | `PATCH /series/{id}/overrides` stores source_lang_override + model_override | integration | `pytest tests/web/test_bible_api.py::test_patch_overrides -x` | ❌ Wave 0 |
| D-108 | Sonarr `discover_sonarr_items` captures `original_language` into MediaItem | unit | `pytest tests/arr/test_sonarr.py::test_original_language -x` | ❌ Wave 0 |
| D-108 | Radarr `discover_radarr_items` captures `original_language` into MediaItem | unit | `pytest tests/arr/test_radarr.py::test_original_language -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/arr/test_bazarr.py` — covers INTG-02 Bazarr client
- [ ] `tests/source_selection/__init__.py` — package init
- [ ] `tests/source_selection/test_rank.py` — covers SRC-01/SRC-02 ranking
- [ ] `tests/source_selection/test_resolve.py` — covers D-112 resolve function
- [ ] `tests/db/test_migration_0003.py` — covers migration 0003 up/down
- [ ] `tests/discover/test_gap.py` — extend with D-110 Case 1.5 + no-loop tests
- [ ] `tests/llm/test_client.py` — extend with per-call model override test
- [ ] `tests/web/test_bible_api.py` — extend with PATCH /series/{id}/overrides test
- [ ] `tests/arr/test_sonarr.py` + `tests/arr/test_radarr.py` — extend with `original_language` capture tests

---

## Security Domain

> `security_enforcement: true`, ASVS level 1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — D-78 single-user trusted-LAN; Bazarr API key is internal |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A — same D-78 posture as Phases 7/8 |
| V5 Input Validation | Yes | `source_lang_override` list: validate that items are 2–3 letter alphanumeric codes; `model_override`: validate as non-empty string or null; Pydantic validators |
| V6 Cryptography | No | API key transmitted over trusted LAN HTTP — same posture as Sonarr/Radarr keys |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| `source_lang_override` injection of arbitrary strings | Tampering | Validate as list of 2–3 letter lowercase codes via Pydantic `field_validator`; reject unknown patterns |
| `model_override` injection — overly long string passed to OpenAI SDK | Tampering | `model_override: str | None` validated as max 128 chars (reasonable model name length) |
| Bazarr API key in logs | Information Disclosure | `_normalize_arr_host` strips credentials from host; API key resolved via `SecretStr.get_secret_value()` only at client boundary (D-11); never logged |
| Bazarr-reported `path` traversal | Tampering | Path already runs through `apply_path_mapping` + `assert_within_media_roots` before use |

---

## Sources

### Primary (HIGH confidence)
- Bazarr source code: `bazarr/api/episodes/episodes.py` + `bazarr/api/movies/movies.py` + `bazarr/api/utils.py` + `bazarr/api/__init__.py` + `bazarr/api/swaggerui.py` — verified endpoint URLs, response shapes, auth header, subtitles array structure
- Project codebase (live read): `trezarr/arr/__init__.py`, `sonarr.py`, `radarr.py`, `web/routes/test_connection.py`, `discover/scan.py`, `discover/gap.py`, `output/ledger_sqla.py`, `output/write.py`, `llm/client.py`, `bible/models.py`, `bible/dto.py`, `db/migration_runner.py`, `alembic/versions/0002_job_queue.py`, `translate/engine.py`, `web/routes/bible.py`, `web/worker.py`, `cli.py`, `config.py`
- `.planning/phases/10-source-selection-per-series-overrides/10-CONTEXT.md` — locked decisions D-103..D-114

### Secondary (MEDIUM confidence)
- Sonarr API: `originalLanguage: {id: int, name: str}` verified via WebSearch + Sonarr forum / Go package docs — [https://sonarr.tv/docs/api/](https://sonarr.tv/docs/api/)
- Radarr API: same `originalLanguage` shape — [https://radarr.video/docs/api/](https://radarr.video/docs/api/)
- Bazarr GitHub repo (morpheus65535/bazarr) — API archive code (`bazarr/api.py` at historical commit) showing `postprocessEpisode` subtitle construction

### Tertiary (LOW confidence / ASSUMED)
- Language tier table (zh/ko/ja/th vs. en) — based on linguistic properties described in PROJECT.md and training knowledge; not independently verified against translation quality studies this session
- `normalize_original_language` language name → code2 mapping table — training knowledge of common language names; not verified against Sonarr/Radarr's actual `originalLanguage.name` enumeration

---

## Metadata

**Confidence breakdown:**
- Bazarr API endpoints/shapes: HIGH — verified from live source code
- Sonarr/Radarr `originalLanguage` shape: MEDIUM — verified from API docs search + Go package source
- Relational-fidelity tier table: MEDIUM — grounded in PROJECT.md + linguistic logic; exact tier 2 membership is Claude's discretion
- Ranking algorithm sort-key: HIGH (as a design choice consistent with CONTEXT.md D-107) — the algorithm correctly handles the stated nuances
- Idempotency D-110 analysis: HIGH — verified by tracing through gap.py + ledger_sqla.py code
- Migration 0003 pattern: HIGH — verified from 0002 template
- Model per-call threading: HIGH — OpenAI SDK documented to accept model per-call; verified from client.py structure

**Research date:** 2026-06-02
**Valid until:** 2026-07-02 (Bazarr API is stable; language tier table is stable; both sides of the project code are locked at Phase 8 head)
