import streamlit as st
import time
import json
import sqlite3
import config
from assistant_runtime import RuntimeContext, build_assistant_context as build_runtime_assistant_context
from config_importer import (
    CONFIG_SCHEMA,
    apply_config_changes,
    diff_config_changes,
    parse_config_payload,
    validate_config_payload,
)
from diagnostic_utils import read_recent_log_summary
from i18n import _
from ui_services.manual_trading import execute_manual_buy, execute_manual_sell


def _pending_orders():
    if "assistant_pending_orders" not in st.session_state:
        st.session_state.assistant_pending_orders = []
    return st.session_state.assistant_pending_orders


def _queue_assistant_order(
    action: str,
    symbol: str,
    source_text: str = "",
    amount_usdt: float | None = None,
    amount_base: float | None = None,
    percent: float | None = None,
):
    order_id = f"{int(time.time() * 1000)}_{len(_pending_orders())}_{action}_{symbol.replace('/', '_')}"
    _pending_orders().append({
        "id": order_id,
        "action": action.upper(),
        "symbol": symbol.upper(),
        "amount_usdt": amount_usdt,
        "amount_base": amount_base,
        "percent": percent,
        "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        "source_text": source_text[:500],
    })
    return order_id


def _remove_pending_order(order_id: str):
    st.session_state.assistant_pending_orders = [
        o for o in _pending_orders() if o.get("id") != order_id
    ]


def _pending_config_changes():
    if "assistant_pending_config_changes" not in st.session_state:
        st.session_state.assistant_pending_config_changes = []
    return st.session_state.assistant_pending_config_changes


def _queue_assistant_config_change(changes: dict, warnings=None, blocked=None, source_text: str = ""):
    change_id = f"{int(time.time() * 1000)}_{len(_pending_config_changes())}_config"
    _pending_config_changes().append({
        "id": change_id,
        "changes": changes,
        "warnings": warnings or [],
        "blocked": blocked or [],
        "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        "source_text": source_text[:800],
    })
    return change_id


def _remove_pending_config_change(change_id: str):
    st.session_state.assistant_pending_config_changes = [
        c for c in _pending_config_changes() if c.get("id") != change_id
    ]


def _position_extra(pos: dict) -> dict:
    raw = (pos or {}).get("extra_data")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _parse_optional_float(value):
    if value is None:
        return None
    try:
        parsed = float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_order_block(block: str):
    fields = {}
    for line in str(block or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().upper()] = value.strip()

    action = fields.get("ACTION", "").upper()
    symbol = fields.get("SYMBOL", "").upper()
    if action not in {"BUY", "SELL"} or not symbol:
        return None

    return {
        "action": action,
        "symbol": symbol,
        "amount_usdt": _parse_optional_float(fields.get("AMOUNT_USDT")),
        "amount_base": _parse_optional_float(fields.get("AMOUNT_BASE") or fields.get("AMOUNT")),
        "percent": _parse_optional_float(fields.get("PERCENT")),
    }


