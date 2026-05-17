import json
import re
import sys
import time
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "dist":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parent


ROOT = project_root()
USER_SETTINGS_PATH = ROOT / "user_settings.json"
STORE_PATH = ROOT / "simulation_profiles.json"
SIMULATIONS_DIR = ROOT / "simulations"
DEFAULT_PROFILE_ID = "default"
DEFAULT_INITIAL_CAPITAL = 60.0

GLOBAL_SETTING_KEYS = {
    "MODO_SIMULACION",
    "SIMULATION_PROFILE_ID",
    "CRYPTO_API_KEY",
    "CRYPTO_API_SECRET",
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "SAMBANOVA_API_KEY",
    "COINDESK_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
}


def _read_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def load_user_settings():
    data = _read_json(USER_SETTINGS_PATH, {})
    return data if isinstance(data, dict) else {}


def save_user_settings(data):
    _write_json(USER_SETTINGS_PATH, data if isinstance(data, dict) else {})


def simulation_mode_enabled(default=True):
    value = load_user_settings().get("MODO_SIMULACION", default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "si", "sí", "on"}


def _default_store():
    return {"profiles": []}


def load_store():
    store = _read_json(STORE_PATH, _default_store())
    if not isinstance(store, dict):
        store = _default_store()
    profiles = store.get("profiles")
    if not isinstance(profiles, list):
        store["profiles"] = []
    return store


def save_store(store):
    _write_json(STORE_PATH, store)


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:40] or DEFAULT_PROFILE_ID


def _profile_dir(profile_id):
    return SIMULATIONS_DIR / str(profile_id)


def profile_db_path(profile_id):
    return _profile_dir(profile_id) / "iversoria.db"


def profile_account_path(profile_id):
    return _profile_dir(profile_id) / "simulated_account.json"


def _find_profile(store, profile_id):
    for profile in store.get("profiles", []):
        if str(profile.get("id")) == str(profile_id):
            return profile
    return None


def _initial_capital_from_settings(default=DEFAULT_INITIAL_CAPITAL):
    try:
        return float(load_user_settings().get("PRESUPUESTO_INICIAL", default) or default)
    except (TypeError, ValueError):
        return default


def _initial_account(capital):
    return {"virtual_balance": float(capital), "virtual_portfolio": {}}


