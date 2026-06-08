---
gsd_state_version: 1.0
milestone: none
milestone_name: (none — v1.0 + v1.1 archived)
status: milestone_archived
stopped_at: Completed 14-02-PLAN.md
last_updated: "2026-06-07T10:41:54.646Z"
last_activity: "2026-06-07 — quick 260607-iab: ContextWeave-benchmark fix. Cloned + benchmarked competitor ContextWeave (same deepseek) vs Trezarr vs gold reference on Ep-142 via a dynamic workflow (6 code-readers + 4 benchmark agents → synthesis → adversarial verify): Trezarr won 3/4 dimensions (register, term/Hán-Việt, structure) but lost the title-card-parentheses sub-dimension (our H4 RULE stripped source `(...)`). Fixed build_translate_prompt H4 rule to PRESERVE source-present parens while still forbidding model-added glosses. trezarr-quality review then caught (and finding-verifier empirically VERIFIED) that the rule re-opened the Pass-3 `(speaker says:…)` hint scaffolding-leak class → FIXED f96c125 (H4 carve-out + new HINT_SCAFFOLD_RE in gate Check 8); re-verified 5/0, 475 passed, reconcile/attribute untouched. On branch fix/contextweave-paren-preservation — NOT yet merged or live-verified. Deferred CW learnings: self-correcting batch retry, queue-exhaustion guard, and the rolling "who-said-what-to-whom" context-carry summary (the biggest idea — gated on a cross-episode proving audit since its 2 motivating defects are already fixed by cheaper means + medium pronoun-moat risk). Prior: quick 260607-dbe attribution-hint-gap + per-pass reasoning (also unmerged); core value single-episode-verified on deepseek; cross-episode (Phase-06) remains"
progress:
  total_phases: 16
  completed_phases: 16
  total_plans: 65
  completed_plans: 65
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-04)

**Core value:** Vietnamese subtitles that stay consistent and relationally correct (right pronoun pair, stable names/terms) across an entire series — produced automatically.
**Current focus:** No active milestone — v1.0 + v1.1 shipped and archived. Next: `/gsd-new-milestone`.

## Current Position

Milestone: none active (v1.0 + v1.1 archived)
Status: milestone_archived
Last activity: 2026-06-08 — quick 260608-e8r: Pass-3 hint-leak strip (live job-9 fix). Server run on api.deepseek.com quarantined the whole episode because deepseek-v4-pro echoed the Pass-3 hint `(speaker says: muội; addresses as: huynh)` into cue 24 — Check 8 caught it (the iab moat backstop working in PROD, no corrupt sidecar shipped) but quarantine-whole-file meant no output. Fix: strip a LEADING echoed hint in parse_numbered_response (recover the cue instead of quarantining; mirrors the Pass-4 (source: splice-guard); hint-only echo → empty → IMP-02 retry; source title-cards preserved; Check 8 stays as unanchored backstop). trezarr-quality PASS (codec + linguist, both ran the suite; round-trip/ReDoS-safe, moat-neutral). TDD 484 passed. Branch fix/pass3-hint-leak-strip. KEY: the live endpoint is now api.deepseek.com (healthy); the earlier 4.5h of 524s was the tlemons.com proxy only. Prior: quick 260607-o4g: IMP-02 self-correcting batch retry + `scripts/translate_one.py` local runner. Fixes the live Ep-142 quarantine (`Missing line [1]…expected 4 lines` — DeepSeek dropped a batch line; the old tenacity loop re-sent the SAME prompt → quarantine) by converting Pass-3 to a bounded message-accumulating self-correction loop (append bad reply + structural-only correction turn, re-call up to translate_batch_retry_attempts+1, then quarantine as before). MOAT-safe (messages[0] append-only; no pronoun content in correction turn), quarantine/idempotency unchanged. trezarr-quality PASS (pipeline-reliability + vietnamese-linguist both ran the suite). TDD 480 passed. Branch feat/selfcorrect-retry-local-runner (stacked on iab) — NOT merged/live-verified. Prior: quick 260607-iab ContextWeave-benchmark fix — cloned + benchmarked competitor ContextWeave (same deepseek) vs Trezarr vs gold reference on Ep-142 via a dynamic workflow (6 code-readers + 4 benchmark agents → synthesis → adversarial verify): Trezarr won 3/4 dimensions (register, term/Hán-Việt, structure) but lost the title-card-parentheses sub-dimension (our H4 RULE stripped source `(...)`). Fixed build_translate_prompt H4 rule to PRESERVE source-present parens while still forbidding model-added glosses. trezarr-quality review then caught (and finding-verifier empirically VERIFIED) that the rule re-opened the Pass-3 `(speaker says:…)` hint scaffolding-leak class → FIXED f96c125 (H4 carve-out + new HINT_SCAFFOLD_RE in gate Check 8); re-verified 5/0, 475 passed, reconcile/attribute untouched. On branch fix/contextweave-paren-preservation — NOT yet merged or live-verified. Deferred CW learnings: self-correcting batch retry, queue-exhaustion guard, and the rolling "who-said-what-to-whom" context-carry summary (the biggest idea — gated on a cross-episode proving audit since its 2 motivating defects are already fixed by cheaper means + medium pronoun-moat risk). Prior: quick 260607-dbe attribution-hint-gap + per-pass reasoning (also unmerged); core value single-episode-verified on deepseek; cross-episode (Phase-06) remains

