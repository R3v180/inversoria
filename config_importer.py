import datetime as dt
import ast
import json
import os
import re
import shutil

from config import SENSITIVE_SETTING_KEYS, USER_SETTINGS_FILE, get_setting, save_settings


SENSITIVE_CONFIG_KEYS = set(SENSITIVE_SETTING_KEYS) | {"ALERT_WEBHOOK_URL"}


CONFIG_SCHEMA = {
    "MODO_SIMULACION": {"type": bool},
    "SIMULATION_PROFILE_ID": {"type": str, "max_len": 80},
    "PRESUPUESTO_INICIAL": {"type": float, "min": 1.0, "max": 1_000_000.0},
    "MONEDAS": {"type": "symbols"},
    "TRADING_EXECUTION_MODE": {"type": "choice", "choices": {"auto", "consultive"}},
    "DECISION_MODE": {"type": "choice", "choices": {"ai_aggressive", "hybrid", "rules"}},
    "MIN_AUTO_DECISION_SCORE": {"type": float, "min": 0.0, "max": 1.0},
    "MANUAL_MAX_POSITIONS_PRIORITY": {"type": bool},
    "MAX_OPEN_POSITIONS": {"type": int, "min": 1, "max": 10},
    "MIN_PROFIT_NET": {"type": float, "min": 0.1, "max": 20.0},
    "STOP_LOSS_PERCENT": {"type": float, "min": 0.1, "max": 50.0},
    "ATR_STOP_ENABLED": {"type": bool},
    "STOP_LOSS_ATR_MULT": {"type": float, "min": 0.2, "max": 10.0},
    "ATR_TRAILING_ENABLED": {"type": bool},
    "TRAILING_ATR_MULT": {"type": float, "min": 0.2, "max": 15.0},
    "TRAILING_ACTIVATION_PCT": {"type": float, "min": 0.1, "max": 50.0},
    "BREAK_EVEN_ACTIVATION_PCT": {"type": float, "min": 0.1, "max": 50.0},
    "MAX_POSITION_AGE_HOURS": {"type": int, "min": 1, "max": 8760},
    "MAX_DAILY_LOSS_PCT": {"type": float, "min": 0.1, "max": 100.0},
    "MAX_PORTFOLIO_DRAWDOWN_PCT": {"type": float, "min": 1.0, "max": 95.0},
    "DRAWDOWN_COOLDOWN_HOURS": {"type": int, "min": 1, "max": 720},
    "MAX_PORTFOLIO_EXPOSURE_PCT": {"type": float, "min": 1.0, "max": 100.0},
    "VOLATILITY_SIZING_ENABLED": {"type": bool},
    "MAX_POSITION_RISK_PCT": {"type": float, "min": 0.1, "max": 20.0},
    "MAX_VOLATILITY_POSITION_MULTIPLIER": {"type": float, "min": 0.25, "max": 3.0},
    "MIN_POSITION_USDT": {"type": float, "min": 0.1, "max": 10_000.0},
    "MAX_SYMBOL_EXPOSURE_PCT": {"type": float, "min": 1.0, "max": 100.0},
    "MAX_ALT_EXPOSURE_PCT": {"type": float, "min": 1.0, "max": 100.0},
    "MAX_BUCKET_EXPOSURE_PCT": {"type": float, "min": 1.0, "max": 100.0},
    "ADAPTIVE_SCORING_ENABLED": {"type": bool},
    "ADAPTIVE_MIN_TRADES": {"type": int, "min": 3, "max": 100},
    "ADAPTIVE_MAX_SCORE_ADJUSTMENT": {"type": float, "min": 0.0, "max": 0.30},
    "METRICS_ROLLING_WINDOW": {"type": int, "min": 5, "max": 500},
    "PORTFOLIO_BUCKETS": {"type": "bucket_map"},
    "RISK_PER_TRADE": {"type": float, "min": 0.01, "max": 1.0, "percent": True},
    "ROTATION_ENABLED": {"type": bool},
    "ROTATION_MIN_PROFIT": {"type": float, "min": 0.0, "max": 20.0},
    "ROTATION_CONFIDENCE_GAP": {"type": float, "min": 0.0, "max": 1.0},
    "ROTATION_MIN_NEW_CONFIDENCE": {"type": float, "min": 0.0, "max": 1.0},
    "AI_ANALYSIS_INTERVAL": {"type": int, "min": 60, "max": 43_200},
    "TRADING_FEE_RATE": {"type": float, "min": 0.0, "max": 0.05, "percent": True},
    "BUY_SLIPPAGE_LIMIT": {"type": float, "min": 0.0001, "max": 0.20, "percent": True},
    "SELL_SLIPPAGE_LIMIT": {"type": float, "min": 0.0001, "max": 0.20, "percent": True},
    "AGGRESSIVE_TRADING_PROFILE": {"type": bool},
    "MACRO_VETO_ALTS_IN_RISK_OFF": {"type": bool},
    "MACRO_RISK_OFF_BTC_DOM": {"type": float, "min": 50.0, "max": 75.0},
    "MACRO_RISK_OFF_CAP_CHANGE_PCT": {"type": float, "min": -20.0, "max": 0.0},
    "MACRO_CAUTION_BTC_DOM": {"type": float, "min": 50.0, "max": 80.0},
    "MACRO_ALTSEASON_BTC_DOM": {"type": float, "min": 35.0, "max": 60.0},
    "MACRO_RISK_ON_MAX_BTC_DOM": {"type": float, "min": 45.0, "max": 75.0},
    "MACRO_CAUTION_RISK_OFF_BTC_DOM": {"type": float, "min": 45.0, "max": 80.0},
    "MACRO_DXY_VETO_PCT": {"type": float, "min": 0.5, "max": 5.0},
    "MACRO_SPY_VETO_PCT": {"type": float, "min": -10.0, "max": 0.0},
    "MIN_CONFIDENCE_ENTRY": {"type": float, "min": 0.0, "max": 1.0},
    "MTF_ALLOW_COUNTER_TREND": {"type": bool},
    "MTF_INCLUDE_15M": {"type": bool},
    "MTF_DIVERGENCE_PENALTY": {"type": float, "min": 0.0, "max": 0.5},
    "BACKTEST_HARD_VETO_WIN_RATE": {"type": float, "min": 0.0, "max": 0.8},
    "BACKTEST_HARD_VETO_MIN_TRADES": {"type": int, "min": 5, "max": 200},
    "BACKTEST_MIN_TRADES_PER_BUCKET": {"type": int, "min": 3, "max": 200},
    "BACKTEST_MIN_SAMPLE_TRADES": {"type": int, "min": 5, "max": 1000},
    "SMALL_ACCOUNT_USDT_THRESHOLD": {"type": float, "min": 10.0, "max": 10_000.0},
    "SMALL_ACCOUNT_FORCE_MIN_ORDER": {"type": bool},
    "SMALL_ACCOUNT_MAX_STOP_DISTANCE_PCT": {"type": float, "min": 1.0, "max": 25.0},
    "DAEMON_CYCLE_SECONDS": {"type": int, "min": 15, "max": 600},
    "WATCHLIST_UPDATE_SECONDS": {"type": int, "min": 900, "max": 86_400},
    "AI_BATCH_DECISIONS_ENABLED": {"type": bool},
    "DUST_WATCH_ENABLED": {"type": bool},
    "DUST_AUTO_SELL_ENABLED": {"type": bool},
    "DUST_SELL_MIN_USDT": {"type": float, "min": 0.1, "max": 10_000.0},
    "DUST_ALERT_ON_RECOVERABLE": {"type": bool},
    "DUST_LOG_COMPACT_ENABLED": {"type": bool},
    "ORDER_RECONCILE_ENABLED": {"type": bool},
    "ORDER_RECONCILE_TIMEOUT_SECONDS": {"type": int, "min": 5, "max": 600},
    "ORDER_MAX_PENDING_SECONDS": {"type": int, "min": 10, "max": 3600},
    "BUY_FEE_BUFFER_PCT": {"type": float, "min": 0.0, "max": 5.0},
    "ORDERBOOK_DEPTH_LEVELS": {"type": int, "min": 1, "max": 50},
    "KILL_SWITCH_ENABLED": {"type": bool},
    "MAX_EXCHANGE_ERRORS_PER_CYCLE": {"type": int, "min": 1, "max": 100},
    "MAX_UNRECONCILED_ORDERS": {"type": int, "min": 0, "max": 100},
    "AUTO_PAUSE_ON_DB_EXCHANGE_MISMATCH": {"type": bool},
    "AUTO_PAUSE_ON_STALE_HEARTBEAT": {"type": bool},
    "AI_MAX_REQUESTS_PER_CYCLE": {"type": int, "min": 0, "max": 100},
    "AI_MAX_REQUESTS_PER_DAY": {"type": int, "min": 0, "max": 10_000},
    "AI_MAX_EST_TOKENS_PER_DAY": {"type": int, "min": 0, "max": 10_000_000},
    "AI_RULES_ONLY_ON_BUDGET_EXHAUSTED": {"type": bool},
    "AI_MAX_OUTPUT_TOKENS": {"type": int, "min": 64, "max": 4096},
    "AI_PROVIDER_TIMEOUT_SECONDS": {"type": int, "min": 3, "max": 120},
    "ADD_TO_WINNER_ENABLED": {"type": bool},
    "ADD_MIN_PROFIT_PCT": {"type": float, "min": 0.0, "max": 50.0},
    "ADD_MIN_SCORE": {"type": float, "min": 0.0, "max": 1.0},
    "ADD_MIN_CONFIDENCE": {"type": float, "min": 0.0, "max": 1.0},
    "ADD_MAX_PER_SYMBOL": {"type": int, "min": 0, "max": 10},
    "ADD_SIZE_MULTIPLIER": {"type": float, "min": 0.05, "max": 2.0},
    "BREAK_EVEN_ENABLED": {"type": bool},
    "PARTIAL_TAKE_PROFIT_ENABLED": {"type": bool},
    "PARTIAL_TAKE_PROFIT_PCT": {"type": float, "min": 1.0, "max": 100.0},
    "ALERTS_ENABLED": {"type": bool},
    "ALERT_WEBHOOK_URL": {"type": str, "max_len": 2_000, "allow_empty": True},
    "ALERT_TIMEOUT_SECONDS": {"type": int, "min": 1, "max": 60},
    "HEALTH_EXPORT_ENABLED": {"type": bool},
    "STRUCTURED_LOGS_ENABLED": {"type": bool},
    "AUDIT_EVENTS_ENABLED": {"type": bool},
    "PROMPT_SENTIMENT": {"type": str, "max_len": 2_000, "allow_empty": True},
    "PROMPT_DECISION": {"type": str, "max_len": 4_000, "allow_empty": True},
    "PROMPT_CURATION": {"type": str, "max_len": 3_000, "allow_empty": True},
}