def _execute_pending_order(order: dict, db, exchange):
    action = order.get("action")
    symbol = order.get("symbol")
    current_price = exchange.get_ticker(symbol)
    if not current_price or current_price <= 0:
        st.error(_("ASSIST_ORDER_NO_PRICE").format(symbol))
        return

    decision_id = None
    if hasattr(db, "add_decision_journal"):
        decision_id = db.add_decision_journal(
            symbol=symbol,
            price=float(current_price),
            ai_action=action,
            action_final=action,
            executable_action=action,
            provider="Assistant",
            decision_mode="manual_assistant",
            execution_mode="manual_confirm",
            regime="MANUAL",
            strategy="ASSISTANT_ORDER",
            confidence=1.0,
            decision_score=1.0,
            score_components={"manual_confirmation": 1.0},
            indicators={},
            portfolio_bucket="MANUAL",
            execution_status="pending_confirmation",
            block_reason="assistant_confirmed_by_user",
        )

    if action == "SELL":
        positions = db.get_open_positions()
        if symbol not in positions:
            st.warning(_("ASSIST_ORDER_NO_POSITION").format(symbol))
            if decision_id:
                db.update_decision_journal(
                    decision_id,
                    execution_status="blocked_no_position",
                    block_reason="No open bot position",
                )
            return
        pos = positions[symbol]
        real_amount = exchange.get_coin_balance(symbol)
        max_sell = min(float(pos["amount"]), float(real_amount)) if real_amount > 0 else float(pos["amount"])
        requested_base = _parse_optional_float(order.get("amount_base"))
        requested_percent = _parse_optional_float(order.get("percent"))
        if requested_base:
            sell_amount = min(float(requested_base), float(max_sell))
        elif requested_percent:
            sell_amount = float(max_sell) * min(float(requested_percent), 100.0) / 100.0
        else:
            sell_amount = float(max_sell)
        if sell_amount <= 0:
            st.error(_("ASSIST_ORDER_LOW_BALANCE").format(f"{max_sell:.8g}"))
            if decision_id:
                db.update_decision_journal(
                    decision_id,
                    execution_status="blocked_min_size",
                    block_reason=f"sell_amount={sell_amount}",
                )
            return
        outcome = execute_manual_sell(
            db,
            exchange,
            symbol,
            sell_amount,
            current_price,
            _("ASSIST_ORDER_SELL_REASON"),
            in_bot=True,
            max_qty=float(pos["amount"]),
        )
        if outcome.get("ok"):
            exit_price = float(outcome.get("exit_price") or current_price)
            sold = float(outcome.get("sold") or sell_amount)
            entry = float(pos.get("entry_price") or exit_price)
            realized_pnl = ((exit_price - entry) / entry) * 100 if entry else 0.0
            if decision_id:
                db.update_decision_journal(
                    decision_id,
                    execution_status=outcome.get("status", "executed"),
                    execution_side="sell",
                    executed_price=exit_price,
                    executed_amount=sold,
                    realized_pnl_pct=realized_pnl,
                    exit_reason=_("ASSIST_ORDER_SELL_REASON"),
                )
            entry_decision_id = _position_extra(pos).get("entry_decision_id")
            if entry_decision_id:
                db.update_decision_journal(
                    entry_decision_id,
                    realized_pnl_pct=realized_pnl,
                    exit_reason=_("ASSIST_ORDER_SELL_REASON"),
                )
            st.success(_("ASSIST_ORDER_SELL_OK").format(symbol, f"{exit_price:.6g}"))
            _remove_pending_order(order["id"])
            time.sleep(0.5)
            st.rerun()
        else:
            st.error(f"{_('ASSIST_ORDER_FAIL')}: {outcome.get('reason', outcome)}")
            if decision_id:
                db.update_decision_journal(
                    decision_id,
                    execution_status="failed",
                    execution_side="sell",
                    block_reason=str(outcome.get("reason", outcome)),
                )
        return

    if action == "BUY":
        usdt_balance = exchange.get_usdt_balance()
        requested_usdt = _parse_optional_float(order.get("amount_usdt"))
        amount_usdt = min(float(requested_usdt), float(usdt_balance)) if requested_usdt else float(usdt_balance) * float(config.RISK_PER_TRADE)
        min_position = float(getattr(config, "MIN_POSITION_USDT", 1.0) or 1.0)
        if amount_usdt <= min_position:
            st.error(_("ASSIST_ORDER_LOW_BALANCE").format(f"{usdt_balance:.2f}"))
            if decision_id:
                db.update_decision_journal(
                    decision_id,
                    execution_status="blocked_min_size",
                    block_reason=f"amount_usdt={amount_usdt:.4f} <= min_position={min_position:.4f}",
                )
            return
        outcome = execute_manual_buy(
            db,
            exchange,
            symbol,
            amount_usdt,
            _("ASSIST_ORDER_BUY_REASON"),
            price=float(current_price),
            provider="Asistente IA",
            decision_id=decision_id,
        )
        if outcome.get("ok"):
            filled = float(outcome.get("filled") or 0)
            trade_id = outcome.get("trade_id")
            if decision_id:
                db.update_decision_journal(
                    decision_id,
                    execution_status=outcome.get("order", {}).get("status", "executed"),
                    execution_side="buy",
                    executed_price=float(outcome.get("price") or current_price),
                    executed_amount=filled,
                    sizing={
                        "amount_usdt": amount_usdt,
                        "amount_base": filled,
                        "sizing_reason": "assistant_manual",
                    },
                    block_reason=f"trade_id={trade_id}",
                )
            st.success(_("ASSIST_ORDER_BUY_OK").format(symbol, f"{outcome.get('price', current_price):.6g}"))
            _remove_pending_order(order["id"])
            time.sleep(0.5)
            st.rerun()
        else:
            st.error(f"{_('ASSIST_ORDER_FAIL')}: {outcome.get('reason', outcome)}")
            if decision_id:
                db.update_decision_journal(
                    decision_id,
                    execution_status="failed",
                    execution_side="buy",
                    block_reason=str(outcome.get("reason", outcome)),
                )


