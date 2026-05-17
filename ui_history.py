import streamlit as st
import pandas as pd
import plotly.express as px
from i18n import _

def render_history():
    st.title(f"🧾 { _('NAV_HISTORY') }")
    
    if 'db' not in st.session_state:
        st.warning(_('DB_NOT_INIT'))
        return
        
    df = st.session_state.db.get_trades_history()
    if df.empty:
        st.info(_('HISTORY_EMPTY'))
        return
    df['Date'] = pd.to_datetime(df['Date'])
    pnl_col = 'PnL_%' if 'PnL_%' in df.columns else 'Pnl_Pct' if 'Pnl_Pct' in df.columns else None
    if pnl_col is None:
        df['PnL_%'] = 0.0
        pnl_col = 'PnL_%'
    df[pnl_col] = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0.0)
    
    # Cálculos de Métricas Pro (Sincronización v2.3)
    ventas = df[df['Side'] == 'sell'].copy()
    total_trades = len(ventas)
    ganadores = len(ventas[ventas[pnl_col] > 0])
    win_rate = (ganadores / total_trades * 100) if total_trades > 0 else 0
    
    profit_sum = ventas[ventas[pnl_col] > 0][pnl_col].sum()
    loss_sum = abs(ventas[ventas[pnl_col] <= 0][pnl_col].sum())
    profit_factor = (profit_sum / loss_sum) if loss_sum > 0 else (profit_sum if profit_sum > 0 else 0)
    expectancy = ventas[pnl_col].mean() if total_trades > 0 else 0.0
    rolling_pf = 0.0
    if total_trades > 0:
        rolling = ventas.tail(30)
        rolling_profit = rolling[rolling[pnl_col] > 0][pnl_col].sum()
        rolling_loss = abs(rolling[rolling[pnl_col] <= 0][pnl_col].sum())
        rolling_pf = (rolling_profit / rolling_loss) if rolling_loss > 0 else (rolling_profit if rolling_profit > 0 else 0)
    rolling_dd = 0.0
    try:
        eq = st.session_state.db.get_equity_history(limit=500)
        if not eq.empty:
            eq['total_value'] = pd.to_numeric(eq['total_value'], errors='coerce')
            roll_max = eq['total_value'].cummax()
            dd = ((eq['total_value'] - roll_max) / roll_max * 100).fillna(0)
            rolling_dd = dd.min()
    except Exception:
        rolling_dd = 0.0
    
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Win Rate", f"{win_rate:.1f}%")
    c2.metric("Profit Factor", f"{profit_factor:.2f}")
    c3.metric(_('TRADES_CLOSED'), total_trades)
    c4.metric(_('BEST_TRADE'), f"{ventas[pnl_col].max() if not ventas.empty else 0:.2f}%")
    c5.metric("Expectancy", f"{expectancy:.2f}%")
    c6.metric("Rolling DD", f"{rolling_dd:.2f}%")

    st.caption(f"Rolling PF últimos 30 cierres: {rolling_pf:.2f}")
    try:
        metrics = st.session_state.db.get_decision_metrics(limit=500)
        provider_stats = metrics.get("provider_stats")
        regime_stats = metrics.get("regime_stats")
        if provider_stats is not None and not provider_stats.empty:
            st.markdown("#### Provider / estrategia real")
            st.dataframe(provider_stats, width="stretch", hide_index=True)
        if regime_stats is not None and not regime_stats.empty:
            st.markdown("#### Régimen")
            st.dataframe(regime_stats, width="stretch", hide_index=True)
        if metrics.get("total_decisions", 0):
            st.caption(
                f"Journal: {metrics.get('total_decisions', 0)} decisiones · "
                f"BUY ejecutadas {metrics.get('accepted_buys', 0)} · "
                f"IA alineada {metrics.get('ai_alignment_pct', 0):.1f}%"
            )
    except Exception:
        pass
    
    st.markdown("---")
    st.subheader(_('EVOLUTION_CURVE'))
    
    ventas = df[df['Side'] == 'sell'].copy()
    if not ventas.empty:
        # Calcular PNL aproximado en USD basado en el % y el capital invertido (price * amount de venta)
        # Esto es una aproximación para la visualización.
        ventas['pnl_usd'] = (ventas['Price'] * ventas['Amount']) * (ventas[pnl_col] / 100)
        ventas['pnl_acumulado'] = ventas['pnl_usd'].cumsum()
        
        fig = px.line(ventas, x='Date', y='pnl_acumulado', title="P&L Acumulado (USD)", markers=True)
        # Dar color verde si es positivo, rojo si es negativo
        color = "#00FFAA" if ventas['pnl_acumulado'].iloc[-1] >= 0 else "#FF4444"
        fig.update_traces(line_color=color, line_width=3, marker=dict(size=8))
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
    else:
        st.write(_('NO_TRADES_MSG'))
        
    st.markdown("---")
    st.subheader(_('TRADING_JOURNAL'))
    
    # Tarjetas Expandibles (Trade Cards)
    for index, row in df.sort_values(by='Date', ascending=False).iterrows():
        action_color = "🟢" if row['Side'] == 'buy' else "🔴"
        action_text = _('BUY') if row['Side'] == 'buy' else _('SELL')
        pnl_text = f" | PNL: {row.get(pnl_col, 0):.2f}%" if row['Side'] == 'sell' else ""
        
        with st.expander(f"{action_color} {action_text} | {row['Date'].strftime('%Y-%m-%d %H:%M')} | {row['Symbol']} a ${row['Price']:.4f}{pnl_text}"):
            st.markdown(f"**Cantidad:** {row['Amount']:.6f}")
            st.markdown(f"**Justificación de la Operación:**")
            st.info(row['Reason'])
