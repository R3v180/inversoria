"""Schema-driven configuration UI — every CONFIG_SCHEMA key editable from Ajustes."""

from __future__ import annotations

import json
import re
from typing import Any

import streamlit as st

from config import DEFAULT_SETTINGS, SENSITIVE_SETTING_KEYS, get_setting
from config_importer import CONFIG_SCHEMA
from i18n import _

# API keys edited only in the Conexiones tab.
CONNECTION_ONLY_KEYS = frozenset(SENSITIVE_SETTING_KEYS)

# Stored as fraction 0–1 but shown as % in the UI.
PERCENT_FRACTION_KEYS = frozenset(
    {
        "RISK_PER_TRADE",
        "TRADING_FEE_RATE",
        "BUY_SLIPPAGE_LIMIT",
        "SELL_SLIPPAGE_LIMIT",
    }
)

# Tab → section ids (connections tab uses CONNECTION_ONLY_KEYS only).
SETTINGS_TAB_OPERATION = "operation"
SETTINGS_TAB_RISK = "risk"
SETTINGS_TAB_ADVANCED = "advanced"

_TAB_SECTION_IDS: dict[str, frozenset[str]] = {
    SETTINGS_TAB_OPERATION: frozenset({"operation_core", "ai_brain"}),
    SETTINGS_TAB_RISK: frozenset({"positions_limits", "risk_exposure", "stops_exits", "rotation"}),
    SETTINGS_TAB_ADVANCED: frozenset(),  # all sections not in operation/risk
}