```
v1.0 MVP                  [##########] SHIPPED 2026-06-03 (phases 1-10, tag v1.0)
v1.1 UI v2 shadcn         [##########] SHIPPED 2026-06-04 (phases 11-16, tag v1.1)
```

Shipped detail in MILESTONES.md; per-milestone archives in milestones/.

## Performance Metrics

**Velocity:**

- Total plans completed: 60 (v1.0)
- Average duration: 6 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 03 | 5 | - | - |
| 04 | 4 | - | - |
| 05 | 6 | - | - |
| 6 | 3 | - | - |
| 7 | 6 | - | - |
| 08 | 4 | - | - |
| 10 | 4 | - | - |
| 11 | 3 | - | - |
| 12 | 1 | - | - |
| 13 | 3 | - | - |
| 14 | 6 | - | - |
| 15 | 7 | - | - |
| 16 | 1 | - | - |

**Recent Trend:**

- Last 5 plans: 6 min
- Trend: establishing baseline

*Updated after each plan completion*
| Phase 01 P02 | 2 | 3 tasks | 4 files |
| Phase 01-codec-llm-client-foundation P03 | 9 | 2 tasks | 3 files |
| Phase 02 P01 | 8 | 2 tasks | 8 files |
| Phase 02 P02 | 10 | 2 tasks | 7 files |
| Phase 02 P03 | 12 | 2 tasks | 4 files |
| Phase 03 P01 | 25 min | 2 tasks | 11 files |
| Phase 03 P03 | 20min | 2 tasks | 4 files |
| Phase 3 P04 | 35min | 2 tasks | 4 files |
| Phase 3 P05 | 50min | 2 tasks | 5 files |
| Phase 05-three-pass-pronoun-engine P01 | 2min | 2 tasks | 5 files |
| Phase 05-three-pass-pronoun-engine P02 | 4 min | 2 tasks | 5 files |
| Phase 05-three-pass-pronoun-engine P03 | 4 min | 1 tasks | 3 files |
| Phase 05 P04 | 3 min | 1 tasks | 2 files |
| Phase 05 P06 | 15min | 2 tasks | 5 files |
| Phase 06 P06-02 | 25 min | 2 tasks | 5 files |
| Phase 06 P06-03 | 15min | 2 tasks | 4 files |
| Phase 07-web-ui-service-hardening P01 | 3 minutes | 2 tasks | 9 files |
| Phase 07 P02 | 13min | 2 tasks | 13 files |
| Phase 07-web-ui-service-hardening P06 | 12 | 3 tasks | 6 files |
| Phase 08 P01 | 5 | 2 tasks | 3 files |
| Phase 08 P02 | 4 min | 2 tasks | 4 files |
| Phase 08 P03 | 8 minutes | 2 tasks | 3 files |
| Phase 08 P04 | continuation | 5 tasks | 10 files |
| Phase 09 P01 | 8 minutes | 2 tasks | 26 files |
| Phase 09-multi-format-ass-ssa-vtt P03 | 25 | 2 tasks | 7 files |
| Phase 09 P04 | 12 | 1 tasks | 2 files |
| Phase 10 P01 | 6min | 2 tasks | 9 files |
| Phase 09-multi-format-ass-ssa-vtt P05 | 35m | 2 tasks | 5 files |
| Phase 10-source-selection-per-series-overrides P02 | 25 | 2 tasks | 12 files |
| Phase 10 P03 | 12min | 2 tasks | 11 files |
| Phase 11-shadcn-foundation-purple-theme P01 | 3 min | 2 tasks | 10 files |
| Phase 11 P02 | 2 minutes | 2 tasks | 3 files |
| Phase 12 P01 | 146 | 3 tasks | 6 files |
| Phase 13 P01 | 149 | 2 tasks | 2 files |
| Phase 13-backend-episodes-enrichment P02 | 6 min | 2 tasks | 4 files |
| Phase 13 P03 | 5 min | 2 tasks | 2 files |
| Phase 14 P01 | 148s | 2 tasks | 4 files |
| Phase 14 P02 | 8m | 2 tasks | 3 files |
| Phase 14 P05 | 2min | 2 tasks | 2 files |
| Phase 15-reskin-existing-pages P01 | 139 | 3 tasks | 3 files |
| Phase 15 P02 | 2m | 2 tasks | 2 files |
| Phase 15 P03 | 135s | 2 tasks | 2 files |
| Phase 15 P04 | 2 min | 2 tasks | 3 files |
| Phase 15-reskin-existing-pages P05 | 5m | 1 tasks | 1 files |
| Phase 15-reskin-existing-pages P06 | 45 | 5 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Leaves-first ordering — codec + LLM client (Phase 1) before any novel logic; validation gate is foundational (Phase 2), not polish.
- Roadmap: First vertical slice (Phase 3) de-risks \*arr path-mapping/permissions before investing in the Series Bible moat.
- Roadmap: Address Map (BIBLE-03) and attribution (PRON) ship together in Phase 5 — they are co-dependent and neither delivers value alone.
- Plan 01: pysubs2 excluded from Phase 1 — thin custom SRT parser built in Plan 02 for byte-identity (D-08)
- Plan 01: asyncio_mode=auto eliminates per-test @pytest.mark.asyncio boilerplate
- Plan 01: xfail(strict=False) stub pattern chosen for Nyquist-compliant pre-implementation test surface
- [Phase ?]: avoids mutating class-level state in multi-threaded scenarios
- [Phase ?]: aligns with test expectations and allows endpoint-level tier probing
- [Phase ?]: _make_translate_batch_fn factory: tenacity stop_after_attempt bound at runtime from settings.translate_batch_retry_attempts
- [Phase 03-03]: Catch pyarr.exceptions.PyarrError (parent) in *arr discovery — pyarr abstracts httpx errors — pyarr wraps httpx.RequestError into PyarrConnectionError and 4xx/5xx into typed Pyarr*Error; raw httpx exceptions never escape pyarr's request layer (Rule 3 deviation from plan)
- [Phase 03-03]: Pass api_ver=v3 to pyarr Sonarr/Radarr constructors — Skips pyarr's GET /api auto-detect probe. Sonarr/Radarr v3 is stable per CLAUDE.md + D-22; test fixtures only mock typed endpoints, not the version probe (Rule 3 deviation)
- [Phase 03-03]: MediaItem dataclass owned by trezarr.arr.sonarr; re-imported by radarr.py — Field 'title' (not series_title) carries both episode and movie titles per 03-REVIEWS.md LOW #17 — defined once to avoid drift
- [Phase ?]: Plan 03-04: scan_for_eligible_items signature is (items, ledger, lang_priority) matching Wave-0 test contract — narrower than the plan body's (items, settings, ledger) so scan decouples from TrezarrSettings
- [Phase ?]: Plan 03-04: apply_permissions asymmetric error handling — chown PermissionError warn-and-continue; chmod OSError raises PermissionApplyError (MEDIUM #13) so cli.py can quarantine
- [Phase ?]: Plan 03-04: 1 xfail marker retained on test_scan_returns_eligible_item_and_scan_stats — it imports trezarr.cli.MediaItem (Plan 03-05 territory); reason updated to point to next wave
- [Phase 03-05]: Rule 1 deviation — `if media_roots:` guard around assert_within_media_roots in cli's translate loop. Architectural invariant preserved via assert_media_roots_configured at startup; the guard inside the loop honors passthrough mode (no *arr + no path_mappings) without changing arr-enabled behaviour.
- [Phase 03-05]: Rule 2 deviation — `all_arr_failed` (enabled_arr > 0 AND len(discovery_failures) == enabled_arr) added to the exit-1 disjunction. Without this, the "both *arrs raised DiscoveryError → 0 items → exit 0" path violated the plan's stated success criterion.
- [Phase 03-05]: Rule 3 deviation — Added `[tool.uv] package = true` + `[build-system] hatchling` + `[tool.hatch.build.targets.wheel] packages = ["trezarr"]` so `uv sync` actually installs `[project.scripts] trezarr = "trezarr.cli:main"`. Without `package = true`, uv silently skips the entry point and `uv run trezarr` does not resolve.
- [Phase 03-05]: Soft observation — `trezarr.cli.MediaItem` and `trezarr.arr.sonarr.MediaItem` are two separate dataclasses. cli.MediaItem carries source_sub_path (post-scan); arr.sonarr.MediaItem carries raw discovery payload. Intentional per Plan-03-01 test contract; future-cleanup candidate (consolidate to EligibleItem) but not a Phase-3 blocker.
- [Phase ?]: xfail raises=(ImportError, AssertionError, TypeError) for stubs in existing modules — trezarr.translate.engine exists from Phase 3, so raises=ImportError alone would cause FAILED not XFAIL for test_pronoun_engine.py stubs
- [Phase ?]: [Phase 05-03]: D-44 threshold gate: confirmed pair uses Address Map entry terms; below-threshold unlocked entry skipped → safe default
- [Phase ?]: translate_file three-pass flow: Pass 1 BARRIER + Pass 2 gather + reconcile + Pass 3 pronoun hints; BibleAnalysisError quarantines; openai.APIError propagates (D-40 D-48 Pitfall B)
- [Phase ?]: derive_episode_key parses SxxExx from subtitle filename stem not episode_number field (D-49 Pitfall F confirmed)
- [Phase ?]: xfail(strict=False) with raises=(ImportError, AssertionError, TypeError) for Wave-0 stubs targeting not-yet-created modules
- [Phase ?]: D-67 ProcessedFile arm uses separate reconcile_in_progress_from_ledger function for independent testability
- [Phase ?]: D-62 process_one_item shared callable extracted from CLI loop body; ItemResult dataclass; worker._execute_job calls same function
- [Phase ?]: D-67 two-arm crash-resume: reconcile_in_progress (Job rows) + reconcile_in_progress_from_ledger (ProcessedFile rows with no matching Job) as separate functions
- [Phase ?]: D-68 per-series asyncio.Lock (not Semaphore) serializes same-series episodes; distinct series run concurrently; zero asyncio.Semaphore in worker.py
- [Phase ?]: Starlette ASGITransport passes inner Router app to lifespan not outer FastAPI instance; engine stored in mutable cell closure for test accessibility
- [Phase ?]: Phase 08-01: xfail(strict=False) with raises=(ImportError, AssertionError, TypeError) for new-module stubs prevents FAILED when module not yet created
- [Phase 09-01]: validate_allowlist xfail stubs use xfail(strict=False) without raises= restriction — raises= is too narrow because pytest.fail() inside try/except raises _pytest.outcomes.Failed, not AssertionError
- [Phase 09-01]: Wave 0 xfail stubs for non-existent modules use pytest.importorskip — tests SKIP cleanly when module absent, go GREEN when module lands (established Trezarr pattern)
- [Phase ?]: no separate test_sonarr.py/test_radarr.py created
- [v1.1 Roadmap]: Phase 11 pins `shadcn@2.10.0 init` (not @latest) — shadcn@latest (4.x) emits Tailwind v4 config that breaks the existing Tailwind v3.4 PostCSS pipeline on first run. The `add` command for components can use @latest safely.
- [v1.1 Roadmap]: NAV-03 (count/LIVE badges) assigned to Phase 14 — badge data requires API-02 `translated_count`/`total_count` from Phase 13; the Phase 12 shell delivers placeholder/zero badges; full badge wiring lands with Phase 14 library pages.
- [v1.1 Roadmap]: Phase 13 (backend enrichment) is parallel-eligible with Phase 12 (shell) — no shared code; but Phase 14 (SeriesDetail) blocks on both Phase 12 (layout route / Outlet) and Phase 13 (stable API contract).
- [v1.1 Roadmap]: BibleEditor reskin is Phase 15 (last page) — 88KB, 5 previously-fixed critical locking bugs; reskin-in-place only (token substitution, no logic changes); test suite must stay green after each of the four sections.
- [v1.1 Roadmap]: Bridge period dual-token strategy — legacy hex tokens kept in tailwind.config.js until all pages are reskinned; removed atomically in Phase 15 (single commit after grep for `bg-[#` returns zero results).
- [Phase ?]: SidebarGroup wrapper added (WR-01): SidebarContent > SidebarGroup > SidebarMenu pattern; adds p-2 inset
- [Phase ?]: NavBadge slot uses flex items-center gap-1 wrapper for LIVE+count badges in SidebarMenuButton (14-02)
- [Phase ?]: WR-03: Route path='*' catch-all as last child of layout route; NotFound.tsx static copy only no XSS surface (14-02)
- [Phase ?]: Settings.tsx SectionHeading uses plain h2 with text-base font-semibold text-card-foreground; CardHeader/CardTitle not imported — plain h2 keeps compact layout within Card/CardContent wrapper

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 5 (Three-Pass Pronoun Engine) is the novel core and flagged for deeper research during planning: prompt design, Bible merge/lock semantics, speaker-inference reliability, Vietnamese pronoun-pair rules, and a cross-episode consistency harness.
- Phase 9 (ASS/SSA) and Phase 10 (source selection) are also research-flagged (intricate ASS tag grammar; novel relational-fidelity ranking heuristic).
- [v1.1] Phase 13 runtime validation needed: Bazarr `fetch_episode_inventory` param format (`seriesid[]` vs `seriesid`) must be verified against the live instance at 192.168.5.42 during Phase 13 — known ambiguity from production observation.
- [v1.1] Phase 14 jolly-ui Table beta stability: evaluate within the first day of Phase 14 implementation; have the shadcn plain `<Table>` fallback ready to swap if Table beta is unstable.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260602-3zg | Fix Phase-5 review findings B1 (reconcile.py name match missing .strip) and M1 (character identity key normalization) | 2026-06-01 | 754292f | [260602-3zg-fix-phase-5-review-findings-b1-reconcile](./quick/260602-3zg-fix-phase-5-review-findings-b1-reconcile/) |
| 260602-g9z | Create README.md for Trezarr | 2026-06-02 | 09890e3 | [260602-g9z-create-readme-md-for-trezarr](./quick/260602-g9z-create-readme-md-for-trezarr/) |
| 260603-laj | Fix CJK character-name resolution in Series Bible analyze (dual-key name_to_id on original_script_name + prompt tightening + CJK regression test) | 2026-06-03 | 66a47ba | [260603-laj-fix-cjk-character-name-resolution-in-ser](./quick/260603-laj-fix-cjk-character-name-resolution-in-ser/) |
| 260603-l8g | Library browser UI + manual single-item translate (arr-themed) + auto_translate poller safety gate; Bug 2 (alembic loggers) + Bug 3 (auto-enable *_enabled on save) | 2026-06-03 | 2fd17c7 | [260603-l8g-library-browser-manual-translate](./quick/260603-l8g-library-browser-manual-translate/) |
| 260603-mc3 | Selective SPA fallback — deep-link/refresh on client-side routes (/library, /bible/:id) now serves index.html instead of {"detail":"Not Found"}; missing assets + unknown /api paths still 404 honestly | 2026-06-03 | cbf1ad3 | [260603-mc3-selective-spa-fallback-for-deep-link-ref](./quick/260603-mc3-selective-spa-fallback-for-deep-link-ref/) |
| 260604-gfl | Fix P0 daemon startup crash-loop: reconcile_in_progress_from_ledger MultipleResultsFound (scalar_one_or_none→.first()) + enqueue_job auto-retry cap (job_max_auto_attempts, poll/webhook only) to bound duplicate Job rows. Specialist-reviewed PASS; full suite green | 2026-06-04 | 44543d0 | [260604-gfl-fix-daemon-crash-loop-job-dedup](./quick/260604-gfl-fix-daemon-crash-loop-job-dedup/) |
| 260604-hb4 | Orphan-sentinel (v1.0 #5): strip hallucinated <<TN>> instead of quarantining (codec-fidelity-guardian PASS) + v1.1 warnings W1 (LIVE-badge services flag), W2 (series_title string\|null), W3 (Bazarr seriesid[]→plain fallback; arr-integration-specialist PASS). 387 passed; frontend build green | 2026-06-04 | 730f062, 30d6b6b | [260604-hb4-fix-orphan-sentinel-and-v11-warnings](./quick/260604-hb4-fix-orphan-sentinel-and-v11-warnings/) |
| 260604-gza | LIVE-VERIFY orphan-sentinel fix on S01E06 (.zh, series 62): rebuilt+redeployed on the fixed code, re-ran via manual translate → job **done, NO quarantine**, `.vi.srt` written (374/374 cue parity, **57 orphan sentinels stripped, 0 integrity failures**). **Thesis CONFIRMED: the harness — not deepseek — was the blocker** (deepseek DID drive the pipeline to output). NEW critical bug found: Pass-4 self-review corrupts ~28% of cues (leaks `(source: …)` scaffolding into output; gate misses it). Verify-only, no code commit. | 2026-06-04 | (verify-only) | [260604-gza-live-verify-sentinel-fix-s01e06](./quick/260604-gza-live-verify-sentinel-fix-s01e06/) |
| 260604-hp2 | Fix the 2 bugs gza found: [CRITICAL] Pass-4 scaffolding-leak → splice guard (REVIEW_SCAFFOLD_RE, drop+keep clean Pass-3) + gate Check 8 (pipeline-reliability PASS); series-entity register merge AttributeError that silently dropped register/overrides (Series PK vs .series_id; bible-consistency PASS). 390 passed | 2026-06-04 | d651c5a, 562bad9 | [260604-hp2-fix-pass4-leak-and-register-merge](./quick/260604-hp2-fix-pass4-leak-and-register-merge/) |
| 260604-ikq | Stage-2 name/term consistency fix: inject Bible glossary (Term Dictionary + character names) into Pass-3 + Pass-4 prompts (Pass-3 was glossary-blind; Pass-4 term filter never matched Latin keys vs Chinese source). Re-ran S01E06 + re-audited (vietnamese-linguist→finding-verifier, **11 VERIFIED / 0 REFUTED**): **CONSISTENT, regression-free** — protagonist 11 renderings→1 (`Daisy` ×56), Sakura/Rōsei/Tōchō snapped to canonical `Anh Đào`/`Lang Tinh`/`Đông Điệp`, 0 raw CJK; pronoun layer unaffected. BLOCKER 2→0, HIGH 3→0. TDD, 394 passed. | 2026-06-04 | 8ad599d | [260604-ikq-term-name-injection-fix](./quick/260604-ikq-term-name-injection-fix/) |
| 260604-kfn | Lock character names as contract (ikq follow-up): `merge_bible_analysis` Step 3.5 + pure `plan_character_name_terms` create-and-LOCK a Term Dictionary entry per character mapping the inferred on-screen name → canonical (no schema migration; reuses inferred `original_script_name`). Live-confirmed (job 8): 5 LOCKED name terms created (`雏菊→Daisy`, `樱→Anh Đào`, `狼星→Lang Tinh`, `冻蝶→Đông Điệp`, `雪→Yuki`; pre-run 0). Output `Daisy ×88`, `Cúc 0`. bible-consistency-auditor PASS (lock-safety/idempotency/txn confirmed). TDD, 396 passed. Residual: 2 raw 雏菊 (model non-determinism — the prompt-ceiling; hard-zero needs output-enforcement). | 2026-06-04 | 4d6e9cd | [260604-kfn-lock-protagonist-name](./quick/260604-kfn-lock-protagonist-name/) |
| 260605-dur | Document the full *arr (Sonarr/Radarr/Bazarr) connection env vars in docker-compose.yml + .env.example so a connection can be configured entirely from compose (PATH B pure-env). Docs-only — pydantic-settings fields already env-configurable; no code change. Corrected the misleading "stored in config.yaml, not as env vars" header → PATH A (web UI) / PATH B (env, precedence env>YAML>defaults). Surfaced all 12 vars (host/port/api_key/enabled × 3), commented-out by default so existing config.yaml deployments are unaffected. Prominent footgun warning in BOTH files: env path has NO auto-enable (web-UI write path does), so `TREZARR_<SVC>_ENABLED=true` is MANDATORY or discovery silently returns nothing. | 2026-06-05 | 0c5a677 | [260605-dur-document-the-full-arr-connection-env-var](./quick/260605-dur-document-the-full-arr-connection-env-var/) |
| fast-0605a | Make *arr + tuning config first-class for env-based deploy (gsd-fast, server-handover prep). docker-compose.yml: switched *arr + tuning env vars to BARE pass-through keys (`- TREZARR_SONARR_HOST`, no `=value`) — empirically verified docker compose OMITS a bare key when unset (config.yaml/defaults win) but passes it through when .env sets it, vs the `${VAR:-}` form which injects an empty string and clobbers config.yaml. Added bare keys for all 12 *arr vars + tuning (bazarr_use_inventory, llm_structured_output_mode, llm_request_timeout, llm_disable_thinking, source_lang_priority, path_mappings, poll_interval). .env.example: added deepseek tuning + translation-behavior placeholder blocks. DEPLOY.md: env-first config (full *arr via .env, UI step optional), required deepseek block, bare pass-through note — now tracked. Local `.env` (gitignored) populated with real arr+LLM values for the running deployment. | 2026-06-05 | 5bca229 | — |
| 260607-iab | **ContextWeave-benchmark fix** — cloned/benchmarked ContextWeave (same deepseek) vs Trezarr vs gold on Ep-142; the one structural sub-dimension CW won was preserving source title-card parentheses (`(...)`), which Trezarr's H4 RULE stripped. Reworked `build_translate_prompt` H4 rule: PRESERVE source-present `()`/`[]` envelopes while still forbidding model-ADDED glosses (Check 12 backstop intact). **Post-impl trezarr-quality review** (codec-fidelity PASS + vietnamese-linguist HIGH → finding-verifier VERIFIED) caught a regression: the rule re-opened the Pass-3 hint scaffolding-leak class (`(speaker says: …; addresses as: …)` could be echoed on-screen — empirically passed all 12 gate checks) → **FIXED f96c125**: H4 carve-out marks the hint PRIVATE/never-echo + new `HINT_SCAFFOLD_RE` in gate Check 8 (defense-in-depth w/ `REVIEW_SCAFFOLD_RE`). Re-verified 5/0 (leak→check 8, 0 false-positives/13 VN cues, title-card win intact). TDD, 475 passed, reconcile/attribute untouched. Report: `.trezarr-harness/REVIEW-20260607_063814.md`. NOT merged/live-verified. Other CW findings (self-correcting retry, queue-guard, rolling-summary context-carry) deferred; context-carry gated on a cross-episode proving audit. | 2026-06-07 | 56c2e69, c287b91, f96c125 | [260607-iab-preserve-source-present-parentheses-and-](./quick/260607-iab-preserve-source-present-parentheses-and-/) |
| 260607-o4g | **IMP-02 self-correcting batch retry + local runner** — fixes the live Ep-142 quarantine (`Missing line [1]…expected 4 lines`: DeepSeek dropped a batch line; the old tenacity loop re-sent the SAME prompt → quarantine after N tries). Converted Pass-3 `_translate_batch_inner` from tenacity-on-`BatchValidationError` to a bounded **message-accumulating self-correction loop**: on count/sentinel failure it appends the bad assistant reply + a STRUCTURAL-only correction user turn and re-calls, up to `translate_batch_retry_attempts+1` total calls, then quarantines exactly as before. MOAT-safe: `messages[0]` (pronoun hints/glossary/register from `build_translate_prompt`) is append-only/authoritative and never paraphrased; the correction turn carries no pronoun content (Test B). Plus `scripts/translate_one.py` — a dev-only runner that translates a single `.srt` against the local `.env` DeepSeek creds (no server, no 16-min deploy). plan-checked (2 blockers fixed pre-exec); **trezarr-quality PASS** (pipeline-reliability + vietnamese-linguist, both ran the suite — no double-retry storm, quarantine/idempotency unchanged, moat-neutral). TDD, 480 passed. Report: `.trezarr-harness/REVIEW-20260607_104746.md`. Branch `feat/selfcorrect-retry-local-runner` (stacked on iab) — NOT merged/live-verified. | 2026-06-07 | f3405e7, dd89d89 | [260607-o4g-self-correcting-batch-retry-imp-02-so-a-](./quick/260607-o4g-self-correcting-batch-retry-imp-02-so-a-/) |
| 260608-e8r | **Pass-3 hint-leak strip** (live job-9 fix) — server run on `api.deepseek.com` quarantined the WHOLE episode because deepseek-v4-pro echoed the Pass-3 hint into cue 24: `(speaker says: muội; addresses as: huynh) Chư vị tu sĩ...`. Check 8/`HINT_SCAFFOLD_RE` caught it (no corrupt sidecar shipped — the iab moat fix working in PROD) but quarantine-whole-file = no output, and the H4 carve-out didn't stop the echo. Fix: `_LEAKED_HINT_RE` strips a LEADING echoed hint in `parse_numbered_response` (after `<<BR>>` restore, before empty-check) so the cue RECOVERS instead of quarantining — mirrors the Pass-4 `(source:` splice-guard. Hint-only echo → empty → raises → IMP-02 retries. Source title-card `(Phàm Nhân Tu Tiên Ký)` NOT matched (guards the iab paren win). Check 8 stays as the unanchored backstop for mid-line echoes. trezarr-quality PASS (codec-fidelity + vietnamese-linguist, both ran the suite; round-trip/sentinel safe, ReDoS-safe, moat-neutral). TDD, 484 passed. Report: `.trezarr-harness/REVIEW-20260608_032641.md`. Branch `fix/pass3-hint-leak-strip`. NOTE: the endpoint is now `api.deepseek.com` (healthy) — the tlemons.com proxy 524 was proxy-only. | 2026-06-08 | 001c491, 53a4863 | [260608-e8r-surgically-strip-a-leaked-pass-3-attribu](./quick/260608-e8r-surgically-strip-a-leaked-pass-3-attribu/) |
| 260607-dbe | Fix the Ep-142 "doesn't know who is talking" failure (diagnosed against live-server output). **FIX-A** — register-aware unhinted-line guardrail in `build_translate_prompt`: when a cue has NO (speaker says/addresses as) hint, the model must render literal "you/your" as a register-appropriate 2nd-person pronoun (`ngươi`/`các hạ` classical xianxia; `anh`/`em`/`bạn` modern) and NEVER substitute a character name — kills the cue 33-34 inversion (`You seem confident` → wrongly `Hàn tiền bối … của mình` instead of `ngươi …`). **FIX-B** — per-pass reasoning: `thinking: bool\|None` per-call override on `LLMClient.call`/`_call_with_fallback` (None=global default unchanged; True=`extra_body{thinking:enabled}`+`reasoning_effort`; False=disabled), built as a LOCAL `effective_call_kwargs` per call so `self._call_kwargs` is NEVER mutated (no-leak test); 3 config knobs (`enable_reasoning_analysis`/`enable_reasoning_attribution`=True, `llm_reasoning_effort="high"`); reasoning threaded into Pass-1 `analyze`/`_analyze_one_chunk` + Pass-2 `attribute_batch` ONLY — Pass-3 translate + Pass-4 review stay fast. Root cause: live `TREZARR_LLM_DISABLE_THINKING=true` ran attribution (the most reasoning-heavy pass) in deepseek's fast non-thinking mode. TDD (RED→GREEN), all HARD INVARIANTS intact (byte-identical round-trip, 12-check gate, sentinel/`<<BR>>`, 1:1 cue alignment, tier-fallback + no-double-retry). 466 passed (was ~451). **Post-impl trezarr-quality review** (pipeline+linguist+codec specialists, adversarially verified 7/7) caught that the guardrail's *fallback pronouns* contradicted reconcile's safe-default ladder — it offered `ngươi` (presumptuous/superior, excluded) + `em` (intimate) as unhinted defaults (1 HIGH + 2 MEDIUM) → **FIXED 209196d**: lead `các hạ`/`bạn`, drop `ngươi`/`em`, reuse canonical `_is_classical_register`; documented per-pass reasoning override (MEDIUM #4 keep-as-is). 466 passed, ruff clean. STILL not merged/live-verified. | 2026-06-07 | 802d03a, 3f1d2bf, ee80a79, 209196d | [260607-dbe-fix-attribution-hint-gap-guardrail-per-p](./quick/260607-dbe-fix-attribution-hint-gap-guardrail-per-p/) |

## Deferred Items

Items acknowledged at the v1.0 + v1.1 milestone close (2026-06-04). The v1.1 UI work passed
clean (8/8 live smoke test); all open debt is v1.0-phase human-verify / core-value debt that
requires a real run against a capable model.

All known code-level bugs are now FIXED (260604-gfl + hb4 + hp2 + ikq, 2026-06-04). The live
re-verification (260604-gza) surfaced two — Pass-4 scaffolding-leak + register-merge — fixed in
hp2; the Stage-2 consistency audit then surfaced name/term drift, fixed in **ikq** (glossary
injection) and re-audited **CONSISTENT, regression-free** (11 VERIFIED/0 REFUTED). So the core
value is now single-episode-verified on deepseek (no frontier model). Remaining open items are
NON-code: **cross-episode** consistency (needs ≥2 episode sources), a recommended bible-completeness
follow-up (lock the protagonist's name), minor residuals, human/live UAT, and one hardening item.

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v1.0 core-value | Translation core value **LARGELY VERIFIED on deepseek (single episode)** — 260604-gza + ikq. Clean `.vi.srt` produced (no frontier model); Stage-2 audit (linguist→verifier, 11 VERIFIED/0 REFUTED) = **CONSISTENT, regression-free**: pronoun/relational moat correct AND name/term moat fixed via glossary injection (ikq) — protagonist 11 renderings→1, named chars snapped to canonical. Remaining = **cross-episode consistency (Phase-06, needs ≥2 episode sources on the volume)** + the minor residuals/follow-ups below. The "needs a frontier model" claim is disproven; a frontier model is OPTIONAL quality lift. | **open (cross-episode only — single-episode verified)** | 2026-06-04 |
| v1.0 bible-completeness | Protagonist/character names not lock-enforced (ikq audit) | ✅ **FIXED 4d6e9cd** (260604-kfn) — `merge_bible_analysis` Step 3.5 create-and-locks a Term Dictionary entry per character mapping the on-screen name → canonical (`雏菊→Daisy` etc.); live-confirmed 5 locked terms. | — |
| v1.0 output-enforcement | [optional, for HARD guarantee] A locked Bible term is still injected as a prompt — it protects the Bible value but doesn't force the output (e.g. 2 raw 雏菊 slipped through job 8 via model non-determinism). A deterministic post-translation normalization (rewrite known name variants → canonical) would zero out residual name leakage. Deferred by choice (260604-kfn). | open (optional follow-up) | 2026-06-04 |
| v1.0 provenance | [LOW, from kfn audit] system auto-locks (Step 3.5) borrow `apply_human_edit_term`'s `source="lock"` + `episode_key=None`, so they're indistinguishable from human UI locks in `bible_event`. Add a `source="system"` (+episode_key) kwarg to `apply_human_edit_term`. | open (LOW) | 2026-06-04 |
| v1.0 Phase-6 reliability | [observation, from ikq audit] **Address-map mutates across re-runs of the SAME episode** — Daisy→Rōsei `em/anh`→`tôi/ngài`, Daisy→Sakura `chị/em`→`tôi/em`, etc., backed by 3 `relationship_event` rows created during the runs. Output is consistent with the *current* Bible, but whether these inferred relationship-events are CORRECT (vs spurious deepseek inferences flipping a lover-pair to formal) needs a Phase-6 audit. | open (needs ≥2 episodes) | 2026-06-04 |
| v1.0 residuals | [from ikq re-audit, all minor] cue-240 Sakura→Daisy register slip (`em` vs deferential `ngài`); cue-79 lone `Daisy-sama` romaji; surname 姬鹰 `Himeotaka`/`Himehawk` split; `「」` corner-bracket punctuation carried from source. | open (LOW/MEDIUM polish) | 2026-06-04 |
| v1.0 code bug | [CRITICAL] Pass-4 self-review scaffolding-leak corruption (`(source: 不要) Đừng` in ~28% of cues) | ✅ **FIXED d651c5a** (260604-hp2) — `_review_batch` splice guard (REVIEW_SCAFFOLD_RE) + gate Check 8 | — |
| v1.0 code bug | Series-entity register/override merge raised `'Series' object has no attribute 'series_id'` → silently dropped register (gza finding #2) | ✅ **FIXED 562bad9** (260604-hp2) — Series uses `.id` for BibleEvent.series_id | — |
| v1.0 UAT (Phase 04) | 1 open HUMAN-UAT scenario; VERIFICATION human_needed (live *arr smoke, asyncio teardown) | open (needs real run) | 2026-06-04 |
| v1.0 UAT (Phase 05) | 2 open HUMAN-UAT scenarios (real-episode pronoun quality; enable_pass1/enable_attribution toggle in prod); VERIFICATION human_needed | open (needs frontier-model run) | 2026-06-04 |
| v1.0 UAT (Phase 06) | 2 open HUMAN-UAT scenarios (real-episode relationship-shift pronoun change; self-review quality on real output); VERIFICATION human_needed | open (needs frontier-model run, ≥2 episodes) | 2026-06-04 |
| v1.0 UAT (Phase 07) | 12 open HUMAN-UAT scenarios (SPA browser conformance, real docker build/run + PUID/PGID ownership, live *arr webhook); VERIFICATION human_needed | open (needs live deployment run) | 2026-06-04 |
| v1.0 UAT (Phase 09) | 09-06 not executed — human visual UAT of positioned-sign rendering (.vi.ass {\pos}/{\an8}, .vi.vtt position:/line:) in mpv/Jellyfin; FMT-04 success criterion 3 unconfirmed | open (needs human visual check) | 2026-06-04 |
| v1.1 tech debt | W1 LIVE-badge false-positive / W2 series_title type drift / W3 Bazarr seriesid[] fallback | ✅ **FIXED 30d6b6b** (260604-hb4) | — |
| reliability hardening | (from 260604-gfl review HIGH-1) enqueue_job auto-retry cap is a SOFT ceiling — no UNIQUE on Job.source_path, so concurrent poll+webhook sweeps can race the count and both insert. Post-fix this only bloats the table slightly (no longer crashes reconcile). Hard bound needs a partial-unique index + dedup-first Alembic migration (live DB already holds duplicate rows) | open (deferred hardening — not a crash) | 2026-06-04 |

> The 5 "missing" quick-tasks flagged by `audit-open` are false positives — all completed and
> committed (754292f, 09890e3, 2fd17c7, 66a47ba, cbf1ad3); the scanner just couldn't parse a
> status field. No deferral needed.

## Session Continuity

Last session: 2026-06-07T10:41:54.640Z
Stopped at: Completed 14-02-PLAN.md
Resume file: None
