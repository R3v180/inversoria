"""
Vista Cartera: inventario completo del exchange vs posiciones del bot,
límites CCXT y venta manual con pre-chequeo.
"""
import streamlit as st
import pandas as pd
from i18n import _


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
                f"min_coste_USDT={c.get('min_cost')} | precision_amt={c.get('amount_precision')}"
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


def render_wallet():
    st.markdown(
        """
        <style>
        .wallet-box { background-color: #161B22; padding: 14px; border-radius: 10px;
        border: 1px solid #30363D; margin-bottom: 12px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title(_("WALLET_TITLE"))
    st.caption(_("WALLET_INTRO"))

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
        table.append(
            {
                _("WALLET_COL_COIN"): r["coin"],
                _("WALLET_COL_FREE"): f"{r['free']:.8g}",
                _("WALLET_COL_TOTAL"): f"{r['total']:.8g}",
                _("WALLET_COL_USD"): f"{r['usd_total']:.2f}",
                _("WALLET_COL_TRACKED"): _("WALLET_YES") if in_bot else _("WALLET_NO"),
                _("WALLET_COL_MIN"): str(min_a) if min_a is not None else "—",
                _("WALLET_COL_MINCOST"): str(min_c) if min_c is not None else "—",
            }
        )
    st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader(_("WALLET_SELL_SECTION"))

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

    for r in sellable:
        sym = r["symbol"]
        coin = r["coin"]
        free = float(r["free"])
        px = ex.get_ticker(sym) or 0.0
        key = f"w_{coin.replace(' ', '_')}"
        with st.expander(f"{coin} ({sym}) — {_('WALLET_COL_FREE')}: {free:.8g} (~${r['usd_free']:.2f})"):
            in_bot = sym in open_pos
            db_amt = float(open_pos[sym]["amount"]) if in_bot else None
            default_qty = min(free, db_amt) if in_bot and db_amt is not None else free
            default_qty = min(default_qty, free)
            st.caption(
                f"Bot DB: {_('WALLET_YES') if in_bot else _('WALLET_NO')}"
                + (f" | amount_db={db_amt:.8g}" if in_bot else "")
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
                st.success(
                    f"OK → ~{pv.get('amount_after_precision')} {coin} "
                    f"({_('WALLET_COL_USD')}: ~{pv.get('amount_after_precision', 0) * px:.2f})"
                )
                for inf in pv.get("info", []):
                    if inf.startswith("NOTIONAL_EST:"):
                        st.caption(inf.replace("NOTIONAL_EST:", "Notional ~ ") + " USDT")

            if st.button(_("WALLET_BTN_SELL"), key=f"sell_{key}", type="primary", disabled=not pv["ok"]):
                res = ex.execute_order(sym, "sell", qty, px)
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
