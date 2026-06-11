"""12-check pre-write validation gate for translated SubDocs (D-16, D-17).

Design decisions honoured:
  D-16  Gate every write on all 7 structural checks (fail-fast).
  D-17  Untranslated-line detection is cheap, layered, and low-false-reject:
        per-line allowlist (punctuation/digits/symbols) + per-file Vietnamese
        diacritic ratio threshold.  No heavy NLP dependency.
  D-18  Failure raises GateError so the engine can quarantine; gate never
        silently swallows a structural error.

The gate deliberately does NOT check Vietnamese quality (pronoun choices,
semantic correctness) — that is the responsibility of Phases 4–6.  It checks
structural integrity only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from trezarr.subtitles.model import SubDoc
from trezarr.translate._timecode import tc_to_ms as _tc_to_ms

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

# Vietnamese diacritic detection — two Unicode ranges combined:
#   U+1E00–U+1EFF: Latin Extended Additional (ổ, ợ, ẫ, ộ, ề, ể, ạ, ặ …)
#   U+01A0/U+01A1: Ơ/ơ ("o horn") — uniquely Vietnamese, not in French/Spanish
#   U+01AF/U+01B0: Ư/ư ("u horn") — uniquely Vietnamese, not in French/Spanish
# French/Spanish use only U+00C0–U+00FF (e.g. é, à, ü) which do NOT overlap.
VN_DIACRITIC_RE = re.compile(r"[Ḁ-ỿƠơƯư]")

# Lines matching this pattern are "legitimately unchanged" — all punctuation,
# digits, whitespace, or common musical/symbolic characters.  Excluded from
# the Vietnamese diacritic ratio denominator (D-17).
ALLOWLIST_RE = re.compile(r"^[\W\d\s♪♫…\.]+$")

# Lines that consist entirely of sentinel placeholder tokens after tag extraction
# have no natural-language content and must not count toward the VI diacritic ratio
# denominator.  A pure-tag cue (e.g. "{\an8}{\pos(960,50)}") becomes "<<T0>><<T1>>"
# after sentinel extraction — SENTINEL_ONLY_RE matches that form.
# Anchored (^ and $) and applied per-line to short strings; no catastrophic
# backtracking path (T-09-03-C, ASVS L1 V5).
SENTINEL_ONLY_RE = re.compile(r"^(<<T\d+>>\s*)*$")

# Backstop check for orphan sentinel tokens that were not reinserted (D-12/D-16 check 6)
SENTINEL_RE = re.compile(r"<<T\d+>>")

# Pass-4 review-prompt scaffolding signature. build_review_prompt emits each line
# as "[N] (source: <orig>) <vi>"; a weak model sometimes echoes that back as its
# "correction". Case-insensitive + whitespace-tolerant after "(" so a recased or
# spaced echo ("(Source:", "( source:") is still caught. Shared by the engine's
# Pass-4 splice guard and gate Check 8 so the two defense layers never drift.
# (A *translated* scaffold token, e.g. "(nguồn:", is residual risk — not matched.)
REVIEW_SCAFFOLD_RE = re.compile(r"\(\s*source\s*:", re.IGNORECASE)

# Pass-3 attribution-hint scaffolding signature. build_translate_prompt injects the
# per-line pronoun hint as a LEADING parenthetical: "[N] (speaker says: <self>; addresses
# as: <addr>) <text>". A weak model can echo that note into the cue — the same
# scaffolding-leak class as the Pass-4 "(source:" leak (260604-gza/hp2); the Ep-142 audit
# saw "(speaker says: tại hạ; addresses as: Mai cô nương)" ship in 7 on-screen cues, and
# the H4 paren-preserve rule (engine.py) *raises* that echo risk. Shared by gate Check 8 as
# the defense-in-depth backstop: a leaked hint quarantines, never ships. Anchored on "(" +
# the English label, whitespace/case-tolerant — mirrors REVIEW_SCAFFOLD_RE. (A
# *translated*-label echo is caught by VN_HINT_SCAFFOLD_RE — see sibling constant below.)
HINT_SCAFFOLD_RE = re.compile(r"\(\s*speaker\s+says\s*:", re.IGNORECASE)

# 260612-7kt (Finding 1 / D-01) — Vietnamese-label variant of the Pass-3 pronoun-hint
# scaffolding leak.  E143 cue 148 incident: a weak model translated the English labels
# 'speaker says' → 'nói' and 'addresses as' → 'xưng hô', producing a parenthetical like
# '(tại hạ nói: tại hạ; xưng hô: cô nương)' that evaded both _LEAKED_HINT_RE (engine
# strip) and HINT_SCAFFOLD_RE (Check 8 — anchored to "speaker says:" only).
#
# Discriminating structural signal: the token IMMEDIATELY before ':' is a pronoun-ROLE
# word — either `nói` (says/speaks) or `xưng hô` (form of address).  The mandatory colon
# distinguishes a label structure from a stage direction:
#   "(nói to)"        → NO colon after nói  → stage direction → NOT matched
#   "(nói: ta)"       → colon after nói     → label structure → MATCHED
#   "(xưng hô: muội)" → colon after xưng hô → label structure → MATCHED
#   "(Hồi 01: …)"    → token before ':' is 'Hồi 01', not a role word → NOT matched
#
# Pattern: open paren, optional non-colon chars (e.g. "tại hạ "), then role token, then colon.
# \(\s*             — literal '(' optionally followed by spaces
# (?:[^():]*        — zero or more chars that are not '(' ')' or ':' (the optional "prefix name")
# (?:nói|xưng\s+hô) — the pronoun-role token (case-insensitive covers Nói, XƯNG HÔ, etc.)
# \s*:)             — zero or more spaces then the mandatory colon
# Non-recursive; no alternation with overlapping paths (ASVS L1 V5 — mirrors HINT_SCAFFOLD_RE).
# Sibling to HINT_SCAFFOLD_RE: one for English labels, one for Vietnamese labels; both feed
# the same Check 8 OR condition.  engine.py _LEAKED_VN_HINT_RE is the strip-layer counterpart.
VN_HINT_SCAFFOLD_RE = re.compile(
    r"\(\s*(?:[^():]*(?:nói|xưng\s+hô)\s*:)",
    re.IGNORECASE,
)

# IMP-02b gate-repair directive signature. _repair_failing_cues injects a
# "[CORRECTION REQUIRED] <directive>" instruction into the RULES block of the repair prompt.
# Proven by the codec guardian (2026-06-08): deepseek echoes context-line instructions
# into output cues, and "[CORRECTION REQUIRED]..." passes all 12 existing checks
# (no VI diacritic, not in source tokens, not a known scaffold pattern). This regex
# adds it to Check 8 as a fail-closed backstop — "[CORRECTION REQUIRED]" cannot appear
# in genuine Vietnamese dialogue, so quarantining is safe and has zero false positives.
# Justification mirrors HINT_SCAFFOLD_RE: same leak class (English internal machinery →
# on-screen sidecar), same defense tier (gate backstop after the parse-layer strip).
CORRECTION_DIRECTIVE_RE = re.compile(r"\[\s*CORRECTION\s+REQUIRED\s*\]", re.IGNORECASE)

# R4 fix (Check 8): attribution meta-commentary that bypasses Check 10/12 diacritic skips
# (audit 260611-l74, 260611-ru6). Two verbatim E03 leak classes:
#   Class 1: '(Correct; "tôi"→"anh" is the right pair; no violation)' — E03 cue 146.
#            Check 12 SKIPPED: parenthetical contains VN diacritics (tôi, anh) → Latin-diacritic
#            guard passes it as "Vietnamese dialogue". Check 10 SKIPPED: cue has VN diacritics.
#   Class 2: '(No violation)' — E03 cue 147.
#            Check 10 SKIPPED: cue has VN diacritics (Tôi sẽ đi). Check 12 doesn't fire
#            (no possessive /'s, no honorific-cap bigram).
# Pattern: anchored to the OPENING of a parenthetical + English review/attribution keyword.
# "no violation" and "correct;" CANNOT appear in genuine Vietnamese dialogue — zero false positives.
# Case-insensitive; covers "No violation", "Correct; ...", "correct;...", "no violation".
# Non-recursive alternation — no ReDoS path (ASVS L1 V5 compliant, T-ru6-01/T-ru6-03).
ATTRIBUTION_META_RE = re.compile(r"\(\s*(?:no\s+violation|correct\s*;)", re.IGNORECASE)

# R4 fix (Check 6): unclosed/orphan sentinel — <<TN without closing >> (260611-ru6).
# E03 cue 459 ships as raw '<<T153' (bytes 3c3c 5431 3533 — NOT HTML-escaped, confirmed
# in 03_verdicts.md). SENTINEL_RE = r"<<T\d+>>" requires the closing '>>' and so
# misses '<<T153'. SENTINEL_ONLY_RE also requires '>>'. Check 10 skipped ('T153' has
# only 1 ASCII letter, so ASCII_WORD_RE finds 0 tokens >= 2 letters).
#
# The (?!>>) lookahead does NOT prevent matching the closed form '<<T153>>'.
# Due to greedy-then-backtrack: \d+ first consumes '153', lookahead sees '>>' → fails;
# engine backtracks to \d+='15', lookahead sees '3' (not '>>') → succeeds → matches
# '<<T15' inside '<<T153>>'. So UNCLOSED_SENTINEL_RE DOES fire on the closed form.
# This is intentional belt-and-suspenders: SENTINEL_RE already catches '<<T153>>' via
# Check 6's OR condition, so the double-fire yields the same GateError(check=6).
# The lookahead provides no exclusion guarantee for closed forms — its actual effect is
# only to reduce the match length when backtracking occurs (cosmetically shorter match,
# same verdict). Closed orphans are already and definitively caught by SENTINEL_RE.
#
# HTML-escaped form &lt;&lt;TN added as secondary pattern — belt-and-suspenders for any
# proxy or templated output that HTML-escapes angle brackets before reaching validate.py.
# ASVS L1 V5: non-recursive, no alternation with overlapping paths (T-ru6-02/T-ru6-03).
UNCLOSED_SENTINEL_RE = re.compile(r"<<T\d+(?!>>)|&lt;&lt;T\d+")

# ── Per-cue leak detectors (audit B2/H4/H5/M3) ──────────────────────────────────
# The per-FILE diacritic average (Check 3) cannot see a single bad cue — ~40 short
# Vietnamese cues average ~40 raw passthroughs away.  Checks 9-12 inspect each cue.

# B2/M3 fix (Check 9): any CJK Unified / CJK ext-A / compatibility / fullwidth, Hangul
# syllables + Jamo, or Hiragana/Katakana codepoint in a translated cue is a hard leak
# (an untranslated Chinese/Korean/Japanese source fragment).  Vietnamese never uses any
# of these scripts, so zero false positives by construction.  Anchorless single-char
# search — no backtracking path (ASVS L1 V5).
CJK_LEAK_RE = re.compile(
    "["
    "一-鿿"  # CJK Unified Ideographs           U+4E00–U+9FFF
    "㐀-䶿"  # CJK Extension A                  U+3400–U+4DBF
    "豈-﫿"  # CJK Compatibility Ideographs     U+F900–U+FAFF
    "＀-￯"  # Halfwidth and Fullwidth Forms    U+FF00–U+FFEF
    "가-힣"  # Hangul Syllables                 U+AC00–U+D7A3
    "ᄀ-ᇿ"  # Hangul Jamo                      U+1100–U+11FF
    "぀-ヿ"  # Hiragana + Katakana              U+3040–U+30FF
    "]"
)

# B2/H5 fix (Check 10): an ASCII alphabetic word token (>=2 letters). Used to decide
# whether a no-diacritic cue is a verbatim source pass-through (every token also present
# in the corresponding source cue). One-letter runs are ignored so a stray ASCII letter
# inside a Vietnamese word (e.g. the 'L' in 'Là') never counts as a token.
ASCII_WORD_RE = re.compile(r"[A-Za-z]{2,}")

# MEDIUM-3 fix (Check 10 false-positive guard): laughter / onomatopoeia / interjections are
# legitimately untranslated and identical to source ("Ha ha ha", "Hmm", "Uh oh"). They are
# all-ASCII, no-diacritic, and verbatim-in-source, so Check 10 would quarantine the whole file.
# A cue made of only these tokens (or a single repeated token) is exempt.
# NOTE: kept to a CLOSED set of non-lexical syllables on purpose. A blanket "any repeated
# token" exemption was rejected (adversarial-verify): it would let real repeated English
# imperatives escape — "Go go", "No no", "Run run", "Stop stop" are repeated tokens but ARE
# untranslated content that Check 10 must still catch. Laughter ("Ha ha ha", "Ho ho ho") is
# covered because its syllables are listed here, not because it repeats.
_INTERJECTION_TOKENS: frozenset[str] = frozenset(
    {
        "ha",
        "haha",
        "hahaha",
        "hah",
        "heh",
        "hehe",
        "hmm",
        "hm",
        "mmm",
        "mm",
        "uh",
        "uhh",
        "ah",
        "ahh",
        "oh",
        "ohh",
        "eh",
        "ehh",
        "oho",
        "huh",
        "hum",
        "wow",
        "ooh",
        "aha",
        "hey",
        "yay",
        "ow",
        "ugh",
        "phew",
        "psst",
        "shh",
        # laughter / non-lexical onomatopoeia syllables (closed set, never real English words):
        "ho",
        "hoho",
        "hohoho",
        "hee",
        "heehee",
        "haw",
        "har",
        "tee",
        "teehee",
        "woo",
        "yoo",
        "boo",
        "grr",
        "brr",
        "argh",
        "aah",
        "hah",
    }
)

# B2/H5 fix (Check 11): an English honorific immediately followed by a capitalized name
# ("Mr. Han", "Elder Zhou", "Miss Mei", "Brother Han") is an untranslated address form
# leaking through. Vietnamese renders these as kinship/honorific words (huynh / trưởng
# lão / cô nương / …), never "Elder Name", so the bigram itself is a reliable defect.
HONORIFIC_CAPNAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Sir|Elder|Brother|Sister|Master|Lord|Lady)\b\.?\s+[A-Z][a-z]+"
)

# H4 fix (Check 12 support): broad Latin-diacritic detector. DELIBERATELY WIDER than
# VN_DIACRITIC_RE — it includes U+00C0–U+024F (à á â ê ô ì í ò ó ù ú ý … that Vietnamese
# shares with French/Spanish) plus U+1E00–U+1EFF plus combining marks. Used ONLY to
# recognize that a parenthetical carries Vietnamese (any accented Latin) so a legitimate
# Vietnamese parenthetical is never flagged as an English gloss. (Check 3 still uses the
# NARROW VN_DIACRITIC_RE for its file-wide ratio — these two are intentionally distinct.)
LATIN_DIACRITIC_RE = re.compile(r"[À-ɏḀ-ỿ̀-ͯ]")

# H4 fix (Check 12): a parenthetical whose inner text has ASCII letters but no Latin
# diacritic and is long enough to be an English gloss. Captures the inner text so the
# check can apply the diacritic/length/space-or-possessive filters; flags
# "(Miss Mei's brother)" / "(X's brother)" but not "(!)"/"(?)"/"(A)" nor a Vietnamese
# parenthetical (which carries diacritics). [^()] inner class is non-recursive — no
# catastrophic backtracking (ASVS L1 V5).
GLOSS_PAREN_RE = re.compile(r"\(([^()]*[A-Za-z][^()]*)\)")

# ── Credit / fansub attribution detector (Check 9 narrow exemption) ──────────
# A fansub credit/attribution cue whose only untranslatable content is a short
# CJK proper-name handle (e.g. "虫二") must not quarantine the entire file.
# The exemption fires ONLY when BOTH conditions hold:
#   1. A credit/attribution keyword appears in the source OR translated cue text.
#   2. The total CJK/Hangul/Kana codepoint count in the TRANSLATED text is ≤ the
#      threshold — a fully-untranslated dialogue body has many CJK chars and exceeds
#      this threshold, so it still quarantines.
# Conservative-by-design: a credit line left fully untranslated (many CJK chars) still
# quarantines — that signals a real translation failure, not a short proper-name handle.
#
# WHY TWO REGEXES (CREDIT_SRC_RE and CREDIT_TRN_RE):
# The translated output is Vietnamese. A CJK token appearing in trn_text is always the
# leak itself — never a credit keyword. Matching the Chinese fansub source markers
# (翻译, 校对, 字幕組, etc.) against trn_text caused the "self-exempt" class of bug:
# a model that leaked "翻译" into the translation would self-satisfy the credit keyword
# condition and escape quarantine even when the source had no credit keyword at all.
# Fix: CJK/source-language markers are matched ONLY against src_text (CREDIT_SRC_RE).
# trn_text is matched ONLY against Vietnamese (and optionally English) markers
# (CREDIT_TRN_RE). Any CJK that appears in trn_text is therefore treated exclusively as
# a potential leak character, counted by CJK_LEAK_RE.findall. (260608-t53 final round)
#
# English signals REQUIRE the attribution form "... by" with word boundaries so bare
# dialogue words (e.g. "subtitle", "subtitles", "timing") cannot trigger a false exemption.
# Bare "subtitle"/"subtitles" and "timing" are intentionally excluded — they collide with
# ordinary dialogue (codec-guardian HIGH finding, 260608-t53).
# Word boundaries (\b) add no backtracking (ASVS L1 V5) — they are zero-width assertions.
#
# Chinese source markers: matched against src_text only (CREDIT_SRC_RE). The full set
# including bare 字幕 (safe on the source side — source text is not Vietnamese) plus all
# compound forms. NEVER matched against trn_text; a Vietnamese output will not contain
# these unless the model leaked them, which is precisely what Check 9 must catch.
#
# Vietnamese prefixes: matched against trn_text only (CREDIT_TRN_RE). Language-specific;
# no dialogue collision risk. Also appears in CREDIT_SRC_RE so source-language VI credit
# cues are still caught when the subtitle is already Vietnamese-sourced.

# Matched against src_text: English "... by" attribution forms + Vietnamese credit prefixes
# + Chinese fansub source markers (翻译, 校对, 字幕組, etc.).
# CJK markers are SOURCE-SIDE ONLY — see WHY TWO REGEXES comment above.
CREDIT_SRC_RE = re.compile(
    r"\b(?:translated|translation|subtitled|subtitles|subbed|sub|synced|encoded|ripped) by\b"
    r"|dịch bởi|phụ đề|biên dịch|người dịch|hiệu đính|vietsub|dịch thuật"
    r"|字幕組|字幕组|字幕|翻譯|翻译|校對|校对|時間軸|时间轴|壓制|压制|后期",
    re.IGNORECASE,
)

# Matched against trn_text: Vietnamese credit prefixes + English "... by" attribution forms.
# NO CJK markers — the translated output is Vietnamese; any CJK in trn_text is the leak,
# not a keyword. (260608-t53 final round)
CREDIT_TRN_RE = re.compile(
    r"\b(?:translated|translation|subtitled|subtitles|subbed|sub|synced|encoded|ripped) by\b"
    r"|dịch bởi|phụ đề|biên dịch|người dịch|hiệu đính|vietsub|dịch thuật",
    re.IGNORECASE,
)

# Maximum number of CJK/Hangul/Kana codepoints allowed in the translated text for the
# credit exemption to fire.  A 2-char fansub handle like "虫二" passes (count=2 ≤ 8).
# A fully-untranslated body like "字幕翻译制作团队制作感谢" (12 chars) exceeds this
# and still quarantines, which is the desired conservative-by-design behaviour.
CJK_CREDIT_EXEMPT_MAX_CJK: int = 8


def is_credit_fansub_cue(src_text: str, trn_text: str) -> bool:
    """Return True iff this cue is a narrowly-detected fansub credit/attribution line.

    Both conditions must hold:
    1. CREDIT_SRC_RE matches src_text OR CREDIT_TRN_RE matches trn_text.
       CJK/source-language markers are checked source-side only (CREDIT_SRC_RE).
       trn_text is checked only against Vietnamese/English markers (CREDIT_TRN_RE).
       Rationale: the translated output is Vietnamese — a CJK token in trn_text is
       always the leak itself, never a credit keyword. (260608-t53 final round)
    2. The total CJK/Hangul/Kana codepoint count in trn_text is ≤ CJK_CREDIT_EXEMPT_MAX_CJK
       (short proper-name handle, not a fully-untranslated body).

    Uses CJK_LEAK_RE.findall to reuse the existing character-class definition without
    duplicating the Unicode range. Anchorless match; no backtracking path (ASVS L1 V5).
    """
    if not CREDIT_SRC_RE.search(src_text) and not CREDIT_TRN_RE.search(trn_text):
        return False
    return len(CJK_LEAK_RE.findall(trn_text)) <= CJK_CREDIT_EXEMPT_MAX_CJK


@dataclass
class GateFailure:
    """Structured description of a validation gate failure.

    Attributes:
        check:           Check number (1–12) that failed.
        reason:          Human-readable failure description.
        failing_indices: Optional list of SubLine indices involved in the failure.
    """

    check: int
    reason: str
    failing_indices: list[int] | None = field(default=None)


class GateError(Exception):
    """Raised by validate_subdoc() when any of the 12 gate checks fails.

    Attributes:
        failure: The GateFailure instance describing the failed check.
    """

    def __init__(self, failure: GateFailure) -> None:
        self.failure = failure
        super().__init__(failure.reason)


def _check_untranslated(
    translated: SubDoc,
    source: SubDoc,
    settings: "TrezarrSettings",
) -> None:
    """Check 3: No untranslated lines (D-17).

    Raises GateError(GateFailure(3, ...)) if the ratio of translatable lines
    containing Vietnamese diacritics falls below settings.translate_vi_diacritic_ratio.

    A line is "translatable" if it is not on the allowlist (i.e. not all-punctuation/
    digits/symbols).  Allowlisted lines are excluded from both numerator and denominator.
    """
    translatable_indices = []
    vi_count = 0

    for i, (trn_line, src_line) in enumerate(zip(translated.lines, source.lines)):
        # D-99/D-98: opaque pass-through cues (karaoke, drawing) — intentionally
        # untranslated.  SubLine.raw is set by the codec at parse time to signal
        # verbatim write-back.  These cues must never count toward the VI ratio.
        if trn_line.raw is not None:
            continue
        text = trn_line.text.strip()
        if not text:
            continue  # caught by check 2 before this; defensive skip
        if ALLOWLIST_RE.match(text):
            continue  # legitimately unchanged — excluded from ratio
        if SENTINEL_ONLY_RE.match(text):
            continue  # pure-tag cue — no natural language after sentinel extraction
        translatable_indices.append(i)
        if VN_DIACRITIC_RE.search(text):
            vi_count += 1

    if not translatable_indices:
        # All lines are allowlist-exempt — ratio defaults to 1.0 (pass)
        return

    ratio = vi_count / len(translatable_indices)
    if ratio < settings.translate_vi_diacritic_ratio:
        failing = [
            i
            for i in translatable_indices
            if not VN_DIACRITIC_RE.search(translated.lines[i].text.strip())
        ]
        raise GateError(
            GateFailure(
                3,
                f"Vietnamese diacritic ratio {ratio:.2f} < threshold {settings.translate_vi_diacritic_ratio:.2f} "
                f"({vi_count}/{len(translatable_indices)} translatable lines have VI diacritics)",
                failing_indices=failing,
            )
        )


def _check_timing_preserved(translated: SubDoc, source: SubDoc) -> None:
    """Check 5 (codec-fidelity invariant): each translated cue's timing equals its source cue.

    Trezarr's text/timing separation invariant (D-08/D-09) means translation NEVER
    alters timecodes — only ``SubLine.text`` is LLM-mutable; index/start_tc/end_tc are
    immutable by convention.  Check 4 verifies byte-identity of those fields; Check 5
    re-expresses this as a millisecond-level invariant so timing corruption (e.g. a
    codec bug that converts a timecode to milliseconds and back incorrectly) is caught
    even if the *string* round-trips cleanly.

    The check deliberately PASSES for source documents that contain overlapping cues
    (e.g. simultaneous song/dual-speaker lines, karaoke layers).  Such overlaps are a
    legitimate source-file property — translation preserves them verbatim, so they must
    never quarantine an otherwise valid translation.

    Raises GateError(GateFailure(5, ...)) if:
    - Any translated cue's start_ms differs from the corresponding source cue's start_ms, OR
    - Any translated cue's end_ms differs from the corresponding source cue's end_ms.

    Non-positive duration in the SOURCE (start_ms >= end_ms) is NOT flagged here —
    that is a property of the source file, faithfully preserved by translation.  A
    future source-validation step may flag it pre-pipeline; the gate's job is only to
    catch *translation-induced* corruption.

    Args:
        translated: The translated SubDoc produced by the engine.
        source:     The original source SubDoc (used for timing comparison).
    """
    for i, (trn_sl, src_sl) in enumerate(zip(translated.lines, source.lines)):
        trn_start = _tc_to_ms(trn_sl.start_tc)
        trn_end = _tc_to_ms(trn_sl.end_tc)
        src_start = _tc_to_ms(src_sl.start_tc)
        src_end = _tc_to_ms(src_sl.end_tc)

        if trn_start != src_start or trn_end != src_end:
            raise GateError(
                GateFailure(
                    5,
                    f"Cue {i} timing altered by translation: "
                    f"source=({src_start}ms, {src_end}ms) "
                    f"translated=({trn_start}ms, {trn_end}ms)",
                    failing_indices=[i],
                )
            )


def validate_subdoc(
    translated: SubDoc,
    source: SubDoc,
    settings: "TrezarrSettings",
    *,
    proper_noun_allowlist: set[str] | None = None,
) -> None:
    """Run all 12 gate checks on a translated SubDoc.  Raises GateError on first failure.

    Checks (fail-fast — stops at first failure):
      1. Cue count equals source
      2. No empty/whitespace-only translated lines
      3. No untranslated lines (per-line allowlist + per-FILE VI diacritic ratio) — backstop
      4. Timecodes/indices byte-identical to source
      5. Monotonic, non-overlapping timestamps
      6. No orphan sentinel tokens (<<TN>>)
      7. All cue texts encode as valid UTF-8
      8. No prompt scaffolding leaked into output ("(source: …)", "(speaker says: …)", "[CORRECTION REQUIRED]")
      9. (B2/M3) No CJK / Hangul / Kana codepoint in any translated cue (raw source leak)
     10. (B2/H5) No source-passthrough leak: a no-diacritic cue whose ASCII word tokens all
         appear verbatim in the corresponding source cue and are not all Bible proper nouns
     11. (B2/H5) No English honorific + Capitalized-name bigram ("Mr. Han", "Elder Zhou")
     12. (H4) No English-gloss parenthetical ("(Miss Mei's brother)")

    Checks 9-12 are PER-CUE (the per-file ratio of Check 3 averages a single bad cue away —
    audit B2). Check 3 is kept as a backstop. The structural checks 1-8 are unchanged.

    Args:
        translated: The translated SubDoc produced by the engine.
        source:     The original source SubDoc (for comparison).
        settings:   Settings supplying translate_vi_diacritic_ratio.
        proper_noun_allowlist: Optional lowercased set of Bible-pinned proper-noun tokens
                    (character names + term renderings/source terms). A cue whose ASCII
                    tokens are ALL in this set is a legitimate name passthrough and does NOT
                    trip Check 10. When None, no tokens are allowlisted (Bible-unaware path).

    Returns:
        None if all checks pass.

    Raises:
        GateError: On the first check that fails, with failure.check set to the
                   check number (1–12).
    """
    # Check 1: cue count equals source
    if len(translated.lines) != len(source.lines):
        raise GateError(
            GateFailure(
                1,
                f"Cue count mismatch: translated has {len(translated.lines)} lines, "
                f"source has {len(source.lines)} lines",
            )
        )

    # Check 2: no empty/whitespace-only translated lines
    for i, sl in enumerate(translated.lines):
        # D-99/D-98: opaque pass-through cues have SubLine.raw set; the codec
        # guarantees they are non-empty by construction.  Skip to avoid any
        # accidental false-alarm if a future codec bug accidentally sets an empty
        # text alongside a non-None raw.
        if sl.raw is not None:
            continue
        if not sl.text.strip():
            raise GateError(
                GateFailure(
                    2,
                    f"Empty translated cue at index {i}",
                    failing_indices=[i],
                )
            )

    # Check 3: untranslated-line detection (two-tier: per-line allowlist + VI ratio)
    _check_untranslated(translated, source, settings)

    # Check 4: timecodes/indices byte-identical to source
    for i, (src, trn) in enumerate(zip(source.lines, translated.lines)):
        if src.index != trn.index or src.start_tc != trn.start_tc or src.end_tc != trn.end_tc:
            raise GateError(
                GateFailure(
                    4,
                    f"Timecode/index mutation at cue {i}: "
                    f"source=({src.index!r}, {src.start_tc!r}, {src.end_tc!r}) "
                    f"translated=({trn.index!r}, {trn.start_tc!r}, {trn.end_tc!r})",
                    failing_indices=[i],
                )
            )

    # Check 5: timing preserved from source (codec-fidelity invariant — D-08/D-09).
    # Overlapping cues that exist in the SOURCE legitimately pass; only translation-
    # induced timing mutations fail.  The check complements Check 4 (byte-identity of
    # timecode strings) by catching ms-level corruption that survives string round-trip.
    _check_timing_preserved(translated, source)

    # Check 6: no orphan sentinel tokens — closed form OR unclosed/orphan form.
    # SENTINEL_RE catches '<<T\d+>>' (closed). UNCLOSED_SENTINEL_RE (R4, 260611-ru6)
    # catches '<<T153' without closing '>>' — E03 cue 459 bypass class confirmed in
    # 260611-l74 adversarial audit: Check 10 skips cues with ≤1 ASCII word >= 2 letters,
    # so a bare '<<T153' leaks past all 12 prior checks without this backstop.
    # HTML-escaped form also caught (belt-and-suspenders, D-ru4-01).
    for i, sl in enumerate(translated.lines):
        if SENTINEL_RE.search(sl.text) or UNCLOSED_SENTINEL_RE.search(sl.text):
            raise GateError(
                GateFailure(
                    6,
                    f"Orphan sentinel token found in cue {i}: {sl.text!r}",
                    failing_indices=[i],
                )
            )

    # Check 7: all cue texts encode as valid UTF-8
    for i, sl in enumerate(translated.lines):
        try:
            sl.text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise GateError(
                GateFailure(
                    7,
                    f"UTF-8 encode error at cue {i}: {exc}",
                    failing_indices=[i],
                )
            ) from exc

    # Check 8: no prompt scaffolding leaked into output. Four signatures, same
    # defense-in-depth class — a sidecar containing internal prompt machinery must
    # NEVER ship even if an upstream guard is bypassed (the blind-trust bar):
    #   - REVIEW_SCAFFOLD_RE      → Pass-4 "(source: …)" review echo (260604-gza/hp2).
    #   - HINT_SCAFFOLD_RE         → Pass-3 "(speaker says: …; addresses as: …)" pronoun-hint
    #     echo (260607 trezarr-quality HIGH; the H4 paren-preserve rule raises this risk,
    #     and the per-cue Check 10/12 below provably do NOT catch a diacritic-bearing hint).
    #   - CORRECTION_DIRECTIVE_RE  → IMP-02b "[CORRECTION REQUIRED] …" gate-repair directive
    #     echo (2026-06-08 codec guardian BLOCKER). The directive is an English internal-machinery
    #     string that passes all other checks (no VI diacritic, not in source tokens) — this
    #     backstop closes the proven echo path. "[CORRECTION REQUIRED]" cannot appear in genuine
    #     Vietnamese dialogue, so quarantining is safe with zero false positives.
    #   - ATTRIBUTION_META_RE     → R4 attribution-audit meta-commentary (260611-l74/ru6):
    #     E03 cue 146 '(Correct; "tôi"→"anh" is the right pair; no violation)' and cue 147
    #     '(No violation)' both bypassed Checks 10/12 because they contain VN diacritics
    #     (tôi, anh) causing those checks to treat them as legitimate Vietnamese dialogue.
    #     "no violation" and "correct;" cannot appear in genuine Vietnamese dialogue; zero FP.
    #   - VN_HINT_SCAFFOLD_RE     → 260612-7kt Finding 1: Vietnamese-label hint echo.
    #     E143 cue 148 incident: '(tại hạ nói: tại hạ; xưng hô: cô nương)' evaded both
    #     _LEAKED_HINT_RE and HINT_SCAFFOLD_RE because the model translated the English labels.
    #     Colon-discriminator: 'nói:' / 'xưng hô:' are structural label signals; stage
    #     directions '(nói to)' lack the colon and are NOT matched (zero false positives
    #     confirmed by false-positive battery — see tests/translate/test_validate.py).
    # All five are prompt scaffolding, not genuine Vietnamese dialogue, so quarantining is safe.
    for i, sl in enumerate(translated.lines):
        if (
            REVIEW_SCAFFOLD_RE.search(sl.text)
            or HINT_SCAFFOLD_RE.search(sl.text)
            or VN_HINT_SCAFFOLD_RE.search(sl.text)
            or CORRECTION_DIRECTIVE_RE.search(sl.text)
            or ATTRIBUTION_META_RE.search(sl.text)
        ):
            raise GateError(
                GateFailure(
                    8,
                    f"Prompt scaffolding leaked into cue {i}: {sl.text!r}",
                    failing_indices=[i],
                )
            )

    # ── Per-cue leak checks 9-12 (audit B2/H4/H5/M3) ──────────────────────────────
    # The per-FILE ratio of Check 3 cannot separate a legitimately-short Vietnamese
    # cue ("Là anh.") from a raw English/CJK passthrough — ~40 short VI cues average
    # away ~40 bad cues. These checks inspect each cue against its CORRESPONDING
    # source cue (raw cues interleave identically in both lists, so zip aligns them).
    # All four loops skip opaque pass-through cues (SubLine.raw set — D-98/D-99).
    #
    # Accumulation design (260612-4lq): collect ALL failing cue indices per check
    # across the full SubDoc, then raise ONE GateError with the complete sorted list.
    # Priority order (highest first): 9 > 11 > 12 > 10 — matches the original
    # left-to-right check order, ensuring engine.py repair receives all failing
    # indices in one shot (fixes MK E01 job-16: 3-cue CJK leak burning 3 repair slots).
    allowlist = {t.lower() for t in (proper_noun_allowlist or set())}
    _fail9: list[int] = []
    _fail10: list[int] = []
    _fail11: list[int] = []
    _fail12: list[int] = []
    for i, (src_sl, trn_sl) in enumerate(zip(source.lines, translated.lines)):
        # Opaque pass-through cues (karaoke/drawing) are intentionally untranslated.
        if trn_sl.raw is not None:
            continue
        text = trn_sl.text.strip()
        if not text:
            continue  # caught by Check 2 above; defensive skip

        # Check 9 (B2/M3): CJK / Hangul / Kana codepoint = untranslated source leak.
        if CJK_LEAK_RE.search(text):
            if is_credit_fansub_cue(src_sl.text, text):
                continue
            _fail9.append(i)
            continue  # a CJK-leaking cue need not be tested for checks 10/11/12

        # Check 12 (H4): English-gloss parenthetical. A parenthetical with ASCII
        # letters, no Latin diacritic, long enough to be a gloss (inner len>=3 AND a
        # space or a possessive ‘s). A Vietnamese parenthetical carries diacritics
        # (LATIN_DIACRITIC_RE) and is skipped; tiny tokens "(!)"/"(?)"/"(A)" are skipped.
        for _m in GLOSS_PAREN_RE.finditer(text):
            inner = _m.group(1).strip()
            if len(inner) < 3:
                continue
            if LATIN_DIACRITIC_RE.search(inner):
                continue  # accented Latin = Vietnamese dialogue, not a gloss
            # MEDIUM-2 fix: a bare "ASCII + a space, no diacritic" parenthetical also matches
            # legitimate diacritic-free Vietnamese asides ("(anh em ta)", "(cho con)"), which
            # would quarantine the whole file. Require a concrete ENGLISH-gloss signal — a
            # possessive (\x27s / ’s) or an English honorific+Capitalized-name bigram — which
            # is the actual audit leak pattern and cannot appear in normal Vietnamese dialogue.
            if ("\x27s" in inner) or ("’s" in inner) or HONORIFIC_CAPNAME_RE.search(inner):
                _fail12.append(i)
                break  # one match per cue is sufficient; skip check 11/10 for this cue
        else:
            # No check-12 trigger for this cue — proceed to check 11 and check 10.

            # Check 11 (B2/H5): English honorific + Capitalized name bigram.
            if HONORIFIC_CAPNAME_RE.search(text):
                _fail11.append(i)
                continue  # skip check 10 for this cue

            # Check 10 (B2/H5): source-passthrough leak. Only consider a cue that has NO
            # Vietnamese diacritic (narrow VN range) and is not allowlist/sentinel-only.
            if VN_DIACRITIC_RE.search(text):
                continue
            if ALLOWLIST_RE.match(text) or SENTINEL_ONLY_RE.match(text):
                continue
            tokens = ASCII_WORD_RE.findall(text)
            if len(tokens) < 2:
                continue  # need >=2 ASCII word tokens (length>=2 each) — short VI cues are safe
            # MEDIUM-3 fix: exempt laughter/onomatopoeia — a cue made ONLY of listed interjection
            # syllables ("Ha ha ha", "Ho ho ho", "Hmm uh") — legitimately untranslated and identical
            # to source. Deliberately NOT a blanket "repeated token" exemption: real repeated English
            # imperatives ("Go go", "No no", "Stop stop") must still be caught as passthrough leaks.
            _lower_tokens = [t.lower() for t in tokens]
            if all(t in _INTERJECTION_TOKENS for t in _lower_tokens):
                continue
            src_lower = (src_sl.text or "").lower()
            all_in_source = all(
                re.search(r"\b" + re.escape(tok.lower()) + r"\b", src_lower) for tok in tokens
            )
            if not all_in_source:
                continue  # not a verbatim echo of the source cue
            if all(tok.lower() in allowlist for tok in tokens):
                continue  # every token is a Bible-pinned proper noun — legitimate passthrough
            _fail10.append(i)
        # end for-else (check 12 inner loop)
    # end outer for loop

    # ── Post-loop: raise ONE GateError carrying all failing indices (priority: 9 > 11 > 12 > 10)
    if _fail9:
        raise GateError(
            GateFailure(
                9,
                f"CJK/Hangul/Kana script leaked into {len(_fail9)} cue(s): {sorted(_fail9)}",
                failing_indices=sorted(_fail9),
            )
        )
    if _fail11:
        raise GateError(
            GateFailure(
                11,
                f"English honorific + name leaked into {len(_fail11)} cue(s): {sorted(_fail11)}",
                failing_indices=sorted(_fail11),
            )
        )
    if _fail12:
        raise GateError(
            GateFailure(
                12,
                f"Gloss/parenthetical leaked into {len(_fail12)} cue(s): {sorted(_fail12)}",
                failing_indices=sorted(_fail12),
            )
        )
    if _fail10:
        raise GateError(
            GateFailure(
                10,
                f"Source-language passthrough leak in {len(_fail10)} cue(s): {sorted(_fail10)}",
                failing_indices=sorted(_fail10),
            )
        )
