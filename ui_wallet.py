"""
Vista Cartera: inventario completo del exchange vs posiciones del bot,
límites CCXT y venta manual con pre-chequeo.
"""
import streamlit as st
import pandas as pd
import config
from i18n import _


def _fmt_usd_val(v: float) -> str:
    v = float(v or 0)
    if abs(v) < 0.000001:
        return "0"
    if abs(v) < 0.01:
        return f"{v:.4f}"
    return f"{v:.2f}"


def build_inventory_snapshot_text(exchange, db) -> str:
    """Texto plano para pegar en el asistente IA."""
    lines = [
        "=== INVENTARIO SPOT (aprox. USDT) ===",
    ]
    rows = exchange.get_spot_inventory_rows()
    if rows and rows[0].get("error"):
        lines.append(f"ERROR: {rows[0].get('error')}")
        return "\n".join(lines)
    for r in rows:
        par = r.get("symbol") or "-"
        lines.append(
            f"{r['coin']}: libre={r['free']:.10g} total={r['total']:.10g} "
            f"valor~{r['usd_total']:.2f} USDT par={par}"
        )
    lines.append("")
    lines.append("=== POSICIONES ABIERTAS (bot / SQLite) ===")
    op = db.get_open_positions()
    if not op:
        lines.append("(ninguna)")
    else:
        for sym, p in op.items():
            lines.append(
                f"{sym} | amount_en_db={float(p.get('amount', 0)):.10g} | "
                f"entry={float(p.get('entry_price', 0)):.8g}"
            )
    lines.append("")
    lines.append("=== LÍMITES DE MERCADO (muestra, CCXT) ===")
    seen = set()
    for r in rows:
        sym = r.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)
        c = exchange.get_market_sell_constraints(sym)
        if c:
            lines.append(
                f"{sym} | min_cantidad={c.get('min_amount')} | "
                f"min_coste_USDT={c.get('min_cost')} | qty_step={c.get('qty_step')}"
            )
    lines.append("")
    lines.append(
        "Instrucciones: identifica retales bajo mínimo de notional, "
        "sugiere orden de consolidación y riesgos."
    )
    return "\n".join(lines)


def _explain_precheck(err: str, pv: dict) -> str:
    fmt = pv.get("amount_after_precision")
    if err == "ZERO_AMOUNT":
        return _("WALLET_ERR_GENERIC").format("cantidad 0")
    if err == "NO_FREE_BALANCE" or err == "NO_SYMBOL":
        return _("WALLET_ERR_NO_FREE")
    if err == "INSUFFICIENT_VIRTUAL":
        return _("WALLET_ERR_GENERIC").format("saldo virtual insuficiente")
    if err == "MARKET_NOT_LISTED":
        return _("WALLET_ERR_GENERIC").format("par no listado en CCXT")
    if err == "PRECISION_ZERO":
        return _("WALLET_ERR_PRECISION")
    if err.startswith("BELOW_MIN_AMOUNT:"):
        mn = err.split(":", 1)[1]
        return _("WALLET_ERR_MIN_AMT").format(mn, fmt)
    if err.startswith("BELOW_MIN_COST:"):
        parts = err.split(":")
        mc = parts[1] if len(parts) > 1 else "?"
        notional = parts[2] if len(parts) > 2 else "?"
        return _("WALLET_ERR_MIN_COST").format(notional, mc)
    if err.startswith("SLIPPAGE:"):
        pct = err.split(":", 1)[1].strip()
        return _("WALLET_ERR_SLIP").format(pct)
    if err.startswith("BALANCE:"):
        return _("WALLET_ERR_GENERIC").format(err)
    return _("WALLET_ERR_GENERIC").format(err)


def _trading_fee_rate() -> float:
    return float(config.get_setting('TRADING_FEE_RATE', 0.001, float))


def _cost_basis_source_label(source: str) -> str:
    if source == 'open_position':
        return _('WALLET_PNL_SOURCE_POS')
    if source == 'avg_trades':
        return _('WALLET_PNL_SOURCE_AVG')
    if source == 'last_buy':
        return _('WALLET_PNL_SOURCE_LAST')
    if source == 'log':
        return _('WALLET_PNL_SOURCE_LOG')
    if source == 'sell_pnl':
        return _('WALLET_PNL_SOURCE_SELL_PNL')
    return "—"


