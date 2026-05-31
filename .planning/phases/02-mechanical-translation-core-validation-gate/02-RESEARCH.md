# Phase 2: Mechanical Translation Core + Validation Gate — Research

**Researched:** 2026-05-31
**Domain:** LLM subtitle translation orchestration, pre-write validation, atomic sidecar write, idempotency ledger
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-12: Placeholder-protect inline tags.** Extract `<i>`, `<b>`, `<u>`, `<font…>`, `{\anX}` before sending; replace with unique non-translatable sentinels; reinsert by sentinel after translation. If sentinels don't round-trip (count/identity mismatch), the cue fails the gate.
- **D-13: Guarantee 1:1 cue mapping by construction.** Numbered-line protocol (lines in / lines out); reassemble by index. Cue-count match enforced at assembly; gate is backstop, not sole defense.
- **D-14: Batch by token budget at safe boundaries (ENG-02).** Never split a single cue. Prefer boundaries at time-gap >= scene/pause threshold; fall back to max-cue-count window. Token estimation: conservative and tokenizer-agnostic.
- **D-15: Surrounding-line context window (ENG-03).** K read-only source lines before/after per batch (default K≈2–5); model sees them but does not re-emit them. Context may cross batch boundaries; cues do not.
- **D-16: Gate every write on ALL of:** (1) cue-count equals source; (2) no empty/whitespace-only translated lines; (3) no untranslated lines (D-17); (4) timecodes/indices byte-identical to source; (5) monotonic, non-overlapping timestamps; (6) sentinel integrity (D-12); (7) result re-parses as valid SRT and encodes as valid UTF-8.
- **D-17: Untranslated-line detection = cheap, layered, low-false-reject.** Per-line allowlist for legitimately-unchanged lines (all-punctuation/digits/whitespace, lone proper nouns/numbers, musical/symbolic). Per-file Vietnamese-diacritic ratio threshold. No heavy per-line language-detection dependency.
- **D-18: Failure handling = bounded per-batch retry, then whole-file reject.** On gate-relevant batch failure, re-prompt up to N times (default 2). On continued failure or document-level gate failure: quarantine (write failure artifact to `/config/quarantine/`), never write a partial sidecar.
- **D-19: Atomic UTF-8 sidecar (FMT-05).** Write to temp file in destination directory, then `os.replace()` to `<video-basename>.vi.srt`. Always UTF-8. Crash mid-write never leaves corrupt or half-visible file.
- **D-20: Idempotency via `/config` processed-files ledger (ENG-07).** Schema-compatible with Phase-4 `processed_file` table. Behavior: unchanged-source-with-valid-output → skip; changed source → regenerate; foreign `.vi.srt` (not in ledger as ours) → skip+log, do NOT clobber; previously quarantined → retry.

### Claude's Discretion
Exact module/package layout (e.g. `trezarr/translate/…`, `trezarr/validate/…`, `trezarr/output/…`), the token-estimation mechanism and its safety margin, the exact batch-packing algorithm and scene-gap threshold, neighbor-line count K, retry count N, the untranslated-ratio threshold, the sentinel token format, the ledger storage format (JSON vs tiny SQLite seam), and prompt wording — provided the decisions above and the four phase success criteria hold.

### Deferred Ideas (OUT OF SCOPE)
- Series Bible / pronoun + relationship consistency (Phases 4–5)
- Two-pass (analyze → translate) and LLM self-review (Phases 4 and 6)
- File-watcher / re-processing-loop prevention (Phase 3/7; Phase 2 only establishes the provenance ledger)
- Configurable "take over a foreign `.vi.srt`" override (Web UI Phase 7)
- ASS/SSA + VTT (Phase 9; SRT-only here)
- PUID/PGID ownership and Docker packaging (Phase 7)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-02 | Trezarr batches/chunks long subtitle files within token limits without splitting a sentence or scene across batch boundaries | D-14: char/token heuristic with 30% overhead reserve + 40% output-expansion reserve; scene-gap boundary detection; max-cue fallback |
| ENG-03 | Each batch is translated with a surrounding-line context window (read-only lines before/after) for conversational coherence | D-15: K=3 neighbor lines marked `[context]` in prompt; model instructed not to emit them; context crosses batch boundaries; cues do not |
| ENG-06 | A hard pre-write validation gate verifies cue-count match, no untranslated lines, monotonic timestamps, and format integrity — failing files are quarantined, never written | D-16/D-17/D-18: 7-check gate; Vietnamese diacritic ratio 0.70 threshold; quarantine JSON artifact; two-tier detection |
| ENG-07 | A failed or rejected translation can be retried/re-run idempotently, reusing existing Series Bible state | D-20: JSON ledger keyed by `source_path`; source content hash for skip/regenerate logic; quarantine-retry on re-run |
| FMT-05 | Output subtitles use correct sidecar naming, are written atomically (temp+rename), and are valid UTF-8 | D-19: `os.replace()` same-filesystem atomic rename; `<video-basename>.vi.srt` naming; UTF-8 encode verified |
</phase_requirements>

---

## Summary

Phase 2 wires the Phase 1 codec (`read_srt`/`write_srt`) and LLM client (`LLMClient.call()`) into the first end-to-end translation path for a single SRT file. The phase has four concrete subproblems: (1) a token-conservative batch-packing algorithm that never splits a cue and prefers scene-gap boundaries; (2) a numbered-line transport protocol that survives the endpoint's structured-output tier (D-04 DeepSeek scenario: may land on text mode); (3) a seven-check validation gate that biases toward false rejects over silent bad writes; and (4) an idempotency ledger that is schema-compatible with the Phase-4 SQLAlchemy `processed_file` table.

All seven gate checks operate without calling the LLM — they are pure Python assertions on the assembled `SubDoc`. The gate's enforcement posture is explicit: a quarantined file is recoverable; a silently-wrong sidecar that Plex trusts forever is not. The gate deliberately does not check Vietnamese *quality* (pronoun choices, consistency) — that is Phases 4–6. It checks structural integrity only.

The idempotency ledger starts as a JSON file in `/config/` rather than a SQLite table, which avoids introducing the `aiosqlite`/`SQLAlchemy` dependency in Phase 2 while keeping schema fields (`source_path`, `output_path`, `status`, `content_hash`, `series_id`, `episode_key`) that Phase 4 will migrate into the `processed_file` table verbatim.

**Primary recommendation:** Implement a `trezarr/translate/` package with three sub-modules — `batching.py` (batch-pack + context-window), `engine.py` (numbered-line orchestration over `LLMClient`), and `validate.py` (the seven-check gate) — plus a `trezarr/output/` package with `write.py` (atomic sidecar) and `ledger.py` (JSON idempotency ledger). Entry point: `translate_file(path, settings) -> TranslationResult` (async, clean callable for Phase 3 to drive).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Batch packing + scene-gap detection | Local Python (no LLM) | — | Token counting and timecode parsing are deterministic; no model needed |
| Tag extraction + sentinel substitution | Local Python (no LLM) | — | Purely mechanical regex operation before and after LLM call |
| Numbered-line prompt construction | Local Python | — | Builds the `[N] text` lines and context markers |
| Translation (LLM call) | `LLMClient.call()` | — | All LLM I/O goes through the existing Phase-1 client; do not bypass |
| Numbered-line response parsing | Local Python (no LLM) | — | Regex parse of `[N] text` lines back to a list |
| Sentinel reinsertion | Local Python (no LLM) | — | Map sentinel tokens back to original tag strings |
| Validation gate (all 7 checks) | Local Python (no LLM) | — | Pure Python assertions on the assembled SubDoc |
| Atomic sidecar write | Local Python / filesystem | — | `tempfile` + `os.replace()` — no LLM, no external service |
| Idempotency ledger read/write | Local Python / `/config` filesystem | Phase-4 SQLite migration | JSON file in Phase 2; migrates to SQLAlchemy table in Phase 4 |
| Quarantine artifact write | Local Python / `/config` filesystem | — | JSON failure artifact; never next to media |

