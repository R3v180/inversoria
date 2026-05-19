"""Persistence for strategy evaluation checkpoints (SQLite)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

EVALUATION_VIEWS_KEY = "evaluation_views"

CHECKPOINT_EVENT_TYPES = frozenset(
    {
        "reset_global",
        "preset_applied",
        "mode_change",
        "config_import",
        "profile_reset",
        "manual",
    }
)


def universe_key(modo_simulacion: bool, simulation_profile_id: str | None) -> str:
    if modo_simulacion:
        return f"sim:{simulation_profile_id or 'default'}"
    return "real"


def ensure_checkpoints_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_checkpoints (
            id TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            event_type TEXT NOT NULL,
            label TEXT NOT NULL,
            equity_usdt REAL NOT NULL,
            modo_simulacion INTEGER NOT NULL,
            simulation_profile_id TEXT,
            preset_id TEXT,
            config_diff_summary TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_checkpoints_universe "
        "ON strategy_checkpoints (modo_simulacion, simulation_profile_id, created_at DESC)"
    )


def _row_to_dict(row) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "id": row["id"],
        "created_at": float(row["created_at"]),
        "event_type": row["event_type"],
        "label": row["label"],
        "equity_usdt": float(row["equity_usdt"]),
        "modo_simulacion": bool(row["modo_simulacion"]),
        "simulation_profile_id": row["simulation_profile_id"],
        "preset_id": row["preset_id"],
        "config_diff_summary": row["config_diff_summary"],
    }


def insert_checkpoint(
    conn,
    *,
    event_type: str,
    label: str,
    equity_usdt: float,
    modo_simulacion: bool,
    simulation_profile_id: str | None,
    preset_id: str | None = None,
    config_diff_summary: str | None = None,
    checkpoint_id: str | None = None,
) -> dict[str, Any]:
    if event_type not in CHECKPOINT_EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}")
    cid = checkpoint_id or str(uuid.uuid4())
    created_at = time.time()
    conn.execute(
        """
        INSERT INTO strategy_checkpoints (
            id, created_at, event_type, label, equity_usdt,
            modo_simulacion, simulation_profile_id, preset_id, config_diff_summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cid,
            created_at,
            event_type,
            label,
            float(equity_usdt or 0.0),
            1 if modo_simulacion else 0,
            simulation_profile_id,
            preset_id,
            config_diff_summary,
        ),
    )
    return {
        "id": cid,
        "created_at": created_at,
        "event_type": event_type,
        "label": label,
        "equity_usdt": float(equity_usdt or 0.0),
        "modo_simulacion": modo_simulacion,
        "simulation_profile_id": simulation_profile_id,
        "preset_id": preset_id,
        "config_diff_summary": config_diff_summary,
    }


def list_checkpoints(
    conn,
    *,
    modo_simulacion: bool,
    simulation_profile_id: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    profile_val = simulation_profile_id if modo_simulacion else None
    rows = conn.execute(
        """
        SELECT * FROM strategy_checkpoints
        WHERE modo_simulacion = ? AND (
            (? = 1 AND simulation_profile_id = ?)
            OR (? = 0 AND simulation_profile_id IS NULL)
        )
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (1 if modo_simulacion else 0, 1 if modo_simulacion else 0, profile_val, 1 if modo_simulacion else 0, limit),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_checkpoint(conn, checkpoint_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM strategy_checkpoints WHERE id = ?",
        (checkpoint_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def load_evaluation_views(conn) -> dict[str, str | None]:
    row = conn.execute(
        "SELECT value FROM system_status WHERE key = ?",
        (EVALUATION_VIEWS_KEY,),
    ).fetchone()
    if not row or not row[0]:
        return {}
    try:
        data = json.loads(row[0])
        if isinstance(data, dict):
            return {str(k): (str(v) if v else None) for k, v in data.items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return {}


def save_evaluation_views(conn, views: dict[str, str | None]) -> None:
    payload = json.dumps(views, ensure_ascii=False)
    conn.execute(
        "INSERT OR REPLACE INTO system_status (key, value) VALUES (?, ?)",
        (EVALUATION_VIEWS_KEY, payload),
    )


def get_active_checkpoint_id(conn, universe: str) -> str | None:
    views = load_evaluation_views(conn)
    cid = views.get(universe)
    return cid if cid else None


def set_active_checkpoint_id(conn, universe: str, checkpoint_id: str | None) -> None:
    views = load_evaluation_views(conn)
    if checkpoint_id:
        views[universe] = checkpoint_id
    else:
        views.pop(universe, None)
    save_evaluation_views(conn, views)
