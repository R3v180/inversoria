"""TradingView / external signal queue persistence."""

from __future__ import annotations

import json
import time


def ensure_webhook_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            source TEXT,
            symbol TEXT,
            action TEXT,
            status TEXT,
            raw_json TEXT,
            confirmed_at REAL,
            notes TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_signals_status_ts "
        "ON external_signals (status, timestamp)"
    )


def enqueue_signal(get_connection, *, source, symbol, action, raw_payload, status="pending"):
    ts = time.time()
    with get_connection() as conn:
        ensure_webhook_table(conn)
        cur = conn.execute(
            """
            INSERT INTO external_signals
                (timestamp, source, symbol, action, status, raw_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                str(source or "tradingview"),
                str(symbol or ""),
                str(action or "HOLD").upper(),
                str(status or "pending"),
                json.dumps(raw_payload or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return cur.lastrowid


def list_signals(get_connection, *, status=None, limit=50):
    with get_connection() as conn:
        ensure_webhook_table(conn)
        if status:
            rows = conn.execute(
                """
                SELECT * FROM external_signals
                WHERE status = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (str(status), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM external_signals
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
    return [dict(row) for row in rows]


def update_signal_status(get_connection, signal_id, status, notes=""):
    with get_connection() as conn:
        ensure_webhook_table(conn)
        conn.execute(
            """
            UPDATE external_signals
            SET status = ?, confirmed_at = ?, notes = ?
            WHERE id = ?
            """,
            (str(status), time.time(), str(notes or ""), int(signal_id)),
        )
        conn.commit()