def _render_pending_orders(db, exchange):
    pending = _pending_orders()
    if not pending:
        return

    st.warning(_("ASSIST_PENDING_WARNING"))
    for order in list(pending):
        action = order.get("action")
        symbol = order.get("symbol")
        price = exchange.get_ticker(symbol) or 0.0
        with st.container(border=True):
            st.markdown(f"**{_('ASSIST_PENDING_ORDER')}**: `{action}` `{symbol}`")
            st.caption(_("ASSIST_PENDING_CREATED").format(order.get("created_at", "-")))
            if price:
                st.metric(_("ASSIST_PENDING_PRICE"), f"${float(price):.6g}")
            if action == "BUY":
                bal = float(exchange.get_usdt_balance() or 0)
                requested_usdt = _parse_optional_float(order.get("amount_usdt"))
                amount_usdt = min(requested_usdt, bal) if requested_usdt else bal * float(config.RISK_PER_TRADE)
                st.caption(_("ASSIST_PENDING_BUY_SIZE").format(f"{amount_usdt:.2f}"))
            elif action == "SELL":
                pos = db.get_open_positions().get(symbol)
                qty = float(pos.get("amount") or 0) if pos else 0.0
                requested_base = _parse_optional_float(order.get("amount_base"))
                requested_percent = _parse_optional_float(order.get("percent"))
                if requested_base:
                    qty = min(float(requested_base), qty)
                elif requested_percent:
                    qty = qty * min(float(requested_percent), 100.0) / 100.0
                st.caption(_("ASSIST_PENDING_SELL_SIZE").format(f"{qty:.8g}"))

            c1, c2 = st.columns(2)
            if c1.button(_("ASSIST_CONFIRM_ORDER"), key=f"confirm_{order['id']}", type="primary"):
                _execute_pending_order(order, db, exchange)
            if c2.button(_("ASSIST_CANCEL_ORDER"), key=f"cancel_{order['id']}"):
                _remove_pending_order(order["id"])
                st.rerun()


def _render_pending_config_changes():
    pending = _pending_config_changes()
    if not pending:
        return

    st.warning(_("ASSIST_CONFIG_PENDING_WARNING"))
    for item in list(pending):
        changes = item.get("changes", {})
        rows = diff_config_changes(changes)
        with st.container(border=True):
            st.markdown(f"**{_('ASSIST_PENDING_CONFIG')}**")
            st.caption(_("ASSIST_PENDING_CREATED").format(item.get("created_at", "-")))
            if rows:
                st.dataframe(rows, width="stretch", hide_index=True)
            else:
                st.info(_("CONFIG_NO_EFFECTIVE_DIFF"))
            if item.get("warnings"):
                with st.expander(_("CONFIG_WARNINGS")):
                    for warning in item.get("warnings", []):
                        st.caption(f"- {warning}")
            if item.get("blocked"):
                st.info(_("CONFIG_BLOCKED_KEYS").format(", ".join(item.get("blocked", []))))

            c1, c2 = st.columns(2)
            if c1.button(_("ASSIST_CONFIRM_CONFIG"), key=f"confirm_config_{item['id']}", type="primary"):
                backup = apply_config_changes(changes)
                _remove_pending_config_change(item["id"])
                if backup:
                    st.success(_("CONFIG_APPLIED_BACKUP").format(backup))
                else:
                    st.success(_("CONFIG_APPLIED"))
                time.sleep(0.5)
                st.rerun()
            if c2.button(_("ASSIST_CANCEL_ORDER"), key=f"cancel_config_{item['id']}"):
                _remove_pending_config_change(item["id"])
                st.rerun()


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _compact_daemon_context(db):
    try:
        diag = json.loads(db.get_system_status("daemon_diagnostics", "{}") or "{}")
    except Exception:
        diag = {}
    if not diag:
        return "Sin diagnóstico del daemon todavía."

    state = diag.get("state", "-")
    scanned = diag.get("scanned", 0)
    actions = diag.get("actions", {})
    providers = diag.get("providers", {})
    holds = diag.get("hold_reasons", {})
    skipped = diag.get("skipped", {})
    open_pos = diag.get("open_positions", 0)
    dyn_max = diag.get("dynamic_max", "-")
    cycle_age = "-"
    if diag.get("cycle_ts"):
        cycle_age = f"{max(0, int(time.time() - float(diag.get('cycle_ts'))))}s"

    lines = [
        f"Estado={state}; último ciclo={cycle_age}; escaneados={scanned}; posiciones={open_pos}/{dyn_max}",
        "Acciones ciclo: " + ", ".join(f"{k}:{v}" for k, v in actions.items()) if actions else "Acciones ciclo: N/A",
        "Providers: " + ", ".join(f"{k}:{v}" for k, v in providers.items()) if providers else "Providers: N/A",
    ]
    if skipped:
        lines.append("Skipped: " + ", ".join(f"{k}:{v}" for k, v in skipped.items()))
    if diag.get("top_buy_candidates"):
        lines.append(
            "Top BUY candidates: " + " | ".join(
                f"{c.get('symbol')} score={c.get('score')} decision={float(c.get('decision_score', 0)):.0%} conf={float(c.get('confidence', 0)):.0%}"
                for c in diag.get("top_buy_candidates", [])[:5]
            )
        )
    if diag.get("risk_guards"):
        rg = diag.get("risk_guards", {})
        lines.append(
            f"Risk guards: ok={rg.get('ok')} daily_loss={rg.get('daily_loss_pct', 0)}% "
            f"exposure={rg.get('exposure_pct', 0)}% alt={rg.get('alt_exposure_pct', 0)}% "
            f"bucket={rg.get('bucket_exposure_pct', 0)}% reasons={rg.get('reasons', [])}"
        )
    if holds:
        top = list(holds.items())[:5]
        lines.append("Top HOLD reasons: " + " | ".join(f"{v}x {k}" for k, v in top))
    return "\n".join(lines)