def _estimate_sell_pnl_for_row(db, row: dict, open_pos: dict, fee_rate: float):
    """PnL % y USD estimados al vender todo el saldo libre al precio actual."""
    sym = row.get("symbol")
    free = float(row.get("free") or 0)
    px = float(row.get("px") or 0)
    if not sym or free <= 0 or px <= 0:
        return None, None
    basis = _get_cost_basis(db, sym, open_pos)
    ep = basis.get("entry_price")
    if not ep or ep <= 0:
        return None, None
    eco = _estimate_sell_economics(free, px, float(ep), fee_rate)
    if not eco:
        return None, None
    return eco["pnl_pct"], eco["pnl_usd"]


def _vendible_pnl_sort_key(e: dict):
    """Solo filas con sell_ok: mejor PnL % primero (ascendente sobre -pnl)."""
    usd = float(e.get("usd_free") or 0)
    pnl = e.get("est_pnl_pct")
    if pnl is None:
        return (1, 0.0, -usd)
    return (0, -float(pnl), -usd)


def _partition_sell_rows(enriched: list) -> tuple:
    """
    Tres bloques: vendible sin posición bot, vendible en posición bot, no vendible.
    Dentro de cada bloque vendible, mejor PnL % estimado primero.
    """
    free_vendible = []
    bot_vendible = []
    blocked = []
    for e in enriched:
        if not e.get("sell_ok"):
            blocked.append(e)
        elif e.get("in_bot"):
            bot_vendible.append(e)
        else:
            free_vendible.append(e)
    free_vendible.sort(key=_vendible_pnl_sort_key)
    bot_vendible.sort(key=_vendible_pnl_sort_key)
    blocked.sort(key=lambda e: -float(e.get("usd_free") or 0))
    return free_vendible, bot_vendible, blocked


def _estimate_sell_economics(qty: float, sell_price: float, entry_price: float, fee_rate: float):
    if not entry_price or entry_price <= 0 or qty <= 0 or sell_price <= 0:
        return None
    cost_base = entry_price * qty
    buy_fee = cost_base * fee_rate
    total_cost = cost_base + buy_fee
    gross = sell_price * qty
    sell_fee = gross * fee_rate
    net_receive = gross - sell_fee
    pnl_usd = net_receive - total_cost
    pnl_pct = (pnl_usd / total_cost * 100.0) if total_cost > 0 else 0.0
    return {
        'cost_base': cost_base,
        'buy_fee': buy_fee,
        'total_cost': total_cost,
        'gross_sell': gross,
        'sell_fee': sell_fee,
        'net_receive': net_receive,
        'pnl_usd': pnl_usd,
        'pnl_pct': pnl_pct,
        'fee_pct_display': fee_rate * 100.0,
    }


def _get_cost_basis(db, sym: str, open_pos: dict):
    if hasattr(db, 'get_cost_basis'):
        return db.get_cost_basis(sym, open_pos)
    from runtime_bootstrap import new_database_manager
    st.session_state.db = new_database_manager()
    return st.session_state.db.get_cost_basis(sym, open_pos)


