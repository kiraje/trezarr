---
phase: quick-260612-dmh
plan: "01"
type: tdd
wave: 1
depends_on: []
files_modified:
  - trezarr/config.py
  - trezarr/web/worker.py
  - tests/web/test_worker_transient_retry.py
autonomous: true
requirements:
  - P0-AUTO-RETRY-TRANSIENT
must_haves:
  truths:
    - "When a job finishes as quarantined with a TRANSIENT reason (Empty/whitespace-only, Missing line, Parsed N lines but expected), worker automatically re-enqueues it after job_auto_retry_delay_s seconds, up to job_auto_retry_max attempts, logging WARNING job_auto_retry job_id=N attempt=K/MAX reason=..."
    - "TRANSIENT auto-retries increment job.attempts (the existing DB column) on each re-run attempt; no new DB column is needed — the count is already persisted and visible in /api/jobs"
    - "Gate-check quarantines (Check 1-12 content defects: CJK leak, scaffolding, diacritics, etc.) are NOT auto-retried; only the BatchValidationError parse-contract family (TRANSIENT allowlist) is eligible"
    - "Setting job_auto_retry_max=0 disables auto-retry entirely (prod-safe off switch)"
    - "The existing manual retry endpoint (/api/jobs/{id}/retry) continues to work and is independent of the auto-retry counter"
    - "A single-queue semantics guarantee holds: the delayed re-enqueue calls enqueue_job, which already enforces the dedup guard (D-66) — no concurrent duplicate of the same job is possible"
    - "Full pytest suite (661 tests baseline) stays green"
  artifacts:
    - path: "trezarr/config.py"
      provides: "job_auto_retry_max (int, default 2) and job_auto_retry_delay_s (float, default 30.0) settings fields"
      contains: "job_auto_retry_max"
    - path: "trezarr/web/worker.py"
      provides: "_TRANSIENT_QUARANTINE_PREFIXES constant + _is_transient_quarantine() helper + auto-retry logic in _execute_job post-quarantine block"
      contains: "_TRANSIENT_QUARANTINE_PREFIXES"
    - path: "tests/web/test_worker_transient_retry.py"
      provides: "TDD RED+GREEN tests: transient reasons trigger retry, non-transient do not, max=0 disables, max exhausted stops, WARNING log emitted"
      contains: "test_transient_quarantine_triggers_auto_retry"
  key_links:
    - from: "trezarr/web/worker.py:_execute_job"
      to: "trezarr/web/worker.py:enqueue_job"
      via: "asyncio.create_task(asyncio.sleep(delay) then enqueue_job(...))"
      pattern: "enqueue_job.*source_path.*trigger.*auto-retry"
    - from: "trezarr/web/worker.py:_TRANSIENT_QUARANTINE_PREFIXES"
      to: "trezarr/translate/engine.py:BatchValidationError messages"
      via: "substring/prefix match on item_result.reason"
      pattern: "_is_transient_quarantine"
---

<objective>
P0 stability fix: job-level auto-retry for TRANSIENT quarantine classes.

Live evidence (2026-06-12): MK E02 quarantined 4x with "Empty/whitespace-only text for line [N] in LLM response" (deepseek partial/bare-number responses). Each required a MANUAL /api/jobs/{id}/retry; attempt 5 succeeded. E19 and E01 also each lost one attempt to the same class tonight. Unattended overnight runs die on the first transient — this is the top-ranked stability item in the core-quality campaign perf profile.

Purpose: Eliminate manual intervention for the BatchValidationError parse-contract family (Empty/whitespace-only, Missing line [N], Parsed N lines but expected M). Gate-check quarantines (content defects: CJK leak, scaffolding, diacritics) remain non-retriable — retry for those burns 20+ min for the same outcome; the multi-cue gate repair (IMP-02b) already handles them in-run.

Output: Two new config knobs (job_auto_retry_max=2, job_auto_retry_delay_s=30), a TRANSIENT allowlist constant + helper in worker.py, and post-quarantine auto-retry logic that schedules a delayed re-enqueue via asyncio.create_task + enqueue_job (reusing the existing D-66 dedup guard). No new DB column, no schema migration — job.attempts already exists and persists the count.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/quick/260612-dmh-p0-auto-retry-transient-quarantines-at-j/260612-dmh-PLAN.md
@trezarr/web/worker.py
@trezarr/config.py
@trezarr/jobs/models.py
</context>

<tasks>

