import datetime as dt
import json
import os
import re
import shutil

from config import USER_SETTINGS_FILE, get_setting, save_settings


SENSITIVE_CONFIG_KEYS = {
    "CRYPTO_API_KEY",
    "CRYPTO_API_SECRET",
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "SAMBANOVA_API_KEY",
    "COINDESK_API_KEY",
}


CONFIG_SCHEMA = {
    "MODO_SIMULACION": {"type": bool},
    "PRESUPUESTO_INICIAL": {"type": float, "min": 1.0, "max": 1_000_000.0},
    "MONEDAS": {"type": "symbols"},
    "MANUAL_MAX_POSITIONS_PRIORITY": {"type": bool},
    "MAX_OPEN_POSITIONS": {"type": int, "min": 1, "max": 10},
    "MIN_PROFIT_NET": {"type": float, "min": 0.1, "max": 20.0},
    "STOP_LOSS_PERCENT": {"type": float, "min": 0.1, "max": 50.0},
    "RISK_PER_TRADE": {"type": float, "min": 0.01, "max": 1.0, "percent": True},
    "ROTATION_ENABLED": {"type": bool},
    "ROTATION_MIN_PROFIT": {"type": float, "min": 0.0, "max": 20.0},
    "ROTATION_CONFIDENCE_GAP": {"type": float, "min": 0.0, "max": 1.0},
    "ROTATION_MIN_NEW_CONFIDENCE": {"type": float, "min": 0.0, "max": 1.0},
    "AI_ANALYSIS_INTERVAL": {"type": int, "min": 60, "max": 43_200},
    "TRADING_FEE_RATE": {"type": float, "min": 0.0, "max": 0.05, "percent": True},
    "BUY_SLIPPAGE_LIMIT": {"type": float, "min": 0.0001, "max": 0.20, "percent": True},
    "SELL_SLIPPAGE_LIMIT": {"type": float, "min": 0.0001, "max": 0.20, "percent": True},
    "PROMPT_SENTIMENT": {"type": str, "max_len": 2_000},
    "PROMPT_DECISION": {"type": str, "max_len": 4_000},
    "PROMPT_CURATION": {"type": str, "max_len": 3_000},
}


EXAMPLE_SAFE_CONFIG = {
    "MODO_SIMULACION": True,
    "PRESUPUESTO_INICIAL": 60.0,
    "MONEDAS": "BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,LINK/USDT,SUI/USDT,RUNE/USDT,QNT/USDT,XLM/USDT",
    "MANUAL_MAX_POSITIONS_PRIORITY": True,
    "MAX_OPEN_POSITIONS": 3,
    "RISK_PER_TRADE": 0.10,
    "MIN_PROFIT_NET": 1.5,
    "ROTATION_ENABLED": True,
    "ROTATION_MIN_PROFIT": 2.0,
    "ROTATION_CONFIDENCE_GAP": 0.25,
    "ROTATION_MIN_NEW_CONFIDENCE": 0.85,
    "AI_ANALYSIS_INTERVAL": 1200,
    "BUY_SLIPPAGE_LIMIT": 0.005,
    "SELL_SLIPPAGE_LIMIT": 0.010,
}


def config_example_json() -> str:
    return json.dumps(EXAMPLE_SAFE_CONFIG, indent=4, ensure_ascii=False)


def current_safe_config_json() -> str:
    data = {}
    for key in CONFIG_SCHEMA:
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

    payload = json.loads(text)
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
        if not coerced:
            raise ValueError("no puede estar vacío")
        if len(coerced) > spec.get("max_len", 10_000):
            raise ValueError("texto demasiado largo")
    elif expected == "symbols":
        coerced = _coerce_symbols(value)
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
            rows.append({"Campo": key, "Antes": old_value, "Después": new_value})
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
