"""Freqtrade-style trading protections (pause buys per symbol or globally)."""

from __future__ import annotations

import time


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def evaluate_buy_protections(db, symbol: str, config) -> dict:
    """Return {ok: bool, reasons: list[str]}. Does not block sells."""
    if not bool(getattr(config, "PROTECTIONS_ENABLED", True)):
        return {"ok": True, "reasons": []}

    reasons = []
    sym = str(symbol or "").upper()

    stop_guard = int(getattr(config, "PROTECTION_STOPLOSS_GUARD_COUNT", 2) or 2)
    stop_window_h = float(getattr(config, "PROTECTION_STOPLOSS_LOOKBACK_HOURS", 24) or 24)
    if stop_guard > 0 and hasattr(db, "count_recent_exit_reasons"):
        try:
            stops = db.count_recent_exit_reasons(
                sym,
                reason_substrings=("STOP LOSS", "STOP_LOSS"),
                hours=stop_window_h,
            )
            if stops >= stop_guard:
                reasons.append(f"STOPLOSS_GUARD:{stops}/{stop_guard}in{stop_window_h:.0f}h")
        except Exception:
            pass

    low_profit_min = int(getattr(config, "PROTECTION_LOW_PROFIT_MIN_TRADES", 8) or 8)
    low_profit_exp = _safe_float(getattr(config, "PROTECTION_LOW_PROFIT_MAX_EXPECTANCY_PCT", -0.15), -0.15)
    if low_profit_min > 0 and hasattr(db, "get_symbol_journal_expectancy"):
        try:
            stats = db.get_symbol_journal_expectancy(sym, limit=200)
            trades = int(stats.get("trades") or 0)
            exp = _safe_float(stats.get("expectancy_pct"), 0.0)
            if trades >= low_profit_min and exp <= low_profit_exp:
                reasons.append(f"LOW_PROFIT_PAIR:trades={trades},exp={exp:.2f}%")
        except Exception:
            pass

    global_until = _safe_float(getattr(config, "PROTECTION_GLOBAL_PAUSE_UNTIL", 0), 0.0)
    if not global_until and hasattr(db, "get_system_status"):
        global_until = _safe_float(db.get_system_status("protection_global_pause_until", "0"), 0.0)
    if global_until > time.time():
        reasons.append("GLOBAL_PROTECTION_PAUSE")

    return {"ok": len(reasons) == 0, "reasons": reasons}
