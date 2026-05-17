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
from i18n import _


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
        tab1, tab2, tab3 = st.tabs([_('TAB_CONNECTIONS'), _('TAB_RISK'), _('TAB_AI')])
        
        with tab1:
            st.subheader(_('API_CREDENTIALS'))
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
                riesgo = st.slider(_('RISK_PER_TRADE_L'), 1, 100, int(get_setting('RISK_PER_TRADE', 0.1, float)*100))
                max_exposure = st.slider(_('MAX_EXPOSURE_L'), 1.0, 100.0, get_setting('MAX_PORTFOLIO_EXPOSURE_PCT', 85.0, float), step=1.0)
                min_profit = st.number_input(
                    _('MIN_PROFIT_L'),
                    min_value=0.1,
                    max_value=10.0,
                    value=get_setting('MIN_PROFIT_NET', 1.0, float),
                    step=0.1,
                    help="El bot solo considerará rentable una operación si supera este % de beneficio"
                )
            
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
            
            p_sent = st.text_area("Prompt Análisis Sentiment", value=get_setting('PROMPT_SENTIMENT', DEFAULT_SETTINGS['PROMPT_SENTIMENT']), height=100)
            p_dec = st.text_area("Prompt Motor de Decisión (JSON)", value=get_setting('PROMPT_DECISION', DEFAULT_SETTINGS['PROMPT_DECISION']), height=100)
            p_cur = st.text_area("Prompt Radar (Curación)", value=get_setting('PROMPT_CURATION', DEFAULT_SETTINGS['PROMPT_CURATION']), height=100)

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
                "RISK_PER_TRADE": riesgo / 100.0,
                "MAX_DAILY_LOSS_PCT": float(max_daily_loss),
                "MAX_PORTFOLIO_EXPOSURE_PCT": float(max_exposure),
                "ROTATION_ENABLED": rot_en,
                "ROTATION_MIN_PROFIT": float(rot_prof),
                "ROTATION_CONFIDENCE_GAP": float(rot_gap),
                "ROTATION_MIN_NEW_CONFIDENCE": float(rot_min_new),
                "AI_ANALYSIS_INTERVAL": int(ai_interval_min * 60),
                "PROMPT_SENTIMENT": p_sent,
                "PROMPT_DECISION": p_dec,
                "PROMPT_CURATION": p_cur
            }
            save_settings(new_data)
            st.success(_('SUCCESS_SETTINGS'))
            st.balloons()

    _render_config_import_export()