EXAMPLE_SAFE_CONFIG = {
    "MODO_SIMULACION": True,
    "SIMULATION_PROFILE_ID": "default",
    "PRESUPUESTO_INICIAL": 60.0,
    "MONEDAS": "BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,LINK/USDT,SUI/USDT,RUNE/USDT,QNT/USDT,XLM/USDT",
    "TRADING_EXECUTION_MODE": "auto",
    "DECISION_MODE": "hybrid",
    "MIN_AUTO_DECISION_SCORE": 0.62,
    "MANUAL_MAX_POSITIONS_PRIORITY": True,
    "MAX_OPEN_POSITIONS": 3,
    "RISK_PER_TRADE": 0.02,
    "MIN_PROFIT_NET": 3.0,
    "STOP_LOSS_PERCENT": 2.0,
    "ATR_STOP_ENABLED": True,
    "STOP_LOSS_ATR_MULT": 1.5,
    "ATR_TRAILING_ENABLED": True,
    "TRAILING_ATR_MULT": 2.5,
    "TRAILING_ACTIVATION_PCT": 2.0,
    "BREAK_EVEN_ACTIVATION_PCT": 1.5,
    "MAX_POSITION_AGE_HOURS": 168,
    "MAX_DAILY_LOSS_PCT": 5.0,
    "MAX_PORTFOLIO_DRAWDOWN_PCT": 15.0,
    "DRAWDOWN_COOLDOWN_HOURS": 24,
    "MAX_PORTFOLIO_EXPOSURE_PCT": 85.0,
    "VOLATILITY_SIZING_ENABLED": True,
    "MAX_POSITION_RISK_PCT": 1.0,
    "MAX_VOLATILITY_POSITION_MULTIPLIER": 1.0,
    "MIN_POSITION_USDT": 1.0,
    "MAX_SYMBOL_EXPOSURE_PCT": 30.0,
    "MAX_ALT_EXPOSURE_PCT": 75.0,
    "MAX_BUCKET_EXPOSURE_PCT": 45.0,
    "ADAPTIVE_SCORING_ENABLED": True,
    "ADAPTIVE_MIN_TRADES": 5,
    "ADAPTIVE_MAX_SCORE_ADJUSTMENT": 0.12,
    "METRICS_ROLLING_WINDOW": 30,
    "PORTFOLIO_BUCKETS": {
        "BTC": ["BTC"],
        "ETH": ["ETH"],
        "LAYER1": ["SOL", "ADA", "AVAX", "DOT", "ATOM", "NEAR", "SUI", "APT", "XLM", "XRP"],
        "DEFI": ["AAVE", "UNI", "LINK", "RUNE", "MKR", "LDO", "CRV", "SNX"],
        "AI": ["FET", "TAO", "RENDER", "RNDR", "GRT", "OCEAN", "AGIX"],
        "MEME": ["DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI"]
    },
    "ROTATION_ENABLED": True,
    "ROTATION_MIN_PROFIT": 2.0,
    "ROTATION_CONFIDENCE_GAP": 0.25,
    "ROTATION_MIN_NEW_CONFIDENCE": 0.85,
    "AI_ANALYSIS_INTERVAL": 1200,
    "AI_BATCH_DECISIONS_ENABLED": True,
    "BUY_SLIPPAGE_LIMIT": 0.005,
    "SELL_SLIPPAGE_LIMIT": 0.010,
    "MACRO_ALTSEASON_BTC_DOM": 48.0,
    "MACRO_RISK_ON_MAX_BTC_DOM": 55.0,
    "MACRO_CAUTION_RISK_OFF_BTC_DOM": 55.0,
    "MTF_INCLUDE_15M": True,
    "MTF_DIVERGENCE_PENALTY": 0.15,
    "BACKTEST_HARD_VETO_WIN_RATE": 0.50,
    "BACKTEST_HARD_VETO_MIN_TRADES": 20,
    "BACKTEST_MIN_TRADES_PER_BUCKET": 5,
    "BACKTEST_MIN_SAMPLE_TRADES": 30,
    "DUST_WATCH_ENABLED": True,
    "DUST_AUTO_SELL_ENABLED": False,
    "DUST_SELL_MIN_USDT": 5.0,
    "DUST_ALERT_ON_RECOVERABLE": True,
    "DUST_LOG_COMPACT_ENABLED": True,
    "ORDER_RECONCILE_ENABLED": True,
    "ORDER_RECONCILE_TIMEOUT_SECONDS": 30,
    "ORDER_MAX_PENDING_SECONDS": 120,
    "BUY_FEE_BUFFER_PCT": 0.5,
    "ORDERBOOK_DEPTH_LEVELS": 5,
    "KILL_SWITCH_ENABLED": True,
    "MAX_EXCHANGE_ERRORS_PER_CYCLE": 3,
    "MAX_UNRECONCILED_ORDERS": 0,
    "AUTO_PAUSE_ON_DB_EXCHANGE_MISMATCH": True,
    "AUTO_PAUSE_ON_STALE_HEARTBEAT": True,
    "AI_MAX_REQUESTS_PER_CYCLE": 2,
    "AI_MAX_REQUESTS_PER_DAY": 80,
    "AI_MAX_EST_TOKENS_PER_DAY": 120000,
    "AI_RULES_ONLY_ON_BUDGET_EXHAUSTED": True,
    "AI_MAX_OUTPUT_TOKENS": 700,
    "AI_PROVIDER_TIMEOUT_SECONDS": 15,
    "ADD_TO_WINNER_ENABLED": False,
    "ADD_MIN_PROFIT_PCT": 1.0,
    "ADD_MIN_SCORE": 0.62,
    "ADD_MIN_CONFIDENCE": 0.65,
    "ADD_MAX_PER_SYMBOL": 1,
    "ADD_SIZE_MULTIPLIER": 0.5,
    "BREAK_EVEN_ENABLED": True,
    "PARTIAL_TAKE_PROFIT_ENABLED": True,
    "PARTIAL_TAKE_PROFIT_PCT": 50.0,
    "ALERTS_ENABLED": False,
    "ALERT_TIMEOUT_SECONDS": 5,
    "HEALTH_EXPORT_ENABLED": True,
    "STRUCTURED_LOGS_ENABLED": True,
    "AUDIT_EVENTS_ENABLED": True,
}


