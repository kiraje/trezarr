"""Shared timecode-to-millisecond helper (IN-04, D-101).

This module exists solely to avoid the verbatim duplication of tc_to_ms
across batching.py and validate.py.

Supported formats:
    SRT:          HH:MM:SS,mmm or HH:MM:SS.mmm  (2-digit hours, comma or period,
                  variable ms digits — existing contract, unchanged)
    ASS:          H:MM:SS.cc  (1+ hour digit, exactly 2 centisecond digits,
                  period separator; centiseconds * 10 = ms)
    VTT with hrs: HH:MM:SS.mmm  (2+ hour digits, exactly 3 ms digits, period only)
    VTT hourless: MM:SS.mmm  (no hours, exactly 3 ms digits, period only)

Contract for malformed input:
    A timecode string that does not match any of the above patterns is
    treated as 0 ms.  In batching.py this can fabricate a spurious gap or none;
    in validate.py check 5 a malformed timecode becomes start=0, end=0 → the
    zero-duration guard raises GateError (fails closed).  This 0-on-malformed
    behaviour is intentional and documented here.
"""
from __future__ import annotations

import re

# Existing SRT pattern (2-digit hours, comma or period, variable ms digits).
# Must be tried FIRST — its variable-digit ms pattern would shadow the fixed-digit
# VTT patterns if tried after them.
_TC_PARSE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)")

# ASS: H:MM:SS.cc (1+ hour digits, exactly 2 centisecond digits, period only).
# Anchored with $ to prevent matching 3-digit ms as a prefix.
_ASS_TC_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})$")

# VTT with hours: HH:MM:SS.mmm (2+ hour digits, exactly 3 ms digits, period only).
_VTT_HOURS_TC_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{3})$")

# VTT hourless: MM:SS.mmm (no hours, exactly 3 ms digits, period only).
_VTT_HOURLESS_TC_RE = re.compile(r"(\d+):(\d{2})\.(\d{3})$")


def tc_to_ms(tc: str) -> int:
    """Convert a subtitle timecode to milliseconds.

    Supports SRT, ASS, and VTT timecode formats.  The try-order is critical:
    SRT is tried first because its variable-digit ms group would shadow VTT's
    3-digit group if attempted second.

    Args:
        tc: Timecode string (e.g. "01:23:45,678", "0:01:23.45", "01:23.456").

    Returns:
        Total milliseconds as an integer, or 0 if the input does not match any
        expected pattern (malformed→0 contract — see module docstring).
    """
    tc = tc.strip()

    # Try SRT first (must be first — existing behavior, 2-digit hours required)
    m = _TC_PARSE_RE.match(tc)
    if m:
        h, mi, s, ms_str = m.group(1), m.group(2), m.group(3), m.group(4)
        ms = int(ms_str.ljust(3, '0')[:3])
        return int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + ms

    # Try ASS: H:MM:SS.cc (exactly 2 centisecond digits; cc * 10 = ms)
    m = _ASS_TC_RE.match(tc)
    if m:
        h, mi, s, cc = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600000 + mi * 60000 + s * 1000 + cc * 10

    # Try VTT with hours: HH:MM:SS.mmm (exactly 3 ms digits)
    m = _VTT_HOURS_TC_RE.match(tc)
    if m:
        h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600000 + mi * 60000 + s * 1000 + ms

    # Try VTT hourless: MM:SS.mmm (exactly 3 ms digits)
    m = _VTT_HOURLESS_TC_RE.match(tc)
    if m:
        mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return mi * 60000 + s * 1000 + ms

    return 0  # malformed timecode — existing contract unchanged
