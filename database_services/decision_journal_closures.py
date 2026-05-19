"""Journal closure helpers: link sells to decision_journal realized PnL."""

from __future__ import annotations

import json
import time
from typing import Any


TRADE_MARKER_PREFIX = "trade_id="


def trade_marker(trade_id: int | str) -> str:
    return f"{TRADE_MARKER_PREFIX}{int(trade_id)}"


def parse_entry_decision_id(extra_data: Any) -> int | None:
    if not extra_data:
        return None
    try:
        extra = json.loads(extra_data) if isinstance(extra_data, str) else dict(extra_data)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    raw = extra.get("entry_decision_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def infer_provider(extra_data: Any, reason: str) -> str:
    parsed = parse_entry_decision_id(extra_data)
    _ = parsed
    try:
        extra = json.loads(extra_data) if isinstance(extra_data, str) else (extra_data or {})
        if isinstance(extra, dict) and extra.get("provider"):
            return str(extra["provider"])
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    reason_l = str(reason or "").lower()
    if "manual" in reason_l:
        return "Manual"
    if "monitor" in reason_l:
        return "PositionMonitor"
    if "assistant" in reason_l:
        return "Assistant"
    return "Bot"


def apply_closure_to_journal(
    conn,
    *,
    symbol: str,
    exit_price: float,
    qty: float,
    pnl_pct: float,
    reason: str,
    extra_data: Any,
    trade_id: int,
    ts: float | None = None,
) -> bool:
    """
    Update entry decision and/or insert a trade-linked closure row.
    Returns True if journal was touched.
    """
    now = float(ts if ts is not None else time.time())
    entry_id = parse_entry_decision_id(extra_data)
    if entry_id:
        conn.execute(
            """
            UPDATE decision_journal
            SET realized_pnl_pct = ?, exit_reason = ?, updated_at = ?,
                execution_status = 'closed', execution_side = 'sell',
                executed_price = ?, executed_amount = ?,
                block_reason = ?
            WHERE id = ?
            """,
            (
                float(pnl_pct),
                str(reason or ""),
                now,
                float(exit_price),
                float(qty),
                trade_marker(trade_id),
                entry_id,
            ),
        )
        return True

    marker = trade_marker(trade_id)
    exists = conn.execute(
        "SELECT 1 FROM decision_journal WHERE block_reason = ? LIMIT 1",
        (marker,),
    ).fetchone()
    if exists:
        return False

    provider = infer_provider(extra_data, reason)
    conn.execute(
        """
        INSERT INTO decision_journal (
            timestamp, updated_at, symbol, price,
            ai_action, action_final, executable_action,
            provider, execution_status, execution_side,
            executed_price, executed_amount, realized_pnl_pct,
            exit_reason, block_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            now,
            str(symbol),
            float(exit_price),
            "SELL",
            "SELL",
            "SELL",
            provider,
            "closed",
            "sell",
            float(exit_price),
            float(qty),
            float(pnl_pct),
            str(reason or "")[:500],
            marker,
        ),
    )
    return True


def backfill_journal_closures_from_trades(conn, *, limit: int = 5000) -> int:
    """Idempotent: create journal closure rows for sells missing trade_id markers."""
    cursor = conn.execute(
        """
        SELECT id, symbol, price, amount, reason, pnl_pct, timestamp
        FROM trades
        WHERE LOWER(side) = 'sell'
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    )
    rows = cursor.fetchall()
    inserted = 0
    now = time.time()
    for row in rows:
        trade_id = int(row["id"])
        marker = trade_marker(trade_id)
        exists = conn.execute(
            "SELECT 1 FROM decision_journal WHERE block_reason = ? LIMIT 1",
            (marker,),
        ).fetchone()
        if exists:
            continue
        ts = float(row["timestamp"] or now)
        symbol = str(row["symbol"] or "")
        exit_price = float(row["price"] or 0)
        qty = float(row["amount"] or 0)
        pnl_pct = float(row["pnl_pct"] or 0)
        reason = str(row["reason"] or "BACKFILL_FROM_TRADES")
        near = conn.execute(
            """
            SELECT 1 FROM decision_journal
            WHERE symbol = ? AND realized_pnl_pct IS NOT NULL
              AND ABS(COALESCE(updated_at, timestamp) - ?) < 120
              AND ABS(realized_pnl_pct - ?) < 0.05
            LIMIT 1
            """,
            (symbol, ts, pnl_pct),
        ).fetchone()
        if near:
            continue
        conn.execute(
            """
            INSERT INTO decision_journal (
                timestamp, updated_at, symbol, price,
                ai_action, action_final, executable_action,
                provider, execution_status, execution_side,
                executed_price, executed_amount, realized_pnl_pct,
                exit_reason, block_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                ts,
                symbol,
                exit_price,
                "SELL",
                "SELL",
                "SELL",
                "Backfill",
                "closed",
                "sell",
                exit_price,
                qty,
                pnl_pct,
                reason[:500],
                marker,
            ),
        )
        inserted += 1
    return inserted
