"""Source-language relational-fidelity ranking (SRC-02, D-107).

Pure functions — no I/O, no imports beyond __future__ annotations and builtins.

Design decisions honoured:
  D-106  Source-agnostic by default; English is the universal last-resort fallback,
         not the default source.
  D-107  Rank available sources by static relational-richness tier biased by
         original_language. Tier 1: zh/ko/ja/th. Tier 2: other relational/honorific
         languages. Tier 3: en and flat-relational.

sort_key algorithm (final algorithm from RESEARCH.md §Deep Dive Ranking):
  - Tier 1 languages (zh, ko, ja, th): carry grammatical relational/honorific info
    that Vietnamese needs for anh/em pronoun selection.
  - Tier 2 languages (id, ms, hi, ta, ar, tr, and unlisted): moderate honorifics.
  - Tier 3 languages (en, and Tier-3-class langs): flat relational — I/you collapses
    all relationships.

  sort_key(lang, original_language) -> float (lower = more preferred):
    if lang == original_language:
      if tier == 3: return 0.0     (native flat-relational → absolute top — D-107)
      else:         return tier - 0.5   (native rich-relational → bonus within tier)
    else:           return float(tier)
"""
from __future__ import annotations

# ── Static relational-richness tier table (D-107) ─────────────────────────────
# Lower tier = richer relational information for Vietnamese pronoun selection.
# Tier 1: high relational fidelity (zh, ko, ja, th)
# Tier 2: moderate relational / honorific marking
# Tier 3: flat-relational (universal fallback)
# Unlisted languages default to Tier 2 (generous — better than flat)

_TIER: dict[str, int] = {
    # ── Tier 1 — high relational fidelity for Vietnamese ─────────────────────
    "zh": 1, "cmn": 1, "zho": 1,   # Chinese (Mandarin / generic Chinese)
    "ko": 1, "kor": 1,               # Korean
    "ja": 1, "jpn": 1,               # Japanese
    "th": 1, "tha": 1,               # Thai
    # ── Tier 2 — moderate relational / honorific marking ──────────────────────
    "id": 2, "ind": 2,               # Indonesian (honorifics, register)
    "ms": 2, "msa": 2,               # Malay
    "hi": 2, "hin": 2,               # Hindi (aap/tum/tu register)
    "ta": 2, "tam": 2,               # Tamil (honorific register)
    "ar": 2, "ara": 2,               # Arabic (formal/informal register)
    "tr": 2, "tur": 2,               # Turkish (siz/sen)
    # ── Tier 3 — flat-relational: universal fallback ───────────────────────────
    "en": 3, "eng": 3,               # English (the universal fallback — D-106)
}

_DEFAULT_TIER = 2  # unlisted languages treated as Tier 2 (moderate)

# ── Language name → ISO 639-1 code mapping (for original_language from *arr) ──
# Sonarr/Radarr return originalLanguage.name as a human-readable string.
# Map common names to 2-letter ISO codes for tier lookup and bias.
# Unlisted names return None → fallback to rank-over-available-set.
_ORIG_LANG_NAME_TO_CODE2: dict[str, str] = {
    # East Asian — Tier 1
    "english": "en",
    "korean": "ko",
    "japanese": "ja",
    "chinese": "zh",
    "thai": "th",
    "vietnamese": "vi",
    "cantonese": "zh",      # Cantonese → zh Tier 1 (Pitfall 5)
    "mandarin": "zh",       # Mandarin → zh Tier 1 (Pitfall 5)
    # Southeast / South Asian — Tier 2
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "portuguese": "pt",
    "italian": "it",
    "russian": "ru",
    "arabic": "ar",
    "hindi": "hi",
    "indonesian": "id",
    "malay": "ms",
    "tamil": "ta",
    "turkish": "tr",
    # Additional common names
    "dutch": "nl",
    "polish": "pl",
    "swedish": "sv",
    "norwegian": "no",
    "danish": "da",
    "finnish": "fi",
    "czech": "cs",
    "hungarian": "hu",
    "romanian": "ro",
    "greek": "el",
    "hebrew": "he",
    "ukrainian": "uk",
    "catalan": "ca",
    "basque": "eu",
    "galician": "gl",
    "bengali": "bn",
    "urdu": "ur",
    "farsi": "fa",
    "persian": "fa",
    "burmese": "my",
    "khmer": "km",
    "lao": "lo",
    "mongolian": "mn",
    "tibetan": "bo",
    "filipino": "fil",
    "tagalog": "tl",
}


def sort_key(lang: str, original_language: str | None) -> float:
    """Return the sort key for a language code (lower = more preferred source).

    This is the "final algorithm" from RESEARCH.md §Deep Dive Ranking:
    - If lang IS the original_language of the content:
        - Tier 3 (flat-relational native, e.g. en for a US show): return 0.0
          (absolute top — native source wins over any fansub)
        - Tier 1/2 (rich-relational native, e.g. ko for a K-drama): return tier - 0.5
          (preferred within tier group — earns a 0.5 bonus)
    - Otherwise: return float(tier)

    This produces correct behaviour for both cases:
      - Korean drama (original=ko): ko gets 0.5, en gets 3.0 → ko wins
      - US show (original=en): en gets 0.0, ko gets 1.0 → en wins

    Args:
        lang:              2- or 3-letter language code (lower-cased).
        original_language: The content's native language code (lower-cased) from
                           normalize_original_language(), or None if unknown.

    Returns:
        Float sort key. Lower = more preferred.
    """
    t = _TIER.get(lang.lower(), _DEFAULT_TIER)
    if original_language and lang.lower() == original_language.lower():
        if t == 3:
            # Flat-relational native language (e.g. en for a US show) → absolute top.
            # Prevents a Tier-1 fansub from displacing the native source.
            return 0.0
        else:
            # Rich-relational native language (e.g. ko for a K-drama).
            # Preferred within tier group but still below a hypothetical
            # natively-tagged Tier-1 that IS the original language.
            return float(t) - 0.5
    return float(t)


def rank_sources(
    available: list[str],
    original_language: str | None,
) -> list[str]:
    """Return available language codes ranked by relational richness + native bias.

    Deterministic: tie-breaking by language code (alphabetical) within the same
    sort_key. This ensures consistent ranking even when multiple languages share
    the same tier and there is no native bias.

    Args:
        available:         List of available source language codes (2- or 3-letter,
                           any case). Duplicates are collapsed via set().
        original_language: The content's native language code (2-letter, lower-cased)
                           from normalize_original_language(), or None.

    Returns:
        Sorted list of lower-cased language codes, most preferred first.
    """
    return sorted(
        set(lang.lower() for lang in available),
        key=lambda lang: (sort_key(lang, original_language), lang),
    )


def normalize_original_language(name: str | None) -> str | None:
    """Map a human-readable language name to a 2-letter ISO-639-1 code.

    Used to translate the originalLanguage.name string from Sonarr/Radarr API
    responses into a code suitable for rank_sources() and sort_key() (D-108).

    Args:
        name: Human-readable language name (e.g. "Korean", "English").
              Case-insensitive. None is passed through as None.

    Returns:
        2-letter ISO 639-1 code (e.g. "ko", "en"), or None if name is None
        or not found in the lookup table.
    """
    if name is None:
        return None
    return _ORIG_LANG_NAME_TO_CODE2.get(name.lower())
