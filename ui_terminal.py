import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas_ta as ta
from config import SYMBOLS

def render_terminal():
    st.markdown("""
        <style>
        .stSelectbox div[data-baseweb="select"] {
            background-color: #161B22;
            border-radius: 8px;
        }
        .log-container {
            height:300px;
            overflow-y:auto;
            background-color:#0D1117;
            padding:15px;
            border-radius:8px;
            border: 1px solid #30363D;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
        }
        </style>
    """, unsafe_allow_html=True)
    st.title("⚡ Terminal de Trading")
    
    # Interruptor de auto-refresco (v3.5)
    col_t1, col_t2 = st.columns([4, 1])
    with col_t2:
        terminal_refresh = st.toggle("Auto-Refresco", value=st.session_state.get('terminal_refresh', False))
        st.session_state.terminal_refresh = terminal_refresh

    if 'exchange' not in st.session_state:
        st.warning("El bot no está inicializado.")
        return

    # Cargar monedas del radar dinámico (v3.5)
    saved_watchlist = st.session_state.db.get_system_status('dynamic_watchlist')
    if saved_watchlist:
        current_symbols = [s.strip() for s in saved_watchlist.split(',') if s.strip()]
    else:
        current_symbols = SYMBOLS

    # Determinar moneda con más inversión para el default (v4.5)
    open_positions = st.session_state.db.get_open_positions()
    default_index = 0
    if open_positions:
        max_value = -1
        max_symbol = current_symbols[0]
        for sym, pos in open_positions.items():
            price = st.session_state.exchange.get_ticker(sym) or pos['entry_price']
            value = pos['amount'] * price
            if value > max_value:
                max_value = value
                max_symbol = sym
        
        if max_symbol in current_symbols:
            default_index = current_symbols.index(max_symbol)

    # Selector de activo con default inteligente
    symbol = st.selectbox("Seleccionar Activo", current_symbols, index=default_index)
    
    col_chart, col_ai = st.columns([3, 1])
    
    with col_chart:
        st.subheader(f"Análisis Técnico: {symbol}")
        with st.spinner("Cargando datos históricos..."):
            ohlcv = st.session_state.exchange.get_historical_data(symbol, limit=300)
            if not ohlcv:
                st.error("No se pudieron cargar datos históricos.")
                return
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['close'] = pd.to_numeric(df['close'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            
            # Calcular indicadores para el gráfico
            df['EMA_50'] = ta.ema(df['close'], length=50)
            df['EMA_200'] = ta.ema(df['close'], length=200)
            df['RSI_14'] = ta.rsi(df['close'], length=14)
            df['ATR_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            
            # Filtrar para no mostrar las 300 velas, solo las últimas 100 para mejor visibilidad
            df = df.tail(100)
            
            # Crear Subplots
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03,
                                row_heights=[0.6, 0.2, 0.2])
                                
            # Velas
            fig.add_trace(go.Candlestick(x=df.index,
                                        open=df['open'], high=df['high'],
                                        low=df['low'], close=df['close'],
                                        name='Precio'), row=1, col=1)
                                        
            # EMAs
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=1.5), name='EMA 50'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(color='white', width=2), name='EMA 200'), row=1, col=1)
            
            # RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI_14'], line=dict(color='purple', width=1.5), name='RSI 14'), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
            
            # ATR
            fig.add_trace(go.Scatter(x=df.index, y=df['ATR_14'], line=dict(color='cyan', width=1.5), name='ATR 14'), row=3, col=1)
            
            fig.update_layout(height=700, margin=dict(l=0, r=0, t=30, b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              xaxis_rangeslider_visible=False)
                              
            fig.update_yaxes(title_text="Precio", row=1, col=1)
            fig.update_yaxes(title_text="RSI", row=2, col=1)
            fig.update_yaxes(title_text="ATR", row=3, col=1)
            
            st.plotly_chart(fig, width="stretch")
            
    with col_ai:
        st.subheader("🤖 Consola IA")
        st.markdown("---")
        
        # Cargar decisión específica para el símbolo seleccionado (Sincronización v2.3)
        last_decision_raw = st.session_state.db.get_system_status(f'decision_{symbol}', '{}')
        try:
            decision = json.loads(last_decision_raw)
        except:
            decision = {}

        last_reason = decision.get('reasoning', 'Sin análisis específico para este activo aún.')
        
        if decision:
            with st.container(border=True):
                st.markdown(f"**🎯 Régimen:** `{decision.get('regime', 'N/A')}`")
                st.markdown(f"**🧠 Estrategia:** `{decision.get('best_strategy', 'N/A')}`")
                conf = decision.get('confidence', 0)
                st.progress(conf, text=f"Confianza: {conf*100:.0f}%")
        
        with st.container(border=True):
            st.caption(f"Última interpretación ({symbol}):")
            st.write(last_reason)
            
        st.markdown("---")
        st.markdown("**Registro de Operaciones (Live):**")
        
        log_html = "<div class='log-container'>"
        raw_logs = st.session_state.db.get_logs()
        logs_to_show = [l for l in raw_logs if "Escaneo" not in l and "Ciclo" not in l][-20:]
        for log in logs_to_show:
            log_html += f"<span style='color:#00FFAA;'>>></span> <span style='color:#D4D4D4;'>{log}</span><br/>"
        log_html += "</div>"
        
        st.markdown(log_html, unsafe_allow_html=True)
