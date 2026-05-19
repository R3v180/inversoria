import streamlit as st
from i18n import _
import json
from ui_services.page_cache import install_page_autorefresh, page_cache_ttl, render_stale_while_revalidate
from ui_services.ui_status import render_cache_status
from ui_services.technical_chart import build_technical_chart
from ui_services.log_display import translate_log_line
from ui_services.terminal_data import build_terminal_snapshot

TERMINAL_AUTO_REFRESH_SEC = 30


def render_terminal_page():
    col_t1, col_t2 = st.columns([4, 1])
    with col_t2:
        terminal_refresh = st.toggle(
            _("UI_TERMINAL_AUTO_REFRESH"),
            value=st.session_state.get("terminal_refresh", True),
            key="terminal_refresh_toggle",
        )
        st.session_state.terminal_refresh = terminal_refresh

    if terminal_refresh:
        interval = install_page_autorefresh("terminal") or TERMINAL_AUTO_REFRESH_SEC
    else:
        interval = TERMINAL_AUTO_REFRESH_SEC

    def _build():
        return build_terminal_snapshot(
            st.session_state.db,
            st.session_state.exchange,
            symbol=st.session_state.get("terminal_chart_symbol"),
        )

    def _render(data, stale=False, age_sec=0):
        render_terminal(data, stale=stale, age_sec=age_sec, refresh_sec=interval)

    render_stale_while_revalidate("terminal", _build, _render, ttl_sec=page_cache_ttl("terminal"))


def render_terminal(snapshot=None, *, stale=False, age_sec=0, refresh_sec=TERMINAL_AUTO_REFRESH_SEC):
    st.markdown("""
        <style>
        .stSelectbox div[data-baseweb="select"] {
            background-color: var(--iv-card-bg);
            color: var(--iv-text);
            border-radius: 8px;
        }
        .log-container {
            height:300px;
            overflow-y:auto;
            padding:15px;
            font-size: 0.85em;
        }
        </style>
    """, unsafe_allow_html=True)
    st.title(f"⚡ { _('NAV_TERMINAL') }")

    if st.session_state.get("terminal_refresh", True):
        st.caption(_("UI_TERMINAL_REFRESH_ON").format(int(refresh_sec)))
    else:
        st.caption(_("UI_TERMINAL_REFRESH_OFF"))
    render_cache_status(stale=stale, age_sec=age_sec, refresh_sec=int(refresh_sec))

    if "exchange" not in st.session_state:
        st.warning(_("TERMINAL_NOT_INITIALIZED"))
        return

    if snapshot is None:
        snapshot = build_terminal_snapshot(
            st.session_state.db,
            st.session_state.exchange,
            symbol=st.session_state.get("terminal_chart_symbol"),
        )

    current_symbols = list(snapshot.get("current_symbols") or [])
    default_index = int(snapshot.get("default_index") or 0)

    if "terminal_chart_symbol" not in st.session_state:
        st.session_state.terminal_chart_symbol = snapshot.get("symbol") or (current_symbols[0] if current_symbols else "BTC/USDT")

    symbol = st.selectbox(
        _("SELECT_ASSET"),
        current_symbols,
        index=default_index if default_index < len(current_symbols) else 0,
        key="terminal_chart_symbol",
    )

    col_chart, col_ai = st.columns([3, 1])

    with col_chart:
        st.subheader(f"{ _('TECH_ANALYSIS') }: {symbol}")
        ohlcv = snapshot.get("ohlcv")
        if symbol != snapshot.get("symbol"):
            ohlcv = st.session_state.exchange.get_historical_data(symbol, limit=300)
        if not ohlcv:
            st.error(_("DATA_ERROR"))
            return
        fig = build_technical_chart(ohlcv, height=700, rows="full")
        if fig is None:
            st.error(_("DATA_ERROR"))
            return
        fig.update_yaxes(title_text=_("PRICE"), row=1, col=1)
        fig.update_yaxes(title_text="RSI", row=2, col=1)
        fig.update_yaxes(title_text="ATR", row=3, col=1)
        st.plotly_chart(fig, width="stretch")

    with col_ai:
        st.subheader(f"🤖 { _('AI_CONSOLE') }")
        st.markdown("---")

        decision = snapshot.get("decision") or {}
        if symbol != snapshot.get("symbol"):
            try:
                raw = st.session_state.db.get_system_status(f"decision_{symbol}", "{}")
                decision = json.loads(raw or "{}")
            except Exception:
                decision = {}

        last_reason = decision.get("reasoning", _("NO_ANALYSIS"))

        if decision:
            with st.container(border=True):
                st.markdown(f"**🎯 { _('REGIME') }:** `{decision.get('regime', 'N/A')}`")
                st.markdown(f"**🧠 { _('STRATEGY') }:** `{decision.get('best_strategy', 'N/A')}`")
                conf = decision.get("confidence", 0)
                st.progress(conf, text=f"{ _('CONFIDENCE') }: {conf*100:.0f}%")

        with st.container(border=True):
            st.caption(f"{ _('LAST_INTERPRETATION') } ({symbol}):")
            st.write(last_reason)

        st.markdown("---")
        st.markdown(f"**{ _('LIVE_LOGS') }:**")

        log_html = "<div class='log-container iv-log-box'>"
        logs = snapshot.get("important_logs") or []
        if symbol != snapshot.get("symbol"):
            from ui_services.log_display import log_line_matches_noise

            raw_logs = st.session_state.db.get_logs()
            logs = [line for line in raw_logs if not log_line_matches_noise(line)][-20:]
        for log in logs:
            log_html += f"<span class='iv-positive'>>></span> <span>{translate_log_line(log)}</span><br/>"
        log_html += "</div>"

        st.markdown(log_html, unsafe_allow_html=True)
