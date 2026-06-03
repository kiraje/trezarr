# Phase 13: Backend Episodes Enrichment - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Rewrite `GET /api/library/series/{series_id}/episodes` to return **season-grouped
Sonarr episode RECORDS** (not just episode-file rows) carrying `audio_languages`,
a Bazarr `subtitles[]` inventory, `episode_key`, and Trezarr `status` — always
HTTP 200 with a `bazarr_available` flag — and extend the **Series + Movies list
items** on `GET /api/library` with `translated_count` / `total_count`. This is
**backend-only**: no frontend consumes the new shape until Phase 14 (it can land
in parallel with the Phase-12 shell work).

**In scope:**
- `trezarr/web/routes/library.py` — rewrite `get_series_episodes` to the
  `research/ARCHITECTURE.md §4` JSON contract (season groups, episode records,
  audio + subtitle badges, fail-soft envelope); wrap all pyarr calls in
  `asyncio.to_thread` (fixes the latent sync-in-async event-loop block).
- `trezarr/web/routes/library.py` — extend `get_library` series + movies items
  with `translated_count` / `total_count` (API-02).
- A new DB **count helper** for per-series completed `vi` output counts (the
  ledger exposes no count method today).
- Backend test coverage: Bazarr fail-soft path, correct `episode.id` (not
  `episodeFile.id`) join to Bazarr, the audio full-name→ISO lookup, and the
  count semantics.

**Out of scope (later phases — do NOT touch):**
- Frontend `Series.tsx` / `SeriesDetail.tsx` / `Movies.tsx` consuming this
  contract → Phase 14.
- NAV-03 sidebar **count badge** + **LIVE** badge (which consume the
  `translated_count` this phase exposes) → Phase 14.
- App shell / route restructure → Phase 12 (sibling phase, in flight).
- Any change to the translation engine/pipeline beyond *ensuring* the ledger's
  `series_id` is populated if the count requires it (see D-03 verification).

</domain>

<decisions>
## Implementation Decisions

### Enriched Episodes Endpoint (API-01)
- **D-01:** Rewrite per `research/ARCHITECTURE.md §4`: call
  `client.episode.get(series_id=N)` for episode **records** (one per episode,
  file or not) alongside `client.episode_file.get(series_id=N)`; build an
  `episodeFile.id → episodeFile` lookup; **group by `seasonNumber` server-side**;
  return the §4 envelope:
  `{ series_id, bazarr_available, seasons: [{ season_number, episodes: [...] }], errors: [] }`.
  **Wrap every pyarr call in `asyncio.to_thread`** (current handler calls sync
  pyarr inside `async def` — a latent event-loop block; the enriched version adds
  calls, so this is mandatory). Season 0 (Specials) is **included**, not filtered.
- **D-02:** Each subtitle badge object carries `code2`, `code3`, `hi`, **and
  `forced`** — API-01 explicitly requires `hi`/`forced`; `research/ARCHITECTURE.md`
  §4 omitted `forced`, so add it. **Strip subtitle file paths** (badges need only
  the codes + flags; do not expose container paths). Join Bazarr inventory to
  episodes by `BazarrInventoryItem.arr_id == episode.id` (`sonarrEpisodeId`) —
  the correct join key is the episode **record** id, NOT `episodeFile.id`.

### Episode Key
- **D-03 (key):** `episode_key = f"S{seasonNumber:02d}E{episodeNumber:02d}"` built
  from the **authoritative Sonarr episode-record ints**. Retire
  `_episode_key_from_file` for this endpoint — it was a workaround for episode-FILE
  records lacking authoritative numbers; episode records have them. Donghua / `NxNN`
  naming is handled because Sonarr's own numbering is authoritative regardless of
  filename. The `status` (`translated`/`has_source`/`nothing`) stays
  **filesystem-based** (`.vi.{srt,ass,vtt}` next to the video), so it does not
  depend on key format.

### Progress Counts (API-02)
- **D-04 (total):** `total_count` = Sonarr series `statistics.episodeFileCount`
  (already present in the `series.get()` payload — **no extra API call**). For a
  movie: `total_count = 1` when `hasFile` else `0`.