# Sections: (id, title_i18n_key, collapsed_by_default, explicit keys)
_UI_SECTION_DEFS: list[tuple[str, str, bool, tuple[str, ...]]] = [
    (
        "operation_core",
        "CFG_SEC_OPERATION",
        False,
        (
            "MODO_SIMULACION",
            "SIMULATION_PROFILE_ID",
            "PRESUPUESTO_INICIAL",
            "TRADING_EXECUTION_MODE",
            "DECISION_MODE",
            "MIN_AUTO_DECISION_SCORE",
            "AGGRESSIVE_TRADING_PROFILE",
            "MONEDAS",
            "PORTFOLIO_BUCKETS",
            "MIN_CONFIDENCE_ENTRY",
            "PAIRLIST_LIQUIDITY_FILTER_ENABLED",
            "PAIRLIST_MAX_SPREAD_PCT",
            "PAIRLIST_MIN_QUOTE_VOLUME_USDT",
        ),
    ),
    (
        "positions_limits",
        "CFG_SEC_POSITIONS_LIMITS",
        False,
        (
            "MANUAL_MAX_POSITIONS_PRIORITY",
            "MAX_OPEN_POSITIONS",
            "RISK_PER_TRADE",
            "MIN_PROFIT_NET",
        ),
    ),
    (
        "risk_exposure",
        "CFG_SEC_RISK",
        False,
        (
            "MAX_DAILY_LOSS_PCT",
            "MAX_PORTFOLIO_DRAWDOWN_PCT",
            "DRAWDOWN_COOLDOWN_HOURS",
            "MAX_PORTFOLIO_EXPOSURE_PCT",
            "MAX_SYMBOL_EXPOSURE_PCT",
            "MAX_ALT_EXPOSURE_PCT",
            "MAX_BUCKET_EXPOSURE_PCT",
            "VOLATILITY_SIZING_ENABLED",
            "MAX_POSITION_RISK_PCT",
            "MAX_VOLATILITY_POSITION_MULTIPLIER",
            "MIN_POSITION_USDT",
            "ADAPTIVE_SCORING_ENABLED",
            "ADAPTIVE_MIN_TRADES",
            "ADAPTIVE_MAX_SCORE_ADJUSTMENT",
            "METRICS_ROLLING_WINDOW",
            "SMALL_ACCOUNT_USDT_THRESHOLD",
            "SMALL_ACCOUNT_FORCE_MIN_ORDER",
            "SMALL_ACCOUNT_MAX_STOP_DISTANCE_PCT",
        ),
    ),
    (
        "stops_exits",
        "CFG_SEC_STOPS",
        False,
        (
            "STOP_LOSS_PERCENT",
            "ATR_STOP_ENABLED",
            "STOP_LOSS_ATR_MULT",
            "ATR_TRAILING_ENABLED",
            "TRAILING_ATR_MULT",
            "TRAILING_ACTIVATION_PCT",
            "BREAK_EVEN_ACTIVATION_PCT",
            "BREAK_EVEN_ENABLED",
            "MAX_POSITION_AGE_HOURS",
            "STOP_LOSS_COOLDOWN_MINUTES",
            "TAKE_PROFIT_COOLDOWN_MINUTES",
            "PARTIAL_TAKE_PROFIT_ENABLED",
            "PARTIAL_TAKE_PROFIT_PCT",
        ),
    ),
    (
        "rotation",
        "CFG_SEC_ROTATION",
        False,
        (
            "ROTATION_ENABLED",
            "ROTATION_MIN_PROFIT",
            "ROTATION_CONFIDENCE_GAP",
            "ROTATION_MIN_NEW_CONFIDENCE",
        ),
    ),
    (
        "ai_brain",
        "CFG_SEC_AI",
        False,
        (
            "AI_ANALYSIS_INTERVAL",
            "AI_BATCH_DECISIONS_ENABLED",
            "AI_ENABLE_LOCAL_BUDGET",
            "AI_MAX_REQUESTS_PER_CYCLE",
            "AI_MAX_REQUESTS_PER_DAY",
            "AI_MAX_EST_TOKENS_PER_DAY",
            "AI_RULES_ONLY_ON_BUDGET_EXHAUSTED",
            "AI_INVALID_RESPONSE_RULES_FALLBACK",
            "AI_MAX_OUTPUT_TOKENS",
            "AI_PROVIDER_TIMEOUT_SECONDS",
            "AI_MAX_POSITION_SIZE_MULTIPLIER",
        ),
    ),
    (
        "prompts",
        "CFG_SEC_PROMPTS",
        True,
        ("PROMPT_SENTIMENT", "PROMPT_DECISION", "PROMPT_CURATION"),
    ),
    (
        "macro_mtf",
        "CFG_SEC_MACRO",
        True,
        (
            "MACRO_VETO_ALTS_IN_RISK_OFF",
            "MACRO_RISK_OFF_BTC_DOM",
            "MACRO_RISK_OFF_CAP_CHANGE_PCT",
            "MACRO_CAUTION_BTC_DOM",
            "MACRO_ALTSEASON_BTC_DOM",
            "MACRO_RISK_ON_MAX_BTC_DOM",
            "MACRO_CAUTION_RISK_OFF_BTC_DOM",
            "MACRO_REGIME_HYSTERESIS_CYCLES",
            "MACRO_BTC_DOM_TREND_WINDOW",
            "MACRO_DXY_VETO_PCT",
            "MACRO_SPY_VETO_PCT",
            "MTF_ALLOW_COUNTER_TREND",
            "MTF_INCLUDE_15M",
            "MTF_DIVERGENCE_PENALTY",
        ),
    ),
    (
        "backtest",
        "CFG_SEC_BACKTEST",
        True,
        (
            "BACKTEST_HARD_VETO_WIN_RATE",
            "BACKTEST_HARD_VETO_MIN_TRADES",
            "BACKTEST_MIN_TRADES_PER_BUCKET",
            "BACKTEST_MIN_SAMPLE_TRADES",
            "BACKTEST_BOOTSTRAP_SAMPLES",
            "BACKTEST_OOS_FRACTION",
            "BACKTEST_DYNAMIC_SLIPPAGE_ENABLED",
            "BACKTEST_DYNAMIC_SLIPPAGE_CAP",
        ),
    ),
    (
        "fees",
        "CFG_GROUP_FEES",
        True,
        (
            "TRADING_FEE_RATE",
            "BUY_SLIPPAGE_LIMIT",
            "SELL_SLIPPAGE_LIMIT",
            "BUY_FEE_BUFFER_PCT",
        ),
    ),
    (
        "motor_gh1",
        "CFG_GROUP_MOTOR_GH1",
        True,
        (
            "PROTECTIONS_ENABLED",
            "PROTECTION_STOPLOSS_GUARD_COUNT",
            "PROTECTION_STOPLOSS_LOOKBACK_HOURS",
            "PROTECTION_LOW_PROFIT_MIN_TRADES",
            "PROTECTION_LOW_PROFIT_MAX_EXPECTANCY_PCT",
            "SCALED_TAKE_PROFIT_ENABLED",
            "SCALED_TAKE_PROFIT_LEVELS",
            "POSITION_AGE_DECAY_ENABLED",
            "POSITION_AGE_DECAY_START_HOURS",
            "POSITION_AGE_DECAY_MIN_PROFIT_PCT",
            "LIMIT_BUY_ENABLED",
            "LIMIT_BUY_PULLBACK_PCT",
            "FUNDING_VETO_ENABLED",
            "FUNDING_VETO_MAX_LONG_PCT",
            "POSITION_MONITOR_ENABLED",
            "POSITION_MONITOR_INTERVAL_SEC",
            "POSITION_MONITOR_SELLS_ENABLED",
        ),
    ),
    (
        "edge_gh2",
        "CFG_GROUP_EDGE_GH2",
        True,
        (
            "INVENTORY_SKEW_ENABLED",
            "INVENTORY_SKEW_TARGET_SYMBOL_PCT",
            "INVENTORY_SKEW_MAX_BOOST",
            "INVENTORY_SKEW_MIN_REDUCE",
            "RULE_SIGNIFICANCE_ENABLED",
            "RULE_SIGNIFICANCE_MIN_TRADES",
            "RULE_SIGNIFICANCE_MAX_ADJ",
            "RULE_SIGNIFICANCE_MIN_WIN_RATE",
            "HYPEROPT_LITE_ENABLED",
            "HYPEROPT_RISK_GRID",
            "HYPEROPT_STOP_LOSS_GRID",
            "WEBHOOK_TRADINGVIEW_ENABLED",
            "WEBHOOK_SERVER_PORT",
            "WEBHOOK_TRADINGVIEW_SECRET",
            "WEBHOOK_AUTO_APPROVE",
            "DCA_GRID_ENABLED",
            "DCA_MAX_TRANCHES",
            "DCA_TRANCHE_MULTIPLIER",
            "GRID_LEVELS",
            "GRID_SPACING_PCT",
            "OLLAMA_ENABLED",
            "OLLAMA_BASE_URL",
            "OLLAMA_MODEL",
        ),
    ),
    (
        "daemon_dust_orders",
        "CFG_SEC_DAEMON",
        True,
        (
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
            "ORDERBOOK_DEPTH_LEVELS",
        ),
    ),
    (
        "safety_alerts",
        "CFG_SEC_SAFETY",
        True,
        (
            "KILL_SWITCH_ENABLED",
            "MAX_EXCHANGE_ERRORS_PER_CYCLE",
            "MAX_UNRECONCILED_ORDERS",
            "AUTO_PAUSE_ON_DB_EXCHANGE_MISMATCH",
            "DB_EXCHANGE_MISMATCH_TOLERANCE_PCT",
            "DB_EXCHANGE_MISMATCH_MIN_USDT",
            "AUTO_PAUSE_ON_STALE_HEARTBEAT",
            "ALERTS_ENABLED",
            "ALERT_WEBHOOK_URL",
            "ALERT_TIMEOUT_SECONDS",
            "ALERT_ORDER_FAILURES",
            "ALERT_MISMATCHES",
            "HEALTH_EXPORT_ENABLED",
            "STRUCTURED_LOGS_ENABLED",
            "AUDIT_EVENTS_ENABLED",
        ),
    ),
    (
        "position_edge",
        "CFG_SEC_POSITION",
        True,
        (
            "ADVANCED_EDGE_ENABLED",
            "ADVANCED_EDGE_MIN_RELIABILITY",
            "ADVANCED_EDGE_MIN_TRADES",
            "ADD_TO_WINNER_ENABLED",
            "ADD_MIN_PROFIT_PCT",
            "ADD_MIN_SCORE",
            "ADD_MIN_CONFIDENCE",
            "ADD_MAX_PER_SYMBOL",
            "ADD_SIZE_MULTIPLIER",
        ),
    ),
]

