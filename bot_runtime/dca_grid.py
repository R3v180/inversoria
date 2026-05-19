"""Isolated DCA / grid helpers (optional mode, does not affect core bot)."""

from __future__ import annotations


def dca_tranche_usdt(base_usdt: float, tranche_index: int, config) -> float:
    if not bool(getattr(config, "DCA_GRID_ENABLED", False)):
        return 0.0
    mult = float(getattr(config, "DCA_TRANCHE_MULTIPLIER", 1.0) or 1.0)
    max_tranches = int(getattr(config, "DCA_MAX_TRANCHES", 3) or 3)
    if tranche_index >= max_tranches:
        return 0.0
    return max(0.0, float(base_usdt) * (mult ** tranche_index))


def grid_limit_prices(reference_price: float, config) -> list[float]:
    if not bool(getattr(config, "DCA_GRID_ENABLED", False)):
        return []
    ref = float(reference_price or 0)
    if ref <= 0:
        return []
    spacing = float(getattr(config, "GRID_SPACING_PCT", 0.5) or 0.5) / 100.0
    levels = int(getattr(config, "GRID_LEVELS", 3) or 3)
    return [ref * (1.0 - spacing * (i + 1)) for i in range(levels)]
