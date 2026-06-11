"""Regression test: `trezarr serve` must configure app-level INFO logging.

Without basicConfig in run_serve, trezarr.* INFO records (notably the per-pass
timing + job_summary instrumentation lines from quick-260612-1tm) fall through
to logging.lastResort, which only emits WARNING+ — so the daemon container logs
contain no instrumentation at all (observed live on 2026-06-12).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from trezarr.web.app import run_serve


def test_run_serve_configures_root_logger_for_info(monkeypatch):
    """run_serve must install a root handler at INFO before uvicorn starts."""
    root = logging.getLogger()
    # Simulate a fresh interpreter: no root handlers (as in the container).
    old_handlers = root.handlers[:]
    old_level = root.level
    root.handlers = []
    root.setLevel(logging.WARNING)
    # Required settings so TrezarrSettings() constructs without a config file.
    monkeypatch.setenv("TREZARR_OPENAI_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("TREZARR_OPENAI_API_KEY", "test-key")
    try:
        with patch("uvicorn.run") as mock_run:
            run_serve()
        assert mock_run.called, "uvicorn.run must still be invoked"
        assert root.handlers, "run_serve must install a root logging handler"
        assert root.level <= logging.INFO, (
            "root logger must pass INFO records (got level "
            f"{logging.getLevelName(root.level)})"
        )
        # The instrumentation logger must be effectively enabled for INFO.
        assert logging.getLogger("trezarr.translate.engine").isEnabledFor(
            logging.INFO
        )
    finally:
        root.handlers = old_handlers
        root.setLevel(old_level)