_PREFIX_SECTIONS: list[tuple[str, str]] = [
    ("PROTECTION_", "CFG_GROUP_MOTOR_GH1"),
    ("PAIRLIST_", "CFG_GROUP_MOTOR_GH1"),
    ("SCALED_", "CFG_GROUP_MOTOR_GH1"),
    ("POSITION_", "CFG_GROUP_MOTOR_GH1"),
    ("LIMIT_BUY_", "CFG_GROUP_MOTOR_GH1"),
    ("FUNDING_", "CFG_GROUP_MOTOR_GH1"),
    ("INVENTORY_", "CFG_GROUP_EDGE_GH2"),
    ("RULE_SIGNIFICANCE_", "CFG_GROUP_EDGE_GH2"),
    ("HYPEROPT_", "CFG_GROUP_EDGE_GH2"),
    ("WEBHOOK_", "CFG_GROUP_EDGE_GH2"),
    ("DCA_", "CFG_GROUP_EDGE_GH2"),
    ("GRID_", "CFG_GROUP_EDGE_GH2"),
    ("OLLAMA_", "CFG_GROUP_EDGE_GH2"),
    ("MACRO_", "CFG_SEC_MACRO"),
    ("BACKTEST_", "CFG_SEC_BACKTEST"),
    ("AI_", "CFG_SEC_AI"),
    ("ROTATION_", "CFG_SEC_ROTATION"),
    ("MTF_", "CFG_SEC_MACRO"),
    ("ORDER_", "CFG_SEC_DAEMON"),
    ("DUST_", "CFG_SEC_DAEMON"),
    ("ALERT_", "CFG_SEC_SAFETY"),
    ("ADD_", "CFG_SEC_POSITION"),
    ("ADVANCED_", "CFG_SEC_POSITION"),
]


