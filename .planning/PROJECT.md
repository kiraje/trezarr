# Trezarr

## What This Is

Trezarr is an automated Vietnamese subtitle translator that runs as a companion to the
Bazarr / Sonarr / Radarr self-hosted media stack. It watches for media that has a
source-language subtitle but no high-quality Vietnamese one, translates it with the user's
own LLM endpoint, and writes a Vietnamese sidecar subtitle (`Show.S01E01.vi.srt`) next to the
media — fully automated, no human in the loop. Its mission is to produce Vietnamese subtitles
good enough to **replace a human translator**, with the glossary, pronoun, and relationship
consistency that ordinary machine translation destroys.

## Core Value

Vietnamese subtitles that stay **consistent and relationally correct across an entire series** —
the right pronoun pair (anh/em, chị/em, ông/bà...) for every relationship, the same character
names and terms from episode 1 to the finale — produced automatically. If everything else fails,
this consistency must work.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**Integration & automation (partial — Phase 3):**
- [x] Connect to Sonarr / Radarr via their REST APIs (X-Api-Key, pyarr 6.x) to discover the media library — Validated in Phase 3 (INTG-01). Bazarr connection deferred to Phase 10.
- [x] Share the same filesystem and write Vietnamese subtitles as sidecar files next to the media (auto-detected by Plex/Jellyfin/Emby) — Validated in Phase 3 (INTG-04: PUID/PGID/UMASK applied in-process; chmod failure quarantines; container↔host path mapping with traversal guard, INTG-03).
- [x] Detect media that has a source subtitle but no good Vietnamese subtitle and queue it — Validated in Phase 3 (AUTO-01 gap detection, AUTO-03 source-sub-hash idempotency, AUTO-04 self-output exclusion via ledger provenance). Continuous monitoring (poll + watchfiles + webhook) deferred to Phase 7.

**Vietnamese consistency engine — Series Bible (partial — Phase 4):**
- [x] Maintain a persistent, per-series Series Bible that is carried forward across all episodes — Validated in Phase 4 (BIBLE-01 SQLite-backed schema + LedgerSQLA, BIBLE-06 carry-forward via `merge_inferred` with lock-precedence; auto-population by LLM is Phase 5).
- [x] Bible tracks Characters (name kept in original Latin form, gender, rough age, role) — Validated in Phase 4 (BIBLE-02 `character` table + `upsert_character`).
- [x] Bible tracks a Term Dictionary — recurring proper nouns, titles, places, domain/fantasy/sci-fi jargon → fixed Vietnamese rendering — Validated in Phase 4 (BIBLE-02 `term_dictionary` table + `upsert_term`).
- [x] The Series Bible is auto-built but **editable** — corrections lock and propagate forward — Validated in Phase 4 (BIBLE-04 per-field `locked_fields` JSON enforced by `merge_inferred`; "human lock > prior value > new inference" verified). Editor UI deferred to a later phase.

**Pronoun engine + Bible auto-population (Phase 5):**
- [x] Three-pass pipeline — Pass 1 analyzes the full file + media metadata into the Bible (barrier), Pass 2 infers speaker/addressee per line, Pass 3 translates applying the resolved pronoun pair — Validated in Phase 5 (ENG-04 analyze-before-translate ordering). LLM self-review pass is Phase 6 (ENG-05).
- [x] Bible tracks a directed Address Map — per ordered character pair, self-term + address-term (e.g. `John→Mary: self=anh, address=em`), with reciprocal coherence — Validated in Phase 5 (BIBLE-03 `upsert_address_pair` + deterministic per-episode reconciliation).
- [x] Bible Register/tone inferred from media metadata + dialogue and grounded into prompts — Validated in Phase 5 (BIBLE-05, populated via `merge_inferred`).
- [x] Infer speaker and addressee per line from dialogue context and apply the correct pronoun pair; low-confidence → safe neutral/polite default rather than a wrong intimate pronoun — Validated in Phase 5 (PRON-01 attribution, PRON-02 application, PRON-03 safe fallback). Per-episode consistency is a deterministic reconciliation property, not an LLM gamble. (Live-LLM pronoun quality tracked in `05-HUMAN-UAT.md`.)

### Active

<!-- Current scope. Building toward these. Hypotheses until shipped. -->

**Integration (continuous monitoring + Bazarr):**
- [ ] Continuous monitor for media that has a source subtitle but no good Vietnamese subtitle, and act automatically (Phase 7 — daemon/poll/webhook/watchfiles)
- [ ] Connect to Bazarr's API to read existing source-language subtitle inventory (Phase 10, INTG-02)

