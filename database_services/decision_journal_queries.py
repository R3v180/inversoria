"""Decision journal query helpers (extracted from database_manager)."""

from __future__ import annotations

import time

import pandas as pd


def count_recent_exit_reasons(get_connection, symbol, reason_substrings=(), hours=24.0):
    sym = str(symbol or "").upper()
    since = time.time() - (float(hours) * 3600.0)
    needles = tuple(str(s).upper() for s in (reason_substrings or ()))
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT symbol, exit_reason, block_reason, timestamp FROM decision_journal ORDER BY id DESC LIMIT 500",
            conn,
        )
    if df.empty:
        return 0
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == sym]
    if "timestamp" in df.columns:
        df = df[pd.to_numeric(df["timestamp"], errors="coerce") >= since]
    if df.empty:
        return 0
    reason_col = df.get("exit_reason", df.get("block_reason", pd.Series(dtype=str))).fillna("").astype(str)
    return sum(1 for text in reason_col if any(n in text.upper() for n in needles))
