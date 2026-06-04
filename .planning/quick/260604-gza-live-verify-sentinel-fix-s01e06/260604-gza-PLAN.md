---
quick_id: 260604-gza
slug: live-verify-sentinel-fix-s01e06
status: in-progress
date: 2026-06-04
---

# Quick Task 260604-gza: Live-verify the orphan-sentinel fix on S01E06

## Goal

Empirically test the thesis **"the harness — not deepseek — was what blocked clean
Vietnamese output"** by re-running the live translation of the one real episode that
previously quarantined, now that orphan-sentinel recovery has landed.

This closes the loop on v1.0 finding #5 and unblocks Phase-04 (end-to-end) verification.
It deliberately does **not** yet audit pronoun quality (Phase-05) — that is Stage 2.

## Context (ground truth captured 2026-06-04)

- **Fix already landed** by the multi-machine sync as commit `730f062`
  *(fix(sentinel): strip hallucinated orphan `<<TN>>` instead of quarantining (v1.0 #5))*.
  Improved over the first draft: strips only the specific orphan tokens
  (`orphans = found - set(sentinel_map)`) **before** reinserting real sentinels.
  `tests/translate/test_sentinel.py` = 10 passed; full `tests/translate` = 79 passed, 10 xpassed.
  → **Nothing to commit in this task** (Step-1 "land fix" was done by the sync).
- **Deployment**: compose-managed container `trezarr:local` on :6868 (healthy, but built
  2026-06-04T03:17 — *predates the fix*, so the running code is stale). Secrets from gitignored
  `.env` (`TREZARR_LLM_MODEL=ds/deepseek-v4-pro`, `base_url=https://api.tlemons.com/v1`).
  Bind mounts: `/Users/dustin/trezarr-config:/config`, `/Users/dustin/trezarr-uat-media:/data/media`
  (UAT media, **not** the real Plex library).
- **Config**: `llm_structured_output_mode: json_object` (deepseek can't do strict json_schema),
  `llm_request_timeout: 600`, path_mappings identity `/data/media -> /data/media`.
- **Series**: id=1, sonarr, **arr_series_id=62**, tvdb 462446 — "Agents of the Four Seasons -
  Dance of Spring".
- **Bible baseline (already persisted)**: 5 characters, **18 directed address-pairs**,
  2 relationship-events, 7 terms. (Resolves the memory-vs-findings discrepancy: the
  findings doc's "0 characters" was the pre-#2-fix run when every LLM call 400'd.)
- **Source** (the song-heavy Chinese sub that quarantined):
  `/data/media/tv/Agents of the Four Seasons - Dance of Spring/Season 1/Agents of the Four Seasons - Dance of Spring - 1x06 - A Place to Call Home.zh.srt`
- **Ledger**: 1 row — that `.zh.srt`, status `quarantined`.

## Tasks

1. **Rebuild + redeploy with the fix.** `docker compose up -d --build` (rebuilds `trezarr:local`,
   recreates the daemon; config/secrets/state preserved via `.env` + `/config` volume). Wait for
   `/api/health` 200.
2. **Trigger the manual translation.** `POST /api/translate` with
   `{kind:"series", source_path:"<container .zh path>", arr_series_id:62}` (manual bypasses the
   5-attempt auto-retry cap that the quarantined item has hit).
3. **Observe + report.** Poll job status / job_log; check for the `<...>.vi.srt` sidecar next to
   the source; capture any `stripped hallucinated orphan sentinel` warnings; confirm whether the
   gate passed (clean output) or quarantined again (and why).

## Success criteria (must-haves)

- The fixed code is what runs (image rebuilt from `730f062`, container recreated).
- The `.zh` episode is re-run end-to-end through the live deepseek path.
- A definitive answer recorded: **clean `.vi.srt` written** (thesis confirmed — harness was the
  blocker) **OR** quarantined again with the new root cause identified (thesis needs more work).
- No change to the real Plex library (UAT media only); no secrets written to the repo.

## Out of scope (Stage 2)

- Pronoun/relational quality audit of the `.vi.srt` (Phase-05) — incl. the Daisy↔Rōsei
  reciprocal asymmetry (`em/anh` vs `tôi/chị`) noted in the baseline.
- Cross-episode consistency (Phase-06) — needs a 2nd episode source on the volume.
