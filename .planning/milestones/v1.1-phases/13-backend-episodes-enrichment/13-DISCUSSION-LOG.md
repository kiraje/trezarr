# Phase 13: Backend Episodes Enrichment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-03
**Phase:** 13-backend-episodes-enrichment
**Areas discussed:** Progress counts (API-02), Episode key derivation, Audio language codes, Fail-soft envelope

---

## Progress counts (API-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Ledger DB (translated) + Sonarr stats (total) | total = Sonarr statistics.episodeFileCount (in series.get() payload); translated = COUNT(processed_file WHERE series_id, status='done'). Cheap, one aggregate query. | ✓ |
| Filesystem scan per series | Walk episodes + glob .vi sidecars. Accurate for non-Trezarr subs, but O(episodes) disk I/O per series on every list render. | |
| Sonarr statistics only | Approximate; can't know vi count without DB/scan. | |

**User's choice:** Ledger DB for translated + Sonarr stats for total (recommended).
**Notes:** No count method exists today → add a (bulk) store/count helper. CRITICAL: verify the engine populates ProcessedFile.series_id (str|None, "reserved for Phase-4 FK") or the count is wrong. Key by str(series_id). Movies: total=1 if hasFile, translated via per-movie filesystem check or ledger.

---

## Episode key derivation

| Option | Description | Selected |
|--------|-------------|----------|
| Authoritative ints S{nn}E{nn} | From Sonarr episode-record seasonNumber/episodeNumber; retire _episode_key_from_file for this endpoint. No regex, correct grouping, donghua handled by Sonarr numbering. | ✓ |
| Keep tolerant filename parsing | Retain _episode_key_from_file SxxExx/NxNN regex. Adds complexity; can disagree with authoritative grouping. | |

**User's choice:** Authoritative ints S{nn}E{nn} (recommended).
**Notes:** .vi status stays filesystem-based, ledger count is per-series — so the key format change won't desync status or the Translate enqueue.

---

## Audio language codes

| Option | Description | Selected |
|--------|-------------|----------|
| Normalize to ISO-639-1 in backend | Map full name → code2 ('Korean'→'ko') server-side (reuse rank.py constants if suitable; else small dict). Split '/'-joined, dedupe, unknown→lowercased/'und'. Matches API-01 criterion. | ✓ |
| Pass through full names | Return ['Korean']; Phase 14 maps. Simpler backend, contradicts API-01 success criterion. | |

**User's choice:** Normalize to ISO-639-1 in the backend (recommended).
**Notes:** Reuse/extend existing language constants in trezarr/source_selection/rank.py if suitable.

---

## Fail-soft envelope

| Option | Description | Selected |
|--------|-------------|----------|
| Bazarr always 200; Sonarr stays non-200 | Bazarr disabled OR unreachable → bazarr_available:false (errors[] only on enabled-but-failed). Sonarr disabled→400, error→502. Matches ARCHITECTURE.md + existing pattern. | ✓ |
| Fully fail-soft (Sonarr-down also 200) | Sonarr failure → empty seasons[] + errors[] too. Uniform, but UI can't tell 'no episodes' from 'Sonarr down'. | |

**User's choice:** Bazarr always 200; Sonarr stays non-200 (recommended).

---

## Claude's Discretion

- Exact name/signature of the new count helper (bulk vs per-series).
- Language map source: reuse rank.py constants vs a new dict.
- Movie translated_count via filesystem vs ledger.
- Envelope field ordering and test fixture shapes.

## Deferred Ideas

- Frontend Series/SeriesDetail/Movies consuming this contract → Phase 14.
- NAV-03 nav count + LIVE badges (consume translated_count/total_count) → Phase 14.
- React Query/SWR on the frontend — rejected by ARCHITECTURE.md §5.
