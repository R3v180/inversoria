"""Translate log line tags for terminal display."""

from __future__ import annotations

import re

from i18n import _

_TAG_MAP = {
    "[SKIP]": "LOG_TAG_SKIP",
    "[BUY]": "LOG_TAG_BUY",
    "[SELL]": "LOG_TAG_SELL",
    "[ERROR]": "LOG_TAG_ERROR",
    "[WARN]": "LOG_TAG_WARN",
    "[BLOCK]": "LOG_TAG_BLOCK",
    "[ROTATION]": "LOG_TAG_ROTATION",
}


def translate_log_line(line: str) -> str:
    out = str(line or "")
    for src, i18n_key in _TAG_MAP.items():
        if src in out:
            out = out.replace(src, _(i18n_key))
    return out


def log_line_matches_noise(line: str) -> bool:
    """True if line should be filtered from important logs."""
    text = str(line or "")
    scan = _("LOG_FILTER_SCAN")
    cycle = _("LOG_FILTER_CYCLE")
    return scan in text or cycle in text or "Escaneo" in text or "Ciclo" in text
