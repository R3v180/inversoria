"""Rule/strategy significance from journal (Jesse-inspired)."""

from __future__ import annotations

import math


def _wilson_lower_bound(wins: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = wins / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denom)


def strategy_significance_adjustment(db, strategy: str, regime: str, config) -> tuple[float, dict]:
    """Return score adjustment in [-max, +max] when sample is statistically weak."""
    if not bool(getattr(config, "RULE_SIGNIFICANCE_ENABLED", True)):
        return 0.0, {}
    min_trades = int(getattr(config, "RULE_SIGNIFICANCE_MIN_TRADES", 12) or 12)
    max_adj = float(getattr(config, "RULE_SIGNIFICANCE_MAX_ADJ", 0.08) or 0.08)
    min_wr = float(getattr(config, "RULE_SIGNIFICANCE_MIN_WIN_RATE", 0.45) or 0.45)

    try:
        journal = db.get_decision_journal(limit=1500)
    except Exception:
        return 0.0, {}

    if journal.empty or "realized_pnl_pct" not in journal.columns:
        return 0.0, {}

    closed = journal[journal["realized_pnl_pct"].notna()].copy()
    if closed.empty:
        return 0.0, {}

    strat = str(strategy or "")
    reg = str(regime or "")
    sample = closed
    if strat and "strategy" in closed.columns:
        sample = sample[sample["strategy"].astype(str) == strat]
    if reg and "regime" in closed.columns:
        sample = sample[sample["regime"].astype(str) == reg]
    n = len(sample)
    if n < min_trades:
        return 0.0, {"significant": False, "trades": n, "reason": "INSUFFICIENT_SAMPLE"}

    pnl = sample["realized_pnl_pct"].astype(float)
    wins = int((pnl > 0).sum())
    wr = wins / n
    lb = _wilson_lower_bound(wins, n)
    evidence = {
        "significant": lb >= min_wr,
        "trades": n,
        "win_rate": round(wr, 4),
        "wilson_lb": round(lb, 4),
        "strategy": strat,
        "regime": reg,
    }
    if lb < min_wr:
        penalty = max_adj * (min_wr - lb) / max(min_wr, 1e-6)
        return -min(max_adj, penalty), evidence
    if wr >= min_wr + 0.08:
        boost = max_adj * 0.5 * (wr - min_wr)
        return min(max_adj * 0.5, boost), evidence
    return 0.0, evidence
