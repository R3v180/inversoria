import streamlit as st
import json
import os
from config import get_setting, USER_SETTINGS_FILE, save_settings, reset_to_defaults, DEFAULT_SETTINGS
from config_importer import (
    apply_config_changes,
    config_example_json,
    current_safe_config_json,
    diff_config_changes,
    parse_config_payload,
    validate_config_payload,
)
from diagnostic_utils import build_safe_diagnostic_package
from i18n import _


def _render_ai_diagnostic_package():
    with st.container(border=True):
        st.subheader(_("DIAG_AI_TITLE"))
        st.caption(_("DIAG_AI_HELP"))

        db = st.session_state.get("db")
        exchange = st.session_state.get("exchange")
        if st.button(_("DIAG_AI_GENERATE"), type="secondary"):
            st.session_state["settings_ai_diagnostic_package"] = build_safe_diagnostic_package(
                db=db,
                exchange=exchange,
            )

        package = st.session_state.get("settings_ai_diagnostic_package")
        if not package:
            st.info(_("DIAG_AI_EMPTY"))
            return

        st.text_area(
            _("DIAG_AI_TEXT_LABEL"),
            value=package,
            height=360,
            help=_("DIAG_AI_TEXT_HELP"),
        )
        st.download_button(
            _("DIAG_AI_DOWNLOAD"),
            data=package,
            file_name="inversoria_diagnostico_ia.txt",
            mime="text/plain",
            width="stretch",
        )


def _render_config_import_export():
    st.markdown("---")
    st.subheader(_("CONFIG_IO_TITLE"))
    st.caption(_("CONFIG_IO_HELP"))

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            _("CONFIG_DOWNLOAD_EXAMPLE"),
            data=config_example_json(),
            file_name="inversoria_config_example.json",
            mime="application/json",
            width="stretch",
        )
    with c2:
        st.download_button(
            _("CONFIG_DOWNLOAD_CURRENT"),
            data=current_safe_config_json(),
            file_name="inversoria_config_actual_safe.json",
            mime="application/json",
            width="stretch",
        )

    _render_ai_diagnostic_package()

    raw_config = st.text_area(
        _("CONFIG_IMPORT_LABEL"),
        height=220,
        placeholder=config_example_json(),
        help=_("CONFIG_IMPORT_HELP"),
    )

    if st.button(_("CONFIG_VALIDATE"), type="secondary"):
        try:
            payload = parse_config_payload(raw_config)
            changes, warnings, blocked, errors = validate_config_payload(payload)
        except Exception as exc:
            st.error(f"{_('CONFIG_IMPORT_ERROR')}: {exc}")
            return

        if errors:
            st.error(_("CONFIG_IMPORT_ERROR"))
            for err in errors:
                st.caption(f"- {err}")
            return
        if not changes:
            st.warning(_("CONFIG_NO_CHANGES"))
            return

        st.session_state.pending_config_import = {
            "changes": changes,
            "warnings": warnings,
            "blocked": blocked,
        }
        st.rerun()

    pending = st.session_state.get("pending_config_import")
    if not pending:
        return

    changes = pending.get("changes", {})
    warnings = pending.get("warnings", [])
    blocked = pending.get("blocked", [])
    rows = diff_config_changes(changes)

    with st.container(border=True):
        st.warning(_("CONFIG_PENDING_WARNING"))
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.info(_("CONFIG_NO_EFFECTIVE_DIFF"))
        if warnings:
            with st.expander(_("CONFIG_WARNINGS")):
                for warning in warnings:
                    st.caption(f"- {warning}")
        if blocked:
            st.info(_("CONFIG_BLOCKED_KEYS").format(", ".join(blocked)))

        a1, a2 = st.columns(2)
        if a1.button(_("CONFIG_APPLY"), type="primary", width="stretch"):
            backup = apply_config_changes(changes)
            st.session_state.pop("pending_config_import", None)
            if backup:
                st.success(_("CONFIG_APPLIED_BACKUP").format(backup))
            else:
                st.success(_("CONFIG_APPLIED"))
            st.rerun()
        if a2.button(_("CONFIG_DISCARD"), width="stretch"):
            st.session_state.pop("pending_config_import", None)
            st.rerun()

