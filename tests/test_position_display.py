import unittest
from unittest.mock import MagicMock

from ui_services.position_display import resolve_position_metrics


class PositionDisplayTests(unittest.TestCase):
    def test_uses_exchange_amount_when_larger_than_db(self):
        exchange = MagicMock()
        exchange.get_coin_balance.return_value = 0.94
        exchange.get_ticker.return_value = 10.0
        pos = {"entry_price": 9.55, "amount": 0.008}
        metrics = resolve_position_metrics("LINK/USDT", pos, exchange, db=None, portfolio={})
        self.assertAlmostEqual(metrics["display_amount"], 0.94)
        self.assertAlmostEqual(metrics["current_value"], 9.4, places=2)
        self.assertAlmostEqual(metrics["invested_usd"], 8.977, places=2)
        self.assertTrue(metrics["amount_mismatch"])

    def test_pnl_from_entry(self):
        exchange = MagicMock()
        exchange.get_coin_balance.return_value = 1.0
        exchange.get_ticker.return_value = 110.0
        pos = {"entry_price": 100.0, "amount": 1.0}
        metrics = resolve_position_metrics("BTC/USDT", pos, exchange)
        self.assertAlmostEqual(metrics["u_pnl"], 10.0, places=2)


if __name__ == "__main__":
    unittest.main()
