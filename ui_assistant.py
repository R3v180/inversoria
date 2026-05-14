import streamlit as st
import time

def render_assistant():
    st.title("💬 Asistente IA Inversor")
    st.caption("Investiga el mercado, debate estrategias y da órdenes en lenguaje natural.")
    st.markdown("---")

    db = st.session_state.db
    exchange = st.session_state.exchange
    sentiment = st.session_state.sentiment

    # Inicializar chat si está vacío
    if "messages" not in st.session_state:
        # Cargar de DB
        history = db.get_chat_history()
        if history:
            st.session_state.messages = history
        else:
            st.session_state.messages = [
                {"role": "assistant", "content": "¡Hola! Soy tu copiloto de trading. ¿En qué puedo ayudarte hoy? Puedes pasarme un tema para investigar o preguntarme por tu cartera."}
            ]

    # Mostrar mensajes
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "timestamp" in msg and msg["timestamp"]:
                st.caption(f"🕒 {msg['timestamp']}")

    # Entrada de usuario
    if prompt := st.chat_input("Escribe tu consulta o comando aquí..."):
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
                    if macro:
                        macro_info = f"Régimen: {macro.get('macro_regime')}, BTC Dominancia: {macro.get('btc_dominance')}%, Sector: {macro.get('leading_sector')}"
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
                system_prompt = """
                Actúa como un asesor de trading experto.
                Si estás proponiendo una acción, pide confirmación.
                Si el usuario TE CONFIRMA claramente que ejecutes una orden (comprar o vender), DEBES incluir al final de tu respuesta este bloque exacto para que el sistema lo procese:
                
                [EXECUTE_ORDER]
                ACTION: BUY o SELL
                SYMBOL: moneda/USDT
                [/EXECUTE_ORDER]
                
                No incluyas el bloque [EXECUTE_ORDER] a menos que el usuario te haya dado una orden directa y clara.
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
                                db.close_position(symbol, current_price, "Venta Manual vía Asistente")
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