- **D-05 (translated):** `translated_count` = number of completed `vi` outputs
  per series from the Trezarr DB:
  `COUNT(processed_file) WHERE series_id = str(series_id) AND status = 'done'`.
  The ledger has **no count method** → add a **store/count helper**, ideally a
  **bulk** query (`translated_counts_for_series(ids) -> {series_id: n}`) so the
  list endpoint makes one aggregate query, not N. Key by `str(series_id)` (ledger
  `series_id` is `str`; Sonarr id is `int`). For a movie, derive `translated_count`
  from the existing per-movie filesystem `vi` check (consistent with today's
  `source_sub_found` cost) or the ledger by output path.
- **D-06 (CRITICAL verification — planner must confirm):** `LedgerEntry.series_id`
  is `str | None` and documented "reserved for Phase-4 FK". If the engine does
  **not** reliably populate `ProcessedFile.series_id` at translate time, the
  per-series count is silently wrong. The planner MUST verify population and, if
  needed, ensure `series_id` is recorded (or pick a documented fallback). Do not
  ship the count assuming `series_id` is set without checking.

### Audio Language Normalization (API-01)
- **D-07:** Normalize `mediaInfo.audioLanguages` **full names → ISO-639-1
  `code2`** in the backend ('Korean'→'ko') — API-01's success criterion names this
  lookup. **Reuse/extend the existing language constants in
  `trezarr/source_selection/rank.py`** if suitable; otherwise add a small mapping
  dict. Split `/`-joined values, dedupe preserving order, and map unknown
  languages to the lowercased original (or `'und'`). `audio_languages = []` when
  there is no file / no `mediaInfo`.

### Fail-Soft Contract
- **D-08:** **Bazarr → always HTTP 200.** Disabled (`bazarr_enabled=False`) →
  `bazarr_available: false`, no `errors[]` entry. Enabled-but-unreachable
  (`BazarrError`) → `bazarr_available: false` **+ an `errors[]` entry**. Either
  way every episode gets `subtitles: []`. **Sonarr → stays non-200:** disabled →
  `400 {"error":"sonarr_disabled"}` (as today); `PyarrError` → `502` (as today) —
  the episodes view genuinely cannot render without Sonarr episodes.

### Claude's Discretion
- Exact name/signature of the new count helper (bulk vs per-series); whether the
  language map reuses `rank.py` constants or a new dict; movie `translated_count`
  via filesystem vs ledger; envelope field ordering; test fixture shapes.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 Research — locks the endpoint design (read first)
- `.planning/research/ARCHITECTURE.md` §4 "Backend: Enriched Episodes Endpoint" —
  the authoritative design: `episode.get()` vs `episode_file.get()`, the
  episodeFile-by-id lookup, season grouping, Bazarr merge by `sonarrEpisodeId`,
  `asyncio.to_thread` + `asyncio.gather` pattern, the full JSON response contract
  + field-by-field table, path-stripping rationale.
- `.planning/research/ARCHITECTURE.md` §5 "Data-Fetching Pattern" — the
  `EpisodeEnrichedRow` / `SeriesEpisodesResponse` TypeScript types the Phase-14
  client expects (keep the backend contract aligned; do NOT add React Query).
- `.planning/research/ARCHITECTURE.md` §6 "Integration Points" — `library.py`
  MODIFIED; `bazarr.py` / `sonarr.py` / `app.py` UNCHANGED.
- `.planning/research/ARCHITECTURE.md` §8 "Risks" — sync-in-async pyarr block;
  **Bazarr `fetch_episode_inventory` `params=[("seriesid[]", id)]` list-form** may
  return empty on the live Bazarr — try the unbracketed form; verify live.

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — **API-01** (season-grouped episode records +
  `audio_languages` + Bazarr `subtitles[]` incl. `hi`/`forced` + status; Bazarr
  fail-soft HTTP 200), **API-02** (Series + Movies list `translated_count` /
  `total_count`).
- `.planning/ROADMAP.md` §"Phase 13: Backend Episodes Enrichment" — goal + four
  success criteria (envelope shape; Bazarr-down all-`subtitles:[]` + flag; list
  counts; tests for fail-soft, `episode.id` join, audio full-name→ISO lookup).

### Existing code baseline (this phase modifies / depends on)
- `trezarr/web/routes/library.py` — `get_series_episodes` (current flat
  episode-FILE list, 400/502, sync pyarr in async) to REWRITE; `get_library`
  (series/movies + `errors[]` HTTP-200 pattern) to EXTEND with counts;
  `_episode_key_from_file` retired for the episodes endpoint.
