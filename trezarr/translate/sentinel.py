"""Inline-tag sentinel extraction and reinsertion (D-12).

Design decisions honoured:
  D-12  Placeholder-protect inline tags before sending text to LLM.
        Extract <i>, <b>, <u>, <font…>, {\\anX} etc. and replace with
        opaque <<TN>> tokens; reinsert by sentinel after translation.
        If sentinels do not round-trip, returns integrity_ok=False so
        the caller (engine.py batch-level gate) can retry or quarantine.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Matches SRT inline tags (<i>, <b>, <u>, <font color="…">, </i> etc.),
# inline ASS override tags ({\anX}, {\pos(x,y)}, {\an8} etc.), and
# ASS raw hard-break sequences (\N, \n, \h — not inside braces, D-98).
# The \\[Nnh] arm is a fixed two-character match (literal backslash + char class);
# no quantifiers, no backtracking — ASVS L1 compliant (T-09-02-B).
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\}|\\[Nnh])')


def extract_sentinels(text: str) -> tuple[str, dict[str, str]]:
    """Replace inline tags with opaque <<TN>> tokens.

    The sentinel counter resets to 0 on every call, so keys are <<T0>>, <<T1>>, …
    relative to the single cue passed in.

    CALLER INVARIANT: Each call to extract_sentinels must produce a sentinel_map
    that is kept and used exclusively with the translated text for that same cue.
    Never merge sentinel_maps from different cues — key <<T0>> is per-cue-local
    and would collide if maps were combined across cues.  The engine (engine.py)
    maintains one sentinel_map per cue in a parallel list and reinserts per cue.

    Args:
        text: Subtitle cue text, possibly containing inline formatting tags.

    Returns:
        (cleaned_text, sentinel_map) where cleaned_text has all tags replaced
        with <<T0>>, <<T1>>, … tokens, and sentinel_map maps each token back
        to its original tag string.  If the input contains no tags, sentinel_map
        is empty and cleaned_text equals the input unchanged.
    """
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
    """Restore inline tags from sentinel tokens.

    Args:
        text:         Translated cue text with <<TN>> tokens still present.
        sentinel_map: Mapping from <<TN>> keys to original tag strings, as
                      returned by extract_sentinels().

    Returns:
        (restored_text, integrity_ok).

        integrity_ok is False ONLY when a *real* sentinel is lost — a key present
        in sentinel_map that is not found in text (the model dropped a tag we must
        restore). The caller retries/quarantines, since silently emitting output
        missing a real formatting tag would corrupt fidelity.

        *Orphan* tokens — `<<T\\d+>>` still present after every map key is
        reinserted — are NOT in sentinel_map and so were never extracted by us:
        the (weak) model hallucinated them into an untagged or already-restored
        cue (v1.0 verification finding #5). These are STRIPPED and integrity_ok
        stays True, rather than quarantining an otherwise-valid translation. A
        lost real sentinel still fails above, so this only ever removes
        never-extracted tokens.
    """
    # Strip hallucinated orphans FIRST, on the raw model output, BEFORE reinserting
    # any tag values. Orphans = <<TN>> tokens the model produced that are not keys
    # we extracted. Doing this before reinsertion is critical: a real tag VALUE can
    # itself contain a <<TN>>-shaped substring (TAG_RE over-matches a literal
    # "<<T1000>>" out of source text), and stripping after reinsertion would delete
    # that legitimately-restored content. We strip only the specific orphan tokens,
    # never the bare <<T\d+>> pattern (the real keys are still present here).
    orphans = {m for m in re.findall(r'<<T\d+>>', text)} - set(sentinel_map)
    if orphans:
        orphan_re = re.compile(
            r'\s*(?:' + '|'.join(re.escape(o) for o in sorted(orphans)) + r')\s*'
        )
        cleaned = orphan_re.sub(' ', text).strip()
        logger.warning(
            "reinsert_sentinels: stripped hallucinated orphan sentinel(s) %s "
            "(not in sentinel_map): %r -> %r",
            sorted(orphans), text, cleaned,
        )
        text = cleaned

    for key, original in sentinel_map.items():
        if key not in text:
            return text, False  # real sentinel was lost — gate will catch this
        text = text.replace(key, original, 1)

    # Any residual <<TN>> after reinserting every real key means either a
    # duplicated real key (model emitted a real token more than once) or a tag
    # VALUE that itself contains a <<TN>>-shaped substring (TAG_RE over-match of
    # literal source). Either way the document gate's Check 6 (identical
    # <<T\d+>> pattern) would quarantine the file, so fail here too — honest and
    # in agreement with the gate, and it lets the batch-level retry try again.
    if re.search(r'<<T\d+>>', text):
        return text, False

    return text, True
