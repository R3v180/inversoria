import streamlit as st
import time
import os
import logging

from runtime_bootstrap import ensure_i18n_module, new_database_manager

ensure_i18n_module()

from config import SYMBOLS, MODO_SIMULACION
from exchange_helper import ExchangeHelper
from sentiment_engine import SentimentEngine
from trading_logic import TradingLogic

# --- CONFIGURACIÓN DE STREAMLIT ---
st.set_page_config(page_title="InversorIA Terminal", layout="wide", page_icon="📈")

# Estilos CSS para Bloomberg style
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .stMetric { background-color: #1E1E1E; padding: 10px; border-radius: 5px; border-left: 4px solid #00FFAA; }
    div[data-testid="stSidebar"] { background-color: #161A22; border-right: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# Configuración de logging permanente
logging.basicConfig(
    filename='iversoria_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- INICIALIZACIÓN ---
# Recrear DB si el código se actualizó en caliente (Streamlit conserva instancias viejas en session_state)
if 'db' not in st.session_state or not hasattr(st.session_state.db, 'get_cost_basis'):
    st.session_state.db = new_database_manager()

if 'exchange' not in st.session_state:
    db_sim_str = st.session_state.db.get_system_status('simulacion', 'true')
    is_sim = str(db_sim_str).lower() == 'true'
    st.session_state.current_mode = is_sim
    st.session_state.exchange = ExchangeHelper(modo_simulacion=is_sim)
    st.session_state.sentiment = SentimentEngine()
    st.session_state.logic = TradingLogic()

def log_message(msg):
    st.session_state.db.add_log(msg)
    logging.info(msg)

# --- ENRUTADOR UI ---
from i18n import _
from ui_onboarding import render_onboarding, is_onboarding_done
from ui_dashboard import render_dashboard
from ui_terminal import render_terminal
from ui_wallet import render_wallet
from ui_history import render_history
from ui_settings import render_settings
from ui_assistant import render_assistant
from streamlit_option_menu import option_menu

# --- CONTROL DE FLUJO (ONBOARDING) ---
if not is_onboarding_done():
    render_onboarding()
    st.stop() # Detiene la ejecución del resto del script

# Una vez completado, inyectamos los datos en el motor de sentimiento
st.session_state.sentiment.set_user_context(
    st.session_state.get('user_name', 'User'),
    st.session_state.get('language', 'es')
)

with st.sidebar:
    st.markdown("### 🚀 InversorIA")
    st.markdown(_('WELCOME_SUBTITLE'))
    st.markdown("---")
    
    selected = option_menu(
        menu_title=None,
        options=[_('NAV_DASHBOARD'), _('NAV_WALLET'), _('NAV_TERMINAL'), _('NAV_ASSISTANT'), _('NAV_HISTORY'), _('NAV_SETTINGS')],
        icons=["pie-chart-fill", "wallet2", "graph-up-arrow", "chat-dots-fill", "journal-text", "gear-fill"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#00FFAA", "font-size": "18px"}, 
            "nav-link": {"font-size": "15px", "text-align": "left", "margin":"0px"},
            "nav-link-selected": {"background-color": "#1E1E1E"},
        }
    )
    
    st.markdown("---")
    st.markdown(f"### 🤖 { _('CORE_ENGINE') }")
    
    is_running_str = st.session_state.db.get_system_status('is_running', 'false')
    is_running = str(is_running_str).lower() == 'true'
    
    if st.button(_('STOP_BOT') if is_running else _('START_BOT'), width='stretch'):
        new_status = not is_running
        st.session_state.db.set_system_status('is_running', 'true' if new_status else 'false')
        st.rerun()
    
    status_color = "#00FFAA" if is_running else "#FF4444"
    status_text = _('STATUS_ONLINE') if is_running else _('STATUS_OFFLINE')
    st.markdown(f"<div style='text-align:center; padding:10px; border-radius:5px; background:#1E1E1E; color:{status_color}; font-weight:bold;'>{status_text}</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.subheader(f"⚙️ { _('NAV_SETTINGS') }")
    
    # Selector de Idioma v7.0
    lang_options = ["Español 🇪🇸", "English 🇺🇸"]
    current_lang_idx = 0 if st.session_state.get('language') == 'es' else 1
    new_lang_sel = st.radio("IDIOMA / LANGUAGE", lang_options, index=current_lang_idx, horizontal=True)
    new_lang_code = 'es' if "Español" in new_lang_sel else 'en'
    
    if st.session_state.get('language') != new_lang_code:
        st.session_state.language = new_lang_code
        st.session_state.db.set_system_status('language', new_lang_code)
        st.rerun()

    st.markdown("<br/>", unsafe_allow_html=True)
    default_mode_index = 0 if st.session_state.current_mode else 1
    modo_seleccionado = st.radio(_('SELECT_MODE'), [_('MODE_SIM'), _('MODE_REAL')], index=default_mode_index)
    
    is_simulacion = modo_seleccionado == _('MODE_SIM')
    
    if not is_simulacion:
        st.warning(_('REAL_FUNDS_WARNING'))
        
    # Detectar cambio de modo
    if st.session_state.current_mode != is_simulacion:
        st.session_state.current_mode = is_simulacion
        st.session_state.db.set_system_status('is_running', 'false')
        st.session_state.db.set_system_status('simulacion', 'true' if is_simulacion else 'false')
        st.session_state.exchange = ExchangeHelper(modo_simulacion=is_simulacion)
        st.session_state.db.clear_open_positions()
        st.rerun()
        
    with st.expander(f"⚠️ { _('EMERGENCY_ACTIONS') }", expanded=False):
        if st.button(_('SELL_ALL_USDT')):
            with st.spinner(_('LIQUIDATING_MSG')):
                resultados = st.session_state.exchange.liquidate_all_to_usdt()
                
                # Procesar éxitos
                for exito in resultados.get("exitos", []):
                    sym = exito['symbol']
                    qty = exito['amount']
                    price = exito['price']
                    st.session_state.db.save_trade(sym, 'sell', price, qty, "Liquidación Manual", 0.0)
                    st.session_state.db.remove_open_position(sym)
                    log_message(f"✅ Liquidado: {qty:.4f} {sym} a {price:.2f}")
                    st.success(f"Liquidado: {sym}")
                
                # Procesar fallos
                for fallo in resultados.get("fallos", []):
                    sym = fallo['symbol']
                    razon = fallo['reason']
                    log_message(f"❌ Fallo al liquidar {sym}: {razon}")
                    st.error(f"Fallo en {sym}: {razon}")
                
                time.sleep(2)
                st.rerun()

# RENDERIZAR VISTAS
if selected == _('NAV_DASHBOARD'):
    from streamlit_autorefresh import st_autorefresh
    # Refresca cada 30 segundos (30000 ms), máximo 1000 veces
    st_autorefresh(interval=30_000, limit=1000, key="dashboard_refresh")
    render_dashboard()
elif selected == _('NAV_WALLET'):
    render_wallet()
elif selected == _('NAV_TERMINAL'):
    render_terminal()
    # Auto-refrescar si el interruptor del terminal está activado
    if st.session_state.get('terminal_refresh', False):
        time.sleep(30)
        st.rerun()
elif selected == _('NAV_ASSISTANT'):
    render_assistant()
elif selected == _('NAV_HISTORY'):
    render_history()
elif selected == _('NAV_SETTINGS'):
    render_settings()
