import json
import re
import time
from pathlib import Path

import config
from config_importer import CONFIG_SCHEMA


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "launcher_logs"
FOCUS_TAGS = ("[SKIP]", "[BLOCK]", "[BUY]", "[SELL]", "[ROTATION]", "[ERROR]", "[WARN]")

DIAGNOSTIC_CONFIG_KEYS = (
    "MODO_SIMULACION",
    "SIMULATION_PROFILE_ID",
    "PRESUPUESTO_INICIAL",
    "TRADING_EXECUTION_MODE",
    "DECISION_MODE",
    "MIN_AUTO_DECISION_SCORE",
    "MANUAL_MAX_POSITIONS_PRIORITY",
    "MAX_OPEN_POSITIONS",
    "RISK_PER_TRADE",
    "MIN_PROFIT_NET",
    "STOP_LOSS_PERCENT",
    "ATR_STOP_ENABLED",
    "STOP_LOSS_ATR_MULT",
    "ATR_TRAILING_ENABLED",
    "TRAILING_ATR_MULT",
    "TRAILING_ACTIVATION_PCT",
    "BREAK_EVEN_ACTIVATION_PCT",
    "MAX_POSITION_AGE_HOURS",
    "STOP_LOSS_COOLDOWN_MINUTES",
    "TAKE_PROFIT_COOLDOWN_MINUTES",
    "MAX_DAILY_LOSS_PCT",
    "MAX_PORTFOLIO_DRAWDOWN_PCT",
    "DRAWDOWN_COOLDOWN_HOURS",
    "MAX_PORTFOLIO_EXPOSURE_PCT",
    "VOLATILITY_SIZING_ENABLED",
    "MAX_POSITION_RISK_PCT",
    "MAX_VOLATILITY_POSITION_MULTIPLIER",
    "MIN_POSITION_USDT",
    "MAX_SYMBOL_EXPOSURE_PCT",
    "MAX_ALT_EXPOSURE_PCT",
    "MAX_BUCKET_EXPOSURE_PCT",
    "ADAPTIVE_SCORING_ENABLED",
    "ADAPTIVE_MIN_TRADES",
    "ADAPTIVE_MAX_SCORE_ADJUSTMENT",
    "METRICS_ROLLING_WINDOW",
    "ROTATION_ENABLED",
    "ROTATION_MIN_PROFIT",
    "ROTATION_CONFIDENCE_GAP",
    "ROTATION_MIN_NEW_CONFIDENCE",
    "AI_ANALYSIS_INTERVAL",
    "AI_BATCH_DECISIONS_ENABLED",
    "TRADING_FEE_RATE",
    "BUY_SLIPPAGE_LIMIT",
    "SELL_SLIPPAGE_LIMIT",
    "AGGRESSIVE_TRADING_PROFILE",
    "MACRO_VETO_ALTS_IN_RISK_OFF",
    "MACRO_RISK_OFF_BTC_DOM",
    "MACRO_RISK_OFF_CAP_CHANGE_PCT",
    "MACRO_CAUTION_BTC_DOM",
    "MACRO_ALTSEASON_BTC_DOM",
    "MACRO_RISK_ON_MAX_BTC_DOM",
    "MACRO_CAUTION_RISK_OFF_BTC_DOM",
    "MACRO_REGIME_HYSTERESIS_CYCLES",
    "MACRO_BTC_DOM_TREND_WINDOW",
    "MIN_CONFIDENCE_ENTRY",
    "MTF_INCLUDE_15M",
    "MTF_DIVERGENCE_PENALTY",
    "BACKTEST_HARD_VETO_WIN_RATE",
    "BACKTEST_HARD_VETO_MIN_TRADES",
    "BACKTEST_MIN_TRADES_PER_BUCKET",
    "BACKTEST_MIN_SAMPLE_TRADES",
    "BACKTEST_BOOTSTRAP_SAMPLES",
    "BACKTEST_OOS_FRACTION",
    "SMALL_ACCOUNT_USDT_THRESHOLD",
    "SMALL_ACCOUNT_FORCE_MIN_ORDER",
    "DAEMON_CYCLE_SECONDS",
    "WATCHLIST_UPDATE_SECONDS",
    "DUST_WATCH_ENABLED",
    "DUST_AUTO_SELL_ENABLED",
    "DUST_SELL_MIN_USDT",
    "DUST_ALERT_ON_RECOVERABLE",
    "DUST_LOG_COMPACT_ENABLED",
    "ORDER_RECONCILE_ENABLED",
    "ORDER_RECONCILE_TIMEOUT_SECONDS",
    "ORDER_MAX_PENDING_SECONDS",
    "ORDER_CLIENT_ID_ENABLED",
    "ORDER_CLIENT_ID_PARAM",
    "BUY_FEE_BUFFER_PCT",
    "ORDERBOOK_DEPTH_LEVELS",
    "KILL_SWITCH_ENABLED",
    "MAX_EXCHANGE_ERRORS_PER_CYCLE",
    "MAX_UNRECONCILED_ORDERS",
    "AUTO_PAUSE_ON_DB_EXCHANGE_MISMATCH",
    "DB_EXCHANGE_MISMATCH_TOLERANCE_PCT",
    "DB_EXCHANGE_MISMATCH_MIN_USDT",
    "AUTO_PAUSE_ON_STALE_HEARTBEAT",
    "AI_ENABLE_LOCAL_BUDGET",
    "AI_MAX_REQUESTS_PER_CYCLE",
    "AI_MAX_REQUESTS_PER_DAY",
    "AI_MAX_EST_TOKENS_PER_DAY",
    "AI_RULES_ONLY_ON_BUDGET_EXHAUSTED",
    "AI_INVALID_RESPONSE_RULES_FALLBACK",
    "AI_MAX_OUTPUT_TOKENS",
    "AI_PROVIDER_TIMEOUT_SECONDS",
    "AI_MAX_POSITION_SIZE_MULTIPLIER",
    "ADD_TO_WINNER_ENABLED",
    "ADVANCED_EDGE_ENABLED",
    "ADVANCED_EDGE_MIN_RELIABILITY",
    "ADVANCED_EDGE_MIN_TRADES",
    "ADD_MIN_PROFIT_PCT",
    "ADD_MIN_SCORE",
    "ADD_MIN_CONFIDENCE",
    "ADD_MAX_PER_SYMBOL",
    "ADD_SIZE_MULTIPLIER",
    "BREAK_EVEN_ENABLED",
    "PARTIAL_TAKE_PROFIT_ENABLED",
    "PARTIAL_TAKE_PROFIT_PCT",
    "ALERTS_ENABLED",
    "ALERT_TIMEOUT_SECONDS",
    "ALERT_ORDER_FAILURES",
    "ALERT_MISMATCHES",
    "HEALTH_EXPORT_ENABLED",
    "STRUCTURED_LOGS_ENABLED",
    "AUDIT_EVENTS_ENABLED",
)