- `trezarr/arr/bazarr.py` — `fetch_episode_inventory(sonarr_series_id)`,
  `BazarrInventoryItem(arr_id=sonarrEpisodeId, path, subtitles)`,
  `BazarrSubtitle(code2, code3, forced, hi)`, `BazarrClient.from_settings`,
  `BazarrError`; already applies path mapping (D-105) — UNCHANGED, just consumed.
- `trezarr/arr/sonarr.py` — `build_sonarr_client`; `episode.get` /
  `episode_file.get`; source of `mediaInfo.audioLanguages` full names.
- `trezarr/output/ledger_sqla.py` — `LedgerSQLA` + `ProcessedFile` table
  (`series_id`, `status`, `output_path`); the **active** ledger backend; needs a
  NEW count helper.
- `trezarr/output/ledger.py` — `LedgerEntry` (`status: done|quarantined|in_progress`,
  `series_id: str | None` "reserved for Phase-4 FK" — see D-06).
- `trezarr/source_selection/rank.py` — existing language constants to reuse for
  the audio full-name→ISO map (D-07).
- `trezarr/paths.py` `apply_path_mapping`; `trezarr/discover/scan.py`
  `find_source_sub` — reused for `local_path` / source-sub status, as today.

### Sibling phase (contract consumer)
- `.planning/phases/12-app-shell-route-restructure/12-CONTEXT.md` — Phase 12 builds
  the shell + stub `SeriesDetail`; Phase 14 wires it to **this** endpoint, so the
  contract must be stable before Phase 14 implements `SeriesDetail`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BazarrClient.fetch_episode_inventory` + DTOs already exist and key by
  `sonarrEpisodeId` — the enrichment is a *merge*, not new client plumbing.
- `get_library` already returns `{series, movies, errors}` HTTP-200; extending
  each item with two integer fields is additive and low-risk.
- `find_source_sub` + `apply_path_mapping` already compute `local_path` /
  `source_path` / source-sub status — keep that logic; feed it episode-record
  `episodeFile.path` instead of the flat episode-file list.

### Established Patterns
- The existing fail-soft `errors[]` / always-HTTP-200 pattern on `get_library` is
  the template for the Bazarr branch (D-08).
- The active ledger backend is **LedgerSQLA** (swapped JSON→SQLite in Phase 4,
  plan 04-04). The count must be a **direct DB aggregate** (a new store fn), NOT
  the ledger's `check`/`record` API (no count method exists).
- Tests live under `tests/web/`; the current endpoint returns a flat list, so the
  test fixtures and assertions change shape — update them to the season-grouped
  envelope.

### Integration Points
- **Join key correctness:** Bazarr inventory joins on the episode **record** id
  (`episode.id` == `sonarrEpisodeId`), NOT `episodeFile.id`. API-01 success
  criterion 4 calls this out — get it right and test it.
- **Sonarr `statistics`:** Sonarr v3 `series.get()` objects carry a `statistics`
  block (`episodeCount`, `episodeFileCount`, …). Use `episodeFileCount` for
  `total_count` (D-04) — verify the field is present in the live payload.
- **series_id keying:** ledger `series_id` is a `str`; Sonarr id is an `int` —
  count by `str(series_id)` (D-05), and verify the engine populates it (D-06).

</code_context>

<specifics>
## Specific Ideas

- Prefer one **bulk** translated-count query over N per-series queries on the list
  endpoint (D-05) — large libraries make N round-trips painful.
- Verify the Bazarr `seriesid[]` list-form param against the live Bazarr at
  192.168.5.42 during integration (ARCHITECTURE.md §8 risk); fall back to the
  unbracketed form if it returns empty.
- Keep the response field names exactly as `research/ARCHITECTURE.md §4/§5`
  specifies so the Phase-14 `EpisodeEnrichedRow` / `SeriesEpisodesResponse` types
  line up without a contract renegotiation.

</specifics>

<deferred>
## Deferred Ideas

- Frontend `Series.tsx` / `SeriesDetail.tsx` / `Movies.tsx` consuming this
  contract (season Accordion, audio/subtitle badges, Translate actions) → Phase 14.
- NAV-03 sidebar nav-row **count badge** (uses `translated_count`/`total_count`
  exposed here) + **LIVE** *arr-connection badge → Phase 14.
- Introducing React Query / SWR on the frontend — explicitly rejected by
  `research/ARCHITECTURE.md §5`; keep the raw `fetch` layer.

None outside the roadmapped phases — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-backend-episodes-enrichment*
*Context gathered: 2026-06-03*
