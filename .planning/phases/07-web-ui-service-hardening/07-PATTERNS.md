# Phase 7: Web UI & Service Hardening — Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 22 new/modified files
**Analogs found:** 19 / 22 (3 greenfield — frontend SPA)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trezarr/web/__init__.py` | package-init | — | `trezarr/bible/__init__.py` | role-match |
| `trezarr/web/app.py` | service-runtime | request-response + event-driven | `trezarr/cli.py::_run_once` (lifespan/CR-01) + `trezarr/db/engine.py` | exact (CR-01 pattern) |
| `trezarr/web/routes/settings.py` | API-endpoint | request-response | `trezarr/config.py` (TrezarrSettings) | role-match |
| `trezarr/web/routes/test_connection.py` | API-endpoint | request-response | `trezarr/arr/sonarr.py` (build_sonarr_client + DiscoveryError) | role-match |
| `trezarr/web/routes/queue.py` | API-endpoint | request-response | `trezarr/output/ledger_sqla.py` (async session SELECT pattern) | role-match |
| `trezarr/web/routes/webhook.py` | API-endpoint | event-driven | `trezarr/cli.py::_run_pipeline_steps` (enqueue-only) | role-match |
| `trezarr/web/worker.py` | worker | event-driven + CRUD | `trezarr/cli.py::_run_pipeline_steps` (per-item callable) | exact |
| `trezarr/web/scheduler.py` | worker | event-driven | `trezarr/cli.py` (APScheduler setup in lifespan) | role-match |
| `trezarr/web/config_writer.py` | service | CRUD | `trezarr/config.py` (TrezarrSettings + SecretStr masking) | role-match |
| `trezarr/jobs/__init__.py` | package-init | — | `trezarr/bible/__init__.py` | role-match |
| `trezarr/jobs/models.py` | persistence | CRUD | `trezarr/bible/models.py` (typed declarative Base models) | exact |
| `alembic/versions/0002_job_queue.py` | migration | CRUD | `alembic/versions/0001_baseline_bible_schema.py` | exact |
| `alembic/env.py` | config | — | `alembic/env.py` (modify: add jobs import) | modify |
| `trezarr/config.py` | config | — | `trezarr/config.py` (add Phase-7 header block) | modify |
| `trezarr/cli.py` | service-runtime | request-response | `trezarr/cli.py` (add serve subparser) | modify |
| `tests/web/__init__.py` | test | — | `tests/db/__init__.py` | role-match |
| `tests/web/test_lifespan.py` | test | request-response | `tests/db/test_migrations.py` (db_engine fixture + async test) | role-match |
| `tests/web/test_settings_api.py` | test | request-response | `tests/config/test_settings.py` | role-match |
| `tests/web/test_connection_tests.py` | test | request-response | `tests/arr/test_arr_discovery.py` (httpx_mock pattern) | exact |
| `tests/web/test_jobs_api.py` | test | CRUD | `tests/output/test_ledger_sqla.py` (async DB fixture) | role-match |
| `tests/web/test_webhook.py` | test | event-driven | `tests/arr/test_arr_discovery.py` | role-match |
| `tests/web/test_worker.py` | test | event-driven | `tests/db/conftest.py` + `tests/integration/` | role-match |
| `Dockerfile` | config | — | (no analog — greenfield; RESEARCH.md Pattern 6 + D-64) | none |
| `docker-compose.example.yml` | config | — | (no analog — greenfield) | none |
| `frontend/` (SPA) | frontend | request-response | (no analog — greenfield React 19 + Vite 7) | none |

---

## Pattern Assignments

### `trezarr/web/app.py` (service-runtime, request-response + event-driven)

**Analog:** `trezarr/cli.py::_run_once` (lines 106–206) — the CR-01 engine lifecycle pattern

**Mirror this because:** The lifespan function must own the AsyncEngine for the whole process lifetime (not per-run), disposing it in shutdown exactly as `_run_once`'s `finally: await engine.dispose()` does — the same CR-01 bug appears at process scope if this is wrong.

**Imports pattern** (`cli.py` lines 39–64):
```python
from trezarr.config import TrezarrSettings
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head
from trezarr.db.session import build_session_factory
from trezarr.paths import assert_media_roots_configured, build_media_roots, probe_media_roots
```

**Startup sequence pattern** (`cli.py` lines 142–201 — adapt to lifespan):
```python
# Step 1: settings + logging
settings = TrezarrSettings()
logging.basicConfig(level=logging.INFO)

