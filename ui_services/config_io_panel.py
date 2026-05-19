"""Import/export and diagnostic tools (Advanced settings tab)."""

from __future__ import annotations

import streamlit as st

from config_importer import (
    ConfigValidationError,
    apply_config_changes,
    config_example_json,
    current_safe_config_json,
    diff_config_changes,
    format_validation_error,
    parse_config_payload,
    partial_config_example_json,
    validate_config_payload,
)
from diagnostic_utils import build_safe_diagnostic_package
from i18n import _, format_config_error


def _render_diagnostic_expander():
    with st.expander(_("SETTINGS_DIAG_EXPANDER"), expanded=False):
        st.caption(_("DIAG_AI_HELP"))
        db = st.session_state.get("db")
        exchange = st.session_state.get("exchange")
        if st.button(_("DIAG_AI_GENERATE"), type="secondary", key="settings_diag_generate"):
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
            height=280,
            help=_("DIAG_AI_TEXT_HELP"),
            key="settings_diag_text",
        )
        st.download_button(
            _("DIAG_AI_DOWNLOAD"),
            data=package,
            file_name="inversoria_diagnostico_ia.txt",
            mime="text/plain",
            use_container_width=True,
            key="settings_diag_download",
        )


def render_config_io_panel():
    """Unified JSON tools: apply patch/full or download backups."""
    with st.expander(_("SETTINGS_IO_EXPANDER"), expanded=False):
        st.caption(_("CONFIG_IO_HELP"))

        intent = st.radio(
            _("SETTINGS_IO_INTENT"),
            options=["apply", "download"],
            format_func=lambda x: _("SETTINGS_IO_INTENT_APPLY")
            if x == "apply"
            else _("SETTINGS_IO_INTENT_DOWNLOAD"),
            horizontal=True,
            key="settings_io_intent",
        )

        if intent == "download":
            dl_kind = st.radio(
                _("SETTINGS_IO_DOWNLOAD_KIND"),
                options=["current", "partial", "full"],
                format_func=lambda k: {
                    "current": _("CONFIG_DOWNLOAD_CURRENT"),
                    "partial": _("CONFIG_DOWNLOAD_PARTIAL"),
                    "full": _("CONFIG_DOWNLOAD_EXAMPLE"),
                }[k],
                key="settings_io_dl_kind",
            )
            data = {
                "current": current_safe_config_json(),
                "partial": partial_config_example_json(),
                "full": config_example_json(),
            }[dl_kind]
            fname = {
                "current": "inversoria_config_actual_safe.json",
                "partial": "inversoria_config_patch.json",
                "full": "inversoria_config_example.json",
            }[dl_kind]
            st.download_button(
                _("SETTINGS_IO_DOWNLOAD_BTN"),
                data=data,
                file_name=fname,
                mime="application/json",
                type="primary",
                use_container_width=True,
            )
            _render_diagnostic_expander()
            return

        mode = st.radio(
            _("CONFIG_IMPORT_MODE"),
            options=["patch", "full"],
            format_func=lambda m: _("CONFIG_IMPORT_MODE_PATCH") if m == "patch" else _("CONFIG_IMPORT_MODE_FULL"),
            horizontal=True,
            key="settings_config_import_mode",
        )
        placeholder = partial_config_example_json() if mode == "patch" else config_example_json()
        raw_config = st.text_area(
            _("CONFIG_IMPORT_LABEL"),
            height=200,
            placeholder=placeholder,
            help=_("CONFIG_IMPORT_HELP_PATCH") if mode == "patch" else _("CONFIG_IMPORT_HELP"),
            key="settings_config_import_raw",
        )

        if st.button(_("CONFIG_VALIDATE"), type="secondary", key="settings_config_validate"):
            try:
                payload = parse_config_payload(raw_config)
                changes, warnings, blocked, errors = validate_config_payload(payload)
            except ConfigValidationError as exc:
                st.error(format_config_error(exc.code, key=exc.key, **exc.kwargs))
                return
            except Exception as exc:
                st.error(f"{_('CONFIG_IMPORT_ERROR')}: {format_validation_error(exc)}")
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
        if pending:
            changes = pending.get("changes", {})
            warnings = pending.get("warnings", [])
            blocked = pending.get("blocked", [])
            rows = diff_config_changes(changes)

            with st.container(border=True):
                st.warning(_("CONFIG_PENDING_WARNING"))
                st.caption(_("CONFIG_PATCH_APPLY_HINT").format(len(changes)))
                if rows:
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.info(_("CONFIG_NO_EFFECTIVE_DIFF"))
                if warnings:
                    with st.expander(_("CONFIG_WARNINGS")):
                        for warning in warnings:
                            st.caption(f"- {warning}")
                if blocked:
                    st.info(_("CONFIG_BLOCKED_KEYS").format(", ".join(blocked)))

                a1, a2 = st.columns(2)
                if a1.button(_("CONFIG_APPLY"), type="primary", use_container_width=True):
                    backup = apply_config_changes(changes)
                    st.session_state.pop("pending_config_import", None)
                    if backup:
                        st.success(_("CONFIG_APPLIED_BACKUP").format(backup))
                    else:
                        st.success(_("CONFIG_APPLIED"))
                    st.rerun()
                if a2.button(_("CONFIG_DISCARD"), use_container_width=True):
                    st.session_state.pop("pending_config_import", None)
                    st.rerun()

        _render_diagnostic_expander()
