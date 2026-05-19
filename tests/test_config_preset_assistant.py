import unittest

from ui_services.config_preset_assistant import suggest_preset_id


class TestConfigPresetAssistant(unittest.TestCase):
    def test_simulation_defaults_recommended(self):
        self.assertEqual(
            suggest_preset_id(
                real_mode=False,
                risk_tolerance="high",
                activity_level="high",
                account_size="large",
            ),
            "recommended",
        )

    def test_real_low_risk_conservative(self):
        self.assertEqual(
            suggest_preset_id(
                real_mode=True,
                risk_tolerance="low",
                activity_level="medium",
                account_size="medium",
            ),
            "conservative",
        )

    def test_small_account_conservative(self):
        self.assertEqual(
            suggest_preset_id(
                real_mode=True,
                risk_tolerance="medium",
                activity_level="medium",
                account_size="small",
            ),
            "conservative",
        )

    def test_high_activity_high_risk_aggressive(self):
        self.assertEqual(
            suggest_preset_id(
                real_mode=True,
                risk_tolerance="high",
                activity_level="high",
                account_size="large",
            ),
            "aggressive",
        )

    def test_real_medium_balanced_recommended(self):
        self.assertEqual(
            suggest_preset_id(
                real_mode=True,
                risk_tolerance="medium",
                activity_level="medium",
                account_size="medium",
            ),
            "recommended",
        )


if __name__ == "__main__":
    unittest.main()
