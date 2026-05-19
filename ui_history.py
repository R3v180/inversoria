import streamlit as st
import pandas as pd
import plotly.express as px
import json
from datetime import datetime
from i18n import _
from ui_theme import apply_plotly_theme
from ui_services.performance_period import (
    PERFORMANCE_PRESETS,
    compute_period_performance,
    preset_start_datetime,
)
from ui_services.page_cache import install_page_autorefresh, page_cache_ttl, render_stale_while_revalidate


def _fmt_trade_price(value):
    try:
        price = float(value)
    except (TypeError, ValueError):
        return "-"
    if price == 0:
        return "0"
    if abs(price) < 0.0001:
        return f"{price:.10f}".rstrip("0").rstrip(".")
    if abs(price) < 1:
        return f"{price:.6f}".rstrip("0").rstrip(".")
    if abs(price) < 100:
        return f"{price:.4f}".rstrip("0").rstrip(".")
    return f"{price:.2f}"


def _fmt_trade_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    if amount == 0:
        return "0"
    if abs(amount) >= 1_000_000:
        return f"{amount:,.0f}"
    if abs(amount) >= 1:
        return f"{amount:,.6f}".rstrip("0").rstrip(".")
    return f"{amount:.10f}".rstrip("0").rstrip(".")


def _fmt_trade_value(price, amount):
    try:
        value = float(price) * float(amount)
    except (TypeError, ValueError):
        return "-"
    return f"${value:,.2f}"


