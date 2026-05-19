"""Between-cycle position monitor: price highs + protective sells."""

from __future__ import annotations

import json


def monitor_open_positions(daemon, *, consultive_mode=None):
    import config

    if not bool(getattr(config, "POSITION_MONITOR_ENABLED", True)):
        return
    if not bool(getattr(config, "POSITION_MONITOR_SELLS_ENABLED", True)):
        return _update_highs_only(daemon)

    consultive = consultive_mode if consultive_mode is not None else daemon.is_consultive_mode()
    open_positions = daemon.db.get_open_positions()
    if not open_positions:
        return

    for symbol, pos in list(open_positions.items()):
        try:
            current_price = daemon._safe_float(daemon.exchange.get_ticker(symbol))
            if current_price <= 0:
                continue
            if current_price > daemon._safe_float(pos.get("highest_price"), 0.0):
                daemon.db.update_highest_price(symbol, current_price)
                pos["highest_price"] = current_price

            decision = _decision_from_position(pos)
            sell_res = daemon.logic.check_sell_conditions(symbol, current_price, pos, decision)
            if not sell_res.get("should_sell"):
                continue
            daemon._execute_position_sell(
                symbol,
                pos,
                current_price,
                sell_res,
                decision,
                decision_journal_id=None,
                consultive_mode=consultive,
                provider="PositionMonitor",
            )
        except Exception as exc:
            daemon.log_message(f"[MONITOR] {symbol} failed: {exc}")


def _update_highs_only(daemon):
    open_positions = daemon.db.get_open_positions()
    for symbol, pos in list(open_positions.items()):
        try:
            current_price = daemon._safe_float(daemon.exchange.get_ticker(symbol))
            if current_price > daemon._safe_float(pos.get("highest_price"), 0.0):
                daemon.db.update_highest_price(symbol, current_price)
        except Exception:
            pass


def _decision_from_position(pos):
    extra = {}
    try:
        extra = json.loads(pos.get("extra_data") or "{}")
    except Exception:
        extra = {}
    return {
        "action": "HOLD",
        "regime": extra.get("regime", "RANGING"),
        "best_strategy": extra.get("best_strategy", "TREND_FOLLOWING"),
        "confidence": float(extra.get("confidence") or extra.get("entry_confidence") or 0.5),
        "provider": extra.get("provider", "Monitor"),
    }
