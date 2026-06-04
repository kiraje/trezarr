# Phase 3: *arr Integration + First Vertical Slice - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 3-arr-integration-first-vertical-slice
**Areas discussed:** Trigger model, Source-sub discovery, Permissions, Path mapping, *arr scope, Source language

---

## Trigger model (run shape)

| Option | Description | Selected |
|--------|-------------|----------|
| One-shot scan (CLI) | `trezarr run --once`: scan via API, translate everything missing, exit. Defers daemon/webhooks/watcher to Phase 7. | ✓ |
| Polling daemon now | APScheduler poll loop as part of Phase 3 — overlaps Phase 7 scope. | |
| You decide | Take the research-grounded default. | |

**User's choice:** One-shot scan (CLI)
**Notes:** Prove the full path with the least long-running surface; daemon/webhook/watcher → Phase 7. → D-21.

---

## Source-sub discovery

| Option | Description | Selected |
|--------|-------------|----------|
| Filesystem scan | Look next to media for a source-lang sidecar via a configured priority; "missing vi" = no honored .vi.srt. No Bazarr dep. | ✓ |
| Query Bazarr API | Ask Bazarr's inventory — pulls INTG-02/Phase 10 forward. | |
| You decide | Take the default. | |

**User's choice:** Filesystem scan
**Notes:** Matches ROADMAP wording ("located on the shared filesystem"); Bazarr is INTG-02/Phase 10. → D-25, D-26.

---

## Permissions depth

| Option | Description | Selected |
|--------|-------------|----------|
| Apply PUID/PGID/UMASK on write | chown/chmod each written sidecar per configured PUID/PGID/UMASK, in-process. Satisfies criterion 3 now. | ✓ |
| Group-readable writes only | Defer all PUID/PGID/chown to Phase 7 container init. | |
| You decide | Take the default. | |

**User's choice:** Apply PUID/PGID/UMASK on write
**Notes:** Real privilege-drop / s6 init stays Phase 7. → D-29.

---

## Path mapping + startup probe

| Option | Description | Selected |
|--------|-------------|----------|
| find/replace pairs + hard-fail startup | remote→local mapping pairs (mirror *arr); probe each root at startup, refuse to start if any unreadable. | ✓ |
| find/replace pairs + warn-and-continue | Same format but warn and keep running on unreadable root. | |
| You decide | Take the default. | |

**User's choice:** find/replace pairs + hard-fail startup
**Notes:** Strongest read of success-criterion 2 (clear error at startup, not silent per-file). → D-23, D-24.

---

## *arr scope

| Option | Description | Selected |
|--------|-------------|----------|
| Both Sonarr + Radarr | Discover TV episodes and movies in one run; identical per-item path. Fully satisfies INTG-01. | ✓ |
| Sonarr-first | TV only this phase; Radarr later. | |
| You decide | Take the default. | |

**User's choice:** Both Sonarr + Radarr
**Notes:** pyarr + shared translate path make both nearly free. → D-22.

---

## Source language (default priority)

| Option | Description | Selected |
|--------|-------------|----------|
| English-first | Default `["en"]`, configurable. | (default applied) |
| Configured list, no default | Require explicit config; skip if unset. | |
| You decide | Take the default. | ✓ |

**User's choice:** You decide → resolved to English-first, configurable list
**Notes:** Relational-fidelity source selection is explicitly Phase 10. → D-25.

---

## Claude's Discretion

- Source-language default (resolved to English-first, configurable) — user delegated.
- Module/package layout, CLI framework, sequential vs bounded-concurrency run, hash algorithm reuse, new config field names, ledger-extension storage shape, and chown-failure degradation — all delegated to planner/researcher within the locked decisions (see CONTEXT.md §Claude's Discretion).

## Deferred Ideas

- Daemon / APScheduler poll loop, FastAPI webhook receiver, watchfiles watcher (+ watcher self-output exclusion) → Phase 7.
- Bazarr API source-sub discovery + intelligent source-language selection → INTG-02 / Phase 10.
- Docker image, s6-overlay, true drop-privileges → Phase 7.
- Tag/monitored-status/series include-exclude filtering → future tuning.
- Qualitative "is the existing vi sub good enough" judgement → later.
