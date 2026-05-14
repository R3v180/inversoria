import streamlit as st
import pandas as pd
import plotly.express as px
import os

def render_history():
    st.title("🧾 Historial y Analítica")
    
    if 'db' not in st.session_state:
        st.warning("Base de datos no inicializada.")
        return
        
    df = st.session_state.db.get_trades_history()
    if df.empty:
        st.info("El historial está vacío.")
        return
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Cálculos de Métricas Pro (Sincronización v2.3)
    ventas = df[df['Side'] == 'sell'].copy()
    total_trades = len(ventas)
    ganadores = len(ventas[ventas['PnL_%'] > 0])
    win_rate = (ganadores / total_trades * 100) if total_trades > 0 else 0
    
    profit_sum = ventas[ventas['PnL_%'] > 0]['PnL_%'].sum()
    loss_sum = abs(ventas[ventas['PnL_%'] <= 0]['PnL_%'].sum())
    profit_factor = (profit_sum / loss_sum) if loss_sum > 0 else (profit_sum if profit_sum > 0 else 0)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Win Rate", f"{win_rate:.1f}%")
    c2.metric("Profit Factor", f"{profit_factor:.2f}")
    c3.metric("Trades Cerrados", total_trades)
    c4.metric("Mejor Trade", f"{ventas['PnL_%'].max() if not ventas.empty else 0:.2f}%")
    
    st.markdown("---")
    
    st.subheader("Curva de Evolución (Trades Completados)")
    
    ventas = df[df['Side'] == 'sell'].copy()
    if not ventas.empty:
        # Calcular PNL aproximado en USD basado en el % y el capital invertido (price * amount de venta)
        # Esto es una aproximación para la visualización.
        ventas['pnl_usd'] = (ventas['Price'] * ventas['Amount']) * (ventas['Pnl_Pct'] / 100)
        ventas['pnl_acumulado'] = ventas['pnl_usd'].cumsum()
        
        fig = px.line(ventas, x='Date', y='pnl_acumulado', title="P&L Acumulado (USD)", markers=True)
        # Dar color verde si es positivo, rojo si es negativo
        color = "#00FFAA" if ventas['pnl_acumulado'].iloc[-1] >= 0 else "#FF4444"
        fig.update_traces(line_color=color, line_width=3, marker=dict(size=8))
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
    else:
        st.write("Aún no hay ventas registradas para generar la curva de equidad.")
        
    st.markdown("---")
    st.subheader("Diario de Trading")
    
    # Tarjetas Expandibles (Trade Cards)
    for index, row in df.sort_values(by='Date', ascending=False).iterrows():
        action_color = "🟢" if row['Side'] == 'buy' else "🔴"
        action_text = "COMPRA" if row['Side'] == 'buy' else "VENTA"
        pnl_text = f" | PNL: {row.get('Pnl_Pct', 0):.2f}%" if row['Side'] == 'sell' else ""
        
        with st.expander(f"{action_color} {action_text} | {row['Date'].strftime('%Y-%m-%d %H:%M')} | {row['Symbol']} a ${row['Price']:.4f}{pnl_text}"):
            st.markdown(f"**Cantidad:** {row['Amount']:.6f}")
            st.markdown(f"**Justificación de la Operación:**")
            st.info(row['Reason'])
