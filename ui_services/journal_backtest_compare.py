"""Compare live journal expectancy vs backtest priors by symbol."""

from __future__ import annotations

import sqlite3

import pandas as pd


def build_journal_vs_backtest_rows(db) -> list[dict]:
    rows_out = []
    try:
        journal = db.get_decision_journal(limit=2000)
    except Exception:
        return rows_out
    if journal.empty or "symbol" not in journal.columns:
        return rows_out

    realized = pd.to_numeric(
        journal.get("realized_pnl_pct", pd.Series([None] * len(journal))),
        errors="coerce",
    )
    closed = journal[realized.notna()].copy()
    if closed.empty:
        return rows_out
    closed["realized_pnl_pct"] = realized[realized.notna()]

    with sqlite3.connect(db.db_path, timeout=10) as conn:
        bt = pd.read_sql_query(
            """
            SELECT symbol, AVG(win_rate) AS bt_win_rate, AVG(profit_factor) AS bt_pf,
                   SUM(total_trades) AS bt_trades
            FROM backtest_conditions
            GROUP BY symbol
            """,
            conn,
        )

    for sym, grp in closed.groupby("symbol"):
        pnl = grp["realized_pnl_pct"]
        live_wr = (pnl > 0).mean() * 100
        live_exp = float(pnl.mean())
        live_n = len(pnl)
        bt_row = bt[bt["symbol"] == sym] if not bt.empty else pd.DataFrame()
        bt_wr = float(bt_row["bt_win_rate"].iloc[0] * 100) if not bt_row.empty else None
        bt_pf = float(bt_row["bt_pf"].iloc[0]) if not bt_row.empty else None
        bt_n = int(bt_row["bt_trades"].iloc[0]) if not bt_row.empty else 0
        gap = (live_wr - bt_wr) if bt_wr is not None else None
        rows_out.append({
            "symbol": sym,
            "live_trades": live_n,
            "live_win_rate": round(live_wr, 1),
            "live_expectancy_pct": round(live_exp, 2),
            "backtest_win_rate": round(bt_wr, 1) if bt_wr is not None else None,
            "backtest_pf": round(bt_pf, 2) if bt_pf is not None else None,
            "backtest_trades": bt_n,
            "wr_gap_live_minus_bt": round(gap, 1) if gap is not None else None,
        })
    rows_out.sort(key=lambda r: -abs(r.get("wr_gap_live_minus_bt") or 0))
    return rows_out