def _compact_settings_context(exchange):
    mode = "simulación" if exchange.modo_simulacion else "REAL"
    effective = config.get_effective_max_positions(_safe_float(exchange.get_balance()))
    allowed_config = ", ".join(CONFIG_SCHEMA.keys())
    return "\n".join([
        f"Modo={mode}",
        f"TRADING_EXECUTION_MODE={getattr(config, 'TRADING_EXECUTION_MODE', 'auto')}; DECISION_MODE={getattr(config, 'DECISION_MODE', 'hybrid')}; MIN_AUTO_DECISION_SCORE={getattr(config, 'MIN_AUTO_DECISION_SCORE', 0.62):.2f}",
        f"RISK_PER_TRADE={config.RISK_PER_TRADE:.2%}",
        f"VOLATILITY_SIZING_ENABLED={getattr(config, 'VOLATILITY_SIZING_ENABLED', True)}; MAX_POSITION_RISK={getattr(config, 'MAX_POSITION_RISK_PCT', 0):.2%}; MIN_POSITION_USDT={getattr(config, 'MIN_POSITION_USDT', 1.0):.2f}",
        f"MAX_DAILY_LOSS={getattr(config, 'MAX_DAILY_LOSS_PCT', 0):.2%}; MAX_PORTFOLIO_EXPOSURE={getattr(config, 'MAX_PORTFOLIO_EXPOSURE_PCT', 0):.2%}; MAX_SYMBOL_EXPOSURE={getattr(config, 'MAX_SYMBOL_EXPOSURE_PCT', 0):.2%}; MAX_ALT_EXPOSURE={getattr(config, 'MAX_ALT_EXPOSURE_PCT', 0):.2%}; MAX_BUCKET_EXPOSURE={getattr(config, 'MAX_BUCKET_EXPOSURE_PCT', 0):.2%}",
        f"ADAPTIVE_SCORING_ENABLED={getattr(config, 'ADAPTIVE_SCORING_ENABLED', True)}; ADAPTIVE_MIN_TRADES={getattr(config, 'ADAPTIVE_MIN_TRADES', 5)}; ADAPTIVE_MAX_SCORE_ADJUSTMENT={getattr(config, 'ADAPTIVE_MAX_SCORE_ADJUSTMENT', 0.12):.2f}",
        f"MAX_OPEN_POSITIONS={config.MAX_OPEN_POSITIONS}; límite efectivo={effective}; prioridad manual={config.get_setting('MANUAL_MAX_POSITIONS_PRIORITY', False, bool)}",
        f"MIN_PROFIT_NET={config.get_setting('MIN_PROFIT_NET', 1.0, float):.2f}%",
        f"ROTATION_ENABLED={config.ROTATION_ENABLED}; ROTATION_MIN_PROFIT={config.ROTATION_MIN_PROFIT:.2f}%; GAP={config.ROTATION_CONFIDENCE_GAP:.2f}; MIN_NEW_CONF={config.ROTATION_MIN_NEW_CONFIDENCE:.2f}",
        f"BUY_SLIPPAGE_LIMIT={config.BUY_SLIPPAGE_LIMIT:.2%}; SELL_SLIPPAGE_LIMIT={config.SELL_SLIPPAGE_LIMIT:.2%}; TRADING_FEE_RATE={config.TRADING_FEE_RATE:.3%}",
        f"AI_ANALYSIS_INTERVAL={config.AI_ANALYSIS_INTERVAL}s",
        f"CONFIG_IMPORT_KEYS_PERMITIDAS={allowed_config}",
    ])


