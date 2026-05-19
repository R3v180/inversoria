import sys
from simulation_profiles import (
    get_active_profile_settings,
    save_active_profile_settings,
)
from config import get_setting
from pathlib import Path
from unittest.mock import patch
import config, simulation_profiles

sys.path.append(str(Path(__file__).resolve().parents[1]))

def test_get_active_profile_settings():
    result = get_active_profile_settings()
    assert isinstance(result, dict)

def test_sensitive_key_reads_from_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret123")
    monkeypatch.setattr(
        config,
        "SENSITIVE_SETTING_KEYS",
        {"API_KEY"}
    )

    result = get_setting("API_KEY", "default")
    assert result == "secret123"

def test_returns_default_when_cast_fails(monkeypatch):
    monkeypatch.setenv("PORT", "abc")
    result = get_setting("PORT", 8000, int)
    assert result == 8000

def test_bool_cast_true(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    result = get_setting("DEBUG", False, bool)
    assert result is True

def test_bool_cast_false(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setattr(config, "SENSITIVE_SETTING_KEYS", {"DEBUG"})
    result = get_setting("DEBUG", True, bool)
    assert result is False

def test_int_cast(monkeypatch):
    monkeypatch.setenv("PORT", "5000")
    result = get_setting("PORT", 8000, int)
    assert result == 5000
    assert isinstance(result, int)

def test_returns_default_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    result = get_setting("MISSING_KEY", "fallback")
    assert result == "fallback"


def test_json_load_failure():
    with patch("json.load", side_effect=Exception):
        result = get_setting("KEY", "default")
    assert result == "default"

def test_key_in_global(monkeypatch):
    monkeypatch.setattr(
        config,
        "GLOBAL_SETTING_KEYS",
        {"GLOBAL"}
    )
    result = get_setting("GLOBAL", "default")
    assert result == "default"

def fake_error():
    raise Exception("boom")


def test_profile_settings_exception(monkeypatch):
    monkeypatch.setattr(
        config,
        "get_active_profile_settings",
        fake_error
    )
    result = config.get_setting("TEST_KEY", "default")

    assert result == "default"