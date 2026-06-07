"""DEV TOOL: not wired into daemon, Docker image, or CI.

Local single-file translate runner for fast dev feedback.

Run the full Trezarr translation pipeline on a single source SRT (or ASS/VTT)
file against the configured LLM endpoint (reads TREZARR_* env vars / .env).

Usage:
    uv run python scripts/translate_one.py path/to/source.en.srt
    uv run python scripts/translate_one.py path/to/source.en.srt --out /tmp/out.vi.srt
    uv run python scripts/translate_one.py path/to/source.en.srt --series-id 42

The script uses a throwaway SQLite Bible DB and JSON ledger so it never touches
the production /config/trezarr.db. Output defaults to the same directory as the
source; pass --out to redirect (RECOMMENDED if working near real media files).

NOTE: This script does NOT commit any output to the production ledger or Bible DB.
All temp state is cleaned up via atexit handlers.

WARNING: The default --out path places the .vi.srt next to the source file.
Pass --out /tmp/... to avoid writing next to real media.
"""
from __future__ import annotations

import argparse
import atexit
import os
import tempfile
import time
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DEV TOOL: Translate a single subtitle file via the Trezarr pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "source",
        help="Path to the source subtitle file (e.g. Show.S01E01.en.srt)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output path for the Vietnamese subtitle (default: <source-dir>/<stem>.vi.srt). "
            "WARNING: default writes next to the source file — use --out /tmp/... "
            "to avoid writing next to real media."
        ),
    )
    parser.add_argument(
        "--series-id",
        type=int,
        default=None,
        dest="series_id",
        help=(
            "Sonarr/Radarr series ID for Bible lookup. When omitted, a synthetic ID=0 is "
            "used (creates a fresh throwaway Bible entry)."
        ),
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    # ── 1. Load settings from env / .env ──────────────────────────────────────
    # DEV CONVENIENCE: TrezarrSettings reads OS env vars (env_prefix TREZARR_) + YAML +
    # code defaults — it does NOT read a .env file (that's a docker-compose convention,
    # not pydantic-settings). A bare local run would otherwise fall back to the code
    # defaults (http://localhost:1234/v1 / gpt-4o) instead of the configured endpoint.
    # Load .env into os.environ here (setdefault → a real OS env var still wins) so this
    # runner hits the SAME LLM endpoint the deployed daemon does.
    _dotenv = Path(".env")
    if _dotenv.exists():
        for _line in _dotenv.read_text(encoding="utf-8").splitlines():
            _s = _line.strip()
            if not _s or _s.startswith("#") or "=" not in _s:
                continue
            _k, _, _v = _s.partition("=")
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            if _k:
                os.environ.setdefault(_k, _v)

    from trezarr.config import TrezarrSettings

    settings = TrezarrSettings(
        _yaml_file="config.yaml" if Path("config.yaml").exists() else None
    )

    # ── 2. Temp SQLite DB ─────────────────────────────────────────────────────
    _tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(_tmp_db_fd)  # close fd immediately; SQLAlchemy opens it separately

    def _cleanup_db() -> None:
        try:
            if os.path.exists(_tmp_db_path):
                os.unlink(_tmp_db_path)
            # Also clean up WAL/SHM sidecar files SQLite may create.
            for _suf in ("-wal", "-shm"):
                _p = _tmp_db_path + _suf
                if os.path.exists(_p):
                    os.unlink(_p)
        except OSError:
            pass

    atexit.register(_cleanup_db)

    # ── 3. Temp JSON ledger ───────────────────────────────────────────────────
    _tmp_ledger_fd, _tmp_ledger_path = tempfile.mkstemp(suffix=".json")
    os.close(_tmp_ledger_fd)
    atexit.register(lambda: os.unlink(_tmp_ledger_path) if os.path.exists(_tmp_ledger_path) else None)

    # ── 4. Temp quarantine dir ────────────────────────────────────────────────
    _tmp_quarantine = Path(tempfile.gettempdir()) / "trezarr_dev_quarantine"

    # ── 5. Single settings_with_overrides object ──────────────────────────────
    # All downstream calls (build_engine, translate_file, LLMClient) use this
    # SINGLE object — no NameError risk from two separate settings objects.
    settings_with_overrides = settings.model_copy(update=dict(
        bible_db_url=f"sqlite+aiosqlite:///{_tmp_db_path}",
        bible_db_run_migrations_on_startup=True,
        translate_quarantine_dir=str(_tmp_quarantine),
        translate_ledger_path=_tmp_ledger_path,
    ))

    # ── 6. Build LLMClient ────────────────────────────────────────────────────
    from trezarr.llm.client import LLMClient

    llm_client = LLMClient(settings_with_overrides)

    # ── 7. Build engine + session_factory + run migrations ────────────────────
    from trezarr.db.engine import build_engine
    from trezarr.db.migration_runner import run_migrations_to_head
    from trezarr.db.session import build_session_factory

    engine = build_engine(settings_with_overrides)
    try:
        await run_migrations_to_head(engine)
        session_factory = build_session_factory(engine)

        # ── 8. Build throwaway ledger ─────────────────────────────────────────
        from trezarr.output.ledger import Ledger

        ledger = Ledger(_tmp_ledger_path)

        # ── 9. Build minimal EligibleItem with a REAL MediaItem ───────────────
        # A MagicMock media_item leaks Mock objects into translate_file's
        # derive_episode_key() (re.sub on a Mock → TypeError), arr_kind, arr_metadata,
        # and tvdb_id/tmdb_id reads. Use a real MediaItem so the pipeline sees plain
        # str/int/None. source_type="episode" routes derive_episode_key to the SxxExx
        # parse (falls back to S00E00 when the filename has no SxxExx — fine for a
        # throwaway single-file run).
        from trezarr.arr.sonarr import MediaItem
        from trezarr.discover.scan import EligibleItem

        source_path = Path(args.source).resolve()
        media_item = MediaItem(
            local_path=source_path,
            title=source_path.stem,
            source_type="episode",
            series_id=args.series_id if args.series_id is not None else 0,
            season_number=0,
            arr_kind="sonarr",
        )
        eligible_item = EligibleItem(
            media_item=media_item,
            source_sub_path=source_path,
            reason="dev runner",
            source_lang="en",
        )

        # ── 10. Resolve output path ────────────────────────────────────────────
        if args.out:
            out_path = Path(args.out)
        else:
            # Default: same directory as source, replacing .en.srt → .vi.srt
            # WARNING: this places the output next to the source file. Use --out to redirect.
            out_path = source_path.parent / (source_path.stem.replace(".en", "") + ".vi.srt")

        # ── 11. Banner ────────────────────────────────────────────────────────
        print("Trezarr translate_one.py — dev runner")
        print(f"  Source:    {source_path}")
        print(f"  Output:    {out_path}")
        print(f"  Series ID: {eligible_item.media_item.series_id}")
        print(f"  LLM:       {settings_with_overrides.llm_base_url} / {settings_with_overrides.llm_model}")
        print("Running pipeline (Pass 1 analyze → Pass 2 attribute → Pass 3 translate → Pass 4 review)…")

        # ── 12. Run translate_file ────────────────────────────────────────────
        from trezarr.translate.engine import translate_file

        t0 = time.monotonic()
        result = await translate_file(
            path=source_path,
            settings=settings_with_overrides,
            llm_client=llm_client,
            ledger=ledger,
            eligible_item=eligible_item,
            session_factory=session_factory,
        )
        elapsed = time.monotonic() - t0

        # ── 13. Print result ──────────────────────────────────────────────────
        if result.status == "done":
            print(f"DONE in {elapsed:.1f}s — output: {result.output_path}")
        elif result.status == "quarantined":
            print(f"QUARANTINED in {elapsed:.1f}s — reason: {result.reason}")
            print(f"Artifact: {result.quarantine_path}")
        elif result.status == "skipped":
            print("SKIPPED (ledger says already done for this hash)")
        else:
            print(f"Unknown status '{result.status}' in {elapsed:.1f}s")

    finally:
        await engine.dispose()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
