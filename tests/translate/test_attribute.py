"""RED stubs for PRON-01 speaker/addressee attribution (Pass 2).

Tests cover:
  PRON-01 — LineAttribution parsed from mock LLM response
  PRON-01 — Unknown speaker/addressee → safe default (no crash)

All trezarr.* imports are deferred inside each test function body so pytest
collection succeeds even when the implementation module does not yet exist.
Tests are marked xfail(strict=False) — they pass at Wave 0 (ImportError expected)
and will be turned GREEN in Phase 5 Plan 03.

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.
"""
import pytest


@pytest.mark.xfail(strict=False, reason="trezarr.translate.attribute not yet implemented", raises=ImportError)
def test_attribution_parsing():
    """LineAttribution and BatchAttribution are parsed from a mock LLM response (PRON-01).

    Assert:
    - LineAttribution importable from trezarr.translate.attribute
    - BatchAttribution importable from trezarr.translate.attribute
    - Parsing a mock LLM JSON response produces LineAttribution objects with
      speaker and addressee fields populated
    """
    from trezarr.translate.attribute import LineAttribution, BatchAttribution
    assert False, "stub — implement in Plan 05-03"


@pytest.mark.xfail(strict=False, reason="trezarr.translate.attribute not yet implemented", raises=ImportError)
def test_unmatched_name_safe_default():
    """Unknown speaker/addressee name → safe default returned, no crash (PRON-01).

    Assert:
    - attribute_batch importable from trezarr.translate.attribute
    - When LLM returns a speaker name not in the character roster,
      attribute_batch returns safe default attribution (not raises)
    """
    from trezarr.translate.attribute import attribute_batch
    assert False, "stub — implement in Plan 05-03"
