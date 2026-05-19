#!/usr/bin/env python3
"""Audit i18n coverage for UI and CONFIG_SCHEMA labels."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import SENSITIVE_SETTING_KEYS
from config_importer import CONFIG_SCHEMA
from i18n import TRANSLATIONS

UI_GLOBS = ["ui_*.py", "app.py", "ui_services/*.py"]
ST_LITERAL = re.compile(
    r"""st\.(?:title|header|subheader|caption|button|checkbox|radio|selectbox|slider|
        number_input|text_input|text_area|toggle|warning|info|error|success|metric|markdown|chat_input)\s*\(\s*
        (?!_\s*\()(?P<q>['\"])(?P<text>(?:\\.|(?!\1).){2,}?)\1""",
    re.VERBOSE | re.IGNORECASE,
)


def _ui_files() -> list[Path]:
    files = []
    for pattern in UI_GLOBS:
        files.extend(ROOT.glob(pattern))
    return sorted({p for p in files if p.is_file()})


def _scan_literals(path: Path) -> list[tuple[int, str]]:
    hits = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return hits
    for line_no, line in enumerate(text.splitlines(), 1):
        if "_(" in line or "unsafe_allow_html" in line:
            continue
        for match in ST_LITERAL.finditer(line):
            literal = match.group("text")
            if literal.strip() in {"---", ""}:
                continue
            if literal.startswith("<") or literal.startswith("http"):
                continue
            hits.append((line_no, literal[:80]))
    return hits


def _missing_cfg_keys() -> list[str]:
    missing = []
    for key in CONFIG_SCHEMA:
        i18n_key = f"CFG_KEY_{key}"
        entry = TRANSLATIONS.get(i18n_key, {})
        if not entry.get("es") or not entry.get("en"):
            missing.append(i18n_key)
    return missing


def _incomplete_translations() -> list[str]:
    bad = []
    for key, entry in TRANSLATIONS.items():
        if not isinstance(entry, dict):
            bad.append(key)
            continue
        if not str(entry.get("es", "")).strip() or not str(entry.get("en", "")).strip():
            bad.append(key)
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit i18n coverage")
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    warnings = 0
    print("=== i18n audit ===\n")

    missing_cfg = _missing_cfg_keys()
    print(f"CFG_KEY_* missing es/en: {len(missing_cfg)}")
    if missing_cfg[:10]:
        for k in missing_cfg[:10]:
            print(f"  - {k}")
    warnings += len(missing_cfg)

    incomplete = _incomplete_translations()
    print(f"\nTRANSLATIONS incomplete: {len(incomplete)}")
    warnings += len(incomplete)

    print("\nHardcoded st.* literals (heuristic):")
    literal_count = 0
    for path in _ui_files():
        hits = _scan_literals(path)
        if hits:
            print(f"\n{path.relative_to(ROOT)} ({len(hits)})")
            for line_no, snippet in hits[:8]:
                print(f"  L{line_no}: {snippet!r}")
            literal_count += len(hits)
    print(f"\nTotal literal hits: {literal_count}")
    warnings += literal_count

    if warnings and args.fail_on_warn:
        print(f"\nFAIL: {warnings} issue(s)")
        return 1
    print(f"\nDone. Issues flagged: {warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
