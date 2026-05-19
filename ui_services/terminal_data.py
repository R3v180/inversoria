from __future__ import annotations

import json

from config import SYMBOLS


def build_terminal_snapshot(db, exchange, symbol: str | None = None):
    saved_watchlist = db.get_system_status("dynamic_watchlist")
    current_symbols = [s.strip() for s in saved_watchlist.split(",") if s.strip()] if saved_watchlist else list(SYMBOLS)

    open_positions = db.get_open_positions()
    default_index = 0
    default_symbol = current_symbols[0] if current_symbols else "BTC/USDT"
    if open_positions:
        max_value = -1.0
        max_symbol = default_symbol
        symbols_for_price = list(open_positions.keys())
        exchange.prefetch_tickers(symbols_for_price)
        for sym, pos in open_positions.items():
            price = exchange.get_ticker(sym) or float(pos.get("entry_price") or 0)
            value = float(pos.get("amount") or 0) * float(price or 0)
            if value > max_value:
                max_value = value
                max_symbol = sym
        if max_symbol not in current_symbols:
            current_symbols.insert(0, max_symbol)
        default_index = current_symbols.index(max_symbol)
        default_symbol = max_symbol

    active_symbol = symbol or default_symbol
    if active_symbol not in current_symbols:
        current_symbols.insert(0, active_symbol)

    ohlcv = exchange.get_historical_data(active_symbol, limit=300)
    try:
        decision = json.loads(db.get_system_status(f"decision_{active_symbol}", "{}") or "{}")
    except Exception:
        decision = {}

    raw_logs = db.get_logs()
    from ui_services.log_display import log_line_matches_noise

    important_logs = [line for line in raw_logs if not log_line_matches_noise(line)][-20:]

    return {
        "current_symbols": current_symbols,
        "default_index": default_index,
        "symbol": active_symbol,
        "ohlcv": ohlcv,
        "decision": decision,
        "important_logs": important_logs,
    }