def _default_for(key: str):
    return DEFAULT_SETTINGS.get(key)


def _label_for(key: str) -> str:
    i18n_key = f"CFG_KEY_{key}"
    text = _(i18n_key)
    return text if text != i18n_key else key.replace("_", " ").title()


def _help_for(key: str) -> str | None:
    i18n_key = f"CFG_HELP_{key}"
    text = _(i18n_key)
    return None if text == i18n_key else text


def _read_raw(key: str) -> Any:
    default = _default_for(key)
    spec = CONFIG_SCHEMA.get(key, {})
    expected = spec.get("type")
    if expected is bool:
        return bool(get_setting(key, default, bool))
    if expected is int:
        return int(get_setting(key, default, int))
    if expected is float:
        return float(get_setting(key, default, float))
    if expected == "bucket_map":
        val = get_setting(key, default)
        if isinstance(val, dict):
            return json.dumps(val, indent=2, ensure_ascii=False)
        return str(val or "")
    if expected == "json_list":
        val = get_setting(key, default)
        if isinstance(val, list):
            return json.dumps(val, ensure_ascii=False)
        return str(val or "")
    if expected == "symbols":
        val = get_setting(key, default, str)
        return str(val or "")
    val = get_setting(key, default)
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val if val is not None else "")


def _display_float(key: str, raw: float) -> float:
    if key in PERCENT_FRACTION_KEYS and raw <= 1.0:
        return float(raw) * 100.0
    spec = CONFIG_SCHEMA.get(key, {})
    if spec.get("percent") and raw <= 1.0:
        return float(raw) * 100.0
    return float(raw)


