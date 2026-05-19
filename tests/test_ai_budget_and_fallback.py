import os
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from database_manager import DatabaseManager
from decision_engine import DecisionEngine


class LocalAiBudgetTests(unittest.TestCase):
    def test_budget_disabled_skips_limits(self):
        from sentiment_engine import SentimentEngine

        engine = SentimentEngine.__new__(SentimentEngine)
        engine.db = MagicMock()
        with patch("sentiment_engine.config") as cfg:
            cfg.AI_ENABLE_LOCAL_BUDGET = False
            cfg.AI_MAX_REQUESTS_PER_CYCLE = 2
            cfg.AI_MAX_REQUESTS_PER_DAY = 80
            cfg.AI_MAX_OUTPUT_TOKENS = 700
            allowed, reason, *_ = engine._ai_budget_check("p", "s", "test")
        self.assertTrue(allowed)
        self.assertEqual(reason, "")
        engine.db.get_ai_usage_summary.assert_not_called()

    def test_budget_block_does_not_record_usage(self):
        from sentiment_engine import SentimentEngine

        engine = SentimentEngine.__new__(SentimentEngine)
        engine.db = MagicMock()
        engine.db.get_ai_usage_summary.side_effect = [
            {"requests": 5, "estimated_tokens": 0},
            {"requests": 100, "estimated_tokens": 0},
        ]
        with patch("sentiment_engine.config") as cfg:
            cfg.AI_ENABLE_LOCAL_BUDGET = True
            cfg.AI_MAX_REQUESTS_PER_CYCLE = 2
            cfg.AI_MAX_REQUESTS_PER_DAY = 80
            cfg.AI_MAX_EST_TOKENS_PER_DAY = 0
            cfg.AI_MAX_OUTPUT_TOKENS = 700
            cfg.DAEMON_CYCLE_SECONDS = 60
            allowed, reason, *_ = engine._ai_budget_check("p", "s", "test")
        self.assertFalse(allowed)
        self.assertIn("AI_MAX_REQUESTS_PER_CYCLE", reason)
        engine.db.record_ai_usage.assert_not_called()

    def test_usage_summary_for_limits_excludes_budget_rows(self):
        db_path = Path(__file__).resolve().parent / "_tmp_ai_usage_test.db"
        if db_path.exists():
            db_path.unlink()
        try:
            db = DatabaseManager(str(db_path))
            now = time.time()
            db.record_ai_usage("budget", "x", "h", success=False, blocked_reason="blocked")
            db.record_ai_usage("Groq-8B", "x", "h", success=True)
            all_usage = db.get_ai_usage_summary(since_ts=now - 10)
            limited = db.get_ai_usage_summary(since_ts=now - 10, for_limits=True)
            self.assertEqual(all_usage["requests"], 2)
            self.assertEqual(limited["requests"], 1)
        finally:
            del db
            if db_path.exists():
                try:
                    os.remove(db_path)
                except OSError:
                    pass


class RulesFallbackTests(unittest.TestCase):
    def test_should_fallback_for_ai_aggressive(self):
        engine = DecisionEngine.__new__(DecisionEngine)
        with patch("decision_engine.config") as cfg:
            cfg.AI_RULES_ONLY_ON_BUDGET_EXHAUSTED = True
            self.assertTrue(engine._should_rules_fallback_when_ai_unavailable("ai_aggressive"))
            self.assertTrue(engine._should_rules_fallback_when_ai_unavailable("hybrid"))
            self.assertFalse(engine._should_rules_fallback_when_ai_unavailable("rules"))

    def test_rules_fallback_builds_action(self):
        engine = DecisionEngine.__new__(DecisionEngine)
        indicators = {"trend": "BULL", "trend_regime": "TRENDING_UP", "rsi": 55, "adx": 28}
        with patch("decision_engine.config") as cfg:
            cfg.MIN_AUTO_DECISION_SCORE = 0.55
            result = engine._rules_fallback_when_ai_unavailable(
                0.72,
                {"technical": 0.7, "mtf": 0.7, "historical": 0.5, "macro": 0.5, "adaptive": 0.5},
                indicators,
                "TREND_FOLLOWING",
                "RISK_ON",
                "test",
            )
        self.assertEqual(result["action"], "BUY")
        self.assertEqual(result["provider"], "RulesEngine")
        self.assertIn("RULES FALLBACK", result["reasoning"])


if __name__ == "__main__":
    unittest.main()
