"""TrezarrSettings — layered config via pydantic-settings (D-11).

Priority order (highest to lowest):
  1. Programmatic init overrides (e.g. LLMClient(settings=TrezarrSettings(llm_model="x")))
  2. TREZARR_* environment variables
  3. YAML config file (default: /config/config.yaml; overridable via TREZARR_CONFIG_PATH or
     the ``_yaml_file`` init arg — used in tests to avoid requiring /config/config.yaml)
  4. Python-defined defaults in this class

Security: llm_api_key is a SecretStr.  Its literal value NEVER appears in str(), repr(), or
model_dump() output (T-01-03-01, D-11).  Call .get_secret_value() ONLY inside LLMClient.__init__.
"""
import os
import threading
from typing import Any, Tuple, Type

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from trezarr.paths import PathMapping

# Default config-file path: Docker /config volume convention (*arr ecosystem).
# Override at startup via TREZARR_CONFIG_PATH env var.
CONFIG_PATH: str = os.environ.get("TREZARR_CONFIG_PATH", "/config/config.yaml")

# Thread-local storage used to pass a per-instantiation yaml_file override from
# __init__ (instance context) to settings_customise_sources (classmethod context).
# This is the only reliable way to thread-through a per-call override to a classmethod
# without mutating shared class state.
_tl: threading.local = threading.local()


