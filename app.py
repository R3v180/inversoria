import streamlit as st
import time
import os
import logging
import base64

from runtime_bootstrap import ensure_i18n_module, new_database_manager

ensure_i18n_module()

from config import SYMBOLS, MODO_SIMULACION, save_settings
from exchange_helper import ExchangeHelper
from sentiment_engine import SentimentEngine
from trading_logic import TradingLogic
from simulation_profiles import (
    create_profile,
    get_active_profile,
    get_database_path_for_current_mode,
    list_profiles,
    reset_profile,
    set_active_profile,
)

# --- CONFIGURACIÓN DE STREAMLIT ---
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_LOGO = os.path.join(APP_ROOT, "assets", "inversoria_logo.png")
if os.path.exists(APP_LOGO) and "_brand_logo_b64" not in st.session_state:
    with open(APP_LOGO, "rb") as logo_file:
        st.session_state["_brand_logo_b64"] = base64.b64encode(logo_file.read()).decode("ascii")
st.set_page_config(
    page_title="InversorIA Terminal",
    layout="wide",
    page_icon=APP_LOGO if os.path.exists(APP_LOGO) else "📈",
)

# Estilos CSS para Bloomberg style
st.markdown("""
<style>
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stHeader"] {
        background-color: #0E1117;
    }
    [data-testid="stHeader"],
    [data-testid="stToolbar"] {
        visibility: hidden;
        height: 0;
    }
    .stMetric {
        background-color: #1E1E1E;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #00FFAA;
    }
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4,
    [data-testid="stAppViewContainer"] h5,
    [data-testid="stAppViewContainer"] h6 {
        color: #F9FAFB;
    }
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"],
    [data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] {
        color: #E5E7EB;
    }
    [data-testid="stMetricLabel"] p {
        color: #D1D5DB !important;
        font-weight: 700;
    }
    [data-testid="stMetricValue"] {
        color: #F9FAFB !important;
    }
    [data-testid="stMetricDelta"] {
        font-weight: 700;
    }
    [data-testid="stDataFrame"],
    [data-testid="stTable"] {
        color: #E5E7EB;
    }
    [data-testid="stAppViewContainer"] [data-testid="stButton"] button,
    [data-testid="stAppViewContainer"] button[kind="secondary"],
    [data-testid="stAppViewContainer"] button[data-testid="baseButton-secondary"] {
        background-color: #1F2937;
        color: #F9FAFB !important;
        border: 1px solid #4B5563;
        border-radius: 0.5rem;
    }
    [data-testid="stAppViewContainer"] [data-testid="stButton"] button *,
    [data-testid="stAppViewContainer"] button[kind="secondary"] *,
    [data-testid="stAppViewContainer"] button[data-testid="baseButton-secondary"] * {
        color: #F9FAFB !important;
    }
    [data-testid="stAppViewContainer"] [data-testid="stButton"] button:hover,
    [data-testid="stAppViewContainer"] button[kind="secondary"]:hover,
    [data-testid="stAppViewContainer"] button[data-testid="baseButton-secondary"]:hover {
        background-color: #374151;
        border-color: #00FFAA;
        color: #FFFFFF !important;
    }
    [data-testid="stAppViewContainer"] [data-testid="stButton"] button:disabled,
    [data-testid="stAppViewContainer"] button:disabled {
        background-color: #111827;
        color: #9CA3AF !important;
        border-color: #30363D;
        opacity: 0.75;
    }
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div,
    div[data-testid="stSidebar"] {
        background-color: #111827;
        border-right: 1px solid #30363D;
    }
    section[data-testid="stSidebar"] *,
    div[data-testid="stSidebar"] * {
        color: #E5E7EB;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {
        color: #E5E7EB !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #30363D;
    }
    section[data-testid="stSidebar"] [role="radiogroup"] label {
        background: transparent;
    }
    section[data-testid="stSidebar"] button {
        background-color: #1F2937;
        color: #F9FAFB;
        border: 1px solid #374151;
    }
    .iversoria-brand {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        padding: 0.35rem 0 0.2rem 0;
        margin-bottom: 0.35rem;
    }
    .iversoria-brand img {
        width: 38px;
        height: 38px;
        border-radius: 10px;
    }
    .iversoria-brand-title {
        font-weight: 800;
        font-size: 1.05rem;
        line-height: 1.05;
        color: #F9FAFB;
    }
    .iversoria-brand-subtitle {
        font-size: 0.68rem;
        line-height: 1.15;
        color: #9CA3AF;
        margin-top: 0.1rem;
    }
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
expected_db_path = get_database_path_for_current_mode()
if (
    'db' not in st.session_state
    or not hasattr(st.session_state.db, 'get_cost_basis')
    or getattr(st.session_state.db, 'db_path', None) != expected_db_path
):
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
from ui_news import render_news
from ui_history import render_history
from ui_settings import render_settings
from ui_assistant import render_assistant

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
    if os.path.exists(APP_LOGO):
        st.markdown(
            f"""
            <div class="iversoria-brand">
                <img src="data:image/png;base64,{st.session_state.get('_brand_logo_b64', '')}" />
                <div>
                    <div class="iversoria-brand-title">InversorIA</div>
                    <div class="iversoria-brand-subtitle">{_('WELCOME_SUBTITLE')}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown("### InversorIA")
    st.markdown("---")

    nav_items = [
        ("dashboard", f"📊 {_('NAV_DASHBOARD')}"),
        ("wallet", _('NAV_WALLET')),
        ("news", _('NAV_NEWS')),
        ("terminal", f"⚡ {_('NAV_TERMINAL')}"),
        ("assistant", f"💬 {_('NAV_ASSISTANT')}"),
        ("history", f"🧾 {_('NAV_HISTORY')}"),
        ("settings", f"⚙️ {_('NAV_SETTINGS')}"),
    ]
    nav_routes = [route for route, _ in nav_items]
    nav_labels = dict(nav_items)
    if st.session_state.get("main_nav_route") not in nav_routes:
        st.session_state.main_nav_route = "dashboard"
    selected_route = st.radio(
        "NAVEGACIÓN",
        nav_routes,
        format_func=lambda route: nav_labels.get(route, route),
        key="main_nav_route",
        label_visibility="collapsed",
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
    else:
        try:
            profiles = list_profiles()
            active_profile = get_active_profile()
            profile_options = [p["id"] for p in profiles]
            profile_labels = {
                p["id"]: f"{p.get('name', p['id'])} · {float(p.get('initial_capital', 0)):.2f} USDT"
                for p in profiles
            }
            selected_profile = st.selectbox(
                _('SIM_PROFILE_L'),
                profile_options,
                index=profile_options.index(active_profile["id"]) if active_profile["id"] in profile_options else 0,
                format_func=lambda pid: profile_labels.get(pid, pid),
                key="sim_profile_select",
            )
            if selected_profile != active_profile["id"]:
                st.session_state.db.set_system_status('is_running', 'false')
                set_active_profile(selected_profile)
                st.session_state.db = new_database_manager()
                st.session_state.exchange = ExchangeHelper(modo_simulacion=True)
                st.session_state.current_mode = True
                st.rerun()

            with st.expander(_('SIM_PROFILE_MANAGE'), expanded=False):
                sim_name = st.text_input(_('SIM_PROFILE_NAME'), value=f"Sim {time.strftime('%Y%m%d-%H%M')}", key="sim_profile_name")
                sim_capital = st.number_input(_('SIM_PROFILE_CAPITAL'), min_value=1.0, value=float(active_profile.get("initial_capital", 60.0)), step=10.0, key="sim_profile_capital")
                c_new, c_reset = st.columns(2)
                if c_new.button(_('SIM_PROFILE_CREATE'), width="stretch"):
                    st.session_state.db.set_system_status('is_running', 'false')
                    create_profile(sim_name, sim_capital, activate=True)
                    st.session_state.db = new_database_manager()
                    st.session_state.exchange = ExchangeHelper(modo_simulacion=True)
                    st.session_state.current_mode = True
                    st.rerun()
                if c_reset.button(_('SIM_PROFILE_RESET'), width="stretch"):
                    st.session_state.db.set_system_status('is_running', 'false')
                    reset_profile(active_profile["id"])
                    st.session_state.db = new_database_manager()
                    st.session_state.exchange = ExchangeHelper(modo_simulacion=True)
                    st.session_state.current_mode = True
                    st.rerun()
        except Exception as exc:
            st.caption(f"{_('SIM_PROFILE_UNAVAILABLE')}: {exc}")
        
    # Detectar cambio de modo
    if st.session_state.current_mode != is_simulacion:
        was_running = str(st.session_state.db.get_system_status('is_running', 'false')).lower() == 'true'
        try:
            armed_until = float(st.session_state.db.get_system_status('launcher_start_armed_until', '0') or 0)
            was_running = was_running or armed_until > time.time()
        except (TypeError, ValueError):
            pass
        st.session_state.current_mode = is_simulacion
        save_settings({"MODO_SIMULACION": bool(is_simulacion)})
        st.session_state.db = new_database_manager()
        st.session_state.db.set_system_status('is_running', 'true' if was_running else 'false')
        st.session_state.db.set_system_status('simulacion', 'true' if is_simulacion else 'false')
        st.session_state.exchange = ExchangeHelper(modo_simulacion=is_simulacion)
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
if selected_route == "dashboard":
    from streamlit_autorefresh import st_autorefresh
    # Refresca cada 30 segundos (30000 ms), máximo 1000 veces
    st_autorefresh(interval=30_000, limit=1000, key="dashboard_refresh")
    render_dashboard()
elif selected_route == "wallet":
    render_wallet()
elif selected_route == "news":
    render_news()
elif selected_route == "terminal":
    if st.session_state.get('terminal_refresh', False):
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=30_000, limit=1000, key="terminal_refresh_timer")
    render_terminal()
elif selected_route == "assistant":
    render_assistant()
elif selected_route == "history":
    render_history()
elif selected_route == "settings":
    render_settings()
