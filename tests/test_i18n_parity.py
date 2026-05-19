import unittest

from config import SENSITIVE_SETTING_KEYS
from config_importer import CONFIG_SCHEMA
from i18n import TRANSLATIONS, _


class I18nParityTests(unittest.TestCase):
    def test_all_translations_have_es_and_en(self):
        incomplete = []
        for key, entry in TRANSLATIONS.items():
            if not isinstance(entry, dict):
                incomplete.append(key)
                continue
            if not str(entry.get("es", "")).strip() or not str(entry.get("en", "")).strip():
                incomplete.append(key)
        self.assertFalse(incomplete, f"Incomplete: {incomplete[:15]}")

    def test_config_schema_has_cfg_key_labels(self):
        missing = []
        for key in CONFIG_SCHEMA:
            i18n_key = f"CFG_KEY_{key}"
            entry = TRANSLATIONS.get(i18n_key, {})
            if not entry.get("es") or not entry.get("en"):
                missing.append(i18n_key)
        self.assertFalse(missing, f"Missing CFG_KEY: {missing[:10]}")

    def test_cfg_key_not_equal_to_raw_key_in_spanish(self):
        """Labels should not fall back to untranslated key name."""
        sample = "RISK_PER_TRADE"
        label_es = _("CFG_KEY_RISK_PER_TRADE", lang="es")
        self.assertNotEqual(label_es, sample)
        self.assertNotEqual(label_es, f"CFG_KEY_{sample}")

    def test_sensitive_keys_have_labels(self):
        for key in SENSITIVE_SETTING_KEYS:
            if key not in CONFIG_SCHEMA:
                continue
            entry = TRANSLATIONS.get(f"CFG_KEY_{key}", {})
            self.assertTrue(entry.get("es") and entry.get("en"), key)


if __name__ == "__main__":
    unittest.main()
