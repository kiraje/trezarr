"""Tests for TrezarrSettings — YAML + env loading and SecretStr masking (ENG-01)."""


def test_settings_loads_defaults():
    """TrezarrSettings() with no arguments uses defined default values."""
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings()
    assert settings.llm_max_retries == 4
    assert settings.llm_max_concurrency == 4
    assert settings.llm_structured_output_mode == "auto"
    assert settings.llm_request_timeout == 120.0
    assert settings.llm_context_window == 32768


def test_env_override(monkeypatch):
    """TREZARR_LLM_MODEL env var overrides the default model value."""
    from trezarr.config import TrezarrSettings  # deferred import

    monkeypatch.setenv("TREZARR_LLM_MODEL", "my-custom-model")
    settings = TrezarrSettings()
    assert settings.llm_model == "my-custom-model"


def test_yaml_load(tmp_path):
    """TrezarrSettings loads values from a YAML config file."""
    from trezarr.config import TrezarrSettings  # deferred import

    config_file = tmp_path / "config.yaml"
    config_file.write_text("llm_model: yaml-model\nllm_max_retries: 7\n")
    settings = TrezarrSettings(_yaml_file=str(config_file))
    assert settings.llm_model == "yaml-model"
    assert settings.llm_max_retries == 7


def test_api_key_not_logged():
    """The literal API key value must NOT appear in any string representation.

    This tests the SecretStr behaviour: str(), repr(), and model_dump() must all
    mask the key value so it can never leak into logs (T-01-W0-01, D-11).
    """
    from trezarr.config import TrezarrSettings  # deferred import

    secret_key = "super-secret-api-key-12345"
    settings = TrezarrSettings(llm_api_key=secret_key)

    # The secret must not appear in any serialized form
    assert secret_key not in str(settings), "Key leaked in str(settings)"
    assert secret_key not in repr(settings), "Key leaked in repr(settings)"
    assert secret_key not in str(settings.model_dump()), "Key leaked in model_dump()"


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3 RED stubs — *arr connection + path_mappings settings (INTG-01, INTG-03)
#
# All stubs use @pytest.mark.xfail(strict=False) — they are RED scaffolding that
# Plan 03-02 will turn GREEN by adding the new TrezarrSettings fields:
#   sonarr_host, sonarr_port, sonarr_api_key, sonarr_enabled,
#   radarr_host, radarr_port, radarr_api_key, radarr_enabled,
#   path_mappings: list[PathMapping], source_lang_priority: list[str],
#   puid, pgid, umask  (per 03-CONTEXT.md D-22, D-23, D-25, D-29)
# ──────────────────────────────────────────────────────────────────────────────
import pytest


def test_sonarr_host_env_override(monkeypatch):
    """TREZARR_SONARR_HOST env var populates settings.sonarr_host (D-22)."""
    from trezarr.config import TrezarrSettings  # deferred import

    monkeypatch.setenv("TREZARR_SONARR_HOST", "192.168.1.10")
    settings = TrezarrSettings()
    assert settings.sonarr_host == "192.168.1.10"


def test_sonarr_api_key_not_in_repr():
    """sonarr_api_key is SecretStr — secret value never appears in repr/str/model_dump (D-11, D-22)."""
    from trezarr.config import TrezarrSettings  # deferred import

    secret_arr_key = "super-secret-sonarr-key-67890"
    settings = TrezarrSettings(sonarr_api_key=secret_arr_key)

    assert secret_arr_key not in str(settings), "sonarr_api_key leaked in str(settings)"
    assert secret_arr_key not in repr(settings), "sonarr_api_key leaked in repr(settings)"
    assert secret_arr_key not in str(settings.model_dump()), "sonarr_api_key leaked in model_dump()"


def test_path_mappings_yaml_load(tmp_path):
    """path_mappings deserializes from a YAML list-of-objects (D-23).

    Verifies the layered-config (YAML override) path for the Phase-3 path-mapping
    configuration surface. Each item becomes a PathMapping(remote=..., local=...).
    """
    from trezarr.config import TrezarrSettings  # deferred import

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "path_mappings:\n"
        "  - remote: /tv\n"
        "    local: /data/media/tv\n"
        "  - remote: /movies\n"
        "    local: /data/media/movies\n",
        encoding="utf-8",
    )
    settings = TrezarrSettings(_yaml_file=str(config_file))

    assert len(settings.path_mappings) == 2, (
        f"Expected 2 path_mappings from YAML, got {len(settings.path_mappings)}"
    )
    assert settings.path_mappings[0].remote == "/tv"
    assert settings.path_mappings[0].local == "/data/media/tv"
    assert settings.path_mappings[1].remote == "/movies"
    assert settings.path_mappings[1].local == "/data/media/movies"