def config_example_json() -> str:
    return json.dumps(EXAMPLE_SAFE_CONFIG, indent=4, ensure_ascii=False)


def current_safe_config_json() -> str:
    data = {}
    for key in CONFIG_SCHEMA:
        if key in SENSITIVE_CONFIG_KEYS:
            continue
        default = EXAMPLE_SAFE_CONFIG.get(key, "")
        data[key] = get_setting(key, default)
    return json.dumps(data, indent=4, ensure_ascii=False)


def parse_config_payload(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("La configuración está vacía.")

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1)
    elif "{" in text and "}" in text:
        text = text[text.find("{"): text.rfind("}") + 1]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Be permissive with configs copied from Python repr/exported legacy values
        # using single quotes, True/False or nested dict strings.
        payload = ast.literal_eval(text)
    if isinstance(payload, dict) and isinstance(payload.get("settings"), dict):
        payload = payload["settings"]
    if not isinstance(payload, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")
    return payload


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "si", "sí", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise ValueError("debe ser true/false")


def _coerce_symbols(value):
    if isinstance(value, list):
        symbols = value
    else:
        symbols = str(value).split(",")
    cleaned = []
    for symbol in symbols:
        sym = str(symbol).strip().upper()
        if not sym:
            continue
        if "/" not in sym:
            sym = f"{sym}/USDT"
        if not re.match(r"^[A-Z0-9]+/[A-Z0-9]+$", sym):
            raise ValueError(f"símbolo inválido: {sym}")
        if sym not in cleaned:
            cleaned.append(sym)
    if not cleaned:
        raise ValueError("debe contener al menos un símbolo")
    return ",".join(cleaned)


def _coerce_bucket_map(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = ast.literal_eval(value)
    if not isinstance(value, dict):
        raise ValueError("debe ser un objeto con buckets y listas de símbolos")
    out = {}
    for bucket, symbols in value.items():
        bucket_name = str(bucket).strip().upper()
        if not bucket_name:
            continue
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",")]
        if not isinstance(symbols, list):
            raise ValueError(f"{bucket_name}: debe ser lista o texto separado por comas")
        cleaned = []
        for symbol in symbols:
            base = str(symbol).strip().upper()
            if "/" in base:
                base = base.split("/", 1)[0]
            if not re.match(r"^[A-Z0-9]+$", base):
                raise ValueError(f"{bucket_name}: símbolo inválido {base}")
            if base and base not in cleaned:
                cleaned.append(base)
        if cleaned:
            out[bucket_name] = cleaned
    if not out:
        raise ValueError("debe contener al menos un bucket")
    return out


