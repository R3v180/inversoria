"""Process external webhook signals into daemon buy candidates."""

from __future__ import annotations

import json


def normalize_tv_symbol(ticker: str) -> str:
    raw = str(ticker or "").upper().replace(" ", "")
    if "/" in raw:
        return raw
    if raw.endswith("USDT"):
        base = raw[:-4]
        return f"{base}/USDT"
    return f"{raw}/USDT"


def parse_tradingview_payload(body: dict, secret_expected: str) -> tuple[bool, str, str, str]:
    if secret_expected:
        token = str(body.get("passphrase") or body.get("secret") or "")
        if token != secret_expected:
            return False, "", "", "INVALID_SECRET"
    action = str(body.get("action") or body.get("side") or "HOLD").upper()
    symbol = normalize_tv_symbol(body.get("ticker") or body.get("symbol") or "")
    if not symbol or action not in {"BUY", "SELL", "HOLD"}:
        return False, "", "", "INVALID_PAYLOAD"
    return True, symbol, action, ""


def process_pending_signals(db, config, log_fn=None) -> list[dict]:
    if not bool(getattr(config, "WEBHOOK_TRADINGVIEW_ENABLED", False)):
        return []
    approved_out = []
    auto = bool(getattr(config, "WEBHOOK_AUTO_APPROVE", False))

    pending = db.list_external_signals(status="pending", limit=20)
    for row in pending:
        sid = row.get("id")
        action = str(row.get("action") or "HOLD").upper()
        symbol = str(row.get("symbol") or "")
        if action == "HOLD":
            db.update_external_signal(sid, "ignored", "HOLD")
            continue
        if not auto:
            continue
        db.update_external_signal(sid, "approved", "auto_approve")
        approved_out.append({"symbol": symbol, "action": action, "signal_id": sid})
        if log_fn:
            log_fn(f"[WEBHOOK] auto-approved {action} {symbol} id={sid}")

    for row in db.list_external_signals(status="approved", limit=20):
        sid = row.get("id")
        action = str(row.get("action") or "HOLD").upper()
        symbol = str(row.get("symbol") or "")
        if action in {"BUY", "SELL"} and symbol:
            approved_out.append({"symbol": symbol, "action": action, "signal_id": sid})
            db.update_external_signal(sid, "consumed", "daemon_cycle")
    return approved_out
