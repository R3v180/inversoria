"""Visual cycle replay from audit snapshots."""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from i18n import _
from ui_theme import apply_plotly_theme


def _open_positions_count(payload: dict) -> int:
    """Cycle snapshots store open_positions as symbol list (start) or count (done)."""
    raw = (payload or {}).get("open_positions")
    if raw is None:
        return 0
    if isinstance(raw, (list, tuple, set)):
        return len(raw)
    if isinstance(raw, dict):
        return len(raw)
    if isinstance(raw, int):
        return max(0, raw)
    if isinstance(raw, float):
        return max(0, int(raw))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _scanned_count(payload: dict) -> int:
    actions = (payload or {}).get("actions")
    if isinstance(actions, dict):
        return int(sum(actions.values()) or 0)
    scanned = (payload or {}).get("scanned")
    if scanned is None:
        return 0
    try:
        return int(scanned)
    except (TypeError, ValueError):
        return 0


def render_cycle_replay_chart(db, *, limit=80):
    snapshots = db.get_cycle_replay_snapshots(limit=limit)
    if not snapshots:
        st.caption(_("HIST_REPLAY_NO_SNAPSHOTS"))
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
            "open_positions": _open_positions_count(payload),
            "scanned": _scanned_count(payload),
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
        title=_("HIST_REPLAY_CHART_TITLE"),
    )
    apply_plotly_theme(fig)
    st.plotly_chart(fig, use_container_width=True)
