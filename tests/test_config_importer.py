from config import SENSITIVE_SETTING_KEYS, USER_SETTINGS_FILE, get_setting, save_settings
from simulation_profiles import (
    GLOBAL_SETTING_KEYS,
    ROOT,
    get_active_profile_settings,
    save_active_profile_settings,
)
from pathlib import Path

def test_sensitive_settings_keys():
    assert isinstance(SENSITIVE_SETTING_KEYS, dict)

def test_user_settings_file():
    assert isinstance(USER_SETTINGS_FILE, Path)