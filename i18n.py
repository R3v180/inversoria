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
    'CASH': {'es': 'Liquidez', 'en': 'Cash/USDT'},
    
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
    'NO_BACKTEST_DATA': {'es': 'Sin datos de backtest. El daemon los genera automáticamente.', 'en': 'No backtest data. The daemon generates them automatically.'},
    
    # --- Terminal ---
    'SELECT_ASSET': {'es': 'Seleccionar Activo', 'en': 'Select Asset'},
    'TECH_ANALYSIS': {'es': 'Análisis Técnico', 'en': 'Technical Analysis'},
    'AI_CONSOLE': {'es': 'Consola IA', 'en': 'AI Console'},
    'REGIME': {'es': 'Régimen', 'en': 'Regime'},
    'STRATEGY': {'es': 'Estrategia', 'en': 'Strategy'},
    'CONFIDENCE': {'es': 'Confianza', 'en': 'Confidence'},
    'LAST_INTERPRETATION': {'es': 'Última interpretación', 'en': 'Last AI Interpretation'},
    'LIVE_LOGS': {'es': 'Registro de Operaciones (Live)', 'en': 'Live Trading Logs'},
    
    # --- History ---
    'TRADES_CLOSED': {'es': 'Trades Cerrados', 'en': 'Closed Trades'},
    'BEST_TRADE': {'es': 'Mejor Trade', 'en': 'Best Trade'},
    'EVOLUTION_CURVE': {'es': 'Curva de Evolución', 'en': 'Equity Evolution'},
    'NO_TRADES_MSG': {'es': 'Aún no hay ventas registradas.', 'en': 'No sales recorded yet.'},
    'TRADING_JOURNAL': {'es': 'Diario de Trading', 'en': 'Trading Journal'},
    'BUY': {'es': 'COMPRA', 'en': 'BUY'},
    'SELL': {'es': 'VENTA', 'en': 'SELL'},
    
    # --- Settings Tabs ---
    'TAB_CONNECTIONS': {'es': '🔑 Conexiones', 'en': '🔑 Connections'},
    'TAB_RISK': {'es': '🛡️ Riesgo & Rotación', 'en': '🛡️ Risk & Rotation'},
    'TAB_AI': {'es': '🧠 Inteligencia (Prompts)', 'en': '🧠 Intelligence (Prompts)'},
    'API_CREDENTIALS': {'es': 'APIs y Credenciales', 'en': 'APIs & Credentials'},
    'CAPITAL_MGMT': {'es': 'Gestión de Capital', 'en': 'Capital Management'},
    'ROTATION_MODULE': {'es': 'Módulo de Rotación Inteligente', 'en': 'Smart Rotation Module'},
    'LINGUISTIC_BRAIN': {'es': 'Cerebro Lingüístico (Prompts)', 'en': 'Linguistic Brain (Prompts)'},
    'INITIAL_CAPITAL': {'es': 'Capital Inicial (USD)', 'en': 'Initial Capital (USD)'},
    'MAX_POSITIONS_L': {'es': 'Máximo Posiciones', 'en': 'Max Positions'},
    'RISK_PER_TRADE_L': {'es': 'Riesgo por Trade (%)', 'en': 'Risk per Trade (%)'},
    'MIN_PROFIT_L': {'es': 'Profit Mínimo Objetivo (%)', 'en': 'Min Profit Target (%)'},
    'ENABLE_ROTATION': {'es': 'Activar Rotación de Capital', 'en': 'Enable Capital Rotation'},
    'MIN_PROFIT_ROT': {'es': 'Min. Profit para Rotar (%)', 'en': 'Min. Profit to Rotate (%)'},
    'CONF_GAP': {'es': 'Gap de Confianza Necesario', 'en': 'Confidence Gap Required'},
    'MIN_NEW_CONF': {'es': 'Confianza Mínima Nueva', 'en': 'Min. New Confidence'},
    'AI_FREQ': {'es': 'Frecuencia Análisis IA (minutos)', 'en': 'AI Analysis Frequency (min)'},
    'PROMPT_WARNING': {'es': '⚠️ Cambiar los prompts afectará la lógica de la IA.', 'en': '⚠️ Changing prompts will directly affect AI logic.'},
    'NO_ANALYSIS': {'es': 'Sin análisis específico para este activo aún.', 'en': 'No specific analysis for this asset yet.'},
    'DB_NOT_INIT': {'es': 'Base de datos no inicializada.', 'en': 'Database not initialized.'},
    'HISTORY_EMPTY': {'es': 'El historial está vacío.', 'en': 'History is empty.'},
    'LOADING_DATA': {'es': 'Cargando datos históricos...', 'en': 'Loading historical data...'},
    'DATA_ERROR': {'es': 'No se pudieron cargar datos.', 'en': 'Could not load data.'},
    
    'TUT_STEP1_TITLE': {'es': 'Métricas en tiempo real', 'en': 'Real-time Metrics'},
    'TUT_STEP1_DESC': {'es': 'Controla tu capital total y beneficio neto al instante.', 'en': 'Monitor your total capital and net profit instantly.'},
    'TUT_STEP2_TITLE': {'es': 'Ojos Globales', 'en': 'Global Eyes'},
    'TUT_STEP2_DESC': {'es': 'El bot monitoriza la Bolsa y el Dólar para evitar riesgos.', 'en': 'The bot monitors Stocks and the Dollar to avoid risks.'},
    
    # --- Daemon Logs ---
    'LOG_DAEMON_INIT': {'es': 'Bot Daemon v5.1 [INTELLIGENCE UPGRADE] Inicializado.', 'en': 'Bot Daemon v5.1 [INTELLIGENCE UPGRADE] Initialized.'},
    'LOG_SCANNING_RADAR': {'es': '🛰️ Escaneando radar de mercado (Top Volumen)...', 'en': '🛰️ Scanning market radar (Top Volume)...'},
    'LOG_WATCHLIST_UPDATED': {'es': '✅ Watchlist actualizada', 'en': '✅ Watchlist updated'},
    'LOG_BACKTEST_START': {'es': '📊 Iniciando backtest semanal automático...', 'en': '📊 Starting automatic weekly backtest...'},
    'LOG_BACKTEST_DONE': {'es': '📊 Backtest semanal completado.', 'en': '📊 Weekly backtest completed.'},
    'LOG_MODE_CHANGED': {'es': 'Modo cambiado a', 'en': 'Mode changed to'},
    'LOG_BUY': {'es': '🚀 COMPRA', 'en': '🚀 BUY'},
    'LOG_SELL': {'es': '💰 VENTA', 'en': '💰 SELL'},
    'LOG_REASON': {'es': 'Motivo', 'en': 'Reason'},
    'LOG_ROTATION': {'es': '🔄 ROTACIÓN', 'en': '🔄 ROTATION'},
    'LOG_YEARS': {'es': 'años', 'en': 'years'},
    'LOG_BEST_STRAT_IS': {'es': 'mejor estrategia =', 'en': 'best strategy ='},
    'LOG_INITIAL_REAL': {'es': '🚀 Saldo inicial REAL fijado en:', 'en': '🚀 Initial REAL balance set at:'},
    'LOG_POS_ADOPTED': {'es': 'Posición adoptada', 'en': 'Position adopted'},
    'LOG_INSUFFICIENT': {'es': '⚠️ Balance USDT insuficiente', 'en': '⚠️ Insufficient USDT balance'},
    'LOG_SACRIFICING': {'es': 'Sacrificando', 'en': 'Sacrificing'},
    'LOG_FOR': {'es': 'por', 'en': 'for'},
    'LOG_EXECUTED': {'es': 'ejecutada', 'en': 'executed'},
    'LOG_SOLD_AT': {'es': 'vendido a', 'en': 'sold at'},
}

def _(key, lang=None):
    """Retorna la traducción según el idioma (Streamlit o Manual)"""
    if not lang:
        try:
            import streamlit as st
            lang = st.session_state.get('language', 'es')
        except:
            lang = 'es' # Default si falla streamlit
    return TRANSLATIONS.get(key, {}).get(lang, key)
