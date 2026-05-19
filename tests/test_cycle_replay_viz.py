import unittest

from ui_services.cycle_replay_viz import _open_positions_count, _scanned_count


class CycleReplayVizTests(unittest.TestCase):
    def test_open_positions_list(self):
        self.assertEqual(_open_positions_count({"open_positions": ["LINK/USDT", "SUI/USDT"]}), 2)

    def test_open_positions_int(self):
        self.assertEqual(_open_positions_count({"open_positions": 3}), 3)

    def test_scanned_from_actions(self):
        self.assertEqual(_scanned_count({"actions": {"BUY": 2, "HOLD": 5, "SELL": 0}}), 7)

    def test_scanned_from_field(self):
        self.assertEqual(_scanned_count({"scanned": 14}), 14)


if __name__ == "__main__":
    unittest.main()
