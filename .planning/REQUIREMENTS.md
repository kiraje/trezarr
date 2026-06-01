# Requirements: Trezarr

**Defined:** 2026-05-31
**Core Value:** Vietnamese subtitles that stay consistent and relationally correct (right pronoun pair, stable names/terms) across an entire series — produced automatically.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Integration

- [x] **INTG-01**: Trezarr connects to Sonarr and Radarr via their REST APIs (API-key auth) to discover the media library, episode/movie identity, file paths, and metadata
- [ ] **INTG-02**: Trezarr connects to Bazarr via its API to read which source-language subtitles already exist for each item (so it never re-downloads subs)
- [x] **INTG-03**: User can configure container↔host path mapping so Trezarr resolves the same media files the *arr stack sees
- [x] **INTG-04**: Trezarr reads source subtitle files and writes Vietnamese sidecar files on the shared filesystem with correct permissions (PUID/PGID)

### Discovery & Automation

- [x] **AUTO-01**: Trezarr automatically detects media that has a source subtitle but no good Vietnamese subtitle and queues it for translation
- [ ] **AUTO-02**: Trezarr monitors for newly added media / new source subtitles on an ongoing basis (polling, with webhook trigger support)
- [x] **AUTO-03**: Trezarr is idempotent — it tracks per-item translation state (incl. source-sub hash) and skips items already up to date, never causing re-translation storms
- [x] **AUTO-04**: Trezarr excludes its own output from re-triggering the watcher (no self-reprocessing loop)
- [ ] **AUTO-05**: Processing resumes safely after a crash or restart without losing or duplicating work

### Subtitle Formats

- [x] **FMT-01**: Trezarr parses and writes SRT, preserving indices, timecodes, and line segmentation exactly (translates text only, never timestamps)
- [ ] **FMT-02**: Trezarr parses and writes ASS/SSA, translating only dialogue text and leaving override tags (`{\an8}`, `\pos`, fonts), drawing commands, `\N` breaks, and `[Script Info]`/`[V4+ Styles]` headers byte-identical
- [ ] **FMT-03**: Trezarr preserves karaoke (`\k`) lines without corruption (verbatim if remapping is unsafe)
- [ ] **FMT-04**: Trezarr parses and writes VTT, round-tripping cue settings/positioning
- [x] **FMT-05**: Output subtitles use correct sidecar naming (`Show.S01E01.vi.srt`, matching the video basename and ISO-639 `vi`), are written atomically (temp+rename), and are valid UTF-8

### Translation Engine

- [x] **ENG-01**: User can configure a user-provided OpenAI-SDK-compatible endpoint (base URL, model, API key) that powers all translation
- [x] **ENG-02**: Trezarr batches/chunks long subtitle files within token limits without splitting a sentence or scene across batch boundaries
- [x] **ENG-03**: Each batch is translated with a surrounding-line context window (read-only lines before/after) for conversational coherence
- [x] **ENG-04**: Trezarr runs a two-pass pipeline — Pass 1 analyzes the full file + media metadata to build/update the Series Bible before Pass 2 translates any line
- [ ] **ENG-05**: Trezarr runs an LLM self-review pass over translated output, checking Series Bible adherence (pronouns/terms/register) and correcting violations before finalizing
- [x] **ENG-06**: A hard pre-write validation gate verifies cue-count match, no untranslated lines, monotonic timestamps, and format integrity — failing files are quarantined, never written
- [x] **ENG-07**: A failed or rejected translation can be retried/re-run idempotently, reusing existing Series Bible state

### Series Bible (Consistency Engine)

- [ ] **BIBLE-01**: Trezarr maintains a persistent per-series Series Bible that is loaded as context for every episode and updated after each
- [ ] **BIBLE-02**: The Bible records Characters (name in original Latin form, gender, rough age, role)
- [x] **BIBLE-03**: The Bible records a directed Address Map — for each ordered character pair, the self-term and address-term (e.g. `John→Mary: self=anh, address=em`), supporting asymmetric pairs
- [ ] **BIBLE-04**: The Bible records a Term Dictionary mapping recurring proper nouns, titles, places, and jargon to fixed Vietnamese renderings (incl. character-name romanization policy)
- [ ] **BIBLE-05**: The Bible records a Register/tone per series, grounded in media metadata (genre/plot/era from Sonarr/Radarr/TMDB)
- [ ] **BIBLE-06**: The Bible is carried forward across episodes so a character is addressed consistently from S01E01 to the finale
- [ ] **BIBLE-07**: Trezarr tracks relationship evolution across episodes (e.g. strangers→lovers, enemies→rivals) with episode markers so pronoun choices change correctly over the series
- [ ] **BIBLE-08**: User can view and edit the Series Bible (characters, address map, term dictionary, register); edits are lockable and survive re-analysis
- [ ] **BIBLE-09**: Locked corrections propagate forward to all subsequent episode translations (the human override valve)

### Pronoun Attribution

- [x] **PRON-01**: Trezarr infers the speaker and addressee for each line from dialogue content, turn-taking, and vocatives (subtitles carry no speaker labels)
- [x] **PRON-02**: Trezarr applies the correct Vietnamese pronoun pair from the Address Map based on the inferred speaker→addressee relationship
- [x] **PRON-03**: When attribution is low-confidence, Trezarr falls back to a safe register rather than risk a wrong intimate pronoun

