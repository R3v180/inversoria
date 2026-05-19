"""Visual cycle replay from audit snapshots."""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from ui_theme import apply_plotly_theme


def render_cycle_replay_chart(db, *, limit=80):
    snapshots = db.get_cycle_replay_snapshots(limit=limit)
    if not snapshots:
        st.caption("Sin snapshots de ciclo para replay.")
        return

    rows = []
    for snap in snapshots:
        payload = {}
        try:
            payload = json.loads(snap.get("payload_json") or "{}")
        except Exception:
            payload = {}
        rows.append({
            "cycle_id": snap.get("cycle_id"),
            "phase": snap.get("phase"),
            "timestamp": float(snap.get("timestamp") or 0),
            "equity": payload.get("equity"),
            "open_positions": len(payload.get("open_positions") or []),
            "scanned": (payload.get("actions") or {}).get("BUY", 0)
            if isinstance(payload.get("actions"), dict)
            else payload.get("scanned"),
        })
    df = pd.DataFrame(rows)
    if df.empty or df["timestamp"].isna().all():
        return
    df["time"] = pd.to_datetime(df["timestamp"], unit="s")
    fig = px.scatter(
        df,
        x="time",
        y="equity",
        color="phase",
        hover_data=["cycle_id", "open_positions"],
        title="Replay visual — equity por fase de ciclo",
    )
    apply_plotly_theme(fig)
    st.plotly_chart(fig, use_container_width=True)
