import streamlit as st

from config import get_setting, reset_to_defaults, save_settings
from config_importer import validate_config_payload
from i18n import _
from ui_services.config_form import (
    CONNECTION_ONLY_KEYS,
    SETTINGS_TAB_ADVANCED,
    SETTINGS_TAB_OPERATION,
    SETTINGS_TAB_RISK,
    render_settings_tab_ui,
    schema_keys_count,
)
from ui_services.config_io_panel import render_config_io_panel
from ui_services.config_presets_ui import render_config_presets_panel
from ui_services.checkpoint_dialog import offer_checkpoint_after_event, render_pending_checkpoint_dialog
from ui_services.checkpoint_ui import MANUAL_FORM_OPEN_KEY, render_manual_checkpoint_form


def render_settings():
    st.title(_("SETTINGS_TITLE"))
    db = st.session_state.get("db")
    exchange = st.session_state.get("exchange")
    if db is not None and exchange is not None:
        render_pending_checkpoint_dialog(db, exchange)

    st.caption(_("CHK_HINT_SETTINGS"))
    if db is not None and exchange is not None:
        if st.button(_("HIST_CHECKPOINT_MANUAL_BTN"), key="settings_open_manual_cp"):
            st.session_state[MANUAL_FORM_OPEN_KEY] = True
        render_manual_checkpoint_form(db, exchange, key_prefix="settings_cp")

    col_reset1, col_reset2 = st.columns([4, 1])
    with col_reset2:
        if st.button(_("RESET_GLOBAL"), help=_("RESET_HELP"), type="secondary"):
            reset_to_defaults()
            if db is not None and exchange is not None:
                offer_checkpoint_after_event(
                    db,
                    exchange,
                    event_type="reset_global",
                    label=_("CHK_EVENT_RESET"),
                    default_primary="activate",
                )
            st.rerun()

    st.caption(_("CFG_SCHEMA_COUNT").format(schema_keys_count()))

    # Presets use st.button — must stay outside st.form (Streamlit limitation).
    with st.container(border=True):
        st.markdown(f"##### {_('TAB_OPERATION')} — {_('PRESETS_TITLE')}")
        st.caption(_("PRESETS_FORM_HINT"))
        render_config_presets_panel()

    with st.form("settings_form"):
        tab_op, tab_risk, tab_conn, tab_adv = st.tabs(
            [
                _("TAB_OPERATION"),
                _("TAB_RISK_LIMITS"),
                _("TAB_CONNECTIONS"),
                _("TAB_ADVANCED"),
            ]
        )

        schema_data: dict = {}
        api_data: dict = {}

        with tab_op:
            schema_data.update(
                render_settings_tab_ui(SETTINGS_TAB_OPERATION, key_prefix="cfg_op")
            )

        with tab_risk:
            schema_data.update(render_settings_tab_ui(SETTINGS_TAB_RISK, key_prefix="cfg_risk"))

        with tab_conn:
            st.subheader(_("API_CREDENTIALS"))
            st.caption(_("SETTINGS_KEYS_SECURITY"))
            for key in sorted(CONNECTION_ONLY_KEYS):
                api_data[key] = st.text_input(
                    _(f"CFG_KEY_{key}"),
                    value=get_setting(key, "", str),
                    type="password",
                    key=f"conn_{key}",
                )

        with tab_adv:
            st.warning(_("PROMPT_WARNING"))
            search = st.text_input(
                _("CFG_SEARCH_LABEL"),
                value="",
                key="cfg_adv_search",
                placeholder=_("CFG_SEARCH_PLACEHOLDER"),
            )
            schema_data.update(
                render_settings_tab_ui(
                    SETTINGS_TAB_ADVANCED,
                    key_prefix="cfg_adv",
                    search=search,
                )
            )

        submit = st.form_submit_button(_("SAVE_SETTINGS"), type="primary", use_container_width=True)

        if submit:
            payload = dict(schema_data)
            payload.update(api_data)
            changes, warnings, blocked, errors = validate_config_payload(payload)
            if errors:
                for err in errors:
                    st.error(err)
                return
            if blocked:
                st.info(_("CONFIG_BLOCKED_KEYS").format(", ".join(blocked)))
            save_settings(changes)
            for warn in warnings:
                st.caption(warn)
            changed_keys = ", ".join(sorted(changes.keys())[:12])
            if len(changes) > 12:
                changed_keys += f" … (+{len(changes) - 12})"
            st.success(_("SUCCESS_SETTINGS"))
            st.info(_("CFG_SAVED_KEYS").format(len(changes), changed_keys))
            st.balloons()

    render_config_io_panel()
