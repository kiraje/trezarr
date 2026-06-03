"""Config read/write service for the settings API (D-70).

Design decisions honoured:
  D-70  GET /api/settings must NEVER return raw SecretStr values. Every SECRET_FIELDS
        entry is replaced with {"is_set": bool, "value": "**REDACTED**"}. The sentinel
        pattern is the read-only wire representation. Writes only update a secret field
        when the caller sends something OTHER than the sentinel (i.e. a real new key).
  D-70  Env-var-sourced settings keep their existing TREZARR_* > YAML precedence.
        get_env_locked_fields() surfaces which fields are currently controlled by env vars
        so the UI can mark them read-only / "set by environment".

Security:
  - settings_to_display_dict() NEVER calls .get_secret_value() and puts it in the result.
  - write_settings_to_yaml() skips any secret field whose patch value == SENTINEL.
  - CONFIG_PATH is a process-level constant from config.py — never derived from user input.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import yaml

from trezarr.config import CONFIG_PATH

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings


# ── Constants ─────────────────────────────────────────────────────────────────

# Canonical set of secret field names. Used to mask values on the GET path and
# to skip sentinel values on the PUT path. Must stay in sync with TrezarrSettings.
SECRET_FIELDS: frozenset[str] = frozenset({
    "llm_api_key",
    "sonarr_api_key",
    "radarr_api_key",
    "bazarr_api_key",
})

# Wire sentinel — returned by GET for every secret field, and recognised on PUT
# as "leave the stored secret unchanged". The UI must display this value as a
# masked placeholder and must NOT write it back to the server unchanged.
SENTINEL: str = "**REDACTED**"

# Settings fields that cannot be hot-reloaded — changing these requires a
# daemon restart. The PUT handler includes these names in `restart_required`.
# WR-03: poll_interval_seconds is baked into the APScheduler job at startup
# (setup_scheduler registers it with a fixed `seconds=` kwarg). A hot PUT
# updates app.state.settings but does NOT reschedule the job, so the interval
# change is silently ignored at runtime. Report it as restart-required so the
# UI does not mislead operators.
RESTART_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "bible_db_url",
    "web_host",
    "web_port",
    "poll_interval_seconds",
})


# ── Public API ─────────────────────────────────────────────────────────────────


def settings_to_display_dict(settings: "TrezarrSettings") -> dict:
    """Return a JSON-safe dict of all settings with secrets masked.

    SECRET_FIELDS entries are replaced with {"is_set": bool, "value": SENTINEL}.
    Every other field is included as-is from model_dump().

    The raw secret value is NEVER called via .get_secret_value() and placed in
    the returned dict — that is a hard security invariant (D-70 / T-07-04-01).

    Args:
        settings: TrezarrSettings instance.

    Returns:
        dict with all fields. Secret fields have value {"is_set": bool, "value": "**REDACTED**"}.
    """
    raw = settings.model_dump()

    for field in SECRET_FIELDS:
        if field in raw:
            # Inspect whether the secret is meaningfully set WITHOUT exposing the value.
            # SecretStr.__bool__ returns False for empty strings; .get_secret_value()
            # is called ONLY to check truthiness and the result is discarded — it never
            # enters the output dict.
            secret_attr = getattr(settings, field, None)
            is_set: bool = bool(
                secret_attr is not None
                and secret_attr.get_secret_value()  # truthy check; value discarded
            )
            raw[field] = {"is_set": is_set, "value": SENTINEL}

    return raw


def write_settings_to_yaml(current: "TrezarrSettings", patch: dict) -> None:
    """Write patched settings values to /config/config.yaml via yaml.safe_dump.

    Only values present in ``patch`` are written — existing YAML keys for
    un-patched fields are left intact. Secret fields whose patch value equals
    the SENTINEL are silently skipped (the stored secret is not overwritten).

    Path-traversal: CONFIG_PATH is a process-constant from config.py. The
    ``patch`` dict is a Pydantic-validated body (field name → primitive value),
    not a file path — no traversal vector (T-07-04-03 mitigated).

    Args:
        current: The current TrezarrSettings (used for type reference; not written).
        patch:   A flat dict of field_name → new_value. Typically from the PUT body.

    Raises:
        OSError: If the config file cannot be written (caller wraps in HTTP 500).
    """
    # Load existing YAML, or start from an empty dict if the file is missing/empty.
    existing: dict = {}
    try:
        with open(CONFIG_PATH) as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                existing = loaded
    except FileNotFoundError:
        pass  # No existing file — will be created fresh.

    # WR-04: filter patch to only known TrezarrSettings field names before writing.
    # Unknown keys (e.g., typos, injected junk, future UI bugs) are dropped so
    # they never land in config.yaml. pydantic-settings silently ignores unknown
    # YAML keys on load, so they would accumulate undetected without this guard.
    # Access model_fields on the class (not the instance) — Pydantic V2.11+ deprecates
    # instance-level access of model_fields.
    known_fields = set(type(current).model_fields.keys())

    # Apply the patch, skipping sentinel secret values and unknown fields.
    for key, value in patch.items():
        if key not in known_fields:
            logger.warning("write_settings_to_yaml: ignoring unknown field %r", key)
            continue
        if key in SECRET_FIELDS and value == SENTINEL:
            # Sentinel means "unchanged" — do NOT overwrite the stored secret.
            continue
        existing[key] = value

    # Bug 3: when a *arr connection's host + api_key are both non-empty after applying
    # the patch, auto-set the corresponding *_enabled = True so discovery/listing works
    # without requiring the user to flip the toggle manually.
    for svc in ("sonarr", "radarr", "bazarr"):
        host_key = f"{svc}_host"
        api_key_key = f"{svc}_api_key"
        enabled_key = f"{svc}_enabled"
        host_val = existing.get(host_key, "")
        api_key_val = existing.get(api_key_key, "")
        # Only auto-enable; never auto-disable (the user may have explicitly disabled).
        if host_val and api_key_val and api_key_val != SENTINEL:
            if not existing.get(enabled_key, False):
                existing[enabled_key] = True
                logger.debug(
                    "write_settings_to_yaml: auto-enabled %s (host+key both set)", enabled_key
                )

    # Ensure the parent directory exists (e.g., /config/ may not be mounted in tests).
    config_path = CONFIG_PATH
    import pathlib  # noqa: PLC0415
    pathlib.Path(config_path).parent.mkdir(parents=True, exist_ok=True)

    # Write back. safe_dump escapes special chars; unicode is allowed (Vietnamese content).
    with open(config_path, "w") as f:
        yaml.safe_dump(existing, f, default_flow_style=False, allow_unicode=True)


def get_env_locked_fields(settings: "TrezarrSettings") -> list[str]:
    """Return the list of setting field names currently controlled by TREZARR_* env vars.

    Implementation: scan os.environ for keys matching TREZARR_{FIELD_NAME.upper()}.
    This is the MVP approach per D-70: not 100% precise (env may be identical to
    YAML), but safe and predictable for UI display.

    Args:
        settings: TrezarrSettings instance (provides the field name list).

    Returns:
        List of field names that have a matching TREZARR_* env var set.
    """
    env_prefix = "TREZARR_"
    locked: list[str] = []

    for field_name in settings.model_fields:
        env_key = f"{env_prefix}{field_name.upper()}"
        if env_key in os.environ:
            locked.append(field_name)

    return locked