<task type="tdd" tdd="true">
  <name>Task 1 (RED): Write failing tests for transient auto-retry behavior</name>
  <files>tests/web/test_worker_transient_retry.py</files>
  <behavior>
    - test_transient_quarantine_triggers_auto_retry: when _execute_job produces item_result.status="quarantined" with reason="Empty/whitespace-only text for line [1] in LLM response" and job_auto_retry_max=2, worker must schedule a re-enqueue; assert enqueue_job called with trigger="auto-retry" (or equivalent) and asyncio.create_task was invoked for the delayed schedule.
    - test_non_transient_quarantine_does_not_retry: reason="CJK script leaked into translated cue" (a gate-check reason) must NOT trigger auto-retry; enqueue_job not called for retry.
    - test_missing_line_prefix_is_transient: reason="Missing line [3] in LLM response (expected 8 lines)" matches TRANSIENT allowlist.
    - test_parsed_lines_mismatch_is_transient: reason="Parsed 4 lines but expected 8 (expected_count=8)" matches TRANSIENT allowlist.
    - test_auto_retry_max_zero_disables: job_auto_retry_max=0 → no re-enqueue even for transient reason.
    - test_auto_retry_warning_logged: transient quarantine with max=2 must emit a WARNING log line containing "job_auto_retry" and "attempt=1/2".
    - test_auto_retry_exhausted_stops: when job has already auto-retried max times (tracked by job.attempts count compared against max), no further re-enqueue is scheduled.

    Helper structure: use the same mock_session_factory pattern from test_worker.py (mock_session.get returns fake_job, mock_session.commit = AsyncMock). Patch enqueue_job and asyncio.create_task to assert call counts without actually running a sleep or DB.

    All tests must FAIL (RED) at this point — _execute_job has no auto-retry logic yet.
  </behavior>
  <action>
    Create tests/web/test_worker_transient_retry.py with the 7 behavior tests listed above.

    Import structure:
    - `from unittest.mock import AsyncMock, MagicMock, patch, call`
    - `from trezarr.web import worker as worker_mod`
    - Use `caplog` pytest fixture (with `caplog.set_level(logging.WARNING)`) to assert the WARNING log.

    For each test that exercises _execute_job, build a `fake_job` MagicMock with:
    - `fake_job.series_id = None`
    - `fake_job.source_path = "/test/ep.en.srt"`
    - `fake_job.media_item_json = None`  (mechanical path — simpler for these tests)
    - `fake_job.status = "queued"`
    - `fake_job.attempts = 0`

    Make `fake_process_one_item` return a MagicMock with `result.status = "quarantined"` and `result.reason = <the reason under test>`. Wire the mock_session_factory as in test_worker.py (mock_session.get = AsyncMock(return_value=fake_job), mock_begin_ctx pattern).

    The key assertion in test_transient_quarantine_triggers_auto_retry: patch `trezarr.web.worker.enqueue_job` with an AsyncMock and assert it was awaited with `trigger="auto-retry"` (or whatever trigger string is chosen — keep consistent with worker.py implementation). Also assert asyncio.create_task was called (patch `asyncio.create_task` if needed, or patch `trezarr.web.worker.asyncio.create_task`).

    For test_auto_retry_exhausted_stops: set `fake_job.attempts = 2` (already used the auto-retry budget when max=2) — the post-quarantine block must check whether the current attempts already >= some threshold and skip re-enqueue.

    Run after writing: `uv run pytest tests/web/test_worker_transient_retry.py -x -q 2>&1 | tail -20` — confirm all 7 tests FAIL (not ImportError, not SyntaxError — actual assertion failures or AttributeError showing the missing constants/logic).
  </action>
  <verify>
    <automated>uv run pytest tests/web/test_worker_transient_retry.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>All 7 tests collected and FAILING (RED) with assertion errors or AttributeError referencing missing worker attributes — not import or syntax errors.</done>
</task>

