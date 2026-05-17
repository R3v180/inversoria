import os
import json
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

USER_SETTINGS_FILE = 'user_settings.json'

DEFAULT_SETTINGS = {
    'MODO_SIMULACION': True,
    'PRESUPUESTO_INICIAL': 60.0,
    'MONEDAS': 'BTC/USDT,ETH/USDT,SOL/USDT,ADA/USDT,DOT/USDT',
    'RISK_PER_TRADE': 0.10,
    'MAX_OPEN_POSITIONS': 5,
    # Control operativo: "auto" ejecuta ordenes; "consultive" solo analiza y registra.
    'TRADING_EXECUTION_MODE': 'auto',
    # Cerebro de decision: "hybrid" fusiona reglas + IA; "ai_aggressive" da mas peso a IA; "rules" no usa IA para decidir.
    'DECISION_MODE': 'hybrid',
    'MIN_AUTO_DECISION_SCORE': 0.62,
    # False = límite por escala de capital (<100→3, etc.). True = usa solo "Máximo Posiciones".
    'MANUAL_MAX_POSITIONS_PRIORITY': False,
    'MIN_PROFIT_NET': 1.0,
    'STOP_LOSS_PERCENT': 3.0,
    'MAX_DAILY_LOSS_PCT': 5.0,
    'MAX_PORTFOLIO_EXPOSURE_PCT': 85.0,
    'VOLATILITY_SIZING_ENABLED': True,
    'MAX_POSITION_RISK_PCT': 1.0,
    'MAX_VOLATILITY_POSITION_MULTIPLIER': 1.0,
    'MIN_POSITION_USDT': 1.0,
    'MAX_SYMBOL_EXPOSURE_PCT': 30.0,
    'MAX_ALT_EXPOSURE_PCT': 75.0,
    'MAX_BUCKET_EXPOSURE_PCT': 45.0,
    'METRICS_ROLLING_WINDOW': 30,
    'PORTFOLIO_BUCKETS': {
        'BTC': ['BTC'],
        'ETH': ['ETH'],
        'LAYER1': ['SOL', 'ADA', 'AVAX', 'DOT', 'ATOM', 'NEAR', 'SUI', 'APT', 'XLM', 'XRP'],
        'DEFI': ['AAVE', 'UNI', 'LINK', 'RUNE', 'MKR', 'LDO', 'CRV', 'SNX'],
        'AI': ['FET', 'TAO', 'RENDER', 'RNDR', 'GRT', 'OCEAN', 'AGIX'],
        'MEME': ['DOGE', 'SHIB', 'PEPE', 'BONK', 'WIF', 'FLOKI'],
    },
    # Parámetros de Rotación
    'ROTATION_ENABLED': True,
    'ROTATION_MIN_PROFIT': 0.35, # Beneficio mínimo para rotar
    'ROTATION_CONFIDENCE_GAP': 0.20, # Diferencia de confianza necesaria
    'ROTATION_MIN_NEW_CONFIDENCE': 0.85, # Confianza mínima de la nueva señal
    # Prompts de IA
    'PROMPT_SENTIMENT': "Eres un analista senior de criptomonedas. Responde solo BULLISH, BEARISH o NEUTRAL y una frase corta.",
    'PROMPT_DECISION': "Eres un analista senior de criptomonedas. Responde SOLO con JSON válido.",
    'PROMPT_CURATION': "Analiza esta lista de símbolos con alto volumen. Devuelve los nombres (separados por comas) de las monedas que tengan un proyecto sólido o sean tendencia legítima. Incluye Blue Chips y proyectos con utilidad. Solo ELIMINA memecoins sin volumen o estafas evidentes. Queremos una lista amplia (aprox 15-20 monedas).",
    'AI_ANALYSIS_INTERVAL': 1200, # 20 minutos por defecto
    # Comisión estimada por lado (compra y venta) para simular PnL en cartera — Crypto.com spot ~0.075–0.4%
    'TRADING_FEE_RATE': 0.001,
    # Protección de spread/slippage antes de enviar órdenes a mercado
    'BUY_SLIPPAGE_LIMIT': 0.005,   # 0.5%
    'SELL_SLIPPAGE_LIMIT': 0.010,  # 1.0%
}

def get_setting(key, default, cast_type=str):
    settings = {}
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception: pass
            
    val = settings.get(key, os.getenv(key, default))
        
    try:
        if cast_type == bool:
            if isinstance(val, bool): return val
            return str(val).lower() in ('true', '1', 't')
        return cast_type(val)
    except: return default

def save_settings(new_settings):
    settings = {}
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except: pass
    settings.update(new_settings)
    with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4)

def reset_to_defaults():
    with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_SETTINGS, f, indent=4)
    return DEFAULT_SETTINGS

# --- Carga de Variables Activas ---
MODO_SIMULACION = get_setting('MODO_SIMULACION', True, bool)
PRESUPUESTO_INICIAL = get_setting('PRESUPUESTO_INICIAL', 60.0, float)
CRYPTO_API_KEY = get_setting('CRYPTO_API_KEY', '')
CRYPTO_API_SECRET = get_setting('CRYPTO_API_SECRET', '')
GROQ_API_KEY = get_setting('GROQ_API_KEY', '')
GOOGLE_API_KEY = get_setting('GOOGLE_API_KEY', '')
SAMBANOVA_API_KEY = get_setting('SAMBANOVA_API_KEY', '')
COINDESK_API_KEY = get_setting('COINDESK_API_KEY', '')