def render_settings():
    st.title(_('SETTINGS_TITLE'))
    
    # ...
    
    # Botón de Reset fuera del formulario para acción inmediata
    col_reset1, col_reset2 = st.columns([4, 1])
    with col_reset2:
        if st.button(_('RESET_GLOBAL'), help=_('RESET_HELP'), type="secondary"):
            reset_to_defaults()
            st.rerun()

    with st.form("settings_form"):
        tab1, tab2, tab3, tab4 = st.tabs([_('TAB_CONNECTIONS'), _('TAB_RISK'), _('TAB_AI'), "Avanzado"])
        
        with tab1:
            st.subheader(_('API_CREDENTIALS'))
            st.caption("Por seguridad, las API keys se leen desde `.env`/variables de entorno y no se guardan en user_settings.json.")
            crypto_api = st.text_input("Crypto.com API Key", value=get_setting('CRYPTO_API_KEY', ''), type="password")
            crypto_sec = st.text_input("Crypto.com API Secret", value=get_setting('CRYPTO_API_SECRET', ''), type="password")
            groq_api = st.text_input("Groq API Key", value=get_setting('GROQ_API_KEY', ''), type="password")
            google_api = st.text_input("Google AI Key (Gemini)", value=get_setting('GOOGLE_API_KEY', ''), type="password")
            sambanova_api = st.text_input("SambaNova API Key", value=get_setting('SAMBANOVA_API_KEY', ''), type="password")
            coindesk_api = st.text_input("News API Key", value=get_setting('COINDESK_API_KEY', ''), type="password")

        with tab2:
            st.subheader(_('CAPITAL_MGMT'))
            exec_labels = {
                "auto": "Auto",
                "consultive": "Consultivo / señales",
            }
            decision_labels = {
                "ai_aggressive": "IA agresiva",
                "hybrid": "Híbrido",
                "rules": "Reglas / quant",
            }
            execution_mode = st.selectbox(
                _('EXECUTION_MODE_L'),
                options=list(exec_labels.keys()),
                format_func=lambda key: exec_labels.get(key, key),
                index=list(exec_labels.keys()).index(get_setting('TRADING_EXECUTION_MODE', 'auto')) if get_setting('TRADING_EXECUTION_MODE', 'auto') in exec_labels else 0,
                help=_('EXECUTION_MODE_HELP'),
            )
            decision_mode = st.selectbox(
                _('DECISION_MODE_L'),
                options=list(decision_labels.keys()),
                format_func=lambda key: decision_labels.get(key, key),
                index=list(decision_labels.keys()).index(get_setting('DECISION_MODE', 'hybrid')) if get_setting('DECISION_MODE', 'hybrid') in decision_labels else 1,
                help=_('DECISION_MODE_HELP'),
            )
            col1, col2 = st.columns(2)
            with col1:
                modo_sim = st.checkbox(_('MODE_SIM'), value=get_setting('MODO_SIMULACION', True, bool))
                presupuesto = st.number_input(_('INITIAL_CAPITAL'), value=get_setting('PRESUPUESTO_INICIAL', 60.0, float))
                min_score = st.slider(_('MIN_SCORE_L'), 0.0, 1.0, get_setting('MIN_AUTO_DECISION_SCORE', 0.62, float), step=0.01)
                max_daily_loss = st.slider(_('MAX_DAILY_LOSS_L'), 0.1, 50.0, get_setting('MAX_DAILY_LOSS_PCT', 5.0, float), step=0.1)
                vol_sizing = st.checkbox(_('VOL_SIZING_L'), value=get_setting('VOLATILITY_SIZING_ENABLED', True, bool))
                max_position_risk = st.slider(_('MAX_POSITION_RISK_L'), 0.1, 10.0, get_setting('MAX_POSITION_RISK_PCT', 1.0, float), step=0.1)
                min_position_usdt = st.number_input(_('MIN_POSITION_USDT_L'), min_value=0.1, value=get_setting('MIN_POSITION_USDT', 1.0, float), step=0.5)
            with col2:
                manual_cap = st.checkbox(
                    _('MANUAL_POS_PRIORITY'),
                    value=get_setting('MANUAL_MAX_POSITIONS_PRIORITY', False, bool),
                    help=_('MANUAL_POS_PRIORITY_HELP'),
                )
                max_pos = st.number_input(
                    _('MAX_POSITIONS_L'),
                    min_value=1,
                    max_value=10,
                    value=get_setting('MAX_OPEN_POSITIONS', 5, int),
                    help=_('MAX_POSITIONS_HELP'),
                )
                riesgo = st.slider(_('RISK_PER_TRADE_L'), 1, 100, int(get_setting('RISK_PER_TRADE', 0.02, float)*100))
                max_exposure = st.slider(_('MAX_EXPOSURE_L'), 1.0, 100.0, get_setting('MAX_PORTFOLIO_EXPOSURE_PCT', 85.0, float), step=1.0)
                max_symbol_exposure = st.slider(_('MAX_SYMBOL_EXPOSURE_L'), 1.0, 100.0, get_setting('MAX_SYMBOL_EXPOSURE_PCT', 30.0, float), step=1.0)
                max_alt_exposure = st.slider(_('MAX_ALT_EXPOSURE_L'), 1.0, 100.0, get_setting('MAX_ALT_EXPOSURE_PCT', 75.0, float), step=1.0)
                max_bucket_exposure = st.slider(_('MAX_BUCKET_EXPOSURE_L'), 1.0, 100.0, get_setting('MAX_BUCKET_EXPOSURE_PCT', 45.0, float), step=1.0)
                adaptive_scoring = st.checkbox(_('ADAPTIVE_SCORING_L'), value=get_setting('ADAPTIVE_SCORING_ENABLED', True, bool))
                adaptive_min_trades = st.number_input(_('ADAPTIVE_MIN_TRADES_L'), min_value=3, max_value=100, value=get_setting('ADAPTIVE_MIN_TRADES', 5, int), step=1)
                adaptive_max_adjustment = st.slider(_('ADAPTIVE_MAX_ADJ_L'), 0.0, 0.30, get_setting('ADAPTIVE_MAX_SCORE_ADJUSTMENT', 0.12, float), step=0.01)
                max_vol_mult = st.slider(_('MAX_VOL_MULT_L'), 0.1, 3.0, get_setting('MAX_VOLATILITY_POSITION_MULTIPLIER', 1.0, float), step=0.1)
                metrics_window = st.number_input(_('METRICS_WINDOW_L'), min_value=5, max_value=500, value=get_setting('METRICS_ROLLING_WINDOW', 30, int), step=5)
                min_profit = st.number_input(
                    _('MIN_PROFIT_L'),
                    min_value=0.1,
                    max_value=20.0,
                    value=get_setting('MIN_PROFIT_NET', 3.0, float),
                    step=0.1,
                    help=_('MIN_PROFIT_NET_HELP')
                )
                stop_loss_percent = st.number_input(
                    "Stop-loss base (%)",
                    min_value=0.1,
                    max_value=50.0,
                    value=get_setting('STOP_LOSS_PERCENT', 2.0, float),
                    step=0.1,
                    help="Fallback porcentual configurable. En fases siguientes se unificará con ATR/backtest.",
                )
                atr_stop_enabled = st.checkbox("Stop-loss basado en ATR", value=get_setting('ATR_STOP_ENABLED', True, bool))
                stop_loss_atr_mult = st.number_input("Multiplicador ATR stop", min_value=0.2, max_value=10.0, value=get_setting('STOP_LOSS_ATR_MULT', 1.5, float), step=0.1)
                atr_trailing_enabled = st.checkbox("Trailing basado en ATR", value=get_setting('ATR_TRAILING_ENABLED', True, bool))
                trailing_atr_mult = st.number_input("Multiplicador ATR trailing", min_value=0.2, max_value=15.0, value=get_setting('TRAILING_ATR_MULT', 2.5, float), step=0.1)
                trailing_activation_pct = st.number_input("Activación trailing (%)", min_value=0.1, max_value=50.0, value=get_setting('TRAILING_ACTIVATION_PCT', 2.0, float), step=0.1)
                break_even_activation_pct = st.number_input("Activación break-even (%)", min_value=0.1, max_value=50.0, value=get_setting('BREAK_EVEN_ACTIVATION_PCT', 1.5, float), step=0.1)
                max_position_age_hours = st.number_input("Edad máxima posición (h)", min_value=1, max_value=8760, value=get_setting('MAX_POSITION_AGE_HOURS', 168, int), step=1)
                stop_loss_cooldown_minutes = st.number_input("Cooldown tras stop-loss (min)", min_value=0, max_value=10080, value=get_setting('STOP_LOSS_COOLDOWN_MINUTES', 180, int), step=15)
                take_profit_cooldown_minutes = st.number_input("Cooldown tras take-profit/trailing (min)", min_value=0, max_value=10080, value=get_setting('TAKE_PROFIT_COOLDOWN_MINUTES', 45, int), step=15)
            
            st.markdown("---")
            st.subheader(_('ROTATION_MODULE'))
            rot_en = st.checkbox(_('ENABLE_ROTATION'), value=get_setting('ROTATION_ENABLED', True, bool))
            col3, col4 = st.columns(2)
            with col3:
                rot_prof = st.slider(_('MIN_PROFIT_ROT'), 0.0, 5.0, get_setting('ROTATION_MIN_PROFIT', 0.35, float), step=0.05)
                rot_gap = st.slider(_('CONF_GAP'), 0.05, 0.50, get_setting('ROTATION_CONFIDENCE_GAP', 0.20, float), step=0.05)
            with col4:
                rot_min_new = st.slider(_('MIN_NEW_CONF'), 0.60, 0.95, get_setting('ROTATION_MIN_NEW_CONFIDENCE', 0.85, float), step=0.05)
                ai_interval_min = st.slider(_('AI_FREQ'), 5, 120, int(get_setting('AI_ANALYSIS_INTERVAL', 1200, int)/60))

        with tab3:
            st.subheader(_('LINGUISTIC_BRAIN'))
            st.warning(_('PROMPT_WARNING'))
            
            p_sent = st.text_area(_('PROMPT_SENTIMENT_LABEL'), value=get_setting('PROMPT_SENTIMENT', DEFAULT_SETTINGS['PROMPT_SENTIMENT']), height=100)
            p_dec = st.text_area(_('PROMPT_DECISION_LABEL'), value=get_setting('PROMPT_DECISION', DEFAULT_SETTINGS['PROMPT_DECISION']), height=100)
            p_cur = st.text_area(_('PROMPT_CURATION_LABEL'), value=get_setting('PROMPT_CURATION', DEFAULT_SETTINGS['PROMPT_CURATION']), height=100)

        with tab4:
            st.subheader("Gobierno operativo")
            st.caption("Parámetros base para dust, órdenes, kill-switches, presupuesto IA y futuras reglas de posición. Algunos preparan funciones que se implementan en issues separadas.")

            st.markdown("##### Ciclo y radar")
            col_a, col_b = st.columns(2)
            with col_a:
                daemon_cycle_seconds = st.number_input("Segundos entre ciclos daemon", min_value=15, max_value=600, value=get_setting('DAEMON_CYCLE_SECONDS', 60, int), step=5)
            with col_b:
                watchlist_update_seconds = st.number_input("Segundos entre refrescos radar", min_value=900, max_value=86400, value=get_setting('WATCHLIST_UPDATE_SECONDS', 14400, int), step=300)

            st.markdown("##### Dust e inventario")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                dust_watch_enabled = st.checkbox("Vigilar dust/inventario", value=get_setting('DUST_WATCH_ENABLED', True, bool))
                dust_auto_sell_enabled = st.checkbox("Auto-vender dust recuperable", value=get_setting('DUST_AUTO_SELL_ENABLED', False, bool), help="Mantener apagado hasta implementar la política completa de dust.")
                dust_alert_on_recoverable = st.checkbox("Avisar cuando dust pase a vendible", value=get_setting('DUST_ALERT_ON_RECOVERABLE', True, bool))
            with col_d2:
                dust_sell_min_usdt = st.number_input("Mínimo USDT para dust sell", min_value=0.1, max_value=10000.0, value=get_setting('DUST_SELL_MIN_USDT', 5.0, float), step=0.5)
                dust_log_compact_enabled = st.checkbox("Compactar logs repetidos de dust", value=get_setting('DUST_LOG_COMPACT_ENABLED', True, bool))

            st.markdown("##### Órdenes y reconciliación")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                order_reconcile_enabled = st.checkbox("Reconciliar órdenes reales", value=get_setting('ORDER_RECONCILE_ENABLED', True, bool))
                order_reconcile_timeout = st.number_input("Timeout reconciliación orden (s)", min_value=5, max_value=600, value=get_setting('ORDER_RECONCILE_TIMEOUT_SECONDS', 30, int), step=5)
                order_max_pending = st.number_input("Máximo tiempo orden pendiente (s)", min_value=10, max_value=3600, value=get_setting('ORDER_MAX_PENDING_SECONDS', 120, int), step=10)
            with col_o2:
                buy_fee_buffer_pct = st.number_input("Buffer fee compra (%)", min_value=0.0, max_value=5.0, value=get_setting('BUY_FEE_BUFFER_PCT', 0.5, float), step=0.1)
                orderbook_depth_levels = st.number_input("Niveles orderbook para validar", min_value=1, max_value=50, value=get_setting('ORDERBOOK_DEPTH_LEVELS', 5, int), step=1)

            st.markdown("##### Kill-switches")
            col_k1, col_k2 = st.columns(2)
            with col_k1:
                kill_switch_enabled = st.checkbox("Activar kill-switches", value=get_setting('KILL_SWITCH_ENABLED', True, bool))
                auto_pause_mismatch = st.checkbox("Pausar por discrepancia DB/exchange", value=get_setting('AUTO_PAUSE_ON_DB_EXCHANGE_MISMATCH', True, bool))
                auto_pause_heartbeat = st.checkbox("Pausar por heartbeat vencido", value=get_setting('AUTO_PAUSE_ON_STALE_HEARTBEAT', True, bool))
                max_portfolio_drawdown_pct = st.number_input("Drawdown máximo portfolio (%)", min_value=1.0, max_value=95.0, value=get_setting('MAX_PORTFOLIO_DRAWDOWN_PCT', 15.0, float), step=1.0)
            with col_k2:
                max_exchange_errors = st.number_input("Errores exchange máximos por ciclo", min_value=1, max_value=100, value=get_setting('MAX_EXCHANGE_ERRORS_PER_CYCLE', 3, int), step=1)
                max_unreconciled_orders = st.number_input("Órdenes sin reconciliar máximas", min_value=0, max_value=100, value=get_setting('MAX_UNRECONCILED_ORDERS', 0, int), step=1)
                drawdown_cooldown_hours = st.number_input("Cooldown por drawdown (h)", min_value=1, max_value=720, value=get_setting('DRAWDOWN_COOLDOWN_HOURS', 24, int), step=1)

            st.markdown("##### Macro y backtest")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                macro_altseason_btc_dom = st.number_input("BTC dominance ALTSEASON máx. (%)", min_value=35.0, max_value=60.0, value=get_setting('MACRO_ALTSEASON_BTC_DOM', 48.0, float), step=0.5)
                macro_risk_on_max_btc_dom = st.number_input("BTC dominance máx. para RISK_ON alts (%)", min_value=45.0, max_value=75.0, value=get_setting('MACRO_RISK_ON_MAX_BTC_DOM', 55.0, float), step=0.5)
                macro_caution_risk_off_btc_dom = st.number_input("BTC dominance RISK_OFF en caídas (%)", min_value=45.0, max_value=80.0, value=get_setting('MACRO_CAUTION_RISK_OFF_BTC_DOM', 55.0, float), step=0.5)
            with col_m2:
                mtf_include_15m = st.checkbox("Incluir 15m en MTF", value=get_setting('MTF_INCLUDE_15M', True, bool))
                mtf_divergence_penalty = st.slider("Penalización divergencia MTF", 0.0, 0.5, get_setting('MTF_DIVERGENCE_PENALTY', 0.15, float), step=0.01)
                backtest_hard_veto_wr = st.slider("Win rate mínimo veto backtest", 0.0, 0.8, get_setting('BACKTEST_HARD_VETO_WIN_RATE', 0.50, float), step=0.01)
                backtest_hard_veto_min_trades = st.number_input("Trades mínimos veto backtest", min_value=5, max_value=200, value=get_setting('BACKTEST_HARD_VETO_MIN_TRADES', 20, int), step=1)
                backtest_min_bucket_trades = st.number_input("Trades mínimos por bucket", min_value=3, max_value=200, value=get_setting('BACKTEST_MIN_TRADES_PER_BUCKET', 5, int), step=1)
                backtest_min_sample_trades = st.number_input("Trades muestra completa fiable", min_value=5, max_value=1000, value=get_setting('BACKTEST_MIN_SAMPLE_TRADES', 30, int), step=1)

            st.markdown("##### Presupuesto IA")
            col_i1, col_i2 = st.columns(2)
            with col_i1:
                ai_batch_decisions_enabled = st.checkbox("Batch IA de decisiones", value=get_setting('AI_BATCH_DECISIONS_ENABLED', True, bool))
                ai_rules_only_budget = st.checkbox("Pasar a rules-only si se agota presupuesto IA", value=get_setting('AI_RULES_ONLY_ON_BUDGET_EXHAUSTED', True, bool))
                ai_invalid_rules_fallback = st.checkbox("Rules-only si IA devuelve JSON inválido", value=get_setting('AI_INVALID_RESPONSE_RULES_FALLBACK', True, bool))
                ai_max_requests_cycle = st.number_input("Máx. requests IA por ciclo", min_value=0, max_value=100, value=get_setting('AI_MAX_REQUESTS_PER_CYCLE', 2, int), step=1)
            with col_i2:
                ai_max_requests_day = st.number_input("Máx. requests IA por día", min_value=0, max_value=10000, value=get_setting('AI_MAX_REQUESTS_PER_DAY', 80, int), step=5)
                ai_max_tokens_day = st.number_input("Máx. tokens estimados IA/día", min_value=0, max_value=10000000, value=get_setting('AI_MAX_EST_TOKENS_PER_DAY', 120000, int), step=5000)
                ai_max_output_tokens = st.number_input("Máx. tokens salida IA", min_value=64, max_value=4096, value=get_setting('AI_MAX_OUTPUT_TOKENS', 700, int), step=64)
                ai_provider_timeout_seconds = st.number_input("Timeout proveedor IA (s)", min_value=3, max_value=120, value=get_setting('AI_PROVIDER_TIMEOUT_SECONDS', 15, int), step=1)
                ai_max_position_size_multiplier = st.slider("Máx. multiplicador tamaño IA", 0.1, 3.0, get_setting('AI_MAX_POSITION_SIZE_MULTIPLIER', 1.5, float), step=0.1)

            st.markdown("##### Gestión avanzada de posiciones")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                advanced_edge_enabled = st.checkbox("Permitir edge avanzado", value=get_setting('ADVANCED_EDGE_ENABLED', False, bool), help="Gate global para piramidación y futuras ventajas avanzadas.")
                add_to_winner_enabled = st.checkbox("Add-to-winner", value=get_setting('ADD_TO_WINNER_ENABLED', False, bool), help="Mantener apagado hasta implementar tramos/lotes.")
                add_min_profit = st.number_input("Beneficio mínimo para add (%)", min_value=0.0, max_value=50.0, value=get_setting('ADD_MIN_PROFIT_PCT', 1.0, float), step=0.1)
                add_min_score = st.slider("Score mínimo para add", 0.0, 1.0, get_setting('ADD_MIN_SCORE', 0.62, float), step=0.01)
                add_min_confidence = st.slider("Confianza mínima para add", 0.0, 1.0, get_setting('ADD_MIN_CONFIDENCE', 0.65, float), step=0.01)
            with col_p2:
                advanced_edge_min_reliability = st.slider("Reliability mínima edge avanzado", 0.0, 1.0, get_setting('ADVANCED_EDGE_MIN_RELIABILITY', 0.65, float), step=0.01)
                advanced_edge_min_trades = st.number_input("Trades mínimos edge avanzado", min_value=1, max_value=1000, value=get_setting('ADVANCED_EDGE_MIN_TRADES', 30, int), step=1)
                add_max_per_symbol = st.number_input("Máx. adds por símbolo", min_value=0, max_value=10, value=get_setting('ADD_MAX_PER_SYMBOL', 1, int), step=1)
                add_size_multiplier = st.slider("Tamaño add vs entrada", 0.05, 2.0, get_setting('ADD_SIZE_MULTIPLIER', 0.5, float), step=0.05)
                break_even_enabled = st.checkbox("Break-even stop", value=get_setting('BREAK_EVEN_ENABLED', True, bool))
                partial_tp_enabled = st.checkbox("Take-profit parcial", value=get_setting('PARTIAL_TAKE_PROFIT_ENABLED', True, bool))
                partial_tp_pct = st.slider("Porcentaje a vender en TP parcial", 1.0, 100.0, get_setting('PARTIAL_TAKE_PROFIT_PCT', 50.0, float), step=1.0)

            st.markdown("##### Observabilidad y alertas")
            col_obs1, col_obs2 = st.columns(2)
            with col_obs1:
                alerts_enabled = st.checkbox("Alertas externas", value=get_setting('ALERTS_ENABLED', False, bool))
                alert_webhook_url = st.text_input("Webhook de alertas", value=get_setting('ALERT_WEBHOOK_URL', ''), type="password")
                alert_timeout_seconds = st.number_input("Timeout alertas (s)", min_value=1, max_value=60, value=get_setting('ALERT_TIMEOUT_SECONDS', 5, int), step=1)
            with col_obs2:
                health_export_enabled = st.checkbox("Exportar health/status", value=get_setting('HEALTH_EXPORT_ENABLED', True, bool))
                structured_logs_enabled = st.checkbox("Logs estructurados", value=get_setting('STRUCTURED_LOGS_ENABLED', True, bool))
                audit_events_enabled = st.checkbox("Audit events", value=get_setting('AUDIT_EVENTS_ENABLED', True, bool))

        # Guardar todo
        submit = st.form_submit_button(_('SAVE_SETTINGS'), type="primary", width="stretch")
        
        if submit:
            new_data = {
                "CRYPTO_API_KEY": crypto_api,
                "CRYPTO_API_SECRET": crypto_sec,
                "GROQ_API_KEY": groq_api,
                "GOOGLE_API_KEY": google_api,
                "SAMBANOVA_API_KEY": sambanova_api,
                "COINDESK_API_KEY": coindesk_api,
                "MODO_SIMULACION": modo_sim,
                "PRESUPUESTO_INICIAL": float(presupuesto),
                "TRADING_EXECUTION_MODE": execution_mode,
                "DECISION_MODE": decision_mode,
                "MIN_AUTO_DECISION_SCORE": float(min_score),
                "MANUAL_MAX_POSITIONS_PRIORITY": bool(manual_cap),
                "MAX_OPEN_POSITIONS": int(max_pos),
                "MIN_PROFIT_NET": float(min_profit),
                "STOP_LOSS_PERCENT": float(stop_loss_percent),
                "ATR_STOP_ENABLED": bool(atr_stop_enabled),
                "STOP_LOSS_ATR_MULT": float(stop_loss_atr_mult),
                "ATR_TRAILING_ENABLED": bool(atr_trailing_enabled),
                "TRAILING_ATR_MULT": float(trailing_atr_mult),
                "TRAILING_ACTIVATION_PCT": float(trailing_activation_pct),
                "BREAK_EVEN_ACTIVATION_PCT": float(break_even_activation_pct),
                "MAX_POSITION_AGE_HOURS": int(max_position_age_hours),
                "STOP_LOSS_COOLDOWN_MINUTES": int(stop_loss_cooldown_minutes),
                "TAKE_PROFIT_COOLDOWN_MINUTES": int(take_profit_cooldown_minutes),
                "RISK_PER_TRADE": riesgo / 100.0,
                "MAX_DAILY_LOSS_PCT": float(max_daily_loss),
                "MAX_PORTFOLIO_DRAWDOWN_PCT": float(max_portfolio_drawdown_pct),
                "DRAWDOWN_COOLDOWN_HOURS": int(drawdown_cooldown_hours),
                "MAX_PORTFOLIO_EXPOSURE_PCT": float(max_exposure),
                "VOLATILITY_SIZING_ENABLED": bool(vol_sizing),
                "MAX_POSITION_RISK_PCT": float(max_position_risk),
                "MAX_VOLATILITY_POSITION_MULTIPLIER": float(max_vol_mult),
                "MIN_POSITION_USDT": float(min_position_usdt),
                "MAX_SYMBOL_EXPOSURE_PCT": float(max_symbol_exposure),
                "MAX_ALT_EXPOSURE_PCT": float(max_alt_exposure),
                "MAX_BUCKET_EXPOSURE_PCT": float(max_bucket_exposure),
                "ADAPTIVE_SCORING_ENABLED": bool(adaptive_scoring),
                "ADAPTIVE_MIN_TRADES": int(adaptive_min_trades),
                "ADAPTIVE_MAX_SCORE_ADJUSTMENT": float(adaptive_max_adjustment),
                "METRICS_ROLLING_WINDOW": int(metrics_window),
                "ROTATION_ENABLED": rot_en,
                "ROTATION_MIN_PROFIT": float(rot_prof),
                "ROTATION_CONFIDENCE_GAP": float(rot_gap),
                "ROTATION_MIN_NEW_CONFIDENCE": float(rot_min_new),
                "AI_ANALYSIS_INTERVAL": int(ai_interval_min * 60),
                "AI_BATCH_DECISIONS_ENABLED": bool(ai_batch_decisions_enabled),
                "DAEMON_CYCLE_SECONDS": int(daemon_cycle_seconds),
                "WATCHLIST_UPDATE_SECONDS": int(watchlist_update_seconds),
                "DUST_WATCH_ENABLED": bool(dust_watch_enabled),
                "DUST_AUTO_SELL_ENABLED": bool(dust_auto_sell_enabled),
                "DUST_SELL_MIN_USDT": float(dust_sell_min_usdt),
                "DUST_ALERT_ON_RECOVERABLE": bool(dust_alert_on_recoverable),
                "DUST_LOG_COMPACT_ENABLED": bool(dust_log_compact_enabled),
                "ORDER_RECONCILE_ENABLED": bool(order_reconcile_enabled),
                "ORDER_RECONCILE_TIMEOUT_SECONDS": int(order_reconcile_timeout),
                "ORDER_MAX_PENDING_SECONDS": int(order_max_pending),
                "BUY_FEE_BUFFER_PCT": float(buy_fee_buffer_pct),
                "ORDERBOOK_DEPTH_LEVELS": int(orderbook_depth_levels),
                "KILL_SWITCH_ENABLED": bool(kill_switch_enabled),
                "MAX_EXCHANGE_ERRORS_PER_CYCLE": int(max_exchange_errors),
                "MAX_UNRECONCILED_ORDERS": int(max_unreconciled_orders),
                "AUTO_PAUSE_ON_DB_EXCHANGE_MISMATCH": bool(auto_pause_mismatch),
                "AUTO_PAUSE_ON_STALE_HEARTBEAT": bool(auto_pause_heartbeat),
                "MACRO_ALTSEASON_BTC_DOM": float(macro_altseason_btc_dom),
                "MACRO_RISK_ON_MAX_BTC_DOM": float(macro_risk_on_max_btc_dom),
                "MACRO_CAUTION_RISK_OFF_BTC_DOM": float(macro_caution_risk_off_btc_dom),
                "MTF_INCLUDE_15M": bool(mtf_include_15m),
                "MTF_DIVERGENCE_PENALTY": float(mtf_divergence_penalty),
                "BACKTEST_HARD_VETO_WIN_RATE": float(backtest_hard_veto_wr),
                "BACKTEST_HARD_VETO_MIN_TRADES": int(backtest_hard_veto_min_trades),
                "BACKTEST_MIN_TRADES_PER_BUCKET": int(backtest_min_bucket_trades),
                "BACKTEST_MIN_SAMPLE_TRADES": int(backtest_min_sample_trades),
                "AI_MAX_REQUESTS_PER_CYCLE": int(ai_max_requests_cycle),
                "AI_MAX_REQUESTS_PER_DAY": int(ai_max_requests_day),
                "AI_MAX_EST_TOKENS_PER_DAY": int(ai_max_tokens_day),
                "AI_RULES_ONLY_ON_BUDGET_EXHAUSTED": bool(ai_rules_only_budget),
                "AI_INVALID_RESPONSE_RULES_FALLBACK": bool(ai_invalid_rules_fallback),
                "AI_MAX_OUTPUT_TOKENS": int(ai_max_output_tokens),
                "AI_PROVIDER_TIMEOUT_SECONDS": int(ai_provider_timeout_seconds),
                "AI_MAX_POSITION_SIZE_MULTIPLIER": float(ai_max_position_size_multiplier),
                "ADVANCED_EDGE_ENABLED": bool(advanced_edge_enabled),
                "ADVANCED_EDGE_MIN_RELIABILITY": float(advanced_edge_min_reliability),
                "ADVANCED_EDGE_MIN_TRADES": int(advanced_edge_min_trades),
                "ADD_TO_WINNER_ENABLED": bool(add_to_winner_enabled),
                "ADD_MIN_PROFIT_PCT": float(add_min_profit),
                "ADD_MIN_SCORE": float(add_min_score),
                "ADD_MIN_CONFIDENCE": float(add_min_confidence),
                "ADD_MAX_PER_SYMBOL": int(add_max_per_symbol),
                "ADD_SIZE_MULTIPLIER": float(add_size_multiplier),
                "BREAK_EVEN_ENABLED": bool(break_even_enabled),
                "PARTIAL_TAKE_PROFIT_ENABLED": bool(partial_tp_enabled),
                "PARTIAL_TAKE_PROFIT_PCT": float(partial_tp_pct),
                "ALERTS_ENABLED": bool(alerts_enabled),
                "ALERT_WEBHOOK_URL": alert_webhook_url,
                "ALERT_TIMEOUT_SECONDS": int(alert_timeout_seconds),
                "HEALTH_EXPORT_ENABLED": bool(health_export_enabled),
                "STRUCTURED_LOGS_ENABLED": bool(structured_logs_enabled),
                "AUDIT_EVENTS_ENABLED": bool(audit_events_enabled),
                "PROMPT_SENTIMENT": p_sent,
                "PROMPT_DECISION": p_dec,
                "PROMPT_CURATION": p_cur
            }
            save_settings(new_data)
            st.success(_('SUCCESS_SETTINGS'))
            st.balloons()

    _render_config_import_export()