class TrezarrSettings(BaseSettings):
    """Project-wide settings loaded from env vars and/or a YAML config file.

    All fields use the ``TREZARR_`` prefix when read from environment variables.
    Example: ``TREZARR_LLM_MODEL=my-model`` → ``settings.llm_model == "my-model"``.
    """

    model_config = SettingsConfigDict(
        env_prefix="TREZARR_",
        env_nested_delimiter="__",
        # NOTE: yaml_file in model_config alone is silently ignored in pydantic-settings 2.x
        # (emits a UserWarning only).  YamlConfigSettingsSource MUST be registered via
        # settings_customise_sources instead (Pitfall 5 in 01-RESEARCH.md).
    )

    # ── LLM endpoint (D-03, D-05) ──────────────────────────────────────────────
    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: SecretStr = SecretStr("not-set")  # NEVER logged; SecretStr masks in repr/str
    llm_model: str = "gpt-4o"

    # ── Retry + reliability (D-07) ─────────────────────────────────────────────
    llm_max_retries: int = 4         # SDK default is 2; D-07 requires 4 explicitly
    llm_request_timeout: float = 120.0

    # ── Concurrency cap (D-06) ─────────────────────────────────────────────────
    llm_max_concurrency: int = 4    # asyncio.Semaphore cap (default 4)

    # ── Structured-output tier (D-04) ──────────────────────────────────────────
    llm_structured_output_mode: str = "auto"  # auto | json_schema | json_object | text

    # ── Context window (D-05 — used by Phase 2 batching) ──────────────────────
    llm_context_window: int = 32768

    # ── Phase 2: Batching (D-14) ───────────────────────────────────────────────────
    translate_chars_per_token: float = 3.5
    translate_overhead_fraction: float = 0.30
    translate_output_expansion: float = 1.40
    translate_max_cues_per_batch: int = 50
    translate_scene_gap_ms: int = 2000

    # ── Phase 2: Context window (D-15) ──────────────────────────────────────────────────
    translate_context_lines_k: int = 3

    # ── Phase 2: Retry + quarantine (D-18) ───────────────────────────────────────────────
    translate_batch_retry_attempts: int = 2

    # ── Phase 2: Validation gate (D-17) ──────────────────────────────────────────────────
    translate_vi_diacritic_ratio: float = 0.70

    # ── Phase 2: Output paths (D-18, D-20) ───────────────────────────────────────────────
    translate_quarantine_dir: str = "/config/quarantine"
    translate_ledger_path: str = "/config/processed_files.json"

    # ── Phase 3: *arr connection (D-22) ────────────────────────────────────────
    sonarr_host: str = ""
    sonarr_port: int = 8989
    sonarr_api_key: SecretStr = SecretStr("")  # NEVER logged; SecretStr masks in repr/str
    sonarr_enabled: bool = False
    radarr_host: str = ""
    radarr_port: int = 7878
    radarr_api_key: SecretStr = SecretStr("")  # NEVER logged; SecretStr masks in repr/str
    radarr_enabled: bool = False

    # ── Phase 3: Path mapping (D-23) ───────────────────────────────────────────
    # Env: TREZARR_PATH_MAPPINGS='[{"remote":"/tv","local":"/data/tv"}]' (JSON array string)
    # YAML: path_mappings: [{remote: /tv, local: /data/tv}]
    # NOTE: Field(default_factory=list) — NOT literal []. Pydantic v2 generally copies
    # model defaults, but the safer & clearer pattern is default_factory for mutable
    # defaults so each instance gets its own list object (03-REVIEWS.md HIGH #1).
    path_mappings: list[PathMapping] = Field(default_factory=list)

    # ── Phase 3: Source-language priority (D-25) ───────────────────────────────
    # NOTE: Field(default_factory=lambda: ["en"]) — NOT literal ["en"]. Same
    # mutable-default-safety rationale as path_mappings (03-REVIEWS.md HIGH #1).
    source_lang_priority: list[str] = Field(default_factory=lambda: ["en"])

    # ── Phase 3: Permissions (D-29) ────────────────────────────────────────────
    # PUID/PGID = -1 means "leave unchanged" (POSIX os.chown convention).
    # umask is the int value only; apply_permissions() computes 0o666 & ~umask per-call.
    # NEVER call os.umask() — that is process-global and unsafe in async code.
    puid: int = -1
    pgid: int = -1
    umask: int = 0o022

    # ── Phase 4: Series Bible persistence (D-31, D-38) ─────────────────────────
    # bible_db_url: SQLite DB at the /config volume convention (*arr ecosystem).
    # NOT a SecretStr — it is a file path, not a secret.
    # Four slashes in sqlite+aiosqlite:////config/... are correct: protocol://[empty-host]/abs-path.
    bible_db_url: str = "sqlite+aiosqlite:////config/trezarr.db"
    bible_db_run_migrations_on_startup: bool = True
    # Toggle PRAGMAs at engine construction — default ON per D-38.
    # Only flip these in tests that need to verify the toggle behaviour.
    bible_db_enable_wal: bool = True
    bible_db_enforce_fk: bool = True

    # ── Phase 5: Three-Pass Pronoun Engine (D-40…D-50) ──────────────────────────
    # Pass 1 — Bible analysis
    enable_pass1_analysis: bool = True         # D-50: toggle for staged rollout/tests
    pass1_max_cues_per_chunk: int = 400        # D-50: cues per Pass-1 chunk (0 = no chunk)

    # Pass 2 — Attribution
    enable_attribution: bool = True            # D-50: toggle; False → all lines get safe default
    attribute_context_lines_k: int = 8         # D-50: wider context than translate (default 3)
    attribute_max_cues_per_batch: int = 30     # D-50: attribution batches may be smaller

    # Pass 3 — Pronoun application
    pronoun_confidence_threshold: str = "medium"    # D-45/D-50: "high"|"medium"|"low"
    # None → use built-in kinship-table defaults (D-45); tuple → user override
    # NOTE: tuple[str,str]|None — pydantic-settings handles JSON array env var (A4 from RESEARCH.md)
    # Use Field(default=None) explicitly to avoid default_factory/mutable default issues
    pronoun_safe_default: tuple[str, str] | None = Field(default=None)  # D-50

    # ── Phase 6: Relationship Evolution + Self-Review (D-51…D-60) ──────────────────
    # Capability A — Relationship Evolution (BIBLE-07)
    enable_relationship_events: bool = True         # D-60: toggle for staged rollout/tests
    relationship_event_min_confidence: float = 0.0  # min confidence to emit (0.0 = all)

    # Capability B — Self-Review Pass (ENG-05)
    enable_self_review: bool = True                 # D-60: toggle for staged rollout/tests
    self_review_context_lines_k: int = 3            # context K for review batches (translate default)
    self_review_max_cues_per_batch: int = 20        # smaller batches → fewer tokens per review call

    # ── Phase 7: Service runtime (D-76, D-77) ──────────────────────────────────
    web_host: str = "0.0.0.0"
    web_port: int = 6868
    poll_interval_seconds: int = 900                # D-76: 15-minute default poll interval
    enable_webhooks: bool = True                    # D-77: toggle webhook receiver
    enable_watchfiles: bool = False                 # D-65: default-off; deferred within phase
    worker_max_concurrent_series: int = 2           # D-68: distinct series in parallel

    # ── Phase 7: Bazarr connection (D-76) ──────────────────────────────────────
    # Connection + webhook ONLY. Inventory reads are Phase 10 (INTG-02).
    bazarr_host: str = ""
    bazarr_port: int = 6767
    bazarr_api_key: SecretStr = SecretStr("")       # NEVER logged; SecretStr masks in repr/str
    bazarr_enabled: bool = False
    # Phase 10: Bazarr inventory use (D-104)
    bazarr_use_inventory: bool = True   # When True: query Bazarr for subtitle inventory.
                                        # When False: degrade to filesystem glob (find_source_sub).

    def __init__(self, _yaml_file: str | None = None, **data: Any) -> None:
        """Create settings.

        Args:
            _yaml_file: Optional path to a YAML config file.  Overrides CONFIG_PATH for
                this instantiation only.  Used in tests to supply a temp config without
                requiring /config/config.yaml to exist.
            **data: Field overrides passed through to BaseSettings (and pydantic).
        """
        _tl.yaml_file = _yaml_file  # make available to settings_customise_sources
        try:
            super().__init__(**data)
        finally:
            _tl.yaml_file = None  # always clean up — never leak across threads

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> Tuple:
        """Register config sources in priority order.

        This override is REQUIRED.  Using ``yaml_file=`` in model_config alone is silently
        ignored by pydantic-settings 2.x — YamlConfigSettingsSource must be explicitly
        registered here (Pitfall 5, empirically confirmed 2026-05-31).
        """
        yaml_file = getattr(_tl, "yaml_file", None) or CONFIG_PATH
        return (
            init_settings,        # highest priority: programmatic overrides
            env_settings,         # TREZARR_* environment variables
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file),
            file_secret_settings,
        )
