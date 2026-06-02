"""Connection-test endpoints — POST /api/test/{sonarr|radarr|bazarr|llm} (D-71, SVC-02).

Design decisions honoured:
  D-71  POST /api/test/* validates a candidate config and returns {ok: bool, error?: str}.
        API keys NEVER appear in the response or logs (T-07-04-02 mitigated).
        Error messages are truncated to 200 chars of the exception string — the exception
        string comes from pyarr's internal error (not the request body), so the api_key
        is not embedded in it. _normalize_arr_host strips any credential from the host.
  D-78  Single-user, trusted-LAN default — no rate limiting needed for v1.

Security discipline:
  - body.api_key is passed to the pyarr/httpx client and NEVER echoed back.
  - Error messages use str(exc)[:200] (pyarr exception message, not the request body).
  - _normalize_arr_host applied to display_host in error branches (WR-01).
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pyarr import Radarr, Sonarr
from pyarr.exceptions import PyarrError

from trezarr.arr import _normalize_arr_host
from trezarr.web.config_writer import SENTINEL

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request body models ────────────────────────────────────────────────────────

class ArrTestParams(BaseModel):
    """Connection parameters for Sonarr/Radarr/Bazarr test."""

    host: str
    port: int
    api_key: str  # received from UI — plaintext over trusted LAN (D-78); NEVER echoed back


class LLMTestParams(BaseModel):
    """Connection parameters for LLM endpoint test."""

    base_url: str
    api_key: str  # NEVER echoed back
    model: str


# ── Stored-credential fallback ───────────────────────────────────────────────

def _resolve_api_key(request: Request, field_name: str, provided: str) -> str:
    """Reuse the stored credential when the UI sends a blank/masked key (D-71).

    The Settings UI shows an already-saved key masked as "set" (MaskedSecretInput)
    and sends an EMPTY api_key when the operator clicks Test Connection without
    re-typing it — the sentinel is also treated as "unchanged" defensively. In
    that case fall back to the server-side stored secret (settings.{field_name})
    so the test reflects the saved configuration rather than an empty key.

    The stored key is read ONLY here to build the client and is NEVER echoed back
    or logged (the response/log discipline in each handler still holds).

    Args:
        request: FastAPI request (reads app.state.settings; falls back to a fresh
            TrezarrSettings() in test environments without lifespan).
        field_name: TrezarrSettings SecretStr attribute name (e.g. "llm_api_key").
        provided: The api_key from the request body.

    Returns:
        The provided key when the operator typed a new one; otherwise the stored
        secret's plaintext value (empty string if nothing is stored).
    """
    if provided and provided != SENTINEL:
        return provided
    try:
        settings = request.app.state.settings
    except AttributeError:
        from trezarr.config import TrezarrSettings  # noqa: PLC0415

        settings = TrezarrSettings()
    secret = getattr(settings, field_name, None)
    if secret is None:
        return provided
    return secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)


# ── Route handlers ─────────────────────────────────────────────────────────────

@router.post("/test/sonarr")
async def test_sonarr(body: ArrTestParams, request: Request) -> JSONResponse:
    """Validate a Sonarr candidate config by calling system/status.

    Returns {"ok": true, "version": "3.x"} on success, or
    {"ok": false, "error": "PyarrXxx: ..."} on failure.
    The api_key from the request body NEVER appears in the response (D-71).

    Args:
        body: SonarrTestParams (host, port, api_key).
        request: FastAPI request (used to access app.state if needed).

    Returns:
        200 JSON {"ok": bool, "version"?: str, "error"?: str}
    """
    try:
        client = Sonarr(
            host=_normalize_arr_host(body.host),
            api_key=_resolve_api_key(request, "sonarr_api_key", body.api_key),
            port=body.port,
            tls=False,
            api_ver="v3",
        )
        status = client.system.get_status()
        version = status.get("version") if isinstance(status, dict) else None
        return JSONResponse({"ok": True, "version": version})
    except PyarrError as exc:
        # WR-01: use _normalize_arr_host so any embedded credentials are stripped.
        # D-71: str(exc)[:200] is the pyarr exception message — it does NOT contain
        # body.api_key (pyarr exceptions describe the HTTP failure, not the request).
        display_host = _normalize_arr_host(body.host)
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("Sonarr connection test failed at %s:%d — %s", display_host, body.port, error_msg)
        return JSONResponse({"ok": False, "error": error_msg})
    except Exception as exc:  # noqa: BLE001
        display_host = _normalize_arr_host(body.host)
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("Sonarr connection test unexpected error at %s:%d — %s", display_host, body.port, error_msg)
        return JSONResponse({"ok": False, "error": error_msg})


@router.post("/test/radarr")
async def test_radarr(body: ArrTestParams, request: Request) -> JSONResponse:
    """Validate a Radarr candidate config by calling system/status.

    Returns {"ok": true, "version": "3.x"} on success, or
    {"ok": false, "error": "PyarrXxx: ..."} on failure.
    The api_key from the request body NEVER appears in the response (D-71).

    Args:
        body: ArrTestParams (host, port, api_key).
        request: FastAPI request.

    Returns:
        200 JSON {"ok": bool, "version"?: str, "error"?: str}
    """
    try:
        client = Radarr(
            host=_normalize_arr_host(body.host),
            api_key=_resolve_api_key(request, "radarr_api_key", body.api_key),
            port=body.port,
            tls=False,
            api_ver="v3",
        )
        status = client.system.get_status()
        version = status.get("version") if isinstance(status, dict) else None
        return JSONResponse({"ok": True, "version": version})
    except PyarrError as exc:
        display_host = _normalize_arr_host(body.host)
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("Radarr connection test failed at %s:%d — %s", display_host, body.port, error_msg)
        return JSONResponse({"ok": False, "error": error_msg})
    except Exception as exc:  # noqa: BLE001
        display_host = _normalize_arr_host(body.host)
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("Radarr connection test unexpected error at %s:%d — %s", display_host, body.port, error_msg)
        return JSONResponse({"ok": False, "error": error_msg})


@router.post("/test/bazarr")
async def test_bazarr(body: ArrTestParams, request: Request) -> JSONResponse:
    """Validate a Bazarr candidate config using httpx.

    Uses httpx (not pyarr) since pyarr Bazarr client coverage is limited. Calls
    GET /api/system/status with X-Api-Key header.

    The api_key from the request body NEVER appears in the response (D-71).

    Args:
        body: ArrTestParams (host, port, api_key).
        request: FastAPI request (reads app.state.settings for bazarr_enabled check).

    Returns:
        200 JSON {"ok": bool, "error"?: str}
    """
    # Check bazarr_enabled setting from app.state (when available).
    try:
        settings = request.app.state.settings
        if not settings.bazarr_enabled:
            return JSONResponse({"ok": False, "error": "Bazarr not enabled"})
    except AttributeError:
        pass  # No settings on app.state (e.g. test environment without lifespan).

    try:
        url = f"http://{_normalize_arr_host(body.host)}:{body.port}/api/system/status"
        api_key = _resolve_api_key(request, "bazarr_api_key", body.api_key)
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers={"X-Api-Key": api_key})
        if r.status_code == 200:
            return JSONResponse({"ok": True})
        else:
            return JSONResponse({"ok": False, "error": f"HTTP {r.status_code}"})
    except httpx.RequestError as exc:
        display_host = _normalize_arr_host(body.host)
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("Bazarr connection test failed at %s:%d — %s", display_host, body.port, error_msg)
        return JSONResponse({"ok": False, "error": error_msg})
    except Exception as exc:  # noqa: BLE001
        display_host = _normalize_arr_host(body.host)
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("Bazarr connection test unexpected error at %s:%d — %s", display_host, body.port, error_msg)
        return JSONResponse({"ok": False, "error": error_msg})


@router.post("/test/llm")
async def test_llm(body: LLMTestParams, request: Request) -> JSONResponse:
    """Validate an LLM endpoint by sending a minimal chat completion.

    Sends a single-token ping (max_tokens=1) to the configured endpoint/model.
    The api_key NEVER appears in the response (D-71).

    Args:
        body: LLMTestParams (base_url, api_key, model).
        request: FastAPI request.

    Returns:
        200 JSON {"ok": bool, "error"?: str}
    """
    try:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI(
            base_url=body.base_url,
            api_key=_resolve_api_key(request, "llm_api_key", body.api_key),
            max_retries=1,
            timeout=15.0,
        )
        await client.chat.completions.create(
            model=body.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return JSONResponse({"ok": True})
    except Exception as exc:  # noqa: BLE001
        # D-71: str(exc)[:200] is the OpenAI SDK exception message.
        # The SDK exception does NOT embed the api_key value in its message.
        error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("LLM connection test failed — %s", error_msg)
        return JSONResponse({"ok": False, "error": error_msg})
