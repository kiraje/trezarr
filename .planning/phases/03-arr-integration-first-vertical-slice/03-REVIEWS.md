---
phase: 3
reviewers: [codex]
reviewed_at: 2026-06-01
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
  - 03-05-PLAN.md
skipped_reviewers:
  claude: "Running inside Claude Code (CLAUDE_CODE_ENTRYPOINT=cli); skipped for independence."
  gemini: "CLI not installed."
  coderabbit: "CLI not installed."
  opencode: "CLI not installed."
  qwen: "CLI not installed."
  cursor: "CLI not installed."
---

# Cross-AI Plan Review — Phase 3

> **Reviewer pool note:** This review was produced by **codex** only. The other AI CLIs in the standard pool (`gemini`, `coderabbit`, `opencode`, `qwen`, `cursor`) are not installed in this environment, and `claude` was skipped because this command was issued from inside a Claude Code session (independence rule). The “consensus” section below is therefore a distilled summary of the single reviewer’s output rather than a multi-AI agreement. To strengthen this review, install at least one more CLI (e.g. `gemini` or `cursor`) and re-run `/gsd-review --phase 3 --all`.

---

## Codex Review

## Summary

The Phase 3 plan set is strong overall: it preserves the intended MVP boundary, keeps the translation engine untouched, and builds the missing integration shell in a disciplined order: dependency/test surface, config/path mapping, *arr discovery, gap detection/permissions, then CLI orchestration. The biggest risks are not architectural but contract risks between plans: async vs sync mismatches, test stubs that are `xfail(strict=False)` masking real implementation drift, ambiguous ledger semantics, and the traversal guard being optional when `media_roots` is empty. With a few tightening edits, this should deliver the vertical slice.

## 03-01-PLAN.md Review

### Strengths

- Good Wave 0 discipline: installs dependencies and lays down tests before implementation.
- Explicitly pins the important pyarr 6.x import shape: `from pyarr import Sonarr, Radarr`, avoiding the common `SonarrAPI` / `RadarrAPI` trap.
- Covers all Phase 3 surfaces early: *arr discovery, path mapping, source scan, gap detection, CLI, config, permissions.
- Uses `pytest-httpx`, which matches pyarr’s `httpx` transport and avoids live Sonarr/Radarr dependency.
- Good security supply-chain posture through prior slopcheck verification.

### Concerns

- **MEDIUM:** `xfail(strict=False)` can allow stubs to unexpectedly pass without forcing removal of the xfail marker. This is acceptable for RED scaffolding, but later plans must explicitly remove or convert these markers. Otherwise the final suite can “pass” while Phase 3 tests remain non-binding.
- **MEDIUM:** The plan says “confirmed RED” but also “suite passes.” That is fine for xfail scaffolding, but the wording should distinguish “expected xfail” from true red tests. Otherwise downstream agents may misunderstand the desired state.
- **LOW:** The expected existing test count `63` is brittle. Any unrelated test addition will make the success statement stale.
- **LOW:** Dependency install versions are described as `pyarr 6.6.x` and `pytest-httpx 0.36.2`, but `uv add pyarr` may install newer compatible versions if available unless constrained.

### Suggestions

- Use explicit constraints if version stability matters:
  - `uv add "pyarr>=6.6,<6.7"`
  - `uv add --dev "pytest-httpx>=0.36,<0.37"`
- Add a required check in later plans: no Phase 3 implementation test remains marked xfail once its module is implemented.
- Replace “63 passed” success wording with “all pre-existing tests pass” to avoid brittle counts.

### Risk Assessment

**LOW-MEDIUM.** The plan is mostly safe. Main risk is process quality: xfail stubs can accidentally become permanent non-tests.

---

## 03-02-PLAN.md Review

### Strengths

- Correctly isolates the foundational layer: settings, path mapping, startup probe, traversal guard.
- Good decision to document `LedgerEntry.content_hash` as the source-subtitle hash instead of adding a duplicate `source_sub_hash`.
- Path mapping covers key edge cases: trailing slashes, longest-prefix match, passthrough.
- Secret handling is appropriately explicit with `SecretStr`.
- Correctly avoids `os.umask()` and keeps umask as data only.

### Concerns

