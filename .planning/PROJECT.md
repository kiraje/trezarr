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

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. Hypotheses until shipped. -->

**Integration (mirrors how Bazarr relates to Sonarr/Radarr — the "seamless" model):**
- [ ] Connect to Bazarr / Sonarr / Radarr via their APIs to discover the media library and existing subtitles
- [ ] Share the same filesystem and write Vietnamese subtitles as sidecar files next to the media (auto-detected by Plex/Jellyfin/Emby)
- [ ] Monitor for media that has a source subtitle but no good Vietnamese subtitle, and act automatically

**Translation engine:**
- [ ] Use the user's own OpenAI-SDK-compatible LLM endpoint (configurable base URL / model / key)
- [ ] Two-pass pipeline: (1) analyze the full subtitle file + media metadata to build/update the Series Bible, (2) translate line-by-line with context
- [ ] LLM self-review pass — model critiques and corrects its own translation for consistency before the file is finalized
- [ ] Translation context includes: surrounding subtitle lines, full-file glossary, media metadata (plot/cast/genre from Sonarr/Radarr/TMDB), and the prior-episode Series Bible

**Vietnamese consistency engine — the "Series Bible":**
- [ ] Maintain a persistent, per-series Series Bible that is carried forward across all episodes
- [ ] Bible tracks Characters (name kept in original Latin form, gender, rough age, role)
- [ ] Bible tracks a directed Address Map — for each ordered character pair, the self-term and address-term (the pronoun engine, e.g. `John→Mary: self=anh, address=em`)
- [ ] Bible tracks a Term Dictionary — recurring proper nouns, titles, places, domain/fantasy/sci-fi jargon → fixed Vietnamese rendering
- [ ] Bible tracks Register/tone (formal historical vs casual sitcom), grounded by media metadata
- [ ] The Series Bible is auto-built but **editable** — the user can open and correct it; corrections lock and propagate forward (this is the human override valve)
- [ ] Track relationship **evolution** across episodes (enemies→lovers, strangers→friends) with episode markers so pronoun choices change correctly over the series

**Smart attribution & source selection:**
- [ ] Infer speaker and addressee per line from dialogue context + the Series Bible (subtitles rarely carry speaker labels), and apply the correct pronoun pair
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
| Persistent, editable per-series "Series Bible" as the consistency core | Vietnamese needs relationship state to choose pronouns; it must persist across episodes and be human-correctable | — Pending |
| LLM infers speaker/addressee from context | Subtitles rarely carry speaker labels; frontier-model inference is where "ultimate" quality comes from | — Pending |
| Track relationship evolution across episodes | Pronoun pairs change as relationships change (enemies→lovers); static maps would drift wrong | — Pending |
| Source-agnostic input, prioritized by relational fidelity to Vietnamese | English flattens relationships; the original East-Asian source preserves the info Vietnamese needs | — Pending |
| Two-pass + LLM self-review pipeline | Full-file analysis enables consistency; a self-critique pass earns blind-trust automation | — Pending |
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
*Last updated: 2026-05-31 after Phase 1 (Codec & LLM Client Foundation) — SRT codec (byte-identical round-trip, FMT-01) and the OpenAI-compatible LLM client (ENG-01) shipped as tested, isolated leaves. Not yet moved to Validated: no user-facing sidecar is produced until Phase 2.*
