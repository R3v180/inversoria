"""Tests for strategy checkpoints and period performance with fixed start equity."""

import os
import tempfile
import time
import unittest

from database_manager import DatabaseManager
from ui_services import checkpoint_service as cs
from ui_services.performance_period import compute_period_performance


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = DatabaseManager(db_path=self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    class _FakeExchange:
        modo_simulacion = True

        def get_balance(self):
            return 120.0

    def test_create_and_list_by_universe(self):
        ex = self._FakeExchange()
        row = cs.create_checkpoint(
            self.db,
            ex,
            event_type="manual",
            label="Test CP",
        )
        self.assertTrue(row.get("id"))
        listed = cs.list_checkpoints(self.db, ex)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["label"], "Test CP")

    def test_active_view_per_universe(self):
        ex = self._FakeExchange()
        row = cs.create_checkpoint(self.db, ex, event_type="manual", label="A")
        cs.set_active_view(self.db, ex, row["id"])
        active = cs.get_active_checkpoint(self.db, ex)
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], row["id"])
        cs.clear_active_view(self.db, ex)
        self.assertIsNone(cs.get_active_checkpoint(self.db, ex))

    def test_compute_period_with_fixed_start_equity(self):
        now = time.time()
        self.db.log_equity(100.0)
        time.sleep(0.01)
        start_dt = __import__("datetime").datetime.fromtimestamp(now)
        perf = compute_period_performance(
            self.db,
            110.0,
            start_dt,
            start_equity=100.0,
        )
        self.assertTrue(perf.get("ok"))
        self.assertAlmostEqual(perf["start_equity"], 100.0)
        self.assertAlmostEqual(perf["pnl_usd"], 10.0)
        self.assertAlmostEqual(perf["pnl_pct"], 10.0)
        self.assertTrue(perf.get("fixed_start_equity"))

    def test_normalize_manual_label_requires_name(self):
        with self.assertRaises(ValueError):
            cs.normalize_manual_label("   ")

    def test_create_manual_checkpoint_activates_view(self):
        ex = self._FakeExchange()
        row = cs.create_manual_checkpoint(self.db, ex, label="  Mi marca  ", activate_view=True)
        self.assertEqual(row["label"], "Mi marca")
        active = cs.get_active_checkpoint(self.db, ex)
        self.assertEqual(active["id"], row["id"])

    def test_create_manual_checkpoint_without_activate(self):
        ex = self._FakeExchange()
        row = cs.create_manual_checkpoint(self.db, ex, label="Solo guardar", activate_view=False)
        self.assertIsNone(cs.get_active_checkpoint(self.db, ex))
        listed = cs.list_checkpoints(self.db, ex)
        self.assertEqual(listed[0]["label"], "Solo guardar")

    def test_import_threshold(self):
        small = {f"KEY_{i}": i for i in range(3)}
        self.assertFalse(cs.should_offer_import_checkpoint(small))
        large = {f"KEY_{i}": i for i in range(10)}
        self.assertTrue(cs.should_offer_import_checkpoint(large))
        risk = {"RISK_PER_TRADE": 0.01}
        self.assertTrue(cs.should_offer_import_checkpoint(risk))


if __name__ == "__main__":
    unittest.main()