---

## Standard Stack

### Core (no new packages required for Phase 2 translation logic)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openai | 2.38.x | LLM client (via `LLMClient`) | Already installed; Phase 2 never calls SDK directly |
| pydantic | 2.13.x | Response model for batch output | Already installed; structures batch parse results |

### New Packages Phase 2 Must Add to pyproject.toml
| Library | Version | Purpose | Why Now |
|---------|---------|---------|---------|
| tenacity | 9.1.x | Pipeline-level batch retry (D-18) | Prescribed stack (CLAUDE.md); cleaner than a manual loop for the N-retry pattern; not yet in pyproject.toml |

**Note:** `aiosqlite`, `sqlalchemy`, and `apscheduler` are prescribed-stack packages but are NOT needed in Phase 2. The idempotency ledger uses JSON (stdlib). Those packages join in Phase 3/4.

**Version verified:** `tenacity 9.1.4` — confirmed live on PyPI 2026-05-31. [VERIFIED: npm registry (PyPI)]

### Standard Library (no install needed)
| Module | Purpose |
|--------|---------|
| `os` | `os.replace()` for atomic rename |
| `tempfile` | `NamedTemporaryFile` for safe intermediate write |
| `hashlib` | SHA-256 content hash for idempotency key |
| `json` | JSON ledger and quarantine artifact format |
| `re` | Sentinel extraction, numbered-line parsing, VI diacritic check |
| `unicodedata` | Unicode character categorization (diacritic detection) |
| `pathlib` | Path manipulation for sidecar naming |
| `asyncio` | `asyncio.gather()` for parallel batch dispatch under the existing Semaphore |

**Installation (tenacity only):**
```bash
uv add tenacity
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JSON ledger | SQLite (aiosqlite) | SQLite is the Phase-4 target; JSON avoids a new dep in Phase 2 while keeping schema-compatible fields |
| char/token heuristic | tiktoken | tiktoken is OpenAI-specific and adds a dep; heuristic is conservative and endpoint-agnostic |
| `os.replace()` | `shutil.move()` | `os.replace()` is POSIX-atomic on same filesystem; `shutil.move()` can fall back to copy+delete |
| `tenacity` retry | manual `for attempt in range(N)` loop | tenacity is cleaner and already in the prescribed stack; adds no new concepts |

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| tenacity | PyPI | 9 yrs | >10M/wk | github.com/jd/tenacity | OK | Approved |
| openai | PyPI | 5 yrs | >50M/wk | github.com/openai/openai-python | OK | Approved |
| pysubs2 | PyPI | 8 yrs | >2M/wk | github.com/tkarabela/pysubs2 | OK | Approved |
| pydantic | PyPI | 10 yrs | >200M/wk | github.com/pydantic/pydantic | OK | Approved |
| pydantic-settings | PyPI | 4 yrs | >50M/wk | github.com/pydantic/pydantic-settings | OK | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck ran successfully (2026-05-31). All packages rated [OK].*

---

## Architecture Patterns

### System Architecture Diagram

```
translate_file(path, settings)
         │
         ▼
[LEDGER CHECK]  ──── already done (our output, same hash) ──▶  skip (idempotent no-op)
         │           already done (foreign vi.srt) ──────────▶  skip + log (D-20)
         │ not done / quarantine retry
         ▼
[READ SOURCE]  read_srt(path) → SubDoc
         │
         ▼
[BATCH PACK]  batch_subdoc(subdoc, settings) → list[Batch]
         │    - estimate tokens (char/token heuristic, conservative)
         │    - find scene-gap boundaries (gap >= SCENE_GAP_MS)
         │    - prefer breaks at gaps; fall back to MAX_CUES_PER_BATCH
         │    - attach K neighbor source lines as context (D-15)
         │
         ▼
[TRANSLATE BATCHES]  asyncio.gather(*[translate_batch(b) for b in batches])
         │           (bounded by LLMClient semaphore, already in Phase 1)
         │    for each batch:
         │      ├─ extract sentinels from cue texts (D-12)
         │      ├─ build numbered-line prompt (D-13)
         │      ├─ LLMClient.call(messages) → raw response
         │      ├─ parse [N] lines → translated texts
         │      ├─ reinsert sentinels
         │      └─ batch-level gate: count + sentinel + empty ──(fail)──▶ retry N times
         │                                                    ──(still fail)──▶ quarantine whole file
         ▼
[ASSEMBLE]  merge translated texts back onto source SubLines (text only; timing/index untouched)
         │
         ▼
[VALIDATION GATE]  validate_subdoc(translated_doc, source_doc, settings)
         │    1. cue count equals source
         │    2. no empty/whitespace-only translated lines
         │    3. no untranslated lines (per-line allowlist + VI diacritic ratio)
         │    4. timecodes/indices byte-identical to source
         │    5. monotonic, non-overlapping timestamps
         │    6. sentinel integrity already checked per batch (backstop here too)
         │    7. re-parses as valid SRT; all texts encode as UTF-8
         │    ANY FAILURE ──────────────────────────────────────▶ quarantine + return failure
         ▼
[ATOMIC WRITE]  write_vi_sidecar(translated_doc, dest_path)
         │    - write to NamedTemporaryFile in dest_dir
         │    - os.replace(tmp, dest)  ← POSIX atomic, same filesystem
         ▼
[LEDGER UPDATE]  ledger.record(source_path, output_path, content_hash, status="done")
         │
         ▼
