from __future__ import annotations

import json


def _invalidate_ui_caches(exchange):
    if hasattr(exchange, "invalidate_ui_cache"):
        exchange.invalidate_ui_cache()
    try:
        from ui_services.page_cache import invalidate_all_snapshots
        invalidate_all_snapshots()
    except Exception:
        pass


def record_manual_buy_position(
    db,
    symbol: str,
    price: float,
    amount: float,
    reason: str,
    provider: str = "Manual",
    extra: dict | None = None,
    decision_id=None,
) -> int:
    positions = db.get_open_positions()
    existing = positions.get(symbol)
    if existing:
        old_amount = float(existing.get("amount") or 0)
        old_entry = float(existing.get("entry_price") or price)
        total_amount = old_amount + amount
        entry = ((old_entry * old_amount) + (price * amount)) / total_amount if total_amount > 0 else price
        highest = max(float(existing.get("highest_price") or price), price)
        entry_time = existing.get("entry_time")
        amount_to_store = total_amount
        existing_extra = {}
        raw_extra = (existing or {}).get("extra_data")
        if raw_extra:
            try:
                existing_extra = json.loads(raw_extra) if isinstance(raw_extra, str) else dict(raw_extra)
            except Exception:
                existing_extra = {}
    else:
        entry = price
        highest = price
        entry_time = None
        amount_to_store = amount
        existing_extra = {}

    extra_payload = {**existing_extra, "provider": provider, "reason": reason, **(extra or {})}
    if decision_id:
        extra_payload["entry_decision_id"] = decision_id
    extra_data = json.dumps(extra_payload, ensure_ascii=False)
    db.add_open_position(symbol, entry, highest, amount_to_store, entry_time=entry_time, extra_data=extra_data)
    trade_id = db.save_trade(symbol, "buy", price, amount, reason, 0.0)
    db.add_log(f"{reason}: {symbol} qty={amount:.10g} @ {price:.6f}")
    return trade_id


def execute_manual_buy(
    db,
    exchange,
    symbol: str,
    amount_usdt: float,
    reason: str,
    price: float | None = None,
    provider: str = "Manual",
    extra: dict | None = None,
    decision_id=None,
) -> dict:
    amount_usdt = float(amount_usdt or 0)
    if amount_usdt <= 0:
        return {"ok": False, "reason": "ZERO_USDT"}

    current_price = price
    if not current_price or current_price <= 0:
        current_price = exchange.get_ticker(symbol)
    if not current_price or current_price <= 0:
        return {"ok": False, "reason": "NO_PRICE"}

    amount_coin = amount_usdt / float(current_price)
    res = exchange.execute_order(symbol, "buy", amount_coin, float(current_price))
    if res.get("status") not in ("closed", "simulated", "open"):
        return {"ok": False, "reason": res.get("reason", res), "order": res}

    try:
        filled = float(res.get("filled") or res.get("amount") or amount_coin)
    except (TypeError, ValueError):
        filled = amount_coin

    _invalidate_ui_caches(exchange)
    trade_id = record_manual_buy_position(
        db,
        symbol,
        float(current_price),
        filled,
        reason,
        provider=provider,
        extra=extra,
        decision_id=decision_id,
    )
    return {
        "ok": True,
        "trade_id": trade_id,
        "filled": filled,
        "price": float(current_price),
        "order": res,
    }


def execute_manual_sell(
    db,
    exchange,
    symbol: str,
    qty: float,
    price: float,
    reason: str,
    in_bot: bool = True,
    max_qty: float | None = None,
) -> dict:
    qty = float(qty or 0)
    if qty <= 0:
        return {"ok": False, "reason": "ZERO_QTY"}

    res = exchange.execute_order(symbol, "sell", qty, price, force_market=True)
    if res.get("status") in ("closed", "simulated", "open"):
        _invalidate_ui_caches(exchange)
    if res.get("status") not in ("closed", "simulated", "open"):
        return {"ok": False, "reason": res.get("reason", res), "order": res}

    exit_price = res.get("average") or res.get("price") or price
    try:
        exit_price = float(exit_price)
    except (TypeError, ValueError):
        exit_price = float(price or 0)

    try:
        sold = float(res.get("filled") or 0)
    except (TypeError, ValueError):
        sold = 0.0
    if sold <= 0:
        sold = float(res.get("amount") or qty)
    if max_qty is not None:
        sold = min(sold, float(max_qty or 0))
    sold = min(sold, qty)

    closed = True
    if in_bot:
        closed = bool(db.close_position(symbol, exit_price, reason, sold_amount=sold))
    if closed:
        db.add_log(f"{reason}: {symbol} qty={sold:.10g} @ {exit_price:.6f}")

    return {
        "ok": closed,
        "reason": None if closed else "CLOSE_POSITION_FAILED",
        "sold": sold,
        "exit_price": exit_price,
        "order": res,
        "status": res.get("status"),
    }