def _render_sell_pnl_panel(db, sym: str, qty: float, sell_price: float, open_pos: dict, fee_rate: float):
    st.markdown(f"**{_('WALLET_PNL_TITLE')}**")
    st.caption(_('WALLET_FEE_NOTE'))
    basis = _get_cost_basis(db, sym, open_pos)
    entry = basis.get('entry_price')
    if not entry or entry <= 0:
        st.info(_('WALLET_PNL_UNKNOWN'))
        return
    eco = _estimate_sell_economics(qty, sell_price, entry, fee_rate)
    if not eco:
        return
    st.caption(f"{_('WALLET_PNL_BUY_SOURCE')}: {_cost_basis_source_label(basis.get('source'))}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(_('WALLET_PNL_BUY_PRICE'), f"${entry:.6g}")
    c2.metric(_('WALLET_PNL_GROSS_SELL'), f"${eco['gross_sell']:.2f}")
    c3.metric(_('WALLET_PNL_NET_RECEIVE'), f"${eco['net_receive']:.2f}")
    pnl_color = "normal" if eco['pnl_usd'] >= 0 else "inverse"
    c4.metric(_('WALLET_PNL_PCT'), f"{eco['pnl_pct']:+.2f}%", f"${eco['pnl_usd']:+.2f}", delta_color=pnl_color)

    d1, d2, d3 = st.columns(3)
    d1.metric(
        _('WALLET_PNL_FEE_BUY').format(f"{eco['fee_pct_display']:.3f}"),
        f"${eco['buy_fee']:.4f}",
    )
    d2.metric(
        _('WALLET_PNL_FEE_SELL').format(f"{eco['fee_pct_display']:.3f}"),
        f"${eco['sell_fee']:.4f}",
    )
    d3.metric(_('WALLET_PNL_COST_TOTAL'), f"${eco['total_cost']:.2f}")


def _evaluate_sell_candidate(ex, row: dict, open_pos: dict) -> dict:
    """Pre-chequeo con saldo libre completo; marca polvo recuperable (OK y sin fila en bot)."""
    sym = row.get("symbol")
    free = float(row.get("free") or 0)
    in_bot = bool(sym and sym in open_pos)
    if not sym or free <= 0:
        return {
            "in_bot": in_bot,
            "pv": {"ok": False, "errors": ["ZERO_AMOUNT"], "info": [], "amount_after_precision": None},
            "sell_ok": False,
            "is_recoverable": False,
        }
    px = ex.get_ticker(sym) or 0.0
    pv = ex.prevalidate_market_sell(sym, free, px, free_override=free)
    sell_ok = bool(pv.get("ok"))
    is_recoverable = sell_ok and not in_bot
    return {
        "in_bot": in_bot,
        "pv": pv,
        "sell_ok": sell_ok,
        "is_recoverable": is_recoverable,
        "px": px,
    }


def render_wallet():
    st.markdown(
        """
        <style>
        .wallet-box { background-color: #161B22; padding: 14px; border-radius: 10px;
        border: 1px solid #30363D; margin-bottom: 12px; }
        .wallet-recover-chip {
            display: inline-block; margin: 4px 6px 4px 0; padding: 6px 12px;
            border-radius: 8px; background: rgba(0, 255, 170, 0.15);
            border: 1px solid #00FFAA; color: #00FFAA; font-weight: 600; font-size: 0.9em;
        }
        .wallet-recover-panel {
            background: rgba(0, 255, 170, 0.08); border: 1px solid #00FFAA;
            border-radius: 10px; padding: 12px 14px; margin-bottom: 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title(_("WALLET_TITLE"))
    st.caption(_("WALLET_INTRO"))

    from runtime_bootstrap import new_database_manager

    if not hasattr(st.session_state.db, 'get_cost_basis'):
        st.session_state.db = new_database_manager()
    db = st.session_state.db
    ex = st.session_state.exchange
    open_pos = db.get_open_positions()

    rows = ex.get_spot_inventory_rows()
    if rows and rows[0].get("error"):
        st.error(rows[0].get("error"))
        return

    equity = ex.get_balance()
    tracked_usd = 0.0
    for sym, p in open_pos.items():
        px = ex.get_ticker(sym) or float(p.get("entry_price") or 0)
        tracked_usd += float(p.get("amount", 0) or 0) * float(px or 0)

    sum_rows_usd = sum(float(r.get("usd_total") or 0) for r in rows)
    untracked = max(0.0, sum_rows_usd - tracked_usd)

    m1, m2, m3 = st.columns(3)
    m1.metric(_("WALLET_METRIC_EQUITY"), f"${equity:.2f}")
    m2.metric(_("WALLET_METRIC_TRACKED"), f"${tracked_usd:.2f}")
    m3.metric(_("WALLET_METRIC_UNTRACKED"), f"${untracked:.2f}")

    st.markdown("---")
    st.subheader(_("WALLET_TABLE_TITLE"))

    table = []
    for r in rows:
        sym = r.get("symbol")
        in_bot = sym in open_pos if sym else False
        cons = ex.get_market_sell_constraints(sym) if sym else None
        min_a = cons.get("min_amount") if cons else None
        min_c = cons.get("min_cost") if cons else None
        qty_step = cons.get("qty_step") if cons else None
        table.append(
            {
                _("WALLET_COL_COIN"): r["coin"],
                _("WALLET_COL_PAIR"): sym or "—",
                _("WALLET_COL_FREE"): f"{r['free']:.8g}",
                _("WALLET_COL_TOTAL"): f"{r['total']:.8g}",
                _("WALLET_COL_USD"): _fmt_usd_val(r["usd_total"]),
                _("WALLET_COL_TRACKED"): _("WALLET_YES") if in_bot else _("WALLET_NO"),
                _("WALLET_COL_MIN"): str(min_a) if min_a is not None else "—",
                _("WALLET_COL_MINCOST"): str(min_c) if min_c is not None else "—",
                _("WALLET_COL_QTYSTEP"): str(qty_step) if qty_step is not None else "—",
            }
        )
    st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
    st.caption(_("WALLET_TABLE_FOOTNOTE"))

    st.markdown("---")
    st.subheader(_("WALLET_SELL_SECTION"))
    st.caption(_("WALLET_SELL_ORDER_HINT"))

    sellable = [
        r
        for r in rows
        if r.get("symbol")
        and r.get("coin") not in ("USDT", "USD")
        and float(r.get("free") or 0) > 0
    ]
    if not sellable:
        st.info(_("WALLET_ERR_NO_FREE"))
        return

    fee_rate = _trading_fee_rate()
    enriched = []
    for r in sellable:
        ev = _evaluate_sell_candidate(ex, r, open_pos)
        item = {**r, **ev}
        pnl_pct, pnl_usd = _estimate_sell_pnl_for_row(db, item, open_pos, fee_rate)
        item["est_pnl_pct"] = pnl_pct
        item["est_pnl_usd"] = pnl_usd
        enriched.append(item)

    free_vendible, bot_vendible, blocked_rows = _partition_sell_rows(enriched)
    recoverable = free_vendible

    st.markdown('<div class="wallet-recover-panel">', unsafe_allow_html=True)
    st.markdown(f"**{_('WALLET_RECOVERABLE_TITLE')}**")
    st.caption(_("WALLET_RECOVERABLE_HINT"))
    if recoverable:
        chip_parts = []
        for e in recoverable:
            pnl_txt = ""
            if e.get("est_pnl_pct") is not None:
                pnl_txt = f" · {e['est_pnl_pct']:+.1f}%"
            chip_parts.append(
                f'<span class="wallet-recover-chip">{e["coin"]} · ~{_fmt_usd_val(e["usd_free"])} USDT{pnl_txt}</span>'
            )
        chips = "".join(chip_parts)
        st.markdown(chips, unsafe_allow_html=True)
    else:
        st.info(_("WALLET_RECOVERABLE_NONE"))
    st.markdown("</div>", unsafe_allow_html=True)

    only_recover = st.checkbox(_("WALLET_FILTER_RECOVERABLE"), value=False, key="wallet_filter_recover")
    if only_recover:
        sell_sections = [(_("WALLET_SELL_FREE_SECTION"), free_vendible)]
    else:
        sell_sections = []
        if free_vendible:
            sell_sections.append((_("WALLET_SELL_FREE_SECTION"), free_vendible))
        if bot_vendible:
            sell_sections.append((_("WALLET_SELL_BOT_SECTION"), bot_vendible))
        if blocked_rows:
            sell_sections.append((_("WALLET_BLOCKED_SECTION"), blocked_rows))

    for sec_title, sec_rows in sell_sections:
        if not sec_rows:
            continue
        st.markdown("---")
        st.markdown(f"#### {sec_title}")
        for e in sec_rows:
            r = e
            sym = r["symbol"]
            coin = r["coin"]
            free = float(r["free"])
            px = e.get("px") or ex.get_ticker(sym) or 0.0
            in_bot = e["in_bot"]
            sell_ok = e["sell_ok"]
            is_recoverable = e["is_recoverable"]
            pv_full = e["pv"]
            key = f"w_{coin.replace(' ', '_')}"

            if is_recoverable:
                badge = f"🟢 {_('WALLET_BADGE_RECOVERABLE')}"
            elif in_bot:
                badge = f"🤖 {_('WALLET_BADGE_BOT_POS')}" if sell_ok else f"🤖 ⛔ {_('WALLET_BADGE_BOT_POS')}"
            else:
                badge = f"⛔ {_('WALLET_BADGE_BLOCKED')}"

            bot_lbl = _("WALLET_BADGE_BOT_POS") if in_bot else _("WALLET_BADGE_NO_BOT")
            pnl_hdr = ""
            if sell_ok and e.get("est_pnl_pct") is not None:
                pnl_hdr = f" · **{e['est_pnl_pct']:+.2f}%**"
            header = (
                f"{badge} · **{coin}** ({sym}) · "
                f"{_('WALLET_COL_FREE')}: {free:.8g} (~{_fmt_usd_val(r['usd_free'])} USDT){pnl_hdr} · {bot_lbl}"
            )
            with st.expander(header, expanded=is_recoverable):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric(_("WALLET_BOT_STATUS"), _("WALLET_YES") if in_bot else _("WALLET_NO"))
                with c2:
                    st.metric(_("WALLET_PRECHECK"), _("WALLET_YES") if sell_ok else _("WALLET_NO"))
                with c3:
                    st.metric(_("WALLET_BADGE_RECOVERABLE"), _("WALLET_YES") if is_recoverable else _("WALLET_NO"))

                if is_recoverable:
                    st.success(_("WALLET_RECOVERABLE_HINT"))
                elif in_bot:
                    st.warning(
                        f"{_('WALLET_BADGE_BOT_POS')}: "
                        + (_("WALLET_YES") if sell_ok else _("WALLET_BADGE_BLOCKED"))
                    )
                elif not sell_ok:
                    for er in pv_full.get("errors", []):
                        st.warning(_explain_precheck(er, pv_full))

                db_amt = float(open_pos[sym]["amount"]) if in_bot else None
                default_qty = free if is_recoverable else (
                    min(free, db_amt) if in_bot and db_amt is not None else free
                )
                default_qty = min(default_qty, free)
                cons_e = ex.get_market_sell_constraints(sym)
                if cons_e:
                    ma = cons_e.get("min_amount")
                    mc = cons_e.get("min_cost")
                    st.caption(
                        _("WALLET_MARKET_META").format(
                            cons_e.get("qty_step") if cons_e.get("qty_step") is not None else "—",
                            ma if ma is not None else "—",
                            mc if mc is not None else "—",
                        )
                    )
                qty = st.number_input(
                    _("WALLET_SELL_QTY"),
                    min_value=0.0,
                    max_value=float(free),
                    value=float(min(default_qty, free)),
                    step=1e-8 if free < 1 else 1e-6,
                    key=f"qty_{key}",
                )
                pv = ex.prevalidate_market_sell(sym, qty, px, free_override=free)
                st.markdown(f"**{_('WALLET_PRECHECK')}**")
                if pv["errors"]:
                    for er in pv["errors"]:
                        st.warning(_explain_precheck(er, pv))
                else:
                    amt_ok = pv.get('amount_after_precision')
                    st.success(
                        _('WALLET_PRECHECK_OK').format(
                            amt_ok,
                            coin,
                            f"{float(amt_ok or 0) * float(px or 0):.2f}",
                        )
                    )
                    for inf in pv.get("info", []):
                        if inf.startswith("NOTIONAL_EST:"):
                            st.caption(inf.replace("NOTIONAL_EST:", "Notional ~ ") + " USDT")

                sell_px = float(px) if px else 0.0
                fmt_qty = float(pv.get("amount_after_precision") or qty) if pv.get("ok") else float(qty)
                if sell_px > 0 and fmt_qty > 0:
                    _render_sell_pnl_panel(db, sym, fmt_qty, sell_px, open_pos, fee_rate)

                hard_errors = [
                    er for er in pv.get("errors", [])
                    if not str(er).startswith("SLIPPAGE:")
                ]
                if pv.get("errors") and not hard_errors:
                    st.warning(_("WALLET_SLIPPAGE_FORCE_HINT"))

                if st.button(_("WALLET_BTN_SELL"), key=f"sell_{key}", type="primary", disabled=bool(hard_errors)):
                    res = ex.execute_order(sym, "sell", qty, px, force_market=True)
                    if res.get("status") in ("closed", "simulated", "open"):
                        exit_p = res.get("average") or res.get("price") or px
                        try:
                            exit_p = float(exit_p)
                        except (TypeError, ValueError):
                            exit_p = float(px)
                        try:
                            sold = float(res.get("filled") or 0)
                        except (TypeError, ValueError):
                            sold = 0.0
                        if sold <= 0:
                            sold = float(res.get("amount") or qty)
                        sold = min(sold, float(qty), free)
                        reason = _("WALLET_REASON_WALLET")
                        if in_bot:
                            db.close_position(sym, exit_p, reason, sold_amount=sold)
                        db.add_log(f"{reason}: {sym} qty={sold} @ {exit_p}")
                        st.success(_("WALLET_SELL_OK"))
                        st.rerun()
                    else:
                        st.error(f"{_('WALLET_SELL_FAIL')}: {res.get('reason', res)}")

    st.markdown("---")
    if st.button(_("WALLET_SNAPSHOT_BTN")):
        st.session_state["_wallet_clipboard"] = build_inventory_snapshot_text(ex, db)
    if st.session_state.get("_wallet_clipboard"):
        st.caption(_("WALLET_SNAPSHOT_HINT"))
        st.code(st.session_state["_wallet_clipboard"], language=None)