TranslationResult(status="done"|"skipped"|"quarantined", output_path, quarantine_path)
```

### Recommended Project Structure

```
trezarr/
├── translate/              # NEW — Phase 2 translation orchestration
│   ├── __init__.py
│   ├── batching.py         # batch_subdoc(): token-budget batch packer + context window
│   ├── engine.py           # translate_file(), translate_batch() — numbered-line LLM calls
│   ├── sentinel.py         # extract_sentinels(), reinsert_sentinels() — tag protection
│   └── validate.py         # validate_subdoc() — 7-check pre-write gate
├── output/                 # NEW — Phase 2 sidecar write + idempotency
│   ├── __init__.py
│   ├── write.py            # write_vi_sidecar() — atomic UTF-8 write + sidecar naming
│   └── ledger.py           # Ledger class — JSON processed-files ledger, Phase-4-compatible
├── subtitles/              # Phase 1 — unchanged
│   ├── model.py
│   ├── srt.py
│   └── encoding.py
├── llm/                    # Phase 1 — unchanged
│   └── client.py
└── config.py               # Phase 1 — extend with Phase-2 settings knobs
```

**Phase-1 files are not modified except `config.py`** (add new settings fields).

---

## Research Questions — Resolved

### Q1: Token-estimation mechanism (D-14)

**Recommendation:** Use a char/token heuristic of **3.5 chars per token** as the denominator, representing the input text only. Reserve **30% of the context window for system prompt + neighbor context overhead**, and **40% expansion headroom for Vietnamese output tokens** (Vietnamese dialogue is word-count-larger than English). The effective input-cue budget per batch is:

```
input_budget_chars = (context_window * 0.70) / (1 + 0.40) * 3.5
```

For the default 32k window: `(32768 × 0.70) / 1.40 × 3.5 ≈ 57,344 chars` of source cue text per batch. At ~100 chars/cue average, this is ~573 cues — typically one or two SRT files. In practice the max-cue cap (see Q2) will bind first.

**Rationale:** The 3.5 chars/token ratio is conservative for English source text (OpenAI tokenizer averages ~4 chars/token for prose; 3.5 is the floor to account for heavy dialogue punctuation). Vietnamese output expansion of ~1.4x is based on word-count comparison of English→Vietnamese translation pairs. The 30% overhead reserve covers the system prompt (~500 tokens), neighbor-line context (K×2 lines × avg cue), and any model-specific overhead. [ASSUMED] — the 1.4x expansion factor is based on general EN→VI translation observation, not measured on subtitle corpora specifically.

**Config knobs to expose (extend `TrezarrSettings`):**
```python
translate_chars_per_token: float = 3.5
translate_overhead_fraction: float = 0.30
translate_output_expansion: float = 1.40
translate_max_cues_per_batch: int = 50   # hard cap regardless of token budget
translate_scene_gap_ms: int = 2000       # 2s gap = scene/pause boundary
translate_context_lines_k: int = 3       # neighbor lines before + after
translate_batch_retry_attempts: int = 2  # D-18: retries before whole-file reject
translate_vi_diacritic_ratio: float = 0.70  # D-17: per-file VI sanity threshold
```

[VERIFIED: trezarr/config.py] — these extend `TrezarrSettings` using the established `pydantic-settings` pattern (D-11).

---

### Q2: Batch-packing algorithm (D-14)

**Recommendation:** A greedy-with-lookback algorithm:

1. Compute `token_budget_chars` using the Q1 formula.
2. Walk cues in order. Accumulate into the current batch as long as:
   - `current_chars + len(cue.text) <= token_budget_chars`, AND
   - `batch_cue_count < translate_max_cues_per_batch`
3. Before adding each cue, check if the gap from the previous cue's `end_tc` to this cue's `start_tc` is `>= translate_scene_gap_ms`. If yes, emit the current batch and start a new one (scene-gap break takes priority over filling the budget).
4. Never split a single cue across batches. If a single cue's text exceeds the budget, treat it as a one-cue batch (and log a warning — this means the configured context window is too small for this cue).

**Scene-gap default: 2000ms (2 seconds).** This covers both explicit scene breaks and natural conversational pauses, matching common subtitle conventions. [ASSUMED] — industry subtitling guidelines typically use 2-3s as scene gap threshold; 2s is a reasonable lower bound.

**Max-cue cap default: 50 cues.** Empirically, 50 cues of English dialogue at ~100 chars/cue = 5000 chars ≈ 1,400 input tokens, well within any modern LLM context while keeping prompts focused. [ASSUMED] — based on general subtitle translation practice; should be tunable.

[VERIFIED: trezarr/subtitles/srt.py] — `SubLine.start_tc` and `end_tc` are verbatim strings; must convert to milliseconds for gap comparison using the same `_TC_RE` pattern already in srt.py (extract into a shared utility or inline in batching.py).

---

### Q3: Surrounding-line context window (D-15)

**Recommendation:** Present K=3 neighbor lines before and after the batch in the prompt, clearly marked as `[CONTEXT]` lines that the model MUST NOT include in its numbered output. Use a distinct section header:

```
[CONTEXT - DO NOT TRANSLATE OR INCLUDE IN YOUR OUTPUT]
[context] She walked into the room.
[context] John: What are you doing here?
[context] -------
[LINES TO TRANSLATE - output ONLY these as [N] lines]
[1] I came to talk.
[2] About what?
[CONTEXT - DO NOT TRANSLATE OR INCLUDE IN YOUR OUTPUT]
[context] -------
[context] Please, sit down.
[context] I'll explain everything.
```

**Why this works:** Models reliably treat section headers and explicit `DO NOT` instructions as separators when the labeled tokens (`[context]`) differ visually from the numbered output tokens (`[N]`). The separator `[context] -------` marks the batch/context boundary. [ASSUMED] — this prompt pattern is derived from general LLM instruction-following best practice, not verified against this specific endpoint (DeepSeek-family).

**Critical:** The validation gate checks that the response contains EXACTLY the numbered lines for the batch, not more. If a model includes `[context]` lines in its output, the numbered-line parser will either: (a) ignore them (they don't match `[N]` format), or (b) error on count mismatch — both are safe outcomes.

---

### Q4: Inline-tag sentinel protection (D-12)

**Recommendation:** Use double-angle-bracket sentinels: `<<T0>>`, `<<T1>>`, `<<T2>>`, etc.

**Rationale for this format:**
- Double angle brackets `<<…>>` are rare in natural dialogue text and never appear in standard subtitle content
- The format looks like a template placeholder / technical token to an LLM — models strongly tend to pass these through untranslated
- Unlike single `<…>` (which models may "fix" as HTML), double brackets have no HTML/XML semantic meaning
- Unlike `{…}` (which may interfere with ASS override tags or Python format strings), `<<…>>` is neutral
- Unlike `[…]` (which is used for the numbered-line protocol), `<<…>>` is visually distinct

**Extraction pattern:**
```python
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\})')
```
This matches SRT inline tags (`<i>`, `<b>`, `<u>`, `<font color="...">`) and occasional inline ASS override tags (`{\anX}`, `{\an8}`, etc.).

**Round-trip integrity check:** After reinsertion, verify:
1. `len(sentinel_map_for_cue)` equals the number of sentinel tokens found in translated text
2. Each sentinel key appears exactly once in the translated text

If either check fails → cue-level sentinel failure → batch-level gate triggers retry (D-18). [VERIFIED: Python 3.9 re module] — sentinel extraction regex tested and confirmed working.

---

### Q5: The validation gate (D-16/D-17/D-18)

**7 checks, in order (fail-fast — stop at first failure):**

#### Check 1: Cue count equals source
```python
assert len(translated_doc.lines) == len(source_doc.lines)
```
[VERIFIED: trezarr/subtitles/model.py] — `SubDoc.lines` is the list; lengths must be equal.

#### Check 2: No empty/whitespace-only translated lines
```python
for i, sl in enumerate(translated_doc.lines):
    if not sl.text.strip():
        raise GateError(f"Empty translated cue at index {i}")