- **HIGH:** `path_mappings: list[PathMapping] = []` uses a mutable default. Pydantic v2 often copies defaults, but the safer and clearer pattern is `Field(default_factory=list)`. Same for `source_lang_priority`.
- **HIGH:** `assert_within_media_roots()` defines allowed roots as the same configured local paths. If a user configures `remote: "/"`, `local: "/"`, the guard allows writes anywhere. This is called out as a threat, but the mitigation does not actually stop dangerously broad local roots.
- **MEDIUM:** `probe_media_roots()` only checks read access, while Phase 3 writes sidecars. Success criterion says unreadable paths fail fast, but INTG-04 also depends on writable paths. A media root can be readable but not writable.
- **MEDIUM:** `Path.resolve()` default behavior may differ when paths do not exist. If the target subtitle path does not exist yet, resolving its parent is safer than resolving the full output path.
- **MEDIUM:** `build_media_roots()` only uses local side of mappings. If no mappings are configured but *arr paths are already local, the traversal guard later becomes empty/disabled.
- **LOW:** Importing `PathMapping` from `trezarr.paths` into `config.py` is okay, but it creates a subtle ownership issue: a config schema model lives in a filesystem utility module.

### Suggestions

- Use:
  ```python
  from pydantic import Field

  path_mappings: list[PathMapping] = Field(default_factory=list)
  source_lang_priority: list[str] = Field(default_factory=lambda: ["en"])
  ```
- Add validation rejecting dangerously broad media roots like `/`, empty string, or possibly home/system roots unless explicitly allowed.
- Extend startup probe to check writability of roots or at least parent directories:
  - `os.access(root, os.R_OK | os.X_OK)`
  - optionally `os.access(root, os.W_OK)` if sidecars are always written under that root.
- Consider explicit `media_roots` as a separate setting instead of deriving trust boundaries solely from mappings.
- For traversal checks on output paths, validate `output_path.parent.resolve()` when the output file may not exist yet.

### Risk Assessment

**MEDIUM.** The foundation is sound, but the security guard can be bypassed by overly broad mappings, and write access is not probed.

---

## 03-03-PLAN.md Review

### Strengths

- Clean separation of *arr API discovery from translation and filesystem scanning.
- Good use of pyarr 6.x composition API.
- Correctly avoids disk scanning for media discovery.
- Radarr plan explicitly handles the common `movie["path"]` vs `movie["movieFile"]["path"]` bug.
- Good disabled-client behavior: returns `[]` without constructing pyarr clients.
- Secrets are resolved only at client construction.

### Concerns

- **HIGH:** The plan says `discover_sonarr_items()` and `discover_radarr_items()` are synchronous, but 03-05 later calls them from an async `_run_once()` without `await`, which is fine. However 03-05’s earlier research example used `await discover_sonarr_items(settings)`. The final plan is sync, but this mismatch should be explicitly settled across tests and implementation.
- **MEDIUM:** pyarr constructor arguments may require a full host URL or specific `host` formatting. The plan assumes `host="192.168.1.100", port=8989, tls=False`. Tests should catch URL generation, but live config ergonomics may suffer if users enter `http://host:8989`.
- **MEDIUM:** No handling for missing keys in API responses. A malformed or version-shifted response with no `path` will raise and abort discovery.
- **MEDIUM:** Discovery-level errors are re-raised, which means one unavailable service can abort the whole run even if the other service is enabled and healthy. That may be acceptable, but the phase’s D-30 “one bad item never aborts” only covers per-item translation, not discovery.
- **LOW:** `MediaItem.series_title` is used for movies too. The name is harmless but semantically muddy.
- **LOW:** Sonarr episode file discovery does not include episode number or episode title metadata. Not required for this phase, but useful for logs and later Series Bible context.

### Suggestions

- Add a small URL normalization helper or validation:
  - accept `sonarr_host="192.168.1.10"` and `sonarr_host="http://192.168.1.10:8989"` predictably, or document only one accepted form.
- Decide whether Sonarr failure should abort the run or produce `failed_discovery=1` while Radarr continues. For a one-shot MVP, aborting is defensible, but the CLI summary should make discovery failure clear.
- Use a neutral field name like `title` instead of `series_title` in `MediaItem`.
- Add defensive `.get("path")` checks and log skips for malformed episode/movie file records.

