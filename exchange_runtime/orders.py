from __future__ import annotations


def build_client_order_params(config_module, client_order_id=None) -> dict:
    if not (bool(getattr(config_module, "ORDER_CLIENT_ID_ENABLED", False)) and client_order_id):
        return {}
    param_name = str(getattr(config_module, "ORDER_CLIENT_ID_PARAM", "client_oid") or "client_oid")
    return {param_name: str(client_order_id)}


def attach_client_order_id(order: dict | None, client_order_id=None) -> dict:
    out = dict(order or {})
    if client_order_id:
        out.setdefault("clientOrderId", str(client_order_id))
    return out