def _prepare_submit_value(key: str, value: Any) -> Any:
    if key in PERCENT_FRACTION_KEYS and isinstance(value, (int, float)) and value > 1:
        return float(value) / 100.0
    spec = CONFIG_SCHEMA.get(key, {})
    if spec.get("type") is float and spec.get("percent") and isinstance(value, (int, float)) and value > 1:
        return float(value) / 100.0
    if spec.get("type") == "bucket_map" and isinstance(value, str):
        return value
    if spec.get("type") == "json_list" and isinstance(value, str):
        return value
    if spec.get("type") == "symbols" and isinstance(value, str):
        return value
    return value


def _build_sections() -> list[dict]:
    assigned: set[str] = set()
    sections: list[dict] = []
    for sid, title_key, collapsed, keys in _UI_SECTION_DEFS:
        valid = [k for k in keys if k in CONFIG_SCHEMA and k not in CONNECTION_ONLY_KEYS]
        assigned.update(valid)
        if valid:
            sections.append(
                {
                    "id": sid,
                    "title_key": title_key,
                    "collapsed": collapsed,
                    "keys": valid,
                }
            )

    remaining = sorted(
        k for k in CONFIG_SCHEMA if k not in assigned and k not in CONNECTION_ONLY_KEYS
    )
    if remaining:
        by_title: dict[str, list[str]] = {}
        for key in remaining:
            title_key = "CFG_SEC_OTHER"
            for prefix, tkey in _PREFIX_SECTIONS:
                if key.startswith(prefix):
                    title_key = tkey
                    break
            by_title.setdefault(title_key, []).append(key)
        for idx, (title_key, keys) in enumerate(sorted(by_title.items(), key=lambda x: x[0])):
            sections.append(
                {
                    "id": f"auto_{idx}",
                    "title_key": title_key,
                    "collapsed": True,
                    "keys": keys,
                }
            )
    return sections


def render_schema_field(key: str, *, key_prefix: str = "cfg") -> Any:
    """Render one widget; return raw value for validate_config_payload."""
    spec = CONFIG_SCHEMA[key]
    expected = spec["type"]
    widget_key = f"{key_prefix}_{key}"
    label = _label_for(key)
    help_text = _help_for(key)

    if expected is bool:
        return st.checkbox(label, value=bool(_read_raw(key)), key=widget_key, help=help_text)

    if expected is int:
        kwargs = {"step": 1, "key": widget_key, "help": help_text}
        if "min" in spec:
            kwargs["min_value"] = int(spec["min"])
        if "max" in spec:
            kwargs["max_value"] = int(spec["max"])
        return st.number_input(label, value=int(_read_raw(key)), **kwargs)

    if expected is float:
        raw = float(_read_raw(key))
        display = _display_float(key, raw)
        kwargs = {"step": 0.01, "key": widget_key, "help": help_text, "format": "%.4f"}
        if "min" in spec:
            lo = float(spec["min"])
            if key in PERCENT_FRACTION_KEYS or spec.get("percent"):
                lo = lo * 100 if lo <= 1 else lo
            kwargs["min_value"] = lo
        if "max" in spec:
            hi = float(spec["max"])
            if key in PERCENT_FRACTION_KEYS or spec.get("percent"):
                hi = hi * 100 if hi <= 1 else hi
            kwargs["max_value"] = hi
        return st.number_input(label, value=float(display), **kwargs)

    if expected == "choice":
        choices = sorted(spec["choices"])
        current = str(_read_raw(key)).strip().lower()
        idx = choices.index(current) if current in choices else 0
        labels = {c: _(f"CFG_CHOICE_{key}_{c}") for c in choices}
        return st.selectbox(
            label,
            options=choices,
            index=idx,
            format_func=lambda c: labels.get(c, c) if labels.get(c, c) != f"CFG_CHOICE_{key}_{c}" else c,
            key=widget_key,
            help=help_text,
        )

    if expected == "symbols":
        return st.text_area(label, value=str(_read_raw(key)), height=90, key=widget_key, help=help_text)

    if expected == "bucket_map":
        return st.text_area(label, value=str(_read_raw(key)), height=160, key=widget_key, help=help_text)

    if expected == "json_list":
        return st.text_area(label, value=str(_read_raw(key)), height=70, key=widget_key, help=help_text)

    if key.startswith("PROMPT_"):
        return st.text_area(label, value=str(_read_raw(key)), height=120, key=widget_key, help=help_text)

    secret = key.endswith("_SECRET") or key in {"ALERT_WEBHOOK_URL", "WEBHOOK_TRADINGVIEW_SECRET"}
    return st.text_input(
        label,
        value=str(_read_raw(key)),
        type="password" if secret else "default",
        key=widget_key,
        help=help_text,
    )