def _parse_json_maybe(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _audit_rows_to_df(rows):
    df = pd.DataFrame(rows or [])
    if df.empty:
        return df
    if "timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
    for col in ("payload_json", "raw_json"):
        if col in df.columns:
            df[col] = df[col].apply(lambda raw: json.dumps(_parse_json_maybe(raw), ensure_ascii=False)[:1200])
    return df


def _render_audit_replay(db):
    with st.expander("Auditoría operativa y replay de ciclos", expanded=False):
        tab_events, tab_snapshots = st.tabs(["Audit events", "Cycle replay"])
        with tab_events:
            c1, c2, c3 = st.columns([1, 1, 2])
            limit = int(c1.selectbox("Eventos", [50, 100, 200, 500, 1000], index=2, key="audit_limit"))
            event_type = c2.text_input("Tipo evento", value="", key="audit_event_type").strip()
            symbol = c3.text_input("Símbolo", value="", key="audit_symbol").strip()
            try:
                rows = db.get_audit_events(limit=limit, event_type=event_type or None, symbol=symbol or None)
                df = _audit_rows_to_df(rows)
                if df.empty:
                    st.info("Sin audit events para esos filtros.")
                else:
                    cols = [c for c in ("date", "event_type", "symbol", "severity", "message", "payload_json") if c in df.columns]
                    st.dataframe(df[cols], width="stretch", hide_index=True)
            except Exception as exc:
                st.warning(f"No se pudieron cargar audit events: {exc}")

        with tab_snapshots:
            c1, c2 = st.columns([1, 3])
            limit = int(c1.selectbox("Snapshots", [25, 50, 100, 250, 500], index=2, key="replay_limit"))
            cycle_id = c2.text_input("Cycle ID", value="", key="replay_cycle_id").strip()
            try:
                rows = db.get_cycle_replay_snapshots(limit=limit, cycle_id=cycle_id or None)
                df = _audit_rows_to_df(rows)
                if df.empty:
                    st.info("Sin snapshots de ciclo para esos filtros.")
                else:
                    cols = [c for c in ("date", "cycle_id", "phase", "payload_json") if c in df.columns]
                    st.dataframe(df[cols], width="stretch", hide_index=True)
            except Exception as exc:
                st.warning(f"No se pudieron cargar snapshots: {exc}")


def _render_period_performance(db, exchange):
    st.markdown("### Rendimiento por periodo")
    st.caption("Calcula equity flotante desde una fecha/hora sin borrar ni alterar el histórico.")
    p1, p2, p3 = st.columns([1, 1, 2])
    preset = p1.selectbox("Periodo", PERFORMANCE_PRESETS, key="perf_period_preset")
    start_dt = preset_start_datetime(preset)
    if preset == "Personalizado":
        selected_date = p2.date_input("Desde fecha", value=datetime.now().date(), key="perf_period_date")
        selected_time = p3.time_input("Desde hora", value=datetime.min.time(), key="perf_period_time")
        start_dt = datetime.combine(selected_date, selected_time)
    else:
        p2.caption("Inicio")
        p2.write(start_dt.strftime("%Y-%m-%d %H:%M") if start_dt else "Primer dato disponible")

    current_equity = float(exchange.get_balance() or 0.0)
    perf = compute_period_performance(db, current_equity, start_dt)
    if not perf.get("ok"):
        st.info(perf.get("reason", "Sin datos de rendimiento."))
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equity inicio periodo", f"${perf['start_equity']:.2f}")
    c2.metric("Equity actual", f"${perf['current_equity']:.2f}")
    c3.metric("PnL periodo", f"${perf['pnl_usd']:+.2f}", f"{perf['pnl_pct']:+.2f}%")
    c4.metric("Puntos equity", perf.get("points", 0))
    st.caption(f"Inicio real usado: {pd.to_datetime(perf['start_ts']).strftime('%Y-%m-%d %H:%M:%S')}")

    curve = perf.get("period_df")
    if curve is not None and not curve.empty:
        fig = px.line(curve, x="timestamp", y="pnl_usd", title="PnL flotante del periodo", markers=True)
        apply_plotly_theme(fig)
        st.plotly_chart(fig, width="stretch")


def _open_position_context(db):
    try:
        positions = db.get_open_positions()
    except Exception:
        return {}
    context = {}
    for symbol, pos in positions.items():
        extra = _parse_json_maybe(pos.get("extra_data"))
        if extra:
            context[str(symbol)] = extra
    return context


def _journal_context(db):
    try:
        journal = db.get_decision_journal(limit=1000)
    except Exception:
        return pd.DataFrame()
    if journal is None or journal.empty:
        return pd.DataFrame()
    journal = journal.copy()
    if "timestamp" in journal.columns:
        journal["Date"] = pd.to_datetime(journal["timestamp"], unit="s", errors="coerce")
    return journal


def _match_journal(row, journal):
    if journal.empty or "symbol" not in journal.columns:
        return {}
    side = str(row.get("Side", "")).lower()
    symbol = str(row.get("Symbol", ""))
    candidates = journal[journal["symbol"].astype(str) == symbol].copy()
    if side == "buy" and "execution_side" in candidates.columns:
        candidates = candidates[candidates["execution_side"].fillna("").astype(str).str.lower().isin(["buy", ""])]
    elif side == "sell" and "execution_side" in candidates.columns:
        candidates = candidates[candidates["execution_side"].fillna("").astype(str).str.lower().isin(["sell", ""])]
    if candidates.empty:
        return {}
    if "Date" in candidates.columns:
        trade_date = row.get("Date")
        candidates["delta"] = (candidates["Date"] - trade_date).abs()
        candidates = candidates.sort_values("delta")
    return candidates.iloc[0].to_dict()


def _build_trade_context(row, open_context, journal):
    context = {}
    if str(row.get("Side", "")).lower() == "buy":
        context.update(open_context.get(str(row.get("Symbol", "")), {}))
    journal_row = _match_journal(row, journal)
    if journal_row:
        context.setdefault("provider", journal_row.get("provider"))
        context.setdefault("regime", journal_row.get("regime"))
        context.setdefault("best_strategy", journal_row.get("strategy"))
        context.setdefault("decision_score", journal_row.get("decision_score"))
        context.setdefault("confidence", journal_row.get("confidence"))
        context.setdefault("sizing", _parse_json_maybe(journal_row.get("sizing")))
    return {k: v for k, v in context.items() if v not in (None, "", {})}


def _short_reason(text, limit=140):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _display_reason(row, context):
    reasoning = context.get("reasoning") or row.get("Reason") or ""
    score = context.get("decision_score")
    confidence = context.get("confidence")
    regime = context.get("regime", "N/A")
    strategy = context.get("best_strategy", context.get("strategy", "N/A"))
    provider = context.get("provider", "")
    parts = []
    if provider:
        parts.append(str(provider))
    try:
        parts.append(f"score={float(score):.2f}")
    except (TypeError, ValueError):
        pass
    try:
        parts.append(f"conf={float(confidence):.2f}")
    except (TypeError, ValueError):
        pass
    if regime and regime != "N/A":
        parts.append(str(regime))
    if strategy and strategy != "N/A":
        parts.append(str(strategy))
    prefix = " | ".join(parts)
    reason = _short_reason(reasoning)
    return f"{prefix} | {reason}" if prefix and reason else reason or str(row.get("Reason", ""))


HISTORY_AUTO_REFRESH_SEC = 45


def render_history_page():
    install_page_autorefresh("history")

    def _build():
        db = st.session_state.db
        exchange = st.session_state.get("exchange")
        return {
            "trades_df": db.get_trades_history(),
            "has_exchange": exchange is not None,
        }

    def _render(data, stale=False, age_sec=0):
        render_history(data.get("trades_df"), stale=stale, age_sec=age_sec)

    render_stale_while_revalidate("history", _build, _render, ttl_sec=page_cache_ttl("history"))


def render_history(trades_df=None, *, stale=False, age_sec=0):
    st.title(f"🧾 { _('NAV_HISTORY') }")
    
    if 'db' not in st.session_state:
        st.warning(_('DB_NOT_INIT'))
        return

    st.caption(
        f"Auto-actualización cada {int(HISTORY_AUTO_REFRESH_SEC)}s "
        f"(trades/journal desde BD; rendimiento por periodo usa equity del exchange)."
    )
    if stale and age_sec is not None:
        remaining = max(0, int(HISTORY_AUTO_REFRESH_SEC - age_sec))
        st.caption(f"Datos de hace {int(age_sec)}s (caché). Actualización automática en ~{remaining}s.")

    if "exchange" in st.session_state:
        _render_period_performance(st.session_state.db, st.session_state.exchange)
    else:
        st.info("Exchange no inicializado; el rendimiento por periodo se mostrará cuando la sesión esté lista.")

    _render_audit_replay(st.session_state.db)

    df = trades_df if trades_df is not None else st.session_state.db.get_trades_history()
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

    with st.expander(_('HISTORY_FILTERS'), expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        all_label = _('HISTORY_ALL')
        symbols = [all_label] + sorted(df['Symbol'].dropna().unique().tolist())
        selected_symbol = f1.selectbox(_('HISTORY_SYMBOL'), symbols, key="hist_symbol")
        selected_side = f2.selectbox(_('HISTORY_TYPE'), [all_label, "buy", "sell"], key="hist_side")
        result_filter = f3.selectbox(_('HISTORY_RESULT'), [all_label, _('HISTORY_WINNERS'), _('HISTORY_LOSERS')], key="hist_result")
        page_size = int(f4.selectbox(_('HISTORY_PER_PAGE'), [25, 50, 100, 250, 500], index=1, key="hist_page_size"))

        d1, d2, d3 = st.columns([1, 1, 2])
        min_date = df['Date'].min().date()
        max_date = df['Date'].max().date()
        start_date = d1.date_input(_('HISTORY_FROM'), min_date, min_value=min_date, max_value=max_date, key="hist_start")
        end_date = d2.date_input(_('HISTORY_TO'), max_date, min_value=min_date, max_value=max_date, key="hist_end")
        metrics_scope = d3.radio(
            _('HISTORY_METRICS'),
            [_('HISTORY_FULL'), _('HISTORY_FILTER_ONLY')],
            horizontal=True,
            key="hist_metrics_scope",
        )

    filtered = df.copy()
    filtered = filtered[
        (filtered['Date'].dt.date >= start_date)
        & (filtered['Date'].dt.date <= end_date)
    ]
    if selected_symbol != all_label:
        filtered = filtered[filtered['Symbol'] == selected_symbol]
    if selected_side != all_label:
        filtered = filtered[filtered['Side'] == selected_side]
    if result_filter == _('HISTORY_WINNERS'):
        filtered = filtered[(filtered['Side'] == 'sell') & (filtered[pnl_col] > 0)]
    elif result_filter == _('HISTORY_LOSERS'):
        filtered = filtered[(filtered['Side'] == 'sell') & (filtered[pnl_col] <= 0)]

    metric_df = filtered if metrics_scope == _('HISTORY_FILTER_ONLY') else df
    if filtered.empty:
        st.warning(_('HISTORY_NO_FILTER_RESULTS'))
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

    st.caption(_('HISTORY_ROLLING_PF').format(f"{rolling_pf:.2f}"))
    if total_trades == 0:
        st.info(_('HISTORY_REALIZED_NOTE'))
    try:
        metrics = st.session_state.db.get_decision_metrics(limit=500)
        provider_stats = metrics.get("provider_stats")
        regime_stats = metrics.get("regime_stats")
        if provider_stats is not None and not provider_stats.empty:
            st.markdown(f"#### {_('HISTORY_PROVIDER_STRATEGY')}")
            st.dataframe(provider_stats, width="stretch", hide_index=True)
        if regime_stats is not None and not regime_stats.empty:
            st.markdown(f"#### {_('HISTORY_REGIME')}")
            st.dataframe(regime_stats, width="stretch", hide_index=True)
        if metrics.get("total_decisions", 0):
            st.caption(
                _('HISTORY_JOURNAL_SUMMARY').format(
                    metrics.get('total_decisions', 0),
                    metrics.get('accepted_buys', 0),
                    metrics.get('ai_alignment_pct', 0),
                )
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
        
        fig = px.line(ventas, x='Date', y='pnl_acumulado', title=_('HISTORY_PNL_CURVE'), markers=True)
        # Dar color verde si es positivo, rojo si es negativo
        color = "#008A63" if ventas['pnl_acumulado'].iloc[-1] >= 0 else "#E5484D"
        fig.update_traces(line_color=color, line_width=3, marker=dict(size=8))
        apply_plotly_theme(fig)
        st.plotly_chart(fig, width="stretch")
    else:
        st.write(_('NO_TRADES_MSG'))
        
    st.markdown("---")
    st.subheader(_('TRADING_JOURNAL'))
    
    sorted_df = filtered.sort_values(by='Date', ascending=False).reset_index(drop=True)
    total_rows = len(sorted_df)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    current_page = int(st.number_input(
        _('HISTORY_PAGE'),
        min_value=1,
        max_value=total_pages,
        value=min(int(st.session_state.get("hist_page", 1)), total_pages),
        step=1,
        key="hist_page",
    ))
    start_idx = (current_page - 1) * page_size
    end_idx = start_idx + page_size
    page_df = sorted_df.iloc[start_idx:end_idx]
    st.caption(_('HISTORY_SHOWING').format(start_idx + 1, min(end_idx, total_rows), total_rows))

    compact = page_df.copy()
    compact['Date'] = compact['Date'].dt.strftime('%Y-%m-%d %H:%M')
    open_context = _open_position_context(st.session_state.db)
    journal = _journal_context(st.session_state.db)
    contexts = [
        _build_trade_context(row, open_context, journal)
        for row_idx, row in page_df.iterrows()
    ]
    price_col = _('HISTORY_PRICE')
    amount_col = _('HISTORY_AMOUNT')
    value_col = _('HISTORY_VALUE_USDT')
    reason_col = _('HISTORY_REASON')
    compact[price_col] = compact["Price"].apply(_fmt_trade_price)
    compact[amount_col] = compact["Amount"].apply(_fmt_trade_amount)
    compact[value_col] = [
        _fmt_trade_value(row["Price"], row["Amount"])
        for row_idx, row in page_df.iterrows()
    ]
    compact[reason_col] = [
        _display_reason(row, context)
        for (row_idx, row), context in zip(page_df.iterrows(), contexts)
    ]
    st.dataframe(
        compact[['Date', 'Symbol', 'Side', price_col, amount_col, value_col, pnl_col, reason_col]],
        width="stretch",
        hide_index=True,
    )

    show_cards = st.toggle(_('HISTORY_SHOW_CARDS'), value=total_rows <= 50, key="hist_show_cards")
    if not show_cards:
        return

    # Tarjetas Expandibles (solo página actual)
    for (row_idx, row), context in zip(page_df.iterrows(), contexts):
        action_color = "🟢" if row['Side'] == 'buy' else "🔴"
        action_text = _('BUY') if row['Side'] == 'buy' else _('SELL')
        pnl_text = f" | PNL: {row.get(pnl_col, 0):.2f}%" if row['Side'] == 'sell' else ""
        price_text = _fmt_trade_price(row["Price"])
        
        with st.expander(f"{action_color} {action_text} | {row['Date'].strftime('%Y-%m-%d %H:%M')} | {row['Symbol']} a ${price_text}{pnl_text}"):
            st.markdown(f"**{_('HISTORY_AMOUNT')}:** {_fmt_trade_amount(row['Amount'])}")
            st.markdown(f"**{_('HISTORY_APPROX_VALUE')}:** {_fmt_trade_value(row['Price'], row['Amount'])}")
            if context:
                meta = []
                if context.get("provider"):
                    meta.append(f"Provider: `{context.get('provider')}`")
                if context.get("regime"):
                    meta.append(f"Régimen: `{context.get('regime')}`")
                if context.get("best_strategy"):
                    meta.append(f"Estrategia: `{context.get('best_strategy')}`")
                if context.get("decision_score") is not None:
                    try:
                        meta.append(f"Score: `{float(context.get('decision_score')):.2f}`")
                    except (TypeError, ValueError):
                        pass
                if context.get("confidence") is not None:
                    try:
                        meta.append(f"Confianza: `{float(context.get('confidence')):.2f}`")
                    except (TypeError, ValueError):
                        pass
                if meta:
                    st.caption(" - ".join(meta))
            st.markdown(f"**{_('HISTORY_OPERATION_REASON')}:**")
            st.info(_display_reason(row, context))
