"""TradingView / external signal queue UI."""

from __future__ import annotations

import streamlit as st

from i18n import _


def render_webhooks_page():
    st.title(_("WEBHOOK_PAGE_TITLE"))
    if "db" not in st.session_state:
        st.warning(_("DB_NOT_INIT"))
        return

    db = st.session_state.db
    import config

    st.caption(_("WEBHOOK_PAGE_CAPTION").format(
        getattr(config, "WEBHOOK_SERVER_PORT", 8765),
    ))

    pending = db.list_external_signals(status="pending", limit=50)
    if not pending:
        st.info(_("WEBHOOK_EMPTY"))
        return

    for row in pending:
        cols = st.columns([3, 1, 1, 1])
        cols[0].markdown(
            f"**{row.get('symbol')}** · {row.get('action')} · "
            f"id={row.get('id')}"
        )
        if cols[1].button(_("WEBHOOK_APPROVE"), key=f"wh_ok_{row.get('id')}"):
            db.update_external_signal(row["id"], "approved", "ui_confirm")
            st.rerun()
        if cols[2].button(_("WEBHOOK_REJECT"), key=f"wh_no_{row.get('id')}"):
            db.update_external_signal(row["id"], "rejected", "ui_reject")
            st.rerun()

    st.markdown("---")
    st.subheader(_("WEBHOOK_HISTORY"))
    history = db.list_external_signals(limit=30)
    if history:
        st.dataframe(history, use_container_width=True, hide_index=True)
