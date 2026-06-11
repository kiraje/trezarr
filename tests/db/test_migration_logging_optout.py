"""Regression test: in-app migrations must not let alembic.ini reconfigure logging.

alembic.ini's [logger_root] is level=WARNING with the "%(levelname)-5.5s
[%(name)s]" format. When env.py ran fileConfig inside the daemon's lifespan,
it replaced run_serve's basicConfig and silently dropped every app INFO record
after startup — the per-pass instrumentation lines (quick-260612-1tm) never
reached docker logs (observed live 2026-06-12).

The fix is the standard Alembic opt-out: run_migrations_to_head sets
cfg.attributes["configure_logger"] = False and env.py honors it. The alembic
CLI path (attribute absent → defaults True) keeps configuring logging.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

from unittest.mock import patch

from trezarr.db import migration_runner


async def test_run_migrations_opts_out_of_alembic_log_config(db_engine):
    """run_migrations_to_head must pass configure_logger=False to env.py."""
    captured = {}

    def spy_upgrade(connection, cfg):
        captured["cfg"] = cfg

    with patch.object(migration_runner, "_do_upgrade", side_effect=spy_upgrade):
        await migration_runner.run_migrations_to_head(db_engine)

    assert "cfg" in captured, "_do_upgrade was never invoked"
    assert captured["cfg"].attributes.get("configure_logger") is False, (
        "in-app migrations must opt out of env.py's fileConfig — otherwise "
        "alembic.ini's WARNING root config silently kills app INFO logging"
    )
