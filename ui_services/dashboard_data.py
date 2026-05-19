"""Preload dashboard data in one pass (fewer exchange round-trips)."""

from __future__ import annotations

import json
import sqlite3

from config import SYMBOLS, get_effective_max_positions
from ui_services.portfolio_summary import collect_visible_portfolio, compute_dashboard_breakdown


def build_dashboard_snapshot(db, exchange, chart_symbol: str | None = None):
    available_usdt = float(exchange.get_usdt_balance() or 0)
    total_value = float(exchange.get_balance() or 0)

    saved_watchlist = db.get_system_status("dynamic_watchlist")
    current_symbols = [s.strip() for s in saved_watchlist.split(",") if s.strip()] if saved_watchlist else list(SYMBOLS)

    portfolio = {}
    try:
        portfolio = collect_visible_portfolio(exchange)
    except Exception:
        portfolio = {}

    breakdown = compute_dashboard_breakdown(db, exchange, total_value, available_usdt)
    open_positions = breakdown["open_positions"]

    chart_symbol = chart_symbol or _default_chart_symbol(exchange, current_symbols, open_positions)
    if chart_symbol not in current_symbols:
        current_symbols = [chart_symbol, *current_symbols]

    symbols_to_price = list(
        dict.fromkeys(
            list(open_positions.keys())
            + list(portfolio.keys())
            + current_symbols[:12]
            + [chart_symbol]
        )
    )
    exchange.prefetch_tickers(symbols_to_price)

    position_rows = []
    for sym, pos in open_positions.items():
        entry = float(pos.get("entry_price") or 0)
        current_price = float(exchange.get_ticker(sym) or entry or 0)
        amount = float(pos.get("amount") or 0)
        u_pnl = ((current_price - entry) / entry) * 100 if entry else 0.0
        position_rows.append(
            {
                "symbol": sym,
                "pos": pos,
                "current_price": current_price,
                "u_pnl": u_pnl,
                "current_value": amount * current_price,
            }
        )

    pie_data = [{"Activo": "CASH", "Valor": available_usdt}]
    for sym, amt in portfolio.items():
        px = exchange.get_ticker(sym)
        if px:
            pie_data.append({"Activo": sym, "Valor": float(amt) * float(px)})

    radar_data = []
    for sym in current_symbols[:8]:
        stats = exchange.get_market_stats(sym)
        raw = stats.get("change_24h")
        try:
            change = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            change = 0.0
        radar_data.append({"Moneda": sym, "Cambio": change})
    radar_data.sort(key=lambda x: x["Cambio"], reverse=True)

    diag_raw = db.get_system_status("daemon_diagnostics", "{}")
    try:
        diag_top = json.loads(diag_raw or "{}")
    except Exception:
        diag_top = {}

    try:
        last_decision = json.loads(db.get_system_status("last_ia_decision", "{}") or "{}")
    except Exception:
        last_decision = {}

    equity_df = db.get_equity_history(limit=500)
    ohlcv = exchange.get_historical_data(chart_symbol, limit=150)

    backtest_runs = []
    try:
        with sqlite3.connect(db.db_path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            backtest_runs = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM backtest_runs ORDER BY run_timestamp DESC LIMIT 5"
                ).fetchall()
            ]
    except Exception:
        backtest_runs = []

    macro = {}
    try:
        macro = json.loads(db.get_system_status("macro_context", "{}") or "{}")
    except Exception:
        macro = {}

    try:
        macro_db = db.get_all_macro_data()
    except Exception:
        macro_db = {}

    logs = db.get_logs()
    important_logs = [line for line in logs if "Escaneo" not in line and "Ciclo" not in line][-15:]

    return {
        "available_usdt": available_usdt,
        "total_value": total_value,
        "portfolio": portfolio,
        "breakdown": breakdown,
        "open_positions": open_positions,
        "position_rows": position_rows,
        "current_symbols": current_symbols,
        "chart_symbol": chart_symbol,
        "ohlcv": ohlcv,
        "pie_data": pie_data,
        "radar_data": radar_data,
        "diag_top": diag_top,
        "diag_raw": diag_raw,
        "last_decision": last_decision,
        "equity_df": equity_df,
        "backtest_runs": backtest_runs,
        "macro": macro,
        "macro_db": macro_db,
        "important_logs": important_logs,
        "dynamic_max": get_effective_max_positions(total_value),
        "portfolio_error": None,
    }


def _default_chart_symbol(exchange, current_symbols, open_positions):
    default_sym = current_symbols[0] if current_symbols else "BTC/USDT"
    if not open_positions:
        return default_sym
    max_v = -1.0
    for sym, pos in open_positions.items():
        price = exchange.get_ticker(sym) or float(pos.get("entry_price") or 0)
        val = float(pos.get("amount") or 0) * float(price or 0)
        if val > max_v:
            max_v = val
            default_sym = sym
    return default_sym
