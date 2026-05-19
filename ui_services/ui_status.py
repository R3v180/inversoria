"""Unified cache / refresh status captions for Streamlit pages."""

from __future__ import annotations

import streamlit as st

from i18n import _


def render_page_refresh_intro(refresh_sec: int) -> None:
    st.caption(_("UI_AUTO_REFRESH_TAB").format(int(refresh_sec)))


def render_cache_status(
    *,
    stale: bool,
    age_sec: float | None,
    refresh_sec: int,
    updating: bool = False,
) -> None:
    if updating:
        st.caption(_("UI_CACHE_UPDATING"))
        return
    if age_sec is None:
        return
    age = max(0, int(age_sec))
    if stale:
        remaining = max(0, int(refresh_sec - age_sec))
        st.caption(_("UI_CACHE_STALE").format(age, remaining))
    elif age > 0:
        st.caption(_("UI_CACHE_FRESH").format(age, int(refresh_sec)))