```

#### Check 3: No untranslated lines (D-17) — layered, two-tier

**Tier A — per-line allowlist (check BEFORE flagging as untranslated):**
A line is "legitimately unchanged" if it matches ANY of:
- Empty or whitespace-only (caught by check 2, but defensive)
- All punctuation/digits/whitespace: `r'^[\W\d\s]+$'`
- Music/symbolic lines: `r'^[♪♫\.…\-_\s]+$'`
- Time references: `r'^\d{1,2}:\d{2}$'`
- Short universal expressions (case-insensitive): `OK`, `Hmm`, `Ah`, `Oh`, `Uh`, `Um`, `Yeah`, `No`, `Yes`, `Ha`, `Mm`, `Shh`

**Per-line untranslated flag:** A translated cue is flagged untranslated if its text is byte-identical to the source cue text AND the source cue is NOT on the allowlist. This is a per-line signal, not a hard-stop on its own.

**Tier B — per-file Vietnamese diacritic ratio:**
Compute the ratio of translatable lines (not on the allowlist) that contain at least one Vietnamese diacritic character (U+1E00–U+1EFF range — the Latin Extended Additional block that Vietnamese uses heavily):
```python
VN_EXTENDED_RE = re.compile(r'[Ḁ-ỿ]')  # U+1E00-U+1EFF
```
If this ratio falls below `translate_vi_diacritic_ratio` (default 0.70), fail the gate.

**Why 0.70:** A well-translated file should have >80% of substantive lines containing Vietnamese diacritics (tonal markers, precomposed chars). 0.70 is a conservative floor that tolerates files with many proper nouns, mixed-language lines, or short-dialogue episodes. [ASSUMED] — not empirically calibrated against real subtitle corpora; configurable so the user can tune.

**Note on false-positive risk:** French also uses some U+00C0–U+00FF accented chars, but Vietnamese heavily uses the U+1E00–U+1EFF block (e.g., `ổ`, `ợ`, `ẫ`) which French does not. The `[Ḁ-ỿ]` range (U+1E00+) is sufficient to distinguish Vietnamese from French/Spanish/German. [VERIFIED: Python unicodedata + regex testing] — confirmed in code.

#### Check 4: Timecodes/indices byte-identical to source
```python
for src, trn in zip(source_doc.lines, translated_doc.lines):
    assert src.index == trn.index
    assert src.start_tc == trn.start_tc
    assert src.end_tc == trn.end_tc
```
[VERIFIED: trezarr/subtitles/model.py] — `SubLine.index`, `start_tc`, `end_tc` are verbatim strings; the translation pipeline must copy them from source and never modify them.

#### Check 5: Monotonic, non-overlapping timestamps
Parse each timecode to milliseconds:
```python
def tc_to_ms(tc: str) -> int:
    m = _TC_RE.match(tc)
    h, mi, s, ms_str = m.groups()
    ms = int(ms_str.ljust(3, '0')[:3])
    return int(h)*3600000 + int(mi)*60000 + int(s)*1000 + ms
```
Then walk translated lines in order: `start_ms < end_ms` for each cue, and `start_ms[i] >= end_ms[i-1]` (non-overlapping). [VERIFIED: local Python testing] — confirmed working.

**Note:** Check 5 operates on the translated doc's timecodes. Because check 4 asserts byte-identity with source, a real-world pass of check 4 guarantees check 5 will also pass (source subtitles were valid SRT). Check 5 is a defensive backstop for the case where assembly somehow corrupts timing.

#### Check 6: Sentinel integrity (backstop)
Already checked per-batch during assembly, but re-verify at document level: if any translated `SubLine.text` contains a `<<T\d+>>` pattern, sentinel reinsertion failed for that cue.

#### Check 7: Re-parses as valid SRT and encodes as valid UTF-8
```python
# Write to a BytesIO equivalent and re-read
import io
tmp_buf = io.BytesIO()
# encode all texts as UTF-8
for sl in translated_doc.lines:
    sl.text.encode('utf-8')  # raises UnicodeEncodeError if lone surrogates, etc.
```
Full re-parse via `write_srt` to a temp path + `read_srt` back is also possible but expensive; encoding check alone is sufficient for the UTF-8 constraint. [VERIFIED: Python UnicodeEncodeError for lone surrogates] — confirmed in testing.

**Gate bias:** False reject (quarantine a translatable file) is always preferred over silent miss (write a structurally wrong file). A quarantined file is recoverable on re-run. A written bad file corrupts the user's media library.

---

### Q6: Atomic UTF-8 sidecar write (D-19)

**Pattern:**
```python
import os, tempfile
from pathlib import Path

def write_vi_sidecar(doc: SubDoc, media_path: str | Path) -> Path:
    media_path = Path(media_path)
    dest = media_path.with_suffix('').with_suffix('.vi.srt')
    # Temp file MUST be in the same directory as dest (same filesystem = atomic os.replace)
    with tempfile.NamedTemporaryFile(
        mode='wb',
        suffix='.tmp',
        dir=dest.parent,
        delete=False,
    ) as f:
        tmp_path = Path(f.name)
        content = serialize_subdoc_utf8(doc)  # always UTF-8
        f.write(content)
    os.replace(tmp_path, dest)  # POSIX-atomic rename, never leaves half-visible dest
    return dest
