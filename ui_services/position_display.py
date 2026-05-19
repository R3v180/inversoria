"""Metrics for open-position cards (exchange-aligned amounts and cost basis)."""

from __future__ import annotations


def _safe_float(value, default=0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_position_metrics(symbol: str, pos: dict, exchange, db=None, portfolio: dict | None = None) -> dict:
    """
    Build display fields for dashboard position cards.

    Uses the greater of DB-tracked amount and exchange balance so UI matches
    wallet reality when reconcile/DB drift occurs.
    """
    portfolio = portfolio or {}
    entry_db = _safe_float(pos.get("entry_price"))
    tracked_amount = _safe_float(pos.get("amount"))
    exchange_amount = _safe_float(portfolio.get(symbol))
    if exchange_amount <= 0 and exchange is not None:
        try:
            exchange_amount = _safe_float(exchange.get_coin_balance(symbol))
        except Exception:
            exchange_amount = 0.0

    display_amount = tracked_amount
    if exchange_amount > tracked_amount + 1e-10:
        display_amount = exchange_amount
    elif exchange_amount > 0 and tracked_amount <= 0:
        display_amount = exchange_amount

    entry_cost = entry_db
    cost_source = "open_position"
    if db is not None and hasattr(db, "get_cost_basis"):
        try:
            basis = db.get_cost_basis(symbol, {symbol: pos}) or {}
            bp = _safe_float(basis.get("entry_price"))
            if bp > 0:
                entry_cost = bp
                cost_source = str(basis.get("source") or cost_source)
        except Exception:
            pass

    current_price = entry_cost
    if exchange is not None:
        try:
            current_price = _safe_float(exchange.get_ticker(symbol), entry_cost)
        except Exception:
            current_price = entry_cost
    if current_price <= 0:
        current_price = entry_cost

    invested_usd = entry_cost * display_amount if entry_cost > 0 and display_amount > 0 else 0.0
    current_value = display_amount * current_price if display_amount > 0 and current_price > 0 else 0.0
    if entry_cost > 0 and current_price > 0:
        u_pnl = ((current_price - entry_cost) / entry_cost) * 100.0
    else:
        u_pnl = 0.0

    amount_mismatch = exchange_amount > tracked_amount * 1.02 and (exchange_amount - tracked_amount) > 1e-8

    return {
        "symbol": symbol,
        "pos": pos,
        "tracked_amount": tracked_amount,
        "exchange_amount": exchange_amount,
        "display_amount": display_amount,
        "entry_price": entry_cost,
        "cost_source": cost_source,
        "current_price": current_price,
        "invested_usd": invested_usd,
        "current_value": current_value,
        "u_pnl": u_pnl,
        "amount_mismatch": amount_mismatch,
    }


def managed_position_value(symbol: str, pos: dict, exchange, portfolio: dict | None = None) -> float:
    metrics = resolve_position_metrics(symbol, pos, exchange, db=None, portfolio=portfolio)
    return _safe_float(metrics.get("current_value"))
