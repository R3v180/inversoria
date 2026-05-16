import streamlit as st
import time
import json
import config
from i18n import _


def _pending_orders():
    if "assistant_pending_orders" not in st.session_state:
        st.session_state.assistant_pending_orders = []
    return st.session_state.assistant_pending_orders


def _queue_assistant_order(action: str, symbol: str, source_text: str = ""):
    order_id = f"{int(time.time() * 1000)}_{len(_pending_orders())}_{action}_{symbol.replace('/', '_')}"
    _pending_orders().append({
        "id": order_id,
        "action": action.upper(),
        "symbol": symbol.upper(),
        "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        "source_text": source_text[:500],
    })
    return order_id


def _remove_pending_order(order_id: str):
    st.session_state.assistant_pending_orders = [
        o for o in _pending_orders() if o.get("id") != order_id
    ]


def _add_or_update_buy_position(db, symbol: str, price: float, amount: float, reason: str):
    positions = db.get_open_positions()
    existing = positions.get(symbol)
    if existing:
        old_amount = float(existing.get("amount") or 0)
        old_entry = float(existing.get("entry_price") or price)
        total_amount = old_amount + amount
        entry = ((old_entry * old_amount) + (price * amount)) / total_amount if total_amount > 0 else price
        highest = max(float(existing.get("highest_price") or price), price)
        entry_time = existing.get("entry_time")
        amount_to_store = total_amount
    else:
        entry = price
        highest = price
        entry_time = None
        amount_to_store = amount

    extra = json.dumps({"provider": "Asistente IA", "reason": reason}, ensure_ascii=False)
    db.add_open_position(symbol, entry, highest, amount_to_store, entry_time=entry_time, extra_data=extra)
    db.save_trade(symbol, "buy", price, amount, reason, 0.0)
    db.add_log(f"{reason}: {symbol} qty={amount} @ {price}")