_SENSITIVE_KEY_RE = re.compile(
    r"(?i)([\"']?\b[A-Z0-9_.-]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASS|PRIVATE[_-]?KEY|"
    r"ACCESS[_-]?KEY|AUTHORIZATION)[A-Z0-9_.-]*[\"']?\s*[:=]\s*)([\"']?)([^\s,\"'}]+)"
)
_AUTH_HEADER_RE = re.compile(r"(?i)\b(Authorization\s*[:=]\s*)(?:Bearer|Basic)?\s*[A-Za-z0-9._~+/=-]{12,}")
_BEARER_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_LONG_TOKEN_RE = re.compile(r"\b(?=[A-Za-z0-9+/_.=-]*[A-Za-z])(?=[A-Za-z0-9+/_.=-]*\d)[A-Za-z0-9+/_.=-]{36,}\b")


def sanitize_text(text) -> str:
    """Redacta secretos comunes sin eliminar señales operativas útiles."""
    safe = str(text or "")
    safe = _EMAIL_RE.sub("[email-redacted]", safe)
    safe = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}[redacted]", safe)
    safe = _BEARER_RE.sub(lambda m: f"{m.group(1)} [redacted]", safe)
    safe = _SENSITIVE_KEY_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", safe)
    safe = _LONG_TOKEN_RE.sub("[redacted-token]", safe)
    return safe


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _tail_file(path: Path, limit: int) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError as exc:
        return [f"No se pudo leer {path.name}: {exc}"]


def _bounded_lines(lines, limit: int, max_len: int = 420) -> list[str]:
    out = []
    for line in lines[-limit:]:
        clean = sanitize_text(line).strip()
        if len(clean) > max_len:
            clean = clean[: max_len - 1].rstrip() + "…"
        if clean:
            out.append(clean)
    return out


def read_recent_log_summary(db=None, tail_lines: int = 80, focus_lines: int = 80) -> str:
    sections = []

    db_lines = []
    if db is not None and hasattr(db, "get_logs"):
        try:
            db_lines = db.get_logs()[-tail_lines:]
        except Exception as exc:
            db_lines = [f"No se pudieron leer logs de DB: {exc}"]
    if db_lines:
        sections.append("DB logs recientes:\n" + "\n".join(_bounded_lines(db_lines, min(tail_lines, 60))))

    for filename in ("daemon.log", "streamlit.log"):
        lines = _tail_file(LOG_DIR / filename, tail_lines)
        if not lines:
            continue
        focus = [line for line in lines if any(tag in line for tag in FOCUS_TAGS)]
        chosen = focus[-focus_lines:] if focus else lines[-min(tail_lines, 40):]
        sections.append(f"{filename} reciente:\n" + "\n".join(_bounded_lines(chosen, min(focus_lines, 80))))

    return "\n\n".join(sections) if sections else "Sin logs locales recientes disponibles."


