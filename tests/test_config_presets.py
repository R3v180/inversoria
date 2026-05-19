import unittest

from config_presets import (
    apply_preset,
    list_presets,
    preview_preset_apply,
    save_current_as_preset,
)


class ConfigPresetsTests(unittest.TestCase):
    def test_builtin_presets_exist(self):
        ids = {p["id"] for p in list_presets()}
        self.assertTrue({"recommended", "conservative", "aggressive"}.issubset(ids))

    def test_preview_recommended(self):
        preview = preview_preset_apply("recommended")
        self.assertIn("changes", preview)
        self.assertFalse(preview.get("errors"))

    def test_save_user_preset(self):
        preset = save_current_as_preset("Test preset unit", "temp")
        self.assertEqual(preset.get("name"), "Test preset unit")
        self.assertFalse(preset.get("builtin"))


if __name__ == "__main__":
    unittest.main()