monedas_raw = get_setting('MONEDAS', 'BTC/USDT,ETH/USDT,SOL/USDT,ADA/USDT,DOT/USDT')
SYMBOLS = [s.strip() for s in (monedas_raw if isinstance(monedas_raw, list) else monedas_raw.split(',')) if s.strip()]

RISK_PER_TRADE = get_setting('RISK_PER_TRADE', 0.10, float)
MAX_OPEN_POSITIONS = get_setting('MAX_OPEN_POSITIONS', 5, int)
TRADING_EXECUTION_MODE = get_setting('TRADING_EXECUTION_MODE', 'auto').lower()
DECISION_MODE = get_setting('DECISION_MODE', 'hybrid').lower()
MIN_AUTO_DECISION_SCORE = get_setting('MIN_AUTO_DECISION_SCORE', 0.62, float)
PROFIT_OBJETIVO = get_setting('MIN_PROFIT_NET', 1.0, float) / 100.0
STOP_LOSS_PCT = get_setting('STOP_LOSS_PERCENT', 3.0, float) / 100.0
MAX_DAILY_LOSS_PCT = get_setting('MAX_DAILY_LOSS_PCT', 5.0, float) / 100.0
MAX_PORTFOLIO_EXPOSURE_PCT = get_setting('MAX_PORTFOLIO_EXPOSURE_PCT', 85.0, float) / 100.0
VOLATILITY_SIZING_ENABLED = get_setting('VOLATILITY_SIZING_ENABLED', True, bool)
MAX_POSITION_RISK_PCT = get_setting('MAX_POSITION_RISK_PCT', 1.0, float) / 100.0
MAX_VOLATILITY_POSITION_MULTIPLIER = get_setting('MAX_VOLATILITY_POSITION_MULTIPLIER', 1.0, float)
MIN_POSITION_USDT = get_setting('MIN_POSITION_USDT', 1.0, float)
MAX_SYMBOL_EXPOSURE_PCT = get_setting('MAX_SYMBOL_EXPOSURE_PCT', 30.0, float) / 100.0
MAX_ALT_EXPOSURE_PCT = get_setting('MAX_ALT_EXPOSURE_PCT', 75.0, float) / 100.0
MAX_BUCKET_EXPOSURE_PCT = get_setting('MAX_BUCKET_EXPOSURE_PCT', 45.0, float) / 100.0
METRICS_ROLLING_WINDOW = get_setting('METRICS_ROLLING_WINDOW', 30, int)

_portfolio_buckets_raw = get_setting('PORTFOLIO_BUCKETS', DEFAULT_SETTINGS['PORTFOLIO_BUCKETS'])
if isinstance(_portfolio_buckets_raw, str):
    try:
        PORTFOLIO_BUCKETS = json.loads(_portfolio_buckets_raw)
    except Exception:
        PORTFOLIO_BUCKETS = DEFAULT_SETTINGS['PORTFOLIO_BUCKETS']
else:
    PORTFOLIO_BUCKETS = _portfolio_buckets_raw

# Rotación
ROTATION_ENABLED = get_setting('ROTATION_ENABLED', True, bool)
ROTATION_MIN_PROFIT = get_setting('ROTATION_MIN_PROFIT', 0.35, float)
ROTATION_CONFIDENCE_GAP = get_setting('ROTATION_CONFIDENCE_GAP', 0.20, float)
ROTATION_MIN_NEW_CONFIDENCE = get_setting('ROTATION_MIN_NEW_CONFIDENCE', 0.85, float)

# Prompts
PROMPT_SENTIMENT = get_setting('PROMPT_SENTIMENT', DEFAULT_SETTINGS['PROMPT_SENTIMENT'])
PROMPT_DECISION = get_setting('PROMPT_DECISION', DEFAULT_SETTINGS['PROMPT_DECISION'])
PROMPT_CURATION = get_setting('PROMPT_CURATION', DEFAULT_SETTINGS['PROMPT_CURATION'])
AI_ANALYSIS_INTERVAL = get_setting('AI_ANALYSIS_INTERVAL', 1200, int)
TRADING_FEE_RATE = get_setting('TRADING_FEE_RATE', 0.001, float)
BUY_SLIPPAGE_LIMIT = get_setting('BUY_SLIPPAGE_LIMIT', 0.005, float)
SELL_SLIPPAGE_LIMIT = get_setting('SELL_SLIPPAGE_LIMIT', 0.010, float)

def get_dynamic_max_positions(balance_usdt: float) -> int:
    """Escala dinámica de posiciones basada en el balance total (v6.1)"""
    if balance_usdt < 100:
        return 3
    elif balance_usdt < 300:
        return 5
    elif balance_usdt < 600:
        return 7
    else:
        return 10


def get_effective_max_positions(balance_usdt: float) -> int:
    """
    Límite de posiciones abiertas para el bot y el dashboard.
    Si MANUAL_MAX_POSITIONS_PRIORITY: usa el valor de MAX_OPEN_POSITIONS (1–10).
    Si no: usa get_dynamic_max_positions (recomendado según capital).
    """
    if get_setting('MANUAL_MAX_POSITIONS_PRIORITY', False, bool):
        m = get_setting('MAX_OPEN_POSITIONS', 5, int)
        return max(1, min(int(m), 10))
    return get_dynamic_max_positions(balance_usdt)
