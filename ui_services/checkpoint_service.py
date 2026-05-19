"""Facade for strategy checkpoints (UI, launcher, assistant)."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import pandas as pd

import config
from database_services import checkpoints as cp
from simulation_profiles import get_active_profile

RISK_IMPORT_TRIGGER_PREFIXES = (
    "RISK_",
    "DECISION_",
    "STOP_",
    "MAX_DAILY",
    "MAX_PORTFOLIO",
    "TRADING_EXECUTION_MODE",
)

IMPORT_CHECKPOINT_MIN_KEYS = 8


def current_universe(exchange=None) -> tuple[bool, str | None, str]:
    modo_sim = bool(getattr(config, "MODO_SIMULACION", True))
    if exchange is not None:
        modo_sim = bool(getattr(exchange, "modo_simulacion", modo_sim))
    profile_id = None
    if modo_sim:
        try:
            profile_id = get_active_profile().get("id") or "default"
        except Exception:
            profile_id = getattr(config, "SIMULATION_PROFILE_ID", "default") or "default"
    return modo_sim, profile_id, cp.universe_key(modo_sim, profile_id)


def _conn(db):
    return db._get_connection()


def normalize_manual_label(label: str) -> str:
    cleaned = (label or "").strip()
    if not cleaned:
        raise ValueError("checkpoint label is required")
    return cleaned[:120]


def create_checkpoint(
    db,
    exchange,
    *,
    event_type: str,
    label: str,
    preset_id: str | None = None,
    config_diff: dict | list | None = None,
) -> dict[str, Any]:
    modo_sim, profile_id, _universe = current_universe(exchange)
    equity = float(exchange.get_balance() or 0.0)
    summary = None
    if config_diff is not None:
        if isinstance(config_diff, dict):
            keys = list(config_diff.keys())[:10]
            summary = json.dumps({"keys": keys}, ensure_ascii=False)
        else:
            summary = json.dumps(config_diff, ensure_ascii=False)[:2000]
    with _conn(db) as conn:
        row = cp.insert_checkpoint(
            conn,
            event_type=event_type,
            label=label,
            equity_usdt=equity,
            modo_simulacion=modo_sim,
            simulation_profile_id=profile_id,
            preset_id=preset_id,
            config_diff_summary=summary,
        )
        conn.commit()
    return row


def create_manual_checkpoint(db, exchange, *, label: str, activate_view: bool = True) -> dict[str, Any]:
    """Create a user-named manual checkpoint; optionally set as active evaluation view."""
    clean_label = normalize_manual_label(label)
    row = create_checkpoint(db, exchange, event_type="manual", label=clean_label)
    if activate_view:
        set_active_view(db, exchange, row["id"])
    return row


def list_checkpoints(db, exchange=None, limit: int = 50) -> list[dict[str, Any]]:
    modo_sim, profile_id, _ = current_universe(exchange)
    with _conn(db) as conn:
        rows = cp.list_checkpoints(
            conn,
            modo_simulacion=modo_sim,
            simulation_profile_id=profile_id,
            limit=limit,
        )
    return rows


def get_checkpoint(db, checkpoint_id: str) -> dict[str, Any] | None:
    with _conn(db) as conn:
        return cp.get_checkpoint(conn, checkpoint_id)


def get_active_checkpoint(db, exchange=None) -> dict[str, Any] | None:
    _modo, _pid, universe = current_universe(exchange)
    with _conn(db) as conn:
        active_id = cp.get_active_checkpoint_id(conn, universe)
        if not active_id:
            return None
        row = cp.get_checkpoint(conn, active_id)
    if not row:
        return None
    modo_sim, profile_id, _ = current_universe(exchange)
    row_universe = cp.universe_key(bool(row.get("modo_simulacion")), row.get("simulation_profile_id"))
    current_u = cp.universe_key(modo_sim, profile_id)
    if row_universe != current_u:
        return None
    return row


def set_active_view(db, exchange, checkpoint_id: str | None) -> None:
    _modo, _pid, universe = current_universe(exchange)
    with _conn(db) as conn:
        if checkpoint_id:
            row = cp.get_checkpoint(conn, checkpoint_id)
            if not row:
                raise ValueError("checkpoint not found")
            row_u = cp.universe_key(bool(row.get("modo_simulacion")), row.get("simulation_profile_id"))
            if row_u != universe:
                raise ValueError("checkpoint belongs to another universe")
        cp.set_active_checkpoint_id(conn, universe, checkpoint_id)
        conn.commit()


def clear_active_view(db, exchange=None) -> None:
    set_active_view(db, exchange, None)


def is_global_view(db, exchange=None) -> bool:
    return get_active_checkpoint(db, exchange) is None


def should_offer_import_checkpoint(changes: dict) -> bool:
    if not changes:
        return False
    keys = [str(k).upper() for k in changes.keys()]
    if len(keys) >= IMPORT_CHECKPOINT_MIN_KEYS:
        return True
    for key in keys:
        for prefix in RISK_IMPORT_TRIGGER_PREFIXES:
            if key.startswith(prefix):
                return True
    return False


def format_checkpoint_datetime(created_at: float) -> str:
    try:
        return datetime.fromtimestamp(float(created_at)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return "-"


def compact_checkpoint_summary(db, exchange) -> str:
    active = get_active_checkpoint(db, exchange)
    lines = []
    if active:
        perf_line = _active_perf_line(db, exchange, active)
        lines.append(
            f"Checkpoint activo: {active.get('label')} ({format_checkpoint_datetime(active.get('created_at'))}) "
            f"equity_ref={float(active.get('equity_usdt', 0)):.2f} USDT"
        )
        if perf_line:
            lines.append(perf_line)
    recent = list_checkpoints(db, exchange, limit=3)
    if recent:
        lines.append("Últimos checkpoints:")
        for row in recent:
            lines.append(
                f"- {row.get('label')} ({row.get('event_type')}) "
                f"{format_checkpoint_datetime(row.get('created_at'))} "
                f"{float(row.get('equity_usdt', 0)):.2f} USDT"
            )
    return "\n".join(lines) if lines else "Vista global (sin checkpoint activo)."


def _active_perf_line(db, exchange, active: dict) -> str:
    from ui_services.performance_period import compute_period_performance

    start_dt = datetime.fromtimestamp(float(active.get("created_at") or time.time()))
    balance = float(exchange.get_balance() or 0.0)
    perf = compute_period_performance(
        db,
        balance,
        start_dt,
        start_equity=float(active.get("equity_usdt") or 0.0),
    )
    if not perf.get("ok"):
        return ""
    return (
        f"Desde checkpoint: {perf['pnl_usd']:+.2f} USDT ({perf['pnl_pct']:+.2f}%)"
    )


def filter_trades_since_checkpoint(trades_df, active_checkpoint: dict | None):
    """Filter trades DataFrame with Date/timestamp >= checkpoint.created_at."""
    if active_checkpoint is None or trades_df is None or trades_df.empty:
        return trades_df
    cutoff = float(active_checkpoint.get("created_at") or 0)
    out = trades_df.copy()
    if "timestamp" in out.columns:
        return out[out["timestamp"] >= cutoff].copy()
    if "Date" in out.columns:
        dates = pd.to_datetime(out["Date"], errors="coerce")
        return out[dates >= pd.to_datetime(cutoff, unit="s", errors="coerce")].copy()
    return trades_df
