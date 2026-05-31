---
phase: 04
slug: series-bible-store-schema
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-01
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (already installed) |
| **Config file** | pyproject.toml / pytest.ini |
| **Quick run command** | `uv run pytest tests/bible tests/db -x --tb=short` |
| **Full suite command** | `uv run pytest -x --tb=short` |
| **Estimated runtime** | ~30 seconds (Phase 4 isolated) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/bible tests/db -x --tb=short`
- **After every plan wave:** Run `uv run pytest -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Filled in by planner. Each row maps a task to its automated test.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD     | TBD  | TBD  | TBD         | TBD        | TBD             | TBD       | TBD               | TBD         | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Test scaffolding the planner MUST stand up before any production code lands:

- [ ] `tests/db/conftest.py` — async engine fixture (temp-file SQLite, fresh per test), session fixture with transactional rollback
- [ ] `tests/bible/conftest.py` — populated-Bible fixtures (series + character + term_dictionary seed helpers)
- [ ] `tests/db/test_engine.py` — stubs for: engine boots, PRAGMAs applied at connect (foreign_keys=ON, journal_mode=WAL, synchronous=NORMAL)
- [ ] `tests/db/test_migrations.py` — stubs for: Alembic baseline applies on fresh DB, all 7 tables created, idempotent re-run
- [ ] `tests/bible/test_store.py` — stubs for: load_series_bible, get_character, lazy series creation (D-36)
- [ ] `tests/bible/test_merge.py` — stubs for: merge_inferred precedence (lock > prior > inference) — BIBLE-06 invariant
- [ ] `tests/bible/test_carry_forward.py` — stub for: S01E01 character flows to S01E05 unchanged unless event/lock — BIBLE-06 success criterion 4
- [ ] `tests/bible/test_bible_event.py` — stubs for: every mutation appends an event row in the same transaction — D-32 invariant
- [ ] `tests/output/test_ledger_sqlite.py` — stubs for: Ledger interface preserved (regression against existing JSON tests)
- [ ] `tests/output/test_ledger_migration.py` — stubs for: one-shot JSON→SQLite migration idempotent, commit-FIRST/rename-SECOND ordering, .migrated.bak created
- [ ] `tests/integration/test_translate_with_sqlite_ledger.py` — stub for: engine.translate_file passes regression with SQLite-backed Ledger

*Phase 4 introduces a new persistence layer; the test scaffolding above IS the Wave 0 work.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| First-boot startup creates `/config/trezarr.db` with correct PUID/PGID ownership | BIBLE-01 / Phase 7 boundary | Permission/ownership depends on docker runtime, can't assert in unit tests | Run `trezarr translate ...` with no DB present; verify file appears at expected path and is owned by configured user |
| WAL `-wal` / `-shm` sidecar files appear after first write | D-38 | WAL behavior depends on real fs (in-memory SQLite differs) | After running any translate, `ls /config/trezarr.db*` should show `.wal` and `.shm` siblings |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
