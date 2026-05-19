from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta

import pandas as pd


PERFORMANCE_PRESETS = (
    "Hoy 00:00",
    "Última hora",
    "Últimas 24h",
    "Inicio disponible",
    "Personalizado",
)


def preset_start_datetime(preset: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    if preset == "Hoy 00:00":
        return datetime.combine(now.date(), dt_time.min)
    if preset == "Última hora":
        return now - timedelta(hours=1)
    if preset == "Últimas 24h":
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


def compute_period_performance(db, current_equity: float, start_dt: datetime | None) -> dict:
    df = load_equity_history(db)
    current_equity = float(current_equity or 0.0)
    if df.empty:
        return {
            "ok": False,
            "reason": "Sin historial de equity todavía.",
            "current_equity": current_equity,
            "period_df": df,
        }

    if start_dt is None:
        period_df = df.copy()
    else:
        start_ts = pd.Timestamp(start_dt)
        period_df = df[df["timestamp"] >= start_ts].copy()
        if period_df.empty:
            period_df = df.tail(1).copy()

    start_row = period_df.iloc[0]
    start_equity = float(start_row["total_value"] or 0.0)
    pnl_usd = current_equity - start_equity
    pnl_pct = (pnl_usd / start_equity * 100.0) if start_equity > 0 else 0.0

    curve_df = period_df[["timestamp", "total_value"]].copy()
    if curve_df.empty or curve_df.iloc[-1]["total_value"] != current_equity:
        curve_df = pd.concat(
            [
                curve_df,
                pd.DataFrame([{"timestamp": pd.Timestamp.now(), "total_value": current_equity}]),
            ],
            ignore_index=True,
        )
    curve_df["pnl_usd"] = curve_df["total_value"] - start_equity

    return {
        "ok": True,
        "start_ts": start_row["timestamp"],
        "start_equity": start_equity,
        "current_equity": current_equity,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "points": len(curve_df),
        "period_df": curve_df,
    }

