"""RED stubs for PRON-02 end-to-end three-pass pronoun engine integration.

Tests cover:
  PRON-02 — Reconciled pronoun pair injected as hint in Pass-3 prompt
  PRON-02 — Same pair → identical pronouns across all batches in one episode
  ENG-04/PRON-03 — Tier-3-only endpoint: translate_file completes without quarantine,
                   all lines use safe default, valid .vi.srt written (D-47)

All trezarr.* imports are deferred inside each test function body so pytest
collection succeeds even when the implementation module does not yet exist.
Tests are marked xfail(strict=False) — they pass at Wave 0 (ImportError expected)
and will be turned GREEN in Phase 5 Plans 05-06.

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.
"""
import pytest


@pytest.mark.xfail(strict=False, reason="build_translate_prompt pronoun hint not yet implemented", raises=(ImportError, AssertionError, TypeError))
def test_pronoun_hint_in_prompt():
    """Reconciled pronoun pair is injected as a hint in the Pass-3 translate prompt (PRON-02).

    Assert:
    - build_translate_prompt importable from trezarr.translate.engine
    - When a pronoun_hint dict is passed (e.g. {'speaker': 'anh', 'addressee': 'em'}),
      the rendered prompt contains the pronoun hint in the [PRONOUNS] or equivalent section

    Note: trezarr.translate.engine already exists (Phase 3); the pronoun_hint parameter
    is new functionality added in Plan 05-05. The stub asserts False to stay RED until
    then. raises=(ImportError, AssertionError, TypeError) covers both the Wave-0 state
    (AssertionError from assert False) and any future import changes.
    """
    from trezarr.translate.engine import build_translate_prompt
    assert False, "stub — implement in Plan 05-05"


@pytest.mark.xfail(strict=False, reason="three-pass pronoun engine not yet implemented", raises=(ImportError, AssertionError, TypeError))
def test_pronoun_consistency_within_episode():
    """Same character pair → identical pronouns across all batches in one episode (PRON-02).

    Assert:
    - translate_file importable from trezarr.translate.engine
    - When translating a mocked episode with a known character pair,
      all translated lines use the same pronoun pair (no inconsistency across batches)

    Note: trezarr.translate.engine already exists (Phase 3); the three-pass pronoun
    consistency is new functionality added in Plan 05-05. The stub asserts False to
    stay RED until then.
    """
    from trezarr.translate.engine import translate_file
    assert False, "stub — implement in Plan 05-05"


@pytest.mark.xfail(strict=False, reason="Tier-3 graceful degrade not yet implemented (D-47)", raises=(ImportError, AssertionError, TypeError))
def test_tier3_endpoint_degrades_gracefully():
    """Tier-3-only endpoint: translate_file completes without quarantine (D-47 / ENG-04 / PRON-03).

    Assert:
    - translate_file importable from trezarr.translate.engine
    - When the LLM endpoint only supports Tier-3 (no structured outputs, no attribution),
      translate_file completes with status='done' (not 'quarantined')
    - All lines use the safe default pronoun pair
    - A valid .vi.srt is written to the output path

    Note: trezarr.translate.engine already exists (Phase 3); the Tier-3 graceful degrade
    path is new functionality added in Plan 05-06. The stub asserts False to stay RED until
    then.
    """
    from trezarr.translate.engine import translate_file
    assert False, "stub — implement in Plan 05-06"
