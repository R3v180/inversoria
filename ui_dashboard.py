import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import json
import pandas_ta as ta
from config import PRESUPUESTO_INICIAL, MAX_OPEN_POSITIONS, SYMBOLS

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

    st.title("🏛️ Terminal Iversoria")
    
    db = st.session_state.db
    exchange = st.session_state.exchange

    # --- DATOS ---
    balance = exchange.get_balance()
    saved_watchlist = db.get_system_status('dynamic_watchlist')
    current_symbols = [s.strip() for s in saved_watchlist.split(',') if s.strip()] if saved_watchlist else SYMBOLS

    portfolio = {}
    if not exchange.modo_simulacion:
        try:
            raw_balances = exchange.exchange.fetch_balance()['free']
            for coin, amount in raw_balances.items():
                if amount > 0 and coin not in ['USDT', 'USD']:
                    portfolio[f"{coin}/USDT"] = amount
        except: pass

    total_value = balance
    for sym, amt in portfolio.items():
        price = exchange.get_ticker(sym)
        if price: total_value += amt * price
            
    pnl = total_value - PRESUPUESTO_INICIAL
    pnl_pct = (pnl / PRESUPUESTO_INICIAL) * 100 if PRESUPUESTO_INICIAL else 0
    open_positions = db.get_open_positions()

    # --- TOP METRICS ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Equity Total", f"${total_value:.2f}", f"{pnl_pct:.2f}%")
    m2.metric("Disponible", f"${balance:.2f}")
    m3.metric("Posiciones", f"{len(open_positions)} / {MAX_OPEN_POSITIONS}")
    m4.metric("PnL USD", f"${pnl:.2f}", f"{pnl_pct:.2f}%")

    # --- COMMAND CENTER ---
    col_equity, col_market = st.columns([1, 1.2])

    with col_equity:
        st.markdown("### 📈 Patrimonio")
        equity_df = db.get_equity_history(limit=500)
        if not equity_df.empty:
            fig_equity = go.Figure()
            fig_equity.add_trace(go.Scatter(x=equity_df['timestamp'], y=equity_df['total_value'], fill='tozeroy', fillcolor='rgba(0, 255, 170, 0.1)', line=dict(color='#00FFAA', width=3)))
            fig_equity.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#30363D'))
            st.plotly_chart(fig_equity, use_container_width=True)

    with col_market:
        c1, c2 = st.columns([2, 1])
        with c1: st.markdown("### 🕯️ Mercado")
        with c2: selected_sym = st.selectbox("Activo", current_symbols, label_visibility="collapsed")
        
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
            st.plotly_chart(fig, use_container_width=True)

    # --- LOWER SECTION ---
    col_left, col_right = st.columns([1.5, 1])

    with col_left:
        st.markdown("### 💼 Posiciones Activas")
        if open_positions:
            for sym, pos in open_positions.items():
                current_price = exchange.get_ticker(sym) or pos['entry_price']
                u_pnl = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                color = "#00FFAA" if u_pnl >= 0 else "#FF4444"
                current_value = pos.get('amount', 0) * current_price
                with st.container():
                    st.markdown(f'<div class="position-card"><div style="display:flex; justify-content:space-between;"><div><b>{sym}</b><br/><span style="color:gray; font-size:0.8em;">Inversión: ${current_value:.2f}</span></div><div style="text-align:right;"><span style="font-size:1.2em; font-weight:bold; color:{color};">{u_pnl:.2f}%</span><br/><span style="font-size:0.8em;">${current_price:.4f}</span></div></div></div>', unsafe_allow_html=True)
        else: st.info("Sin posiciones activas.")

    with col_right:
        st.markdown("### 🤖 IA & Logs")
        last_decision_raw = db.get_system_status('last_ia_decision', '{}')
        try:
            decision = json.loads(last_decision_raw)
            if decision:
                st.markdown(f'<div class="ai-card"><b>{decision.get("symbol", "N/A")}</b> | <span style="color:#00FFAA;">{decision.get("regime", "N/A")}</span><p style="font-size:0.85em; margin-top:5px;">{decision.get("reasoning", "")[:100]}...</p></div>', unsafe_allow_html=True)
        except: pass
        
        st.markdown("<br/>", unsafe_allow_html=True)
        logs = db.get_logs()[-15:]
        log_content = "".join([f"<span style='color:#00FFAA;'>>></span> {l}<br/>" for l in logs])
        st.markdown(f'<div class="log-box">{log_content}</div>', unsafe_allow_html=True)

    # --- FINAL SECTION: PIE + RADAR ---
    st.markdown("---")
    c_pie, c_radar = st.columns([1, 1])
    
    with c_pie:
        with st.expander("🥧 Distribución del Portfolio", expanded=True):
            pie_data = [{"Activo": "Liquidez", "Valor": balance}]
            for sym, amt in portfolio.items():
                p = exchange.get_ticker(sym)
                if p: pie_data.append({"Activo": sym, "Valor": amt * p})
            st.plotly_chart(px.pie(pd.DataFrame(pie_data), values='Valor', names='Activo', hole=0.6, color_discrete_sequence=['#00FFAA', '#3A86FF', '#FF006E']), use_container_width=True)

    with c_radar:
        with st.expander("🛰️ Radar de Oportunidades (Top 24h)", expanded=True):
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

    # BOTÓN DE EMERGENCIA
    st.markdown("---")
    with st.expander("⚠️ Acciones de Emergencia", expanded=False):
        if st.button("🔴 LIQUIDAR TODO A USDT", use_container_width=True, type="primary"):
            exchange.liquidate_all_to_usdt()
            db.clear_open_positions()
            st.rerun()
