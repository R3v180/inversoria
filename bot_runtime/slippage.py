"""Dynamic slippage estimates for backtest (Freqtrade liquidity idea)."""

from __future__ import annotations


def dynamic_slippage_pair(volume_ratio: float, config, *, side: str = "buy") -> float:
    base_buy = float(getattr(config, "BUY_SLIPPAGE_LIMIT", 0.005) or 0.005)
    base_sell = float(getattr(config, "SELL_SLIPPAGE_LIMIT", 0.01) or 0.01)
    base = base_buy if side == "buy" else base_sell
    if not bool(getattr(config, "BACKTEST_DYNAMIC_SLIPPAGE_ENABLED", True)):
        return base
    vol = max(0.2, float(volume_ratio or 1.0))
    mult = max(0.6, min(2.5, 1.0 / vol))
    cap = float(getattr(config, "BACKTEST_DYNAMIC_SLIPPAGE_CAP", 0.02) or 0.02)
    return min(cap, base * mult)