def _compact_positions_context(db, exchange):
    positions = db.get_open_positions()
    if not positions:
        return "Sin posiciones abiertas gestionadas por el bot."

    lines = []
    for sym, pos in list(positions.items())[:10]:
        entry = _safe_float(pos.get("entry_price"))
        amount = _safe_float(pos.get("amount"))
        px = _safe_float(exchange.get_ticker(sym), entry)
        value = amount * px
        pnl = ((px - entry) / entry * 100.0) if entry > 0 else 0.0
        lines.append(f"{sym}: qty={amount:.8g}; entry={entry:.8g}; px={px:.8g}; valor~{value:.2f} USDT; PnL={pnl:+.2f}%")
    return "\n".join(lines)


def _compact_wallet_context(db, exchange, max_rows=8):
    try:
        rows = exchange.get_spot_inventory_rows()
    except Exception as exc:
        return f"No se pudo leer cartera exchange: {exc}"
    if not rows or rows[0].get("error"):
        return f"Cartera exchange no disponible: {rows[0].get('error') if rows else 'sin datos'}"

    open_pos = db.get_open_positions()
    recoverable = []
    bot_assets = []
    blocked = []
    untracked_value = 0.0

    for row in rows:
        sym = row.get("symbol")
        coin = row.get("coin")
        if coin in ("USDT", "USD") or not sym:
            continue
        free = _safe_float(row.get("free"))
        usd_free = _safe_float(row.get("usd_free"))
        if usd_free > 0 and sym not in open_pos:
            untracked_value += usd_free
        if free <= 0:
            continue
        in_bot = sym in open_pos
        if in_bot:
            bot_assets.append((usd_free, f"{sym}: libre~{usd_free:.2f} USDT (posición bot)"))
            continue
        px = _safe_float(exchange.get_ticker(sym))
        pv = exchange.prevalidate_market_sell(sym, free, px, free_override=free)
        if pv.get("ok"):
            recoverable.append((usd_free, f"{sym}: recuperable libre~{usd_free:.2f} USDT"))
        else:
            errs = ",".join(pv.get("errors", [])[:2])
            blocked.append((usd_free, f"{sym}: no vendible ahora libre~{usd_free:.2f} USDT ({errs})"))

    def top_text(items):
        items = sorted(items, key=lambda x: -x[0])[:max_rows]
        return "\n".join(x[1] for x in items) if items else "(ninguno)"

    return "\n".join([
        f"Valor libre no gestionado aprox: {untracked_value:.2f} USDT",
        "Recuperables sin posición bot:",
        top_text(recoverable),
        "Saldos libres en posición bot:",
        top_text(bot_assets),
        "No vendibles principales:",
        top_text(blocked),
    ])


def _compact_decisions_context(db, symbols):
    lines = []
    seen = []
    for sym in symbols:
        if sym and sym not in seen:
            seen.append(sym)
    for sym in seen[:12]:
        raw = db.get_system_status(f"decision_{sym}")
        if not raw:
            continue
        try:
            dec = json.loads(raw)
        except Exception:
            continue
        reason = str(dec.get("reasoning", ""))[:100]
        lines.append(
            f"{sym}: {dec.get('action', 'HOLD')} conf={_safe_float(dec.get('confidence')):.0%} "
            f"exec={dec.get('executable_action', dec.get('action', 'HOLD'))} "
            f"score={_safe_float(dec.get('decision_score')):.0%} "
            f"regime={dec.get('regime', '-')} strategy={dec.get('best_strategy', '-')} reason={reason}"
        )
    return "\n".join(lines) if lines else "Sin decisiones recientes por símbolo."


