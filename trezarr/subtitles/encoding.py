"""Encoding detection for subtitle files.

Implements a three-tier detection strategy to correctly identify the character
encoding of a raw byte stream before decoding it:

  1. BOM check — authoritative and zero-ambiguity.
  2. Strict UTF-8 decode — handles the large majority of modern files.
  3. charset-normalizer fallback — best-effort for legacy encodings.

The third tier includes a CJK-codec guard: charset-normalizer misidentifies
CP1258 (Windows Vietnamese) as ``big5`` on short subtitle files (Pitfall 4).
When a CJK codec is returned for what should be a Vietnamese file, a
``UserWarning`` is emitted and ``"utf-8"`` is returned as a safe fallback.
Users with old CP1258-encoded subtitle files should convert them to UTF-8 for
reliable handling.

See: .planning/phases/01-codec-llm-client-foundation/01-RESEARCH.md Pattern 2
"""
from __future__ import annotations

import warnings

import charset_normalizer

# CJK codecs that charset-normalizer may return for short Vietnamese files that
# are actually CP1258-encoded.  Any of these triggers the guard + fallback.
_CJK_CODECS: frozenset[str] = frozenset({
    "big5",
    "gb2312",
    "gb18030",
    "euc-kr",
    "euc-jp",
    "shift-jis",
    "shift_jis",
})


def detect_encoding(data: bytes) -> str:
    """Detect the character encoding of *data* and return a codec name.

    The codec name is suitable for use as the *encoding* argument to
    ``bytes.decode()`` and ``str.encode()``.  The function never raises —
    it always returns a string, defaulting to ``"utf-8"`` when detection
    is uncertain.

    Detection strategy (in order):

    1. **BOM** — unambiguous signature bytes at the start of the stream.
       ``\\xef\\xbb\\xbf`` → ``"utf-8-sig"``
       ``\\xff\\xfe`` or ``\\xfe\\xff`` → ``"utf-16"``

    2. **Strict UTF-8** — try to decode as UTF-8.  On success, return
       ``"utf-8"`` (covers the vast majority of modern subtitle files).

    3. **charset-normalizer fallback** — statistical encoding detection.
       If the best guess is a CJK codec, emit a ``UserWarning`` and return
       ``"utf-8"`` instead (CP1258 misidentification guard).

    Args:
        data: Raw bytes from a subtitle file.

    Returns:
        A codec name string (e.g. ``"utf-8"``, ``"utf-8-sig"``, ``"utf-16"``).
    """
    # ---- Tier 1: BOM check -----------------------------------------------
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    # WR-01: map the UTF-16 BOM to the *explicit* endianness so the byte order
    # round-trips.  Plain "utf-16" re-encodes with the platform's native
    # endianness on write (which may differ from the source) and also strips the
    # BOM on decode — both break byte-identity.  The "utf-16-le"/"utf-16-be"
    # codecs preserve the BOM through decode→encode for a big- or little-endian
    # source alike.
    if data[:2] == b"\xff\xfe":
        return "utf-16-le"
    if data[:2] == b"\xfe\xff":
        return "utf-16-be"

    # ---- Tier 2: Strict UTF-8 decode -------------------------------------
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # ---- Tier 3: charset-normalizer fallback -----------------------------
    result = charset_normalizer.from_bytes(data).best()
    if result is None:
        return "utf-8"

    detected = result.encoding
    if detected.lower() in _CJK_CODECS:
        warnings.warn(
            f"detect_encoding: charset-normalizer returned '{detected}' for a likely "
            "Vietnamese file.  This may indicate a CP1258-encoded file (known "
            "misidentification by charset-normalizer on short files).  Falling back "
            "to utf-8.  Convert the file to UTF-8 for reliable handling.",
            UserWarning,
            stacklevel=2,
        )
        return "utf-8"

    return detected
