"""Tests for the auto_translate_enabled safety gate in poll_and_enqueue
(quick task 260603-l8g).

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
All trezarr.* imports are deferred inside test bodies (PLC0415 pattern).
"""
from __future__ import annotations


async def test_poll_and_enqueue_skips_when_auto_translate_disabled():
    """poll_and_enqueue is a no-op when auto_translate_enabled=False (safety gate)."""
    from trezarr.web.scheduler import poll_and_enqueue  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    settings = TrezarrSettings()
    assert settings.auto_translate_enabled is False, (
        "auto_translate_enabled must default to False (safety invariant)"
    )
    # Calling with real settings (auto_translate=False) and a non-None session_factory stub
    # must return without attempting discovery.
    # We verify this by passing a session_factory that would raise if called:
    class _RaisingSF:
        def __call__(self, *a, **kw):
            raise AssertionError(
                "session_factory must not be called when auto_translate_enabled=False"
            )

    await poll_and_enqueue(session_factory=_RaisingSF(), settings=settings)
    # If we reach here without AssertionError, the gate worked.


async def test_auto_translate_enabled_default_false():
    """TrezarrSettings.auto_translate_enabled defaults to False."""
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    s = TrezarrSettings()
    assert s.auto_translate_enabled is False
