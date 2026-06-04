# Phase 3: *arr Integration + First Vertical Slice - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 makes the Phase-2 translation engine fire on a **real episode/movie discovered through the *arr stack**, not a hand-fed file path. It is the first complete vertical slice — crude but genuinely end-to-end:

1. **Discover** media identity, file paths, and metadata via Sonarr **and** Radarr REST APIs (API-key auth) — no disk scanning for discovery ("API for knowledge"). (INTG-01)
2. **Resolve** each API-returned path to a real local path via a configurable container↔host **path mapping**, with a fail-fast startup readability probe. (INTG-03)
3. **Locate** the source subtitle on the shared filesystem next to the media (configured source-language priority), detect "has source sub, lacks a good `vi` sub", and **queue** it. (AUTO-01)
4. **Translate** each eligible item through the existing Phase-2 `translate_file()` pipeline and **write** the `.vi.srt` sidecar with correct **PUID/PGID/UMASK** permissions so the media server can read it. (INTG-04)
5. **Stay idempotent** — track per-item state including the **source-sub content hash**, skip already-done items, and never re-translate Trezarr's own output. (AUTO-03, AUTO-04)

Requirements covered: **INTG-01** (Sonarr/Radarr discovery), **INTG-03** (path mapping), **INTG-04** (read source / write sidecar with permissions), **AUTO-01** (gap detection + queue), **AUTO-03** (source-sub-hash idempotency), **AUTO-04** (self-output exclusion).

**In scope:** pyarr-based Sonarr+Radarr discovery, the path-mapping layer + startup probe, filesystem source-sub discovery, gap detection, a one-shot CLI run that drives the Phase-2 engine per item, permission-correct sidecar writes, and extending the Phase-2 ledger with the source-sub hash.

**Out of scope (later phases):**
- **No long-running daemon, scheduler, webhooks, or filesystem watcher** — Phase 3 is a **one-shot CLI scan** (`trezarr run --once`). The APScheduler poll loop, the FastAPI webhook receiver, and the `watchfiles` watcher are **Phase 7** (Service Hardening).
- **No Bazarr API integration** — source-sub discovery is filesystem-based this phase. Reading Bazarr's subtitle inventory is **INTG-02 / Phase 10** (Source Selection).
- **No Series Bible / pronoun engine / relational consistency** — still Phases 4–6. Phase 3 reuses Phase 2's *mechanical* single pass unchanged.
- **No Docker image / s6-overlay / real privilege-drop** — Phase 3 applies PUID/PGID/UMASK to written files **in-process**; container init and true drop-privileges are **Phase 7**.
- **No quality scoring of an existing `vi` sub** — "lacks a *good* vi sub" is treated as presence-based this phase (no honored `vi` sidecar exists). Qualitative judgement is later.
- **No tag/monitored-status filtering UI** — process all monitored items the APIs return; selective filtering is deferred.

</domain>

<decisions>
## Implementation Decisions

Continues the project decision ledger (Phase 1 D-01…D-11, Phase 2 D-12…D-20). All numbered values are sensible defaults the planner/researcher may tune; all are overridable in planning.

### Run model
- **D-21: One-shot CLI run for the slice.** Phase 3 ships `trezarr run --once`: discover → resolve paths → find eligible items → translate each via the Phase-2 engine → write sidecars → exit. **No daemon, scheduler, webhook, or watcher** — all deferred to Phase 7. This proves the full path with the least new long-running surface.
- **D-30: Batch-run semantics — one bad item never aborts the slice.** Process all eligible items; a per-item failure quarantines that item (Phase 2 D-18 behavior) and the run continues. Emit an end-of-run summary (translated / skipped / quarantined / failed counts). The process exits non-zero if any item failed or was quarantined, zero otherwise.

### *arr discovery (INTG-01)
- **D-22: Discover via pyarr, Sonarr + Radarr both.** Use `pyarr` with `X-Api-Key` auth against Sonarr and Radarr `/api/v3`. Pull media identity, on-disk file paths, and metadata from the API — **never scan disk to discover** ("API for knowledge, filesystem for action"). Both TV episodes (Sonarr) and movies (Radarr) are handled in the same run; the per-item translate→gate→write path is identical. Drop to `httpx` only for a specific endpoint pyarr lacks (Phase-1 httpx already present).

