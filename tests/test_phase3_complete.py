import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import config
from bot_runtime.dca_grid import dca_tranche_usdt, grid_limit_prices
from bot_runtime.hyperopt_lite import run_hyperopt_lite
from bot_runtime.inventory_skew import inventory_skew_multiplier
from bot_runtime.rule_significance import _wilson_lower_bound
from bot_runtime.webhook_processor import normalize_tv_symbol, parse_tradingview_payload


class Phase3CompleteTests(unittest.TestCase):
    def test_normalize_tv_symbol(self):
        self.assertEqual(normalize_tv_symbol("ETHUSDT"), "ETH/USDT")

    def test_webhook_secret(self):
        ok, sym, action, err = parse_tradingview_payload(
            {"passphrase": "x", "ticker": "BTCUSDT", "action": "buy"},
            "x",
        )
        self.assertTrue(ok)
        self.assertEqual(sym, "BTC/USDT")
        self.assertEqual(action, "BUY")

    def test_inventory_skew_reduces_overweight(self):
        cfg = SimpleNamespace(
            INVENTORY_SKEW_ENABLED=True,
            INVENTORY_SKEW_TARGET_SYMBOL_PCT=0.10,
            INVENTORY_SKEW_MAX_BOOST=1.25,
            INVENTORY_SKEW_MIN_REDUCE=0.65,
        )
        exposures = {"symbols": {"BTC/USDT": 80.0}}
        mult = inventory_skew_multiplier("BTC/USDT", exposures, 100.0, cfg)
        self.assertLess(mult, 1.0)

    def test_dca_grid_helpers(self):
        cfg = SimpleNamespace(DCA_GRID_ENABLED=True, DCA_MAX_TRANCHES=3, DCA_TRANCHE_MULTIPLIER=1.5)
        self.assertGreater(dca_tranche_usdt(10.0, 1, cfg), 0)
        prices = grid_limit_prices(100.0, cfg)
        self.assertEqual(len(prices), 3)

    def test_wilson_bound(self):
        self.assertGreater(_wilson_lower_bound(8, 10), 0.4)

    def test_hyperopt_disabled(self):
        result = run_hyperopt_lite(":memory:", config)
        self.assertFalse(result.get("enabled"))


if __name__ == "__main__":
    unittest.main()