def render_config_section(
    section: dict,
    *,
    key_prefix: str = "cfg",
    search: str = "",
) -> dict:
    keys = section["keys"]
    if search:
        needle = search.strip().lower()
        keys = [k for k in keys if needle in k.lower() or needle in _label_for(k).lower()]
    if not keys:
        return {}

    title = _(section["title_key"])
    container = st.expander(title, expanded=not section["collapsed"]) if section["collapsed"] else st.container()
    out: dict = {}
    with container:
        if not section["collapsed"]:
            st.markdown(f"##### {title}")
        cols = st.columns(2)
        for idx, key in enumerate(keys):
            with cols[idx % 2]:
                out[key] = render_schema_field(key, key_prefix=key_prefix)
    return out


def _sections_for_tab(tab_id: str) -> list[dict]:
    all_sections = _build_sections()
    if tab_id == SETTINGS_TAB_ADVANCED:
        used = _TAB_SECTION_IDS[SETTINGS_TAB_OPERATION] | _TAB_SECTION_IDS[SETTINGS_TAB_RISK]
        return [s for s in all_sections if s["id"] not in used]
    allowed = _TAB_SECTION_IDS.get(tab_id, frozenset())
    return [s for s in all_sections if s["id"] in allowed]


def render_settings_tab_ui(
    tab_id: str,
    *,
    key_prefix: str = "cfg",
    search: str = "",
    show_tab_caption: bool = True,
) -> dict:
    """Render CONFIG_SCHEMA fields for one settings tab."""
    captions = {
        SETTINGS_TAB_OPERATION: "CFG_TAB_OPERATION_CAPTION",
        SETTINGS_TAB_RISK: "CFG_TAB_RISK_CAPTION",
        SETTINGS_TAB_ADVANCED: "CFG_TAB_ADVANCED_CAPTION",
    }
    cap_key = captions.get(tab_id)
    if show_tab_caption and cap_key:
        text = _(cap_key)
        if text != cap_key:
            st.caption(text)

    merged: dict = {}
    for section in _sections_for_tab(tab_id):
        merged.update(render_config_section(section, key_prefix=key_prefix, search=search))
    if search and not merged:
        st.info(_("CFG_SEARCH_EMPTY"))
    return {k: _prepare_submit_value(k, v) for k, v in merged.items()}


def render_complete_config_ui(*, key_prefix: str = "cfg_all") -> dict:
    """All CONFIG_SCHEMA keys except API credentials (legacy / advanced search)."""
    return render_settings_tab_ui(
        SETTINGS_TAB_ADVANCED,
        key_prefix=key_prefix,
        search=st.session_state.get(f"{key_prefix}_search", ""),
        show_tab_caption=False,
    )


def schema_keys_count() -> int:
    return len([k for k in CONFIG_SCHEMA if k not in CONNECTION_ONLY_KEYS])


# Backward compatibility
def render_motor_tab(*, key_prefix: str = "motor") -> dict:
    return render_complete_config_ui(key_prefix=key_prefix)