# Step 2: assert_media_roots_configured FIRST (refuses empty path_mappings when arr enabled)
assert_media_roots_configured(settings)

# Step 3: probe BEFORE any API call
media_roots = build_media_roots(settings)
probe_media_roots(media_roots)

# Step 3.5: engine created BEFORE the outer try, so its existence is
# unambiguous on every dispose path (CR-01 comment in cli.py lines 156-166)
engine = build_engine(settings)
try:
    await run_migrations_to_head(engine)
    session_factory = build_session_factory(engine)
    # ... scheduler / worker startup ...
    yield    # ← only in lifespan (not in _run_once)
finally:
    # CR-01: ALWAYS dispose before the coroutine returns
    await engine.dispose()
```

**Lifespan shutdown pattern** — add before `engine.dispose()`:
```python
finally:
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    scheduler.shutdown(wait=False)
    await engine.dispose()   # CR-01 at process scope
```

**SPA static file mount** — must be LAST, after all API routers:
```python
# RESEARCH.md Pattern 6: API routes FIRST, StaticFiles LAST
app.include_router(settings_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(webhook_router)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
```

---

### `trezarr/web/worker.py` (worker, event-driven + CRUD)

**Analog:** `trezarr/cli.py::_run_pipeline_steps` (lines 209–420)

**Mirror this because:** The per-item body of the worker is exactly `_run_pipeline_steps` — the worker callable must replicate the same discover→scan→translate→apply_permissions flow. D-62 says this body is extracted and reused by both the CLI and the new worker.

**Per-item callable skeleton** (mirrors `_run_pipeline_steps` loop body, `cli.py` lines 294–376):
```python
async def _execute_job(job_id: int, session_factory, settings, ledger, media_roots, llm_client):
    # Same structure as _run_pipeline_steps loop body:
    source_sub_path = eligible_item.source_sub_path
    try:
        result = await translate_file(
            source_sub_path,
            settings,
            llm_client,
            ledger,
            eligible_item=eligible_item,
            session_factory=session_factory,
        )
        if result.status == "done":
            if media_roots:
                assert_within_media_roots(result.output_path, media_roots)
            apply_permissions(result.output_path, settings.puid, settings.pgid, settings.umask)
        # ... handle skipped/quarantined/unknown as in _run_pipeline_steps
    except Exception:
        logger.exception("unhandled error translating %s", source_sub_path)
```

**Per-series lock pattern** (D-68; no second Semaphore — see `cli.py` lines 33–36 SEQUENTIAL note):
```python
_series_locks: dict[int, asyncio.Lock] = {}   # keyed by series_id; lazily created

async def _execute_job(job_id, ...):
    # ...
    lock = _series_locks.setdefault(series_id, asyncio.Lock())
    async with lock:          # BINARY lock — not a Semaphore (D-68 / Pitfall C)
        await _do_translate(...)
```

**Crash-resume reconciliation** (D-67; mirrors `gap.py` Case 4 logic):
```python
async def reconcile_in_progress(session_factory):
    """On startup, re-enqueue any job rows left running/queued by a crashed process."""
    async with session_factory() as session:
        result = await session.execute(
            select(Job).where(Job.status.in_(["queued", "running"]))
        )
        for job in result.scalars():
            job.status = "queued"
            await _work_queue.put(job.id)
        await session.commit()
```

---

### `trezarr/jobs/models.py` (persistence, CRUD)

**Analog:** `trezarr/bible/models.py` — specifically `BibleEvent` (append-log with `CheckConstraint` + `server_default=func.current_timestamp()`) and `ProcessedFile` (status enum with `CheckConstraint`).

**Mirror this because:** All SQLAlchemy 2.0 typed declarative models in this project use `Mapped[T] = mapped_column(...)`, `Base` from `trezarr.db.base`, `CheckConstraint` for enum columns, and `server_default=func.current_timestamp()` for audit timestamps — copy this exact pattern for `Job` and `JobLog`.

**Import pattern** (`bible/models.py` lines 31–46):
```python
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from trezarr.db.base import Base
```

**CheckConstraint + status enum pattern** (`bible/models.py` lines 288–305 — `ProcessedFile`):
```python
class ProcessedFile(Base):
    __tablename__ = "processed_file"
    __table_args__ = (
        CheckConstraint(
            "status IN ('done', 'quarantined', 'in_progress')",
            name="ck_processed_file_status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
```

**Timestamp with server_default** (`bible/models.py` lines 212–216 — `RelationshipEvent`):
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime, server_default=func.current_timestamp()
)
```

**Job model shape** (D-69 + RESEARCH.md Pattern 4):
```python
class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','failed','quarantined')",
            name="ck_job_status",
        ),
        CheckConstraint(
            "trigger IN ('poll','webhook','manual-retry','startup-reconcile')",
            name="ck_job_trigger",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

class JobLog(Base):
    __tablename__ = "job_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
```

---

### `alembic/versions/0002_job_queue.py` (migration, CRUD)

**Analog:** `alembic/versions/0001_baseline_bible_schema.py` — the entire file is the template.

**Mirror this because:** The chaining convention (`down_revision = "0001"`), `sa.CheckConstraint` usage, `sa.text("(CURRENT_TIMESTAMP)")` for server defaults, index creation AFTER table creation, and the FK-safe table order are all established by the 0001 migration.

**File header pattern** (`0001_baseline_bible_schema.py` lines 32–35):
```python
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"   # ← chains off Phase-4 baseline
branch_labels = None
depends_on = None
```

**Table creation with CheckConstraint + server_default** (`0001_baseline_bible_schema.py` lines 136–179):
```python
def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_path", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column(
            "enqueued_at", sa.DateTime, nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed','quarantined')",
            name="ck_job_status",
        ),
    )
    op.create_table("job_log", ...)
    # Create indexes AFTER tables (FK-safe order from 0001):
    op.create_index("ix_job_source_path", "job", ["source_path"])
    op.create_index("ix_job_log_job_id", "job_log", ["job_id"])

def downgrade() -> None:
    op.drop_index("ix_job_log_job_id", table_name="job_log")
    op.drop_index("ix_job_source_path", table_name="job")
    op.drop_table("job_log")
    op.drop_table("job")
```

---

### `alembic/env.py` (modify — add jobs model import)

**Analog:** `alembic/env.py` line 24 — the existing `from trezarr.bible import models` import.

**Mirror this because:** The pattern comment on line 24–26 explains exactly what to copy: a noqa-F401 import that registers model classes into `Base.metadata` for autogenerate. New `Job` and `JobLog` models need the same treatment.

**Add after existing bible import** (`alembic/env.py` line 24):
```python
from trezarr.bible import models  # noqa: F401 — LIVE import (Pitfall 8 in 04-RESEARCH.md)
from trezarr.jobs import models as _job_models  # noqa: F401 — registers Job/JobLog into Base.metadata
```

---

### `trezarr/config.py` (modify — add Phase-7 settings block)

**Analog:** `trezarr/config.py` lines 128–153 — the Phase-5 and Phase-6 settings blocks under comment headers.

**Mirror this because:** Every phase adds settings under a `# ── Phase N: ... ──` header comment, with `# D-NN:` inline annotations, `SecretStr` for API keys, `Field(default_factory=...)` for mutable defaults, and a descriptive comment explaining the toggle purpose.

**Phase-5 settings block as template** (`config.py` lines 128–153):
```python
    # ── Phase 5: Three-Pass Pronoun Engine (D-40…D-50) ──────────────────────────
    # Pass 1 — Bible analysis
    enable_pass1_analysis: bool = True         # D-50: toggle for staged rollout/tests
    pass1_max_cues_per_chunk: int = 400        # D-50: cues per Pass-1 chunk
```

**Phase-7 block to add** (mirror style, D-76/D-77):
```python
    # ── Phase 7: Service runtime (D-76, D-77) ──────────────────────────────────
    web_host: str = "0.0.0.0"
    web_port: int = 6868
    poll_interval_seconds: int = 900            # D-76: 15-minute default poll interval
    enable_webhooks: bool = True                # D-77: toggle webhook receiver
    enable_watchfiles: bool = False             # D-65: default-off; deferred within phase
    worker_max_concurrent_series: int = 2       # D-68: distinct series in parallel

    # ── Phase 7: Bazarr connection (D-76) ──────────────────────────────────────
    # Connection + webhook ONLY. Inventory reads are Phase 10 (INTG-02).
    bazarr_host: str = ""
    bazarr_port: int = 6767
    bazarr_api_key: SecretStr = SecretStr("")   # NEVER logged; SecretStr masks in repr/str
    bazarr_enabled: bool = False
```

---

### `trezarr/cli.py` (modify — add `serve` subparser)

**Analog:** `trezarr/cli.py` lines 80–103 — the existing `run` subparser registration.

**Mirror this because:** The `serve` subparser must follow the exact same argparse pattern (subparsers, `add_parser`, `add_argument`, dispatch on `args.command`) to preserve the `trezarr run --once` path unchanged while adding `trezarr serve`.

**Existing subparser pattern** (`cli.py` lines 80–103):
```python
subparsers = parser.add_subparsers(dest="command", required=True)

run_parser = subparsers.add_parser(
    "run",
    help="Run one pass of the discover → translate → write pipeline and exit (D-21).",
)
run_parser.add_argument("--once", action="store_true", required=True, ...)
run_parser.add_argument("--config", default=None, ...)

# Dispatch:
if args.command == "run" and args.once:
    raise SystemExit(asyncio.run(_run_once(args.config)))
```

**Serve subparser to add** (mirror the run pattern):
```python
serve_parser = subparsers.add_parser(
    "serve",
    help="Start the long-running daemon service (D-61, SVC-01).",
)
serve_parser.add_argument("--config", default=None, ...)

# Dispatch (add alongside the existing run dispatch):
elif args.command == "serve":
    from trezarr.web.app import run_serve
    run_serve(args.config)
```

---

### `trezarr/web/config_writer.py` (service, CRUD)

**Analog:** `trezarr/config.py` lines 33–191 — `TrezarrSettings`, `SecretStr` usage, `CONFIG_PATH`, `settings_customise_sources`.

**Mirror this because:** The config-writer reads from and writes back to `CONFIG_PATH`, must respect the same `SecretStr` masking discipline (D-11), and must never echo `llm_api_key`, `sonarr_api_key`, `radarr_api_key`, `bazarr_api_key` to the caller.

**SecretStr discipline pattern** (`config.py` lines 50, 89–94):
```python
llm_api_key: SecretStr = SecretStr("not-set")  # NEVER logged; SecretStr masks in repr/str
# Call .get_secret_value() ONLY inside LLMClient.__init__
```

**YAML priority / CONFIG_PATH** (`config.py` lines 24, 184–191):
```python
CONFIG_PATH: str = os.environ.get("TREZARR_CONFIG_PATH", "/config/config.yaml")

# settings_customise_sources defines env > YAML > defaults:
yaml_file = getattr(_tl, "yaml_file", None) or CONFIG_PATH
return (
    init_settings,        # highest priority: programmatic overrides
    env_settings,         # TREZARR_* environment variables
    YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file),
    file_secret_settings,
)
```

**Secret masking for API response** (D-70 — extend the discipline to the wire):
```python
SECRET_FIELDS = {"llm_api_key", "sonarr_api_key", "radarr_api_key", "bazarr_api_key"}
SENTINEL = "**REDACTED**"

def settings_to_display_dict(settings: TrezarrSettings) -> dict:
    raw = settings.model_dump()
    for field in SECRET_FIELDS:
        if field in raw:
            val = getattr(settings, field)
            raw[field] = {
                "is_set": bool(val and val.get_secret_value()),
                "value": SENTINEL,
            }
    return raw
```

---

### `trezarr/web/routes/test_connection.py` (API-endpoint, request-response)

**Analog:** `trezarr/arr/sonarr.py` — `build_sonarr_client` (lines 102–125), `discover_sonarr_items` error handling (lines 205–225).

**Mirror this because:** Connection-test endpoints call the same pyarr client construction, catch the same `PyarrError` hierarchy, and must apply the same `_normalize_arr_host` credential-strip before logging — the D-71 "never include API key in response or logs" rule is an extension of the WR-01 pattern in sonarr.py.

**PyarrError catch pattern** (`sonarr.py` lines 205–225):
```python
except PyarrError as exc:
    display_host = _normalize_arr_host(settings.sonarr_host)
    logger.error(
        "Sonarr discovery failed at %s:%d — %s: %s",
        display_host, settings.sonarr_port, type(exc).__name__, exc,
    )
    raise DiscoveryError(
        f"Sonarr discovery failed at {display_host}:{settings.sonarr_port}: "
        f"{type(exc).__name__}: {exc}"
    ) from exc
```

**Test-connection endpoint shape** (D-71):
```python
@router.post("/test/sonarr")
async def test_sonarr(body: SonarrConnectionParams, request: Request) -> dict:
    try:
        client = Sonarr(
            host=_normalize_arr_host(body.host),
            api_key=body.api_key,  # received from UI — never echoed back
            port=body.port, tls=False, api_ver="v3",
        )
        status = client.system.get_status()   # cheap ping
        return {"ok": True, "version": status.get("version")}
    except PyarrError as exc:
        # WR-01: strip credentials from display_host before returning
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        # NEVER include body.api_key in the error string
```

---

### `trezarr/web/routes/queue.py` (API-endpoint, CRUD)

**Analog:** `trezarr/output/ledger_sqla.py` — `LedgerSQLA.check` (lines 68–86) for the async `select` pattern.

**Mirror this because:** Queue and History endpoints perform async `select` queries against `Job` using the same `session_factory() as session` + `session.execute(select(...))` pattern that `LedgerSQLA` established.

**Async SELECT pattern** (`ledger_sqla.py` lines 78–86):
```python
async with self._session_factory() as session:
    result = await session.execute(
        select(ProcessedFile).where(ProcessedFile.source_path == key)
    )
    row = result.scalar_one_or_none()
```

**Retry endpoint — SELECT-then-UPDATE** (mirrors `ledger_sqla.py::record` lines 98–130):
```python
async with session_factory() as session:
    async with session.begin():
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404)
        job.status = "queued"
        job.error_reason = None
        job.attempts = 0
        job.trigger = "manual-retry"
    await _work_queue.put(job.id)
```

---

### `trezarr/web/routes/webhook.py` (API-endpoint, event-driven)

**Analog:** `trezarr/cli.py::_run_pipeline_steps` discovery section (lines 229–273) — specifically the enqueue-only contract.

**Mirror this because:** The webhook handler must never call `translate_file` — it returns 200 immediately after enqueueing, exactly as the D-66 decision mirrors the CLI's separation of discovery and translation.

**Webhook handler pattern** (D-66 + RESEARCH.md Pattern 10):
```python
@router.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    event_type = body.get("eventType", "unknown")
    series_id = body.get("series", {}).get("id")   # Sonarr; Radarr uses "movie"
    # Trigger a scan task — DO NOT await translate_file here (D-66, Pitfall D)
    asyncio.create_task(
        poll_and_enqueue(
            request.app.state.session_factory,
            request.app.state.settings,
            series_id_hint=series_id,
        )
    )
    return {"status": "accepted", "eventType": event_type}
```

---

### `tests/web/test_lifespan.py` (test, request-response)

**Analog:** `tests/db/test_migrations.py` (lines 1–50) and `tests/db/conftest.py` (full file).

**Mirror this because:** Lifespan tests need the same temp-file SQLite pattern (`tmp_path / "trezarr.db"`), the same `build_engine` + `run_migrations_to_head` fixture chain, and the same `asyncio_mode="auto"` implicit decoration. The 0002 migration test mirrors `test_baseline_creates_all_seven_tables`.

**Temp-file SQLite fixture pattern** (`tests/db/conftest.py` lines 29–51):
```python
@pytest_asyncio.fixture
async def db_engine(tmp_path):
    db_path = tmp_path / "trezarr.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    await run_migrations_to_head(engine)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)
```

**Migration verification pattern** (`tests/db/test_migrations.py` lines 32–49):
```python
async def test_0002_migration_creates_job_tables(db_engine):
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = {row[0] for row in result}
    assert "job" in tables
    assert "job_log" in tables
```

---

### `tests/web/test_connection_tests.py` (test, request-response)

**Analog:** `tests/arr/test_arr_discovery.py` (lines 33–72) — `httpx_mock` pattern for pyarr testing.

**Mirror this because:** Connection-test endpoints call pyarr which uses httpx internally; `httpx_mock` intercepts at the transport layer — identical to how `test_arr_discovery.py` mocks pyarr responses without a live *arr instance.

**httpx_mock pattern** (`tests/arr/test_arr_discovery.py` lines 33–67):
```python
def test_sonarr_connection_ok(httpx_mock):
    # pyarr is synchronous — use plain def test, not async def
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[...],
    )
    settings = TrezarrSettings(
        sonarr_enabled=True, sonarr_host="192.168.1.100",
        sonarr_port=8989, sonarr_api_key="test-key",
    )
    items = discover_sonarr_items(settings)
    assert len(items) == 1
```

---

### `tests/web/test_jobs_api.py` and `tests/web/test_worker.py` (test, CRUD + event-driven)

**Analog:** `tests/output/test_ledger_sqla.py` + `tests/db/conftest.py` (async DB fixture chain).

**Mirror this because:** These tests need an async SQLite DB with the 0002 migration applied, matching the `session_factory` fixture pattern exactly.

**Async DB test pattern** (`tests/output/test_ledger_sqla.py` structure — uses `session_factory` fixture from `tests/db/conftest.py`):
```python
# tests/web/conftest.py — extend db/conftest.py fixture for web tests
import pytest_asyncio
from tests.db.conftest import db_engine, session_factory  # re-export

@pytest_asyncio.fixture
async def web_session_factory(tmp_path):
    """Session factory with both 0001 + 0002 migrations applied."""
    db_path = tmp_path / "trezarr_web.db"
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",
    )
    engine = build_engine(settings)
    await run_migrations_to_head(engine)   # runs 0001 + 0002
    sf = async_sessionmaker(engine, expire_on_commit=False)
    yield sf
    await engine.dispose()
```

---

## Shared Patterns

### CR-01 Engine Lifecycle (apply to `trezarr/web/app.py`)
**Source:** `trezarr/cli.py` lines 156–206
**Rule:** Engine is created BEFORE the outer `try`. Every code path goes through `finally: await engine.dispose()`. In the lifespan, `yield` replaces the per-run work, but the `finally` is identical.
```python
engine = build_engine(settings)   # before try
try:
    await run_migrations_to_head(engine)
    # ... startup ...
    yield                          # lifespan only
finally:
    await engine.dispose()         # CR-01: always
```

### SecretStr Masking (apply to all API endpoints touching settings)
**Source:** `trezarr/config.py` lines 50, 89–94, and the module docstring
**Rule:** `.get_secret_value()` is called ONLY inside `LLMClient.__init__`. API responses must never include the raw value. Use the `is_set: bool` + sentinel pattern (D-70) for the HTTP surface.

### `expire_on_commit=False` (apply to all new session factories)
**Source:** `trezarr/db/session.py` lines 29–33
**Rule:** Every `async_sessionmaker` must be constructed with `expire_on_commit=False`. Default `True` causes `MissingGreenlet` after `await session.commit()` in async code (Pitfall 2).
```python
return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

### Per-Connection PRAGMA (do NOT replicate in web layer — already in `build_engine`)
**Source:** `trezarr/db/engine.py` lines 46–53
**Rule:** PRAGMAs are registered once via `event.listens_for(engine.sync_engine, "connect")` in `build_engine`. The web `lifespan` calls `build_engine(settings)` and gets them for free — do NOT add additional PRAGMA calls.

### `asyncio_mode="auto"` (apply to all new test files)
**Source:** `pyproject.toml [tool.pytest.ini_options]` (project-wide)
**Rule:** New test files in `tests/web/` do not need `@pytest.mark.asyncio` or `@pytest_asyncio.mark.asyncio` — `asyncio_mode="auto"` is set project-wide. Use `@pytest_asyncio.fixture` for async fixtures (not `@pytest.fixture`).

### Dedup guard for enqueueing (apply to `trezarr/web/worker.py`)
**Source:** `trezarr/output/ledger_sqla.py` lines 98–119 (SELECT-then-insert pattern)
**Rule:** Before inserting a new `Job` row, SELECT for an existing job with the same `source_path` and `status IN ('queued', 'running')`. If found, return False without inserting. Mirrors the ledger's `select_then_upsert` approach.

### D-30 batch resilience (apply to `trezarr/web/worker.py::_execute_job`)
**Source:** `trezarr/cli.py` lines 369–376
**Rule:** One bad item must never abort the worker loop. Wrap per-item execution in `except Exception: logger.exception(...)` — `logger.exception` captures the traceback automatically (WR-05).

---

## No Analog Found

Files with no close match in the codebase — planner uses RESEARCH.md patterns instead:

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `Dockerfile` | config | — | No existing Docker infrastructure; use RESEARCH.md D-64 + multi-stage node→python pattern |
| `docker-compose.example.yml` | config | — | No existing compose file; greenfield documentation artifact |
| `frontend/` (entire SPA) | frontend | request-response | No existing React/Vite code anywhere in the repo; greenfield. UI-SPEC.md is the contract: hand-rolled Tailwind, no shadcn, `react-router-dom`, `lucide-react`, `fetch` API client. |

---

## Metadata

**Analog search scope:** `trezarr/`, `tests/`, `alembic/`
**Files scanned:** 24 source files read; 50+ file paths examined via directory listing
**Pattern extraction date:** 2026-06-02

**Critical constraints to carry forward to planning:**
1. `engine = build_engine(...)` must appear BEFORE the outer `try` in `lifespan` — same CR-01 invariant as `cli.py` line 161.
2. `AsyncIOScheduler.start()` must be called INSIDE the lifespan (after the async context starts), never at module scope.
3. `StaticFiles` mount must be registered LAST, after all API routers — FastAPI matches in registration order.
4. Per-series serialization uses `asyncio.Lock` (binary ownership), NOT a second `asyncio.Semaphore` — the single `LLMClient._semaphore` (D-06) remains the only global LLM cap.
5. New `Job`/`JobLog` models must be imported in `alembic/env.py` alongside the existing `from trezarr.bible import models` line — Pitfall F.
