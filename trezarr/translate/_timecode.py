"""Shared timecode-to-millisecond helper (IN-04).

This module exists solely to avoid the verbatim duplication of _tc_to_ms
across batching.py and validate.py.

Contract for calformed input:
    A timecode string that does not match HH:MM:SS,mmm or HH:MM:SS.mmm is
    treated as 0 ms.  In batching.py this can fabricate a spurious gap or none;
    in validate.py check 5 a malformed timecode becomes start=0, end=0 → the
    zero-duration guard raises GateError (fails closed).  This 0-on-malformed
    behaviour is intentional and documented here.
"""
from __future__ import annotations

import re

# Matches HH:MM:SS,mmm or HH:MM:SS.mmm (any number of millisecond digits).
_TC_PARSE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)")


def tc_to_ms(tc: str) -> int:
    """Convert HH:MM:SS,mmm or HH:MM:SS.mmm to milliseconds.

    Truncates sub-millisecond precision (digits beyond the third are ignored).

    Args:
        tc: Timecode string (e.g. "01:23:45,678" or "01:23:45.678").

    Returns:
        Total milliseconds as an integer, or 0 if the input does not match the
        expected pattern (malformed→0 contract — see module docstring).
    """
    m = _TC_PARSE_RE.match(tc)
    if m is None:
        return 0  # malformed timecode — treat as 0ms (defensive; gate will catch bad docs)
    h, mi, s, ms_str = m.group(1), m.group(2), m.group(3), m.group(4)
    ms = int(ms_str.ljust(3, '0')[:3])
    return int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + ms
