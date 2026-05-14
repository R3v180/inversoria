import streamlit as st
import time
from i18n import _

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
                Si el usuario TE CONFIRMA claramente que ejecutes una orden (comprar o vender), DEBES incluir al final de tu respuesta este bloque exacto para que el sistema lo procese:
                
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
                
                # 3. Interceptar y ejecutar órdenes
                import re
                order_matches = re.finditer(r'\[EXECUTE_ORDER\]\s*ACTION:\s*(BUY|SELL)\s*SYMBOL:\s*([A-Z0-9/-]+)\s*\[/EXECUTE_ORDER\]', full_response, re.IGNORECASE)
                for order_match in order_matches:
                    action = order_match.group(1).upper()
                    symbol = order_match.group(2).upper()
                    
                    st.info(f"⚡ Procesando orden automática del asistente: {action} {symbol}")
                    current_price = exchange.get_ticker(symbol)
                    
                    if action == 'SELL':
                        if symbol in positions:
                            pos = positions[symbol]
                            real_amount = exchange.get_coin_balance(symbol)
                            sell_amount = min(pos['amount'], real_amount) if real_amount > 0 else pos['amount']
                            
                            res = exchange.execute_order(symbol, 'sell', sell_amount, current_price)
                            if res.get('status') in ['closed', 'open', 'simulated']:
                                try:
                                    sold = float(res.get('filled') or 0)
                                except (TypeError, ValueError):
                                    sold = 0.0
                                if sold <= 0:
                                    sold = float(sell_amount)
                                sold = min(sold, float(pos['amount']))
                                db.close_position(symbol, current_price, "Venta Manual vía Asistente", sold_amount=sold)
                                st.success(f"✅ Venta ejecutada exitosamente: {symbol} a {current_price}")
                                time.sleep(1) # Pausa breve para asegurar que el balance USDT se actualiza en el exchange
                            else:
                                st.error(f"❌ Fallo al ejecutar venta: {res.get('reason')}")
                        else:
                            st.warning(f"⚠️ No tienes posiciones abiertas en {symbol}")
                            
                    elif action == 'BUY':
                        usdt_balance = exchange.get_usdt_balance()
                        import config
                        amount_usdt = usdt_balance * config.RISK_PER_TRADE
                        if amount_usdt > 1.0:
                            amount_coin = amount_usdt / current_price
                            res = exchange.execute_order(symbol, 'buy', amount_coin, current_price)
                            if res.get('status') in ['closed', 'open', 'simulated']:
                                db.add_open_position(symbol, current_price, current_price, amount_coin, extra_data='{"provider": "Asistente IA"}')
                                st.success(f"✅ Compra ejecutada exitosamente: {symbol} a {current_price}")
                            else:
                                st.error(f"❌ Fallo al ejecutar compra: {res.get('reason')}")
                        else:
                            st.error(f"⚠️ Balance USDT insuficiente para ejecutar compra. Balance: {usdt_balance}")

    # Botón para limpiar chat
    if st.sidebar.button("🧹 Limpiar Chat"):
        db.clear_chat_history()
        del st.session_state.messages
        st.rerun()
