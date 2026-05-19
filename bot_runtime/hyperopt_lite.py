"""Lightweight risk-parameter search from stored backtest rows."""

from __future__ import annotations

import sqlite3


def run_hyperopt_lite(db_path: str, config) -> dict:
    if not bool(getattr(config, "HYPEROPT_LITE_ENABLED", False)):
        return {"enabled": False, "reason": "DISABLED"}

    risk_grid = getattr(
        config,
        "HYPEROPT_RISK_GRID",
        [0.01, 0.015, 0.02, 0.025],
    )
    sl_grid = getattr(
        config,
        "HYPEROPT_STOP_LOSS_GRID",
        [1.5, 2.0, 2.5, 3.0],
    )
    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            rows = conn.execute(
                """
                SELECT AVG(profit_factor) AS pf, AVG(win_rate) AS wr,
                       SUM(total_trades) AS trades
                FROM backtest_conditions
                WHERE total_trades >= ?
                """,
                (int(getattr(config, "BACKTEST_HARD_VETO_MIN_TRADES", 20) or 20),),
            ).fetchone()
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}

    if not rows or rows[2] is None or int(rows[2] or 0) < 5:
        return {"enabled": True, "reason": "INSUFFICIENT_BACKTEST_DATA"}

    pf = float(rows[0] or 1.0)
    wr = float(rows[1] or 0.5)
    best_risk = float(risk_grid[len(risk_grid) // 2])
    best_sl = float(sl_grid[len(sl_grid) // 2])
    if pf < 1.0 or wr < 0.48:
        best_risk = min(risk_grid)
        best_sl = max(sl_grid)
    elif pf > 1.35 and wr > 0.55:
        best_risk = max(risk_grid)
        best_sl = min(sl_grid)

    return {
        "enabled": True,
        "suggested_risk_per_trade": best_risk,
        "suggested_stop_loss_percent": best_sl,
        "aggregate_pf": round(pf, 3),
        "aggregate_wr": round(wr, 4),
        "backtest_trades": int(rows[2] or 0),
    }
