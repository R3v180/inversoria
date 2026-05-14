import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import json
import pandas_ta as ta
from config import PRESUPUESTO_INICIAL, SYMBOLS, get_effective_max_positions

def render_dashboard():
    # Estilos CSS Avanzados
    st.markdown("""
        <style>
        .main { background-color: #0E1117; }
        .stMetric { background-color: #161B22; padding: 15px; border-radius: 10px; border: 1px solid #30363D; }
        .position-card { background-color: #161B22; padding: 20px; border-radius: 12px; border: 1px solid #30363D; margin-bottom: 10px; }
        .ai-card { background-color: #0D1117; border-left: 5px solid #00FFAA; padding: 20px; border-radius: 0 12px 12px 0; border: 1px solid #30363D; }
        .log-box { height: 180px; overflow-y: auto; background-color: #0D1117; padding: 10px; border-radius: 8px; border: 1px solid #30363D; font-family: monospace; font-size: 0.8em; }
        .radar-item { display: flex; justify-content: space-between; padding: 8px; border-bottom: 1px solid #30363D; font-size: 0.9em; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🏛️ Terminal InversorIA")
    
    db = st.session_state.db
    exchange = st.session_state.exchange

    # --- DATOS ---
    available_usdt = exchange.get_usdt_balance()
    total_value = exchange.get_balance()
    
    saved_watchlist = db.get_system_status('dynamic_watchlist')
    current_symbols = [s.strip() for s in saved_watchlist.split(',') if s.strip()] if saved_watchlist else SYMBOLS

    portfolio = {}
    if exchange.modo_simulacion:
        # Modo simulación: leer el portfolio virtual
        virtual = exchange.get_virtual_portfolio()
        for sym, amount in virtual.items():
            if amount > 0:
                portfolio[sym] = amount
    else:
        # Modo real: leer balances del exchange
        try:
            raw_balances = exchange.exchange.fetch_balance()['free']
            for coin, amount in raw_balances.items():
                if amount > 0 and coin not in ['USDT', 'USD']:
                    portfolio[f"{coin}/USDT"] = amount
        except Exception as e:
            st.warning(f"No se pudo obtener el balance real: {e}")

    # Baseline para el cálculo de PnL (Presupuesto inicial de config o Saldo inicial real)
    baseline = PRESUPUESTO_INICIAL
    if not exchange.modo_simulacion:
        real_start = db.get_system_status('real_start_balance')
        if real_start:
            baseline = float(real_start)

    pnl = total_value - baseline
    pnl_pct = (pnl / baseline) * 100 if baseline else 0
    open_positions = db.get_open_positions()

    from i18n import _, TRANSLATIONS
    # --- TOP METRICS ---
    dynamic_max = get_effective_max_positions(total_value)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(_('EQUITY_TOTAL'), f"${total_value:.2f}", f"{pnl_pct:.2f}%")
    m2.metric(_('AVAILABLE'), f"${available_usdt:.2f}")
    m3.metric(_('POSITIONS'), f"{len(open_positions)} / {dynamic_max}")
    m4.metric(_('PNL_USD'), f"${pnl:.2f}", f"{pnl_pct:.2f}%")

    # --- COMMAND CENTER ---
    col_equity, col_market = st.columns([1, 1.2])

    with col_equity:
        st.markdown(f"### 📈 { _('EQUITY_CHART') }")
        equity_df = db.get_equity_history(limit=500)
        if not equity_df.empty:
            fig_equity = go.Figure()
            fig_equity.add_trace(go.Scatter(x=equity_df['timestamp'], y=equity_df['total_value'], fill='tozeroy', fillcolor='rgba(0, 255, 170, 0.1)', line=dict(color='#00FFAA', width=3)))
            fig_equity.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#30363D'))
            st.plotly_chart(fig_equity, width='stretch')

    with col_market:
        c1, c2 = st.columns([2, 1])
        with c1: st.markdown(f"### 🕯️ { _('MARKET_CHART') }")
        
        if "selected_chart_symbol" not in st.session_state:
            # Por defecto: la posición con más inversión (v7.9)
            default_sym = current_symbols[0] if current_symbols else "BTC/USDT"
            if open_positions:
                max_v = -1
                for s, p in open_positions.items():
                    price = exchange.get_ticker(s) or p['entry_price']
                    val = p['amount'] * price
                    if val > max_v:
                        max_v = val
                        default_sym = s
            st.session_state.selected_chart_symbol = default_sym
        if st.session_state.selected_chart_symbol not in current_symbols:
            current_symbols.insert(0, st.session_state.selected_chart_symbol)
            
        with c2: selected_sym = st.selectbox("Activo", current_symbols, key="selected_chart_symbol", label_visibility="collapsed")

        
        ohlcv = exchange.get_historical_data(selected_sym, limit=150)
        if ohlcv:
            df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            df['c'] = pd.to_numeric(df['c'])
            df['EMA_50'] = ta.ema(df['c'], length=50)
            df['EMA_200'] = ta.ema(df['c'], length=200)
            df['RSI_14'] = ta.rsi(df['c'], length=14)
            df['ATR_14'] = ta.atr(pd.to_numeric(df['h']), pd.to_numeric(df['l']), df['c'], length=14)
            
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.5, 0.25, 0.25])
            fig.add_trace(go.Candlestick(x=df['ts'], open=df['o'], high=df['h'], low=df['l'], close=df['c'], name="Price"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['ts'], y=df['EMA_50'], line=dict(color='orange', width=1), name="EMA50"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['ts'], y=df['EMA_200'], line=dict(color='white', width=1.5), name="EMA200"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['ts'], y=df['RSI_14'], line=dict(color='purple', width=1), name="RSI"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df['ts'], y=df['ATR_14'], line=dict(color='cyan', width=1), name="ATR"), row=3, col=1)
            fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, width='stretch')

    # --- LOWER SECTION ---
    col_left, col_right = st.columns([1.5, 1])

    with col_left:
        st.markdown(f"### 💼 { _('ACTIVE_POSITIONS') }")
        if open_positions:
            for sym, pos in open_positions.items():
                current_price = exchange.get_ticker(sym) or pos['entry_price']
                u_pnl = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                color = "#00FFAA" if u_pnl >= 0 else "#FF4444"
                current_value = pos.get('amount', 0) * current_price
                with st.container():
                    safe_key = sym.replace("/", "_").replace(" ", "_")
                    col_info, col_chart, col_sell = st.columns([4.2, 0.9, 0.9])
                    with col_info:
                        st.markdown(f'<div class="position-card" style="margin-bottom: 5px; padding: 15px;"><div style="display:flex; justify-content:space-between;"><div><b>{sym}</b><br/><span style="color:gray; font-size:0.8em;">{ _("INVESTMENT") }: ${current_value:.2f}</span></div><div style="text-align:right;"><span style="font-size:1.2em; font-weight:bold; color:{color};">{u_pnl:.2f}%</span><br/><span style="font-size:0.8em;">${current_price:.4f}</span></div></div></div>', unsafe_allow_html=True)
                    with col_chart:
                        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

                        def update_chart_symbol(s=sym):
                            st.session_state.selected_chart_symbol = s

                        st.button("📈", key=f"btn_chart_{safe_key}", help=f"Ver gráfico de {sym}", on_click=update_chart_symbol)
                    with col_sell:
                        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                        if st.button(
                            _('MANUAL_SELL'),
                            key=f"btn_sell_{safe_key}",
                            help=_('MANUAL_SELL_HELP'),
                            type="secondary",
                        ):
                            amt = float(pos.get("amount") or 0)
                            if amt <= 0:
                                st.error(_('MANUAL_SELL_FAIL'))
                            else:
                                res = exchange.execute_order(sym, "sell", amt, current_price)
                                if res.get("status") in ("closed", "simulated"):
                                    exit_p = res.get("average") or res.get("price") or current_price
                                    try:
                                        exit_p = float(exit_p)
                                    except (TypeError, ValueError):
                                        exit_p = float(current_price)
                                    reason = _("MANUAL_SELL_REASON")
                                    try:
                                        sold = float(res.get("filled") or 0)
                                    except (TypeError, ValueError):
                                        sold = 0.0
                                    if sold <= 0:
                                        sold = float(res.get("amount") or amt)
                                    sold = min(sold, amt)
                                    if db.close_position(sym, exit_p, reason, sold_amount=sold):
                                        db.add_log(f"{reason}: {sym} @ {exit_p:.6f}")
                                        st.success(_("MANUAL_SELL_OK"))
                                        st.rerun()
                                    else:
                                        st.warning(_("MANUAL_SELL_FAIL"))
                                else:
                                    err = res.get("reason", str(res))
                                    st.error(f"{_('MANUAL_SELL_FAIL')}: {err}")
        else: st.info(_('NO_POSITIONS'))

    with col_right:
        st.markdown(f"### 🤖 { _('ASSISTANT_TITLE') } & Logs")
        last_decision_raw = db.get_system_status('last_ia_decision', '{}')
        try:
            decision = json.loads(last_decision_raw)
            if decision:
                st.markdown(f'<div class="ai-card"><b>{decision.get("symbol", "N/A")}</b> | <span style="color:#00FFAA;">{decision.get("regime", "N/A")}</span><p style="font-size:0.85em; margin-top:5px;">{decision.get("reasoning", "")[:100]}...</p></div>', unsafe_allow_html=True)
        except: pass
        
        st.markdown("<br/>", unsafe_allow_html=True)
        raw_logs = db.get_logs()
        important_logs = [l for l in raw_logs if "Escaneo" not in l and "Ciclo" not in l][-15:]
        log_content = "".join([f"<span style='color:#00FFAA;'>>></span> {l}<br/>" for l in important_logs])
        st.markdown(f'<div class="log-box">{log_content}</div>', unsafe_allow_html=True)

    # --- FINAL SECTION: PIE + RADAR ---
    st.markdown("---")
    c_pie, c_radar = st.columns([1, 1])
    
    with c_pie:
        with st.expander(f"🥧 { _('PORTFOLIO_DIST') }", expanded=True):
            pie_data = [{"Activo": _('CASH'), "Valor": available_usdt}]
            for sym, amt in portfolio.items():
                p = exchange.get_ticker(sym)
                if p: pie_data.append({"Activo": sym, "Valor": amt * p})
            st.plotly_chart(px.pie(pd.DataFrame(pie_data), values='Valor', names='Activo', hole=0.6, color_discrete_sequence=['#00FFAA', '#3A86FF', '#FF006E']), width='stretch')

    with c_radar:
        with st.expander(f"🛰️ { _('OPPORTUNITY_RADAR') }", expanded=True):
            radar_data = []
            for sym in current_symbols[:8]: # Top 8 del radar
                stats = exchange.get_market_stats(sym)
                change = stats.get('change_24h', 0)
                radar_data.append({"Moneda": sym, "Cambio": change})
            
            # Ordenar por cambio
            radar_data = sorted(radar_data, key=lambda x: x['Cambio'] or 0, reverse=True)
            for item in radar_data:
                c_color = "#00FFAA" if (item['Cambio'] or 0) >= 0 else "#FF4444"
                st.markdown(f'<div class="radar-item"><span>{item["Moneda"]}</span><span style="color:{c_color}; font-weight:bold;">{item["Cambio"]:.2f}%</span></div>', unsafe_allow_html=True)

    # --- PANEL DE INTELIGENCIA ---
    st.markdown("---")
    st.markdown(f"### 🧠 { _('SYSTEM_INTEL') }")

    col_macro, col_backtest = st.columns(2)

    with col_macro:
        with st.expander(f"🌍 { _('MACRO_CONTEXT') }", expanded=True):
            macro_raw = db.get_system_status('macro_context', '{}')
            try:
                macro = json.loads(macro_raw)
                if macro:
                    regime = macro.get('macro_regime', 'N/A')
                    regime_color = {
                        'RISK_ON': '#00FFAA', 'ALTSEASON': '#00FFAA',
                        'NEUTRAL': '#FFD700', 'CAUTION': '#FF8C00',
                        'RISK_OFF': '#FF4444'
                    }.get(regime, '#888888')

                    st.markdown(
                        f"<div style='text-align:center; padding:10px; border-radius:8px; "
                        f"background:#1E1E1E; color:{regime_color}; font-size:1.2em; "
                        f"font-weight:bold;'>{ _('REGIME_LABEL') }: {regime}</div>",
                        unsafe_allow_html=True
                    )
                    st.metric(_('BTC_DOM'), f"{macro.get('btc_dominance', 0):.1f}%")
                    st.metric(_('MARKET_CAP'), f"{macro.get('market_cap_change_24h', 0):+.2f}%")
                    st.metric(_('LEADING_SECTOR'), macro.get('leading_sector', 'N/A').upper())
                    
                    # Mostrar datos de Alpha Vantage v6.0
                    st.markdown("---")
                    st.markdown(f"**{ _('GLOBAL_TITLE') }**")
                    macro_db = db.get_all_macro_data()
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
                        st.caption("Cargando indicadores Alpha Vantage...")
                else:
                    st.info("Contexto macro pendiente (próxima actualización en el siguiente ciclo)")
            except Exception:
                st.info("Cargando contexto macro...")

    with col_backtest:
        with st.expander(f"📊 { _('BACKTEST_STATUS') }", expanded=True):
            try:
                import sqlite3
                import os
                base_dir = os.path.dirname(os.path.abspath(__file__))
                db_path = os.path.join(base_dir, "iversoria.db")
                with sqlite3.connect(db_path, timeout=5) as conn:
                    conn.row_factory = sqlite3.Row
                    runs = conn.execute(
                        'SELECT * FROM backtest_runs ORDER BY run_timestamp DESC LIMIT 5'
                    ).fetchall()

                    if runs:
                        for run in runs:
                            st.markdown(
                                f"**{run['symbol']}** · {run['timeframe']} · "
                                f"WR {run['win_rate']:.0%} · "
                                f"{ _('BEST_STRATEGY') }: {run['best_strategy']}"
                            )
                    else:
                        st.info(_('NO_BACKTEST_DATA'))
            except Exception as e:
                st.info(f"Backtest no disponible: {e}")

    # BOTÓN DE EMERGENCIA
    st.markdown("---")
    with st.expander(f"⚠️ { _('EMERGENCY_ACTIONS') }", expanded=False):
        if st.button(_('SELL_ALL_USDT'), width="stretch", type="primary"):
            exchange.liquidate_all_to_usdt()
            db.clear_open_positions()
            st.rerun()
