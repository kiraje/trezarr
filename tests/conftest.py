"""Shared pytest fixtures and configuration for Trezarr tests."""
from pathlib import Path

import pytest

# Path constant used by golden-file tests
FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure(config):
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "live: marks tests as requiring a live LLM endpoint (deselect with '-m not live')",
    )


@pytest.fixture
def settings_factory():
    """Return a callable that creates TrezarrSettings instances with test-safe defaults.

    Usage::

        def test_something(settings_factory):
            settings = settings_factory()               # all defaults
            settings = settings_factory(llm_max_retries=2)  # override
    """
    try:
        from trezarr.config import TrezarrSettings
    except ImportError:
        pytest.skip("trezarr.config not yet implemented (Plan 03)")

    def _factory(**overrides):
        defaults = dict(
            llm_base_url="http://localhost:1234/v1",
            llm_api_key="test-key",  # meaningless literal — never a real key (T-01-W0-01)
            llm_model="test-model",
            llm_max_concurrency=1,
        )
        defaults.update(overrides)
        return TrezarrSettings(**defaults)

    return _factory
