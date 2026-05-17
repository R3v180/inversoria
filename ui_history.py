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
    df['Side'] = df['Side'].astype(str).str.lower()
    df['Symbol'] = df['Symbol'].astype(str)

    with st.expander("Filtros y paginación", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        symbols = ["Todos"] + sorted(df['Symbol'].dropna().unique().tolist())
        selected_symbol = f1.selectbox("Símbolo", symbols, key="hist_symbol")
        selected_side = f2.selectbox("Tipo", ["Todos", "buy", "sell"], key="hist_side")
        result_filter = f3.selectbox("Resultado", ["Todos", "Ganadoras", "Perdedoras / break-even"], key="hist_result")
        page_size = int(f4.selectbox("Por página", [25, 50, 100, 250, 500], index=1, key="hist_page_size"))

        d1, d2, d3 = st.columns([1, 1, 2])
        min_date = df['Date'].min().date()
        max_date = df['Date'].max().date()
        start_date = d1.date_input("Desde", min_date, min_value=min_date, max_value=max_date, key="hist_start")
        end_date = d2.date_input("Hasta", max_date, min_value=min_date, max_value=max_date, key="hist_end")
        metrics_scope = d3.radio(
            "Métricas",
            ["Histórico completo", "Solo filtro actual"],
            horizontal=True,
            key="hist_metrics_scope",
        )

    filtered = df.copy()
    filtered = filtered[
        (filtered['Date'].dt.date >= start_date)
        & (filtered['Date'].dt.date <= end_date)
    ]
    if selected_symbol != "Todos":
        filtered = filtered[filtered['Symbol'] == selected_symbol]
    if selected_side != "Todos":
        filtered = filtered[filtered['Side'] == selected_side]
    if result_filter == "Ganadoras":
        filtered = filtered[(filtered['Side'] == 'sell') & (filtered[pnl_col] > 0)]
    elif result_filter == "Perdedoras / break-even":
        filtered = filtered[(filtered['Side'] == 'sell') & (filtered[pnl_col] <= 0)]

    metric_df = filtered if metrics_scope == "Solo filtro actual" else df
    if filtered.empty:
        st.warning("No hay operaciones para los filtros seleccionados.")
        return
    
    # Cálculos de Métricas Pro (Sincronización v2.3)
    ventas = metric_df[metric_df['Side'] == 'sell'].copy()
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
        edge = st.session_state.db.get_adaptive_edge_snapshot(limit=1000, min_trades=5)
        if edge.get("enabled") and edge.get("global"):
            g = edge.get("global", {})
            st.caption(
                f"Adaptive edge: expectancy {g.get('expectancy_pct', 0):.2f}% · "
                f"PF {g.get('profit_factor', 0):.2f} · ajuste base {g.get('adjustment', 0):+.3f} · "
                f"decay {edge.get('edge_decay_pct', 0):+.2f}%"
            )
    except Exception:
        pass
    
    st.markdown("---")
    st.subheader(_('EVOLUTION_CURVE'))
    
    ventas = metric_df[metric_df['Side'] == 'sell'].copy()
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
    
    sorted_df = filtered.sort_values(by='Date', ascending=False).reset_index(drop=True)
    total_rows = len(sorted_df)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    current_page = int(st.number_input(
        "Página",
        min_value=1,
        max_value=total_pages,
        value=min(int(st.session_state.get("hist_page", 1)), total_pages),
        step=1,
        key="hist_page",
    ))
    start_idx = (current_page - 1) * page_size
    end_idx = start_idx + page_size
    page_df = sorted_df.iloc[start_idx:end_idx]
    st.caption(f"Mostrando {start_idx + 1}-{min(end_idx, total_rows)} de {total_rows} operaciones filtradas.")

    compact = page_df.copy()
    compact['Date'] = compact['Date'].dt.strftime('%Y-%m-%d %H:%M')
    st.dataframe(
        compact[['Date', 'Symbol', 'Side', 'Price', 'Amount', pnl_col, 'Reason']],
        width="stretch",
        hide_index=True,
    )

    show_cards = st.toggle("Mostrar tarjetas detalladas de esta página", value=total_rows <= 50, key="hist_show_cards")
    if not show_cards:
        return

    # Tarjetas Expandibles (solo página actual)
    for index, row in page_df.iterrows():
        action_color = "🟢" if row['Side'] == 'buy' else "🔴"
        action_text = _('BUY') if row['Side'] == 'buy' else _('SELL')
        pnl_text = f" | PNL: {row.get(pnl_col, 0):.2f}%" if row['Side'] == 'sell' else ""
        
        with st.expander(f"{action_color} {action_text} | {row['Date'].strftime('%Y-%m-%d %H:%M')} | {row['Symbol']} a ${row['Price']:.4f}{pnl_text}"):
            st.markdown(f"**Cantidad:** {row['Amount']:.6f}")
            st.markdown(f"**Justificación de la Operación:**")
            st.info(row['Reason'])
