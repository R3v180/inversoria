"""Streamlit UI for configuration presets (cards, assistant, manage)."""

from __future__ import annotations

import streamlit as st

import config
from config_presets import (
    apply_preset,
    delete_user_preset,
    duplicate_preset,
    get_active_preset_id,
    import_user_preset,
    list_presets,
    preset_export_json,
    preview_preset_apply,
    save_current_as_preset,
)
from i18n import _
from ui_services.config_preset_assistant import BUILTIN_PRESET_IDS, suggest_preset_id

_BUILTIN_I18N: dict[str, tuple[str, str]] = {
    "recommended": ("PRESETS_BUILTIN_RECOMMENDED_NAME", "PRESETS_BUILTIN_RECOMMENDED_DESC"),
    "conservative": ("PRESETS_BUILTIN_CONSERVATIVE_NAME", "PRESETS_BUILTIN_CONSERVATIVE_DESC"),
    "aggressive": ("PRESETS_BUILTIN_AGGRESSIVE_NAME", "PRESETS_BUILTIN_AGGRESSIVE_DESC"),
}

_PENDING_KEY = "pending_preset_apply"


def _preset_label(preset: dict) -> str:
    pid = preset.get("id", "")
    if pid in _BUILTIN_I18N:
        name_key, _desc_key = _BUILTIN_I18N[pid]
        name = _(name_key)
        if name == name_key:
            name = preset.get("name", pid)
        return f"{name}{_('PRESETS_BUILTIN_SUFFIX')}"
    return str(preset.get("name", pid))


def _preset_description(preset: dict) -> str:
    pid = preset.get("id", "")
    if pid in _BUILTIN_I18N:
        _name_key, desc_key = _BUILTIN_I18N[pid]
        text = _(desc_key)
        if text != desc_key:
            return text
    return str(preset.get("description") or "")


def _render_preset_pending(preset_id: str):
    pending = st.session_state.get(_PENDING_KEY)
    if not pending or pending.get("preset_id") != preset_id:
        return
    preview = pending.get("preview") or {}
    rows = preview.get("diff") or []
    with st.container(border=True):
        st.warning(_("PRESETS_PENDING_APPLY"))
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info(_("CONFIG_NO_EFFECTIVE_DIFF"))
        for w in preview.get("warnings") or []:
            text = _("PRESET_LOCKED_KEYS_SKIPPED") if w == "PRESET_LOCKED_KEYS_SKIPPED" else w
            st.caption(f"- {text}")
        real_mode = not bool(getattr(config, "MODO_SIMULACION", True))
        confirm_real = False
        if real_mode:
            confirm_real = st.checkbox(_("PRESETS_CONFIRM_REAL"), key=f"preset_confirm_real_{preset_id}")
        c1, c2 = st.columns(2)
        if c1.button(_("PRESETS_APPLY"), type="primary", key=f"preset_apply_{preset_id}"):
            try:
                if real_mode and not confirm_real:
                    st.error(_("PRESETS_REAL_REQUIRED"))
                else:
                    result = apply_preset(preset_id, confirm_real=confirm_real or not real_mode)
                    st.session_state.pop(_PENDING_KEY, None)
                    msg = _("CONFIG_APPLIED")
                    if result.get("backup"):
                        msg = _("CONFIG_APPLIED_BACKUP").format(result["backup"])
                    st.success(msg)
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if c2.button(_("PRESETS_DISCARD"), key=f"preset_discard_{preset_id}"):
            st.session_state.pop(_PENDING_KEY, None)
            st.rerun()


def _start_preset_preview(preset_id: str):
    try:
        preview = preview_preset_apply(preset_id)
        st.session_state[_PENDING_KEY] = {"preset_id": preset_id, "preview": preview}
    except Exception as exc:
        st.error(_("PRESETS_ERROR_GENERIC").format(exc))


def render_preset_assistant():
    """Phase D: short questionnaire → suggested built-in preset."""
    with st.expander(_("PRESETS_ASSISTANT_TITLE"), expanded=False):
        st.caption(_("PRESETS_ASSISTANT_CAPTION"))
        real_mode = st.radio(
            _("PRESETS_ASSISTANT_REAL"),
            options=[False, True],
            format_func=lambda v: _("PRESETS_ASSISTANT_SIM") if not v else _("PRESETS_ASSISTANT_REAL_YES"),
            horizontal=True,
            key="preset_assistant_real",
        )
        account_size = st.radio(
            _("PRESETS_ASSISTANT_ACCOUNT"),
            options=["small", "medium", "large"],
            format_func=lambda v: {
                "small": _("PRESETS_ASSISTANT_ACCOUNT_SMALL"),
                "medium": _("PRESETS_ASSISTANT_ACCOUNT_MEDIUM"),
                "large": _("PRESETS_ASSISTANT_ACCOUNT_LARGE"),
            }[v],
            horizontal=True,
            key="preset_assistant_account",
        )
        risk = st.radio(
            _("PRESETS_ASSISTANT_RISK"),
            options=["low", "medium", "high"],
            format_func=lambda v: {
                "low": _("PRESETS_ASSISTANT_RISK_LOW"),
                "medium": _("PRESETS_ASSISTANT_RISK_MED"),
                "high": _("PRESETS_ASSISTANT_RISK_HIGH"),
            }[v],
            horizontal=True,
            key="preset_assistant_risk",
        )
        activity = st.radio(
            _("PRESETS_ASSISTANT_ACTIVITY"),
            options=["low", "medium", "high"],
            format_func=lambda v: {
                "low": _("PRESETS_ASSISTANT_ACTIVITY_LOW"),
                "medium": _("PRESETS_ASSISTANT_ACTIVITY_MED"),
                "high": _("PRESETS_ASSISTANT_ACTIVITY_HIGH"),
            }[v],
            horizontal=True,
            key="preset_assistant_activity",
        )
        suggested = suggest_preset_id(
            real_mode=bool(real_mode),
            risk_tolerance=risk,
            activity_level=activity,
            account_size=account_size,
        )
        name_key, desc_key = _BUILTIN_I18N[suggested]
        st.info(_("PRESETS_ASSISTANT_RESULT").format(_(name_key), _(desc_key)))
        if st.button(_("PRESETS_ASSISTANT_PREVIEW"), type="primary", key="preset_assistant_preview"):
            _start_preset_preview(suggested)
            st.rerun()


