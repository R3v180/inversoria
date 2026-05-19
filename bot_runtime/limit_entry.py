"""Limit-style buy entry with pullback (Passivbot/Jesse-inspired)."""

from __future__ import annotations


def compute_limit_buy_price(reference_price: float, config) -> float:
    pullback_pct = float(getattr(config, "LIMIT_BUY_PULLBACK_PCT", 0.25) or 0.25)
    ref = float(reference_price or 0)
    if ref <= 0:
        return 0.0
    return ref * (1.0 - pullback_pct / 100.0)


def should_skip_buy_until_pullback(reference_price: float, config) -> tuple[bool, float]:
    """If limit buys enabled and price above limit, defer to next cycle."""
    if not bool(getattr(config, "LIMIT_BUY_ENABLED", False)):
        return False, float(reference_price or 0)
    limit_px = compute_limit_buy_price(reference_price, config)
    ref = float(reference_price or 0)
    if ref <= limit_px:
        return False, limit_px
    return True, limit_px