def _coerce_value(key, value, spec, warnings):
    expected = spec["type"]
    if expected is bool:
        coerced = _coerce_bool(value)
    elif expected is int:
        coerced = int(value)
    elif expected is float:
        coerced = float(value)
        if spec.get("percent") and coerced > 1:
            coerced = coerced / 100.0
            warnings.append(f"{key}: valor interpretado como porcentaje y convertido a {coerced:.4f}.")
    elif expected is str:
        coerced = str(value).strip()
        if key.startswith("PROMPT_") and not coerced:
            warnings.append(f"{key}: vacío; el bot usará el prompt por defecto interno.")
        if not coerced and not spec.get("allow_empty"):
            raise ValueError("no puede estar vacío")
        if len(coerced) > spec.get("max_len", 10_000):
            raise ValueError("texto demasiado largo")
    elif expected == "symbols":
        coerced = _coerce_symbols(value)
    elif expected == "bucket_map":
        coerced = _coerce_bucket_map(value)
    elif expected == "choice":
        coerced = str(value).strip().lower()
        if coerced not in spec["choices"]:
            raise ValueError(f"debe ser uno de: {', '.join(sorted(spec['choices']))}")
    else:
        raise ValueError("tipo no soportado")

    if "min" in spec and coerced < spec["min"]:
        raise ValueError(f"debe ser >= {spec['min']}")
    if "max" in spec and coerced > spec["max"]:
        raise ValueError(f"debe ser <= {spec['max']}")
    return coerced


