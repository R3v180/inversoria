"""Shared checkpoint UI blocks for History and Settings."""

from __future__ import annotations

import streamlit as st

from i18n import _
from ui_services import checkpoint_service as cs

MANUAL_FORM_OPEN_KEY = "manual_checkpoint_form_open"


def render_evaluation_view_bar(db, exchange, *, key_prefix: str = "hist") -> str:
    """
    Render global vs checkpoint view controls.
    Returns resolved view mode: 'global' | 'checkpoint'.
    """
    active = cs.get_active_checkpoint(db, exchange)
    view_options = ["global", "checkpoint"]
    widget_key = f"{key_prefix}_eval_view_mode"
    resolved_key = f"{key_prefix}_eval_view_resolved"

    bar_col, btn_col = st.columns([4, 1])
    with bar_col:
        pending = st.session_state.get(widget_key, "global")
        if pending == "checkpoint" and not active:
            pending = "global"
        default_idx = 1 if (pending == "checkpoint" and active) else 0
        view_mode = st.radio(
            _("HIST_VIEW_MODE_LABEL"),
            view_options,
            index=default_idx,
            format_func=lambda v: _("HIST_VIEW_GLOBAL") if v == "global" else _("HIST_VIEW_CHECKPOINT"),
            horizontal=True,
            key=widget_key,
        )
    with btn_col:
        st.write("")
        if st.button(
            _("HIST_CHECKPOINT_MANUAL_BTN"),
            key=f"{key_prefix}_open_manual_cp",
            use_container_width=True,
        ):
            st.session_state[MANUAL_FORM_OPEN_KEY] = True

    if view_mode == "global" and active:
        if st.button(_("HIST_CHECKPOINT_CLEAR_VIEW"), key=f"{key_prefix}_clear_cp_view"):
            cs.clear_active_view(db, exchange)
            st.rerun()
    resolved = view_mode
    if view_mode == "checkpoint" and not active:
        st.info(_("HIST_CHECKPOINT_EMPTY"))
        resolved = "global"

    render_manual_checkpoint_form(db, exchange, key_prefix=key_prefix)

    st.session_state[resolved_key] = resolved
    return resolved


def render_manual_checkpoint_form(db, exchange, *, key_prefix: str = "hist"):
    if not st.session_state.get(MANUAL_FORM_OPEN_KEY):
        return

    with st.container(border=True):
        st.markdown(f"##### {_('HIST_CHECKPOINT_MANUAL_FORM_TITLE')}")
        st.caption(_("HIST_CHECKPOINT_MANUAL_HINT"))
        label = st.text_input(
            _("HIST_CHECKPOINT_MANUAL_LABEL"),
            value="",
            placeholder=_("HIST_CHECKPOINT_MANUAL_PLACEHOLDER"),
            key=f"{key_prefix}_manual_cp_name",
        )
        activate_now = st.checkbox(
            _("HIST_CHECKPOINT_ACTIVATE_ON_CREATE"),
            value=True,
            key=f"{key_prefix}_manual_cp_activate",
        )
        save_col, cancel_col = st.columns(2)
        if save_col.button(
            _("HIST_CHECKPOINT_MANUAL_SAVE"),
            type="primary",
            key=f"{key_prefix}_manual_cp_save",
            use_container_width=True,
        ):
            name = (label or "").strip()
            if not name:
                st.error(_("HIST_CHECKPOINT_NAME_REQUIRED"))
                return
            cs.create_manual_checkpoint(
                db,
                exchange,
                label=name,
                activate_view=activate_now,
            )
            st.session_state[MANUAL_FORM_OPEN_KEY] = False
            st.success(_("HIST_CHECKPOINT_CREATED"))
            st.rerun()

        if cancel_col.button(
            _("HIST_CHECKPOINT_CANCEL"),
            key=f"{key_prefix}_manual_cp_cancel",
            use_container_width=True,
        ):
            st.session_state[MANUAL_FORM_OPEN_KEY] = False
            st.rerun()


def render_checkpoint_manager(db, exchange, *, key_prefix: str = "hist"):
    with st.expander(_("HIST_CHECKPOINT_LIST_TITLE"), expanded=False):
        rows = cs.list_checkpoints(db, exchange, limit=30)
        if not rows:
            st.caption(_("HIST_CHECKPOINT_EMPTY"))
        else:
            for row in rows:
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.write(
                    f"**{row.get('label')}** · {cs.format_checkpoint_datetime(row.get('created_at'))} "
                    f"· {float(row.get('equity_usdt', 0)):.2f} USDT"
                )
                event_type = row.get("event_type") or ""
                if event_type == "manual":
                    event_type = _("HIST_CHECKPOINT_EVENT_MANUAL")
                c2.caption(str(event_type))
                if c3.button(
                    _("HIST_CHECKPOINT_ACTIVATE_BTN"),
                    key=f"{key_prefix}_activate_{row.get('id')}",
                ):
                    cs.set_active_view(db, exchange, row["id"])
                    st.rerun()

        st.caption(_("HIST_CHECKPOINT_LIST_HINT"))
