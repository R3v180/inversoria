import unittest

from decision_engine import DecisionEngine, _clamp, _safe_float


class TrendScoreTests(unittest.TestCase):
    def test_trend_score_regimes(self):
        engine = DecisionEngine.__new__(DecisionEngine)
        engine._adaptive_cache = {"enabled": False}
        engine._adaptive_cache_ts = 0
        engine.ADAPTIVE_CACHE_TTL = 300
        indicators_bear = {"trend": "BEAR", "trend_regime": "BEAR", "rsi": 50, "adx": 20}
        score_bear, _ = engine.build_decision_score(
            indicators_bear, "NEUTRAL", 0.5, {"found": False}, symbol="BTC/USDT"
        )
        indicators_bull = {"trend": "BULL", "trend_regime": "TRENDING_UP", "rsi": 50, "adx": 25}
        score_bull, _ = engine.build_decision_score(
            indicators_bull, "RISK_ON", 0.8, {"found": False}, symbol="BTC/USDT"
        )
        self.assertGreater(score_bull, score_bear)


class AdaptiveCapTests(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(_clamp(1.5), 1.0)
        self.assertEqual(_safe_float("bad", 0.1), 0.1)


if __name__ == "__main__":
    unittest.main()