```

**Edge cases:**
- `dest.parent` must be writable — handle `PermissionError` at call site and quarantine
- `os.replace()` on Windows is not guaranteed atomic before Python 3.3, but Python 3.12+ (our floor) provides POSIX-level `MoveFileEx(MOVEFILE_REPLACE_EXISTING)` which is atomic on NTFS. [ASSUMED] — this project targets Linux Docker; `os.replace()` is POSIX-atomic on Linux. Windows not in scope.
- If `tmp_path` write completes but `os.replace()` fails (e.g. cross-device), the `.tmp` file is left behind. Clean up in a `try/finally` block around the whole write operation.

**Sidecar naming:**
- Input: `/media/tv/Show/Season 1/Show.S01E01.en.srt`
- Output: `/media/tv/Show/Season 1/Show.S01E01.vi.srt`
- Rule: strip all existing suffixes after the last `.` in the stem that look like language codes or format extensions (`.en`, `.en.srt`, `.srt`), then append `.vi.srt`.
- Implementation: `Path(media_path).stem` may have `.en` embedded in the filename; the safest approach is to strip the full extension chain down to the video basename and append `.vi.srt`. The video path is available when Phase 3 drives this; for Phase 2 standalone use, accept the source SRT path and replace the last two dot-segments with `.vi.srt`.

[VERIFIED: Python os.replace on macOS/Linux] — confirmed atomic, same-filesystem, tested.

---

### Q7: Idempotency ledger (D-20)

**Format: JSON file at `/config/processed_files.json`**

Schema for each record (Phase-4-compatible with `processed_file` table):
```json
{
  "source_path": "/media/tv/Show/S01/Show.S01E01.en.srt",
  "output_path": "/media/tv/Show/S01/Show.S01E01.vi.srt",
  "status": "done",
  "content_hash": "ac032970dca04837",
  "series_id": null,
  "source_lang": "en",
  "episode_key": null,
  "translated_at": "2026-05-31T10:00:00Z",
  "quarantine_path": null
}
```

**`status` values:** `done` | `quarantined` | `in_progress` (in_progress is cleared on restart — allows resumption)

**Content hash:** `hashlib.sha256(source_bytes).hexdigest()[:16]` — 16 hex chars (64 bits) is sufficient for file identity. Hash the raw source bytes (before decode), not the decoded text, so encoding-normalized files don't collide. [VERIFIED: Python hashlib.sha256 testing]

**Ledger stored as:** `dict[source_path, record]` in memory; written atomically on each update using `os.replace()` (same pattern as sidecar write).

**Behavior table:**

| Condition | Action |
|-----------|--------|
| source_path not in ledger | Proceed with translation |
| status == "done", output_path exists, current_hash == stored_hash | Skip (idempotent no-op) |
| status == "done", output_path exists, current_hash != stored_hash | Regenerate (source upgraded) |
| status == "done", output_path does NOT exist | Regenerate (output was deleted externally) |
| status == "quarantined" | Retry (re-run the translation — it may succeed now) |
| status == "in_progress" | Treat as not done (previous run crashed mid-flight) |
| output_path exists but source_path NOT in ledger | Foreign `.vi.srt` — skip + log "not ours, skipping" (Pitfall 10, D-20) |

**Phase-4 migration path:** Phase 4 introduces `SQLAlchemy` + `aiosqlite`. The `Ledger` class in Phase 2 exposes an identical interface (`async def check(path) → LedgerEntry | None`, `async def record(...)`) so Phase 4 can swap the JSON backend for a SQLAlchemy `async_sessionmaker` without changing any call sites. The JSON field names match the `processed_file` SQLAlchemy column names.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file rename | Custom temp+copy+delete | `os.replace()` (stdlib) | POSIX guarantee; cross-platform in Python 3.12+; copy+delete is NOT atomic |
| LLM retry with backoff | `asyncio.sleep()` loops | `tenacity` at pipeline level | Correct jitter/backoff; already prescribed stack; avoids double-retry with SDK |
| SHA-256 hash | Custom rolling hash | `hashlib.sha256` (stdlib) | Collision-resistance, correct; no dep needed |
| Unicode normalization | Manual char tables | `unicodedata` (stdlib) + regex range `[Ḁ-ỿ]` | Python stdlib covers all Unicode; range `U+1E00–U+1EFF` is exactly the Latin Extended Additional block |
| Structured JSON ledger | Raw file append | `json.load` / `json.dumps` + atomic write | The ledger is read fully on startup and written atomically; simple dict is sufficient |
| Timecode parsing | Regex from scratch | Reuse `_TC_RE` from `trezarr/subtitles/srt.py` (or extract to a shared util) | Regex is already tested and handles comma/period separators |

**Key insight:** Phase 2 has zero novel algorithmic problems. Every sub-problem has a stdlib or prescribed-stack solution. The only intellectual work is the gate's threshold calibration and the prompt design for the numbered-line protocol — not the infrastructure.

---

## Common Pitfalls

### Pitfall 1: Batch dispatch without the existing Semaphore (double-cap or no-cap)
**What goes wrong:** Phase 2 fans out `asyncio.gather(*[translate_batch(b) for b in batches])`. If the developer wraps `LLMClient.call()` inside a second `asyncio.Semaphore`, LLM calls are double-throttled. If they bypass `LLMClient.call()` and call the SDK directly, the cap is lost entirely.
**Why it happens:** `translate_batch()` looks like it needs its own concurrency control.
**How to avoid:** Always call `LLMClient.call()` and never touch `self._semaphore` outside of it. The existing semaphore in Phase 1 is the sole concurrency gate.
**Warning signs:** More than `llm_max_concurrency` concurrent requests seen at the endpoint, or throughput is half of expected.
[VERIFIED: trezarr/llm/client.py] — `async with self._semaphore` is inside `call()`, not outside.

### Pitfall 2: Sentinel format that the model translates or reformats
**What goes wrong:** The model "fixes" `<<T0>>` to `<T0>` (removes one angle bracket), or translates `<<Kiểu chữ nghiêng 0>>` (if the sentinel isn't opaque enough), or moves sentinels to the wrong position in the translated sentence.
**Why it happens:** Vietnamese sentence structure differs from English; inline tags mid-word may move. The model doesn't know `<<T0>>` is a protected token unless instructed.
**How to avoid:** Explicitly instruct the model: "Tokens in `<<T…>>` format are formatting placeholders. Keep them exactly as-is in your output, in the same relative position, never translate or modify them." Also run the sentinel-integrity check (check 6 of the gate) per batch.
**Warning signs:** `<<T0>>` missing from translated cue, or count of `<<T\d+>>` in output differs from input.

### Pitfall 3: Temp file on a different filesystem than the destination
**What goes wrong:** `os.replace()` raises `OSError: [Errno 18] Invalid cross-device link` if the temp file and the destination are on different filesystem mount points.
**Why it happens:** Using `tempfile.NamedTemporaryFile()` without `dir=` argument creates the temp file in the system temp dir (`/tmp`), which is commonly a separate tmpfs mount from `/media`.
**How to avoid:** Always pass `dir=dest.parent` to `NamedTemporaryFile`. This ensures temp + dest are on the same filesystem.
[VERIFIED: Python os.replace testing] — `os.replace` cross-device behavior confirmed.

### Pitfall 4: Ledger not written atomically — JSON partial writes
**What goes wrong:** The ledger JSON write crashes mid-write (process killed, OOM). Next startup reads a corrupt/partial JSON file and either raises `json.JSONDecodeError` or silently loses entries.
**Why it happens:** `json.dump(ledger, open(path, 'w'))` is not atomic.
**How to avoid:** Write ledger with the same `NamedTemporaryFile` + `os.replace()` pattern as the sidecar. Wrap the ledger read in a `try/except json.JSONDecodeError` with a fallback to an empty ledger + a loud warning.
**Warning signs:** Startup failures with JSONDecodeError on the ledger file.

### Pitfall 5: Adding tenacity per-batch AND relying on LLMClient's SDK retries
**What goes wrong:** `tenacity` retries the whole batch (including the `LLMClient.call()` call). The SDK also retries internally on 429/5xx. If the endpoint is slow, the user gets `max_retries × tenacity_attempts` requests.
**Why it happens:** Misunderstanding the retry responsibility split.
**How to avoid:** `tenacity` retry at the batch level should retry only on `BatchValidationError` (count mismatch, empty line, sentinel failure) — NOT on `openai.APIError` / `openai.RateLimitError`. The SDK handles transport failures; tenacity handles LLM output quality failures. Use `retry=retry_if_exception_type(BatchValidationError)` in the tenacity decorator.
[VERIFIED: CLAUDE.md] — "Do NOT wrap individual `create`/`parse` calls in tenacity (double-retry storm). Use tenacity only at the pipeline-step level."

### Pitfall 6: The vi-diacritic ratio rejecting files with many proper nouns or English-mixed dialogue
**What goes wrong:** An episode has many characters with English/Latin names that appear frequently and aren't translated (correct behavior). The per-file Vietnamese diacritic ratio falls below 0.70, and the gate quarantines a correctly-translated file.
**Why it happens:** Proper nouns like "Doctor Strange", "Captain America" appear in the translated text unchanged. This is correct, but they lower the VI ratio.
**How to avoid:** (a) The per-line allowlist helps — lines that are ALL proper nouns (all non-translatable text) are exempt from the ratio denominator. (b) The 0.70 threshold is conservative precisely to absorb proper-noun-heavy content. (c) Expose `translate_vi_diacritic_ratio` in `TrezarrSettings` so the user can lower it for heavily-proper-noun content.
**Warning signs:** Files quarantined with reason "VI diacritic ratio 0.65 < threshold 0.70" when the translation visually looks correct.

### Pitfall 7: Foreign `.vi.srt` check using file presence instead of ledger
**What goes wrong:** Code checks `if dest.exists(): skip`. A Bazarr-downloaded human Vietnamese sub exists at `Show.S01E01.vi.srt`. Trezarr sees the file, skips it — which is correct. But after Bazarr updates the file, the content_hash doesn't match the ledger (because we have no ledger entry), and Trezarr either wrongly regenerates or wrongly skips.
**Why it happens:** File-existence check without consulting the ledger misses the "is this ours?" question.
**How to avoid:** The ledger is the authority. File exists but not in ledger → foreign file → skip + log. File exists AND in ledger with matching hash → our output → skip. File exists AND in ledger but hash mismatch → source changed → regenerate.
[VERIFIED: D-20, PITFALLS.md Pitfall 10] — explicit Bazarr-collision protection requirement.

### Pitfall 8: Mutating SubLine.text on source doc lines during assembly
**What goes wrong:** `translated_doc` shares `SubLine` object references with `source_doc` (Python dataclass mutation). Mutating `translated_doc.lines[i].text` also mutates `source_doc.lines[i].text`, breaking gate check 4 (byte-identity comparison).
**Why it happens:** `SubDoc` is constructed by reference; shallow copy of `SubDoc.lines` doesn't deep-copy the `SubLine` objects.
**How to avoid:** Construct `translated_doc` as a new `SubDoc` with new `SubLine` instances: `SubLine(index=src.index, start_tc=src.start_tc, end_tc=src.end_tc, text=translated_text)` for each cue. Never mutate source lines.
[VERIFIED: trezarr/subtitles/model.py] — `SubLine` is a plain `@dataclass`, mutable by default.

---

## Code Examples

### Numbered-line prompt construction (D-13)
```python
# Source: Design decision D-13 + validated locally
def build_translate_prompt(
    batch_texts: list[str],
    context_before: list[str],
    context_after: list[str],
    source_lang: str = "English",
) -> str:
    parts = [
        f"Translate the following {source_lang} subtitle lines to Vietnamese.",
        "RULES:",
        "1. Output ONLY the numbered lines [1], [2], ... [N] in order.",
        "2. Keep <<T0>>, <<T1>>, ... tokens EXACTLY as-is (formatting placeholders).",
        "3. Do NOT translate or output the [context] lines.",
        "",
    ]
    if context_before:
        parts.append("[CONTEXT - read only, do not output]")
        for line in context_before:
            parts.append(f"[context] {line.strip()}")
        parts.append("")
    parts.append("[LINES TO TRANSLATE]")
    for i, text in enumerate(batch_texts, 1):
        parts.append(f"[{i}] {text.strip()}")
    if context_after:
        parts.append("")
        parts.append("[CONTEXT - read only, do not output]")
        for line in context_after:
            parts.append(f"[context] {line.strip()}")
    return "\n".join(parts)