<task type="tdd" tdd="true">
  <name>Task 2 (GREEN): Implement transient auto-retry in config + worker</name>
  <files>trezarr/config.py, trezarr/web/worker.py</files>
  <behavior>
    After this task:
    - All 7 new tests pass (GREEN).
    - Full suite still passes: `uv run pytest -x -q 2>&1 | tail -5` shows 668 passed (661 + 7).
  </behavior>
  <action>
    STEP A — trezarr/config.py: add two fields after `job_max_auto_attempts` (around line 229):

      # ── Transient-quarantine auto-retry (P0 campaign, 260612-dmh) ────────────
      # When a job quarantines due to a transient LLM response defect (empty/missing
      # lines — BatchValidationError parse-contract family), automatically re-enqueue
      # it after job_auto_retry_delay_s seconds, up to job_auto_retry_max times.
      # Set job_auto_retry_max=0 to disable (prod-safe). Gate-check quarantines
      # (content defects: CJK leak, scaffolding, diacritics) are never auto-retried.
      job_auto_retry_max: int = 2
      job_auto_retry_delay_s: float = 30.0

    STEP B — trezarr/web/worker.py: add constants and helper near the top of the file, after the existing `_TERMINAL_STATUSES` constant (around line 55):

      # Transient quarantine reason prefixes/substrings that are eligible for
      # automatic job-level retry (P0 campaign, 260612-dmh). These are all
      # BatchValidationError parse-contract failures — deepseek returning partial,
      # bare-number, or empty numbered-list responses. NOT included: gate-check
      # quarantines (Check 1-12 content defects) where retry burns 20+ min for the
      # same likely outcome (multi-cue gate repair handles those in-run via IMP-02b).
      _TRANSIENT_QUARANTINE_PREFIXES: tuple[str, ...] = (
          "Empty/whitespace-only text for line [",
          "Missing line [",
          "Parsed ",  # "Parsed N lines but expected M"
      )

      def _is_transient_quarantine(reason: str | None) -> bool:
          """Return True if reason matches a TRANSIENT quarantine class eligible for auto-retry."""
          if not reason:
              return False
          return any(reason.startswith(prefix) for prefix in _TRANSIENT_QUARANTINE_PREFIXES)

    NOTE on "Parsed " prefix: this is intentionally broad (matches "Parsed N lines but expected M" from engine.py:906). It does NOT collide with any gate-check reasons (gate checks use phrases like "CJK script", "scaffolding", "diacritic", "honorific", etc.) — confirm with a grep if uncertain.

    STEP C — trezarr/web/worker.py: in `_execute_job`, inside the `try` block, after the `async with session_factory() as session:` block that updates job status (currently ending around line 556 with `await session.commit()`), add the auto-retry hook BEFORE the `except Exception:` clause:

      The hook goes directly after the final `await session.commit()` in the successful-execution path (where `item_result.status` was set). Structure:

        # ── Transient auto-retry (P0 campaign, 260612-dmh) ──────────────────
        if (
            item_result.status == "quarantined"
            and _is_transient_quarantine(item_result.reason)
            and settings.job_auto_retry_max > 0
        ):
            # job.attempts was already incremented at the start of this execution.
            # If we are still within budget, schedule a delayed re-enqueue.
            # Re-read attempts from the committed DB state (job was re-fetched above).
            current_attempts = job.attempts or 0
            if current_attempts < settings.job_auto_retry_max:
                logger.warning(
                    "job_auto_retry job_id=%d attempt=%d/%d reason=%s — "
                    "scheduling re-enqueue in %.0fs",
                    job_id,
                    current_attempts,
                    settings.job_auto_retry_max,
                    item_result.reason,
                    settings.job_auto_retry_delay_s,
                )

                async def _delayed_reenqueue(
                    _sf=session_factory,
                    _sp=source_path,
                    _sid=series_id,
                    _mij=media_item_json,
                    _delay=settings.job_auto_retry_delay_s,
                ) -> None:
                    await asyncio.sleep(_delay)
                    await enqueue_job(
                        _sf,
                        _sp,
                        series_id=_sid,
                        trigger="auto-retry",
                        media_item=None if _mij is None else SimpleNamespace(**_mij),
                    )

                t = asyncio.create_task(_delayed_reenqueue())
                _background_tasks.add(t)
                t.add_done_callback(_background_tasks.discard)
            else:
                logger.warning(
                    "job_auto_retry job_id=%d: auto-retry budget exhausted "
                    "(%d/%d attempts); will not re-enqueue automatically. "
                    "Use a manual retry to force.",
                    job_id,
                    current_attempts,
                    settings.job_auto_retry_max,
                )

    TRIGGER VALUE: use `trigger="auto-retry"` — this is a NEW trigger value. The CheckConstraint on `ck_job_trigger` in the DB currently allows: `{poll, webhook, manual, manual-retry, startup-reconcile}`. "auto-retry" is NOT in the current constraint, so inserting with this trigger will raise IntegrityError at runtime.

    ALEMBIC MIGRATION REQUIRED: create alembic/versions/0005_job_trigger_auto_retry.py following the pattern of 0004_job_trigger_manual.py (batch_alter_table recreate="always", drop+recreate ck_job_trigger to add "auto-retry"). Set `revision = "0005"`, `down_revision = "0004"`. The new constraint value set: `{poll, webhook, manual, manual-retry, startup-reconcile, auto-retry}`.

    Also update the CheckConstraint in trezarr/jobs/models.py to match:
      "trigger IN ('poll','webhook','manual','manual-retry','startup-reconcile','auto-retry')"

    MANUAL RETRY SEMANTICS: the existing manual retry endpoint calls `enqueue_job(trigger="manual-retry")`. That is independent — it already bypasses the cap (only "poll" and "webhook" are in `_AUTO_TRIGGERS`). No change needed to the manual retry endpoint.

    SETTINGS THREADING: `settings` is already passed into `_execute_job` as a parameter. Access `settings.job_auto_retry_max` and `settings.job_auto_retry_delay_s` directly — no import changes needed.

    After implementing, run: `uv run pytest tests/web/test_worker_transient_retry.py -x -q 2>&1 | tail -10` to confirm GREEN, then `uv run pytest -x -q 2>&1 | tail -5` for full suite.
  </action>
  <verify>
    <automated>uv run pytest tests/web/test_worker_transient_retry.py -v 2>&1 | tail -15 && uv run pytest -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>All 7 new tests pass. Full suite passes (668+ tests). `_TRANSIENT_QUARANTINE_PREFIXES` constant exists in worker.py. `job_auto_retry_max` and `job_auto_retry_delay_s` exist in config.py. Migration 0005 adds "auto-retry" to ck_job_trigger. WARNING log fires with "job_auto_retry job_id=N attempt=K/MAX reason=...".</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| item_result.reason → retry decision | The reason string comes from the translation engine (internal); no external input crosses here. Substring match on a fixed allowlist is safe. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-dmh-01 | Denial of Service | auto-retry loop | mitigate | `job_auto_retry_max` cap (default 2) bounds retries per quarantine event; `job_max_auto_attempts` (existing, default 5) bounds total poll-cycle re-enqueues; both caps compose to bound total LLM spend. |
