"""Tests for TrezarrSettings — YAML + env loading and SecretStr masking (ENG-01).

All tests are marked xfail(strict=False) until the Plan 03 config implementation
ships.
"""
import os

import pytest


@pytest.mark.xfail(strict=False, reason="TrezarrSettings not yet implemented (Plan 03)")
def test_settings_loads_defaults():
    """TrezarrSettings() with no arguments uses defined default values."""
    from trezarr.config import TrezarrSettings  # deferred import

    settings = TrezarrSettings()
    assert settings.llm_max_retries == 4
    assert settings.llm_max_concurrency == 4
    assert settings.llm_structured_output_mode == "auto"
    assert settings.llm_request_timeout == 120.0
    assert settings.llm_context_window == 32768


@pytest.mark.xfail(strict=False, reason="TrezarrSettings not yet implemented (Plan 03)")
def test_env_override(monkeypatch):
    """TREZARR_LLM_MODEL env var overrides the default model value."""
    from trezarr.config import TrezarrSettings  # deferred import

    monkeypatch.setenv("TREZARR_LLM_MODEL", "my-custom-model")
    settings = TrezarrSettings()
    assert settings.llm_model == "my-custom-model"


@pytest.mark.xfail(strict=False, reason="TrezarrSettings not yet implemented (Plan 03)")
def test_yaml_load(tmp_path):
    """TrezarrSettings loads values from a YAML config file."""
    from trezarr.config import TrezarrSettings  # deferred import

    config_file = tmp_path / "config.yaml"
    config_file.write_text("llm_model: yaml-model\nllm_max_retries: 7\n")
    settings = TrezarrSettings(_yaml_file=str(config_file))
    assert settings.llm_model == "yaml-model"
    assert settings.llm_max_retries == 7


@pytest.mark.xfail(strict=False, reason="TrezarrSettings not yet implemented (Plan 03)")
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