```

### Sentinel extraction (D-12)
```python
# Source: Design decision D-12 + regex testing
import re
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\})')

def extract_sentinels(text: str) -> tuple[str, dict[str, str]]:
    sentinel_map: dict[str, str] = {}
    counter = 0
    def replacer(m: re.Match) -> str:
        nonlocal counter
        key = f"<<T{counter}>>"
        sentinel_map[key] = m.group(0)
        counter += 1
        return key
    cleaned = TAG_RE.sub(replacer, text)
    return cleaned, sentinel_map

def reinsert_sentinels(text: str, sentinel_map: dict[str, str]) -> tuple[str, bool]:
    """Returns (restored_text, integrity_ok). integrity_ok=False if any sentinel missing."""
    for key, original in sentinel_map.items():
        if key not in text:
            return text, False  # sentinel lost — gate will catch this
        text = text.replace(key, original, 1)
    # Check no orphan sentinels remain
    if re.search(r'<<T\d+>>', text):
        return text, False
    return text, True
```

### Vietnamese diacritic ratio check (D-17)
```python
# Source: Design decision D-17 + Python unicodedata/regex testing
import re
VN_DIACRITIC_RE = re.compile(r'[Ḁ-ỿ]')  # U+1E00-U+1EFF: Latin Extended Additional
ALLOWLIST_RE = re.compile(r'^[\W\d\s♪♫…]+$')  # legitimately unchanged

def vi_diacritic_ratio(translated_lines: list[str], source_lines: list[str]) -> float:
    translatable = [
        t for t, s in zip(translated_lines, source_lines)
        if t.strip() and not ALLOWLIST_RE.match(t.strip())
    ]
    if not translatable:
        return 1.0
    vi_count = sum(1 for t in translatable if VN_DIACRITIC_RE.search(t))
    return vi_count / len(translatable)
```

### Atomic sidecar write (D-19)
```python
# Source: Design decision D-19 + os.replace testing
import os, tempfile
from pathlib import Path
from trezarr.subtitles.srt import write_srt
from trezarr.subtitles.model import SubDoc

def write_vi_sidecar(doc: SubDoc, media_path: str | Path) -> Path:
    media_path = Path(media_path)
    # Derive .vi.srt path: strip format extension(s), add .vi.srt
    stem = media_path.stem  # e.g. "Show.S01E01.en" from "Show.S01E01.en.srt"
    if stem.endswith('.en') or stem.endswith('.ja') or stem.endswith(('.hi', '.fr')):
        stem = stem.rsplit('.', 1)[0]  # strip language code
    dest = media_path.parent / (stem + '.vi.srt')

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix='.tmp',
            dir=dest.parent,   # MUST be same filesystem as dest
            delete=False,
        ) as f:
            tmp_path = Path(f.name)
        # write_srt encodes with doc.encoding; override to utf-8 for output
        doc_out = SubDoc(
            lines=doc.lines,
            encoding='utf-8',          # always UTF-8 output
            line_ending=doc.line_ending,
            separators=doc.separators,
            leading=doc.leading,
            trailer=doc.trailer,
        )
        write_srt(doc_out, tmp_path)
        os.replace(tmp_path, dest)     # POSIX-atomic rename
        tmp_path = None                # prevent cleanup in finally
        return dest
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()           # cleanup on any failure
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-line LLM translation | Windowed batching with numbered-line protocol | ~2023 (GPT-4 era) | Batch protocol is now the standard in all OSS subtitle translators (chatgpt-subtitle-translator, subtitle-translator) |
| JSON response_format for batch translation | Numbered-line plain-text protocol | 2024–2025 | JSON mode is brittle on long files (truncation/unescaped quotes corrupt the whole parse); numbered lines are more robust and endpoint-agnostic |
| pysubs2 for SRT codec | Custom byte-identical SRT reader (Phase 1 choice) | Phase 1 decision | pysubs2 normalizes timecodes/indices, breaking byte-identity; custom codec already built |
| File-presence check for idempotency | Content-hash keyed ledger | 2024+ LLM pipeline practice | Hash detects source upgrades that file-presence misses |

