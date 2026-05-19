from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta

import pandas as pd

from i18n import _

PERFORMANCE_PRESET_IDS = (
    "today",
    "last_hour",
    "last_24h",
    "earliest",
    "from_active_checkpoint",
    "custom",
)

# Backward compatibility
PERFORMANCE_PRESETS = PERFORMANCE_PRESET_IDS


def performance_preset_label(preset_id: str) -> str:
    key = f"HIST_PRESET_{preset_id.upper()}"
    text = _(key)
    return text if text != key else preset_id


def preset_start_datetime(
    preset_id: str,
    now: datetime | None = None,
    *,
    active_checkpoint: dict | None = None,
) -> datetime | None:
    now = now or datetime.now()
    if preset_id == "from_active_checkpoint":
        if active_checkpoint and active_checkpoint.get("created_at"):
            return datetime.fromtimestamp(float(active_checkpoint["created_at"]))
        return None
    if preset_id == "today":
        return datetime.combine(now.date(), dt_time.min)
    if preset_id == "last_hour":
        return now - timedelta(hours=1)
    if preset_id == "last_24h":
        return now - timedelta(hours=24)
    return None


def load_equity_history(db, limit: int = 5000) -> pd.DataFrame:
    try:
        df = db.get_equity_history(limit=limit)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["total_value"] = pd.to_numeric(out["total_value"], errors="coerce")
    out = out.dropna(subset=["timestamp", "total_value"]).sort_values("timestamp")
    return out


def compute_period_performance(
    db,
    current_equity: float,
    start_dt: datetime | None,
    *,
    start_equity: float | None = None,
) -> dict:
    df = load_equity_history(db)
    current_equity = float(current_equity or 0.0)
    fixed_start_equity = start_equity is not None
    if df.empty and not fixed_start_equity:
        return {
            "ok": False,
            "reason": _("HIST_PERF_NO_EQUITY_HISTORY"),
            "current_equity": current_equity,
            "period_df": df,
        }

    if start_dt is None:
        period_df = df.copy() if not df.empty else pd.DataFrame()
    else:
        start_ts = pd.Timestamp(start_dt)
        period_df = df[df["timestamp"] >= start_ts].copy() if not df.empty else pd.DataFrame()
        if period_df.empty and not df.empty:
            period_df = df.tail(1).copy()

    if fixed_start_equity:
        start_equity_val = float(start_equity or 0.0)
        start_ts_used = pd.Timestamp(start_dt) if start_dt is not None else pd.Timestamp.now()
    elif period_df.empty:
        return {
            "ok": False,
            "reason": _("HIST_PERF_NO_EQUITY_HISTORY"),
            "current_equity": current_equity,
            "period_df": period_df,
        }
    else:
        start_row = period_df.iloc[0]
        start_equity_val = float(start_row["total_value"] or 0.0)
        start_ts_used = start_row["timestamp"]
    pnl_usd = current_equity - start_equity_val
    pnl_pct = (pnl_usd / start_equity_val * 100.0) if start_equity_val > 0 else 0.0

    if not period_df.empty and "timestamp" in period_df.columns and "total_value" in period_df.columns:
        curve_df = period_df[["timestamp", "total_value"]].copy()
    else:
        curve_df = pd.DataFrame(columns=["timestamp", "total_value"])
    if curve_df.empty or curve_df.iloc[-1]["total_value"] != current_equity:
        curve_df = pd.concat(
            [
                curve_df,
                pd.DataFrame([{"timestamp": pd.Timestamp.now(), "total_value": current_equity}]),
            ],
            ignore_index=True,
        )
    curve_df["pnl_usd"] = curve_df["total_value"] - start_equity_val

    return {
        "ok": True,
        "start_ts": start_ts_used,
        "start_equity": start_equity_val,
        "current_equity": current_equity,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "points": len(curve_df),
        "period_df": curve_df,
        "fixed_start_equity": fixed_start_equity,
    }
