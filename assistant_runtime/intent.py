"""Detect user intent for assistant context expansion."""

from __future__ import annotations

import re

SECTION_ALIASES = {
    "logs": "ÚLTIMOS LOGS",
    "log": "ÚLTIMOS LOGS",
    "daemon": "DAEMON",
    "noticias": "NOTICIAS RELEVANTES",
    "news": "NOTICIAS RELEVANTES",
    "config": "MODO / CONFIG",
    "configuracion": "MODO / CONFIG",
    "configuration": "MODO / CONFIG",
    "cartera": "CARTERA / POSICIONES BOT",
    "wallet": "CARTERA EXCHANGE / DUST",
    "exchange": "CARTERA EXCHANGE / DUST",
    "journal": "DECISION JOURNAL / MÉTRICAS",
    "decisiones": "DECISIONES RECIENTES",
    "backtest": "BACKTEST",
    "audit": "AUDIT / REPLAY",
    "replay": "AUDIT / REPLAY",
    "webhook": "WEBHOOKS / SEÑALES",
    "senal": "WEBHOOKS / SEÑALES",
    "señal": "WEBHOOKS / SEÑALES",
    "ordenes": "ÓRDENES PENDIENTES",
    "órdenes": "ÓRDENES PENDIENTES",
    "macro": "MACRO",
    "preset": "PLANTILLA ACTIVA",
    "plantilla": "PLANTILLA ACTIVA",
}


def detect_intent_sections(user_message: str) -> set[str]:
    text = str(user_message or "").lower()
    found = set()
    for token, section in SECTION_ALIASES.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            found.add(section)
    if any(w in text for w in ("error", "fallo", "failed", "traceback", "bug")):
        found.add("ÚLTIMOS LOGS")
        found.add("DAEMON")
    if any(w in text for w in ("diagnostico", "diagnóstico", "estado", "health")):
        found.add("PRIORIDAD / ESTADO CRÍTICO")
        found.add("DAEMON")
    return found


def parse_fetch_context_block(text: str) -> set[str]:
    match = re.search(
        r"\[FETCH_CONTEXT\](.*?)\[/FETCH_CONTEXT\]",
        text or "",
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return set()
    body = match.group(1)
    sections = set()
    for part in re.split(r"[,;\s]+", body):
        part = part.strip().lower()
        if not part or "=" in part:
            if "sections=" in body.lower():
                raw = re.search(r"sections=([^\]]+)", body, re.I)
                if raw:
                    for s in raw.group(1).split(","):
                        s = s.strip().lower()
                        sections.add(SECTION_ALIASES.get(s, s))
            continue
        sections.add(SECTION_ALIASES.get(part, part))
    return sections
