import json
import os
import tempfile
import unittest
from unittest.mock import patch

from config import DEFAULT_SETTINGS, USER_SETTINGS_FILE
from config_presets import (
    PRESET_LOCKED_KEYS,
    apply_preset,
    list_presets,
    preview_preset_apply,
    reset_settings_to_recommended,
    save_current_as_preset,
    strip_preset_locked_keys,
)


class ConfigPresetsTests(unittest.TestCase):
    def test_builtin_presets_exist(self):
        ids = {p["id"] for p in list_presets()}
        self.assertTrue({"recommended", "conservative", "aggressive"}.issubset(ids))

    def test_builtin_presets_exclude_locked_keys(self):
        for preset in list_presets():
            if not preset.get("builtin"):
                continue
            keys = {str(k).upper() for k in (preset.get("settings") or {})}
            self.assertFalse(keys & PRESET_LOCKED_KEYS, preset["id"])

    def test_preview_conservative_keeps_real_mode(self):
        with patch("config_importer.get_setting") as mock_get:
            mock_get.side_effect = lambda key, default, *args, **kwargs: (
                False if key == "MODO_SIMULACION" else default
            )
            preview = preview_preset_apply("conservative")
        diff_keys = {row.get("Campo") or row.get("Field") for row in (preview.get("diff") or [])}
        for alt in diff_keys:
            if alt:
                self.assertNotIn("MODO_SIMULACION", str(alt).upper())

    def test_strip_locked_keys(self):
        raw = {
            "MODO_SIMULACION": False,
            "RISK_PER_TRADE": 0.01,
            "TRADING_EXECUTION_MODE": "consultive",
        }
        stripped = strip_preset_locked_keys(raw)
        self.assertNotIn("MODO_SIMULACION", stripped)
        self.assertEqual(stripped["RISK_PER_TRADE"], 0.01)

    def test_reset_applies_recommended_preserves_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "user_settings.json")
            with patch("config_presets.USER_SETTINGS_FILE", settings_path), patch(
                "config.USER_SETTINGS_FILE", settings_path
            ), patch("config_importer.USER_SETTINGS_FILE", settings_path), patch(
                "config_presets.get_setting"
            ) as mock_get, patch(
                "config_presets.USER_SETTINGS_FILE", settings_path
            ):
                mock_get.side_effect = lambda key, default, *a, **k: (
                    False
                    if key == "MODO_SIMULACION"
                    else ("custom" if key == "SIMULATION_PROFILE_ID" else default)
                )
                result = reset_settings_to_recommended()
            self.assertFalse(result["MODO_SIMULACION"])
            self.assertEqual(result["SIMULATION_PROFILE_ID"], "custom")
            self.assertEqual(result["DECISION_MODE"], "hybrid")
            self.assertEqual(result["MAX_OPEN_POSITIONS"], 3)
            with open(settings_path, encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertFalse(on_disk["MODO_SIMULACION"])
            self.assertEqual(on_disk["TRADING_EXECUTION_MODE"], "auto")

    def test_save_user_preset_strips_mode(self):
        with patch("config_presets.current_safe_config_dict") as mock_cfg:
            mock_cfg.return_value = {
                "MODO_SIMULACION": False,
                "DECISION_MODE": "hybrid",
            }
            with patch("config_presets._load_user_store", return_value={"presets": []}), patch(
                "config_presets._save_user_store"
            ):
                preset = save_current_as_preset("Test preset unit", "temp")
        self.assertNotIn("MODO_SIMULACION", preset.get("settings") or {})


if __name__ == "__main__":
    unittest.main()