### Source Selection

- [ ] **SRC-01**: Trezarr is source-language-agnostic — it can translate from any available source-language subtitle to Vietnamese
- [ ] **SRC-02**: When multiple source subtitles exist for the same item, Trezarr selects the source language whose honorific/relational system best preserves the information Vietnamese needs (prefer Chinese/Korean/Japanese/Thai for East-Asian content over English, which flattens relationships), falling back to whatever is available

### Service & Web UI

- [ ] **SVC-01**: Trezarr ships as a single Dockerized, long-running self-hosted service deployable alongside the *arr stack (`/config` volume for DB + config)
- [ ] **SVC-02**: A web UI lets the user configure connections (Sonarr/Radarr/Bazarr, LLM endpoint, paths) and global settings
- [ ] **SVC-03**: The web UI shows a Queue (in-flight), History (completed/failed with per-item reason), and per-job logs
- [ ] **SVC-04**: User can retry or re-run a failed/rejected item from the UI
- [ ] **SVC-05**: User can set per-series overrides (source-language preference, register, model)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Trust & Observability

- **OBS-01**: Confidence-flagging of low-certainty attribution lines surfaced in the UI
- **OBS-02**: Notifications (Discord/Telegram/ntfy) on completion/failure

### Scale & Community

- **SCALE-01**: Support multiple Sonarr/Radarr instances
- **COMM-01**: Series Bible / glossary import-export and sharing between users

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Target languages other than Vietnamese | Vietnamese relational consistency is the hard problem and the moat; multi-target dilutes the engine |
| Re-downloading / acquiring source subtitles | Bazarr already does this seamlessly; duplicating it competes with the tool we integrate with |
| Bundling/hosting a local LLM model | User brings their own OpenAI-compatible endpoint; hosting models is an ops burden |
| Per-line human review/correction workflow UI | Contradicts the fully-automated mission; the editable Series Bible is the only human touchpoint |
| Cost/token budgeting dashboards | User runs their own endpoint; per-call cost is not a concern |
| Burning subtitles into video / re-muxing | Destroys the sidecar model media servers rely on; heavy and risky |
| Real-time/streaming translation | The consistency engine needs the whole file up front; accuracy over latency |
| Auto-syncing/re-timing subtitles | That's Bazarr/sub-sync's job; mixing it in risks breaking preserved timing |
| Generating subs from audio (ASR/Whisper) | Different problem (speech→text); Trezarr translates existing subs |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INTG-01 | Phase 3 | Complete |
| INTG-02 | Phase 10 | Pending |
| INTG-03 | Phase 3 | Complete |
| INTG-04 | Phase 3 | Complete |
| AUTO-01 | Phase 3 | Complete |
| AUTO-02 | Phase 7 | Pending |
| AUTO-03 | Phase 3 | Complete |
| AUTO-04 | Phase 3 | Complete |
| AUTO-05 | Phase 7 | Pending |
| FMT-01 | Phase 1 | Complete |
| FMT-02 | Phase 9 | Pending |
| FMT-03 | Phase 9 | Pending |
| FMT-04 | Phase 9 | Pending |
| FMT-05 | Phase 2 | Complete |
| ENG-01 | Phase 1 | Complete |
| ENG-02 | Phase 2 | Complete |
| ENG-03 | Phase 2 | Complete |
| ENG-04 | Phase 5 | Complete |
| ENG-05 | Phase 6 | Pending |
| ENG-06 | Phase 2 | Complete |
| ENG-07 | Phase 2 | Complete |
| BIBLE-01 | Phase 4 | Pending |
| BIBLE-02 | Phase 4 | Pending |
| BIBLE-03 | Phase 5 | Complete |
| BIBLE-04 | Phase 4 | Pending |
| BIBLE-05 | Phase 4 | Pending |
| BIBLE-06 | Phase 4 | Pending |
| BIBLE-07 | Phase 6 | Pending |
| BIBLE-08 | Phase 8 | Pending |
| BIBLE-09 | Phase 8 | Pending |
| PRON-01 | Phase 5 | Complete |
| PRON-02 | Phase 5 | Complete |
| PRON-03 | Phase 5 | Complete |
| SRC-01 | Phase 10 | Pending |
| SRC-02 | Phase 10 | Pending |
| SVC-01 | Phase 7 | Pending |
| SVC-02 | Phase 7 | Pending |
| SVC-03 | Phase 7 | Pending |
| SVC-04 | Phase 7 | Pending |
| SVC-05 | Phase 10 | Pending |

**Coverage:**
- v1 requirements: 40 total (INTG 4, AUTO 5, FMT 5, ENG 7, BIBLE 9, PRON 3, SRC 2, SVC 5 — the initial header count of "38" was a miscount; all 40 listed requirements are mapped)
- Mapped to phases: 40 ✓
- Unmapped: 0 ✓
- Duplicates (a requirement in >1 phase): 0 ✓

---
*Requirements defined: 2026-05-31*
*Last updated: 2026-06-01 — Phase 3 complete: INTG-01, INTG-03, INTG-04, AUTO-01, AUTO-03, AUTO-04 marked Complete in traceability table*
