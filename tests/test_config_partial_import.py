import unittest

from config_importer import apply_config_changes, diff_config_changes, parse_config_payload, partial_config_example_json, validate_config_payload


class ConfigPartialImportTests(unittest.TestCase):
    def test_partial_payload_validates(self):
        payload = parse_config_payload(partial_config_example_json())
        changes, warnings, blocked, errors = validate_config_payload(payload)
        self.assertFalse(errors)
        self.assertIn("MIN_AUTO_DECISION_SCORE", changes)
        self.assertEqual(len(changes), 3)

    def test_partial_diff_smaller_than_full(self):
        payload = parse_config_payload('{"ROTATION_ENABLED": false}')
        changes, _, _, errors = validate_config_payload(payload)
        self.assertFalse(errors)
        self.assertEqual(len(changes), 1)
        rows = diff_config_changes(changes)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
