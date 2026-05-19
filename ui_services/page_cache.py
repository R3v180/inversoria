"""Stale-while-revalidate helpers for Streamlit pages.

Shows the last cached snapshot immediately on navigation, then refreshes on the
next rerun when data is older than ttl_sec.
"""

from __future__ import annotations

import time

import streamlit as st

# interval: auto-refresh mientras permaneces en la pestaña (segundos)
# ttl: cuándo considerar datos viejos y forzar rebuild (debe ser < interval)
PAGE_LIVE_REFRESH = {
    "dashboard": {"interval": 30, "ttl": 25},
    "wallet": {"interval": 30, "ttl": 25},
    "history": {"interval": 45, "ttl": 40},
    "terminal": {"interval": 30, "ttl": 25},
}


def install_page_autorefresh(page_id: str) -> int | None:
    """Activa st_autorefresh para la pestaña. Devuelve el intervalo en segundos o None."""
    cfg = PAGE_LIVE_REFRESH.get(page_id)
    if not cfg:
        return None
    interval = int(cfg["interval"])
    from streamlit_autorefresh import st_autorefresh

    st_autorefresh(interval=interval * 1000, limit=1000, key=f"{page_id}_live_refresh")
    return interval


def page_cache_ttl(page_id: str, default: float = 25.0) -> float:
    cfg = PAGE_LIVE_REFRESH.get(page_id) or {}
    return float(cfg.get("ttl", default))


def _snapshot_store():
    return st.session_state.setdefault("ui_page_snapshots", {})


def get_snapshot(page_id: str) -> dict | None:
    entry = _snapshot_store().get(page_id)
    if not entry:
        return None
    return entry.get("data")


def set_snapshot(page_id: str, data) -> None:
    _snapshot_store()[page_id] = {"data": data, "ts": time.time()}


def snapshot_age_sec(page_id: str) -> float | None:
    entry = _snapshot_store().get(page_id)
    if not entry:
        return None
    return max(0.0, time.time() - float(entry.get("ts") or 0))


def invalidate_snapshot(page_id: str) -> None:
    _snapshot_store().pop(page_id, None)
    st.session_state.pop(f"_ui_refresh_pending_{page_id}", None)


def invalidate_all_snapshots() -> None:
    st.session_state.pop("ui_page_snapshots", None)
    for key in list(st.session_state.keys()):
        if str(key).startswith("_ui_refresh_pending_"):
            st.session_state.pop(key, None)


def render_stale_while_revalidate(
    page_id: str,
    build_fn,
    render_fn,
    ttl_sec: float = 25.0,
    *,
    force: bool = False,
) -> None:
    """Render cached page data first; refresh in a follow-up rerun when stale."""
    store = _snapshot_store()
    entry = store.get(page_id)
    pending_key = f"_ui_refresh_pending_{page_id}"
    pending = bool(st.session_state.get(pending_key))
    now = time.time()
    age = (now - float(entry["ts"])) if entry else None

    if force:
        st.session_state.pop(pending_key, None)
        entry = None

    if entry and entry.get("data") is not None and not pending:
        render_fn(entry["data"], stale=bool(age and age > ttl_sec), age_sec=age)
        if age is None or age > ttl_sec:
            st.session_state[pending_key] = True
            st.rerun()
        return

    if entry and pending:
        render_fn(entry["data"], stale=True, age_sec=age or 0.0)
        st.caption("Actualizando datos en segundo plano…")

    data = build_fn()
    store[page_id] = {"data": data, "ts": time.time()}
    st.session_state.pop(pending_key, None)
    render_fn(data, stale=False, age_sec=0.0)