### Path mapping + startup probe (INTG-03)
- **D-23: Path mapping = ordered remote→local find/replace pairs.** Mirror the *arr "remote path mapping" convention: a configured list of `{ from: <remote prefix>, to: <local prefix> }` pairs applied (longest-prefix / first-match) to every API-returned path before any filesystem use.
- **D-24: Fail-fast startup readability probe.** At startup, probe each configured local media root for existence + readability. If **any** root is unreadable, **refuse to start** with a clear, actionable error (exit non-zero) — surfacing the misconfig once at startup, never as silent per-file failures (success-criterion 2).

### Source-sub discovery + gap detection (AUTO-01)
- **D-25: Filesystem source-sub scan with a source-language priority.** Next to the resolved media path, scan for a source-language sidecar using a configured priority list, **default `["en"]`** (configurable, extendable). First match in priority order wins. No Bazarr dependency this phase.
- **D-26: Gap detection = source exists AND no honored `vi` sidecar.** An item is eligible when a source sub is found and there is no `vi` sidecar Trezarr would honor. "Honored `vi`" follows D-20 provenance: ours + source unchanged → skip; a **foreign** `vi` sub (not attributed to Trezarr) → **skip + log, never clobber** (Bazarr-collision safety, Pitfall 10).

### Idempotency (AUTO-03, AUTO-04)
- **D-27: Source-sub-hash idempotency.** Extend the Phase-2 ledger to record the **source-subtitle content hash** alongside the existing fields. Unchanged source + our `vi` present → **skip**; changed source (re-grab/upgrade) → **re-translate** and atomically overwrite *our own* output. Ledger stays schema-compatible with the Phase-4 `processed_file` table — additive only.
- **D-28: Self-output exclusion via provenance (AUTO-04).** Gap detection never selects Trezarr's own `.vi.srt`; the ledger provenance record is the mechanism (no watcher exists yet to loop on). Event-level watcher exclusion arrives with the watcher in Phase 7.

### Permissions (INTG-04)
- **D-29: Apply PUID/PGID/UMASK on write, in-process.** Read configured `PUID`, `PGID`, `UMASK`. After the Phase-2 atomic write completes, `os.chown` the sidecar to `PUID:PGID` and `os.chmod` per `UMASK` so the media server (Plex/Jellyfin/Bazarr) can read it — even before container init exists. Constrain all writes to within configured media roots (path-traversal guard). Real drop-privileges / s6-overlay container init is Phase 7.

