import unittest
from unittest.mock import MagicMock

import config
from bot_runtime.protections import evaluate_buy_protections


class ProtectionsTests(unittest.TestCase):
    def test_disabled_passes(self):
        db = MagicMock()
        old = getattr(config, "PROTECTIONS_ENABLED", True)
        try:
            config.PROTECTIONS_ENABLED = False
            result = evaluate_buy_protections(db, "BTC/USDT", config)
            self.assertTrue(result["ok"])
        finally:
            config.PROTECTIONS_ENABLED = old


if __name__ == "__main__":
    unittest.main()