**Translation engine:**
- [ ] Use the user's own OpenAI-SDK-compatible LLM endpoint (configurable base URL / model / key)
- [ ] LLM self-review pass — model critiques and corrects its own translation for consistency before the file is finalized — Phase 6 (ENG-05). The analyze→attribute→translate pipeline it reviews shipped in Phase 5 (now Validated).
- [ ] Translation context includes: surrounding subtitle lines, full-file glossary, media metadata (plot/cast/genre from Sonarr/Radarr/TMDB), and the prior-episode Series Bible (Pass-1 metadata + Bible grounding shipped in Phase 5)

**Vietnamese consistency engine — the "Series Bible" (persistence Phase 4, LLM auto-population + Address Map Phase 5):**
- [ ] Track relationship **evolution** across episodes (enemies→lovers, strangers→friends) with episode markers so pronoun choices change correctly over the series — Phase 6 (BIBLE-07). Phase 5 writes a static-per-episode Address Map with `valid_from_episode` set; Phase 6 makes the active pair change over the series.

**Smart attribution & source selection:**
- [ ] Source-agnostic input, but **intelligently prioritized**: when multiple source subtitles exist for the same media, prefer the source language whose honorific/relational system best preserves the information Vietnamese needs (e.g. prefer a Chinese/Korean/Japanese source for East-Asian content over English, which flattens all relationships to "I/you"); fall back to whatever is available

**Formats & delivery:**
- [ ] Handle SRT (universal baseline)
- [ ] Handle ASS/SSA while preserving styling, fonts, and positioning (anime/fansub use)
- [ ] Handle VTT
- [ ] Ship as a Dockerized, long-running self-hosted service with a web config/dashboard UI, deployable alongside the *arr stack

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Target languages other than Vietnamese — Vietnamese is the entire focus and the hard problem worth solving; other targets dilute it
- Replacing Bazarr's subtitle *downloading* — Bazarr already fetches source subs seamlessly; Trezarr's value is translation, not acquisition (full-replacement was considered and rejected)
- A human review/correction *UI workflow* — the product is fully automated; the editable Series Bible file is the only human touchpoint for v1
- Local/self-hosted model bundling — the user brings their own OpenAI-compatible endpoint; Trezarr does not host or ship a model
- Cost/token budgeting features — the user runs their own endpoint, so per-translation cost is not a v1 concern

## Context

