import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import config
from bot_runtime.funding import funding_blocks_long
from bot_runtime.limit_entry import should_skip_buy_until_pullback
from bot_runtime.slippage import dynamic_slippage_pair
from trading_logic import TradingLogic


class Phase2RuntimeTests(unittest.TestCase):
    def test_limit_pullback_defers_when_price_above_limit(self):
        cfg = SimpleNamespace(LIMIT_BUY_ENABLED=True, LIMIT_BUY_PULLBACK_PCT=1.0)
        skip, limit_px = should_skip_buy_until_pullback(100.0, cfg)
        self.assertTrue(skip)
        self.assertAlmostEqual(limit_px, 99.0)

    def test_dynamic_slippage_increases_on_low_volume(self):
        cfg = SimpleNamespace(
            BUY_SLIPPAGE_LIMIT=0.01,
            SELL_SLIPPAGE_LIMIT=0.01,
            BACKTEST_DYNAMIC_SLIPPAGE_ENABLED=True,
            BACKTEST_DYNAMIC_SLIPPAGE_CAP=0.05,
        )
        low_vol = dynamic_slippage_pair(0.3, cfg, side="buy")
        high_vol = dynamic_slippage_pair(2.0, cfg, side="buy")
        self.assertGreater(low_vol, high_vol)

    def test_funding_veto_blocks_high_rate(self):
        exchange = MagicMock()
        exchange.exchange.fetch_funding_rate.return_value = {"fundingRate": 0.001}
        cfg = SimpleNamespace(FUNDING_VETO_ENABLED=True, FUNDING_VETO_MAX_LONG_PCT=0.05)
        blocked, reason = funding_blocks_long("BTC/USDT", exchange, cfg)
        self.assertTrue(blocked)
        self.assertIn("FUNDING", reason)

    def test_scaled_tp_first_level(self):
        logic = TradingLogic()
        saved = {
            k: getattr(config, k, None)
            for k in (
                "SCALED_TAKE_PROFIT_ENABLED",
                "SCALED_TAKE_PROFIT_LEVELS",
                "BREAK_EVEN_ENABLED",
                "PARTIAL_TAKE_PROFIT_ENABLED",
                "AGGRESSIVE_TRADING_PROFILE",
                "POSITION_AGE_DECAY_ENABLED",
                "MAX_POSITION_AGE_HOURS",
            )
        }
        try:
            config.SCALED_TAKE_PROFIT_ENABLED = True
            config.SCALED_TAKE_PROFIT_LEVELS = "2.0:0.5"
            config.BREAK_EVEN_ENABLED = False
            config.PARTIAL_TAKE_PROFIT_ENABLED = False
            config.AGGRESSIVE_TRADING_PROFILE = False
            config.POSITION_AGE_DECAY_ENABLED = False
            config.MAX_POSITION_AGE_HOURS = 0
            res = logic.check_sell_conditions(
                "BTC/USDT",
                102.0,
                {"entry_price": 100.0, "highest_price": 102.0, "extra_data": "{}"},
                {"regime": "RANGING", "action": "HOLD"},
            )
        finally:
            for key, value in saved.items():
                if value is None and hasattr(config, key):
                    delattr(config, key)
                elif value is not None:
                    setattr(config, key, value)
        self.assertTrue(res["should_sell"])
        self.assertIn("SCALED TP", res["reason"])


if __name__ == "__main__":
    unittest.main()