### Risk Assessment

**MEDIUM.** The module shape is good. Main risk is real-world pyarr/API shape drift and whether one failed *arr service should kill the whole run.

---

## 03-04-PLAN.md Review

### Strengths

- Correctly focuses on the core automation semantics: source-sub presence, foreign Vietnamese sidecar protection, source hash idempotency, quarantine retry.
- Good call to support both 2-letter and 3-letter language codes.
- Correctly uses `derive_vi_sidecar_path(source_sub_path)`, preserving Phase 2 naming behavior.
- `apply_permissions()` design is pragmatic: `PermissionError` warns and continues, `chmod` still runs, `os.umask()` is avoided.
- Foreign `vi` sidecar handling is appropriately conservative: skip, never clobber.

### Concerns

- **HIGH:** `is_eligible(source_sub_path, media_path, ledger)` takes `media_path` but does not use it. This is a smell and may hide a missing traversal check or output path validation. Either use it or remove it.
- **HIGH:** `scan_for_eligible_items()` returns tuples, but there is no typed dataclass for eligible work. This can become fragile when CLI, tests, and future queue/history code grow.
- **MEDIUM:** Source subtitle discovery only scans `media_stem.*.srt`. Some real-world subtitles include tags such as `Show.S01E01.en.forced.srt`, `Show.S01E01.default.en.srt`, or provider suffixes. Phase 3 can stay simple, but the limitation should be explicit.
- **MEDIUM:** If multiple candidates exist for the same language, `found[lang] = candidate` silently keeps the last filesystem iteration result, which is nondeterministic.
- **MEDIUM:** Gap detection treats `entry.status == "in_progress"` as eligible. That may be correct for crash recovery, but if another run is genuinely in progress, this permits duplicate work. Phase 3 has no daemon, so acceptable, but mention single-process assumption.
- **MEDIUM:** `apply_permissions()` catches all `OSError` from `chown` and `chmod` as warnings. A chmod failure can leave a sidecar unreadable while the run still counts as success.
- **LOW:** The plan’s verification grep says `grep -v "^#" trezarr/discover/gap.py | grep "os.umask"`; `gap.py` would not be expected to call `os.umask()` anyway. The meaningful check is in `write.py`.

### Suggestions

- Replace tuple return with a dataclass:
  ```python
  @dataclass(frozen=True)
  class EligibleItem:
      media_item: MediaItem
      source_sub_path: Path
      reason: str
      source_lang: str
  ```
- Either remove unused `media_path` from `is_eligible()` or use it to assert the source subtitle is adjacent to the media file.
- Make same-language collisions deterministic:
  - sort candidates by name
  - log if multiple candidates exist for one language
  - choose exact `{stem}.{lang}.srt` over variants if variants are later supported.
- Consider making `chmod` failure count as item failure, not just warning, because it directly threatens INTG-04.
- Add tests for uppercase language codes, e.g. `.EN.srt`, since the regex is case-insensitive and returns lowercase.

### Risk Assessment

**MEDIUM.** The logic covers the MVP, but tuple contracts and permission-error policy may cause subtle correctness gaps.

---

## 03-05-PLAN.md Review

### Strengths

- Correctly wires the vertical slice in the intended order: settings → startup probe → *arr discovery → gap detection → translation → traversal guard → permissions → summary.
- D-30 batch semantics are clear and testable.
- CLI remains scoped: no daemon, scheduler, webhook, or watcher creep.
- Good requirement that `probe_media_roots()` happens before API calls.
- Good requirement that `assert_within_media_roots()` happens before permission changes.
- Console script registration is included.

### Concerns

