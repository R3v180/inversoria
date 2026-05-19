"""Local Ollama provider for AI fallback."""

from __future__ import annotations

import json

import requests

import config


def call_ollama(prompt: str, system_instruction: str = "", *, timeout=None) -> tuple[str | None, str]:
    if not bool(getattr(config, "OLLAMA_ENABLED", False)):
        return None, ""
    base = str(getattr(config, "OLLAMA_BASE_URL", "http://127.0.0.1:11434") or "").rstrip("/")
    model = str(getattr(config, "OLLAMA_MODEL", "llama3.2") or "llama3.2")
    timeout = timeout or int(getattr(config, "AI_PROVIDER_TIMEOUT_SECONDS", 30) or 30)
    payload = {
        "model": model,
        "prompt": f"{system_instruction}\n\n{prompt}".strip(),
        "stream": False,
    }
    try:
        resp = requests.post(f"{base}/api/generate", json=payload, timeout=timeout)
        if resp.status_code >= 400:
            return None, ""
        data = resp.json()
        text = str(data.get("response") or "").strip()
        return (text or None), "Ollama"
    except Exception:
        return None, ""
