from __future__ import annotations

from config import PRESUPUESTO_INICIAL


def collect_visible_portfolio(exchange) -> dict:
    portfolio = {}
    if exchange.modo_simulacion:
        for symbol, amount in (exchange.get_virtual_portfolio() or {}).items():
            if float(amount or 0) > 0:
                portfolio[symbol] = float(amount)
        return portfolio

    rows = exchange.get_spot_inventory_rows()
    if rows and rows[0].get("error"):
        raise RuntimeError(rows[0].get("error"))
    for row in rows or []:
        coin = row.get("coin")
        symbol = row.get("symbol")
        amount = float(row.get("free") or 0)
        if amount > 0 and symbol and coin not in ["USDT", "USD"]:
            portfolio[symbol] = amount
    return portfolio


def resolve_dashboard_baseline(db, exchange) -> tuple[float, str]:
    baseline = PRESUPUESTO_INICIAL
    label = "initial"
    if not exchange.modo_simulacion:
        real_start = db.get_system_status("real_start_balance")
        if real_start:
            baseline = float(real_start)
            label = "real_start"
    return baseline, label


def compute_dashboard_breakdown(db, exchange, total_value: float, available_usdt: float) -> dict:
    open_positions = db.get_open_positions()
    managed_positions_value = 0.0
    for symbol, pos in open_positions.items():
        price = exchange.get_ticker(symbol) or pos.get("entry_price") or 0
        managed_positions_value += float(pos.get("amount") or 0) * float(price or 0)
    other_balances_value = float(total_value or 0) - float(available_usdt or 0) - managed_positions_value
    baseline, baseline_label = resolve_dashboard_baseline(db, exchange)
    pnl = float(total_value or 0) - baseline
    pnl_pct = (pnl / baseline * 100.0) if baseline else 0.0
    return {
        "open_positions": open_positions,
        "managed_positions_value": managed_positions_value,
        "other_balances_value": other_balances_value,
        "baseline": baseline,
        "baseline_label": baseline_label,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }

