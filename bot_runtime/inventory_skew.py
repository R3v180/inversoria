"""Inventory skew sizing (Hummingbot-style exposure balancing)."""

from __future__ import annotations


def inventory_skew_multiplier(symbol: str, exposures: dict, total_value: float, config) -> float:
    if not bool(getattr(config, "INVENTORY_SKEW_ENABLED", False)):
        return 1.0
    total_value = float(total_value or 0)
    if total_value <= 0:
        return 1.0
    sym = str(symbol or "").upper()
    symbol_value = float((exposures.get("symbols") or {}).get(sym, 0.0))
    symbol_pct = symbol_value / total_value
    target = float(getattr(config, "INVENTORY_SKEW_TARGET_SYMBOL_PCT", 0.12) or 0.12)
    max_mult = float(getattr(config, "INVENTORY_SKEW_MAX_BOOST", 1.25) or 1.25)
    min_mult = float(getattr(config, "INVENTORY_SKEW_MIN_REDUCE", 0.65) or 0.65)
    if symbol_pct >= target * 1.5:
        return max(min_mult, 1.0 - (symbol_pct - target))
    if symbol_pct <= target * 0.5:
        return min(max_mult, 1.0 + (target - symbol_pct))
    return 1.0