- **HIGH:** `_run_once()` calls `sys.exit(1)` inside an async function. This is awkward for tests and reuse. Returning an integer exit code from `_run_once()` and letting `main()` call `sys.exit(code)` is cleaner and avoids `SystemExit` control flow inside tests.
- **HIGH:** If `media_roots` is empty, traversal guard is skipped. The threat model accepts this because paths are “trusted *arr APIs on the same LAN,” but this weakens D-29. API responses and path mappings should still be treated as untrusted.
- **HIGH:** The plan instantiates `LLMClient(settings)` before knowing whether there are eligible items. If no items are eligible, this may still validate or require LLM settings unnecessarily.
- **MEDIUM:** Discovery exceptions happen before the per-item loop and are not represented in the summary. A Sonarr connection error may produce a traceback unless caught at `_run_once()` or `main()`.
- **MEDIUM:** The plan counts only eligible items. Items skipped by gap detection, no source subtitle, foreign vi, or already done are not included in `n_skip`, even though the summary says `skipped=N`. That makes the summary misleading.
- **MEDIUM:** The CLI says “per-item failure quarantines that item,” but the catch block only logs and increments `n_fail`. It does not explicitly quarantine through the ledger or existing Phase 2 quarantine mechanism unless `translate_file()` itself did so before raising.
- **MEDIUM:** `apply_permissions(result.output_path, ...)` assumes `result.output_path` is not `None` when status is `"done"`. This should be asserted or guarded.
- **LOW:** Requiring `--once` via `add_argument(..., required=True)` on a boolean optional can be awkward, though argparse supports it for optional args. A cleaner UX is `trezarr run --once` for now, but future `run` modes may need a subcommand or mutually exclusive group.

### Suggestions

- Make `_run_once()` return `int`:
  ```python
  async def _run_once(config_path: str | None) -> int:
      ...
      return 1 if n_fail or n_quar else 0

  def main() -> None:
      ...
      raise SystemExit(asyncio.run(_run_once(args.config)))
  ```
- Do not skip traversal guard when `media_roots` is empty. Instead either:
  - fail startup if no media roots/path mappings are configured, or
  - add explicit `media_roots` config for passthrough setups.
- Instantiate `LLMClient` only after `eligible` is non-empty.
- Include gap-detection skips in summary. For example, have `scan_for_eligible_items()` return both eligible items and skip counts/reasons.
- Catch discovery-level exceptions and exit with a clear one-line error instead of a traceback.
- If an unexpected exception happens after translation starts, record a failed/quarantined ledger entry if the existing ledger API supports it.
- Assert `result.output_path is not None` for `"done"` and treat violation as a failure.

### Risk Assessment

**MEDIUM-HIGH.** This is the riskiest plan because it is the integration point. The pipeline is right, but exit-code design, empty media roots, misleading skip counts, and discovery exception handling need tightening.

---

## Cross-Plan Concerns

- **HIGH:** The traversal guard depends on configured roots, but empty or overly broad roots reduce protection. D-29 should require a non-empty, non-root media root set before any write-capable run.
- **HIGH:** `xfail(strict=False)` stubs need a removal policy. By the end of Phase 3, all Phase 3 tests should be normal passing tests unless explicitly deferred.
- **MEDIUM:** The test and implementation contracts mix sync and async examples. Finalize: *arr discovery is sync in Phase 3; CLI `_run_once()` is async only because `translate_file()` is async.
- **MEDIUM:** The summary counters need clearer definitions. “Skipped” should include no source sub, already done, foreign vi, disabled services, or be renamed to only mean `translate_file()` returned `"skipped"`.
- **MEDIUM:** Permission correctness is partly best-effort. If `chmod` fails, the requirement “media server can read them” may not hold.
- **LOW:** Several plans require creating summary markdown files, but those outputs are process artifacts, not product deliverables. Fine for GSD, but they should not distract from verification.

## Overall Risk Assessment

**MEDIUM.**

The plans are coherent and likely to achieve the Phase 3 goal: a one-shot end-to-end *arr-discovered translation slice. The strongest parts are the phase boundary, dependency ordering, reuse of Phase 2 translation/write/ledger behavior, and explicit handling of foreign Vietnamese sidecars.

The main risks are integration-contract risks rather than missing features: empty media-root guard behavior, weak final enforcement of initially-xfailed tests, possible pyarr host/API shape mismatch, and summary/exit semantics that may not reflect all skipped or failed conditions. Addressing those before execution would make this a solid implementation plan.

---

## Consensus Summary

> Only one reviewer (codex) was available. The items below are codex’s findings re-grouped by severity and impact, **not** an inter-AI consensus.

### Agreed Strengths