def ensure_profile_files(profile):
    profile_id = profile["id"]
    _profile_dir(profile_id).mkdir(parents=True, exist_ok=True)
    account_path = profile_account_path(profile_id)
    if not account_path.exists():
        legacy_account = ROOT / "simulated_account.json"
        if profile_id == DEFAULT_PROFILE_ID and legacy_account.exists():
            try:
                account_path.write_text(legacy_account.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                _write_json(account_path, _initial_account(profile.get("initial_capital", DEFAULT_INITIAL_CAPITAL)))
        else:
            _write_json(account_path, _initial_account(profile.get("initial_capital", DEFAULT_INITIAL_CAPITAL)))
    return profile


def list_profiles():
    ensure_default_profile()
    store = load_store()
    profiles = sorted(store.get("profiles", []), key=lambda p: str(p.get("created_at", "")))
    return [ensure_profile_files(dict(profile)) for profile in profiles]


def ensure_default_profile(initial_capital=None):
    store = load_store()
    if _find_profile(store, DEFAULT_PROFILE_ID):
        profile = _find_profile(store, DEFAULT_PROFILE_ID)
        ensure_profile_files(profile)
    else:
        now = time.time()
        capital = float(initial_capital if initial_capital is not None else _initial_capital_from_settings())
        profile = {
            "id": DEFAULT_PROFILE_ID,
            "name": "Default",
            "initial_capital": capital,
            "settings": {"PRESUPUESTO_INICIAL": capital},
            "created_at": now,
            "updated_at": now,
        }
        store["profiles"].append(profile)
        save_store(store)
        ensure_profile_files(profile)

    settings = load_user_settings()
    if not settings.get("SIMULATION_PROFILE_ID"):
        settings["SIMULATION_PROFILE_ID"] = DEFAULT_PROFILE_ID
        save_user_settings(settings)
    return profile


def get_active_profile_id():
    ensure_default_profile()
    settings = load_user_settings()
    profile_id = str(settings.get("SIMULATION_PROFILE_ID") or DEFAULT_PROFILE_ID)
    store = load_store()
    if not _find_profile(store, profile_id):
        profile_id = DEFAULT_PROFILE_ID
        settings["SIMULATION_PROFILE_ID"] = profile_id
        save_user_settings(settings)
    return profile_id


def set_active_profile(profile_id):
    ensure_default_profile()
    store = load_store()
    if not _find_profile(store, profile_id):
        raise ValueError(f"simulation profile not found: {profile_id}")
    settings = load_user_settings()
    settings["SIMULATION_PROFILE_ID"] = str(profile_id)
    settings["MODO_SIMULACION"] = True
    save_user_settings(settings)
    return get_active_profile()


def get_active_profile():
    profile_id = get_active_profile_id()
    store = load_store()
    profile = _find_profile(store, profile_id) or ensure_default_profile()
    return ensure_profile_files(dict(profile))


def create_profile(name, initial_capital, settings=None, activate=True):
    store = load_store()
    base = _slugify(name)
    profile_id = base
    existing = {str(p.get("id")) for p in store.get("profiles", [])}
    if profile_id in existing:
        profile_id = f"{base}-{int(time.time())}"
    capital = max(1.0, float(initial_capital or DEFAULT_INITIAL_CAPITAL))
    now = time.time()
    safe_settings = sanitize_profile_settings(settings or {})
    safe_settings["PRESUPUESTO_INICIAL"] = capital
    profile = {
        "id": profile_id,
        "name": str(name or profile_id).strip() or profile_id,
        "initial_capital": capital,
        "settings": safe_settings,
        "created_at": now,
        "updated_at": now,
    }
    store.setdefault("profiles", []).append(profile)
    save_store(store)
    ensure_profile_files(profile)
    if activate:
        set_active_profile(profile_id)
    return profile


def reset_profile(profile_id=None, initial_capital=None):
    ensure_default_profile()
    profile_id = profile_id or get_active_profile_id()
    store = load_store()
    profile = _find_profile(store, profile_id)
    if not profile:
        raise ValueError(f"simulation profile not found: {profile_id}")
    if initial_capital is not None:
        profile["initial_capital"] = max(1.0, float(initial_capital))
        profile.setdefault("settings", {})["PRESUPUESTO_INICIAL"] = profile["initial_capital"]
    profile["updated_at"] = time.time()
    save_store(store)
    profile_dir = _profile_dir(profile_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("iversoria.db", "iversoria.db-journal", "simulated_account.json"):
        path = profile_dir / filename
        if path.exists():
            path.unlink()
    _write_json(profile_account_path(profile_id), _initial_account(profile.get("initial_capital", DEFAULT_INITIAL_CAPITAL)))
    return dict(profile)


def sanitize_profile_settings(settings):
    out = {}
    for key, value in (settings or {}).items():
        normalized = str(key).strip().upper()
        if not normalized or normalized in GLOBAL_SETTING_KEYS:
            continue
        out[normalized] = value
    return out


def get_active_profile_settings():
    if not simulation_mode_enabled(default=True):
        return {}
    profile = get_active_profile()
    settings = profile.get("settings") if isinstance(profile.get("settings"), dict) else {}
    return dict(settings)


def save_active_profile_settings(changes):
    profile_id = get_active_profile_id()
    safe_changes = sanitize_profile_settings(changes)
    if not safe_changes:
        return get_active_profile()
    store = load_store()
    profile = _find_profile(store, profile_id)
    if not profile:
        profile = ensure_default_profile()
    profile.setdefault("settings", {}).update(safe_changes)
    if "PRESUPUESTO_INICIAL" in safe_changes:
        try:
            profile["initial_capital"] = float(safe_changes["PRESUPUESTO_INICIAL"])
        except (TypeError, ValueError):
            pass
    profile["updated_at"] = time.time()
    save_store(store)
    ensure_profile_files(profile)
    return dict(profile)


def get_database_path_for_current_mode():
    if simulation_mode_enabled(default=True):
        profile = get_active_profile()
        return str(profile_db_path(profile["id"]))
    return str(ROOT / "iversoria.db")


def get_active_account_path():
    profile = get_active_profile()
    return str(profile_account_path(profile["id"]))
