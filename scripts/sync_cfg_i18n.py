#!/usr/bin/env python3
"""Generate i18n_config_labels.py from CONFIG_SCHEMA + YAML overrides."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import yaml
except ImportError:
    yaml = None

from config import SENSITIVE_SETTING_KEYS
from config_importer import CONFIG_SCHEMA

OUT_PATH = ROOT / "i18n_config_labels.py"
OVERRIDES_PATH = ROOT / "i18n" / "config_overrides.yaml"

ACRONYMS = {
    "AI", "ATR", "MTF", "BTC", "USDT", "JSON", "API", "DB", "OOS", "TP", "SL",
    "DCA", "GH", "TV", "URL", "ID", "PF", "DD", "MACRO", "MTF", "OLLAMA",
}

WORD_ES = {
    "enabled": "activado",
    "disabled": "desactivado",
    "max": "máximo",
    "min": "mínimo",
    "risk": "riesgo",
    "trade": "operación",
    "trades": "operaciones",
    "profit": "beneficio",
    "loss": "pérdida",
    "stop": "stop",
    "trailing": "trailing",
    "position": "posición",
    "positions": "posiciones",
    "portfolio": "cartera",
    "exposure": "exposición",
    "drawdown": "drawdown",
    "cooldown": "enfriamiento",
    "hours": "horas",
    "minutes": "minutos",
    "seconds": "segundos",
    "interval": "intervalo",
    "analysis": "análisis",
    "decision": "decisión",
    "decisions": "decisiones",
    "score": "puntuación",
    "confidence": "confianza",
    "rotation": "rotación",
    "macro": "macro",
    "backtest": "backtest",
    "bootstrap": "bootstrap",
    "sample": "muestra",
    "bucket": "bucket",
    "buckets": "buckets",
    "symbol": "símbolo",
    "symbols": "símbolos",
    "fee": "comisión",
    "fees": "comisiones",
    "slippage": "slippage",
    "limit": "límite",
    "order": "orden",
    "orders": "órdenes",
    "reconcile": "reconciliación",
    "pending": "pendiente",
    "alert": "alerta",
    "alerts": "alertas",
    "webhook": "webhook",
    "server": "servidor",
    "port": "puerto",
    "secret": "secreto",
    "auto": "auto",
    "approve": "aprobar",
    "protection": "protección",
    "protections": "protecciones",
    "guard": "guardia",
    "lookback": "ventana",
    "liquidity": "liquidez",
    "filter": "filtro",
    "spread": "spread",
    "volume": "volumen",
    "scaled": "escalonado",
    "take": "toma",
    "age": "edad",
    "decay": "decaimiento",
    "funding": "funding",
    "veto": "veto",
    "dynamic": "dinámico",
    "monitor": "monitor",
    "inventory": "inventario",
    "skew": "sesgo",
    "target": "objetivo",
    "boost": "impulso",
    "reduce": "reducción",
    "rule": "regla",
    "significance": "significancia",
    "adjustment": "ajuste",
    "adjust": "ajuste",
    "win": "ganancia",
    "rate": "tasa",
    "hyperopt": "hyperopt",
    "lite": "lite",
    "grid": "grid",
    "levels": "niveles",
    "spacing": "espaciado",
    "tranches": "tramos",
    "multiplier": "multiplicador",
    "aggressive": "agresivo",
    "profile": "perfil",
    "simulation": "simulación",
    "budget": "presupuesto",
    "initial": "inicial",
    "manual": "manual",
    "open": "abiertas",
    "net": "neto",
    "percent": "porcentaje",
    "activation": "activación",
    "break": "break",
    "even": "even",
    "partial": "parcial",
    "winner": "ganador",
    "advanced": "avanzado",
    "edge": "edge",
    "reliability": "fiabilidad",
    "add": "añadir",
    "size": "tamaño",
    "health": "salud",
    "export": "exportar",
    "structured": "estructurados",
    "logs": "logs",
    "audit": "auditoría",
    "events": "eventos",
    "mismatch": "discrepancia",
    "tolerance": "tolerancia",
    "pause": "pausa",
    "heartbeat": "latido",
    "stale": "obsoleto",
    "exchange": "exchange",
    "errors": "errores",
    "cycle": "ciclo",
    "daemon": "daemon",
    "watchlist": "lista de seguimiento",
    "update": "actualización",
    "dust": "dust",
    "sell": "venta",
    "watch": "vigilar",
    "recoverable": "recuperable",
    "compact": "compacto",
    "client": "cliente",
    "param": "parámetro",
    "buffer": "buffer",
    "orderbook": "libro de órdenes",
    "depth": "profundidad",
    "kill": "kill",
    "switch": "switch",
    "unreconciled": "sin reconciliar",
    "requests": "peticiones",
    "tokens": "tokens",
    "output": "salida",
    "provider": "proveedor",
    "timeout": "timeout",
    "rules": "reglas",
    "only": "solo",
    "budget": "presupuesto",
    "exhausted": "agotado",
    "invalid": "inválida",
    "response": "respuesta",
    "fallback": "respaldo",
    "batch": "lote",
    "dom": "dominancia",
    "regime": "régimen",
    "hysteresis": "histéresis",
    "window": "ventana",
    "caution": "precaución",
    "altseason": "altseason",
    "alts": "alts",
    "off": "off",
    "on": "on",
    "change": "cambio",
    "cap": "cap",
    "entry": "entrada",
    "allow": "permitir",
    "counter": "contrario",
    "trend": "tendencia",
    "divergence": "divergencia",
    "penalty": "penalización",
    "hard": "duro",
    "fraction": "fracción",
    "account": "cuenta",
    "small": "pequeña",
    "force": "forzar",
    "distance": "distancia",
    "expectancy": "expectativa",
    "low": "bajo",
    "quote": "quote",
    "pullback": "retroceso",
    "buy": "compra",
    "long": "long",
    "levels": "niveles",
    "enabled": "habilitado",
    "sells": "ventas",
    "model": "modelo",
    "base": "base",
    "url": "URL",
}


def _load_overrides() -> dict:
    if not OVERRIDES_PATH.exists() or yaml is None:
        return {"labels": {}, "helps": {}, "choices": {}}
    data = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8")) or {}
    return {
        "labels": data.get("labels") or {},
        "helps": data.get("helps") or {},
        "choices": data.get("choices") or {},
    }


def _title_en(parts: list[str]) -> str:
    out = []
    for p in parts:
        up = p.upper()
        if up in ACRONYMS:
            out.append(up)
        elif p in {"pct", "usdt"}:
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def _title_es(parts: list[str]) -> str:
    out = []
    for p in parts:
        up = p.upper()
        if up in ACRONYMS:
            out.append(up)
        elif p in WORD_ES:
            out.append(WORD_ES[p])
        else:
            out.append(p)
    text = " ".join(out)
    if text:
        return text[0].upper() + text[1:]
    return text


def _auto_label(key: str) -> dict[str, str]:
    parts = [p for p in key.lower().split("_") if p]
    return {"es": _title_es(parts), "en": _title_en(parts)}


def _auto_help(key: str, lang: str) -> str:
    label = _auto_label(key)[lang]
    if lang == "es":
        return f"Parámetro: {label}."
    return f"Setting: {label}."


def _build_entries() -> dict[str, dict[str, str]]:
    overrides = _load_overrides()
    entries: dict[str, dict[str, str]] = {}

    for key in sorted(CONFIG_SCHEMA):
        if key in SENSITIVE_SETTING_KEYS:
            label_ov = overrides["labels"].get(key, {})
            entries[f"CFG_KEY_{key}"] = {
                "es": label_ov.get("es") or _auto_label(key)["es"],
                "en": label_ov.get("en") or _auto_label(key)["en"],
            }
            help_ov = overrides["helps"].get(key, {})
            if help_ov:
                entries[f"CFG_HELP_{key}"] = {
                    "es": help_ov.get("es", _auto_help(key, "es")),
                    "en": help_ov.get("en", _auto_help(key, "en")),
                }
            continue

        label_ov = overrides["labels"].get(key, {})
        auto = _auto_label(key)
        entries[f"CFG_KEY_{key}"] = {
            "es": label_ov.get("es") or auto["es"],
            "en": label_ov.get("en") or auto["en"],
        }
        help_ov = overrides["helps"].get(key, {})
        entries[f"CFG_HELP_{key}"] = {
            "es": help_ov.get("es") or _auto_help(key, "es"),
            "en": help_ov.get("en") or _auto_help(key, "en"),
        }

        spec = CONFIG_SCHEMA[key]
        if spec.get("type") == "choice":
            for choice in sorted(spec["choices"]):
                ch_ov = (overrides["choices"].get(key) or {}).get(choice, {})
                auto_ch = {"es": choice.replace("_", " "), "en": choice.replace("_", " ")}
                entries[f"CFG_CHOICE_{key}_{choice}"] = {
                    "es": ch_ov.get("es") or auto_ch["es"],
                    "en": ch_ov.get("en") or auto_ch["en"],
                }

    return entries


def main() -> int:
    entries = _build_entries()
    lines = [
        '"""Auto-generated config labels — run: python scripts/sync_cfg_i18n.py"""',
        "",
        "CFG_LABELS = " + json.dumps(entries, indent=4, ensure_ascii=False),
        "",
    ]
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
