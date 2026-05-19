"""Tests for journal vs backtest compare and closure sync."""

import os
import tempfile
import time
import unittest

from database_manager import DatabaseManager
from ui_services.journal_backtest_compare import build_journal_vs_backtest_rows, ensure_journal_closures


class JournalBacktestCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = DatabaseManager(db_path=self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_close_position_links_journal_for_manual_path(self):
        self.db.add_open_position("BTC/USDT", 100.0, 100.0, 1.0, entry_time=time.time())
        ok = self.db.close_position("BTC/USDT", 110.0, "MANUAL TEST", sold_amount=1.0, sync_journal=True)
        self.assertTrue(ok)
        closed = self.db.get_closed_decision_journal(limit=10)
        self.assertEqual(len(closed), 1)
        self.assertAlmostEqual(float(closed.iloc[0]["realized_pnl_pct"]), 10.0, places=2)

    def test_backfill_from_trades_and_compare_rows(self):
        ts = time.time()
        with self.db._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_conditions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timeframe TEXT,
                    win_rate REAL,
                    profit_factor REAL,
                    total_trades INTEGER,
                    updated_at REAL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO trades (symbol, side, price, amount, reason, pnl_pct, timestamp)
                VALUES (?, 'sell', ?, ?, ?, ?, ?)
                """,
                ("ETH/USDT", 200.0, 0.5, "OLD SELL", 5.0, ts),
            )
            conn.execute(
                """
                INSERT INTO trades (symbol, side, price, amount, reason, pnl_pct, timestamp)
                VALUES (?, 'sell', ?, ?, ?, ?, ?)
                """,
                ("ETH/USDT", 190.0, 0.5, "OLD SELL 2", -2.0, ts + 400),
            )
            conn.execute(
                """
                INSERT INTO backtest_conditions
                (symbol, timeframe, win_rate, profit_factor, total_trades, updated_at)
                VALUES (?, '4h', ?, ?, ?, ?)
                """,
                ("ETH/USDT", 0.55, 1.2, 20, ts),
            )
            conn.commit()

        inserted = ensure_journal_closures(self.db)
        self.assertEqual(inserted, 2)
        inserted_again = ensure_journal_closures(self.db)
        self.assertEqual(inserted_again, 0)

        rows = build_journal_vs_backtest_rows(self.db)
        self.assertGreaterEqual(len(rows), 1)
        eth = next(r for r in rows if r["symbol"] == "ETH/USDT")
        self.assertEqual(eth["live_trades"], 2)
        self.assertIsNotNone(eth["backtest_win_rate"])


if __name__ == "__main__":
    unittest.main()
