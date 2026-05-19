"""Pre-start helpers for InversorIA Launcher (prepare config before spawning processes)."""

from __future__ import annotations

import json
from pathlib import Path

LOG_SESSION_MARKERS = (
    "[LAUNCHER] Sesión",
    "[LAUNCHER] Nueva sesión daemon",
)


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


def lines_since_last_session(lines: list[str]) -> list[str]:
    """Keep log lines from the latest launcher session marker onward."""
    if not lines:
        return []
    last_idx = -1
    for idx, line in enumerate(lines):
        if any(marker in line for marker in LOG_SESSION_MARKERS):
            last_idx = idx
    if last_idx >= 0:
        return lines[last_idx:]
    return lines


def filter_operational_log_lines(lines: list[str], *, limit: int = 220) -> list[str]:
    if not lines:
        return []
    lines = lines_since_last_session(lines)
    filtered = [
        line
        for line in lines
        if any(tag in line for tag in OPERATIONAL_LOG_TAGS)
    ]
    source = filtered if filtered else lines
    return source[-limit:]


def read_log_file(path: Path, *, limit: int = 400, session_only: bool = True) -> list[str]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if session_only:
            lines = lines_since_last_session(lines)
        return lines[-limit:]
    except OSError:
        return []


def rotate_log_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.parent / f"{path.name}.1"
    if not path.exists():
        return
    try:
        if backup.exists():
            backup.unlink()
        path.replace(backup)
    except OSError:
        pass


def append_session_marker(path: Path, *, label: str) -> None:
    import time

    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"\n[LAUNCHER] Sesión · {stamp} · {label}\n")


def read_health_json(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
        return json.dumps(data, indent=2, ensure_ascii=False)[:8000]
    except Exception:
        return ""