**Deprecated/outdated:**
- Using `json_schema` structured output for batch translation: NOT recommended for Phase 2 translation batches (only for Series Bible extraction in later phases). The DeepSeek endpoint may land on `text` mode (D-04); numbered-line protocol survives all three tiers.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Vietnamese output is ~1.4x longer than English input in token terms | Q1 (Token estimation) | If expansion is higher (e.g. 1.8x), batches may overflow context window; mitigated by 30% overhead reserve and max-cue cap |
| A2 | 2000ms is a reasonable scene-gap threshold for subtitle batch boundaries | Q2 (Batch packing) | If too low: many small batches, more LLM calls; if too high: context not respected at scene breaks. Configurable. |
| A3 | K=3 neighbor lines is sufficient for conversational coherence | Q3 (Context window) | If K is too small, pronoun choices in early Phase 2 may be less coherent; Phase 4+ (Series Bible) is the real solution |
| A4 | `<<T…>>` sentinel format is reliably preserved by the DeepSeek-family endpoint | Q4 (Sentinels) | If the model strips angle brackets, sentinel check fails → batch retry → quarantine; recoverable. |
| A5 | The `[Ḁ-ỿ]` regex (U+1E00+) reliably identifies Vietnamese vs. French/Spanish output | Q5 (Gate check 3) | French does not use U+1E00-U+1EFF; Vietnamese does heavily. Risk: a Pinyin-transliterated Chinese line might slip through. Acceptable for Phase 2. |
| A6 | 0.70 VI diacritic ratio threshold is appropriately conservative | Q5 (Gate check 3) | If too high: false-reject proper-noun-heavy episodes. If too low: passes partially-untranslated files. Configurable. |
| A7 | The `[N] text` numbered-line prompt format elicits compliant output from the DeepSeek endpoint | Q3/Q4 (Prompt design) | If the endpoint rephrases or reorders output differently, the parser needs to be more forgiving (e.g. strip `[N].` vs `[N]`). Mitigation: use forgiving regex `r'\[(\d+)\][.\)]?\s*(.*)'`. |
| A8 | `os.replace()` is POSIX-atomic on the Linux Docker target | Q6 (Atomic write) | Linux + ext4/xfs/btrfs: guaranteed atomic. macOS (dev env): tested and confirmed. Windows: out of scope. |

---

## Open Questions

1. **Proper noun detection for VI ratio denominator**
   - What we know: Lines with only proper nouns (character names, place names) should be excluded from the VI diacritic ratio denominator, not just all-punctuation lines
   - What's unclear: A reliable heuristic for "is this line all proper nouns?" without an NLP library dependency
   - Recommendation: Use the existing allowlist (all-caps / title-case only lines are often names) as a best-effort; accept that some proper-noun lines will slightly lower the ratio; the 0.70 threshold already accounts for this

2. **Multi-line SRT cues and sentinel positioning**
   - What we know: `SubLine.text` may contain embedded newlines (multi-line cues in SRT); e.g. `"First line\nSecond line"`. The numbered-line protocol sends `SubLine.text.strip()` as a single `[N]` entry.
   - What's unclear: If the model reformats a two-line cue as one line or vice versa, is that a quality issue or a gate failure?
   - Recommendation: For Phase 2, treat multi-line cues as single units (send stripped, accept back as single line). The gate only checks cue count, not internal newline count. Phase 4+ can add multi-line awareness.

3. **Sidecar naming when source has no language code in stem**
   - What we know: Some SRT files are named `Show.S01E01.srt` (no language code); others are `Show.S01E01.en.srt`.
   - What's unclear: Reliable detection of whether `.en` in the stem is a language code or part of the show title
   - Recommendation: Use a short list of known ISO-639 codes for the strip check. If not matched, just strip the `.srt` extension and append `.vi.srt`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Project floor (pyarr) | dev: 3.9.6 (system); project uses uv venv | uv env: 3.12.x | uv ensures 3.12 in project venv |
| tenacity | Batch-level retry (D-18) | Not installed in project yet | 9.1.4 on PyPI | Simple `for attempt in range(N)` loop (less clean) |
| hashlib | Content hashing for ledger | stdlib — always available | stdlib | — |
| os.replace | Atomic sidecar write | stdlib — confirmed working | stdlib | — |
| json | Idempotency ledger | stdlib — always available | stdlib | — |
| re / unicodedata | Sentinel regex, VI diacritic check | stdlib — confirmed working | stdlib | — |
| pytest / pytest-asyncio | Test framework | Installed — 27 tests pass | pytest 9.0.3 | — |

**Missing dependencies with no fallback:**
- `tenacity` must be added to `pyproject.toml` (`uv add tenacity`) before Phase 2 implementation — or the batch retry uses a manual loop (acceptable but not prescribed-stack-compliant)

**Missing dependencies with fallback:**
- None of the required logic depends on an external service or unavailable tool

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.2.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/translate/ tests/output/ -x -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENG-02 | Batching respects token budget and never splits a cue | unit | `uv run pytest tests/translate/test_batching.py -x` | No — Wave 0 |
| ENG-02 | Scene-gap boundary preference | unit | `uv run pytest tests/translate/test_batching.py::test_scene_gap_boundary -x` | No — Wave 0 |
| ENG-02 | Max-cue-count fallback when no scene gap | unit | `uv run pytest tests/translate/test_batching.py::test_max_cue_fallback -x` | No — Wave 0 |
| ENG-03 | Context window K lines attached, model instructions not to re-emit | unit | `uv run pytest tests/translate/test_engine.py::test_context_window_prompt -x` | No — Wave 0 |
| ENG-06 | Gate rejects cue-count mismatch | unit | `uv run pytest tests/translate/test_validate.py::test_gate_count_mismatch -x` | No — Wave 0 |
| ENG-06 | Gate rejects empty translated line | unit | `uv run pytest tests/translate/test_validate.py::test_gate_empty_line -x` | No — Wave 0 |
| ENG-06 | Gate rejects VI diacritic ratio below threshold | unit | `uv run pytest tests/translate/test_validate.py::test_gate_vi_ratio -x` | No — Wave 0 |
| ENG-06 | Gate rejects timecode mutation | unit | `uv run pytest tests/translate/test_validate.py::test_gate_timecode_mutation -x` | No — Wave 0 |
| ENG-06 | Gate rejects non-monotonic timestamps | unit | `uv run pytest tests/translate/test_validate.py::test_gate_nonmonotonic -x` | No — Wave 0 |
| ENG-06 | Gate rejects orphan sentinel tokens | unit | `uv run pytest tests/translate/test_validate.py::test_gate_sentinel_orphan -x` | No — Wave 0 |
| ENG-06 | Gate rejects lone-surrogate UTF-8 | unit | `uv run pytest tests/translate/test_validate.py::test_gate_utf8_invalid -x` | No — Wave 0 |
| ENG-06 | Batch retry: gate passes on second attempt (mock LLM) | unit | `uv run pytest tests/translate/test_engine.py::test_batch_retry -x` | No — Wave 0 |
| ENG-06 | Whole-file quarantine after retry exhaustion | unit | `uv run pytest tests/translate/test_engine.py::test_quarantine_on_retry_exhaustion -x` | No — Wave 0 |
| ENG-07 | Ledger skip when output exists + hash matches | unit | `uv run pytest tests/output/test_ledger.py::test_skip_unchanged -x` | No — Wave 0 |
| ENG-07 | Ledger regenerate when source hash changed | unit | `uv run pytest tests/output/test_ledger.py::test_regenerate_on_hash_change -x` | No — Wave 0 |
| ENG-07 | Foreign `.vi.srt` skipped + logged, not clobbered | unit | `uv run pytest tests/output/test_ledger.py::test_foreign_srt_not_clobbered -x` | No — Wave 0 |
| ENG-07 | Quarantined file retried on re-run | unit | `uv run pytest tests/output/test_ledger.py::test_quarantine_retry -x` | No — Wave 0 |
| FMT-05 | Sidecar naming derives `.vi.srt` from source path | unit | `uv run pytest tests/output/test_write.py::test_sidecar_naming -x` | No — Wave 0 |
| FMT-05 | Atomic write: crash before os.replace leaves no corrupt dest | unit | `uv run pytest tests/output/test_write.py::test_atomic_write_crash_safety -x` | No — Wave 0 |
| FMT-05 | Output is valid UTF-8 (diacritics round-trip) | unit | `uv run pytest tests/output/test_write.py::test_utf8_output -x` | No — Wave 0 |

