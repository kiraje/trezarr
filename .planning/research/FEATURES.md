# Feature Research

**Domain:** Automated subtitle translation tool / *arr-stack companion service (Vietnamese specialization)
**Researched:** 2026-05-31
**Confidence:** MEDIUM-HIGH (integration patterns & LLM-subtitle features HIGH from real tools; Vietnamese-consistency engine is novel, so its feature shape is reasoned-from-evidence MEDIUM)

## Context: The Baseline to Beat

**Bazarr does NOT do quality translation.** Auto-translation "isn't meant to be" a Bazarr feature and is explicitly not on its roadmap. Where translation exists in the ecosystem it is bolted on (Tautulli-agent scripts like `Bazarr_AutoTranslate`, community last-resort hacks) and uses flat NMT engines (Google Translate, LibreTranslate, DeepL). These translate each line **independently with no cross-line, cross-episode, or relationship context** — exactly the failure mode that destroys Vietnamese pronoun correctness. The bar Trezarr must clear is low on *quality* but high on *seamlessness*: Bazarr/Sonarr/Radarr users expect zero-friction API+sidecar integration, and a tool that doesn't match those conventions feels broken regardless of translation quality.

**The dominant LLM-subtitle tool to learn from is `machinewrapped/llm-subtrans`** (SRT/SSA/ASS/VTT, batching, scene detection, terminology maps, name lists, substitution pairs, multi-provider incl. OpenAI-compatible, project files for resume). `rockbenben/subtitle-translator` and `Cerlancism/chatgpt-subtitle-translator` confirm the same feature DNA: batching with surrounding-line context, glossary-in-system-prompt, format preservation. **None of these are series-aware, none track relationship state, none are Vietnamese-aware, and none integrate with the *arr stack.** That gap is Trezarr's entire opportunity.

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any of these makes Trezarr feel like a broken *arr citizen or an incomplete translator — users leave.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Sidecar output with correct naming (`Show.S01E01.vi.srt`) | Plex/Jellyfin/Emby auto-detect external subs only via `basename.<ISO639>.ext`; this is the *whole* delivery mechanism | LOW | Match video basename exactly; use `vi` (ISO-639-1). Support `.forced`/`.sdh` suffix passthrough. Write atomically (temp+rename) so media servers don't index half-written files |
| Connect to Sonarr/Radarr via API | Discover library, media metadata, paths, series/episode identity | MEDIUM | REST APIs are stable & well-documented; auth via API key. Need path-mapping config (container vs host paths) — a notorious *arr footgun |
| Connect to Bazarr via API | Discover which source subs already exist & their languages; avoid re-doing Bazarr's job | MEDIUM | Bazarr is the source-sub provider per the PROJECT decision; read its sub inventory rather than re-scanning |
| Monitor for new media / new source subs and act automatically | The "fire and forget" promise of the *arr stack; polling or webhook-driven | MEDIUM | Webhook in (Sonarr/Radarr "On Import"/"On Download" connect) is the clean trigger; polling fallback for missed events. Detect: has source sub, lacks good `vi` sub |
| Parse & write SRT preserving timing + line structure | Universal baseline format; broken timing = unusable subs | LOW | Index, timecodes, and segmentation must round-trip exactly. Translate text only, never touch timestamps |
| User-provided OpenAI-compatible endpoint (base URL / model / key) | Per PROJECT constraint; users bring their own LLM | LOW | Standard `openai` SDK pattern; must tolerate non-OpenAI quirks (missing fields, different tokenizers) |
| Batching / chunking within token limits | Subtitle files exceed context windows; naive whole-file calls fail | MEDIUM | Industry default ~30 lines/batch (conservative); large-context models handle 150+. Keep prompt+context ≤~70% of context window. **Batch boundaries must not split a sentence/scene** |
| Surrounding-line context per batch | Independent-line translation loses coherence & antecedents (who "she" is) | MEDIUM | Send N lines before/after the batch as read-only context; standard in llm-subtrans/subtitle-translator |
| Glossary / terminology consistency (names, places, jargon) | The #1 consistency feature in every CAT tool and LLM-sub tool; without it terms drift | MEDIUM | Term base = source term → fixed target rendering, injected into prompt. This is the *generic* half of the Series Bible |
| Preserve ASS/SSA styling, tags, fonts, positioning | Anime/fansub audience; stripping `{\an8}`, `\pos`, override tags corrupts the file | HIGH | Must translate only dialogue text inside events, leaving inline override blocks `{...}`, drawing commands, and the `[Script Info]`/`[V4+ Styles]` headers untouched. Easy to get subtly wrong |
| VTT support | Web/Jellyfin-native format | LOW | Similar to SRT; cue settings/positioning must round-trip |
| Dockerized long-running service + web UI | Matches *arr deployment expectations; users compose it alongside the stack | MEDIUM | Single container, persistent volume for DB/Series Bibles, env-or-UI config, exposed port |
| Queue + history + logs in the UI | Every *arr tool has Activity/Queue + History + per-item failure reason; users expect to see what's processing, what failed, and why | MEDIUM | Sonarr's model: Queue (in-flight), History (done/failed with reason). Per-job log access is expected |
| Retry / re-run a failed or rejected translation | LLM calls fail (rate limits, timeouts, bad output); manual retry is baseline | LOW-MEDIUM | Idempotent re-run; should re-use existing Series Bible state |
| Idempotency / "don't re-translate what's done" | Re-processing wastes calls and risks overwriting good output | MEDIUM | Track per-episode translation state + source-sub hash; skip if up-to-date |

