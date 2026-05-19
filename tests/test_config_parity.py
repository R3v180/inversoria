import unittest

import config
from config_importer import CONFIG_SCHEMA, SENSITIVE_CONFIG_KEYS


class ConfigParityTests(unittest.TestCase):
    def test_default_settings_in_schema(self):
        missing = []
        for key in config.DEFAULT_SETTINGS:
            if key in config.SENSITIVE_SETTING_KEYS:
                continue
            if key not in CONFIG_SCHEMA:
                missing.append(key)
        self.assertEqual(missing, [], f"CONFIG_SCHEMA missing: {missing}")

    def test_sensitive_not_exportable(self):
        for key in config.SENSITIVE_SETTING_KEYS:
            self.assertIn(key, SENSITIVE_CONFIG_KEYS)


if __name__ == "__main__":
    unittest.main()