### Key Validation Priority (Gate bias test)
The gate's "false reject over missed miss" bias is the most critical property to test. For each gate check, there must be a test that proves:
- A **true failure** (e.g. wrong cue count, orphan sentinel) is **always caught** (zero false negatives)
- A **legitimate edge case** (proper nouns lowering VI ratio slightly, multi-line cue) is **not wrongly rejected** (low false positives)

### Sampling Rate
- **Per task commit:** `uv run pytest tests/translate/ tests/output/ -x -q`
- **Per wave merge:** `uv run pytest -q` (full suite including Phase 1 codec + LLM client tests)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/translate/__init__.py`
- [ ] `tests/translate/test_batching.py` — covers ENG-02 (batch packing, scene-gap, max-cue)
- [ ] `tests/translate/test_engine.py` — covers ENG-03, ENG-06 retry/quarantine, D-13 numbered-line parse
- [ ] `tests/translate/test_validate.py` — covers all 7 gate checks (ENG-06)
- [ ] `tests/translate/test_sentinel.py` — covers D-12 sentinel extract/reinsert + integrity check
- [ ] `tests/output/__init__.py`
- [ ] `tests/output/test_write.py` — covers FMT-05 naming, atomic write, UTF-8
- [ ] `tests/output/test_ledger.py` — covers ENG-07 skip/regenerate/foreign/quarantine-retry

---

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1` (ASVS Level 1 applies)

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Phase 2 has no auth surface (file I/O + in-process calls only) |
| V3 Session Management | No | No sessions in Phase 2 |
| V4 Access Control | No | Single-user daemon; file write access controlled by PUID/PGID (Phase 7) |
| V5 Input Validation | Yes | Validate all LLM responses before acting on them (gate checks 1–7) |
| V6 Cryptography | No | SHA-256 content hash is not a security primitive here; no secrets stored |
| V7 Error Handling | Yes | Quarantine on failure; never swallow exceptions silently; log loudly |
| V12 Files and Resources | Yes | Atomic write prevents partial files; `dir=dest.parent` prevents cross-device race |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM output injection (prompt injection via subtitle content) | Tampering | Numbered-line protocol + sentinel extraction means raw text is never evaluated as code; output is parsed structurally, not executed |
| Path traversal via media path arg | Tampering | `Path(media_path).resolve()` in `write_vi_sidecar`; validate path is within configured media roots (Phase 3 will enforce; Phase 2 should accept only absolute paths) |
| Quarantine artifact leaks subtitle content | Information Disclosure | Quarantine JSON includes failing cue indices and reason, but should NOT include full cue text if the source subtitle may be proprietary. Recommend: include cue indices + reason, NOT cue text, in quarantine artifact. |
| Ledger JSON corruption → re-translate foreign VI subs | Tampering | Fallback on `JSONDecodeError` to empty ledger + loud warning; foreign-file check also relies on file existence + ledger absence (belt-and-suspenders) |

### ASVS V5 Input Validation — Specific Controls
The LLM response is untrusted input. The gate (all 7 checks) is the V5 control. Every piece of the LLM response that mutates application state (cue text) must pass the gate before being written. This is the architectural realization of "never trust LLM output without validation."

---

## Sources

### Primary (HIGH confidence)
- `trezarr/subtitles/model.py` — SubDoc/SubLine field names, mutability, SubLine.text as sole LLM-mutable field [VERIFIED: read directly]
- `trezarr/subtitles/srt.py` — read_srt/write_srt byte-identical contract, _TC_RE timecode regex [VERIFIED: read directly + uv run testing]
- `trezarr/llm/client.py` — LLMClient.call() semaphore placement, D-04 degradation, exception catch policy [VERIFIED: read directly]
- `trezarr/config.py` — TrezarrSettings field names, pydantic-settings pattern for extension [VERIFIED: read directly]
- `.planning/phases/02-mechanical-translation-core-validation-gate/02-CONTEXT.md` — D-12 through D-20, all locked decisions [VERIFIED: read directly]
- `.planning/research/PITFALLS.md` — Pitfall 1 (cue-count drift), Pitfall 7 (silent bad write), Pitfall 10 (Bazarr collision + self-loop) [VERIFIED: read directly]
- Python stdlib docs — `os.replace` POSIX atomicity, `hashlib.sha256`, `tempfile.NamedTemporaryFile` [VERIFIED: stdlib testing]

### Secondary (MEDIUM confidence)
- CLAUDE.md (project CLAUDE.md) — full prescribed stack, "no per-call tenacity", AsyncOpenAI pattern, semaphore concurrency [CITED: project CLAUDE.md]
- `.planning/research/STACK.md` — tenacity 9.1.x prescribed, "use tenacity only at pipeline-step level" [VERIFIED: read directly]
- PyPI JSON API (2026-05-31) — tenacity 9.1.4 current version [VERIFIED: live PyPI query]
- slopcheck results (2026-05-31) — all 5 packages [OK] [VERIFIED: slopcheck run]
- chatgpt-subtitle-translator (Cerlancism) — numbered-line protocol, cascading batch-size retry [CITED: PITFALLS.md reference]

### Tertiary (LOW confidence — marked [ASSUMED] above)
- Vietnamese output expansion 1.4x vs English: general translation observation, not subtitle-corpus measured [ASSUMED]
- 2000ms scene-gap threshold: industry subtitling convention lower bound [ASSUMED]
- K=3 neighbor lines for coherence: general LLM translation best practice [ASSUMED]
- `<<T…>>` sentinel LLM pass-through: derived from general model behavior with template tokens [ASSUMED]
- 0.70 VI diacritic ratio threshold: not calibrated against real subtitle corpora [ASSUMED]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Phase 1 stack unchanged; tenacity is prescribed; all stdlib
- Architecture: HIGH — directly grounded in Phase 1 code; data flow verified against actual SubDoc/SubLine model
- Gate checks 1-4, 6-7: HIGH — implemented logic verified in Python
- Gate check 5 (VI diacritic ratio threshold): MEDIUM — logic verified, threshold value assumed
- Batch-packing algorithm: MEDIUM — logic verified, parameter values assumed
- Prompt design: MEDIUM — pattern is standard, DeepSeek endpoint behavior unverified
- Pitfalls: HIGH — grounded in Phase 1 code + PITFALLS.md

**Research date:** 2026-05-31
**Valid until:** 2026-07-01 (stable domain; no fast-moving dependencies in Phase 2 scope)
