"""Pairlist liquidity filters (inspired by Freqtrade dynamic pairlists)."""

from __future__ import annotations


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def passes_liquidity_filter(exchange, symbol: str, config) -> tuple[bool, str]:
    """Check spread and 24h quote volume when exchange exposes them."""
    if not bool(getattr(config, "PAIRLIST_LIQUIDITY_FILTER_ENABLED", True)):
        return True, ""

    max_spread = _safe_float(getattr(config, "PAIRLIST_MAX_SPREAD_PCT", 0.35), 0.35)
    min_volume = _safe_float(getattr(config, "PAIRLIST_MIN_QUOTE_VOLUME_USDT", 50000.0), 50000.0)

    try:
        ticker = exchange.exchange.fetch_ticker(symbol) if getattr(exchange, "exchange", None) else {}
    except Exception as exc:
        return True, f"liquidity_check_skipped:{exc}"

    bid = _safe_float(ticker.get("bid"))
    ask = _safe_float(ticker.get("ask"))
    if bid > 0 and ask > 0:
        spread_pct = ((ask - bid) / bid) * 100.0
        if spread_pct > max_spread:
            return False, f"SPREAD_{spread_pct:.2f}pct"

    quote_vol = _safe_float(ticker.get("quoteVolume") or ticker.get("info", {}).get("quote_volume"))
    if quote_vol > 0 and quote_vol < min_volume:
        return False, f"LOW_VOLUME_{quote_vol:.0f}"

    return True, ""