def _render_preset_card(preset: dict, *, active_id: str | None):
    pid = preset["id"]
    is_active = pid == active_id
    border = "border" if is_active else None
    with st.container(border=border):
        title = _preset_label(preset)
        if is_active:
            title = f"✓ {title}"
        st.markdown(f"**{title}**")
        desc = _preset_description(preset)
        if desc:
            st.caption(desc)
        if st.button(_("PRESETS_PREVIEW"), key=f"preset_card_preview_{pid}", use_container_width=True):
            _start_preset_preview(pid)
            st.rerun()
    _render_preset_pending(pid)


def render_preset_cards():
    """Built-in presets as cards + optional user presets row."""
    presets = list_presets()
    if not presets:
        st.info(_("PRESETS_EMPTY"))
        return

    active = get_active_preset_id()
    builtins = [p for p in presets if p.get("id") in BUILTIN_PRESET_IDS]
    builtins.sort(key=lambda p: BUILTIN_PRESET_IDS.index(p["id"]) if p["id"] in BUILTIN_PRESET_IDS else 99)
    user = [p for p in presets if p.get("id") not in BUILTIN_PRESET_IDS]

    cols = st.columns(min(3, max(1, len(builtins))))
    for idx, preset in enumerate(builtins):
        with cols[idx % len(cols)]:
            _render_preset_card(preset, active_id=active)

    if user:
        st.markdown("##### " + _("PRESETS_USER_SECTION"))
        for preset in user:
            _render_preset_card(preset, active_id=active)


def render_preset_manage_expander():
    """Save, duplicate, export, delete, import — collapsed by default."""
    presets = list_presets()
    if not presets:
        return

    labels = {p["id"]: _preset_label(p) for p in presets}
    ids = list(labels.keys())
    active = get_active_preset_id()
    default_idx = ids.index(active) if active in ids else 0

    with st.expander(_("PRESETS_MANAGE_EXPANDER"), expanded=False):
        selected_id = st.selectbox(
            _("PRESETS_SELECT"),
            ids,
            index=default_idx,
            format_func=lambda pid: labels.get(pid, pid),
            key="config_preset_manage_select",
        )
        selected = next(p for p in presets if p["id"] == selected_id)

        c1, c2, c3 = st.columns(3)
        with c1:
            new_name = st.text_input(_("PRESETS_SAVE_NAME"), key="preset_save_name")
            new_desc = st.text_input(_("PRESETS_SAVE_DESC"), key="preset_save_desc")
            if st.button(_("PRESETS_SAVE_CURRENT"), key="preset_save_btn"):
                if not new_name.strip():
                    st.error(_("PRESETS_NAME_REQUIRED"))
                else:
                    try:
                        save_current_as_preset(new_name.strip(), new_desc.strip())
                        st.success(_("PRESETS_SAVED"))
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        with c2:
            dup_name = st.text_input(
                _("PRESETS_DUP_NAME"),
                value=f"{selected.get('name', '')}{_('PRESETS_COPY_SUFFIX')}",
                key="preset_dup_name",
            )
            if st.button(_("PRESETS_DUPLICATE"), key="preset_dup_btn"):
                try:
                    duplicate_preset(selected_id, dup_name.strip())
                    st.success(_("PRESETS_DUPLICATED"))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with c3:
            st.download_button(
                _("PRESETS_EXPORT"),
                data=preset_export_json(selected_id),
                file_name=f"inversoria_preset_{selected_id}.json",
                mime="application/json",
                use_container_width=True,
                key="preset_export_btn",
            )

        if not selected.get("builtin"):
            if st.button(_("PRESETS_DELETE"), type="secondary", key="preset_delete_btn"):
                if delete_user_preset(selected_id):
                    st.success(_("PRESETS_DELETED"))
                    st.rerun()

        st.markdown("##### " + _("PRESETS_IMPORT"))
        raw = st.text_area(_("PRESETS_IMPORT_LABEL"), height=100, key="preset_import_raw")
        if st.button(_("PRESETS_IMPORT_BTN"), key="preset_import_btn"):
            try:
                import_user_preset(raw)
                st.success(_("PRESETS_IMPORTED"))
                st.rerun()
            except Exception as exc:
                st.error(_("PRESETS_ERROR_GENERIC").format(exc))


def render_config_presets_panel():
    """Presets block (cards + assistant + manage). Call outside st.form."""
    st.caption(_("PRESETS_LOCKED_KEYS_HINT"))
    render_preset_assistant()
    render_preset_cards()
    render_preset_manage_expander()
