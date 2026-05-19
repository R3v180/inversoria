"""Post-event checkpoint offer dialog (Streamlit, outside st.form)."""

from __future__ import annotations

import streamlit as st

from i18n import _
from ui_services import checkpoint_service as cs

PENDING_KEY = "pending_checkpoint_dialog"


def queue_checkpoint_dialog(
    checkpoint: dict,
    *,
    default_primary: str = "activate",
    allow_cancel: bool = False,
    on_cancel_key: str | None = None,
):
    """Queue dialog for next rerun. default_primary: activate | save_only."""
    st.session_state[PENDING_KEY] = {
        "checkpoint_id": checkpoint.get("id"),
        "label": checkpoint.get("label"),
        "equity_usdt": float(checkpoint.get("equity_usdt") or 0.0),
        "default_primary": default_primary,
        "allow_cancel": allow_cancel,
        "on_cancel_key": on_cancel_key,
    }


def render_pending_checkpoint_dialog(db, exchange) -> bool:
    """
    Render dialog if pending. Returns True if something was shown.
  """
    pending = st.session_state.get(PENDING_KEY)
    if not pending:
        return False

    label = pending.get("label") or _("CHK_DEFAULT_LABEL")
    equity = float(pending.get("equity_usdt") or 0.0)
    cid = pending.get("checkpoint_id")
    default_primary = pending.get("default_primary") or "activate"
    allow_cancel = bool(pending.get("allow_cancel"))

    with st.container(border=True):
        st.markdown(f"#### {_('CHK_DIALOG_TITLE')}")
        st.caption(
            _("CHK_DIALOG_BODY").format(label=label, equity=f"{equity:.2f}")
        )
        c1, c2, c3 = st.columns(3)
        activate_type = "primary" if default_primary == "activate" else "secondary"
        save_type = "primary" if default_primary == "save_only" else "secondary"

        if c1.button(
            _("CHK_DIALOG_USE_NOW"),
            type=activate_type,
            key="chk_dialog_activate",
            use_container_width=True,
        ):
            if cid:
                cs.set_active_view(db, exchange, cid)
            st.session_state.pop(PENDING_KEY, None)
            st.success(_("CHK_DIALOG_ACTIVATED"))
            st.rerun()

        if c2.button(
            _("CHK_DIALOG_SAVE_ONLY"),
            type=save_type,
            key="chk_dialog_save",
            use_container_width=True,
        ):
            st.session_state.pop(PENDING_KEY, None)
            st.info(_("CHK_DIALOG_SAVED_ONLY"))
            st.rerun()

        if allow_cancel and c3.button(
            _("CHK_DIALOG_CANCEL"),
            key="chk_dialog_cancel",
            use_container_width=True,
        ):
            cancel_key = pending.get("on_cancel_key")
            st.session_state.pop(PENDING_KEY, None)
            if cancel_key:
                handler = st.session_state.get(cancel_key)
                if callable(handler):
                    handler()
            st.rerun()

    return True


def offer_checkpoint_after_event(
    db,
    exchange,
    *,
    event_type: str,
    label: str,
    preset_id: str | None = None,
    config_diff=None,
    default_primary: str = "activate",
    allow_cancel: bool = False,
    on_cancel_key: str | None = None,
) -> dict:
    checkpoint = cs.create_checkpoint(
        db,
        exchange,
        event_type=event_type,
        label=label,
        preset_id=preset_id,
        config_diff=config_diff,
    )
    queue_checkpoint_dialog(
        checkpoint,
        default_primary=default_primary,
        allow_cancel=allow_cancel,
        on_cancel_key=on_cancel_key,
    )
    return checkpoint
