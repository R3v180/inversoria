import streamlit as st

# Diccionario de traducciones v7.0
# Estructura: 'KEY': {'es': 'Texto en Español', 'en': 'Text in English'}

TRANSLATIONS = {
    # --- Onboarding ---
    'WELCOME_TITLE': {'es': 'Bienvenido a la Terminal Inversoria', 'en': 'Welcome to Inversoria Terminal'},
    'WELCOME_SUBTITLE': {'es': 'Configura tu experiencia de trading institucional', 'en': 'Configure your institutional trading experience'},
    'USER_NAME_LABEL': {'es': '¿Cómo quieres que te llame?', 'en': 'How should I call you?'},
    'LANG_LABEL': {'es': 'Idioma de la interfaz', 'en': 'Interface language'},
    'RISK_PROFILE_LABEL': {'es': 'Perfil de Riesgo', 'en': 'Risk Profile'},
    'RISK_CONSERVATIVE': {'es': 'Conservador (Preservar capital)', 'en': 'Conservative (Capital preservation)'},
    'RISK_MODERATE': {'es': 'Moderado (Equilibrio)', 'en': 'Moderate (Balanced)'},
    'RISK_AGGRESSIVE': {'es': 'Agresivo (Maximizar retornos)', 'en': 'Aggressive (Maximize returns)'},
    'START_BUTTON': {'es': 'Inicializar Sistema', 'en': 'Initialize System'},
    
    # --- Sidebar / App ---
    'NAV_DASHBOARD': {'es': 'Dashboard', 'en': 'Dashboard'},
    'NAV_TERMINAL': {'es': 'Terminal de Trading', 'en': 'Trading Terminal'},
    'NAV_ASSISTANT': {'es': 'Asistente IA', 'en': 'AI Assistant'},
    'NAV_HISTORY': {'es': 'Historial y Analítica', 'en': 'History & Analytics'},
    'NAV_SETTINGS': {'es': 'Configuración', 'en': 'Settings'},
    'CORE_ENGINE': {'es': 'Motor Core', 'en': 'Core Engine'},
    'STOP_BOT': {'es': 'Detener Bot', 'en': 'Stop Bot'},
    'START_BOT': {'es': 'Arrancar Bot', 'en': 'Start Bot'},
    'STATUS_ONLINE': {'es': 'ESTADO: EN LÍNEA', 'en': 'STATUS: ONLINE'},
    'STATUS_OFFLINE': {'es': 'ESTADO: APAGADO', 'en': 'STATUS: OFFLINE'},
    
    # --- Dashboard ---
    'EQUITY_TOTAL': {'es': 'Equity Total', 'en': 'Total Equity'},
    'AVAILABLE': {'es': 'Disponible', 'en': 'Available'},
    'POSITIONS': {'es': 'Posiciones', 'en': 'Positions'},
    'PNL_USD': {'es': 'PnL USD', 'en': 'PnL USD'},
    'EQUITY_CHART': {'es': 'Patrimonio', 'en': 'Equity Curve'},
    'MARKET_CHART': {'es': 'Mercado', 'en': 'Market View'},
    'ACTIVE_POSITIONS': {'es': 'Posiciones Activas', 'en': 'Active Positions'},
    'NO_POSITIONS': {'es': 'No hay posiciones abiertas', 'en': 'No open positions'},
    'MACRO_CONTEXT': {'es': 'Contexto Macro', 'en': 'Macro Context'},
    'GLOBAL_MARKETS': {'es': 'Mercados Globales', 'en': 'Global Markets'},
    'LEADING_SECTOR': {'es': 'Sector líder', 'en': 'Leading Sector'},
    'PORTFOLIO_DIST': {'es': 'Distribución del Portfolio', 'en': 'Portfolio Distribution'},
    'OPPORTUNITY_RADAR': {'es': 'Radar de Oportunidades', 'en': 'Opportunity Radar'},
    
    # --- Assistant ---
    'ASSISTANT_TITLE': {'es': 'Asistente IA', 'en': 'AI Assistant'},
    'ASSISTANT_CAPTION': {'es': 'Investiga el mercado y da órdenes.', 'en': 'Research the market and give orders.'},
    'CLEAN_CHAT': {'es': '🧹 Limpiar Chat', 'en': '🧹 Clear Chat'},
    'THINKING': {'es': 'Pensando e investigando...', 'en': 'Thinking and researching...'},
    
    # --- Tutorial steps ---
    'BTC_DOM': {'es': 'Dominancia BTC', 'en': 'BTC Dominance'},
    'MARKET_CAP': {'es': 'Cap. total 24h', 'en': 'Total Cap 24h'},
    'GLOBAL_TITLE': {'es': '🌍 Mercados Globales', 'en': '🌍 Global Markets'},
    'DOLLAR': {'es': 'Dólar (UUP)', 'en': 'Dollar (UUP)'},
    'SP500': {'es': 'S&P 500 (SPY)', 'en': 'S&P 500 (SPY)'},
    'SETTINGS_TITLE': {'es': '⚙️ Centro de Mandos - Configuración', 'en': '⚙️ Command Center - Settings'},
    'SAVE_SETTINGS': {'es': '💾 Guardar Cambios en Caliente', 'en': '💾 Save Hot Changes'},
    'RESET_GLOBAL': {'es': '🔄 Reset Global', 'en': '🔄 Global Reset'},
    'SUCCESS_SETTINGS': {'es': '¡Configuración actualizada!', 'en': 'Settings updated!'},
    'SELECT_MODE': {'es': 'SELECCIONAR MODO', 'en': 'SELECT MODE'},
    'MODE_SIM': {'es': '🤖 Simulación (Dinero Ficticio)', 'en': '🤖 Simulation (Paper Money)'},
    'MODE_REAL': {'es': '💰 REAL (Fondos Crypto.com)', 'en': '💰 REAL (Crypto.com Funds)'},
    'REAL_FUNDS_WARNING': {'es': '⚠️ CUIDADO: El bot operará con fondos reales en tu cuenta.', 'en': '⚠️ CAUTION: The bot will operate with real funds in your account.'},
    'EMERGENCY_ACTIONS': {'es': 'Acciones de Emergencia', 'en': 'Emergency Actions'},
    'SELL_ALL_USDT': {'es': '🔴 VENDER TODO A USDT', 'en': '🔴 SELL ALL TO USDT'},
    'LIQUIDATING_MSG': {'es': 'Liquidando activos a mercado...', 'en': 'Liquidating assets at market price...'},
    'SYSTEM_INTEL': {'es': 'Inteligencia del Sistema', 'en': 'System Intelligence'},
    'BACKTEST_STATUS': {'es': 'Estado del Backtest', 'en': 'Backtest Status'},
    'INVESTMENT': {'es': 'Inversión', 'en': 'Investment'},
    'REGIME_LABEL': {'es': 'RÉGIMEN', 'en': 'REGIME'},
    'BEST_STRATEGY': {'es': 'Mejor', 'en': 'Best'},
    'NO_BACKTEST_DATA': {'es': 'Sin datos de backtest. El daemon los genera automáticamente.', 'en': 'No backtest data. The daemon generates them automatically.'},
    'TUT_STEP1_TITLE': {'es': 'Métricas en tiempo real', 'en': 'Real-time Metrics'},
    'TUT_STEP1_DESC': {'es': 'Controla tu capital total y beneficio neto al instante.', 'en': 'Monitor your total capital and net profit instantly.'},
    'TUT_STEP2_TITLE': {'es': 'Ojos Globales', 'en': 'Global Eyes'},
    'TUT_STEP2_DESC': {'es': 'El bot monitoriza la Bolsa y el Dólar para evitar riesgos.', 'en': 'The bot monitors Stocks and the Dollar to avoid risks.'}
}

def _(key):
    """Retorna la traducción según el idioma en session_state"""
    lang = st.session_state.get('language', 'es')
    return TRANSLATIONS.get(key, {}).get(lang, key)
