"""Named configuration presets (full settings, same contract as config importer)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from simulation_profiles import ROOT

from config import DEFAULT_SETTINGS, SENSITIVE_SETTING_KEYS, USER_SETTINGS_FILE, get_setting
from config_importer import (
    CONFIG_SCHEMA,
    SENSITIVE_CONFIG_KEYS,
    apply_config_changes,
    current_safe_config_dict,
    diff_config_changes,
    validate_config_payload,
)

PRESETS_DIR = ROOT / "config_presets"
BUILTIN_DIR = PRESETS_DIR / "builtin"
USER_STORE_FILE = PRESETS_DIR / "user_presets.json"

# Never changed when applying a preset (sidebar / launcher own sim vs real).
PRESET_LOCKED_KEYS = frozenset(
    {
        "MODO_SIMULACION",
        "SIMULATION_PROFILE_ID",
        "PRESUPUESTO_INICIAL",
    }
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:48] or f"preset-{int(time.time())}"


def strip_preset_locked_keys(settings: dict) -> dict:
    """Remove keys that must not be overridden by preset apply/preview."""
    if not settings:
        return {}
    return {
        str(k).strip().upper(): v
        for k, v in settings.items()
        if str(k).strip().upper() not in PRESET_LOCKED_KEYS
    }


def _builtin_definitions() -> list[dict]:
    # Only strategy/risk deltas — not full DEFAULT_SETTINGS (avoids forcing sim mode).
    recommended = {
        "TRADING_EXECUTION_MODE": "auto",
        "DECISION_MODE": "hybrid",
        "MIN_AUTO_DECISION_SCORE": 0.62,
        "MANUAL_MAX_POSITIONS_PRIORITY": True,
        "MAX_OPEN_POSITIONS": 3,
        "RISK_PER_TRADE": 0.02,
        "PROTECTIONS_ENABLED": True,
        "PAIRLIST_LIQUIDITY_FILTER_ENABLED": True,
        "POSITION_MONITOR_SELLS_ENABLED": True,
        "AGGRESSIVE_TRADING_PROFILE": False,
        "AI_ENABLE_LOCAL_BUDGET": False,
        "AI_RULES_ONLY_ON_BUDGET_EXHAUSTED": True,
    }
    signals_only = {
        "TRADING_EXECUTION_MODE": "consultive",
        "DECISION_MODE": "hybrid",
        "MIN_AUTO_DECISION_SCORE": 0.68,
        "RISK_PER_TRADE": 0.01,
        "MAX_OPEN_POSITIONS": 2,
        "PROTECTIONS_ENABLED": True,
        "PAIRLIST_LIQUIDITY_FILTER_ENABLED": True,
        "ROTATION_ENABLED": False,
        "WEBHOOK_AUTO_APPROVE": False,
    }
    conservative = {
        "TRADING_EXECUTION_MODE": "auto",
        "DECISION_MODE": "hybrid",
        "MIN_AUTO_DECISION_SCORE": 0.72,
        "RISK_PER_TRADE": 0.01,
        "MAX_OPEN_POSITIONS": 2,
        "MAX_DAILY_LOSS_PCT": 3.0,
        "MAX_PORTFOLIO_EXPOSURE_PCT": 60.0,
        "PROTECTIONS_ENABLED": True,
        "FUNDING_VETO_ENABLED": True,
        "PAIRLIST_LIQUIDITY_FILTER_ENABLED": True,
        "AI_ENABLE_LOCAL_BUDGET": True,
        "AI_MAX_REQUESTS_PER_CYCLE": 1,
        "AI_MAX_REQUESTS_PER_DAY": 40,
        "AGGRESSIVE_TRADING_PROFILE": False,
        "ROTATION_ENABLED": False,
        "WEBHOOK_AUTO_APPROVE": False,
    }
    aggressive = {
        "TRADING_EXECUTION_MODE": "auto",
        "DECISION_MODE": "ai_aggressive",
        "MIN_AUTO_DECISION_SCORE": 0.55,
        "RISK_PER_TRADE": 0.03,
        "MAX_OPEN_POSITIONS": 5,
        "MANUAL_MAX_POSITIONS_PRIORITY": False,
        "AGGRESSIVE_TRADING_PROFILE": True,
        "ROTATION_ENABLED": True,
        "PROTECTIONS_ENABLED": True,
        "AI_ENABLE_LOCAL_BUDGET": False,
        "AI_MAX_REQUESTS_PER_CYCLE": 0,
        "AI_MAX_REQUESTS_PER_DAY": 0,
        "SCALED_TAKE_PROFIT_ENABLED": True,
        "INVENTORY_SKEW_ENABLED": False,
    }
    return [
        {
            "id": "recommended",
            "name": "Recomendado",
            "description": "Equilibrio entre supervivencia, IA y frecuencia operativa.",
            "builtin": True,
            "settings": recommended,
        },
        {
            "id": "conservative",
            "name": "Conservador",
            "description": "Menor riesgo y más filtros; ejecución automática con umbrales estrictos.",
            "builtin": True,
            "settings": conservative,
        },
        {
            "id": "aggressive",
            "name": "Agresivo",
            "description": "Más señales y exposición; solo para cuentas que aceptan mayor volatilidad.",
            "builtin": True,
            "settings": aggressive,
        },
        {
            "id": "signals_only",
            "name": "Solo señales",
            "description": "Análisis y registro sin ejecutar órdenes (modo consultivo).",
            "builtin": True,
            "settings": signals_only,
        },
    ]


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_user_store() -> dict:
    store = _read_json(USER_STORE_FILE, {"presets": [], "active_preset_id": None})
    if not isinstance(store.get("presets"), list):
        store["presets"] = []
    return store


def _save_user_store(store: dict):
    _write_json(USER_STORE_FILE, store)


def list_presets() -> list[dict]:
    builtins = _builtin_definitions()
    store = _load_user_store()
    user = [p for p in store.get("presets", []) if not p.get("builtin")]
    return builtins + user


def get_preset(preset_id: str) -> dict | None:
    for preset in list_presets():
        if str(preset.get("id")) == str(preset_id):
            return preset
    return None


def get_active_preset_id() -> str | None:
    store = _load_user_store()
    active = store.get("active_preset_id")
    return str(active) if active else None


def set_active_preset_id(preset_id: str | None):
    store = _load_user_store()
    store["active_preset_id"] = preset_id
    _save_user_store(store)


def preset_export_json(preset_id: str) -> str:
    preset = get_preset(preset_id)
    if not preset:
        raise ValueError("preset not found")
    payload = {
        "id": preset.get("id"),
        "name": preset.get("name"),
        "description": preset.get("description", ""),
        "settings": preset.get("settings") or {},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def parse_preset_import(raw: str) -> dict:
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError("invalid preset json")
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else data
    if not isinstance(settings, dict):
        raise ValueError("settings must be object")
    return {
        "id": _slugify(data.get("id") or data.get("name") or "imported"),
        "name": str(data.get("name") or "Importado"),
        "description": str(data.get("description") or ""),
        "builtin": False,
        "settings": settings,
    }


def validate_preset_settings(settings: dict):
    return validate_config_payload(strip_preset_locked_keys(settings))


def preview_preset_apply(preset_id: str):
    preset = get_preset(preset_id)
    if not preset:
        raise ValueError("preset not found")
    changes, warnings, blocked, errors = validate_preset_settings(preset.get("settings") or {})
    warnings = list(warnings)
    if any(str(k).strip().upper() in PRESET_LOCKED_KEYS for k in (preset.get("settings") or {})):
        warnings.append("PRESET_LOCKED_KEYS_SKIPPED")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "changes": changes,
        "warnings": warnings,
        "blocked": blocked,
        "diff": diff_config_changes(changes),
    }


def apply_preset(preset_id: str, *, confirm_real: bool = False) -> dict:
    import config as cfg

    preset = get_preset(preset_id)
    if not preset:
        raise ValueError("preset not found")
    preview = preview_preset_apply(preset_id)
    changes = preview["changes"]
    if not changes:
        return {"backup": None, "changes": {}, "warnings": preview["warnings"]}

    if not cfg.get_setting("MODO_SIMULACION", True, bool) and not confirm_real:
        raise ValueError("REAL_MODE_CONFIRM_REQUIRED")

    backup = apply_config_changes(changes)
    set_active_preset_id(preset_id)
    return {
        "backup": backup,
        "changes": changes,
        "warnings": preview["warnings"],
        "blocked": preview["blocked"],
    }


def save_current_as_preset(name: str, description: str = "") -> dict:
    settings = strip_preset_locked_keys(current_safe_config_dict())
    preset_id = _slugify(name)
    store = _load_user_store()
    existing_ids = {str(p.get("id")) for p in store.get("presets", [])}
    builtin_ids = {p["id"] for p in _builtin_definitions()}
    if preset_id in builtin_ids:
        preset_id = f"{preset_id}-{int(time.time())}"
    while preset_id in existing_ids:
        preset_id = f"{preset_id}-{int(time.time()) % 10000}"

    preset = {
        "id": preset_id,
        "name": str(name).strip() or preset_id,
        "description": str(description or "").strip(),
        "builtin": False,
        "created_at": time.time(),
        "settings": settings,
    }
    store.setdefault("presets", []).append(preset)
    _save_user_store(store)
    return preset


def duplicate_preset(preset_id: str, new_name: str) -> dict:
    source = get_preset(preset_id)
    if not source:
        raise ValueError("preset not found")
    new_id = _slugify(new_name)
    store = _load_user_store()
    existing_ids = {str(p.get("id")) for p in store.get("presets", [])}
    while new_id in existing_ids or new_id in {p["id"] for p in _builtin_definitions()}:
        new_id = f"{new_id}-{int(time.time()) % 10000}"
    preset = {
        "id": new_id,
        "name": str(new_name).strip() or new_id,
        "description": f"Copia de {source.get('name', preset_id)}",
        "builtin": False,
        "created_at": time.time(),
        "settings": strip_preset_locked_keys(dict(source.get("settings") or {})),
    }
    store.setdefault("presets", []).append(preset)
    _save_user_store(store)
    return preset


def delete_user_preset(preset_id: str) -> bool:
    store = _load_user_store()
    presets = store.get("presets", [])
    new_list = [p for p in presets if str(p.get("id")) != str(preset_id)]
    if len(new_list) == len(presets):
        return False
    store["presets"] = new_list
    if store.get("active_preset_id") == preset_id:
        store["active_preset_id"] = None
    _save_user_store(store)
    return True


def import_user_preset(raw: str) -> dict:
    preset = parse_preset_import(raw)
    if preset.get("builtin"):
        preset["builtin"] = False
    preset["settings"] = strip_preset_locked_keys(preset.get("settings") or {})
    changes, warnings, blocked, errors = validate_preset_settings(preset["settings"])
    if errors:
        raise ValueError("; ".join(errors))
    preset["settings"] = changes
    store = _load_user_store()
    store["presets"] = [p for p in store.get("presets", []) if p.get("id") != preset["id"]]
    store["presets"].append(preset)
    _save_user_store(store)
    return preset


def reset_settings_to_recommended() -> dict:
    """Factory defaults + plantilla Recomendado; conserva modo sim/real y perfil activo."""
    preserved = {
        "MODO_SIMULACION": get_setting("MODO_SIMULACION", DEFAULT_SETTINGS["MODO_SIMULACION"], bool),
        "SIMULATION_PROFILE_ID": get_setting(
            "SIMULATION_PROFILE_ID", DEFAULT_SETTINGS["SIMULATION_PROFILE_ID"], str
        ),
    }
    if preserved["MODO_SIMULACION"]:
        preserved["PRESUPUESTO_INICIAL"] = get_setting(
            "PRESUPUESTO_INICIAL", DEFAULT_SETTINGS["PRESUPUESTO_INICIAL"], float
        )

    base = {
        key: value
        for key, value in DEFAULT_SETTINGS.items()
        if str(key).strip().upper() not in SENSITIVE_SETTING_KEYS
    }
    recommended = get_preset("recommended")
    if recommended:
        overrides, _warnings, _blocked, errors = validate_preset_settings(recommended.get("settings") or {})
        if errors:
            raise ValueError("; ".join(errors))
        base.update(overrides)
    base.update(preserved)

    with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(base, f, indent=4)
    set_active_preset_id("recommended")
    return base