def _diagnostic_config_keys() -> tuple[str, ...]:
    """Keys for diagnostics: static list plus schema keys for motor/edge groups."""
    seen = set(DIAGNOSTIC_CONFIG_KEYS)
    prefixes = (
        "PROTECTION_",
        "PAIRLIST_",
        "SCALED_",
        "POSITION_AGE_",
        "POSITION_MONITOR_",
        "LIMIT_BUY_",
        "FUNDING_",
        "WEBHOOK_",
        "INVENTORY_",
        "RULE_SIGNIFICANCE_",
        "HYPEROPT_",
        "OLLAMA_",
        "DCA_",
        "GRID_",
    )
    for key in CONFIG_SCHEMA:
        if key in seen:
            continue
        if any(key.startswith(p) for p in prefixes):
            seen.add(key)
    return tuple(seen)


def _safe_config_snapshot() -> dict:
    snapshot = {}
    for key in _diagnostic_config_keys():
        if key not in CONFIG_SCHEMA:
            continue
        default = config.DEFAULT_SETTINGS.get(key, "")
        snapshot[key] = config.get_setting(key, default)
    return snapshot


def _daemon_diagnostics(db) -> str:
    if db is None or not hasattr(db, "get_system_status"):
        return "No disponible: base de datos no inicializada."
    try:
        raw = db.get_system_status("daemon_diagnostics", "{}") or "{}"
        diag = json.loads(raw)
    except Exception as exc:
        return f"No disponible: {exc}"
    if not diag:
        return "Sin diagnóstico del daemon todavía."

    compact = {
        "state": diag.get("state"),
        "seconds_since_cycle": None,
        "scanned": diag.get("scanned"),
        "actions": diag.get("actions"),
        "providers": diag.get("providers"),
        "hold_reasons": dict(list((diag.get("hold_reasons") or {}).items())[:8]),
        "skipped": diag.get("skipped"),
        "open_positions": diag.get("open_positions"),
        "dynamic_max": diag.get("dynamic_max"),
        "risk_guards": diag.get("risk_guards"),
        "operational_guard": diag.get("operational_guard"),
        "kill_switch": diag.get("kill_switch"),
        "dust_watch": diag.get("dust_watch"),
        "ai_usage_24h": diag.get("ai_usage_24h"),
        "top_buy_candidates": (diag.get("top_buy_candidates") or [])[:5],
    }
    if diag.get("cycle_ts"):
        compact["seconds_since_cycle"] = int(max(0, time.time() - float(diag["cycle_ts"])))
    return sanitize_text(json.dumps(compact, indent=2, ensure_ascii=False))


def build_safe_diagnostic_package(db=None, exchange=None, include_instructions: bool = True) -> str:
    mode = "simulación" if config.get_setting("MODO_SIMULACION", True, bool) else "REAL"
    if exchange is not None and hasattr(exchange, "modo_simulacion"):
        mode = "simulación" if exchange.modo_simulacion else "REAL"

    balance = None
    effective_max = None
    if exchange is not None and hasattr(exchange, "get_balance"):
        try:
            balance = _safe_float(exchange.get_balance())
            effective_max = config.get_effective_max_positions(balance)
        except Exception:
            balance = None

    config_snapshot = _safe_config_snapshot()
    lines = [
        "=== PAQUETE DIAGNÓSTICO SEGURO INVERSORIA ===",
        "",
    ]
    if include_instructions:
        lines.extend([
            "Instrucciones para IA:",
            "- Analiza estos ajustes y logs recientes sin pedir claves API ni secretos.",
            "- Si propones cambios de configuración, devuelve solo claves permitidas y evita credenciales.",
            "- Prioriza riesgos operativos: modo real/simulación, límites, mínimos, rotación, bloqueos y errores.",
            "",
        ])

    lines.extend([
        "MODO / EJECUCIÓN:",
        f"- Modo actual: {mode}",
        f"- TRADING_EXECUTION_MODE: {config_snapshot.get('TRADING_EXECUTION_MODE')}",
        f"- DECISION_MODE: {config_snapshot.get('DECISION_MODE')}",
        f"- Balance estimado para límite dinámico: {balance:.2f} USDT" if balance is not None else "- Balance estimado: no disponible en esta pantalla",
        f"- Límite efectivo de posiciones: {effective_max}" if effective_max is not None else "- Límite efectivo de posiciones: no calculado",
        "",
        "CONFIGURACIÓN SEGURA RELEVANTE:",
        sanitize_text(json.dumps(config_snapshot, indent=2, ensure_ascii=False)),
        "",
        "DIAGNÓSTICO DEL DAEMON:",
        _daemon_diagnostics(db),
        "",
        "LOGS RECIENTES SANEADOS:",
        read_recent_log_summary(db=db),
        "",
        "NOTAS DE SEGURIDAD:",
        "- No se incluye .env ni JSON privado completo.",
        "- Las claves con API_KEY, TOKEN, SECRET, PASSWORD, AUTHORIZATION y correos se redactan.",
        "- Los logs se recortan para evitar enviar miles de líneas.",
    ])
    return sanitize_text("\n".join(lines))