### Claude's Discretion
Per the user's "you decide" on source-language default (resolved to English-first, configurable) and the standing delegation, planner/researcher retain latitude on: exact module/package layout (e.g. `trezarr/arr/`, `trezarr/discover/`, `trezarr/cli.py`, `trezarr/paths.py`); CLI framework (argparse / typer / click); whether the one-shot run translates items sequentially or with bounded concurrency (respecting the existing LLM semaphore); the hash algorithm for the source sub (reuse Phase-2's content-hash approach); exact new `TrezarrSettings` field names for *arr URLs/keys, path mappings, source-lang priority, and PUID/PGID/UMASK; ledger-extension storage shape (JSON field add vs. tiny SQLite seam); and how chown failures (non-root process can't chown to an arbitrary UID) degrade — log-and-continue vs. surface — provided the decisions above and the four phase success criteria hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` — INTG-01, INTG-03, INTG-04 (§Integration) and AUTO-01, AUTO-03, AUTO-04 (§Automation); the six requirements this phase delivers
- `.planning/ROADMAP.md` §"Phase 3: *arr Integration + First Vertical Slice" — goal + 4 success criteria

### Research (risk & stack grounding) — directly Phase-3-load-bearing
- `.planning/research/PITFALLS.md` — **Pitfall 8** (Docker path-mapping mismatch → find/replace mapping + startup readability probe + mirror *arr volume conventions); **Pitfall 9** (PUID/PGID/UMASK — sidecars unreadable to the media server); **Pitfall 10** (Bazarr `.vi.srt` collision + re-processing loop → provenance, never clobber a foreign vi, exclude own output); §Security row "Writing into arbitrary host paths via path-map → constrain writes to configured media roots"
- `.planning/research/ARCHITECTURE.md` — "API for knowledge, filesystem for action"; where the discover→resolve→translate→write seam sits
- `.planning/research/STACK.md` — `pyarr` (Sonarr/Radarr, X-Api-Key, `/api/v3`), `pydantic-settings` config surface (path mappings, PUID/PGID/UMASK, source-lang priority live here), hybrid webhook+poll guidance (the daemon half is Phase 7)
- `.planning/research/SUMMARY.md` — phase sequencing rationale

### Prior-phase foundations this phase consumes
- `.planning/phases/02-mechanical-translation-core-validation-gate/02-CONTEXT.md` — D-12…D-20, esp. **D-19** (atomic UTF-8 sidecar) and **D-20** (ledger provenance: skip-our-own / regenerate-on-source-change / never-clobber-foreign / retry-quarantined) — Phase 3 extends D-20 with the source-sub hash
- `.planning/phases/01-codec-llm-client-foundation/01-CONTEXT.md` — D-11 (layered config), D-04 (structured-output degradation already inside the LLM client)

### Existing code to reuse (do not reinvent)
- `trezarr/translate/engine.py` — `translate_file(path, settings, llm_client, ledger)` — the per-item entry point the CLI calls
- `trezarr/output/write.py` — `derive_vi_sidecar_path()`, `write_vi_sidecar()` (atomic temp+rename) — wrap chown/chmod around this
- `trezarr/output/ledger.py` — `Ledger`, `LedgerEntry` — extend with the source-sub hash field
- `trezarr/output/ledger.py` provenance + `trezarr/subtitles/srt.py` `read_srt()` — for source-sub read + hash
- `trezarr/config.py` — `TrezarrSettings` (layered env/YAML, SecretStr for keys) — add *arr URLs/keys, path mappings, source-lang priority, PUID/PGID/UMASK fields here

### External docs (canonical *arr references)
- TRaSH Guides — Remote Path Mappings: https://trash-guides.info/Radarr/Radarr-remote-path-mapping/ — the mapping model D-23 mirrors
- Servarr Docker Guide: https://wiki.servarr.com/docker-guide — PUID/PGID/UMASK + volume conventions (D-24, D-29)
- pyarr: https://github.com/totaldebug/pyarr — Sonarr/Radarr client, X-Api-Key, JSON results

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `translate_file()` (engine.py): the complete Phase-2 translate→gate→write pipeline — Phase 3 is mostly the *discovery + path-resolution + permission* shell that calls this per item. No translation logic changes.
- `write_vi_sidecar()` / `derive_vi_sidecar_path()` (write.py): atomic UTF-8 write + correct naming already done — Phase 3 layers chown/chmod (D-29) after the write returns.
- `Ledger` / `LedgerEntry` (ledger.py): idempotency + provenance already implemented (D-20). Phase 3 adds the source-sub hash field (D-27) — additive, Phase-4-schema-safe.
- `TrezarrSettings` (config.py): layered env→YAML→defaults config with SecretStr keys — the natural home for every new Phase-3 knob.

### Established Patterns
- "API for knowledge, filesystem for action" — discovery reads APIs; all file ops happen on resolved local paths after path mapping.
- Config is declarative `pydantic-settings`; secrets are `SecretStr`; `/config` is the state/volume root (`processed_files.json`, `config.yaml`, quarantine already live there).
- Failure = quarantine + log + continue, never a silent partial write (D-16/D-18 carry into the batch run via D-30).

### Integration Points
- New CLI entry (`trezarr run --once`) → discovery (pyarr) → path mapping/probe → source-sub scan → `translate_file()` per eligible item → permission-correct write → ledger update → summary.
- Path-mapping layer sits between every *arr-API path and every filesystem call (read source, write sidecar, probe roots).

</code_context>

<specifics>
## Specific Ideas

- The first slice is deliberately a **one-shot CLI** (`trezarr run --once`) so the full discover→translate→write path is proven before any long-running service machinery is introduced in Phase 7.
- Source-language default is **English-first** (`["en"]`), configurable — the relational-fidelity case for preferring an East-Asian source is explicitly a Phase-10 concern, not this slice.

</specifics>

<deferred>
## Deferred Ideas

- **Daemon / APScheduler poll loop, FastAPI webhook receiver, `watchfiles` watcher** — the always-on service that replaces `--once`. → Phase 7 (Service Hardening). Watcher-level self-output event exclusion also lands there.
- **Bazarr API source-sub discovery + intelligent source-language selection** for relational fidelity. → INTG-02 / Phase 10.
- **Docker image, s6-overlay, true drop-privileges** (vs. in-process chown/umask now). → Phase 7.
- **Tag/monitored-status/series include-exclude filtering** of what gets translated. → future tuning (Phase 10 per-series overrides territory).
- **Qualitative "is the existing vi sub good enough" judgement** (vs. presence-based gap detection now). → later, once the Bible/quality machinery exists.

</deferred>

---

*Phase: 3-arr-integration-first-vertical-slice*
*Context gathered: 2026-05-31*
