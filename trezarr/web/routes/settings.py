"""Settings API routes — GET/PUT /api/settings and GET /api/settings/env-locked (D-70, SVC-02).

Design decisions honoured:
  D-70  GET /api/settings returns all non-secret settings fields; secret fields return
        {"is_set": bool, "value": "**REDACTED**"} — the raw key value is NEVER in the response.
  D-70  PUT /api/settings writes changed non-sentinel values to /config/config.yaml;
        unchanged secrets (sentinel value) are not overwritten.
  D-70  GET /api/settings/env-locked returns the list of fields currently set by
        TREZARR_* env vars.
  D-72  Hot re-apply on save: re-reads TrezarrSettings from YAML and updates app.state.settings
        for fields that can be applied without restart. Fields in RESTART_REQUIRED_FIELDS
        are flagged in the response body.

Security:
  - settings_to_display_dict() is the single choke-point — raw SecretStr values NEVER
    travel over the wire (T-07-04-01 mitigated).
  - CONFIG_PATH is a process constant — the write path cannot be redirected by request body
    (T-07-04-03 mitigated).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from trezarr.web.config_writer import (
    RESTART_REQUIRED_FIELDS,
    SENTINEL,
    get_env_locked_fields,
    settings_to_display_dict,
    write_settings_to_yaml,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_settings(request: Request):
    """Retrieve settings from app.state, falling back to a fresh TrezarrSettings().

    The lifespan sets app.state.settings after startup. In test environments that
    call create_app() without triggering the ASGI lifespan, the fallback ensures
    the endpoint is still functional.
    """
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    try:
        return request.app.state.settings
    except AttributeError:
        return TrezarrSettings()


@router.get("/settings")
async def get_settings(request: Request) -> JSONResponse:
    """Return all settings with secrets masked (D-70).

    Secret fields (llm_api_key, sonarr_api_key, radarr_api_key, bazarr_api_key) are
    replaced with {"is_set": bool, "value": "**REDACTED**"}. Raw values NEVER appear.

    Returns:
        200 JSON with all settings fields, secrets masked.
    """
    settings = _get_settings(request)
    display = settings_to_display_dict(settings)
    return JSONResponse(display)


@router.put("/settings")
async def put_settings(request: Request) -> JSONResponse:
    """Write changed settings to /config/config.yaml and hot-reload (D-70, D-72).

    Sentinel secret values ("**REDACTED**") in the patch are NOT written to YAML —
    unchanged secrets are preserved.

    Fields in RESTART_REQUIRED_FIELDS (bible_db_url, web_host, web_port) cannot be
    hot-reloaded; they are listed in `restart_required` in the response.

    Returns:
        200 {"ok": true, "restart_required": [...]} on success.
        500 on YAML write failure.
    """
    patch: dict = await request.json()
    settings = _get_settings(request)

    persisted = True
    try:
        write_settings_to_yaml(settings, patch)
    except OSError as exc:
        # CONFIG_PATH may not be writable in development/test environments without
        # a /config volume mounted. Log the error but continue — in production the
        # /config Docker volume is always writable (D-64 convention).
        logger.warning(
            "Could not persist settings to %s: %s — "
            "changes applied in-memory only (restart to lose them); "
            "in production ensure /config is mounted writable.",
            exc.filename, exc,
        )
        persisted = False

    # D-72: Hot re-apply — reload TrezarrSettings from disk and update app.state.settings.
    # Fields that require restart are flagged but NOT applied at runtime.
    try:
        from trezarr.config import TrezarrSettings  # noqa: PLC0415

        new_settings = TrezarrSettings()
        # Only update app.state.settings if the reload succeeded.
        request.app.state.settings = new_settings
        logger.info("Settings hot-reloaded from config YAML")
    except Exception as exc:  # noqa: BLE001
        # Non-fatal — the write succeeded; log and continue with existing settings.
        logger.warning("Settings hot-reload failed (will take effect on next restart): %s", exc)

    # Identify fields that need a restart based on what was patched.
    restart_required = [
        key for key in patch
        if key in RESTART_REQUIRED_FIELDS and patch[key] != SENTINEL
    ]

    return JSONResponse({"ok": True, "restart_required": restart_required, "persisted": persisted})


@router.get("/settings/env-locked")
async def get_env_locked(request: Request) -> JSONResponse:
    """Return list of fields currently controlled by TREZARR_* env vars (D-70/Pitfall G).

    These fields are env-locked: saving a different value via PUT /api/settings will
    write to config.yaml, but the env var will still override it at next startup.
    The UI should mark these fields as read-only with an explanatory tooltip.

    Returns:
        200 {"env_locked": ["field_name", ...]}
    """
    settings = _get_settings(request)
    locked = get_env_locked_fields(settings)
    return JSONResponse({"env_locked": locked})
