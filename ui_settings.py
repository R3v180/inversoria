import streamlit as st
import json
import os
from config import get_setting, USER_SETTINGS_FILE, save_settings, reset_to_defaults, DEFAULT_SETTINGS

def render_settings():
    st.title("⚙️ Centro de Mandos - Configuración")
    
    st.markdown("""
    <div style='background: rgba(255, 255, 255, 0.05); padding: 20px; border-radius: 10px; border: 1px solid rgba(0, 255, 127, 0.2); margin-bottom: 20px;'>
        Ajusta los parámetros de inteligencia y riesgo de Iversoria. Los cambios se guardarán automáticamente en <code>user_settings.json</code>.
    </div>
    """, unsafe_allow_html=True)

    # Botón de Reset fuera del formulario para acción inmediata
    col_reset1, col_reset2 = st.columns([4, 1])
    with col_reset2:
        if st.button("🔄 Reset Global", help="Restaurar toda la configuración sugerida por Iversoria", type="secondary"):
            reset_to_defaults()
            st.rerun()

    with st.form("settings_form"):
        tab1, tab2, tab3 = st.tabs(["🔑 Conexiones", "🛡️ Riesgo & Rotación", "🧠 Inteligencia (Prompts)"])
        
        with tab1:
            st.subheader("APIs y Credenciales")
            crypto_api = st.text_input("Crypto.com API Key", value=get_setting('CRYPTO_API_KEY', ''), type="password")
            crypto_sec = st.text_input("Crypto.com API Secret", value=get_setting('CRYPTO_API_SECRET', ''), type="password")
            groq_api = st.text_input("Groq API Key", value=get_setting('GROQ_API_KEY', ''), type="password")
            google_api = st.text_input("Google AI Key (Gemini)", value=get_setting('GOOGLE_API_KEY', ''), type="password")
            sambanova_api = st.text_input("SambaNova API Key", value=get_setting('SAMBANOVA_API_KEY', ''), type="password")
            coindesk_api = st.text_input("News API Key", value=get_setting('COINDESK_API_KEY', ''), type="password")

        with tab2:
            st.subheader("Gestión de Capital")
            col1, col2 = st.columns(2)
            with col1:
                modo_sim = st.checkbox("Modo Simulación", value=get_setting('MODO_SIMULACION', True, bool))
                presupuesto = st.number_input("Capital Inicial (USD)", value=get_setting('PRESUPUESTO_INICIAL', 60.0, float))
            with col2:
                max_pos = st.number_input("Máximo Posiciones", min_value=1, max_value=10, value=get_setting('MAX_OPEN_POSITIONS', 3, int))
                riesgo = st.slider("Riesgo por Trade (%)", 1, 100, int(get_setting('RISK_PER_TRADE', 0.1, float)*100))
                min_profit = st.number_input(
                    "Profit Mínimo Objetivo (%)",
                    min_value=0.1,
                    max_value=10.0,
                    value=get_setting('MIN_PROFIT_NET', 1.0, float),
                    step=0.1,
                    help="El bot solo considerará rentable una operación si supera este % de beneficio"
                )
            
            st.markdown("---")
            st.subheader("Módulo de Rotación Inteligente")
            rot_en = st.checkbox("Activar Rotación de Capital", value=get_setting('ROTATION_ENABLED', True, bool))
            col3, col4 = st.columns(2)
            with col3:
                rot_prof = st.slider("Min. Profit para Rotar (%)", 0.0, 5.0, get_setting('ROTATION_MIN_PROFIT', 0.35, float), step=0.05)
                rot_gap = st.slider("Gap de Confianza Necesario", 0.05, 0.50, get_setting('ROTATION_CONFIDENCE_GAP', 0.20, float), step=0.05)
            with col4:
                rot_min_new = st.slider("Confianza Mínima Nueva", 0.60, 0.95, get_setting('ROTATION_MIN_NEW_CONFIDENCE', 0.85, float), step=0.05)
                ai_interval_min = st.slider("Frecuencia Análisis IA (minutos)", 5, 120, int(get_setting('AI_ANALYSIS_INTERVAL', 1200, int)/60))

        with tab3:
            st.subheader("Cerebro Lingüístico (Prompts)")
            st.warning("⚠️ Cambiar los prompts afectará directamente la lógica de decisión de la IA.")
            
            p_sent = st.text_area("Prompt Análisis Sentiment", value=get_setting('PROMPT_SENTIMENT', DEFAULT_SETTINGS['PROMPT_SENTIMENT']), height=100)
            p_dec = st.text_area("Prompt Motor de Decisión (JSON)", value=get_setting('PROMPT_DECISION', DEFAULT_SETTINGS['PROMPT_DECISION']), height=100)
            p_cur = st.text_area("Prompt Radar (Curación)", value=get_setting('PROMPT_CURATION', DEFAULT_SETTINGS['PROMPT_CURATION']), height=100)

        # Guardar todo
        submit = st.form_submit_button("💾 Guardar Cambios en Caliente", type="primary", use_container_width=True)
        
        if submit:
            new_data = {
                "CRYPTO_API_KEY": crypto_api,
                "CRYPTO_API_SECRET": crypto_sec,
                "GROQ_API_KEY": groq_api,
                "GOOGLE_API_KEY": google_api,
                "SAMBANOVA_API_KEY": sambanova_api,
                "COINDESK_API_KEY": coindesk_api,
                "MODO_SIMULACION": modo_sim,
                "PRESUPUESTO_INICIAL": float(presupuesto),
                "MAX_OPEN_POSITIONS": int(max_pos),
                "MIN_PROFIT_NET": float(min_profit),
                "RISK_PER_TRADE": riesgo / 100.0,
                "ROTATION_ENABLED": rot_en,
                "ROTATION_MIN_PROFIT": float(rot_prof),
                "ROTATION_CONFIDENCE_GAP": float(rot_gap),
                "ROTATION_MIN_NEW_CONFIDENCE": float(rot_min_new),
                "AI_ANALYSIS_INTERVAL": int(ai_interval_min * 60),
                "PROMPT_SENTIMENT": p_sent,
                "PROMPT_DECISION": p_dec,
                "PROMPT_CURATION": p_cur
            }
            save_settings(new_data)
            st.success("¡Configuración actualizada! El Bot Daemon captará los cambios en el próximo ciclo.")
            st.balloons()