- Phase boundary is well-respected: Phase 2 engine reused unchanged; no daemon, scheduler, or watcher creep.
- Dependency ordering across the five plans is clean (Wave 0 → config/paths → arr discovery → gap+permissions → CLI).
- Foreign `.vi.srt` collision safety (D-26) is correctly handled: skip + log, never clobber.
- `LedgerEntry.content_hash` is reused as the source-sub hash rather than introducing a parallel field (avoids the divergence risk in Pitfall 7).
- Security posture on secrets (`SecretStr`, resolved only inside client constructors) and dependency supply chain (slopcheck) is sound.

### Highest-Priority Concerns (HIGH)

1. **Traversal-guard weakening when `media_roots` is empty (03-02, 03-05).** D-29 silently degrades to a passthrough no-op if the user configures no path mappings — and the threat model accepts this. Recommend either failing startup when no media roots are configured, or introducing an explicit `media_roots` setting independent of `path_mappings`.
2. **Mutable default values on `path_mappings` and `source_lang_priority` (03-02).** Use `Field(default_factory=...)` rather than literal `[]`/`["en"]` on Pydantic model fields.
3. **`xfail(strict=False)` stubs have no removal policy (03-01).** Each implementation wave should explicitly remove the xfail marker once its module lands; otherwise Phase 3 tests can end up permanently non-binding.
4. **Unused `media_path` parameter in `is_eligible()` (03-04).** Either drop it or use it (e.g. to assert sub-adjacency or feed traversal validation).
5. **`scan_for_eligible_items()` returns bare tuples (03-04).** Promote to a small `EligibleItem` dataclass to keep the contract stable as later phases consume it.
6. **`_run_once()` calls `sys.exit()` from inside `async` (03-05).** Refactor to return an `int`; let `main()` translate it to `SystemExit`. Easier to test, easier to reuse.
7. **`LLMClient(settings)` instantiated unconditionally (03-05).** Construct it only when `eligible` is non-empty; otherwise an empty run unnecessarily exercises LLM config.

### Important Concerns (MEDIUM)

- **`probe_media_roots()` only checks readability.** INTG-04 also requires writability — extend the probe to `os.R_OK | os.X_OK` (and optionally `W_OK`).
- **`Path.resolve()` on a not-yet-existing sidecar.** Resolve `output_path.parent` instead, so traversal validation works for new files.
- **Discovery-level exceptions are unhandled (03-03, 03-05).** A Sonarr 401 or unreachable host will produce a traceback rather than a clean exit. Catch at the discovery boundary and decide whether one bad *arr service aborts the whole run or just zeroes that source.
- **Source-sub glob is rigid (03-04).** Real-world subs use suffixes like `.forced.srt`, `.default.en.srt`. Phase 3 may stay strict, but document the limitation explicitly.
- **Same-language collision is nondeterministic (03-04).** Sort `Path.glob()` results or pick exact `{stem}.{lang}.srt` first.
- **`apply_permissions()` swallows `chmod` errors (03-04).** A failed `chmod` directly threatens INTG-04 (media server readability); consider escalating to an item failure rather than a warning.
- **Summary counters are misleading (03-05).** Items skipped pre-translation (no source sub, foreign vi, already-done) are not represented in `n_skip`. Either widen the counters or rename to `translate_skipped`.
- **Sonarr host format (03-03).** Document whether `host` accepts bare IPs or full URLs and validate at settings load.

### Lower-Priority Concerns (LOW)

- Brittle “63 passed” success wording (03-01).
- `pyarr` and `pytest-httpx` should be version-pinned at install time (`uv add "pyarr>=6.6,<6.7"`).
- `MediaItem.series_title` is reused for movies — slight semantic mismatch; rename to `title`.
- `PathMapping` model lives in `paths.py` but is consumed as a config schema — minor ownership smell.
- `gap.py` `grep "os.umask"` verification is meaningful only against `write.py`.

### Divergent Views

Not applicable — only one reviewer.

---

*Reviewed 2026-06-01 by codex (gpt-5.5) only. Independence rule skipped `claude` (current runtime). Re-run with `--gemini`/`--cursor` once an additional CLI is installed to obtain a multi-AI consensus.*
