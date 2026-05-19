"""Funding rate context (Hummingbot-inspired veto, not arbitrage)."""

from __future__ import annotations


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def fetch_funding_rate_pct(exchange, symbol: str) -> float | None:
    """Return funding rate in percent if CCXT exposes it."""
    try:
        ex = getattr(exchange, "exchange", None) or getattr(exchange, "public_exchange", None)
        if ex is None or not hasattr(ex, "fetch_funding_rate"):
            return None
        data = ex.fetch_funding_rate(symbol)
        rate = _safe_float((data or {}).get("fundingRate") or (data or {}).get("funding_rate"))
        return rate * 100.0 if abs(rate) < 1 else rate
    except Exception:
        return None


def funding_blocks_long(symbol: str, exchange, config) -> tuple[bool, str]:
    if not bool(getattr(config, "FUNDING_VETO_ENABLED", False)):
        return False, ""
    rate = fetch_funding_rate_pct(exchange, symbol)
    if rate is None:
        return False, ""
    max_long = _safe_float(getattr(config, "FUNDING_VETO_MAX_LONG_PCT", 0.08), 0.08)
    if rate > max_long:
        return True, f"FUNDING_HIGH_{rate:.3f}pct"
    return False, ""
