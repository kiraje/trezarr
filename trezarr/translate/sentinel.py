"""Inline-tag sentinel extraction and reinsertion (D-12).

Design decisions honoured:
  D-12  Placeholder-protect inline tags before sending text to LLM.
        Extract <i>, <b>, <u>, <font…>, {\\anX} etc. and replace with
        opaque <<TN>> tokens; reinsert by sentinel after translation.
        If sentinels do not round-trip, returns integrity_ok=False so
        the caller (engine.py batch-level gate) can retry or quarantine.
"""
from __future__ import annotations

import re

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
        (restored_text, integrity_ok).  integrity_ok is True only when every
        sentinel in sentinel_map was found exactly once in text AND no orphan
        <<T\\d+>> tokens remain after reinsertion.  Returns (text, False) at the
        first integrity violation — the caller is responsible for retry/quarantine.
    """
    for key, original in sentinel_map.items():
        if key not in text:
            return text, False  # sentinel was lost — gate will catch this
        text = text.replace(key, original, 1)

    # No orphan sentinels must remain after all map entries are reinserted
    if re.search(r'<<T\d+>>', text):
        return text, False

    return text, True