| T-dmh-02 | Tampering | ck_job_trigger constraint | mitigate | Alembic migration 0005 extends the CHECK constraint to include "auto-retry" before any rows are inserted; the constraint is the DB-level enforcement. |
| T-dmh-03 | Elevation of Privilege | "Parsed " prefix match | accept | The prefix "Parsed " is broad but only matches engine.py parse-contract failures; gate-check reasons never start with "Parsed "; risk is one non-transient reason accidentally being retried — low impact (one extra LLM call, same quarantine outcome). |
</threat_model>

<verification>
1. `uv run pytest tests/web/test_worker_transient_retry.py -v` — all 7 new tests pass
2. `uv run pytest -x -q 2>&1 | tail -5` — full suite passes (668+ tests, 0 failures)
3. `grep -n "job_auto_retry_max\|job_auto_retry_delay_s" trezarr/config.py` — both fields present with defaults 2 and 30.0
4. `grep -n "_TRANSIENT_QUARANTINE_PREFIXES\|_is_transient_quarantine" trezarr/web/worker.py` — constant and helper present
5. `grep -n "auto-retry" alembic/versions/0005_job_trigger_auto_retry.py` — migration contains "auto-retry" in the constraint
6. `grep -n "job_auto_retry" trezarr/web/worker.py` — WARNING log line with "job_auto_retry job_id=" present
</verification>

<success_criteria>
- Unattended overnight runs with deepseek transient failures (empty/partial numbered lists) recover automatically within job_auto_retry_delay_s seconds instead of dying quarantined.
- Gate-check quarantines (Check 1-12 content defects) are never auto-retried (confirmed by test_non_transient_quarantine_does_not_retry).
- `docker logs trezarr` shows WARNING lines: "job_auto_retry job_id=N attempt=K/MAX reason=Empty/whitespace-only..." when retry fires.
- Manual /api/jobs/{id}/retry endpoint continues to work independently (unaffected).
- job.attempts increments on each execution (existing behavior) — visible in /api/jobs response and usable to audit how many attempts a job consumed.
- Full 661-test baseline stays green with 7 new tests added.
</success_criteria>

<output>
Create `.planning/quick/260612-dmh-p0-auto-retry-transient-quarantines-at-j/260612-dmh-SUMMARY.md` when done.
</output>
