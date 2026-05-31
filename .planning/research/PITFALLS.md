# Pitfalls Research

**Domain:** Automated, unattended LLM Vietnamese subtitle translation (companion to Bazarr/*arr stack)
**Researched:** 2026-05-31
**Confidence:** HIGH for structural/format/integration pitfalls (verified against tool implementations, *arr issue trackers, subtitle-MT literature); MEDIUM for Vietnamese-specific and Series-Bible pitfalls (verified against linguistics sources + MT research, but Trezarr's Bible mechanism is novel so failure modes are reasoned, not observed).

These pitfalls are organized around the one promise that can break: **"consistent, blind-trust, replace-human-translator."** Every critical pitfall below is one that silently produces a wrong-but-plausible file the user will never review — the worst outcome for an unattended system.

---

## Critical Pitfalls

### Pitfall 1: Line-count drift / structural desync between source and output

**What goes wrong:**
The LLM merges two source cues into one fluent sentence, splits one into two, or drops/adds a line. Output no longer has a 1:1 mapping to source cues. Once one line is lost, **every subsequent timestamp is wrong** (off-by-one cascade) — subtitles drift later and later until they're captioning the wrong scene. In an unattended pipeline this ships silently.

**Why it happens:**
LLMs optimize for fluent prose, not structural fidelity. "He said X. Then Y." is more natural as one sentence than two. Long files exceed context/output budgets and the tail gets truncated or summarized. Batching across cue boundaries lets the model re-segment.

**How to avoid:**
- **Never let the model touch timestamps or indices.** Strip timecodes + cue numbers locally, send only text, re-attach originals after translation (the universal approach in `chatgpt-subtitle-translator`, `subtitle-translator`, Immersive Translate).
- Translate with an **explicit per-cue ID schema** (numbered lines in / numbered lines out) and **validate line count after every batch**. On mismatch, retry with a smaller batch (cascading batch-size fallback: e.g. 20→10→5→1).
- Treat the 1:1 invariant as a **hard gate**: a file that fails count validation after retries must NOT be written — quarantine it and log loudly.
- For ASS where merging is sometimes legitimate, validate on **time-span boundary match** rather than raw count (the `timestamp`-mode trick from `chatgpt-subtitle-translator`).

**Warning signs:**
Output cue count ≠ input cue count; subtitle that displays correctly at the start of a file but drifts out of sync toward the end; a single merged cue early in the file.

**Phase to address:** Core translation engine phase — the per-cue invariant and count-validation gate are foundational, not a polish item.

---

### Pitfall 2: Wrong relational pronoun (rude vs intimate) — the core-value failure

**What goes wrong:**
Vietnamese has no neutral I/you; every line encodes the speaker→addressee relationship (anh/em, chị/em, ông/bà, con/bố...). The model picks the wrong pair: a subordinate addresses a king casually, lovers address each other with cold formality, or — worst — an intimate/condescending term where a respectful one is required. The subtitle is grammatical and fluent but **socially wrong or insulting**, which a Vietnamese viewer registers instantly. This is the exact failure ordinary MT makes and the entire reason Trezarr exists.

**Why it happens:**
Subtitles rarely carry speaker labels, so speaker/addressee must be inferred. English source has already flattened all relationships to "I/you" — the relational information is **gone** by the time it reaches a model translating from English. Romantic convention (man = anh, woman = em regardless of actual age) and register (historical/formal vs casual) override the naive age-based default.

**How to avoid:**
- The **directed Address Map** in the Series Bible is the mitigation — but it only works if speaker/addressee attribution per line is reliable (see Pitfall 3) and the map is grounded in real relationship facts, not guesses.
- **Source selection matters here, not just for fidelity:** prefer a source language that preserves relational info (Chinese/Korean/Japanese honorifics) over English for East-Asian content. Translating relationships *from English* is reconstructing information that was destroyed.
- Ground register in media metadata (genre/era from Sonarr/Radarr/TMDB) so historical drama ≠ sitcom default.
- The **self-review pass** should specifically check pronoun-pair consistency against the Bible, not just fluency.

**Warning signs:**
Same character pair using different pronoun pairs within one episode; default `tôi`/`bạn` (the MT-flattened neutral) appearing for characters with a known relationship; pronoun choices that ignore the register set in the Bible.

**Phase to address:** Series Bible + attribution phase (the pronoun engine) and source-selection phase. This is the product's core value — it deserves the deepest research and its own validation harness.

---

### Pitfall 3: Mis-inferred speaker/addressee flipping the pronoun pair

**What goes wrong:**
Attribution is the input to the pronoun engine. If the model guesses the wrong speaker or addressee for a line, it confidently applies the **inverted** pair (em↔anh), producing a junior speaking down to a senior. One wrong attribution can poison a whole exchange.

**Why it happens:**
Subtitles have no speaker tags. Rapid back-and-forth dialogue, overheard/narrated lines, group scenes, and phone calls make turn assignment ambiguous. The model fills the gap with a plausible guess and never signals low confidence.

**How to avoid:**
- Use **surrounding-line context windows** for attribution, not single lines.
- Have attribution emit a **confidence signal**; low-confidence lines should fall back to a safe, relationship-neutral-but-not-rude default rather than a confident wrong pair.
- The self-review pass should re-check that pronoun direction is consistent within a conversational turn (A→B and B→A should be reciprocal per the Address Map).

**Warning signs:**
Non-reciprocal pronouns inside one exchange (A calls B "em" while B also calls A "em"); pronoun pair flips mid-conversation with no relationship event.

**Phase to address:** Attribution sub-component of the Series Bible / translation phase.

---

### Pitfall 4: Series Bible drift, contradiction, and staleness after user edits

**What goes wrong:**
The Bible is the consistency backbone, but across 12+ episodes it can: (a) **drift** — episode 8 invents a new pronoun pair contradicting episode 1; (b) **go stale** — the user manually corrects a term/pronoun, but later episodes re-derive the old value and overwrite the human fix, defeating the "human override valve"; (c) **bloat** — every minor character and one-off term accumulates until the Bible no longer fits in the context budget and gets silently truncated.

**Why it happens:**
Each episode re-runs the LLM, which is stochastic — re-derivation produces slightly different values. Without a lock/precedence mechanism, the newest LLM output wins over the human edit. Without pruning, append-only growth is inevitable.

**How to avoid:**
- **Locked fields:** user edits set a "locked" flag; locked entries are read-only context the model must follow and may never overwrite. Make precedence explicit: human lock > prior established value > new inference.
- **Append with provenance, not overwrite:** track where each value came from (inferred ep.N / user-edited) and which episode established it, so corrections propagate forward deterministically.
- **Relationship evolution needs explicit episode markers**, not silent reassignment — "enemies→lovers at S02E04" is a logged transition, so pronoun changes are intentional and auditable, not drift.
- **Bible budgeting:** cap/prune by salience (recurring characters and terms, not one-off extras). The PROJECT scope says cost isn't a v1 concern, but **context-window overflow is a correctness concern** — a truncated Bible silently drops the very consistency it exists to provide.

**Warning signs:**
A user-edited value reverting in a later episode; Bible size growing without bound; a pronoun pair changing across episodes with no logged relationship event; Bible exceeding model context limit (silent truncation).

**Phase to address:** Series Bible persistence/lifecycle phase. The lock/precedence model is a design decision that must be settled before multi-episode runs.

---

### Pitfall 5: Concurrency races — parallel episodes of one series mutating one Bible

**What goes wrong:**
Trezarr is a long-running service watching a library; multiple episodes of the same series can be queued and translated in parallel. Two episodes read the same Bible, each derives new entries, each writes back — last-write-wins clobbers the other's updates, or the Bible file is corrupted by interleaved writes. Cross-episode consistency (the core value) is destroyed by a data race.

**Why it happens:**
Naive file-based state + parallel workers + no locking. Easy to miss because it only manifests under concurrent load, not in single-file testing.

**How to avoid:**
- **Serialize Bible mutation per series** (per-series lock / single-writer queue). Episodes of the *same* series should not update the Bible concurrently; different series can run in parallel freely.
- Consider processing a series' episodes **in order** for Bible-building, since later episodes depend on earlier relationship state anyway.
- Atomic writes (write-temp-then-rename) so a crash mid-write never leaves a corrupt Bible.

**Warning signs:**
Bible entries disappearing/reverting after a parallel run; corrupted/half-written Bible file; inconsistent results that aren't reproducible single-threaded.

**Phase to address:** Service/orchestration + Bible persistence phase.

---

### Pitfall 6: ASS/SSA override tags translated, mangled, or stripped

**What goes wrong:**
ASS dialogue lines contain inline override tags — `{\an8}` (position), `{\pos(x,y)}`, `{\i1}`, color `{\c&H...&}`, fonts, and karaoke `\k/\kf/\ko` timing — plus `\N` hard line breaks. A naive translator sends the whole `Text` field to the LLM, which translates tag contents, drops braces, reorders or "fixes" them. Result: typesetting destroyed, signs mispositioned, karaoke timing broken, or the line fails to render. For anime/fansub users this is unacceptable.

**Why it happens:**
Treating ASS like SRT (translate the text field wholesale). The model sees `{\pos(192,50)}Hello` and helpfully "improves" it.

**How to avoid:**
- **Parse out override blocks `{...}` and `\N` before translation; translate only the plain-text spans; reassemble** with tags byte-identical and in original order (the documented correct approach; most tools get this wrong).
- Keep `\k` karaoke tags attached to their syllables — naive translation breaks per-syllable timing. If syllable count changes, karaoke can't be cleanly remapped; for v1, **preserve karaoke lines verbatim rather than corrupt them** if remapping is too risky.
- Preserve `\N` break positions or re-flow deliberately; don't let the model invent or delete breaks.
- Don't touch the `[Script Info]`, `[V4+ Styles]`, font-embedding, or `[Events]` non-Dialogue lines.

**Warning signs:**
Output ASS with fewer/altered `{...}` blocks than input; translated text inside braces; signs rendering in the wrong screen position; karaoke desync; missing `\N`.

**Phase to address:** ASS/SSA format-handling phase (after SRT baseline). Flag for dedicated research — ASS tag grammar is intricate.

---

### Pitfall 7: Silent failure / writing an unvalidated bad file in unattended mode

**What goes wrong:**
Because no human reviews output, ANY undetected error (truncated file, partial translation, untranslated lines passed through, encoding garbage, JSON/format-mode parse failure on a long file) gets written as the final `Show.S01E01.vi.srt` and trusted forever. The promise is blind trust — so a silent failure is a betrayal of the core contract.

**Why it happens:**
Happy-path coding; treating LLM output as always-valid; structured/JSON output modes that fail on long inputs and fall back to partial text; no pre-write validation gate.

**How to avoid:**
- **Validate before overwrite, always.** Gate every write on: cue count match, no empty/untranslated lines (heuristic: line still in source language, or unchanged from source), valid encoding, parseable format, timestamps monotonic. Fail → quarantine + log, never write.
- Prefer **plain numbered-line protocols over JSON** for long files — JSON mode is brittle at length (unescaped quotes, truncation breaks the whole parse). If using structured output, validate parse and have a fallback.
- **Loud failure, not silent:** surface failures in the dashboard/health endpoint; an unattended system needs observability or failures are invisible.

**Warning signs:**
Output files containing source-language lines; empty cues; files much shorter than source; parse errors swallowed in logs; no per-file success/failure record.

**Phase to address:** Translation engine + service phase. The validation gate is a v1 must-have, not hardening.

---

### Pitfall 8: Docker path-mapping mismatch with the *arr stack

**What goes wrong:**
The classic *arr "remote path mapping" failure. Bazarr/Sonarr/Radarr report a media path (e.g. `/tv/Show/...`) that, inside Trezarr's container, maps to a different or non-existent path. Trezarr either can't find the media, writes the sidecar to the wrong location, or writes nowhere. Subtitles never appear next to the media; integration looks broken.

**Why it happens:**
Each container has its own volume mounts; API responses return *the other app's* internal paths, not Trezarr's. This is the single most common *arr-stack support issue.

**How to avoid:**
- **Mirror the *arr volume conventions** — document and strongly recommend identical mount points across the stack (TRaSH-guide single-`/data` mount pattern), so paths match without translation.
- Provide a **path-mapping config** (find/replace remote→local) as the escape hatch when mounts differ, exactly as Sonarr/Radarr/Bazarr do.
- **Validate path resolution at startup/config time** — probe that an API-reported media path is actually readable inside the container, and surface a clear error if not (don't fail silently per-file later).

**Warning signs:**
"Path does not exist / not accessible" errors; media discovered via API but file ops fail; sidecars written but not visible to Plex/Jellyfin.

**Phase to address:** *arr integration phase. This is a known, well-documented domain trap — design the path layer for it from day one.

---

### Pitfall 9: Permissions (PUID/PGID/umask) — sidecar written but unreadable/unwritable

**What goes wrong:**
Trezarr writes `Show.S01E01.vi.srt` but with ownership/permissions that the media server (or the user) can't read, or it can't write into a directory owned by another stack user. Subtitles silently don't appear, or writes fail.

**Why it happens:**
Container UID/GID differs from the host/other containers; no umask coordination, so files aren't group-readable.

**How to avoid:**
- Support **PUID/PGID and UMASK** env vars (the LinuxServer.io convention the whole *arr ecosystem uses); document matching them across the stack.
- Write files with appropriate group-read/write so Plex/Jellyfin/Bazarr can read them.

**Warning signs:**
Sidecar files owned by root or wrong UID; media server can't see subtitles that exist on disk; permission-denied on write.

**Phase to address:** *arr integration / deployment phase.

---

### Pitfall 10: Race with Bazarr writing the same file + re-processing loops

**What goes wrong:**
Two ways this breaks: (a) Bazarr and Trezarr both write a `.vi.srt` for the same media and clobber each other or Trezarr overwrites a real downloaded Vietnamese sub with a machine one; (b) Trezarr's own file-watcher sees the sidecar it just wrote, treats it as new media activity, and re-translates — an infinite re-processing loop burning the user's LLM endpoint.

**Why it happens:**
No idempotency marker distinguishing "media that needs translation" from "media Trezarr already handled"; watcher not filtering out its own output; not respecting Bazarr's existing Vietnamese sub (PROJECT explicitly: only act when there's a source sub but *no good Vietnamese* one).

**How to avoid:**
- **Idempotency:** maintain a processed-state record (per media + source version hash). Before translating, check "do I already have a current `.vi` output for this exact source?" — skip if yes.
- **Exclude own output** from the watch trigger; never treat a `.vi.srt` Trezarr produced as an input event.
- **Respect existing Vietnamese subs** — only fill the gap, don't compete with Bazarr-downloaded human subs (matches the explicit "fill gaps, don't replace acquisition" decision).
- Atomic write (temp+rename) so a partial file never looks like a finished one.

**Warning signs:**
Same episode translated repeatedly; LLM endpoint hit in a tight loop; Trezarr overwriting a human-sourced Vietnamese sub; ping-pong file modifications between Bazarr and Trezarr.

**Phase to address:** Service/orchestration phase (watcher + idempotency). Mark for careful design — re-processing loops are a cost/abuse risk even though per-token cost is "out of scope."

---

### Pitfall 11: No resumability / crash leaves corrupt or partial state

**What goes wrong:**
A long file (or a series batch) is half-translated when the service crashes/restarts. On restart it either re-does completed work (wasting the endpoint) or writes a half-translated file, or leaves a corrupt Bible. Unattended services restart often (updates, OOM, host reboots).

**Why it happens:**
In-memory-only progress; non-atomic writes; no checkpoint of which cues/episodes are done.

**How to avoid:**
- **Checkpoint at batch boundaries**; on restart, resume from the last completed batch rather than from zero.
- **Atomic finalization:** only the fully-validated file replaces the target; partial work lives in a temp/work area.
- Idempotency keys scoped to the unit of work (per-file, per-episode) so replay after crash doesn't duplicate side effects.

**Warning signs:**
Re-translating whole files after a restart; half-written sidecars on disk; corrupt Bible after an unclean shutdown.

**Phase to address:** Service/orchestration phase.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Send whole ASS `Text` field (tags included) to the LLM | ASS "works" without a parser | Mangled typesetting, broken karaoke; fansub users reject output | Never — gate ASS support behind a real tag parser |
| Translate from English source for all content | Simplest source path | Relational info already destroyed → wrong pronouns on East-Asian content (core-value failure) | Only as fallback when no relational source exists |
| Bible as append-only JSON, no locks/provenance | Fast to build | Drift, stale-after-edit, clobbered human fixes, unbounded bloat | MVP single-episode only; never for multi-episode |
| Skip pre-write validation gate | Ship faster | Silent bad files = breaks blind-trust contract permanently | Never in unattended mode |
| JSON/structured output for translation | Easy parsing | Brittle on long files (truncation/escaping breaks whole parse) | Short files only; always validate + fallback |
| Single global queue, no per-series serialization | Simple | Concurrency races corrupt Bible / break cross-episode consistency | Never once parallel processing is enabled |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Sonarr/Radarr/Bazarr API paths | Trusting API-returned paths as local | Path mapping + startup readability probe; mirror *arr volume conventions |
| Filesystem / containers | Default container UID/GID | PUID/PGID/UMASK env vars matching the stack |
| Sidecar naming | `.hi` without language code, or `Show..srt` double-dot | Always `Show.S01E01.vi.srt`; HI/forced flags *after* the language code (ISO-639-1 `vi`) |
| Bazarr coexistence | Overwriting/competing with Bazarr's Vietnamese subs | Only fill the no-good-Vietnamese gap; never clobber a downloaded sub |
| File watcher | Re-triggering on own output | Exclude self-produced `.vi.*` files from watch events |
| Plex/Jellyfin pickup | Non-UTF-8 output | Always write UTF-8 (no BOM issues); never CP1258 |

## Performance / Cost Traps

(PROJECT marks per-token cost out of scope, but these are *correctness/abuse* failures, not budgeting features.)

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-processing loop | Same episode translated repeatedly; endpoint hammered | Idempotency record + exclude own output | Immediately, in unattended mode |
| Retry storm on bad input | One unparseable file retried unboundedly | Cap retries; quarantine after N; cascading batch-size fallback then stop | When a single file persistently fails |
| Bible context overflow | Bible silently truncated → consistency lost | Salience-based pruning; cap Bible size; measure tokens | Long-running series (10+ episodes, many characters) |
| Unbounded parallelism | OOM, endpoint rate-limit, corrupt Bible | Concurrency cap; per-series serialization | Large library initial scan |

## Security / Trust Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| LLM base URL/key in plaintext config or logs | Credential leak | Secret handling; never log keys |
| Trusting user-provided base URL blindly | SSRF / exfiltration of subtitle content to unexpected host | It's user's own endpoint by design, but validate/confirm; don't auto-forward to third parties |
| Writing into arbitrary host paths via path-map | Path traversal outside media roots | Constrain writes to configured media roots |
| No auth on dashboard/API | Local-network exposure of config (incl. endpoint key) | Auth on the web UI, matching *arr conventions |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Bible edits silently overwritten next episode | User loses trust in the override valve | Lock edited fields; show provenance/lock state in UI |
| Failures invisible in unattended mode | User believes it works; ships bad subs blindly | Dashboard health + per-file success/fail log + quarantine view |
| Name over-translation (translating proper nouns) | Character names rendered as common Vietnamese words | Bible keeps names in original Latin form (PROJECT decision); enforce in prompt + self-review |
| No way to see *why* a file was skipped | "It's not translating!" confusion | Surface skip reasons (already has VI sub / no source / path error) |

## "Looks Done But Isn't" Checklist

- [ ] **SRT translation:** Often missing the cue-count validation gate — verify a deliberately tricky file (overlapping cues, very long lines) round-trips with identical count and synced timestamps.
- [ ] **ASS support:** Often missing tag preservation — verify `{...}` blocks and `\N` are byte-identical in output and signs render in position.
- [ ] **Pronoun engine:** Often "works" on a clean test episode but drifts across episodes — verify the *same* character pair keeps the *same* pair from ep.1 to ep.N, including across a logged relationship change.
- [ ] **Bible editing:** Often missing lock propagation — verify a user edit survives the next 3 episodes unchanged.
- [ ] **Encoding:** Often missing UTF-8 enforcement — verify diacritics (đ, ă, ơ, ư + tone marks) render in Plex AND Jellyfin, not just in a text editor.
- [ ] **Path integration:** Often "works on my single-container test" — verify with mismatched volume mounts (the real *arr scenario).
- [ ] **Idempotency:** Often missing — verify the watcher does NOT re-translate the file it just wrote.
- [ ] **Crash recovery:** Often missing — kill the service mid-file and verify it resumes without a corrupt sidecar or Bible.
- [ ] **Untranslated-line detection:** Often missing — verify lines the model passed through in the source language are caught before write.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Bad file already written (silent failure) | MEDIUM | Re-translate from source; needs source retained + per-file provenance to detect which outputs are suspect |
| Bible drift / clobbered human edit | HIGH | Hard if no provenance/versioning; with Bible version history, roll back the field. **Prevent, don't recover.** |
| Re-processing loop | LOW | Add idempotency record + watcher exclusion; stop the loop |
| Path/permission misconfig | LOW | Config fix; startup probe surfaces it before any damage |
| Corrupt Bible from race/crash | HIGH | Atomic writes + per-series lock prevent it; recovery means rebuilding from episodes |
| Wrong-source-selected (poor/out-of-sync sub) | MEDIUM | Re-run with better source; needs source-quality/sync scoring to detect |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Line-count drift (1) | Core translation engine | Round-trip count + timestamp-sync test on tricky files |
| Wrong pronoun (2) | Series Bible + attribution + source-selection | Cross-episode pronoun-consistency harness; native-speaker spot check |
| Mis-attribution (3) | Attribution sub-component | Reciprocal-pronoun check within exchanges |
| Bible drift/stale (4) | Bible lifecycle/persistence | Edit-survives-N-episodes test; bloat/token cap test |
| Concurrency race (5) | Service orchestration + Bible persistence | Parallel same-series run produces consistent Bible |
| ASS tag mangling (6) | ASS format phase (flag for research) | Tag/`\N` byte-identity + render-position test |
| Silent bad-file write (7) | Translation engine + service | Validation gate rejects malformed output |
| Docker path mismatch (8) | *arr integration | Mismatched-mount integration test + startup probe |
| Permissions (9) | *arr integration / deployment | PUID/PGID/umask test; media server reads output |
| Bazarr race / loop (10) | Service orchestration | Idempotency + watcher-exclusion test |
| No resumability (11) | Service orchestration | Mid-file crash → clean resume test |
| Encoding corruption | Format/output phase | UTF-8 diacritic render test on Plex + Jellyfin |
| Source quality/sync | Source-selection phase | Sync/quality scoring before selection |

## Sources

- [How Subtitles Are Generated Using LLMs (And Why It's Harder Than It Looks)](https://apoorvamittal.substack.com/p/how-subtitles-are-generated-using) — line/timing alignment failure modes (MEDIUM)
- [LLM Translation Hallucination Index 2026](https://www.analyticsinsight.net/llm/llm-translation-hallucination-index-2026-which-models-add-drop-or-rewrite-meaning-most-ranked) — add/drop/rewrite rates, short+long-text risk (MEDIUM)
- [Cerlancism/chatgpt-subtitle-translator](https://github.com/Cerlancism/chatgpt-subtitle-translator) — cascading batch-size retry, repetition guard, timestamp-boundary validation (HIGH, implementation-verified)
- [rockbenben/subtitle-translator](https://github.com/rockbenben/subtitle-translator) — SRT/ASS/VTT batch translation patterns (HIGH)
- [ArjanCodes: Translating SRT with AI](https://arjancodes.com/blog/translating-srt-files-with-ai/) — strip-timecodes-locally, per-line mapping (MEDIUM)
- [Aegisub ASS Override Tags](https://aegisub.org/docs/latest/ass_tags/) and [Nikse ASSA override tags](https://www.nikse.dk/subtitleedit/formats/assa-override-tags) — tag grammar (HIGH)
- [doc2lang ASS translator](https://doc2lang.com/ass-translate) / [O.Translator ASS](https://otranslator.com/en/intro/ass) — which tags must be preserved, karaoke remap (MEDIUM)
- [Vietnamese pronouns — Wikipedia](https://en.wikipedia.org/wiki/Vietnamese_pronouns) and [Migaku pronoun guide](https://migaku.com/blog/language-fun/vietnamese-personal-pronouns-guide) — relational/register system, romantic convention (HIGH for linguistics)
- [Problems with automating translation of movie/TV subtitles (arXiv 1909.05362)](https://arxiv.org/pdf/1909.05362) — proper-noun KNP gap, over-translation (HIGH, peer literature)
- [Post-editing challenges in Chinese→English NMT subtitles (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S2590291124001463) — semantic/proper-noun errors (MEDIUM)
- [How to Use AI to Translate Anime Subtitles Preserving Honorifics](https://www.alibaba.com/product-insights/how-to-use-ai-to-translate-anime-subtitles-while-preserving-honorifics-and-tone.html) — English flattening honorifics (LOW, vendor)
- [TRaSH Guides: Remote Path Mappings](https://trash-guides.info/Radarr/Radarr-remote-path-mapping/) and [Servarr Docker Guide](https://wiki.servarr.com/docker-guide) — path-mapping, PUID/PGID/umask (HIGH, canonical *arr docs)
- [Bazarr issue #3195 (.hi without language code)](https://github.com/morpheus65535/bazarr/issues/3195), [#3252 (double-dot)](https://github.com/morpheus65535/bazarr/issues/3252), [#703 (missing lang code)](https://github.com/morpheus65535/bazarr/issues/703) — sidecar naming pitfalls (HIGH, real issues)
- [Plex local subtitles naming](https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/) and [UTF-8 Subtitles Converter](https://github.com/adriantc/UTF-8SubtitlesConverter.bundle) — UTF-8 requirement, lang-code naming (HIGH)
- [Idempotency Is Not Optional in LLM Pipelines](https://tianpan.co/blog/2026-04-20-idempotency-llm-pipelines), [AI Agent Workflow Checkpointing & Resumability](https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability) — idempotency keys, checkpointing, intent logging (MEDIUM)

---
*Pitfalls research for: automated unattended LLM Vietnamese subtitle translation (Bazarr/*arr companion)*
*Researched: 2026-05-31*