def _execute_pending_order(order: dict, db, exchange):
    action = order.get("action")
    symbol = order.get("symbol")
    current_price = exchange.get_ticker(symbol)
    if not current_price or current_price <= 0:
        st.error(_("ASSIST_ORDER_NO_PRICE").format(symbol))
        return

    if action == "SELL":
        positions = db.get_open_positions()
        if symbol not in positions:
            st.warning(_("ASSIST_ORDER_NO_POSITION").format(symbol))
            return
        pos = positions[symbol]
        real_amount = exchange.get_coin_balance(symbol)
        sell_amount = min(float(pos["amount"]), float(real_amount)) if real_amount > 0 else float(pos["amount"])
        res = exchange.execute_order(symbol, "sell", sell_amount, current_price, force_market=True)
        if res.get("status") in ["closed", "open", "simulated"]:
            try:
                sold = float(res.get("filled") or 0)
            except (TypeError, ValueError):
                sold = 0.0
            if sold <= 0:
                sold = float(res.get("amount") or sell_amount)
            sold = min(sold, float(pos["amount"]))
            exit_price = float(res.get("average") or res.get("price") or current_price)
            db.close_position(symbol, exit_price, _("ASSIST_ORDER_SELL_REASON"), sold_amount=sold)
            st.success(_("ASSIST_ORDER_SELL_OK").format(symbol, f"{exit_price:.6g}"))
            _remove_pending_order(order["id"])
            time.sleep(0.5)
            st.rerun()
        else:
            st.error(f"{_('ASSIST_ORDER_FAIL')}: {res.get('reason', res)}")
        return

    if action == "BUY":
        usdt_balance = exchange.get_usdt_balance()
        amount_usdt = float(usdt_balance) * float(config.RISK_PER_TRADE)
        if amount_usdt <= 1.0:
            st.error(_("ASSIST_ORDER_LOW_BALANCE").format(f"{usdt_balance:.2f}"))
            return
        amount_coin = amount_usdt / float(current_price)
        res = exchange.execute_order(symbol, "buy", amount_coin, current_price)
        if res.get("status") in ["closed", "open", "simulated"]:
            try:
                filled = float(res.get("filled") or res.get("amount") or amount_coin)
            except (TypeError, ValueError):
                filled = amount_coin
            _add_or_update_buy_position(db, symbol, float(current_price), filled, _("ASSIST_ORDER_BUY_REASON"))
            st.success(_("ASSIST_ORDER_BUY_OK").format(symbol, f"{current_price:.6g}"))
            _remove_pending_order(order["id"])
            time.sleep(0.5)
            st.rerun()
        else:
            st.error(f"{_('ASSIST_ORDER_FAIL')}: {res.get('reason', res)}")


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
                st.caption(_("ASSIST_PENDING_BUY_SIZE").format(f"{bal * float(config.RISK_PER_TRADE):.2f}"))
            elif action == "SELL":
                pos = db.get_open_positions().get(symbol)
                qty = float(pos.get("amount") or 0) if pos else 0.0
                st.caption(_("ASSIST_PENDING_SELL_SIZE").format(f"{qty:.8g}"))

            c1, c2 = st.columns(2)
            if c1.button(_("ASSIST_CONFIRM_ORDER"), key=f"confirm_{order['id']}", type="primary"):
                _execute_pending_order(order, db, exchange)
            if c2.button(_("ASSIST_CANCEL_ORDER"), key=f"cancel_{order['id']}"):
                _remove_pending_order(order["id"])
                st.rerun()


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
    if _pending_orders():
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
                # 1. Preparar contexto (Balance, Posiciones, Últimos logs y CAPAS DE INTELIGENCIA)
                balance = exchange.get_balance()
                positions = db.get_open_positions()
                logs = db.get_logs()[-10:]
                
                # Extraer conocimiento de las nuevas capas (Macro y Backtest)
                import json
                import sqlite3
                import os
                
                macro_info = "Sin datos"
                try:
                    macro = json.loads(db.get_system_status('macro_context', '{}'))
                    macro_db = db.get_all_macro_data()
                    macro_list = [f"{k}: {v['price']} ({v['change_24h']:+.2f}%)" for k, v in macro_db.items()]
                    macro_str = " | ".join(macro_list) if macro_list else "N/A"
                    
                    if macro:
                        macro_info = (
                            f"Régimen: {macro.get('macro_regime')}, "
                            f"BTC Dominancia: {macro.get('btc_dominance')}%, "
                            f"Sector Líder: {macro.get('leading_sector')}. "
                            f"Indicadores Globales: {macro_str}"
                        )
                except: pass

                backtest_info = "Sin datos"
                try:
                    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iversoria.db")
                    with sqlite3.connect(db_path, timeout=5) as conn:
                        conn.row_factory = sqlite3.Row
                        runs = conn.execute('SELECT symbol, win_rate, best_strategy FROM backtest_runs ORDER BY run_timestamp DESC LIMIT 3').fetchall()
                        if runs:
                            backtest_info = ", ".join([f"{r['symbol']} ({r['best_strategy']} WR:{r['win_rate']:.0%})" for r in runs])
                except: pass
                
                context = f"""
                CONTEXTO DE CARTERA:
                - Balance Estimado: ${balance:.2f}
                - Posiciones abiertas: {list(positions.keys())}
                
                CONTEXTO MACRO Y ESTRATEGIA (NUEVAS CAPAS):
                - MacroGlobal: {macro_info}
                - Top Backtests: {backtest_info}
                
                ÚLTIMOS EVENTOS LOG: {logs}
                """
                
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
                [/EXECUTE_ORDER]
                """
                
                raw_response, provider = sentiment.call_ai_hybrid(
                    system_instruction=system_prompt,
                    prompt=f"{context}\nUSUARIO DICE: {prompt}"
                )
                
                full_response = raw_response if raw_response else "Lo siento, no he podido procesar esa consulta."
                
                st.write(full_response)
                st.caption(f"🕒 {current_time}") 
                st.session_state.messages.append({"role": "assistant", "content": full_response, "timestamp": current_time})
                db.save_chat_message("assistant", full_response)
                
                # 3. Interceptar órdenes propuestas: quedan pendientes hasta confirmación UI
                import re
                order_matches = re.finditer(r'\[EXECUTE_ORDER\]\s*ACTION:\s*(BUY|SELL)\s*SYMBOL:\s*([A-Z0-9/-]+)\s*\[/EXECUTE_ORDER\]', full_response, re.IGNORECASE)
                queued = []
                for order_match in order_matches:
                    action = order_match.group(1).upper()
                    symbol = order_match.group(2).upper()
                    _queue_assistant_order(action, symbol, full_response)
                    queued.append(f"{action} {symbol}")
                if queued:
                    st.warning(_("ASSIST_ORDER_QUEUED").format(", ".join(queued)))
                    st.rerun()

    # Botón para limpiar chat
    if st.sidebar.button("🧹 Limpiar Chat"):
        db.clear_chat_history()
        st.session_state.assistant_pending_orders = []
        del st.session_state.messages
        st.rerun()
