import streamlit as st
import time
import json
import config
from assistant_runtime import RuntimeContext, build_assistant_context as build_runtime_assistant_context
from config_importer import (
    apply_config_changes,
    diff_config_changes,
    parse_config_payload,
    validate_config_payload,
)
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


def _build_assistant_context(db, exchange, user_message: str = ""):
    from assistant_runtime.intent import detect_intent_sections, parse_fetch_context_block

    saved_watchlist = db.get_system_status('dynamic_watchlist', '')
    watchlist = [s.strip() for s in saved_watchlist.split(',') if s.strip()] or list(config.SYMBOLS)
    focus_symbols = list(dict.fromkeys(list(db.get_open_positions().keys()) + watchlist[:12]))
    priority = detect_intent_sections(user_message) | parse_fetch_context_block(user_message)
    max_chars = 24000 if priority else 16000
    runtime_ctx = RuntimeContext(
        db=db,
        exchange=exchange,
        config=config,
        language=st.session_state.get("language", "es"),
        user_name=st.session_state.get("user_name", "User"),
        focus_symbols=focus_symbols,
        max_chars=max_chars,
    )
    context = build_runtime_assistant_context(
        runtime_ctx,
        priority_sections=priority if priority else None,
    )
    fetch_hint = ""
    if priority:
        fetch_hint = (
            "\n- Contexto ampliado por petición del usuario: "
            + ", ".join(sorted(priority))
        )
    return f"""{context}

REGLAS DE SEGURIDAD:
- No ejecutes órdenes directamente: si el usuario confirma una operación, emite el bloque [EXECUTE_ORDER]; la app creará una orden pendiente con botón de confirmación.
- En órdenes BUY puedes añadir AMOUNT_USDT opcional. En órdenes SELL puedes añadir AMOUNT_BASE o PERCENT opcional; si no lo haces, SELL venderá el máximo disponible de la posición.
- Si el usuario pide cambiar configuración, puedes proponer un bloque [CONFIG_CHANGE] con JSON. La app solo creará una tarjeta pendiente y el usuario tendrá que confirmarla con botón.
- Diferencia siempre entre posiciones del bot (open_positions) y saldos/retales del exchange.
- Si hablas de comprar, considera macro, diagnóstico daemon, slippage, riesgo por trade, posiciones disponibles y noticias.
- Prioriza primero riesgos/bloqueos actuales, después señales, después recomendaciones generales.
- Si necesitas más datos (logs, noticias, journal, webhooks), puedes pedir al usuario confirmación o emitir [FETCH_CONTEXT] sections=logs,news [/FETCH_CONTEXT] en tu respuesta; el siguiente turno incluirá ese contexto.{fetch_hint}
- Las claves de configuración permitidas son las de CONFIG_SCHEMA (importador/plantillas); no inventes claves nuevas.
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
            welcome_msg = _("ASSIST_WELCOME").format(user_name)
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
    if prompt := st.chat_input(_("ASSIST_CHAT_PLACEHOLDER")):
        # Guardar y mostrar mensaje de usuario
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        st.session_state.messages.append({"role": "user", "content": prompt, "timestamp": current_time})
        db.save_chat_message("user", prompt)
        with st.chat_message("user"):
            st.write(prompt)
            st.caption(f"🕒 {current_time}")

        # Respuesta de la IA
        with st.chat_message("assistant"):
            with st.spinner(_("ASSISTANT_THINKING")):
                # 1. Preparar contexto compacto con cartera, macro, diagnóstico, noticias y decisiones.
                context = _build_assistant_context(db, exchange, prompt)
                
                # 2. Llamada a la IA (Conversacional)
                lang_name = _("ASSIST_LANG_NAME_ES") if st.session_state.get('language') == 'es' else _("ASSIST_LANG_NAME_EN")
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
