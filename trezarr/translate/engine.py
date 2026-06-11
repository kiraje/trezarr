"""End-to-end translation engine: numbered-line protocol, batch dispatch, gate, quarantine (D-12..D-20).

Design decisions honoured:
  D-12  Inline-tag sentinel protection — extract before LLM, reinsert after.
  D-13  Numbered-line protocol guarantees 1:1 cue mapping by construction.
  D-14  Batch dispatch via asyncio.gather over LLMClient.call().
  D-15  Context window (K source lines before/after) included in every prompt.
  D-16  Document-level gate via validate_subdoc() before any write.
  D-17  Untranslated-line detection inside validate_subdoc().
  D-18  Bounded per-batch retry via an internal message-accumulating correction loop.
        When the LLM returns a structurally defective response (wrong count / bad sentinel),
        the bad assistant reply and a structural-only correction user turn are appended to the
        messages list and the LLM is called again — up to translate_batch_retry_attempts
        retries. BatchValidationError is the sole recovery mechanism for count/sentinel failures;
        tenacity is NOT used for BatchValidationError (no retry storm).
        openai.APIError is NOT caught here — the SDK handles transport failures.
  D-19  Atomic UTF-8 sidecar write via write_vi_sidecar().
  D-20  Idempotency: await ledger.check() at entry; await ledger.record() after write/quarantine.
  D-37  ledger.check/record are async (Phase 4 — BREAKING INTERNAL API CHANGE, see
        _ledger_protocol.py); type-annotated as LedgerProtocol; all call sites in this
        file await the calls (enforced by test_repo_wide_ledger_await_gate).

Critical constraints:
  - No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (Pitfall 1).
  - No tenacity decorator on _translate_batch_inner; the correction loop is bounded by
    translate_batch_retry_attempts + 1 total LLM calls (Pitfall 5 — no double-retry storm).
  - BatchValidationError is handled exclusively by the correction loop, never by tenacity.
  - New SubLine objects for translated doc — never mutate source SubLines (Pitfall 8).
  - Pass 4 self-review: _review_batch returns list[str] | None — NEVER raises (D-59).
  - No quarantine path in Pass 4 — validate_subdoc remains the sole arbiter (D-55/D-59).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from trezarr.llm.client import LLMClient
from trezarr.llm.metrics import PassStatsCollector
from trezarr.output._ledger_protocol import LedgerProtocol
from trezarr.output.ledger import LedgerEntry
from trezarr.output.write import derive_vi_sidecar_path, write_vi_sidecar
from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.subtitles.dispatch import read_subtitle
from trezarr.translate.batching import Batch, batch_subdoc
from trezarr.translate.sentinel import extract_sentinels, reinsert_sentinels
from trezarr.translate.validate import REVIEW_SCAFFOLD_RE, GateError, validate_subdoc

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.discover.scan import EligibleItem
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)


# B3 fix (C6 aliases, IN-MEMORY only — no DB/schema change): normalize a name before
# id lookup by stripping a leading English honorific/title and a trailing period, so
# "Mr. Han" / "Elder Han" / "Senior Han" / "Young Master Han" all resolve to the
# character "Han". This is the shared contract reused by reconcile.py and analyze.py.
# Backward compatible: a name with no honorific normalizes to itself (lowercased + stripped,
# identical to the prior `.strip().lower()` everywhere). Address-Map starvation on a cold
# Bible was partly the LLM referencing "Elder Zhou" while the character row was "Zhou".
_HONORIFIC_PREFIXES: frozenset[str] = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "sir",
        "madam",
        "master",
        "elder",
        "senior",
        "brother",
        "sister",
        "lord",
        "lady",
        "young",
    }
)


def _normalize_name(name: str) -> str:
    """Normalize a name for case-insensitive id lookup, stripping leading honorifics (B3).

    Lowercases and strips, then peels leading honorific/title tokens (each optionally
    followed by a period) so "Mr. Han" -> "han", "Elder Zhou" -> "zhou",
    "Young Master Han" -> "han". Never returns empty: if every token is an honorific
    (e.g. "Elder", "Brother") the original lowercased+stripped string is returned so a
    bare-honorific form still maps to whatever the existing code mapped before.
    Pure function; no DB, no schema change.
    """
    base = (name or "").strip().lower()
    if not base:
        return base
    tokens = base.split()
    # Peel leading honorific tokens (a trailing period on a token is part of the honorific).
    i = 0
    while i < len(tokens) - 1 and tokens[i].rstrip(".") in _HONORIFIC_PREFIXES:
        i += 1
    stripped = " ".join(tokens[i:]).strip()
    return stripped or base


def _resolve_char_id(name_to_char_id: "dict[str, int]", name: "str | None") -> "int | None":
    """Resolve a (possibly honorific-prefixed) name to a character id (B3 alias-collision guard).

    The index MUST be keyed by EXACT lowercased names. The EXACT match is tried first; the
    honorific-stripped alias (``_normalize_name``) is only a FALLBACK. This is what keeps two
    distinct characters that differ only by an honorific (e.g. 'Zhou' and 'Elder Zhou') from
    silently collapsing onto one id — the bug an alias-keyed index would introduce. A name with
    no honorific resolves identically to the original ``.strip().lower()`` lookup.
    """
    if not name:
        return None
    return name_to_char_id.get(name.strip().lower()) or name_to_char_id.get(_normalize_name(name))


# ── Episode key derivation ─────────────────────────────────────────────────────


def derive_episode_key(media_item: object, source_sub_path: "str | Path | None" = None) -> str:
    """Derive a stable episode identifier from a MediaItem and subtitle path (D-49, Pitfall F).

    For episode items: parses SxxExx from the subtitle filename stem.
    For movie items: slugifies the title into "movie-<slug>".

    CRITICAL (Pitfall F): Do NOT access media_item.episode_number — that field
    does not exist on MediaItem. Episode number must be parsed from source_sub_path stem.

    Args:
        media_item:      A MediaItem-like object with source_type, season_number, title.
        source_sub_path: Path to the source subtitle file (used to parse episode number).

    Returns:
        A stable string key like "S01E03" or "movie-some-title".
    """
    source_type = getattr(media_item, "source_type", "episode")

    if source_type == "episode":
        # Parse SxxExx from subtitle filename stem (Pitfall F: no episode_number field)
        if source_sub_path is not None:
            stem = Path(source_sub_path).stem
            m = re.search(r"S(\d{2,})E(\d{2,})", stem, re.IGNORECASE)
            if m:
                return f"S{m.group(1).upper()}E{m.group(2).upper()}"
            # R2 fix (260611-ru6): also match Plex "NxNN" / "NxNNN" dash-separated stems
            # (case-insensitive, 1-2 digit season, 1-3 digit episode).
            # Example: "A Record of a Mortal's Journey to Immortality - 6x19 - Episode 143"
            # → S06E19. The SxxExx primary regex takes priority (elif not if) so a stem that
            # has both forms uses the SxxExx form — backward-compatible.
            # Without this fix, Plex stems collapse to S{season:02d}E00 which matches every
            # cold-Bible S00E00 relationship_event — the episode_key collapse BLOCKER (audit B2).
            #
            # Digit-boundary lookarounds prevent resolution/aspect strings from matching:
            # e.g. "1024x768" → "24x76" sub-match is blocked because '4' is immediately
            # preceded by the digit '2'. Mirrors library.py:51 which uses the same pattern
            # ("lookarounds avoid matching resolutions like 1920x1080").
            # TODO: extract one shared anchored parser from engine.py + library.py (MEDIUM,
            # tracked as tech-debt — see pipeline-reliability-reviewer R2 MEDIUM finding).
            m_plex = re.search(r"(?<!\d)(\d{1,2})[xX](\d{1,3})(?!\d)", stem)
            if m_plex:
                return f"S{int(m_plex.group(1)):02d}E{int(m_plex.group(2)):02d}"
        # Fallback: use season_number if parse fails
        season = getattr(media_item, "season_number", None) or 0
        return f"S{season:02d}E00"
    else:
        # Movie: slug from title
        title = getattr(media_item, "title", None) or "movie"
        slug = title.lower()[:20].replace(" ", "-")
        # Remove characters unsafe for a filesystem key
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        return f"movie-{slug}"


# ── Exception hierarchy ────────────────────────────────────────────────────────


class BatchValidationError(Exception):
    """Raised when a translated batch fails batch-level gate checks.

    Caught ONLY by the internal correction loop in _translate_batch_inner.
    When the LLM drops a line or returns a wrong count, the bad reply and a
    structural-only correction turn are appended to the messages list and the
    LLM is called again — up to translate_batch_retry_attempts times.
    After budget exhaustion, BatchValidationError propagates to translate_file
    → quarantine. Tenacity does NOT catch this exception (no double-retry storm).
    """


class TranslationError(Exception):
    """Raised for whole-file translation failures that trigger quarantine.

    Propagates from translate_file when the document-level gate fails.
    """


# ── Result dataclass ───────────────────────────────────────────────────────────


@dataclass
class TranslationResult:
    """Result returned by translate_file().

    Attributes:
        status:          "done" | "skipped" | "quarantined"
        output_path:     Path to the written vi sidecar (status="done" only; mirrors source extension — D-95).
        quarantine_path: Path to the quarantine JSON artifact (status="quarantined" only).
        reason:          Human-readable description of the failure (status="quarantined" only).
    """

    status: str  # "done" | "skipped" | "quarantined"
    output_path: Path | None = None
    quarantine_path: Path | None = None
    reason: str | None = None


# ── Prompt construction ────────────────────────────────────────────────────────


def build_glossary_lines(bible: object) -> list[str]:
    """Build "source → canonical rendering" glossary lines from the Series Bible.

    Pins every Term Dictionary entry (``source_term → vietnamese_rendering``) and every character
    name so the translator renders proper nouns IDENTICALLY across all cues — the consistency moat
    (BIBLE-04). A character whose name already has a Term Dictionary entry is covered by it; a
    character without one is pinned to its own ``original_latin_name`` (e.g. ``Daisy → Daisy``),
    which is what prevents the protagonist drifting into many spellings within one episode.

    Tolerant of a bible with no characters/terms (returns []).
    """
    lines: list[str] = []
    seen: set[str] = set()
    for t in getattr(bible, "terms", None) or []:
        src = (getattr(t, "source_term", "") or "").strip()
        ren = (getattr(t, "vietnamese_rendering", "") or "").strip()
        if src and ren:
            lines.append(f"{src} → {ren}")
            seen.add(src.lower())
    for c in getattr(bible, "characters", None) or []:
        name = (getattr(c, "original_latin_name", "") or "").strip()
        if name and name.lower() not in seen:
            lines.append(f"{name} → {name}")
            seen.add(name.lower())
    return lines


def build_translate_prompt(
    batch_texts: list[str],
    context_before: list[str],
    context_after: list[str],
    source_lang: str = "English",
    pronoun_hints: "dict[int, tuple[str, str]] | None" = None,
    glossary: "list[str] | None" = None,
    register: "str | None" = None,
    correction_directive: "str | None" = None,
) -> str:
    """Build the numbered-line translation prompt (D-13, D-15, ENG-03, D-46).

    Structure:
      - Optional [REGISTER] note (C3/H1) instructing the translator to match the series tone.
      - Optional [GLOSSARY] block + "use these EXACTLY" rule.
      - Optional [CONTEXT] block before the lines to translate (context_before)
      - [LINES TO TRANSLATE] block with [1] ... [N] numbered lines
      - Optional [CONTEXT] block after the lines to translate (context_after)

    Args:
        batch_texts:          Source texts for the cues to translate, in order.
        context_before:       Read-only context lines preceding this batch.
        context_after:        Read-only context lines following this batch.
        source_lang:          Human-readable source language name (default "English").
        pronoun_hints:        Optional dict mapping 1-based line index to
                              (self_term, address_term) pronoun pair (D-46).
                              When provided, hinted lines render as:
                              "[N] (speaker says: X; addresses as: Y) <text>"
                              Unhinted lines render as "[N] <text>" (unchanged).
        glossary:             Optional list of "source → canonical rendering" lines (character
                              names + Term Dictionary). When provided, a [GLOSSARY] block + a
                              "use these EXACTLY" rule are injected so proper nouns render
                              identically across every cue (the consistency moat). Build it with
                              build_glossary_lines(bible).
        register:             Optional series register/tone (e.g. "xianxia", "wuxia",
                              "cultivation", "historical", "romantic", "casual"). C3/H1 fix:
                              when truthy, a [REGISTER] note + a RULE are injected instructing
                              the translator to MATCH that tone — a classical/historical/wuxia/
                              xianxia/cultivation register demands classical Sino-Vietnamese
                              (Hán-Việt) vocabulary and pronouns, never flat modern speech.
                              Thread it with bible.register_value (mirror of glossary).
        correction_directive: Optional IMP-02b gate-repair correction instruction injected
                              as a prominent RULE near the top of the RULES block (prefixed
                              with "[CORRECTION REQUIRED]" so its echo is catchable by the
                              parse-layer strip and validate.py Check 8 backstop). Must NOT
                              be passed via context_before (proven echo-prone by e8r/job-9).

    B1 fix: a cue's internal newlines are encoded as the literal token ``<<BR>>`` on the
    [N] marker line (so a 2-line cue 'A' + newline + 'B' becomes "[N] A<<BR>>B"). A RULE
    instructs the model to keep every <<BR>> verbatim; parse_numbered_response restores it
    to a newline so multi-line cues round-trip byte-identical instead of being truncated to
    their first physical line (audit B1).

    Returns:
        A prompt string ready to send to LLMClient.call() as a user message.
    """
    # B1 fix: build the static rules with a running counter so the always-present <<BR>>
    # rule and the optional glossary/register/mixed-gender rules all get correct sequential
    # numbers regardless of which optional blocks fire.
    parts = [
        f"Translate the following {source_lang} subtitle lines to Vietnamese.",
        "RULES:",
        "1. Output ONLY the numbered lines [1], [2], ... [N] in order.",
        "2. Keep <<T0>>, <<T1>>, ... tokens EXACTLY as-is (formatting placeholders — never translate or modify them).",
        "3. Do NOT translate or output the [context] lines.",
    ]
    rule_n = 4
    # B1 fix: a 2-line cue is sent as "Line one<<BR>>Line two"; the model must preserve
    # every <<BR>> verbatim so the cue round-trips to its original physical-line count.
    parts.append(
        f"{rule_n}. Each line may contain <<BR>> markers that stand for line breaks inside a "
        "single subtitle cue. Keep every <<BR>> EXACTLY where it is — never delete, add, "
        "translate, reorder, or split a line on them. Output the SAME number of <<BR>> "
        "markers you received."
    )
    rule_n += 1
    if glossary:
        # H2 fix: the glossary RULE now POSITIVELY requires Hán-Việt (Sino-Vietnamese)
        # readings for romanized/pinyin proper names — not just a negative "don't invent"
        # instruction. A cold Bible used to leak raw pinyin ("Feng Tianji", "Elder Zhou").
        # [linguist: refine wording]
        parts.append(
            f"{rule_n}. For any name or term in [GLOSSARY], use the EXACT Vietnamese rendering "
            "on the right — identical in every line. For any romanized/pinyin proper name NOT "
            "in [GLOSSARY], render it with its Sino-Vietnamese (Hán-Việt) reading (e.g. pinyin "
            "'Feng Tianji' → 'Phong Thiên Cực', 'Han' → 'Hàn'), and render a kinship/honorific "
            "used as a form of address with its Vietnamese equivalent ('Brother' → 'huynh', "
            "'Elder' → 'trưởng lão', 'Senior' → 'tiền bối'), NOT as a literal name. Never invent "
            "alternate transliterations, use Japanese romaji, leave pinyin, or leave source-"
            "language script."
        )
        rule_n += 1
    # H4 fix: PRESERVE source-present parentheses/brackets and forbid ADDING new explanatory
    # glosses. The old unqualified "Do NOT add parentheticals" caused weak models (DeepSeek)
    # to strip parentheses already in the source — e.g. a title card "(A Record of Mortal's
    # Journey to Immortality)" became "A Record…" with no parens. The fix is two-part:
    # (a) positively preserve the delimiter envelope when it is already in the source cue,
    # and (b) still forbid the model from ADDING its own glosses or translator notes.
    # validate.py Check 12 (GLOSS_PAREN_RE) remains the hard backstop against model-added
    # English-gloss parentheticals.
    #
    # SCAFFOLDING-LEAK CARVE-OUT (trezarr-quality HIGH, 260607): the per-line attribution
    # hint below is itself a LEADING parenthetical "(speaker says: …; addresses as: …)".
    # Without this carve-out, "preserve source parentheses" reads as license to echo that
    # hint on-screen — re-opening the 260604/260607 scaffolding leak (the Ep-142 audit saw
    # "(speaker says: tại hạ; addresses as: Mai cô nương)" ship in 7 cues). The rule names
    # the hint and marks it a PRIVATE instruction to strip. validate.py Check 8
    # (HINT_SCAFFOLD_RE) is the gate-layer backstop. [linguist: refine wording]
    parts.append(
        f'{rule_n}. If the source cue contains parentheses "( )" or square brackets "[ ]", '
        'TRANSLATE the text inside them and PRESERVE the surrounding "(" ")" / "[" "]" '
        "envelope in the output — do NOT strip the delimiters. Do NOT add new glosses, "
        "translator notes, or explanatory parentheticals that are NOT already present in the "
        'source cue. EXCEPTION: a leading note in the form "(speaker says: …; addresses as: '
        '…)" is a PRIVATE pronoun instruction, NOT subtitle text — use it only to choose '
        "pronouns, then NEVER translate, echo, or keep it or its parentheses in your output."
    )
    rule_n += 1
    if register:
        # H1 fix: the register/tone MUST reach Pass-3 (the pass that writes the subtitle).
        # Pass-4 review only nudges verbatim lines, so a flat-modern Pass-3 output stayed flat.
        # [linguist: refine the register-specific wording]
        parts.append(
            f"{rule_n}. Match the series register/tone given in [REGISTER]. If the register is "
            "classical / historical / wuxia / xianxia / cultivation (cổ trang / tiên hiệp / "
            "kiếm hiệp), use classical Sino-Vietnamese (Hán-Việt) vocabulary and classical "
            "pronouns (e.g. self: ta / tại hạ / lão phu; address: ngươi / các hạ / chư vị / "
            "huynh / muội / tiền bối / trưởng lão) — do NOT flatten the dialogue into plain "
            "modern speech (tôi / bạn / anh / em) when the register is classical. Render any "
            "romanized/pinyin proper name with its Sino-Vietnamese (Hán-Việt) reading and never "
            "leave pinyin or source-language script (this holds even when no [GLOSSARY] is given)."
        )
        rule_n += 1
    # B4 fix: a single line that addresses MULTIPLE people must use a NON-GENDERED plural.
    # [linguist: refine classical vs modern wording]
    parts.append(
        f"{rule_n}. When a single line addresses MORE THAN ONE person, use a non-gendered "
        "plural address — classical: 'chư vị' / 'các vị' / 'các ngươi'; modern: 'các bạn' / "
        "'mọi người'. NEVER use a gendered plural ('các cô' / 'các cậu' / 'các anh' / 'các "
        "chị') for a mixed-gender group, and if any addressee is male never use a female-"
        "gendered term."
    )
    rule_n += 1
    # FIX-A (260607-dbe): unhinted-line guardrail — forbid character-name substitution for
    # 2nd-person pronouns when no (speaker says / addresses as) hint is on the line.
    # Review fix (260607-dbe quality pass): reuse reconcile._is_classical_register (the canonical
    # 16-token classifier) instead of a divergent inline keyword set, and offer ONLY
    # safe-default-ladder pronouns — never `ngươi` (presumptuous/superior, deliberately excluded
    # from reconcile's safe-default ladder) or `em` (intimate) on a no-relationship-signal line.
    # This mirrors reconcile.get_safe_default's policy so the unhinted fallback can never drift
    # from it. Function-local import matches the existing engine<->reconcile cycle-avoidance pattern.
    from trezarr.translate.reconcile import _is_classical_register

    if _is_classical_register(register):
        _pronoun_examples = "các hạ (respectful, non-gendered) — never a proper name"
    else:
        _pronoun_examples = "bạn, or anh/chị by gender — never 'em' and never a proper name"
    parts.append(
        f"{rule_n}. For any line WITHOUT a (speaker says / addresses as) hint: render English "
        "'you/your/yourself' as a safe, non-presumptuous 2nd-person Vietnamese pronoun — NEVER "
        "substitute a character name. "
        f"Use {_pronoun_examples}."
    )
    rule_n += 1
    # IMP-02b FIX 1(a): inject gate-repair correction directive as a RULE (not context_before).
    # context_before is rendered under "[CONTEXT - read only, do not output]" with the instruction
    # "Do NOT translate or output the [context] lines" — the e8r/job-9 incident proved deepseek
    # IGNORES that instruction and echoes context lines verbatim into output cues. Moving the
    # directive into the RULES block (with the mandatory "[CORRECTION REQUIRED]" marker prefix so
    # its echo is catchable by _LEAKED_DIRECTIVE_RE + validate.py CORRECTION_DIRECTIVE_RE) cuts
    # the echo likelihood while keeping the gate-layer backstop. Markerless-paraphrase echoes
    # (e.g. "Render EVERY name in its Vietnamese Hán-Việt form.") are accepted residual risk —
    # their semantic content is benign instructions, not internal machinery tokens.
    if correction_directive:
        parts.append(f"{rule_n}. [CORRECTION REQUIRED] {correction_directive}")
        rule_n += 1  # noqa: F841 — rule_n kept for future rules added after this block
    parts.append("")

    # C3/H1 fix: inject a [REGISTER] note so the translator matches the series tone. A
    # classical/historical/wuxia/xianxia/cultivation register requires classical
    # Sino-Vietnamese vocabulary and pronouns, NOT flat modern speech.
    # [linguist: refine the register-specific wording]
    if register:
        parts.append("[REGISTER - match this tone in every line]")
        parts.append(
            f"- Series register/tone: {register}. Match it. A classical / historical / wuxia / "
            "xianxia / cultivation register requires classical Sino-Vietnamese vocabulary and "
            "pronouns (e.g. ta / ngươi / tại hạ / các hạ), never flat modern speech."
        )
        parts.append("")

    if glossary:
        parts.append("[GLOSSARY - canonical renderings, use EXACTLY]")
        for g in glossary:
            parts.append(f"- {g}")
        parts.append("")

    if context_before:
        parts.append("[CONTEXT - read only, do not output]")
        for line in context_before:
            parts.append(f"[context] {line.strip()}")
        parts.append("")

    parts.append("[LINES TO TRANSLATE]")
    for i, text in enumerate(batch_texts, 1):
        # B1 fix: sentinel internal newlines as <<BR>> so a multi-line cue survives the
        # numbered-line round-trip (parse_numbered_response reverses this).
        marked = text.strip().replace(chr(10), "<<BR>>")
        if pronoun_hints and i in pronoun_hints:
            self_t, addr_t = pronoun_hints[i]
            parts.append(f"[{i}] (speaker says: {self_t}; addresses as: {addr_t}) {marked}")
        else:
            parts.append(f"[{i}] {marked}")

    if context_after:
        parts.append("")
        parts.append("[CONTEXT - read only, do not output]")
        for line in context_after:
            parts.append(f"[context] {line.strip()}")

    return "\n".join(parts)


# ── Pass-4 self-review prompt construction ─────────────────────────────────────


def build_review_prompt(
    source_texts: list[str],
    translated_texts: list[str],
    resolved_map: "dict[tuple[int, int], tuple[str, str]]",
    bible: object,
    settings: "TrezarrSettings",
    dominant_pair: "tuple[int, int] | None" = None,
) -> str:
    """Build the Pass-4 self-review prompt (D-57, D-58).

    Instructs the reviewer to correct Bible violations only — NOT to paraphrase
    or "improve" adherent lines (D-58). Reuses the numbered-line [N] protocol.

    Args:
        source_texts:    Source cue texts for context.
        translated_texts: Pass-3 Vietnamese cue texts to review (sentinel-cleaned).
        resolved_map:    (speaker_id, addressee_id) → (self_term, address_term).
        bible:           SeriesBibleDTO for register + term dictionary context.
        settings:        TrezarrSettings (unused directly; reserved for future knobs).
        dominant_pair:   (speaker_id, addressee_id) dominant pair for this batch.
    """
    parts = [
        "[INSTRUCTIONS]",
        "You are a Vietnamese subtitle reviewer. Check each numbered line for Series Bible violations ONLY.",
        "",
        "Series Bible for this batch:",
    ]

    # H3 fix: never inject the literal string "neutral" as the register to imitate — that
    # actively steered Pass-4 away from a classical/xianxia tone. When no real register is
    # known (None/empty or the placeholder "neutral"), tell the reviewer to MATCH the source
    # tone and not flatten it; only emit a concrete Register/tone line for a real register.
    register = (getattr(bible, "register_value", None) or "").strip()
    if register and register.lower() != "neutral":
        parts.append(f"  - Register/tone: {register}")
    else:
        parts.append(
            "  - Register/tone: match the source tone; do NOT flatten a classical/historical/"
            "wuxia/xianxia/cultivation register into plain modern speech."
        )

    if dominant_pair is not None and dominant_pair in resolved_map:
        self_t, addr_t = resolved_map[dominant_pair]
        parts.append(
            f'  - Pronoun pair (speaker→addressee): speaker says "{self_t}", '
            f'addresses as "{addr_t}"'
        )

    # Filter term dictionary to relevant terms (those appearing in source texts)
    source_combined = " ".join(source_texts).lower()
    relevant_terms = [
        t for t in getattr(bible, "terms", []) if (t.source_term or "").lower() in source_combined
    ]
    for term in relevant_terms[:10]:  # cap at 10 to control token count
        parts.append(f"  - Term: {term.source_term} → {term.vietnamese_rendering}")

    # Character names — injected UNCONDITIONALLY (not substring-filtered). The term filter above
    # can never match a Latin term key (e.g. "Sakura") against a non-Latin source (e.g. Chinese
    # "樱"), so for CJK sources Pass-4 injected nothing and the protagonist drifted. Always pin
    # the canonical character names so the reviewer can catch a wrong/variant rendering.
    for ch in (getattr(bible, "characters", None) or [])[:15]:
        nm = (getattr(ch, "original_latin_name", "") or "").strip()
        if nm:
            parts.append(f"  - Name (render identically everywhere): {nm}")

    parts.extend(
        [
            "",
            "RULES:",
            "1. Output ONLY numbered lines [1], [2], ... [N] in order.",
            "2. Keep <<T0>>, <<T1>>, ... tokens EXACTLY as-is.",
            # B1 fix: the same <<BR>> line-break sentinel contract as Pass-3 so multi-line
            # cues round-trip through the reviewer instead of being flattened.
            "3. Keep every <<BR>> marker EXACTLY where it is — it stands for a line break "
            "inside the subtitle cue; never delete, add, translate, reorder, or split on them.",
            "4. Return each line VERBATIM unless it has a SPECIFIC Bible violation:",
            "   - Wrong pronoun: uses different first-person or second-person term than the Bible pair above.",
            "   - Wrong term: a proper noun/title/place from the Bible is not rendered as specified above.",
            "   - Wrong register: significantly more formal or informal than the series register.",
            # B4 fix: flag a gendered plural address used for a mixed-gender group (cue addressing
            # multiple people) — the review-pass analogue of the Pass-3 mixed-gender rule.
            "   - Wrong plural address (B4): a line addressing MORE THAN ONE person uses a gendered "
            "plural ('các cô' / 'các cậu' / 'các anh' / 'các chị') for a mixed-gender group — replace "
            "with a non-gendered plural ('chư vị' / 'các vị' / 'các ngươi' for classical; 'các bạn' / "
            "'mọi người' for modern); if any addressee is male, never use a female-gendered term.",
            "5. Do NOT rephrase, 'improve', or paraphrase lines that already comply.",
            "",
            "[LINES TO REVIEW]",
        ]
    )

    for i, (src, vi) in enumerate(zip(source_texts, translated_texts), 1):
        # B1 fix: encode internal newlines as <<BR>> on both the source echo and the
        # text under review so a multi-line cue stays on one physical [N] line and is
        # restored intact by parse_numbered_response.
        src_marked = src.strip().replace(chr(10), "<<BR>>")
        vi_marked = vi.strip().replace(chr(10), "<<BR>>")
        parts.append(f"[{i}] (source: {src_marked}) {vi_marked}")

    return "\n".join(parts)


def _reject_scaffolded_correction(corrected: str, fallback: str) -> str:
    """Drop a Pass-4 "correction" that leaked the review-prompt scaffolding.

    build_review_prompt formats each line as "[N] (source: <orig>) <vi>"; a weak
    model sometimes echoes the whole scaffolded line back as its "correction".
    parse_numbered_response cannot tell that apart from a real correction, and the
    validation gate's diacritic ratio misses it (the trailing VI text clears the
    threshold), so it would splice e.g. "(source: 不要) Đừng" into the final
    subtitle (v1.0 live-verify, 260604-gza). If ``corrected`` matches the shared
    REVIEW_SCAFFOLD_RE, discard it and keep the clean pre-review (Pass-3)
    ``fallback`` — the per-line analogue of D-59: never make a line worse than
    the pre-review translation. (Gate Check 8 uses the same RE as a backstop.)
    """
    if REVIEW_SCAFFOLD_RE.search(corrected):
        return fallback
    return corrected


# ── Pass-4 self-review batch handler ──────────────────────────────────────────
# No asyncio.Semaphore here. LLMClient._semaphore is the sole gate (D-06, Pitfall 1).


async def _review_batch(
    review_batch: "Batch",
    source_lines_by_index: dict,
    resolved_map: "dict[tuple[int, int], tuple[str, str]]",
    bible: object,
    llm_client: LLMClient,
    settings: "TrezarrSettings",
    model: "str | None" = None,  # D-113: per-call model override
    collector: "PassStatsCollector | None" = None,  # 260612-1tm: per-pass metrics
) -> "list[str] | None":
    """Review a batch of translated cues against the Series Bible.

    Returns corrected texts, or None on ANY failure (D-59 best-effort — never raises,
    never quarantines). Mirrors _translate_batch_inner but with softer error handling.

    Steps (mirror of _translate_batch_inner):
      1. extract_sentinels per translated cue (D-12)
      2. build_review_prompt with source text + Bible context (D-57, D-58)
      3. llm_client.call(messages) — NO response_model (D-57)
      4. parse_numbered_response
      5. reinsert_sentinels — return None on integrity failure (D-59)
    """
    try:
        # Step 1: Extract sentinels from TRANSLATED texts (<<T...>> tokens are in translated)
        cleaned_texts: list[str] = []
        sentinel_maps: list[dict[str, str]] = []
        source_texts: list[str] = []

        for cue in review_batch.cues:
            cleaned, smap = extract_sentinels(cue.text)
            cleaned_texts.append(cleaned)
            sentinel_maps.append(smap)
            src = source_lines_by_index.get(cue.index)
            source_texts.append(src.text if src else "")

        # Step 2: Build review prompt with Bible context
        dominant_pair = getattr(review_batch, "dominant_pair", None)
        prompt = build_review_prompt(
            source_texts=source_texts,
            translated_texts=cleaned_texts,
            resolved_map=resolved_map,
            bible=bible,
            settings=settings,
            dominant_pair=dominant_pair,
        )

        # Step 3: LLM call — no response_model (D-57); D-113: forward per-call model override
        # 260612-1tm: forward per-pass collector for duration + token capture
        raw_response = await llm_client.call(
            [{"role": "user", "content": prompt}], model=model, collector=collector
        )

        # Step 4: Parse numbered-line response (MEDIUM-4: only multi-line cues accept
        # continuation lines, so trailing reviewer prose is dropped, not spliced in).
        _ml_idx = {i for i, t in enumerate(cleaned_texts, 1) if "\n" in t}
        corrected_texts = parse_numbered_response(
            str(raw_response), len(review_batch.cues), multiline_indices=_ml_idx
        )

        # Step 4.5: Scaffolding-leak guard — discard any "correction" that echoed
        # the review-prompt "(source: …)" scaffolding and keep the clean pre-review
        # (Pass-3) text for that cue (per-line D-59; never make a line worse).
        corrected_texts = [
            _reject_scaffolded_correction(corr, clean)
            for corr, clean in zip(corrected_texts, cleaned_texts)
        ]

        # Step 5: Reinsert sentinels — return None on integrity failure (D-59).
        # Always call (even for an empty smap) so a hallucinated orphan <<TN>> is
        # stripped; integrity_ok is False only on a LOST REAL sentinel.
        restored: list[str] = []
        for text, smap in zip(corrected_texts, sentinel_maps):
            restored_text, integrity_ok = reinsert_sentinels(text, smap)
            if not integrity_ok:
                logger.warning(
                    "Pass 4: sentinel integrity failure — using pre-review output for this batch (D-59)"
                )
                return None  # fallback, not exception
            restored.append(restored_text)

        return restored

    except Exception:
        logger.warning(
            "Pass 4 review batch failed — using pre-review output (D-59)",
            exc_info=True,
        )
        return None  # NEVER raises, NEVER quarantines (D-59)


# ── Numbered-line response parser ──────────────────────────────────────────────

# Forgiving regex per A7 in RESEARCH.md: handles "[1] text", "[1]. text", "[1]) text"
_NUMBERED_LINE_RE = re.compile(r"\[(\d+)\][.\)]?\s*(.*)")

# B1 fix: tolerant marker for the internal-line-break sentinel placed by build_translate_prompt
# / build_review_prompt. Tolerant of stray whitespace a weak model may insert ("<< BR >>").
_BR_RE = re.compile(r"<<\s*BR\s*>>")

# 260608-e8r: strip a LEADING echoed Pass-3 pronoun hint from translated cue text.
# build_translate_prompt injects "(speaker says: <self>; addresses as: <addr>)" as a
# LEADING parenthetical hint on each numbered line. A weak model sometimes echoes that
# instruction phrase verbatim into its output (job-9 incident: cue quarantined the whole
# episode). This regex matches ONLY that specific English instruction phrase at the START
# of the text, so:
#   "(speaker says: muội; addresses as: huynh) Chư vị tu sĩ..." → "Chư vị tu sĩ..."
#   "(speaker says: ta; addresses as: ngươi)" → "" → empty-check → BatchValidationError
#   "(Phàm Nhân Tu Tiên Ký)" → NOT matched (no "speaker says:") → preserved unchanged
# Anchored with ^ (applied on the assembled single-cue string after <<BR>> restoration).
# [^)]* stops at the first ")" — no nested parens in the hint → no backtracking risk.
# Case-insensitive + space-tolerant, mirroring HINT_SCAFFOLD_RE in validate.py.
# MOAT INVARIANT: strips ONLY the echoed English instruction phrase; the actual translated
# dialogue pronouns are untouched. validate.py Check 8 / HINT_SCAFFOLD_RE remains the
# defense-in-depth backstop for any leaked hint that this strip does not catch.
_LEAKED_HINT_RE = re.compile(
    r"^\s*\(\s*speaker\s+says\s*:[^)]*\)\s*",
    re.IGNORECASE,
)

# IMP-02b: strip a LEADING echoed gate-repair directive from translated cue text.
# _repair_failing_cues injects "[CORRECTION REQUIRED] <directive>" as an instruction in
# the RULES block of the repair prompt. Proven by the codec guardian (2026-06-08):
# deepseek echoes instruction phrases into output cues. Mirroring _LEAKED_HINT_RE:
#   "[CORRECTION REQUIRED] Translate fully into Vietnamese." → "" → BatchValidationError
#   "Chư vị tu sĩ..." → NOT matched (no [CORRECTION REQUIRED]) → preserved unchanged
# Anchored at ^ + matches the whole "[CORRECTION REQUIRED] ..." prefix + optional newline.
# [^\n]* stops at end of the directive line — no catastrophic backtracking.
# validate.py Check 8 / CORRECTION_DIRECTIVE_RE remains the gate-layer backstop.
_LEAKED_DIRECTIVE_RE = re.compile(
    r"^\s*\[\s*CORRECTION\s+REQUIRED\s*\][^\n]*\n?",
    re.IGNORECASE,
)

# 260612-7kt (Finding 1 / D-01) — Vietnamese-label variant of the Pass-3 pronoun-hint strip.
# Sibling of _LEAKED_HINT_RE (English-label form, anchored to "speaker says:").
# E143 cue 148: a weak model translated the hint labels into Vietnamese:
#   "(tại hạ nói: tại hạ; xưng hô: cô nương) xin cô nương nén bi thương."
#   → stripped: "xin cô nương nén bi thương."
#   "(xưng hô: anh) Mình đi thôi." → "Mình đi thôi."
#   "(Phàm Nhân Tu Tiên Ký) Cảnh mở đầu." → NOT matched (no xưng hô:) → preserved
#   "(Hắn nói: đợi ta ở đây)" → NOT matched (nói: only, no xưng hô:) → preserved
#
# Mandatory anchor: `xưng hô:` — same policy as VN_HINT_SCAFFOLD_RE (validate.py).
# `nói:` alone matches ordinary reported speech and must NOT be stripped.
#
# Evasion hardening (260612-7kt review, findings A+B):
#   • Mandatory anchor: xưng hô[:：] — nói:-only is legitimate reported speech (Finding A).
#   • Colon class `[:：]` — catches fullwidth colon U+FF1A (Finding B).
#   • Two alternations: `(...)` and `[...]` envelope styles with matching closers (Finding B).
#   • Interior `[^()]*` / `[^\[\]]*` — stops at bracket boundaries only; colons in
#     the interior (e.g. "nói: tại hạ;") are allowed so the two-label form
#     "(tại hạ nói: tại hạ; xưng hô: cô nương)" is still stripped.
#   • Post-anchor remainder `[^)]*` / `[^\]]*` — consumes to the matching closer.
#
# MOAT INVARIANT: strips ONLY the echoed Vietnamese-label prefix; dialogue pronouns untouched.
# validate.py Check 8 / VN_HINT_SCAFFOLD_RE is the defense-in-depth backstop for any
# leaked VN-label hint that this strip does not catch.
_LEAKED_VN_HINT_RE = re.compile(
    r"^\s*(?:"
    r"\(\s*(?:[^()]*xưng\s+hô\s*[:：])[^)]*\)"
    r"|"
    r"\[\s*(?:[^\[\]]*xưng\s+hô\s*[:：])[^\]]*\]"
    r")\s*",
    re.IGNORECASE,
)


def parse_numbered_response(
    response: str,
    expected_count: int,
    multiline_indices: "set[int] | None" = None,
) -> list[str]:
    """Parse a numbered-line LLM response into a list of translated strings (D-13).

    Uses a forgiving regex that handles "[N] text", "[N]. text", and "[N]) text"
    variants (Assumption A7 from RESEARCH.md).

    B1 fix (multi-line cue round-trip): any response line that does NOT match the [N]
    marker is accumulated into the most-recently-seen line number's text (joined with a
    newline), so a model that emits a real newline instead of <<BR>> still keeps the
    continuation. Text before the first [1] marker is ignored. After assembling each
    cue, every <<BR>> sentinel is replaced with a newline; a <<BR>> emitted alongside a
    real newline at the same break collapses to a single newline (no doubled blank line).

    MEDIUM-4 fix (trailing-prose guard): when ``multiline_indices`` is supplied, continuation
    accumulation is restricted to cue numbers whose SOURCE was actually multi-line (a <<BR>>
    was sent for them). This prevents trailing model prose after the last cue — e.g. a chatty
    "Hope this helps!" line — from being silently spliced into an otherwise single-line cue
    (the worst failure class under the blind-trust bar). When None (e.g. a bare unit-test call),
    every continuation line is accumulated, preserving the pure round-trip behaviour.

    Args:
        response:          Raw string response from the LLM.
        expected_count:    The number of lines that should be in the response.
        multiline_indices: Optional set of 1-based cue numbers whose source was multi-line.
                           Continuation lines are only merged onto a cue in this set.

    Returns:
        Ordered list of translated text strings (one per numbered line).

    Raises:
        BatchValidationError: If any expected line number is missing, any line is
                              empty/whitespace-only, any line number is out of range,
                              duplicated, or the parsed count != expected_count.
    """
    parsed: dict[int, str] = {}
    current: int | None = None
    for raw_line in response.splitlines():
        stripped = raw_line.strip()
        m = _NUMBERED_LINE_RE.match(stripped)
        if m:
            line_num = int(m.group(1))
            text = m.group(2).strip()
            if line_num in parsed:
                raise BatchValidationError(f"Duplicate line number [{line_num}] in LLM response")
            parsed[line_num] = text
            current = line_num
        elif (
            current is not None
            and stripped
            and (multiline_indices is None or current in multiline_indices)
        ):
            # B1 fix: continuation of the current cue (model emitted a real newline
            # instead of <<BR>>). Leading text before the first [1] marker is ignored.
            # MEDIUM-4 guard: only merge onto cues whose source was multi-line, so trailing
            # prose after a single-line cue is dropped (old behaviour) rather than spliced in.
            parsed[current] = f"{parsed[current]}\n{stripped}" if parsed[current] else stripped

    # Reject any line numbers outside the expected range (hallucinated extra lines).
    # An over-count response is a strong batch-misalignment signal that should retry.
    extra = [n for n in parsed if n < 1 or n > expected_count]
    if extra:
        raise BatchValidationError(
            f"LLM response contains unexpected line numbers {extra} (expected 1..{expected_count})"
        )

    # Validate all expected line numbers are present, restore <<BR>> -> newline, and
    # reject empties (the empty check runs on the post-<<BR>> text — B1 fix).
    for n in range(1, expected_count + 1):
        if n not in parsed:
            raise BatchValidationError(
                f"Missing line [{n}] in LLM response (expected {expected_count} lines)"
            )
        text = parsed[n]
        # Collapse a <<BR>> emitted together with a real newline at the same break so
        # the cue does not gain a doubled blank line (B1 fix).
        text = re.sub(r"<<\s*BR\s*>>[ \t]*\n", "\n", text)
        text = re.sub(r"\n[ \t]*<<\s*BR\s*>>", "\n", text)
        text = _BR_RE.sub("\n", text)
        # Strip a LEADING echoed Pass-3 pronoun hint (job-9 incident, 260608-e8r).
        # "(speaker says: X; addresses as: Y)" is an English instruction phrase that
        # CANNOT appear in genuine Vietnamese dialogue. Stripping only the leading prefix
        # leaves the actual translation intact. If the model echoed the hint with NO dialogue,
        # the result is empty → the existing empty-check below raises BatchValidationError
        # → IMP-02's correction loop retries the batch (desired).
        # A source-present paren "(Phàm Nhân Tu Tiên Ký)" does NOT match "speaker says:"
        # so it is preserved — guards the 260607-iab paren-preservation win.
        # MOAT INVARIANT: this strip touches ONLY the echoed instruction text, not the
        # translated dialogue pronouns. validate.py Check 8 / HINT_SCAFFOLD_RE remains
        # the defense-in-depth backstop for any leak this strip does not catch.
        text = _LEAKED_HINT_RE.sub("", text)
        # Strip a LEADING echoed Vietnamese-label pronoun hint (260612-7kt, 2026-06-12).
        # '(tại hạ nói: tại hạ; xưng hô: cô nương)' is the translated-label variant of
        # the English hint echo above.  Chained AFTER _LEAKED_HINT_RE (the two are sibling
        # patterns — English first, Vietnamese second; applying them both is safe because
        # they match non-overlapping forms). validate.py Check 8 / VN_HINT_SCAFFOLD_RE is
        # the defense-in-depth backstop for any leaked VN-label hint this strip misses.
        text = _LEAKED_VN_HINT_RE.sub("", text)
        # Strip a LEADING echoed gate-repair directive (IMP-02b, 2026-06-08).
        # "[CORRECTION REQUIRED] ..." is an English internal-machinery phrase injected as
        # a RULES instruction in the repair prompt. A leading echo collapses to empty →
        # BatchValidationError → correction loop retries (same recovery as hint-strip above).
        # validate.py Check 8 / CORRECTION_DIRECTIVE_RE is the gate-layer backstop.
        text = _LEAKED_DIRECTIVE_RE.sub("", text)
        parsed[n] = text
        if not parsed[n].strip():
            raise BatchValidationError(f"Empty/whitespace-only text for line [{n}] in LLM response")

    if len(parsed) < expected_count:
        raise BatchValidationError(f"Parsed {len(parsed)} lines but expected {expected_count}")

    return [parsed[n] for n in range(1, expected_count + 1)]


# ── Batch translation with message-accumulating correction loop ────────────────

# ── IMP-02b: gate-level cue repair constants ──────────────────────────────────

# Checks whose failure is REPAIRABLE (i.e. only the translation content is wrong,
# not a structural mismatch). Structural checks {1,2,4,5,6,7,8} fall straight to
# quarantine — they indicate a pipeline/codec problem that re-translating cannot fix.
_REPAIRABLE_CHECKS: frozenset[int] = frozenset({3, 9, 10, 11, 12})

# Per-check correction directives forwarded to the repair LLM (IMP-02b).
# IMP-02b FIX 1(a): directives are now injected via build_translate_prompt's
# correction_directive param (as a RULE with "[CORRECTION REQUIRED]" prefix), NOT via
# context_before. The e8r/job-9 incident proved deepseek echoes context-line instructions
# verbatim into output cues; RULE-block injection is significantly less echo-prone.
# FIX 4: "huynh" removed from the Check-11 suggestion list — it is a DIRECTED seniority
# term that can cause an age/seniority inversion when the repair has no attribution.
# Non-directed / safe-default terms only: cô / cô nương / tiền bối / trưởng lão / các hạ.
_REPAIR_DIRECTIVE: dict[int, str] = {
    3: (
        "One or more lines lacked Vietnamese diacritics (possible source-language passthrough). "
        "Translate EVERY line in full Vietnamese with proper diacritics."
    ),
    9: (
        "One or more lines contained CJK/Hangul/Kana script (source leak). "
        "Translate ALL script characters into Vietnamese — output NO CJK, Hangul, or Kana codepoints."
    ),
    10: (
        "One or more lines appear to be source-language passthrough (no Vietnamese diacritics, "
        "all tokens matching source). Translate fully into Vietnamese."
    ),
    11: (
        "A prior attempt left an English honorific+name untranslated (e.g. 'Miss Mei', 'Mr. Han'). "
        "Render EVERY name in its Vietnamese Hán-Việt form and EVERY honorific/title as a "
        "non-directed kinship/address word (cô / cô nương / tiền bối / trưởng lão / các hạ / …). "
        "NEVER output an English honorific like 'Miss/Mr/Elder + Name'."
    ),
    12: (
        "A prior attempt added an English-gloss parenthetical (e.g. '(Miss Mei\\'s brother)'). "
        "NEVER add parentheticals not in the source. "
        "Remove any English-gloss parenthetical from the output."
    ),
}


# Module-level correction-turn template (D-18, IMP-02).
#
# MOAT INVARIANT: this template references pronoun hints as "from my FIRST message"
# and contains NO slot for pronoun-pair content — the hint/glossary/register live
# exclusively in messages[0] (the original prompt from build_translate_prompt).
# The correction turn NEVER re-emits "(speaker says: …)" content.
# Test B in test_batch_self_correct.py asserts "(speaker says:" is absent.
_STRUCT_CORRECTION_MSG = (
    "Your response had a structural error: {defect}. "
    "I need EXACTLY {n} lines, numbered [1] through [{n}], one per source line, in order. "
    "Do NOT skip any number. Keep every <<T0>>/<<BR>> token exactly as in my first message. "
    "Follow ALL rules, the GLOSSARY, the REGISTER, and all pronoun hints from my FIRST message. "
    "Output ONLY the {n} numbered lines."
)


def _make_translate_batch_fn(settings: "TrezarrSettings"):
    """Build a _translate_batch function bound to settings.

    The correction loop parameters depend on settings.translate_batch_retry_attempts,
    which is only known at runtime.  We construct the inner function once per
    translate_file() call so the attempt budget is correct.

    Design (D-18, IMP-02): the returned function is a plain async def with no tenacity
    decorator. BatchValidationError is handled exclusively by an internal bounded
    message-accumulating correction loop — NOT tenacity. Tenacity is removed from this
    function entirely (it was only needed for the retry-on-error pattern, which the
    correction loop now owns). openai.APIError propagates unmodified; the SDK handles
    transport-level retries (D-07, Pitfall 5).
    """
    attempts = (
        settings.translate_batch_retry_attempts + 1
    )  # total LLM calls = 1 initial + N retries

    async def _translate_batch_inner(
        batch: Batch,
        llm_client: LLMClient,
        _settings: "TrezarrSettings",
        pronoun_hints: "dict[int, tuple[str, str]] | None" = None,
        model: "str | None" = None,  # D-113: per-call model override
        glossary: "list[str] | None" = None,
        register: "str | None" = None,  # H1 fix: thread series register into Pass-3
        correction_directive: "str | None" = None,  # IMP-02b FIX 1(a): repair directive as RULE
        collector: "PassStatsCollector | None" = None,  # 260612-1tm: per-pass metrics
    ) -> list[str]:
        """Translate a single batch with a bounded message-accumulating correction loop (D-18).

        Steps:
          1. Extract sentinels from each cue's text (D-12)
          2. Build numbered-line prompt with context (D-13, D-15)
          3. Initialize messages = [{"role": "user", "content": prompt}]
          4. Loop up to `attempts` times:
               a. Call LLMClient.call(messages) — NEVER bypassed, NEVER wrapped in a second Semaphore
               b. Parse the numbered-line response + reinsert sentinels
               c. On success: return restored texts
               d. On BatchValidationError: if last attempt → raise; else append bad reply +
                  correction user-turn to messages and continue

        The original prompt in messages[0] stays authoritative and is never re-emitted or
        paraphrased, protecting the pronoun-hint moat (MOAT INVARIANT).

        openai.APIError propagates unmodified — the SDK handles transport-level retries
        (D-07, Pitfall 5). No tenacity wrapper. No second asyncio.Semaphore (D-06, Pitfall 1).

        Args:
            batch:                The Batch to translate.
            llm_client:           The LLM client to call.
            _settings:            Settings (passed through; not used in body).
            pronoun_hints:        Optional {1-based line index → (self_term, address_term)} (D-46).
            model:                Optional per-call model override (D-113).
            glossary:             Optional glossary lines for proper noun pinning.
            register:             Optional series register/tone (H1 fix).
            correction_directive: Optional IMP-02b gate-repair correction instruction
                                  (injected as a RULE in build_translate_prompt, not context_before).

        Returns:
            List of translated text strings (one per cue in batch.cues).

        Raises:
            BatchValidationError: After translate_batch_retry_attempts+1 total LLM calls
                                  with no valid response. Propagates to translate_file → quarantine.
        """
        # Step 1: Extract sentinels from each cue
        cleaned_texts: list[str] = []
        sentinel_maps: list[dict[str, str]] = []
        for cue in batch.cues:
            cleaned, smap = extract_sentinels(cue.text)
            cleaned_texts.append(cleaned)
            sentinel_maps.append(smap)

        # Step 2: Build the numbered-line prompt (D-46: forward pronoun_hints)
        context_before_texts = [c.text for c in batch.context_before]
        context_after_texts = [c.text for c in batch.context_after]
        prompt = build_translate_prompt(
            cleaned_texts,
            context_before_texts,
            context_after_texts,
            pronoun_hints=pronoun_hints,
            glossary=glossary,
            register=register,  # H1 fix
            correction_directive=correction_directive,  # IMP-02b FIX 1(a)
        )

        # Step 3: Initialize message list — messages[0] stays the sole authoritative
        # carrier of hints/glossary/register. The correction loop NEVER re-emits it.
        messages: list[dict] = [{"role": "user", "content": prompt}]

        # Step 4: Bounded correction loop — up to `attempts` total LLM calls
        _ml_idx = {i for i, t in enumerate(cleaned_texts, 1) if "\n" in t}
        n = len(batch.cues)

        for attempt_num in range(attempts):
            is_last_attempt = attempt_num == attempts - 1

            # Step 4a: Call LLMClient — the sole concurrency gate is inside LLMClient._semaphore
            # D-113: forward per-call model override; None = use client's global model
            # Pass-3 stays fast: no thinking= kwarg (Pass-1/Pass-2 get thinking=True per FIX-B)
            # 260612-1tm: forward per-pass collector for duration + token capture
            raw_response = await llm_client.call(messages, model=model, collector=collector)

            try:
                # Step 4b: Parse + reinsert sentinels — both raise BatchValidationError on failure.
                # MEDIUM-4: only multi-line source cues accept continuation lines.
                translated_texts = parse_numbered_response(
                    str(raw_response), n, multiline_indices=_ml_idx
                )

                # Reinsert sentinels. Always call (even for an empty smap) so a hallucinated
                # orphan <<TN>> in an untagged cue is stripped rather than surviving to the
                # document gate → whole-file quarantine (v1.0 #5).
                # integrity_ok is False only on a LOST REAL sentinel — structural failure,
                # triggers the correction loop just like a wrong count.
                restored: list[str] = []
                for i, (text, smap) in enumerate(zip(translated_texts, sentinel_maps)):
                    restored_text, integrity_ok = reinsert_sentinels(text, smap)
                    if not integrity_ok:
                        raise BatchValidationError(
                            f"Sentinel integrity failure for cue {i}: "
                            f"real sentinel(s) lost from {restored_text!r}"
                        )
                    restored.append(restored_text)

                # Step 4c: Success — return translated texts
                return restored

            except BatchValidationError as exc:
                if is_last_attempt:
                    # Step 4d (budget exhausted): re-raise so translate_file can quarantine.
                    # This is the ONLY place BatchValidationError escapes — tenacity does
                    # NOT add another retry layer on top (no double-retry storm, IMP-02 Test E).
                    raise

                # Step 4d (correction turn): append the bad reply + a structural-only correction
                # user turn to the messages list. messages[0] is NEVER touched — it remains the
                # sole authoritative carrier of hints/glossary/register (MOAT INVARIANT).
                # The correction turn references them as "from my FIRST message" without quoting.
                correction_turn = _STRUCT_CORRECTION_MSG.format(defect=str(exc), n=n)
                messages.append({"role": "assistant", "content": str(raw_response)})
                messages.append({"role": "user", "content": correction_turn})
                # Continue to next loop iteration — LLM will see the full conversation context

        # Unreachable: loop always returns or raises inside. Guard for type checker.
        raise BatchValidationError(
            "Correction loop exhausted without returning"
        )  # pragma: no cover

    return _translate_batch_inner


async def _translate_batch(
    batch: Batch,
    llm_client: LLMClient,
    settings: "TrezarrSettings",
    pronoun_hints: "dict[int, tuple[str, str]] | None" = None,
    model: "str | None" = None,  # D-113: per-call model override
    glossary: "list[str] | None" = None,
    register: "str | None" = None,  # H1 fix: thread series register into Pass-3
    correction_directive: "str | None" = None,  # IMP-02b FIX 1(a): repair directive as RULE
    collector: "PassStatsCollector | None" = None,  # 260612-1tm: per-pass metrics
) -> list[str]:
    """Public entry point for translating a single batch with the correction loop.

    Thin wrapper that builds a settings-bound inner function and calls it.
    Exposed as a module-level name for testing (test_engine.py).

    Args:
        batch:                The Batch to translate.
        llm_client:           The LLM client to call.
        settings:             Settings supplying translate_batch_retry_attempts.
        pronoun_hints:        Optional {1-based line index → (self_term, address_term)} (D-46).
        model:                Optional per-call model override (D-113).
        glossary:             Optional glossary lines for proper noun pinning.
        register:             Optional series register/tone (H1 fix).
        correction_directive: Optional IMP-02b gate-repair correction instruction.
        collector:            Optional PassStatsCollector for per-call duration + token capture
                              (260612-1tm). Forwarded to _translate_batch_inner and then to
                              llm_client.call(). None = no metrics (zero regression).

    Returns:
        List of translated text strings.

    Raises:
        BatchValidationError: If all correction-loop retries are exhausted.
    """
    fn = _make_translate_batch_fn(settings)
    return await fn(
        batch, llm_client, settings, pronoun_hints, model, glossary, register,
        correction_directive, collector,
    )


# ── Quarantine artifact write ──────────────────────────────────────────────────


def _write_quarantine(
    source_path: Path,
    reason: str,
    failing_indices: list[int],
    settings: "TrezarrSettings",
) -> Path:
    """Write a quarantine JSON artifact for a failed translation (D-18, T-02-03-03).

    The artifact contains only: reason, failing_cue_indices, timestamp, source_path.
    It intentionally does NOT include cue text — source subtitles may be proprietary
    (T-02-03-03: information disclosure control).

    Args:
        source_path:     Absolute path to the source SRT file.
        reason:          Human-readable failure description.
        failing_indices: List of cue indices that triggered the failure.
        settings:        Settings supplying translate_quarantine_dir.

    Returns:
        Path to the written quarantine JSON file.
    """
    quarantine_dir = Path(settings.translate_quarantine_dir)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    artifact_name = source_path.stem + ".json"
    quarantine_path = quarantine_dir / artifact_name

    artifact = {
        "reason": reason,
        "failing_cue_indices": failing_indices,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        # NOTE: cue text is explicitly excluded — T-02-03-03 (proprietary content)
    }

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            dir=quarantine_dir,
            delete=False,
        ) as f:
            tmp_path = Path(f.name)
            json.dump(artifact, f, indent=2)
        os.replace(tmp_path, quarantine_path)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()

    return quarantine_path


def _splice_review_corrections(
    translated_lines: list[SubLine],
    review_batches: "list[Batch]",
    review_results: "list[list[str] | None]",
) -> list[SubLine]:
    """Apply Pass-4 self-review corrections back onto the translated document.

    CR-02 (D-98/D-99): ``review_batches`` come from ``batch_subdoc``, which SKIPS
    raw-flagged (karaoke/drawing) cues — so ``rb.cues`` spans only the NON-raw
    cues, in document order. ``translated_lines`` contains ALL cues, with raw
    cues interleaved at their original positions. We flatten the corrections to
    one entry per non-raw cue, then walk the full document and advance the
    correction pointer ONLY on non-raw cues; raw cues are appended verbatim.
    Indexing by a non-raw running offset (the old approach) overwrote raw
    pass-through slots and misaligned every subsequent cue (FMT-03 violation).

    Returns a new list of SubLine objects — never mutates the inputs (Pitfall 8).
    """
    # One entry per non-raw cue, in document order: (cue, new_text) or None.
    corrections: list = []
    for rb, corrected_texts in zip(review_batches, review_results):
        if corrected_texts is None:
            corrections.extend([None] * len(rb.cues))
        else:
            # Align defensively to rb.cues length (contract: _review_batch returns
            # one text per cue) so the per-batch entry count always matches.
            for idx in range(len(rb.cues)):
                if idx < len(corrected_texts):
                    corrections.append((rb.cues[idx], corrected_texts[idx]))
                else:
                    corrections.append(None)

    corr_iter = iter(corrections)
    result: list[SubLine] = []
    for line in translated_lines:
        if line.raw is not None:
            # Raw pass-through (karaoke/drawing) — never reviewed; preserve verbatim.
            result.append(line)
            continue
        corr = next(corr_iter)
        if corr is None:
            result.append(line)  # batch returned no correction — keep translated
        else:
            cue, new_text = corr
            result.append(
                SubLine(
                    index=cue.index,
                    start_tc=cue.start_tc,
                    end_tc=cue.end_tc,
                    text=new_text,
                    raw=None,
                )
            )
    return result


# ── pbz: Deterministic envelope preservation ──────────────────────────────────

_OPENER_MAP: dict[str, str] = {"(": ")", "[": "]"}


def _preserve_source_envelopes(
    translated_doc: "SubDoc",
    source_doc: "SubDoc",
    settings: "TrezarrSettings",
) -> "SubDoc":
    """Re-wrap translated cues whose source was fully enclosed in a single outer bracket pair.

    Pure sync function — no LLM, no DB, no async. Returns a new SubDoc carrying all
    metadata (encoding/line_ending/separators/leading/trailer/envelope) forward from
    translated_doc (D-92 pattern). Never mutates the input SubLines (Pitfall 8).

    Full-enclosure detection — THREE steps that ALL must pass:

    Step A: stripped source text starts with an opener ('(' or '[') and ends with
            its matching closer. If not, the cue is not a bracket envelope → skip.

    Step B: bracket-depth scan over stripped source, counting ONLY the Step-A bracket
            type. Depth increments on opener, decrements on closer.
            - If depth reaches 0 BEFORE the final character: the two groups share the
              same bracket type but are NOT one spanning envelope (e.g. "(a) and (b)")
              → NOT enclosed → skip.
            - After the full scan, depth == 0 with no premature close → fully enclosed.

    Step C: idempotency guard. If the stripped translated text already starts with the
            opener AND ends with the closer → the wrapper is already present → no-op.

    Re-wrap: prepend opener and append closer to the ORIGINAL (un-stripped) translated
    text, preserving any internal leading/trailing whitespace the LLM may have left.
    Construct a new SubLine with index/start_tc/end_tc copied verbatim from the source
    line (D-ENV-06: byte identity) and raw=None (well-formed translated cue).

    enable_envelope_preservation=False bypasses this function (complete no-op, D-ENV-08).
    """
    if not settings.enable_envelope_preservation:
        return translated_doc

    new_lines: list[SubLine] = []
    for src_line, trn_line in zip(source_doc.lines, translated_doc.lines):
        # D-ENV-05: raw/opaque cues (karaoke/drawing) are skipped verbatim.
        if trn_line.raw is not None:
            new_lines.append(trn_line)
            continue

        # Step A: check that stripped source is opened and closed by a matching bracket pair.
        stripped_src = src_line.text.strip()
        if len(stripped_src) < 2:
            new_lines.append(trn_line)
            continue
        first_char = stripped_src[0]
        if first_char not in _OPENER_MAP:
            new_lines.append(trn_line)
            continue
        opener = first_char
        closer = _OPENER_MAP[opener]
        if stripped_src[-1] != closer:
            new_lines.append(trn_line)
            continue

        # Step B: bracket-depth scan — only the Step-A bracket type participates.
        # A premature return to depth 0 (before the final index) means two separate
        # groups, not a single spanning envelope.
        depth = 0
        not_enclosed = False
        final_idx = len(stripped_src) - 1
        for i, ch in enumerate(stripped_src):
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
            if depth == 0 and i < final_idx:
                # Bracket closed before the end of the string — two-group form → skip.
                not_enclosed = True
                break
        if not_enclosed or depth != 0:
            new_lines.append(trn_line)
            continue

        # Step C: idempotency — if the translation is already wrapped, do nothing.
        stripped_trn = trn_line.text.strip()
        if stripped_trn.startswith(opener) and stripped_trn.endswith(closer):
            new_lines.append(trn_line)
            continue

        # Re-wrap: prepend/append to the ORIGINAL text (not the stripped form) so
        # any internal whitespace retained by the LLM is preserved.
        new_text = opener + trn_line.text + closer
        new_lines.append(
            SubLine(
                index=src_line.index,
                start_tc=src_line.start_tc,
                end_tc=src_line.end_tc,
                text=new_text,
                raw=None,
            )
        )

    return SubDoc(
        lines=new_lines,
        encoding=translated_doc.encoding,
        line_ending=translated_doc.line_ending,
        separators=translated_doc.separators,
        leading=translated_doc.leading,
        trailer=translated_doc.trailer,
        envelope=translated_doc.envelope,
    )


# ── IMP-02b: Gate-level cue repair helper ─────────────────────────────────────


async def _repair_failing_cues(
    failing_indices: list[int],
    source_doc: SubDoc,
    translated_doc: SubDoc,
    check_number: int,
    llm_client: LLMClient,
    settings: "TrezarrSettings",
    glossary_lines: "list[str] | None",
    register_value: "str | None",
    resolved_map: dict,
    bible: object,
    model: "str | None",
    flat_attributions: "list | None" = None,
    name_to_char_id: "dict[str, int] | None" = None,
) -> "list[SubLine] | None":
    """Re-translate only the failing source cues and return a full repaired lines list.

    Returns a NEW list of SubLine objects (same length as translated_doc.lines) with
    only the failing indices replaced by fresh translations.  Returns None on a
    BatchValidationError (genuine "repair couldn't produce a valid translation");
    all other exceptions (including openai.APIError) propagate so the file is NOT
    permanently quarantined on a transient endpoint error (D-47 / Pitfall B).

    MOAT INVARIANT: re-translates through the SAME _translate_batch machinery that
    Pass-3 uses, forwarding the same glossary_lines, register_value, and directed
    pronoun hints for the failing cue indices (built from flat_attributions + resolved_map
    when attribution data is available) — so Bible consistency and the pronoun/relational
    moat are preserved. Pitfall 1: no new asyncio.Semaphore. Pitfall 5: no tenacity.

    Args:
        failing_indices:   0-based indices into translated_doc.lines that failed the gate.
        source_doc:        The original source SubDoc.
        translated_doc:    The translated SubDoc (with the failing cues).
        check_number:      The gate check number that fired (must be in _REPAIRABLE_CHECKS).
        llm_client:        LLMClient instance (its _semaphore is the sole concurrency gate).
        settings:          TrezarrSettings.
        glossary_lines:    Glossary lines from build_glossary_lines(bible), or None.
        register_value:    Series register/tone from bible.register_value, or None.
        resolved_map:      (speaker_id, addressee_id) → (self_term, address_term) from reconcile.
        bible:             SeriesBibleDTO (or None for Bible-unaware mode).
        model:             Per-call model override (D-113).
        flat_attributions: Doc-global list of LineAttribution objects (1:1 with source cues),
                           or None when the Phase-5 attribution pass is inactive. Used to
                           thread the directed pronoun hint for each failing cue (FIX 3).
        name_to_char_id:   Lowercased character name → character id reverse index
                           (built from bible.characters in translate_file). Used with
                           flat_attributions to resolve hints. None when inactive.

    Returns:
        Full repaired list[SubLine] on success; None on BatchValidationError (repair miss).

    Raises:
        openai.APIError:  Propagates unmodified — transient transport failure; caller
                          leaves the file in_progress for retry next poll (D-47/Pitfall B).
        Any other non-BatchValidationError exception: propagates so bugs are loud.
    """
    # FIX 2: narrow exception handling — only BatchValidationError is a "repair miss"
    # (the LLM produced something structurally invalid after retries). Everything else
    # (openai.APIError transport, RuntimeError empty-content, IndexError logic bug)
    # propagates unmodified. This mirrors the Step-7 main translate path which catches
    # ONLY BatchValidationError and lets APIError propagate (engine.py:1628).
    try:
        directive = _REPAIR_DIRECTIVE.get(check_number, "")

        # Build a minimal Batch containing only the failing source cues.
        # FIX 5: skip repair for any failing index where the source line is raw
        # (opaque pass-through / ASS-VTT styling — D-98/D-99). Repairable checks
        # {3,9,10,11,12} already skip raw cues in validate.py so this cannot fire today,
        # but the splice must not assume it — defensively preserve the original raw cue.
        failing_source_cues: list[SubLine] = []
        repair_batch_local_indices: list[int] = []  # doc-global indices that enter the repair batch
        for doc_idx in failing_indices:
            line = translated_doc.lines[doc_idx]
            if line.raw is not None:
                # Opaque pass-through — cannot be re-translated; keep verbatim (FIX 5).
                logger.debug(
                    "Skipping repair for raw/opaque cue at index %d (D-98/D-99 pass-through)",
                    doc_idx,
                )
                continue
            failing_source_cues.append(source_doc.lines[doc_idx])
            repair_batch_local_indices.append(doc_idx)

        if not failing_source_cues:
            # All failing indices were raw — nothing to repair.
            return None

        repair_batch = Batch(
            cues=failing_source_cues,
            context_before=[],
            context_after=[],
        )

        # FIX 3: thread the directed pronoun hint for each failing cue into the repair batch.
        # flat_attributions is doc-globally ordered 1:1 with source cues; failing_indices are
        # 0-based doc-global indices. For each failing cue at doc index i, if attribution
        # is present (flat_attributions[i].speaker / .addressee), resolve to char ids via
        # name_to_char_id (exact-first, honorific-fallback per _resolve_char_id), then look up
        # resolved_map[(spk_id, addr_id)] → (self_term, addr_term). Key the hint by the repair
        # batch's LOCAL 1-based index (position among failing_source_cues). Missing attribution
        # for a cue → no hint → safe-default floor (current behavior) — so the safe path is
        # preserved exactly where attribution is genuinely absent.
        repair_pronoun_hints: dict[int, tuple[str, str]] | None = None
        if flat_attributions and name_to_char_id and resolved_map:
            _batch_hints: dict[int, tuple[str, str]] = {}
            for local_idx, doc_idx in enumerate(repair_batch_local_indices, 1):
                if doc_idx >= len(flat_attributions):
                    continue
                attr = flat_attributions[doc_idx]
                spk_id = _resolve_char_id(name_to_char_id, getattr(attr, "speaker", None))
                addr_id = _resolve_char_id(name_to_char_id, getattr(attr, "addressee", None))
                if spk_id is not None and addr_id is not None:
                    hint = resolved_map.get((spk_id, addr_id))
                    if hint is not None:
                        _batch_hints[local_idx] = hint
            if _batch_hints:
                repair_pronoun_hints = _batch_hints

        # FIX 1(a): pass the correction directive via build_translate_prompt's
        # correction_directive param (injected as a RULE with "[CORRECTION REQUIRED]" prefix),
        # NOT via context_before. context_before is rendered under a "read only, do not output"
        # block that the e8r/job-9 incident proved deepseek ignores — instruction-block injection
        # is significantly less echo-prone. The "[CORRECTION REQUIRED]" marker prefix ensures
        # any echo is catchable by _LEAKED_DIRECTIVE_RE and validate.py CORRECTION_DIRECTIVE_RE.
        repair_directive_str = directive if directive else None

        # Re-use _translate_batch (which goes through LLMClient._semaphore — no new Semaphore).
        repair_translated_texts = await _translate_batch(
            repair_batch,
            llm_client,
            settings,
            pronoun_hints=repair_pronoun_hints,
            model=model,
            glossary=glossary_lines,
            register=register_value,
            correction_directive=repair_directive_str,
        )

        # Build the full repaired SubLine list: walk translated_doc.lines, splice at
        # failing indices.  Preserve index/start_tc/end_tc byte-identically from
        # translated_doc; replace ONLY .text.  NEVER mutate source SubLines (Pitfall 8).
        repair_text_iter = iter(repair_translated_texts)
        repaired_lines: list[SubLine] = []
        repair_set = set(repair_batch_local_indices)  # doc-global indices that were re-translated
        for i, line in enumerate(translated_doc.lines):
            if i in repair_set:
                new_text = next(repair_text_iter)
                repaired_lines.append(
                    SubLine(
                        index=line.index,
                        start_tc=line.start_tc,
                        end_tc=line.end_tc,
                        text=new_text,
                        raw=None,
                    )
                )
            elif i in set(failing_indices):
                # FIX 5: raw cue that was skipped — preserve verbatim (D-98/D-99).
                repaired_lines.append(
                    SubLine(
                        index=line.index,
                        start_tc=line.start_tc,
                        end_tc=line.end_tc,
                        text=line.text,
                        raw=line.raw,
                    )
                )
            else:
                repaired_lines.append(
                    SubLine(
                        index=line.index,
                        start_tc=line.start_tc,
                        end_tc=line.end_tc,
                        text=line.text,
                        raw=line.raw,
                    )
                )

        return repaired_lines

    except BatchValidationError:
        # FIX 2: genuine repair miss — the LLM could not produce a valid translation
        # after all retries. Return None so the caller can quarantine immediately.
        # Unlike openai.APIError (transient transport, should propagate), this is a
        # validation-logic failure that means this specific repair attempt failed.
        logger.warning(
            "Gate repair batch validation failed for check=%d failing=%r — quarantining",
            check_number,
            failing_indices,
            exc_info=True,
        )
        return None


# ── Main entry point ───────────────────────────────────────────────────────────


async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: LedgerProtocol,
    eligible_item: "EligibleItem | None" = None,
    session_factory: "async_sessionmaker[AsyncSession] | None" = None,
    model: str | None = None,  # D-113: per-call model override; threads to llm_client.call()
) -> TranslationResult:
    """Translate a source subtitle file to Vietnamese and write a vi sidecar.

    This is the Phase-3-callable entry point for the translation pipeline.
    Phase-5 extension (D-48): when eligible_item and session_factory are provided,
    runs the three-pass pronoun engine:
      Pass 1 (BARRIER): analyze_file + merge_bible_analysis
      Pass 2: attribute_batch (gather over batches)
      Reconcile: reconcile_attributions → resolved_map
      Pass 3: translate with pronoun hints from resolved_map

    Steps:
      1. Resolve path to absolute; read source bytes; compute content hash
      2. Derive destination vi sidecar path (mirrors source extension — D-95)
      3. Ledger check (D-20 behavior table):
         - done + dest.exists() + hash matches → skip (idempotent no-op)
         - dest.exists() + not in ledger → foreign file, skip + log
         - quarantined → proceed (retry)
         - in_progress → proceed (previous run crashed)
         - not in ledger → proceed
      4. Record in_progress in ledger
      5. read_srt() → source SubDoc
      6. batch_subdoc() → list[Batch]
      4.5 (Phase 5): Pass 1 BARRIER → Pass 2 gather → reconcile → resolved_map
      7. asyncio.gather() dispatches all batches concurrently (with pronoun hints)
      8. Assemble translated SubDoc (new SubLine objects — never mutate source)
      9. validate_subdoc() document-level gate
      10. write_vi_sidecar() atomic UTF-8 write
      11. ledger.record(status="done")
      12. Return TranslationResult(status="done")

    On any failure (retry exhaustion or gate failure):
      - Write quarantine artifact (no cue text — T-02-03-03)
      - ledger.record(status="quarantined")
      - Return TranslationResult(status="quarantined")

    Pass 1 BibleAnalysisError → quarantine (never on openai.APIError — Pitfall B).

    Args:
        path:            Path to the source SRT file (str or Path; resolved to absolute).
        settings:        TrezarrSettings supplying all pipeline configuration.
        llm_client:      LLMClient instance (Phase-1, semaphore-gated).
        ledger:          Ledger instance for idempotency tracking.
        eligible_item:   EligibleItem from discovery (D-48, Phase 5). When None,
                         the three-pass Bible logic is bypassed (backward compat).
        session_factory: Async session factory for Bible DB (D-48, Phase 5). When None,
                         the three-pass Bible logic is bypassed.

    Returns:
        TranslationResult with status "done", "skipped", or "quarantined".
    """
    # Step 1: Resolve path and compute content hash
    path = Path(path).resolve()
    source_bytes = path.read_bytes()
    content_hash = ledger.content_hash(source_bytes)

    # Step 2: Derive destination path via the shared helper so engine and writer
    # can never diverge on naming (WR-06).
    dest = derive_vi_sidecar_path(path)

    # Step 3: Ledger check (D-20 behavior table)
    entry = await ledger.check(str(path))

    # Foreign file: dest exists but source_path not in ledger → skip + log (T-02-03-04)
    # WR-02 / D-110 Case 1.5: before skipping, check if Trezarr owns this vi sidecar
    # via a DIFFERENT (lower-priority) source path. If so, this is a richer-source
    # upgrade approved by gap.is_eligible — proceed instead of skipping.
    # Only skip when check_by_output_path also returns None (truly foreign vi, D-26).
    if entry is None and dest.exists():
        prior_entry = await ledger.check_by_output_path(str(dest))
        if prior_entry is None:
            # Truly foreign vi sidecar — not written by Trezarr. D-26: never clobber.
            logger.info("foreign vi sidecar at %s, not ours — skipping %s", dest, path)
            return TranslationResult(status="skipped")
        # Trezarr wrote this vi from a different source (prior_entry.source_path).
        # The current path is a richer source — proceed with the upgrade (D-110).
        logger.info(
            "richer source upgrade: re-translating %s (prior source: %s)",
            path,
            prior_entry.source_path,
        )

    # Already done + dest exists + hash matches → idempotent skip
    if (
        entry is not None
        and entry.status == "done"
        and dest.exists()
        and entry.content_hash == content_hash
    ):
        return TranslationResult(status="skipped")

    # 260612-1tm: per-pass metrics collectors + wall-clock durations.
    # Initialized to zero here so the job_summary line always fires with safe defaults
    # even if a pass is bypassed (passthrough mode, enable_attribution=False, etc.).
    # Collectors for Pass 1/2 are wall-clock-only (analyze_file/attribute_batch don't
    # accept collector= yet); tokens for those passes will show 0 in the summary.
    _p1_col = PassStatsCollector()
    _p2_col = PassStatsCollector()
    _p3_col = PassStatsCollector()
    _p4_col = PassStatsCollector()
    _p1_dur: float = 0.0
    _p2_dur: float = 0.0
    _p3_dur: float = 0.0
    _p4_dur: float = 0.0

    # Step 4: Record in_progress (in case this run crashes mid-flight)
    await ledger.record(
        LedgerEntry(
            source_path=str(path),
            output_path=str(dest),
            status="in_progress",
            content_hash=content_hash,
        )
    )

    # Steps 5-6: Read and batch the source.  Both can raise on poisoned source files
    # (PermissionError, decode errors, malformed SRT).  A raise here would leave the
    # ledger at in_progress forever — catch and quarantine per the function contract.
    try:
        source_doc = read_subtitle(path)
        batches = batch_subdoc(source_doc, settings)
    except Exception as exc:
        reason = f"read/batch failure: {exc}"
        quarantine_path = _write_quarantine(path, reason, [], settings)
        await ledger.record(
            LedgerEntry(
                source_path=str(path),
                output_path=None,
                status="quarantined",
                content_hash=content_hash,
                quarantine_path=str(quarantine_path),
            )
        )
        return TranslationResult(
            status="quarantined",
            quarantine_path=quarantine_path,
            reason=reason,
        )

    # Step 4.5 (Phase 5, D-48): Three-pass pronoun engine.
    # Bypassed when eligible_item or session_factory is None (backward compat).
    # No new asyncio.Semaphore here — all LLM calls go through LLMClient._semaphore (D-06, Pitfall A).
    # WR-02: gate only on eligible_item+session_factory — NOT on enable_pass1_analysis.
    # Each pass honours its own toggle internally:
    #   analyze_file()  → early-returns on enable_pass1_analysis=False (analyze.py:244)
    #   attribute_batch → skips on enable_attribution=False (attribute.py:278)
    # Coupling the engine gate to enable_pass1_analysis silently disabled attribution
    # and reconciliation whenever Pass 1 was toggled off, contrary to D-50 semantics.
    resolved_map: dict[tuple[int, int], tuple[str, str]] = {}
    flat_attributions: list = []
    bible = None  # populated below when Phase-5 path is active

    # D-06: extract arr_series_id outside the session_factory guard so it is available
    # for the Step 11 ledger.record() call regardless of whether session_factory is provided.
    # When eligible_item is None (passthrough mode), arr_series_id stays 0 (falsy → None in ledger).
    arr_series_id = (
        getattr(eligible_item.media_item, "series_id", None) or 0
        if eligible_item is not None
        else 0
    )

    if eligible_item is not None and session_factory is not None:
        from trezarr.bible.store import get_or_create_series, load_series_bible
        from trezarr.bible.analyze import analyze_file, merge_bible_analysis, BibleAnalysisError
        from trezarr.translate.attribute import attribute_batch
        from trezarr.translate.reconcile import reconcile_attributions

        media_item = eligible_item.media_item
        arr_kind = getattr(media_item, "arr_kind", None) or "sonarr"
        # arr_series_id already extracted above (D-06 fix) — reuse it here
        episode_key = derive_episode_key(media_item, path)

        # Build metadata snapshot (safe subset only — T-05-06-01)
        _SAFE_META_KEYS = (
            "title",
            "genres",
            "overview",
            "year",
            "network",
            "runtime",
            "tvdb_id",
            "tmdb_id",
        )
        arr_metadata: dict = {
            k: getattr(media_item, k, None)
            for k in _SAFE_META_KEYS
            if getattr(media_item, k, None) is not None
        }

        series_dto = await get_or_create_series(
            session_factory,
            arr_kind=arr_kind,
            arr_series_id=arr_series_id,
            arr_metadata_snapshot=arr_metadata,
            tvdb_id=getattr(media_item, "tvdb_id", None),
            tmdb_id=getattr(media_item, "tmdb_id", None),
        )

        bible = await load_series_bible(session_factory, series_dto.id)

        # PASS 1 BARRIER (D-40, ENG-04) — quarantine ONLY on BibleAnalysisError
        # (logic failure); openai.APIError must propagate (Pitfall B / T-05-06-02)
        # 260612-1tm: wall-clock timing only (analyze_file/merge_bible_analysis don't
        # accept collector=; token capture for Pass 1 is deferred to future wiring).
        _p1_t0 = time.perf_counter()
        try:
            analysis = await analyze_file(
                source_doc, bible, arr_metadata, llm_client, settings, episode_key
            )
            await merge_bible_analysis(
                session_factory, series_dto, analysis, episode_key, settings=settings
            )
        except BibleAnalysisError as exc:
            reason = f"pass1 analysis failure: {exc}"
            quarantine_path = _write_quarantine(path, reason, [], settings)
            await ledger.record(
                LedgerEntry(
                    source_path=str(path),
                    output_path=None,
                    status="quarantined",
                    content_hash=content_hash,
                    quarantine_path=str(quarantine_path),
                )
            )
            return TranslationResult(
                status="quarantined",
                quarantine_path=quarantine_path,
                reason=reason,
            )

        # 260612-1tm: record Pass 1 wall-clock duration and emit per-pass log line.
        _p1_dur = time.perf_counter() - _p1_t0
        logger.info("pass=1 duration_s=%.2f file=%s", _p1_dur, path.name)

        # Reload Bible so Pass 2/3 see the fresh Address Map (D-48)
        bible = await load_series_bible(session_factory, series_dto.id)

        # PASS 2 (D-43): concurrent attribution gather.
        # Build attribution batches with the WIDER context window (D-50/WR-01):
        # attribute_context_lines_k is typically 8 vs translate_context_lines_k=3.
        # batch_subdoc with context_lines_k= attaches more context lines per batch;
        # cue grouping is identical (K does not affect scene-gap/budget boundaries),
        # so flat_attributions aligns 1:1 with the Pass-3 batches below.
        if settings.enable_attribution:
            attr_batches = batch_subdoc(
                source_doc,
                settings,
                context_lines_k=settings.attribute_context_lines_k,
                max_cues_per_batch=settings.attribute_max_cues_per_batch,
            )
            # WR-04: TaskGroup cancels siblings on first failure; no orphaned tasks.
            # Attribution degrades gracefully (never raises BatchValidationError),
            # so no ExceptionGroup handling is needed here.
            # 260612-1tm: wall-clock timing only (attribute_batch doesn't accept collector=)
            _p2_t0 = time.perf_counter()
            async with asyncio.TaskGroup() as tg:
                attr_tasks = [
                    tg.create_task(attribute_batch(b, bible, llm_client, settings))
                    for b in attr_batches
                ]
            _p2_dur = time.perf_counter() - _p2_t0
            attr_per_batch = [t.result() for t in attr_tasks]
            flat_attributions = [a for batch_attrs in attr_per_batch for a in batch_attrs]
            logger.info("pass=2 duration_s=%.2f file=%s", _p2_dur, path.name)
        else:
            flat_attributions = []

        # RECONCILE (D-44): build resolved_map for Pass 3 pronoun hints
        resolved_map = await reconcile_attributions(
            flat_attributions, bible, session_factory, series_dto.id, episode_key, settings
        )

    # Build pronoun_hints per batch from resolved_map + flat_attributions (D-46, Pitfall E).
    # name_to_char_id bridges speaker/addressee name strings to character IDs.
    # Unknown names → no hint → safe default in Pass 3.
    per_batch_hints: list[dict[int, tuple[str, str]] | None] = [None] * len(batches)
    if resolved_map and bible is not None:
        # B3 fix: EXACT-keyed index (lowercased name → id); _resolve_char_id tries the exact
        # name first and only falls back to the honorific-stripped alias, so an honorific-prefixed
        # attribution name ("Elder Zhou") still resolves to the seeded row ("zhou") WITHOUT two
        # distinct characters that differ only by an honorific colliding onto one id.
        name_to_char_id: dict[str, int] = {
            c.original_latin_name.strip().lower(): c.id for c in bible.characters
        }
        # Build a doc-global index → attribution lookup from flat_attributions
        # flat_attributions are ordered: batch 0 line 1..N, batch 1 line 1..M, ...
        # Pitfall E: line_index in each LineAttribution is 1-based WITHIN its batch.
        doc_offset = 0
        for b_idx, batch in enumerate(batches):
            batch_size = len(batch.cues)
            batch_hints: dict[int, tuple[str, str]] = {}

            # Slice the flat_attributions for this batch
            batch_attrs = flat_attributions[doc_offset : doc_offset + batch_size]

            for local_i, attr in enumerate(batch_attrs, 1):
                spk_id = _resolve_char_id(name_to_char_id, attr.speaker)
                addr_id = _resolve_char_id(name_to_char_id, attr.addressee)
                if spk_id is not None and addr_id is not None:
                    # resolved_map includes carried Bible pairs (scy); hint fires for any fully-attributed line.
                    hint = resolved_map.get((spk_id, addr_id))
                    if hint is not None:
                        batch_hints[local_i] = hint

            per_batch_hints[b_idx] = batch_hints if batch_hints else None
            doc_offset += batch_size

    # Step 7: Dispatch all batches concurrently via TaskGroup (WR-04).
    # TaskGroup cancels sibling tasks on first failure, avoiding orphaned coroutines
    # that would otherwise keep consuming the LLM semaphore.
    # ONLY quarantine on BatchValidationError (retry-exhausted batch gate failure).
    # openai.APIError and any other exception propagate: the file stays out of "done"
    # and is retried on the next poll cycle.  Pitfall 5 / D-18: SDK handles transport
    # failures; never permanently quarantine on a transient endpoint error.
    # TaskGroup wraps failures in ExceptionGroup — use except* to unwrap (Python 3.11+).
    # NOTE: `return` is not allowed inside except* (Python 3.11+ restriction), so we
    # capture the quarantine result and return after the try/except* block.
    _batch_quarantine: TranslationResult | None = None
    batch_results: list[list[str]] = []
    # Glossary (character names + Term Dictionary) injected into every Pass-3 prompt so proper
    # nouns render IDENTICALLY across all cues (the consistency moat). Computed once per file;
    # None when Bible-unaware (mechanical fallback) so the prompt is unchanged there.
    glossary_lines = build_glossary_lines(bible) if bible is not None else None
    # H1 fix: thread the series register into Pass-3 so classical/xianxia tone reaches the
    # pass that actually writes the subtitle (Pass-4 review only nudges, never re-translates).
    # None when Bible-unaware → build_translate_prompt omits the [REGISTER] block (unchanged).
    register_value = getattr(bible, "register_value", None) if bible is not None else None
    # B2 fix (Check 10 source-passthrough allowlist): lowercased token set of every
    # Bible-pinned proper noun, so a no-diacritic cue made entirely of pinned names
    # (e.g. "Hàn", "Mai") is NOT mis-flagged as an English passthrough. Tokens come from
    # the glossary rendering (RHS of ' → '), character names, and term renderings + sources.
    # None when Bible-unaware so the gate stays in pure-structural mode.
    proper_noun_allowlist: set[str] | None = None
    if bible is not None:
        proper_noun_allowlist = set()
        for _g in glossary_lines or []:
            # build_glossary_lines emits "source → rendering"; take the rendering side.
            _rhs = _g.split(" → ", 1)[-1]
            for _tok in re.findall(r"[^\W\d_]+", _rhs.lower(), re.UNICODE):
                if _tok:
                    proper_noun_allowlist.add(_tok)
        for _c in getattr(bible, "characters", None) or []:
            for _tok in re.findall(
                r"[^\W\d_]+", (getattr(_c, "original_latin_name", "") or "").lower(), re.UNICODE
            ):
                if _tok:
                    proper_noun_allowlist.add(_tok)
        for _t in getattr(bible, "terms", None) or []:
            for _field in (
                (getattr(_t, "vietnamese_rendering", "") or ""),
                (getattr(_t, "source_term", "") or ""),
            ):
                for _tok in re.findall(r"[^\W\d_]+", _field.lower(), re.UNICODE):
                    if _tok:
                        proper_noun_allowlist.add(_tok)
    # 260612-1tm: Pass 3 wall-clock + token instrumentation via _p3_col.
    # _p3_col is threaded into each _translate_batch call so all concurrent batch LLM calls
    # accumulate into the same collector (asyncio single-threaded → no race).
    _p3_t0 = time.perf_counter()
    try:
        async with asyncio.TaskGroup() as tg:
            translate_tasks = [
                tg.create_task(
                    _translate_batch(
                        b,
                        llm_client,
                        settings,
                        per_batch_hints[i],
                        model,
                        glossary_lines,
                        register_value,
                        collector=_p3_col,  # 260612-1tm: thread Pass-3 collector
                    )
                )
                for i, b in enumerate(batches)
            ]
        batch_results = [t.result() for t in translate_tasks]
    except* BatchValidationError as eg:
        _reason = str(eg.exceptions[0])
        _qpath = _write_quarantine(path, _reason, [], settings)
        await ledger.record(
            LedgerEntry(
                source_path=str(path),
                output_path=None,
                status="quarantined",
                content_hash=content_hash,
                quarantine_path=str(_qpath),
            )
        )
        _batch_quarantine = TranslationResult(
            status="quarantined",
            quarantine_path=_qpath,
            reason=_reason,
        )

    if _batch_quarantine is not None:
        return _batch_quarantine

    # 260612-1tm: Pass 3 wall-clock duration + per-pass log line (success path only —
    # quarantined files already returned above, so this line is always for a completed pass).
    _p3_dur = time.perf_counter() - _p3_t0
    logger.info("pass=3 duration_s=%.2f file=%s", _p3_dur, path.name)

    # Step 8: Assemble translated SubDoc (Pitfall 8 — never mutate source SubLines)
    #
    # CRITICAL (D-98/D-99 reassembly integrity): batch_subdoc skips cues whose
    # SubLine.raw is not None (karaoke/drawing pass-through).  Those cues are
    # absent from every batch.cues list but MUST appear in the translated_doc at
    # their original positions so the cue count matches source_doc.lines and the
    # AssDoc slot index alignment (sub_index) stays correct.
    #
    # Algorithm:
    #   1. Flatten batch_results into a queue of translated texts in document order.
    #      The order of batch.cues matches the order of non-raw source lines because
    #      batch_subdoc walks source_doc.lines sequentially and skips raw-flagged cues.
    #   2. Walk source_doc.lines; for each cue:
    #        - raw is not None  →  preserve verbatim (same SubLine object)
    #        - raw is None      →  pop next translated text from the queue
    _translated_queue: list[str] = []
    for batch, translated_texts in zip(batches, batch_results):
        _translated_queue.extend(translated_texts)

    _queue_iter = iter(_translated_queue)
    translated_lines: list[SubLine] = []
    for src_line in source_doc.lines:
        if src_line.raw is not None:
            # Opaque pass-through cue (karaoke/drawing) — preserve verbatim.
            # New SubLine to honour "never mutate source SubLines" (Pitfall 8).
            translated_lines.append(
                SubLine(
                    index=src_line.index,
                    start_tc=src_line.start_tc,
                    end_tc=src_line.end_tc,
                    text=src_line.text,
                    raw=src_line.raw,
                )
            )
        else:
            translated_lines.append(
                SubLine(
                    index=src_line.index,
                    start_tc=src_line.start_tc,
                    end_tc=src_line.end_tc,
                    text=next(_queue_iter),
                    raw=None,  # well-formed translated cue — raw not needed
                )
            )

    translated_doc = SubDoc(
        lines=translated_lines,
        encoding="utf-8",
        line_ending=source_doc.line_ending,
        separators=source_doc.separators,
        leading=source_doc.leading,
        trailer=source_doc.trailer,
        envelope=source_doc.envelope,  # carry AssDoc/VttDoc for write codec (D-92)
    )

    # Step 8.5 (Phase 6, D-55): Pass 4 Self-Review — best-effort Bible adherence correction.
    # Runs ONLY in the Bible-aware branch (eligible_item + session_factory + enable_self_review).
    # On ANY failure (LLM error, parse failure, sentinel failure): keep pre-review translated_doc.
    # NEVER quarantines — validate_subdoc (Step 9) remains the sole arbiter (D-59).
    # Tier-3 guard: if llm_client._mode == "text", Pass 4 naturally degrades via the except
    # Exception catch in _review_batch (plain-text LLM still returns numbered lines).
    if (
        settings.enable_self_review
        and eligible_item is not None
        and session_factory is not None
        and bible is not None
    ):
        review_batches = batch_subdoc(
            translated_doc,  # review the TRANSLATED document (Assumption A4)
            settings,
            context_lines_k=settings.self_review_context_lines_k,
            max_cues_per_batch=settings.self_review_max_cues_per_batch,
        )
        source_lines_by_index = {line.index: line for line in source_doc.lines}

        # CR-01 (D-56): Stamp dominant_pair onto each review batch from flat_attributions.
        # batch_subdoc cannot compute dominant_pair — it has no attribution data.
        # The translated_doc is batched with the SAME cue ordering as the source_doc,
        # so flat_attributions[doc_offset:doc_offset+batch_size] aligns 1:1 with review batch cues.
        # name_to_char_id uses the same case-insensitive contract as the Pass-2/3 code (CR-01).
        if flat_attributions and bible is not None:
            # B3 fix / CR-01: EXACT-keyed index + _resolve_char_id (exact-first, honorific
            # fallback) — identical contract to Pass-2/3, no alias collisions.
            _name_to_char_id_rev: dict[str, int] = {
                c.original_latin_name.strip().lower(): c.id for c in bible.characters
            }
            _rb_offset = 0
            for rb in review_batches:
                _batch_size = len(rb.cues)
                _rb_attrs = flat_attributions[_rb_offset : _rb_offset + _batch_size]
                _pair_counts: dict[tuple[int, int], int] = {}
                for _attr in _rb_attrs:
                    _spk_id = _resolve_char_id(_name_to_char_id_rev, _attr.speaker)
                    _addr_id = _resolve_char_id(_name_to_char_id_rev, _attr.addressee)
                    if _spk_id is not None and _addr_id is not None:
                        _p = (_spk_id, _addr_id)
                        if _p in resolved_map:  # only include pairs that were actually resolved
                            _pair_counts[_p] = _pair_counts.get(_p, 0) + 1
                rb.dominant_pair = (
                    max(_pair_counts, key=lambda p: _pair_counts[p]) if _pair_counts else None
                )
                _rb_offset += _batch_size

        # TaskGroup dispatch — mirrors Pass-2 attribution gather.
        # _review_batch catches all exceptions internally and returns None (D-59).
        # except* correctly unwraps ExceptionGroup from TaskGroup (Python 3.11+, CR-03).
        # _review_batch must never raise (D-59); reaching except* indicates a bug.
        # NOTE: `return` is not allowed inside except* — use a flag variable instead.
        # 260612-1tm: Pass 4 wall-clock + token instrumentation via _p4_col.
        _review_failed = False
        _p4_t0 = time.perf_counter()
        try:
            async with asyncio.TaskGroup() as tg:
                review_tasks = [
                    tg.create_task(
                        _review_batch(
                            review_batch=rb,
                            source_lines_by_index=source_lines_by_index,
                            resolved_map=resolved_map,
                            bible=bible,
                            llm_client=llm_client,
                            settings=settings,
                            model=model,  # D-113: per-call model override
                            collector=_p4_col,  # 260612-1tm: thread Pass-4 collector
                        )
                    )
                    for rb in review_batches
                ]
            review_results = [t.result() for t in review_tasks]
        except* Exception as eg:
            # _review_batch must never raise (D-59); reaching here indicates a violated contract
            logger.error(
                "Pass 4 TaskGroup raised unexpectedly (%d exceptions) — "
                "this violates the D-59 best-effort contract; keeping pre-review doc",
                len(eg.exceptions),
                exc_info=True,
            )
            _review_failed = True

        if _review_failed:
            review_results = [None] * len(review_batches)

        # 260612-1tm: Pass 4 wall-clock duration + per-pass log line.
        _p4_dur = time.perf_counter() - _p4_t0
        logger.info("pass=4 duration_s=%.2f file=%s", _p4_dur, path.name)

        # CR-02 (D-98/D-99): splice Pass-4 corrections back onto translated_doc.
        # Corrections map to NON-raw cues only; raw (karaoke/drawing) pass-through
        # slots are preserved verbatim and never misaligned. New SubLine objects,
        # never mutate (Pitfall 8). See _splice_review_corrections for the logic.
        corrected_lines = _splice_review_corrections(
            translated_doc.lines,
            review_batches,
            review_results,
        )

        translated_doc = SubDoc(
            lines=corrected_lines,
            encoding=translated_doc.encoding,
            line_ending=translated_doc.line_ending,
            separators=translated_doc.separators,
            leading=translated_doc.leading,
            trailer=translated_doc.trailer,
            envelope=translated_doc.envelope,  # carry forward for write codec (D-92)
        )

    # Step 8.6: Deterministic envelope preservation (pbz).
    # For cues whose SOURCE is fully enclosed in a single outer ( ) or [ ] bracket pair
    # and whose translated output is missing that wrapper, re-wrap deterministically.
    # Pure structural pass — no LLM, no gate. Runs pre-gate so validate_subdoc validates
    # the final wrapped text. enable_envelope_preservation=False → exact pre-pbz behavior.
    if settings.enable_envelope_preservation:
        translated_doc = _preserve_source_envelopes(translated_doc, source_doc, settings)

    # Step 9: Document-level validation gate (D-16, D-17) with IMP-02b bounded repair loop.
    #
    # REPAIR LOOP LOGIC:
    #   - If enable_gate_repair=False OR check not in _REPAIRABLE_CHECKS OR no failing_indices
    #     OR budget exhausted: fall through to the unchanged quarantine path.
    #   - Otherwise: decrement budget, call _repair_failing_cues, splice repaired lines
    #     back as a new translated_doc, re-validate.
    #   - If _repair_failing_cues returns None (LLM/parse failure): quarantine immediately.
    #   - Gate remains the SOLE arbiter: nothing ships without a clean validate_subdoc pass.
    _repair_budget = settings.gate_repair_max_attempts
    while True:
        try:
            validate_subdoc(
                translated_doc,
                source_doc,
                settings,
                proper_noun_allowlist=proper_noun_allowlist,  # B2 fix: exempt Bible proper nouns from check 10
            )
            break  # gate passed — proceed to write
        except GateError as exc:
            check = exc.failure.check
            failing = exc.failure.failing_indices or []
            _can_repair = (
                settings.enable_gate_repair
                and check in _REPAIRABLE_CHECKS
                and bool(failing)
                and _repair_budget > 0
            )
            if not _can_repair:
                # Standard quarantine path (unchanged from pre-IMP-02b)
                reason = str(exc)
                quarantine_path = _write_quarantine(path, reason, failing, settings)
                await ledger.record(
                    LedgerEntry(
                        source_path=str(path),
                        output_path=None,
                        status="quarantined",
                        content_hash=content_hash,
                        quarantine_path=str(quarantine_path),
                    )
                )
                return TranslationResult(
                    status="quarantined",
                    quarantine_path=quarantine_path,
                    reason=reason,
                )
            _repair_budget -= 1
            logger.info(
                "Gate repair attempt (budget=%d remaining): check=%d failing=%r",
                _repair_budget,
                check,
                failing,
            )
            # FIX 3: pass flat_attributions + name_to_char_id so the repair batch can
            # thread directed pronoun hints for cues with known attribution (not always
            # available — Phase-5 path only; None in Bible-unaware mode → safe-default).
            _repair_name_to_char_id: dict[str, int] | None = None
            if bible is not None and flat_attributions:
                _repair_name_to_char_id = {
                    c.original_latin_name.strip().lower(): c.id for c in bible.characters
                }
            repaired_lines = await _repair_failing_cues(
                failing_indices=failing,
                source_doc=source_doc,
                translated_doc=translated_doc,
                check_number=check,
                llm_client=llm_client,
                settings=settings,
                glossary_lines=glossary_lines,
                register_value=register_value,
                resolved_map=resolved_map,
                bible=bible,
                model=model,
                flat_attributions=flat_attributions if flat_attributions else None,
                name_to_char_id=_repair_name_to_char_id,
            )
            if repaired_lines is None:
                # Repair LLM failed — treat as budget exhausted, quarantine now
                reason = str(exc)
                quarantine_path = _write_quarantine(path, reason, failing, settings)
                await ledger.record(
                    LedgerEntry(
                        source_path=str(path),
                        output_path=None,
                        status="quarantined",
                        content_hash=content_hash,
                        quarantine_path=str(quarantine_path),
                    )
                )
                return TranslationResult(
                    status="quarantined",
                    quarantine_path=quarantine_path,
                    reason=reason,
                )
            # Splice repaired cues → new translated_doc → re-validate on next loop iteration
            translated_doc = SubDoc(
                lines=repaired_lines,
                encoding=translated_doc.encoding,
                line_ending=translated_doc.line_ending,
                separators=translated_doc.separators,
                leading=translated_doc.leading,
                trailer=translated_doc.trailer,
                envelope=translated_doc.envelope,
            )
            # Harness finding (pbz): re-apply envelope preservation after each repair splice.
            # _repair_failing_cues re-translates via the LLM, which can drop the source
            # bracket envelope again. Step C idempotency no-ops already-wrapped cues;
            # enable_envelope_preservation=False short-circuits the whole call.
            translated_doc = _preserve_source_envelopes(translated_doc, source_doc, settings)

    # 260612-1tm: job-completion summary log line — structured key=value pairs, grep-friendly.
    # Pass 1/2 token fields are 0 (collectors not wired into analyze_file/attribute_batch yet).
    # Pass 3/4 token fields carry actual values when collectors are wired into those calls.
    # Duration fields use the local wall-clock floats (0.0 for bypassed passes).
    _p1s = _p1_col.summary()
    _p2s = _p2_col.summary()
    _p3s = _p3_col.summary()
    _p4s = _p4_col.summary()
    logger.info(
        "job_summary file=%s "
        "pass1_calls=%d pass1_prompt_tokens=%d pass1_completion_tokens=%d pass1_duration_s=%.2f "
        "pass2_calls=%d pass2_prompt_tokens=%d pass2_completion_tokens=%d pass2_duration_s=%.2f "
        "pass3_calls=%d pass3_prompt_tokens=%d pass3_completion_tokens=%d pass3_duration_s=%.2f "
        "pass4_calls=%d pass4_prompt_tokens=%d pass4_completion_tokens=%d pass4_duration_s=%.2f",
        path.name,
        _p1s.call_count, _p1s.prompt_tokens, _p1s.completion_tokens, _p1_dur,
        _p2s.call_count, _p2s.prompt_tokens, _p2s.completion_tokens, _p2_dur,
        _p3s.call_count, _p3s.prompt_tokens, _p3s.completion_tokens, _p3_dur,
        _p4s.call_count, _p4s.prompt_tokens, _p4s.completion_tokens, _p4_dur,
    )

    # Step 10: Atomic UTF-8 write (D-19)
    output_path = write_vi_sidecar(translated_doc, path)

    # Step 11: Record completion in ledger
    _ledger_series_id: str | None = (
        str(arr_series_id) if eligible_item is not None and arr_series_id else None
    )
    await ledger.record(
        LedgerEntry(
            source_path=str(path),
            output_path=str(output_path),
            status="done",
            content_hash=content_hash,
            translated_at=datetime.now(timezone.utc).isoformat(),
            series_id=_ledger_series_id,
        )
    )

    # Step 12: Return success result
    return TranslationResult(status="done", output_path=output_path)
