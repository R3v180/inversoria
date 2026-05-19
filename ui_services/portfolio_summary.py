from __future__ import annotations

from config import PRESUPUESTO_INICIAL
from ui_services.position_display import managed_position_value


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


def compute_strategy_pnl(db, exchange, total_value: float) -> dict | None:
    """PnL since active evaluation checkpoint, if any."""
    try:
        from datetime import datetime

        from ui_services import checkpoint_service as cs
        from ui_services.performance_period import compute_period_performance

        active = cs.get_active_checkpoint(db, exchange)
        if not active:
            return None
        start_dt = datetime.fromtimestamp(float(active.get("created_at") or 0))
        perf = compute_period_performance(
            db,
            float(total_value or 0.0),
            start_dt,
            start_equity=float(active.get("equity_usdt") or 0.0),
        )
        if not perf.get("ok"):
            return None
        return {
            "checkpoint": active,
            "pnl_usd": perf["pnl_usd"],
            "pnl_pct": perf["pnl_pct"],
            "start_equity": perf["start_equity"],
        }
    except Exception:
        return None


def compute_dashboard_breakdown(db, exchange, total_value: float, available_usdt: float) -> dict:
    open_positions = db.get_open_positions()
    portfolio = {}
    try:
        portfolio = collect_visible_portfolio(exchange)
    except Exception:
        portfolio = {}
    managed_positions_value = 0.0
    for symbol, pos in open_positions.items():
        managed_positions_value += managed_position_value(symbol, pos, exchange, portfolio=portfolio)
    other_balances_value = float(total_value or 0) - float(available_usdt or 0) - managed_positions_value
    baseline, baseline_label = resolve_dashboard_baseline(db, exchange)
    pnl = float(total_value or 0) - baseline
    pnl_pct = (pnl / baseline * 100.0) if baseline else 0.0
    strategy = compute_strategy_pnl(db, exchange, total_value)
    return {
        "open_positions": open_positions,
        "managed_positions_value": managed_positions_value,
        "other_balances_value": other_balances_value,
        "baseline": baseline,
        "baseline_label": baseline_label,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "strategy_pnl": strategy,
    }