### Differentiators (Competitive Advantage)

This is where Trezarr wins. **The Series Bible consistency engine is the entire moat** — no existing tool does series-persistent relational consistency, and none is Vietnamese-aware.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Persistent per-series "Series Bible"** carried across all episodes | The core innovation: consistency that spans S01E01→finale, which every batch-only tool fundamentally cannot do | HIGH | Persistent store (DB row/JSON per series) loaded as context for every episode and updated after each. This is the spine everything else hangs from |
| **Directed Address Map** (per ordered character pair: self-term + address-term) | Encodes the Vietnamese pronoun engine — `John→Mary: self=anh, address=em`. This is *the* thing flat MT cannot represent | HIGH | Directed (A→B ≠ B→A), per-pair. The hard part: choosing pairs from gender/age/role/relationship, and asymmetry (one says `em`, other says `anh`) |
| **Speaker + addressee attribution per line** (LLM-inferred) | Subtitles carry no speaker labels; you cannot pick a pronoun without knowing who→whom. Frontier-model inference is the quality source | HIGH | Infer from dialogue content, turn-taking, vocatives (names called out), and Bible. Wrong attribution = wrong pronoun = the exact failure to avoid. Confidence-flagging on low-certainty lines is valuable |
| **Relationship evolution tracking across episodes** | Pronoun pairs legitimately change (strangers→lovers→`anh/em`, enemies→`mày/tao`). Static maps drift wrong over a series | HIGH | Episode-marked transitions in the Address Map; needs the LLM analysis pass to detect relationship shifts and version them |
| **Register/tone per series, grounded in media metadata** | Formal wuxia historical vs casual sitcom demand different Vietnamese registers; metadata (genre/plot/era) grounds the choice | MEDIUM | Pull genre/plot/year/cast from Sonarr/Radarr/TMDB; set register that biases vocabulary & politeness across the whole series |
| **Editable Series Bible (human override valve)** | Auto-built but user-correctable; corrections lock & propagate forward. The single human touchpoint that makes blind automation trustworthy | MEDIUM-HIGH | UI to view/edit Characters, Address Map, Term Dictionary, Register. "Locked" fields must survive re-analysis. This is what turns "MT slop" into "replaces a translator" |
| **Source-language selection by relational fidelity** | When multiple source subs exist, prefer the language that *encodes* the relationship info Vietnamese needs (zh/ko/ja/th over en, which flattens to I/you) | MEDIUM | Ranking policy: relational-rich source languages > English > others. Falls back to whatever exists. A genuinely novel selection heuristic |
| **Two-pass pipeline (analyze → translate)** | Pass 1 reads the *whole* file + metadata to build/update the Bible before any line is translated, enabling global consistency | HIGH | Pass 1: extract characters, relationships, terms, register. Pass 2: translate with the assembled Bible + surrounding lines. llm-subtrans only does batch-accumulated maps — full-file pre-analysis is stronger |
| **LLM self-review / critique pass** | Model re-reads its own output for pronoun/term/register consistency before finalizing — what earns blind trust | HIGH | Third pass over translated output checking Bible adherence; correct violations. Cost is acceptable per PROJECT (user's own endpoint). The "good enough to not need a human" lever |
| **Character name romanization policy** | Keep names in original Latin form consistently (per PROJECT); avoid translating/transliterating names inconsistently | LOW-MEDIUM | Names live in the Term Dictionary as fixed renderings; prevents "John/Giôn/Giăng" drift |
| **Per-series settings** (override source-lang preference, register, model) | Power users want to tune individual shows | MEDIUM | Series-scoped config overriding global defaults |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Re-downloading / acquiring source subtitles | "Make it one tool" | Bazarr already does this seamlessly; duplicating it is scope creep and competes with the thing you integrate with (explicitly rejected in PROJECT) | Read Bazarr's existing source subs via API; only translate |
| Targeting many output languages | "Why only Vietnamese?" | Vietnamese relational consistency is the hard problem and the moat; multi-target dilutes the engine and the prompts/Bible schema | Stay Vietnamese-only; the design *is* the value |
| Bundling/hosting a local model | "Make it work out of the box" | Hosting models = ops burden, GPU requirements, version churn, support load — and PROJECT scopes it out | User brings OpenAI-compatible endpoint; document recommended models |
| Full human review/correction *workflow* UI (segment-by-segment approve/edit) | "Translators want to QA every line" | Contradicts the "fully automated, no human in loop" mission; a line-editor turns it into a CAT tool, not an automation service | The editable **Series Bible** is the only human touchpoint — fix the *rules*, not every line; corrections propagate |
| Cost / token budgeting & quota dashboards | "Track my spend" | User runs their own endpoint; per-call cost isn't a v1 concern (PROJECT) and it's a big UI surface | Omit for v1; maybe surface raw call/token counts in logs only |
| Burning subtitles into video / re-muxing | "Embed it in the file" | Destroys the sidecar model media servers rely on, heavy (ffmpeg transcode), risks the original media | Always sidecar; let the media server overlay |
| Real-time / streaming translation | "Translate as it plays" | Subtitles are static files; the whole consistency engine needs the *whole file* up front | Batch, file-at-a-time, two-pass — accuracy over latency |
| Auto-syncing/re-timing subtitles | "Fix out-of-sync subs" | That's Bazarr/sub-sync's job; mixing timing correction with translation invites breaking the timing you must preserve | Preserve source timing 1:1; defer sync to Bazarr |
| Generating subs from audio (ASR/Whisper) | "Make subs when none exist" | Different problem (speech→text), heavy compute, out of mission (you translate existing subs) | Require an existing source sub; ASR is a separate v2+ idea at most |

## Feature Dependencies

```
Sidecar output (correct naming)
    └──requires──> Sonarr/Radarr API (paths, basenames, episode identity)

Monitor & act automatically
    └──requires──> Sonarr/Radarr API + Bazarr API (what exists / what's missing)
    └──requires──> Idempotency / translation-state tracking

Translate line-by-line (Pass 2)
    └──requires──> Series Bible (Pass 1 analysis)
                       └──requires──> Source-language selection (which sub feeds Pass 1)
                       └──enhanced-by──> Media metadata (Sonarr/Radarr/TMDB) for Register
    └──requires──> Speaker/addressee attribution
                       └──requires──> Address Map (in Series Bible)
    └──requires──> Batching + surrounding-line context

Self-review pass
    └──requires──> Pass 2 output + Series Bible (to check adherence)

Relationship evolution tracking
    └──requires──> Persistent Series Bible (cross-episode state)
    └──requires──> Pass 1 analysis run per episode (detect shifts)

Editable Series Bible UI
    └──requires──> Series Bible store
    └──enhances──> every translation pass (locked corrections propagate)

ASS/SSA styling preservation
    └──independent of consistency engine (parser-level concern)

Per-series settings ──enhances──> source selection, register, model choice

Burn-in / ASR / re-sync ──conflicts──> sidecar + preserve-timing model
```

### Dependency Notes

- **Pass 2 requires the Series Bible (Pass 1):** you cannot choose a pronoun without the Address Map; the analysis pass must complete (and merge with prior-episode state) before any line is translated. This forces phase ordering: parsing → Bible schema/store → Pass 1 → Pass 2 → self-review.
- **Attribution requires the Address Map, and the Address Map is only useful with attribution:** they are co-dependent — neither delivers value alone. Build them together.
- **Source-language selection feeds Pass 1:** the *choice* of which source sub to analyze changes how much relational info is available; it must run before analysis, not after.
- **Editable Bible depends on a stable Bible schema:** the persistence model and schema must be designed before the editing UI, and "locked" semantics must be a first-class field, not bolted on.
- **Idempotency/state gates the monitor loop:** automatic monitoring without "already done" tracking causes re-translation storms.
- **ASS/SSA preservation is orthogonal:** it lives in the parser layer and can be developed in parallel with the consistency engine; do not entangle them.

## MVP Definition

### Launch With (v1)

The thinnest slice that proves the core thesis: *automated, series-consistent, relationally-correct Vietnamese subs in the *arr stack.*

- [ ] Sonarr/Radarr + Bazarr API connection + path mapping — without integration it's just a CLI script, not an *arr companion
- [ ] Monitor + auto-act on (has source sub, no `vi` sub) — the automation promise
- [ ] SRT parse/write preserving timing — universal baseline
- [ ] Sidecar output with correct `Show.S01E01.vi.srt` naming, atomic write — the delivery mechanism
- [ ] OpenAI-compatible endpoint config — the engine plumbing
- [ ] Batching + surrounding-line context — required for any coherent output
- [ ] Two-pass: full-file analysis → Series Bible → contextual translation — the core thesis
- [ ] Series Bible: Characters + directed Address Map + Term Dictionary + Register — the consistency engine
- [ ] Speaker/addressee attribution → correct pronoun pair — the Vietnamese differentiator
- [ ] Persistent Bible carried across episodes — what makes it *series* consistency
- [ ] Editable Series Bible (view + correct + lock + propagate) — the human override that earns blind trust
- [ ] Web UI: config + queue + history + logs + retry — the *arr-citizen baseline
- [ ] Dockerized service — the deployment expectation

### Add After Validation (v1.x)

- [ ] LLM self-review/critique pass — trigger: once base translation quality is measured and the consistency engine is stable (highest-cost, highest-polish lever)
- [ ] Source-language selection by relational fidelity — trigger: when users have multi-source libraries (East-Asian content); single-source works without it
- [ ] ASS/SSA styling preservation — trigger: anime/fansub adoption; SRT covers the majority first
- [ ] Relationship evolution tracking (episode-marked transitions) — trigger: after static Address Map is proven; needs analysis-pass maturity
- [ ] Per-series settings overrides — trigger: power-user demand
- [ ] VTT support — trigger: Jellyfin/web users requesting it
- [ ] Webhook-driven triggering (vs polling) — trigger: lower-latency processing once polling baseline works

### Future Consideration (v2+)

- [ ] Confidence-flagging of low-certainty attribution lines in the UI — defer: needs attribution maturity + UI surface; nice trust signal
- [ ] Multi-instance / multiple Sonarr-Radarr support — defer: most self-hosters run one of each
- [ ] Notifications (Discord/Telegram/ntfy on completion/failure) — defer: matches *arr ecosystem norms but not core value
- [ ] Glossary import/export & sharing between users — defer: community feature once Bibles are valuable

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Sonarr/Radarr/Bazarr API + path mapping | HIGH | MEDIUM | P1 |
| Sidecar naming + atomic write | HIGH | LOW | P1 |
| Monitor + auto-act + idempotency | HIGH | MEDIUM | P1 |
| SRT parse/write preserve timing | HIGH | LOW | P1 |
| OpenAI-compatible endpoint | HIGH | LOW | P1 |
| Batching + surrounding-line context | HIGH | MEDIUM | P1 |
| Two-pass analyze→translate | HIGH | HIGH | P1 |
| Series Bible (Chars/Address Map/Terms/Register) | HIGH | HIGH | P1 |
| Speaker/addressee attribution | HIGH | HIGH | P1 |
| Persistent cross-episode Bible | HIGH | MEDIUM | P1 |
| Editable Series Bible UI | HIGH | MEDIUM-HIGH | P1 |
| Web UI: queue/history/logs/retry | HIGH | MEDIUM | P1 |
| Dockerized service | HIGH | MEDIUM | P1 |
| LLM self-review pass | HIGH | HIGH | P2 |
| Source-language fidelity selection | MEDIUM-HIGH | MEDIUM | P2 |
| ASS/SSA preservation | MEDIUM | HIGH | P2 |
| Relationship evolution tracking | MEDIUM-HIGH | HIGH | P2 |
| Per-series settings | MEDIUM | MEDIUM | P2 |
| VTT support | MEDIUM | LOW | P2 |
| Webhook triggering | MEDIUM | LOW-MEDIUM | P2 |
| Attribution confidence flags | MEDIUM | MEDIUM | P3 |
| Notifications | LOW-MEDIUM | LOW | P3 |
| Glossary sharing | LOW | MEDIUM | P3 |

## Competitor Feature Analysis

| Feature | Bazarr (+ translate hacks) | llm-subtrans / subtitle-translator | Our Approach (Trezarr) |
|---------|----------------------------|-------------------------------------|------------------------|
| *arr integration | Native (Sonarr/Radarr) | None (CLI/desktop) | Native API + sidecar, one layer up |
| Translation engine | Flat NMT (Google/Libre/DeepL) | LLM, batch + accumulated maps | LLM, two-pass + self-review |
| Cross-line context | None | Surrounding lines per batch | Surrounding lines + full-file Bible |
| Cross-episode consistency | None | None | **Persistent Series Bible** |
| Relationship/pronoun modeling | None | Generic terminology map | **Directed Address Map + attribution** |
| Vietnamese awareness | None | None (generic) | **Entire focus** |
| Source-language selection | Manual priority list | N/A | **Relational-fidelity ranking** |
| Term consistency | None | Name lists / substitutions | Term Dictionary in Bible (editable, locked) |
| Format preservation | Passthrough | SRT/ASS/VTT preserve | SRT (v1) → ASS/VTT, preserve timing/tags |
| Human override | N/A | Edit instructions/summaries | **Editable Series Bible (rule-level)** |
| Deployment | Docker + web UI | CLI / desktop GUI | Docker + web UI (*arr-style) |

## Sources

- [Bazarr Wiki — Settings](https://wiki.bazarr.media/Additional-Configuration/Settings/) and [Setup Guide](https://wiki.bazarr.media/Getting-Started/Setup-Guide/) (HIGH — official)
- [Bazarr feature request: Auto translation (rejected/not on roadmap)](https://bazarr.featureupvote.com/suggestions/126221/auto-translation-feature) and [Automatically translate as last resort](https://bazarr.featureupvote.com/suggestions/283561/automatically-translate-subtitles-as-last-resort) (HIGH)
- [anast20sm/Bazarr_AutoTranslate (community translate-on-import hack)](https://github.com/anast20sm/Bazarr_AutoTranslate) (MEDIUM)
- [machinewrapped/llm-subtrans (leading LLM subtitle tool)](https://github.com/machinewrapped/llm-subtrans) (HIGH — feature set verified)
- [rockbenben/subtitle-translator](https://github.com/rockbenben/subtitle-translator), [Cerlancism/chatgpt-subtitle-translator](https://github.com/Cerlancism/chatgpt-subtitle-translator), [pysubtrans](https://pypi.org/project/pysubtrans/) (MEDIUM-HIGH — batching/context norms)
- [AnimeSubs LLM Subtitle Translator (glossary-in-prompt, ASS positioning)](https://dev.to/enrell/animesubs-an-llm-subtitle-translator-4eek) (MEDIUM)
- [How Subtitles Are Generated Using LLMs (sync/merge pitfalls)](https://apoorvamittal.substack.com/p/how-subtitles-are-generated-using) (MEDIUM)
- [Enhancing Entertainment Translation using Adaptive Context, Style and LLMs (arXiv)](https://arxiv.org/pdf/2412.20440) (MEDIUM — context-aware dialogue translation)
- [Vietnamese pronouns — Wikipedia](https://en.wikipedia.org/wiki/Vietnamese_pronouns), [Vietnamese honorifics — Wikipedia](https://en.wikipedia.org/wiki/Vietnamese_honorifics), [Migaku pronoun guide](https://migaku.com/blog/language-fun/vietnamese-personal-pronouns-guide), [Vietnameselab anh/chị/em guide](https://vietnameselab.com/blog/thanthu-xungho) (HIGH — linguistic facts)
- [Terminology management in CAT tools / term base consistency (ResearchGate, Smartcat, Transifex)](https://help.smartcat.com/getting-started/6987550190610-Leveraging-Smartcat-linguistic-assets) (HIGH — TMS term-base model)
- [Sonarr/Radarr webhook + language in notifications (Sonarr #7421, Radarr #10733)](https://github.com/Sonarr/Sonarr/issues/7421), [qudiqudi/langarr](https://github.com/qudiqudi/langarr) (HIGH — integration patterns)
- [Plex local subtitles naming](https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/), [Jellyfin external subtitle naming #7057](https://github.com/jellyfin/jellyfin/issues/7057), [Jellyfin subtitles + Bazarr guide](https://jellywatch.app/blog/jellyfin-subtitles-complete-guide-2026) (HIGH — sidecar conventions)
- [Kha-kis/arr-dashboard (queue/history/retry UI conventions)](https://github.com/Kha-kis/arr-dashboard), [Homarr](https://www.blog.brightcoding.dev/2025/07/30/homarr-the-modern-dashboard-for-taming-your-self-hosted-universe) (MEDIUM — UX norms)

---
*Feature research for: automated Vietnamese subtitle translation / *arr-stack companion*
*Researched: 2026-05-31*
