import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import json
from config import SYMBOLS, get_effective_max_positions
from i18n import _
from ui_theme import apply_plotly_theme
from ui_services.emergency_actions import liquidate_all_to_usdt
from ui_services.manual_trading import execute_manual_sell
from ui_services.portfolio_summary import collect_visible_portfolio, compute_dashboard_breakdown
from ui_services.technical_chart import build_technical_chart
from ui_services.dashboard_data import build_dashboard_snapshot
from ui_services.page_cache import (
    invalidate_snapshot,
    install_page_autorefresh,
    page_cache_ttl,
    render_stale_while_revalidate,
)
from ui_services.ui_status import render_cache_status, render_page_refresh_intro


def _execute_dashboard_manual_sell(db, exchange, sym: str, qty: float, current_price: float):
    if qty <= 0:
        st.error(_('MANUAL_SELL_ZERO'))
        return

    outcome = execute_manual_sell(db, exchange, sym, qty, current_price, _("MANUAL_SELL_REASON"))
    if outcome.get("ok"):
        exchange.invalidate_ui_cache()
        invalidate_snapshot("dashboard")
        st.success(_("MANUAL_SELL_OK"))
        st.rerun()
    else:
        st.error(f"{_('MANUAL_SELL_FAIL')}: {outcome.get('reason', outcome)}")


def _get_dashboard_max_sell(exchange, sym: str, pos: dict) -> float:
    pos_amount = float(pos.get("amount") or 0)
    real_amount = float(exchange.get_coin_balance(sym) or 0)
    max_sell = min(pos_amount, real_amount) if real_amount > 0 else pos_amount
    return max(0.0, float(max_sell or 0))


def _render_dashboard_sell_options(db, exchange, sym: str, pos: dict, current_price: float, safe_key: str):
    panel_key = f"dash_sell_panel_{safe_key}"
    max_sell = _get_dashboard_max_sell(exchange, sym, pos)

    with st.expander(
        f"{_('MANUAL_SELL_OPTIONS')} · {sym}",
        expanded=bool(st.session_state.get(panel_key, False)),
    ):
        st.caption(_("MANUAL_SELL_MAX").format(f"{max_sell:.10g}"))

        if max_sell <= 0:
            st.warning(_("MANUAL_SELL_ZERO"))
            if st.button(_("MANUAL_SELL_CANCEL"), key=f"dash_sell_cancel_empty_{safe_key}"):
                st.session_state[panel_key] = False
                st.rerun()
            return

        mode = st.radio(
            _("MANUAL_SELL_MODE"),
            [_("MANUAL_SELL_ALL"), _("MANUAL_SELL_CUSTOM")],
            horizontal=True,
            key=f"dash_sell_mode_{safe_key}",
        )
        if mode == _("MANUAL_SELL_ALL"):
            qty = max_sell
        else:
            qty = st.number_input(
                _("MANUAL_SELL_QTY"),
                min_value=0.0,
                max_value=float(max_sell),
                value=float(max_sell),
                step=1e-8 if max_sell < 1 else 1e-6,
                key=f"dash_sell_qty_{safe_key}",
            )

        pv = exchange.prevalidate_market_sell(sym, qty, current_price, free_override=max_sell)
        hard_errors = [
            er for er in pv.get("errors", [])
            if not str(er).startswith("SLIPPAGE:")
        ]
        if pv.get("errors"):
            for er in pv.get("errors", []):
                st.warning(str(er))
        else:
            amt_ok = pv.get("amount_after_precision") or qty
            st.success(f"{_('WALLET_PRECHECK')}: OK · {float(amt_ok):.10g} (~{float(amt_ok) * float(current_price):.2f} USDT)")

        c1, c2 = st.columns(2)
        if c1.button(_("MANUAL_SELL_SUBMIT"), key=f"dash_sell_submit_{safe_key}", type="primary", disabled=bool(hard_errors)):
            _execute_dashboard_manual_sell(db, exchange, sym, float(qty), float(current_price))
        if c2.button(_("MANUAL_SELL_CANCEL"), key=f"dash_sell_cancel_{safe_key}"):
            st.session_state[panel_key] = False
            st.rerun()


def _render_refresh_status(diag: dict):
    now_txt = time.strftime("%H:%M:%S")
    state = diag.get("state", "-") if isinstance(diag, dict) else "-"
    state_age = None
    if isinstance(diag, dict) and diag.get("state_ts"):
        try:
            state_age = max(0, int(time.time() - float(diag.get("state_ts"))))
        except (TypeError, ValueError):
            state_age = None
    age_txt = _("DASH_AGO_SECONDS").format(state_age) if state_age is not None else _("DASH_NO_HEARTBEAT")
    scanned = diag.get("scanned", 0) if isinstance(diag, dict) else 0
    st.caption(f"{_('DASH_LAST_UI_UPDATE')}: {now_txt} · {_('DASH_DAEMON')}: {state} · {age_txt} · scan {scanned}")


