"""Keep CONFIG_SCHEMA aligned with DEFAULT_SETTINGS."""

from __future__ import annotations

import config


def infer_schema_spec(key: str, default_value):
    if isinstance(default_value, bool):
        return {"type": bool}
    if isinstance(default_value, int):
        return {"type": int, "min": -1_000_000, "max": 10_000_000}
    if isinstance(default_value, float):
        spec = {"type": float, "min": -1_000_000.0, "max": 1_000_000.0}
        if key.endswith("_PCT") and "GRID" not in key and default_value <= 100:
            if key in {
                "MAX_DAILY_LOSS_PCT",
                "MAX_PORTFOLIO_DRAWDOWN_PCT",
                "MAX_PORTFOLIO_EXPOSURE_PCT",
                "MAX_SYMBOL_EXPOSURE_PCT",
                "MAX_ALT_EXPOSURE_PCT",
                "MAX_BUCKET_EXPOSURE_PCT",
                "MAX_POSITION_RISK_PCT",
                "SMALL_ACCOUNT_MAX_STOP_DISTANCE_PCT",
                "DB_EXCHANGE_MISMATCH_TOLERANCE_PCT",
                "BUY_FEE_BUFFER_PCT",
                "PARTIAL_TAKE_PROFIT_PCT",
                "ADD_MIN_PROFIT_PCT",
                "POSITION_AGE_DECAY_MIN_PROFIT_PCT",
                "PROTECTION_LOW_PROFIT_MAX_EXPECTANCY_PCT",
                "FUNDING_VETO_MAX_LONG_PCT",
                "INVENTORY_SKEW_TARGET_SYMBOL_PCT",
                "GRID_SPACING_PCT",
            }:
                spec["min"] = -100.0
                spec["max"] = 100.0
        return spec
    if isinstance(default_value, list):
        return {"type": "json_list", "min_items": 0, "max_items": 50}
    if isinstance(default_value, dict):
        return {"type": "bucket_map"}
    if key == "MONEDAS":
        return {"type": "symbols"}
    if key == "TRADING_EXECUTION_MODE":
        return {"type": "choice", "choices": {"auto", "consultive"}}
    if key == "DECISION_MODE":
        return {"type": "choice", "choices": {"ai_aggressive", "hybrid", "rules"}}
    if key.startswith("PROMPT_"):
        return {"type": str, "max_len": 4_000, "allow_empty": True}
    if key.endswith("_SECRET") or key == "ALERT_WEBHOOK_URL":
        return {"type": str, "max_len": 500, "allow_empty": True}
    return {"type": str, "max_len": 500, "allow_empty": True}


def sync_config_schema(schema: dict) -> dict:
    for key, default in config.DEFAULT_SETTINGS.items():
        if key in config.SENSITIVE_SETTING_KEYS:
            continue
        if key not in schema:
            schema[key] = infer_schema_spec(key, default)
    return schema