- The target audience is self-hosters running the Sonarr/Radarr/Bazarr stack first; the Vietnamese fansub/media community is an eventual, intended audience (build for self, design to share).
- Vietnamese is uniquely hard for machine translation: it has no neutral "I/you" — every utterance encodes the relationship between speaker and listener through an extensive system of relational pronouns and kinship/honorific terms. Standard MT (and Bazarr's built-in translators) flatten this and produce subtitles that are tonally wrong or outright rude.
- Reference product for integration patterns and conventions: Bazarr (https://github.com/morpheus65535/bazarr) — Python + web UI, Dockerized, connects to Sonarr/Radarr via API, writes sidecar subtitle files. Trezarr mirrors this relationship one level up (Trezarr ↔ Bazarr/*arr).
- Key linguistic insight driving source selection: source languages structurally similar to Vietnamese (Chinese, Korean, Japanese, Thai — relational address, honorifics, speech levels) carry the relationship information that English discards, and therefore translate more faithfully into Vietnamese.

## Constraints

- **Tech stack**: LLM access is via an OpenAI-SDK-compatible endpoint (user-provided base URL/model/key)
- **Deployment**: Must run as a Dockerized self-hosted service with a web UI, deployable alongside Bazarr/Sonarr/Radarr
- **Integration**: Must interoperate cleanly with Sonarr/Radarr/Bazarr APIs and the *arr-stack filesystem/sidecar conventions
- **Compatibility**: Output subtitles must be auto-detected by common media players (Plex/Jellyfin/Emby) and preserve original styling for ASS/SSA
- **Quality bar**: Fully automated output must be trustworthy enough to use blind ("replace human translator") — consistency is non-negotiable

## Key Decisions

<!-- Decisions that constrain future work. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Companion to Bazarr/*arr, not a replacement | Bazarr already downloads source subs seamlessly; Trezarr adds translation as the smart layer | — Pending |
| Persistent, editable per-series "Series Bible" as the consistency core | Vietnamese needs relationship state to choose pronouns; it must persist across episodes and be human-correctable | ✓ Implemented (Phase 4 persistence/locks + Phase 5 LLM auto-population incl. directed Address Map). Editor UI deferred. |
| LLM infers speaker/addressee from context | Subtitles rarely carry speaker labels; frontier-model inference is where "ultimate" quality comes from | ✓ Implemented (Phase 5) — Pass 2 attribution + deterministic reconciliation; one pronoun pair per ordered pair per episode, low-confidence → safe default |
| Track relationship evolution across episodes | Pronoun pairs change as relationships change (enemies→lovers); static maps would drift wrong | — Pending |
| Source-agnostic input, prioritized by relational fidelity to Vietnamese | English flattens relationships; the original East-Asian source preserves the info Vietnamese needs | — Pending |
| Two-pass + LLM self-review pipeline | Full-file analysis enables consistency; a self-critique pass earns blind-trust automation | ◑ Partial — three-pass analyze→attribute→translate shipped (Phase 5); LLM self-review pass is Phase 6 (ENG-05) |
| User-provided OpenAI-compatible endpoint | User already has their own LLM endpoint; avoids hosting models and cost-management scope | ✓ Implemented (Phase 1) — AsyncOpenAI client wraps base_url/model/key with retries, an asyncio.Semaphore concurrency cap, and json_schema→json_object→text fallback, as an isolated tested leaf |
| Dockerized service + web UI | Matches *arr-stack conventions self-hosters expect | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-02 after Phase 5 (Three-Pass Pronoun Engine) — see Phase 5 entry below for what shipped.

*Phase 5 (Three-Pass Pronoun Engine, 2026-06-02): the translation pipeline became Bible-aware and shipped the core differentiator. `translate_file` now runs Pass 1 (full-file Bible analysis → merge characters/terms/register/directed Address Map, a barrier) → Pass 2 (per-cue speaker/addressee attribution with confidence) → deterministic reconciliation (one `(self_term, address_term)` per ordered pair per episode, reciprocal-coherent via a Vietnamese kinship table) → Pass 3 (numbered-line translation with per-line pronoun hints injected into the prompt; no mechanical substitution) → existing document gate → atomic write. New: `trezarr/bible/analyze.py`, `trezarr/translate/attribute.py`, `trezarr/translate/reconcile.py`, `upsert_address_pair`/`load_address_map` + `AddressMapDTO`, `Series.address_maps` relationship (no migration), `derive_episode_key` (parses SxxExx from filename), and Phase-5 `TrezarrSettings` fields. Low-confidence/unknown → safe neutral default (`tôi`/`bạn`); Tier-3-only endpoints degrade gracefully rather than quarantine; only Pass-1/2 logic failures quarantine. Single `asyncio.Semaphore` invariant and Pydantic-only store boundary preserved. Code review found + fixed 2 blockers (case-sensitive name resolution silently dropping pairs; a consistency test that didn't actually test consistency) and 7 warnings. 226 tests GREEN, 0 xfailed. Verified 4/4 must-haves (ENG-04, BIBLE-03, PRON-01/02/03). 2 live-LLM items pending in `05-HUMAN-UAT.md` (real-episode pronoun quality; the enable_pass1_analysis/enable_attribution toggle in production).*

*Phase 2 (Mechanical Translation Core + Validation Gate, 2026-05-31): `translate_file()` batches a parsed source (scene-gap/token-aware), translates via a single LLM pass with surrounding-line context, enforces a hard 7-check pre-write validation gate (failing files quarantined, never written), and writes an atomic UTF-8 `Show.S01E01.vi.srt` sidecar with idempotent re-run via a content-hash ledger (ENG-02, ENG-03, ENG-06, ENG-07, FMT-05 — verified 4/4).*

*Phase 4 (Series Bible Store & Schema, 2026-06-01): SQLite-backed Series Bible substrate ships — SQLAlchemy 2.0 async + aiosqlite + Alembic baseline migration creating 7 tables (series, character, term_dictionary, address_map, bible_event, relationship_event, processed_file). `get_or_create_series` lazily persists per-series rows with an arr_metadata snapshot from Sonarr/Radarr. `merge_inferred` enforces `human lock > prior value > new inference` and writes the row UPDATE + `bible_event` audit row in a single transaction (D-32). Per-field locks via `locked_fields` JSON survive merges. The Phase-2 JSON ledger is retired in favor of `LedgerSQLA` with a commit-first/rename-second one-shot JSON→SQLite migration. 208 tests GREEN. Register stays NULL by design — LLM populates it in Phase 5. Known advisory issues: CR-01 missing `await engine.dispose()` in `_run_once`, CR-02 Pydantic `register` field shadows BaseModel.register (rename + alias needed). 2 human UAT items pending in `04-HUMAN-UAT.md` (live *arr smoke, asyncio teardown). BIBLE-01/02/04/05/06 verified 5/5.*
