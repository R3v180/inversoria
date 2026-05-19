"""Pre-start helpers for InversorIA Launcher (prepare config before spawning processes)."""

from __future__ import annotations

import json
from pathlib import Path

OPERATIONAL_LOG_TAGS = (
    "[DECISION]",
    "[BUY]",
    "[SELL]",
    "[BLOCK]",
    "[SKIP]",
    "[RISK]",
    "[WEBHOOK]",
    "[ERROR]",
    "[ARMED]",
    "[IDLE]",
    "[DAEMON]",
)


def list_builtin_preset_ids() -> list[str]:
    try:
        from config_presets import list_presets

        return [str(p["id"]) for p in list_presets() if p.get("builtin")]
    except Exception:
        return ["recommended", "conservative", "aggressive", "signals_only"]


def apply_preset_for_launcher(preset_id: str, *, confirm_real: bool = True) -> dict:
    if not preset_id or preset_id == "__keep__":
        return {"skipped": True}
    from config_presets import apply_preset

    return apply_preset(preset_id, confirm_real=confirm_real)


def effective_config_summary() -> str:
    try:
        import config

        return (
            f"DECISION_MODE={getattr(config, 'DECISION_MODE', '?')} · "
            f"TRADING_EXECUTION_MODE={getattr(config, 'TRADING_EXECUTION_MODE', '?')} · "
            f"MAX_OPEN_POSITIONS={getattr(config, 'MAX_OPEN_POSITIONS', '?')} · "
            f"RISK_PER_TRADE={float(getattr(config, 'RISK_PER_TRADE', 0)):.2%}"
        )
    except Exception as exc:
        return f"config: {exc}"


def filter_operational_log_lines(lines: list[str], *, limit: int = 220) -> list[str]:
    if not lines:
        return []
    filtered = [
        line
        for line in lines
        if any(tag in line for tag in OPERATIONAL_LOG_TAGS)
    ]
    source = filtered if filtered else lines
    return source[-limit:]


def read_log_file(path: Path, *, limit: int = 400) -> list[str]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.splitlines()[-limit:]
    except OSError:
        return []


def read_health_json(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
        return json.dumps(data, indent=2, ensure_ascii=False)[:8000]
    except Exception:
        return ""
