"""Minimal HTTP server for TradingView webhooks (stdlib only)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from database_manager import DatabaseManager
from bot_runtime.webhook_processor import parse_tradingview_payload
import config


class TradingViewWebhookHandler(BaseHTTPRequestHandler):
    db = None

    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"invalid_json"}')
            return

        secret = str(getattr(config, "WEBHOOK_TRADINGVIEW_SECRET", "") or "")
        ok, symbol, action, err = parse_tradingview_payload(body, secret)
        if not ok:
            self.send_response(403 if err == "INVALID_SECRET" else 400)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": err}).encode("utf-8"))
            return

        db = self.db or DatabaseManager()
        signal_id = db.enqueue_external_signal(
            source="tradingview",
            symbol=symbol,
            action=action,
            raw_payload=body,
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "id": signal_id, "symbol": symbol, "action": action}).encode("utf-8"))


def start_webhook_server(db=None, daemon=True):
    if not bool(getattr(config, "WEBHOOK_TRADINGVIEW_ENABLED", False)):
        return None
    port = int(getattr(config, "WEBHOOK_SERVER_PORT", 8765) or 8765)
    TradingViewWebhookHandler.db = db or DatabaseManager()
    server = HTTPServer(("0.0.0.0", port), TradingViewWebhookHandler)
    thread = threading.Thread(target=server.serve_forever, name="tv-webhook", daemon=daemon)
    thread.start()
    return server


if __name__ == "__main__":
    start_webhook_server(daemon=False)