def validate_config_payload(payload: dict):
    changes = {}
    warnings = []
    blocked = []
    errors = []

    for key, value in payload.items():
        normalized_key = str(key).strip().upper()
        if normalized_key in SENSITIVE_CONFIG_KEYS:
            blocked.append(normalized_key)
            continue
        if normalized_key not in CONFIG_SCHEMA:
            warnings.append(f"{normalized_key}: clave ignorada porque no está permitida.")
            continue
        try:
            changes[normalized_key] = _coerce_value(
                normalized_key,
                value,
                CONFIG_SCHEMA[normalized_key],
                warnings,
            )
        except Exception as exc:
            errors.append(f"{normalized_key}: {exc}")

    return changes, warnings, blocked, errors


def diff_config_changes(changes: dict):
    rows = []
    for key, new_value in changes.items():
        old_value = get_setting(key, None)
        if old_value != new_value:
            rows.append({
                "Campo": str(key),
                "Antes": "" if old_value is None else str(old_value),
                "Después": "" if new_value is None else str(new_value),
            })
    return rows


def backup_user_settings() -> str | None:
    if not os.path.exists(USER_SETTINGS_FILE):
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{USER_SETTINGS_FILE}.backup-{stamp}.json"
    shutil.copy2(USER_SETTINGS_FILE, backup_path)
    return backup_path


def apply_config_changes(changes: dict) -> str | None:
    backup_path = backup_user_settings()
    save_settings(changes)
    return backup_path