DASHBOARD_AUTO_REFRESH_SEC = 30


def render_dashboard_page():
    """Caché rápida al cambiar pestaña + auto-refresh cada 30s mientras miras el dashboard."""
    install_page_autorefresh("dashboard")
    render_stale_while_revalidate(
        "dashboard",
        lambda: build_dashboard_snapshot(
            st.session_state.db,
            st.session_state.exchange,
            chart_symbol=st.session_state.get("selected_chart_symbol"),
        ),
        lambda data, stale=False, age_sec=0: render_dashboard(data, stale=stale, age_sec=age_sec),
        ttl_sec=page_cache_ttl("dashboard"),
    )


def render_dashboard(snapshot=None, *, stale=False, age_sec=0):
    # Estilos locales apoyados en las variables globales de tema.
    st.markdown("""
        <style>
        .position-card { padding: 20px; margin-bottom: 10px; }
        .position-card .muted { color: var(--iv-muted); font-size: 0.8em; }
        .ai-card {
            border-left: 5px solid var(--iv-accent);
            padding: 20px;
            border-radius: 0 12px 12px 0;
        }
        .log-box { height: 180px; overflow-y: auto; padding: 10px; font-size: 0.8em; }
        .radar-item {
            display: flex;
            justify-content: space-between;
            padding: 8px;
            border-bottom: 1px solid var(--iv-border);
            color: var(--iv-text);
            font-size: 0.9em;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title(f"🏛️ { _('DASHBOARD_TITLE') }")
    render_page_refresh_intro(DASHBOARD_AUTO_REFRESH_SEC)
    render_cache_status(stale=stale, age_sec=age_sec, refresh_sec=DASHBOARD_AUTO_REFRESH_SEC)

    db = st.session_state.db
    exchange = st.session_state.exchange

    if snapshot is None:
        snapshot = build_dashboard_snapshot(
            db,
            exchange,
            chart_symbol=st.session_state.get("selected_chart_symbol"),
        )

    if "selected_chart_symbol" not in st.session_state:
        st.session_state.selected_chart_symbol = snapshot.get("chart_symbol", "BTC/USDT")

    available_usdt = snapshot["available_usdt"]
    total_value = snapshot["total_value"]
    portfolio = snapshot.get("portfolio") or {}
    breakdown = snapshot["breakdown"]
    baseline = breakdown["baseline"]
    baseline_label = breakdown["baseline_label"]
    pnl = breakdown["pnl"]
    pnl_pct = breakdown["pnl_pct"]
    open_positions = breakdown["open_positions"]
    managed_positions_value = breakdown["managed_positions_value"]
    other_balances_value = breakdown["other_balances_value"]
    current_symbols = list(snapshot.get("current_symbols") or SYMBOLS)
    diag_top = snapshot.get("diag_top") or {}
    diag_raw = snapshot.get("diag_raw") or "{}"
    dynamic_max = snapshot.get("dynamic_max") or get_effective_max_positions(total_value)

    # --- TOP METRICS ---
    exec_mode = diag_top.get("execution_mode", "-")
    decision_mode = diag_top.get("decision_mode", "-")
    mode_label = f"{'SIM' if exchange.modo_simulacion else 'REAL'} · {exec_mode}"
    state_label = diag_top.get("state", "-")
    _render_refresh_status(diag_top)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric(_('EQUITY_TOTAL'), f"${total_value:.2f}", f"{pnl_pct:.2f}%")
    m2.metric(_('AVAILABLE'), f"${available_usdt:.2f}")
    m3.metric(_('POSITIONS'), f"{len(open_positions)} / {dynamic_max}")
    m4.metric(_('PNL_USD'), f"${pnl:.2f}", f"{pnl_pct:.2f}%")
    m5.metric(_("DASH_MODE"), mode_label)
    m6.metric(_("DAEMON_STATE"), state_label, f"{decision_mode} · {diag_top.get('scanned', 0)} scan")
    baseline_text = {
        "real_start": _("BASELINE_REAL_START"),
        "initial": _("BASELINE_INITIAL"),
    }.get(baseline_label, baseline_label)
    st.caption(
        _("DASH_EQUITY_BREAKDOWN").format(
            available_usdt,
            managed_positions_value,
            other_balances_value,
            baseline_text,
            baseline,
        )
    )
    st.caption(_("DASH_AUTO_REFRESH_NOTE"))

    # --- POSITIONS + LIVE EVENTS FIRST ---
    col_left, col_right = st.columns([1.5, 1])

    with col_left:
        st.markdown(f"### 💼 { _('ACTIVE_POSITIONS') }")
        if open_positions:
            for row in snapshot.get("position_rows") or []:
                sym = row["symbol"]
                pos = row["pos"]
                current_price = row["current_price"]
                u_pnl = row["u_pnl"]
                current_value = row["current_value"]
                color = "var(--iv-accent)" if u_pnl >= 0 else "var(--iv-danger)"
                with st.container():
                    safe_key = sym.replace("/", "_").replace(" ", "_")
                    col_info, col_chart, col_sell = st.columns([4.2, 0.9, 0.9])
                    with col_info:
                        st.markdown(f'<div class="position-card iv-card" style="margin-bottom: 5px; padding: 15px;"><div style="display:flex; justify-content:space-between;"><div><b>{sym}</b><br/><span class="muted">{ _("INVESTMENT") }: ${current_value:.2f}</span></div><div style="text-align:right;"><span style="font-size:1.2em; font-weight:bold; color:{color};">{u_pnl:.2f}%</span><br/><span class="muted">${current_price:.4f}</span></div></div></div>', unsafe_allow_html=True)
                    with col_chart:
                        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

                        def update_chart_symbol(s=sym):
                            st.session_state.selected_chart_symbol = s

                        st.button("📈", key=f"btn_chart_{safe_key}", help=_('DASH_VIEW_CHART').format(sym), on_click=update_chart_symbol)
                    with col_sell:
                        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                        if st.button(
                            _('MANUAL_SELL'),
                            key=f"btn_sell_{safe_key}",
                            help=_('MANUAL_SELL_HELP'),
                            type="secondary",
                        ):
                            max_sell = _get_dashboard_max_sell(exchange, sym, pos)
                            _execute_dashboard_manual_sell(db, exchange, sym, max_sell, current_price)
                    _render_dashboard_sell_options(db, exchange, sym, pos, current_price, safe_key)
        else:
            st.info(_('NO_POSITIONS'))

    with col_right:
        st.markdown(f"### 🤖 { _('DASH_LIVE_EVENTS') }")
        decision = snapshot.get("last_decision") or {}
        if decision:
            st.markdown(f'<div class="ai-card iv-card"><b>{decision.get("symbol", "N/A")}</b> | <span class="iv-positive">{decision.get("regime", "N/A")}</span><p style="font-size:0.85em; margin-top:5px;">{decision.get("reasoning", "")[:100]}...</p></div>', unsafe_allow_html=True)

        st.markdown("<br/>", unsafe_allow_html=True)
        important_logs = snapshot.get("important_logs") or []
        log_content = "".join([f"<span class='iv-positive'>>></span> {l}<br/>" for l in important_logs])
        st.markdown(f'<div class="log-box iv-log-box">{log_content}</div>', unsafe_allow_html=True)

    # --- COMMAND CENTER ---
    st.markdown("---")
    col_equity, col_market = st.columns([1, 1.2])

    with col_equity:
        st.markdown(f"### 📈 { _('EQUITY_CHART') }")
        equity_df = snapshot.get("equity_df")
        if equity_df is None:
            equity_df = db.get_equity_history(limit=500)
        if not equity_df.empty:
            fig_equity = go.Figure()
            fig_equity.add_trace(go.Scatter(x=equity_df['timestamp'], y=equity_df['total_value'], fill='tozeroy', fillcolor='rgba(0, 168, 120, 0.14)', line=dict(color='#008A63', width=3)))
            apply_plotly_theme(fig_equity, height=400, margin=dict(l=0, r=0, t=0, b=0))
            fig_equity.update_xaxes(showgrid=False)
            st.plotly_chart(fig_equity, width='stretch')

    with col_market:
        c1, c2 = st.columns([2, 1])
        with c1: st.markdown(f"### 🕯️ { _('MARKET_CHART') }")
        
        if st.session_state.selected_chart_symbol not in current_symbols:
            current_symbols.insert(0, st.session_state.selected_chart_symbol)

        with c2:
            selected_sym = st.selectbox(_('SELECT_ASSET'), current_symbols, key="selected_chart_symbol", label_visibility="collapsed")

        ohlcv = snapshot.get("ohlcv")
        if selected_sym != snapshot.get("chart_symbol"):
            ohlcv = exchange.get_historical_data(selected_sym, limit=150)
        fig = build_technical_chart(ohlcv, height=400, rows="compact")
        if fig:
            st.plotly_chart(fig, width='stretch')

    # --- PANEL DE INTELIGENCIA ---
    st.markdown("---")
    st.markdown(f"### 🧠 { _('SYSTEM_INTEL') }")

    col_macro, col_backtest = st.columns(2)

    with col_macro:
        with st.expander(f"🌍 { _('MACRO_CONTEXT') }", expanded=True):
            macro = snapshot.get("macro") or {}
            try:
                if macro:
                    regime = macro.get('macro_regime', 'N/A')
                    regime_color = {
                        'RISK_ON': 'var(--iv-accent)', 'ALTSEASON': 'var(--iv-accent)',
                        'NEUTRAL': 'var(--iv-warning)', 'CAUTION': 'var(--iv-warning)',
                        'RISK_OFF': 'var(--iv-danger)'
                    }.get(regime, 'var(--iv-muted)')

                    st.markdown(
                        f"<div style='text-align:center; padding:10px; border-radius:8px; "
                        f"background:var(--iv-card-bg); border:1px solid var(--iv-border); color:{regime_color}; font-size:1.2em; "
                        f"font-weight:bold;'>{ _('REGIME_LABEL') }: {regime}</div>",
                        unsafe_allow_html=True
                    )
                    st.metric(_('BTC_DOM'), f"{macro.get('btc_dominance', 0):.1f}%")
                    st.metric(_('MARKET_CAP'), f"{macro.get('market_cap_change_24h', 0):+.2f}%")
                    st.metric(_('LEADING_SECTOR'), macro.get('leading_sector', 'N/A').upper())
                    
                    # Mostrar datos de Alpha Vantage v6.0
                    st.markdown("---")
                    st.markdown(f"**{ _('GLOBAL_TITLE') }**")
                    macro_db = snapshot.get("macro_db") or {}
                    if macro_db:
                        c_m1, c_m2 = st.columns(2)
                        # DXY Proxy
                        if 'UUP' in macro_db:
                            d = macro_db['UUP']
                            c_m1.metric(_('DOLLAR'), f"${d['price']:.2f}", f"{d['change_24h']:+.2f}%")
                        # SP500
                        if 'SPY' in macro_db:
                            d = macro_db['SPY']
                            c_m2.metric(_('SP500'), f"${d['price']:.2f}", f"{d['change_24h']:+.2f}%")
                    else:
                        st.caption(_('DASH_ALPHA_LOADING'))
                else:
                    st.info(_('DASH_MACRO_PENDING'))
            except Exception:
                st.info(_('DASH_MACRO_LOADING'))

    with col_backtest:
        with st.container(border=True):
            st.markdown(f"**📊 { _('BACKTEST_STATUS') }**")
            runs = snapshot.get("backtest_runs") or []
            if runs:
                for run in runs:
                    st.markdown(
                        f"**{run.get('symbol')}** · {run.get('timeframe')} · "
                        f"WR {float(run.get('win_rate') or 0):.0%} · "
                        f"{ _('BEST_STRATEGY') }: {run.get('best_strategy')}"
                    )
            else:
                st.info(_('NO_BACKTEST_DATA'))

            st.markdown("---")
            try:
                from ui_news import render_news_widget
                widget_symbols = list({*current_symbols[:12], *open_positions.keys()})
                render_news_widget(widget_symbols, limit=4)
            except Exception as e:
                st.info(f"{_('NEWS_WIDGET_TITLE')}: {e}")

    with st.expander(f"🩺 { _('DAEMON_DIAG_TITLE') }", expanded=False):
        try:
            diag = json.loads(diag_raw or "{}")
            if not diag:
                st.info(_('DAEMON_NO_DIAG'))
            else:
                state_age = max(0, int(time.time() - float(diag.get("state_ts", 0))))
                cycle_ts = float(diag.get("cycle_ts") or 0)
                cycle_age = max(0, int(time.time() - cycle_ts)) if cycle_ts else None
                d1, d2, d3, d4 = st.columns(4)
                d1.metric(_('DAEMON_STATE'), diag.get("state", "-"), f"{state_age}s")
                d2.metric(_('DAEMON_LAST_CYCLE'), f"{cycle_age}s" if cycle_age is not None else "-")
                d3.metric(_('DAEMON_SCANNED'), diag.get("scanned", 0))
                d4.metric(_('DAEMON_OPEN_POS'), f"{diag.get('open_positions', 0)} / {diag.get('dynamic_max', '-')}")

                a1, a2, a3 = st.columns(3)
                actions = diag.get("actions", {})
                a1.caption(f"BUY: {actions.get('BUY', 0)}")
                a2.caption(f"SELL: {actions.get('SELL', 0)}")
                a3.caption(f"HOLD: {actions.get('HOLD', 0)}")

                if diag.get("providers"):
                    st.caption("Providers: " + ", ".join(f"{k}: {v}" for k, v in diag["providers"].items()))
                if diag.get("skipped"):
                    st.caption("Skipped: " + ", ".join(f"{k}: {v}" for k, v in diag["skipped"].items()))
                if diag.get("unreconciled_orders_count", 0):
                    st.warning(f"Órdenes pendientes/no reconciliadas: {diag.get('unreconciled_orders_count')}")
                    rows = diag.get("unreconciled_orders") or []
                    if rows:
                        st.dataframe(rows, width="stretch", hide_index=True)
                if diag.get("order_reconcile"):
                    rec = diag.get("order_reconcile") or {}
                    st.caption(
                        "Reconciliación órdenes: "
                        f"checked={rec.get('checked', 0)} · "
                        f"updated={rec.get('updated', 0)} · "
                        f"applied={rec.get('applied', 0)}"
                    )
                if diag.get("symbol_cooldowns"):
                    st.markdown("**Cooldowns por símbolo**")
                    for row in diag.get("symbol_cooldowns") or []:
                        minutes = max(1, int(float(row.get("remaining_seconds") or 0) / 60))
                        st.caption(f"{row.get('symbol')} · {minutes}m restantes")
                if diag.get("risk_guards"):
                    rg = diag.get("risk_guards") or {}
                    status = "OK" if rg.get("ok", True) else _('DASH_RISK_BLOCKING')
                    st.caption(
                        _('DASH_RISK_SUMMARY').format(
                            status,
                            rg.get('daily_loss_pct', 0),
                            rg.get('exposure_pct', 0),
                            rg.get('alt_exposure_pct', 0),
                            rg.get('bucket_exposure_pct', 0),
                        )
                    )
                if diag.get("top_buy_candidates"):
                    st.markdown(f"**{_('DASH_TOP_BUY_CANDIDATES')}**")
                    for c in diag["top_buy_candidates"]:
                        st.caption(
                            f"{c.get('symbol')} · score {c.get('score')} · "
                            f"decision {float(c.get('decision_score', 0)):.0%} · "
                            f"conf {float(c.get('confidence', 0)):.0%}"
                        )
                if diag.get("hold_reasons"):
                    st.markdown(f"**{_('DAEMON_TOP_HOLDS')}**")
                    for reason, count in diag["hold_reasons"].items():
                        st.caption(f"{count}× {reason}")
                st.caption("Métricas detalladas de provider/régimen movidas a Historial y Analítica.")
        except Exception as e:
            st.info(f"{_('DAEMON_DIAG_TITLE')}: {e}")

    # --- PORTFOLIO CONTEXT ---
    st.markdown("---")
    c_pie, c_radar = st.columns([1, 1])
    
    with c_pie:
        with st.expander(f"🥧 { _('PORTFOLIO_DIST') }", expanded=False):
            pie_data = [{"Activo": _('CASH'), "Valor": available_usdt}]
            for item in snapshot.get("pie_data") or []:
                if item.get("Activo") == "CASH":
                    continue
                pie_data.append({"Activo": item.get("Activo"), "Valor": item.get("Valor")})
            fig_pie = px.pie(pd.DataFrame(pie_data), values='Valor', names='Activo', hole=0.6, color_discrete_sequence=['#008A63', '#3A86FF', '#C026D3'])
            apply_plotly_theme(fig_pie)
            st.plotly_chart(fig_pie, width='stretch')

    with c_radar:
        with st.expander(f"🛰️ { _('OPPORTUNITY_RADAR') }", expanded=False):
            for item in snapshot.get("radar_data") or []:
                chg = float(item['Cambio'] or 0)
                c_color = "var(--iv-accent)" if chg >= 0 else "var(--iv-danger)"
                st.markdown(
                    f'<div class="radar-item"><span>{item["Moneda"]}</span>'
                    f'<span style="color:{c_color}; font-weight:bold;">{chg:.2f}%</span></div>',
                    unsafe_allow_html=True,
                )

    # BOTÓN DE EMERGENCIA
    st.markdown("---")
    with st.expander(f"⚠️ { _('EMERGENCY_ACTIONS') }", expanded=False):
        if st.button(_('SELL_ALL_USDT'), width="stretch", type="primary"):
            liquidate_all_to_usdt(db, exchange)
            exchange.invalidate_ui_cache()
            invalidate_snapshot("dashboard")
            st.rerun()