def _compact_backtest_context(db):
    try:
        with sqlite3.connect(db.db_path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            runs = conn.execute(
                'SELECT symbol, timeframe, win_rate, best_strategy FROM backtest_runs ORDER BY run_timestamp DESC LIMIT 5'
            ).fetchall()
        if not runs:
            return "Sin datos de backtest."
        return ", ".join(f"{r['symbol']} {r['timeframe']} WR:{r['win_rate']:.0%} best:{r['best_strategy']}" for r in runs)
    except Exception as exc:
        return f"Backtest no disponible: {exc}"


def _compact_decision_journal_context(db):
    if not hasattr(db, "get_decision_metrics"):
        return "Decision journal no disponible."
    try:
        metrics = db.get_decision_metrics(limit=500)
    except Exception as exc:
        return f"Decision journal no disponible: {exc}"
    lines = [
        f"Decisiones journal={metrics.get('total_decisions', 0)}; BUY ejecutadas={metrics.get('accepted_buys', 0)}; bloqueos/señales={metrics.get('blocked', 0)}; IA alineada={metrics.get('ai_alignment_pct', 0):.1f}%"
    ]
    provider_stats = metrics.get("provider_stats")
    if provider_stats is not None and not provider_stats.empty:
        top = provider_stats.head(5)
        lines.append(
            "Provider stats: " + " | ".join(
                f"{r.get('provider', 'N/A')} trades={r.get('trades')} WR={r.get('win_rate')}% exp={r.get('expectancy_pct')}%"
                for _, r in top.iterrows()
            )
        )
    regime_stats = metrics.get("regime_stats")
    if regime_stats is not None and not regime_stats.empty:
        top = regime_stats.head(5)
        lines.append(
            "Regime stats: " + " | ".join(
                f"{r.get('regime', 'N/A')} trades={r.get('trades')} WR={r.get('win_rate')}% exp={r.get('expectancy_pct')}%"
                for _, r in top.iterrows()
            )
        )
    return "\n".join(lines)


def _compact_chat_context(db, limit=6):
    try:
        rows = db.get_chat_history(limit=limit)
    except Exception as exc:
        return f"Historial no disponible: {exc}"
    if not rows:
        return "Sin conversación previa relevante."
    rows = rows[-limit:]
    lines = []
    for row in rows:
        role = str(row.get("role") or "-")[:12]
        content = " ".join(str(row.get("content") or "").split())
        if not content:
            continue
        lines.append(f"{role}: {content[:260]}")
    return "\n".join(lines) if lines else "Sin conversación previa relevante."


def _compact_news_context(symbols, limit=5):
    try:
        from news_service import relevant_news_lines
        lines = relevant_news_lines(symbols, limit=limit)
    except Exception as exc:
        return f"Noticias no disponibles: {exc}"
    if not lines:
        return "Sin noticias cacheadas."
    return "\n".join(lines)


def _assistant_priority_context(db, exchange, positions, diag, risk_guards):
    lines = []
    mode = "simulación" if exchange.modo_simulacion else "REAL"
    lines.append(f"Modo={mode}; posiciones={len(positions)}; bot_state={diag.get('state', '-')}")
    if risk_guards:
        lines.append(
            f"Risk ok={risk_guards.get('ok')} daily_loss={risk_guards.get('daily_loss_pct', 0)}% "
            f"exposure={risk_guards.get('exposure_pct', 0)}% reasons={risk_guards.get('reasons', [])}"
        )
    if diag.get("skipped"):
        lines.append("Bloqueos recientes: " + ", ".join(f"{k}:{v}" for k, v in diag.get("skipped", {}).items()))
    if diag.get("hold_reasons"):
        top_hold = list(diag.get("hold_reasons", {}).items())[:3]
        lines.append("HOLD principales: " + " | ".join(f"{v}x {k}" for k, v in top_hold))
    cooldowns = diag.get("ai_provider_cooldowns") or {}
    if cooldowns:
        lines.append(
            "Cooldown IA: " + ", ".join(
                f"{k}={v.get('cooldown_in', 0)}s" for k, v in cooldowns.items()
            )
        )
    return "\n".join(lines)


def _build_assistant_context(db, exchange):
    saved_watchlist = db.get_system_status('dynamic_watchlist', '')
    watchlist = [s.strip() for s in saved_watchlist.split(',') if s.strip()] or list(config.SYMBOLS)
    focus_symbols = list(dict.fromkeys(list(db.get_open_positions().keys()) + watchlist[:12]))
    runtime_ctx = RuntimeContext(
        db=db,
        exchange=exchange,
        config=config,
        language=st.session_state.get("language", "es"),
        user_name=st.session_state.get("user_name", "User"),
        focus_symbols=focus_symbols,
        max_chars=16000,
    )
    context = build_runtime_assistant_context(runtime_ctx)
    return f"""{context}

REGLAS DE SEGURIDAD:
- No ejecutes órdenes directamente: si el usuario confirma una operación, emite el bloque [EXECUTE_ORDER]; la app creará una orden pendiente con botón de confirmación.
- En órdenes BUY puedes añadir AMOUNT_USDT opcional. En órdenes SELL puedes añadir AMOUNT_BASE o PERCENT opcional; si no lo haces, SELL venderá el máximo disponible de la posición.
- Si el usuario pide cambiar configuración, puedes proponer un bloque [CONFIG_CHANGE] con JSON. La app solo creará una tarjeta pendiente y el usuario tendrá que confirmarla con botón.
- Diferencia siempre entre posiciones del bot (open_positions) y saldos/retales del exchange.
- Si hablas de comprar, considera macro, diagnóstico daemon, slippage, riesgo por trade, posiciones disponibles y noticias.
- Prioriza primero riesgos/bloqueos actuales, después señales, después recomendaciones generales.
""".strip()


def render_assistant():
    user_name = st.session_state.get('user_name', 'User')
    db = st.session_state.db
    exchange = st.session_state.exchange
    sentiment = st.session_state.sentiment

    st.title(_('ASSISTANT_TITLE'))
    st.caption(_('ASSISTANT_CAPTION'))
    from ui_wallet import build_inventory_snapshot_text
    if st.button(_('WALLET_SNAPSHOT_BTN'), key="asst_wallet_snapshot"):
        st.session_state["_asst_wallet_clip"] = build_inventory_snapshot_text(exchange, db)
    if st.session_state.get("_asst_wallet_clip"):
        st.caption(_("WALLET_SNAPSHOT_HINT"))
        st.code(st.session_state["_asst_wallet_clip"], language=None)
    st.markdown("---")
    _render_pending_orders(db, exchange)
    _render_pending_config_changes()
    if _pending_orders() or _pending_config_changes():
        st.markdown("---")

    # Inicializar chat si está vacío
    if "messages" not in st.session_state:
        # Cargar de DB
        history = db.get_chat_history()
        if history:
            st.session_state.messages = history
        else:
            welcome_msg = f"Hello {user_name}! I am your trading copilot. How can I help you today?" if st.session_state.get('language') == 'en' else f"¡Hola {user_name}! Soy tu copiloto de trading. ¿En qué puedo ayudarte hoy?"
            st.session_state.messages = [
                {"role": "assistant", "content": welcome_msg}
            ]

    # Mostrar mensajes
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "timestamp" in msg and msg["timestamp"]:
                st.caption(f"🕒 {msg['timestamp']}")

    # Entrada de usuario
    input_placeholder = "Escribe tu consulta aquí..." if st.session_state.get('language') == 'es' else "Type your query here..."
    if prompt := st.chat_input(input_placeholder):
        # Guardar y mostrar mensaje de usuario
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        st.session_state.messages.append({"role": "user", "content": prompt, "timestamp": current_time})
        db.save_chat_message("user", prompt)
        with st.chat_message("user"):
            st.write(prompt)
            st.caption(f"🕒 {current_time}")

        # Respuesta de la IA
        with st.chat_message("assistant"):
            with st.spinner("Pensando e investigando..."):
                # 1. Preparar contexto compacto con cartera, macro, diagnóstico, noticias y decisiones.
                context = _build_assistant_context(db, exchange)
                
                # 2. Llamada a la IA (Conversacional)
                lang_name = "Spanish" if st.session_state.get('language') == 'es' else "English"
                system_prompt = f"""
                Actúa como un asesor de trading experto. Tu cliente se llama {user_name}.
                DEBES responder SIEMPRE en idioma {lang_name}.
                Si estás proponiendo una acción, pide confirmación.
                Si el usuario TE CONFIRMA claramente que ejecutes una orden (comprar o vender), DEBES incluir al final de tu respuesta este bloque exacto.
                IMPORTANTE: la aplicación NO ejecutará la orden automáticamente; solo creará una tarjeta pendiente para confirmación manual mediante botón:
                
                [EXECUTE_ORDER]
                ACTION: BUY o SELL
                SYMBOL: moneda/USDT
                AMOUNT_USDT: opcional solo para BUY
                AMOUNT_BASE: opcional solo para SELL
                PERCENT: opcional solo para SELL, 1-100
                [/EXECUTE_ORDER]

                Si no incluyes AMOUNT_BASE ni PERCENT en una orden SELL, la app interpretará que se vende el máximo disponible de esa posición.
                Si no incluyes AMOUNT_USDT en una orden BUY, la app usará el tamaño manual por RISK_PER_TRADE. El daemon automático usa además volatility sizing/ATR y guardrails.

                Si el usuario te pide cambiar la configuración, puedes proponer cambios con este bloque exacto al final.
                IMPORTANTE: la aplicación NO aplicará la configuración automáticamente; solo creará una tarjeta pendiente para confirmación manual mediante botón.
                No incluyas claves API ni secretos.

                [CONFIG_CHANGE]
                {{
                  "TRADING_EXECUTION_MODE": "auto",
                  "DECISION_MODE": "hybrid",
                  "MIN_AUTO_DECISION_SCORE": 0.62,
                  "MAX_OPEN_POSITIONS": 3,
                  "MANUAL_MAX_POSITIONS_PRIORITY": true,
                  "RISK_PER_TRADE": 0.10,
                  "VOLATILITY_SIZING_ENABLED": true,
                  "ADAPTIVE_SCORING_ENABLED": true,
                  "MAX_DAILY_LOSS_PCT": 5.0,
                  "MAX_PORTFOLIO_EXPOSURE_PCT": 85.0
                }}
                [/CONFIG_CHANGE]
                """
                
                raw_response, provider = sentiment.call_ai_hybrid(
                    system_instruction=system_prompt,
                    prompt=f"{context}\nUSUARIO DICE: {prompt}",
                    feature="assistant",
                )
                
                full_response = raw_response if raw_response else "Lo siento, no he podido procesar esa consulta."
                
                st.write(full_response)
                st.caption(f"🕒 {current_time}") 
                st.session_state.messages.append({"role": "assistant", "content": full_response, "timestamp": current_time})
                db.save_chat_message("assistant", full_response)
                
                # 3. Interceptar órdenes propuestas: quedan pendientes hasta confirmación UI
                import re
                order_matches = re.finditer(r'\[EXECUTE_ORDER\](.*?)\[/EXECUTE_ORDER\]', full_response, re.IGNORECASE | re.DOTALL)
                queued = []
                for order_match in order_matches:
                    parsed_order = _parse_order_block(order_match.group(1))
                    if not parsed_order:
                        continue
                    action = parsed_order["action"]
                    symbol = parsed_order["symbol"]
                    _queue_assistant_order(
                        action,
                        symbol,
                        full_response,
                        amount_usdt=parsed_order.get("amount_usdt"),
                        amount_base=parsed_order.get("amount_base"),
                        percent=parsed_order.get("percent"),
                    )
                    queued.append(f"{action} {symbol}")
                if queued:
                    st.warning(_("ASSIST_ORDER_QUEUED").format(", ".join(queued)))

                config_matches = re.finditer(r'\[CONFIG_CHANGE\](.*?)\[/CONFIG_CHANGE\]', full_response, re.IGNORECASE | re.DOTALL)
                queued_configs = 0
                config_errors = []
                for config_match in config_matches:
                    block = config_match.group(1)
                    try:
                        payload = parse_config_payload(block)
                        changes, warnings, blocked, errors = validate_config_payload(payload)
                    except Exception as exc:
                        config_errors.append(str(exc))
                        continue
                    if errors:
                        config_errors.extend(errors)
                        continue
                    if changes:
                        _queue_assistant_config_change(changes, warnings, blocked, full_response)
                        queued_configs += 1
                if config_errors:
                    st.error(f"{_('CONFIG_IMPORT_ERROR')}: {'; '.join(config_errors[:3])}")
                if queued_configs:
                    st.warning(_("ASSIST_CONFIG_QUEUED"))
                if queued or queued_configs:
                    st.rerun()

    # Botón para limpiar chat
    if st.sidebar.button("🧹 Limpiar Chat"):
        db.clear_chat_history()
        st.session_state.assistant_pending_orders = []
        st.session_state.assistant_pending_config_changes = []
        del st.session_state.messages
        st.rerun()
