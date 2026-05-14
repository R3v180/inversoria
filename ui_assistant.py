import streamlit as st
import json
import time
import pandas as pd

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

    # Entrada de usuario
    if prompt := st.chat_input("Escribe tu consulta o comando aquí..."):
        # Guardar y mostrar mensaje de usuario
        st.session_state.messages.append({"role": "user", "content": prompt})
        db.save_chat_message("user", prompt)
        with st.chat_message("user"):
            st.write(prompt)

        # Respuesta de la IA
        with st.chat_message("assistant"):
            with st.spinner("Pensando e investigando..."):
                # 1. Preparar contexto (Balance, Posiciones, Últimos logs)
                balance = exchange.get_balance()
                positions = db.get_open_positions()
                logs = db.get_logs()[-10:]
                
                context = f"""
                CONTEXTO ACTUAL:
                - Balance USDT: {balance}
                - Posiciones abiertas: {list(positions.keys())}
                - Últimos eventos: {logs}
                """
                
                # 2. Llamada a la IA (Conversacional)
                # Por simplicidad ahora, usamos un prompt enriquecido. 
                # En v5.1 implementaremos Function Calling real de Google.
                response = sentiment.call_ai_hybrid(
                    prompt_type="DECISION", # Reutilizamos o creamos uno nuevo
                    input_data=f"{context}\nUSUARIO DICE: {prompt}\nINSTRUCCIÓN: Actúa como un asesor. Si el usuario te pide comprar o vender, analiza si es buena idea y propón la acción exacta. NO ejecutes nada aún."
                )
                
                full_response = response.get('reasoning', "Lo siento, no he podido procesar esa consulta.")
                
                st.write(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                db.save_chat_message("assistant", full_response)
                
        st.rerun()

    # Botón para limpiar chat
    if st.sidebar.button("🧹 Limpiar Chat"):
        db.clear_chat_history()
        del st.session_state.messages
        st.rerun()
