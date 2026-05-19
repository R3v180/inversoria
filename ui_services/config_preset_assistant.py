"""Wizard: suggest a built-in configuration preset from simple answers."""

from __future__ import annotations

from typing import Literal

RiskTolerance = Literal["low", "medium", "high"]
ActivityLevel = Literal["low", "medium", "high"]
AccountSize = Literal["small", "medium", "large"]

BUILTIN_PRESET_IDS = ("recommended", "conservative", "aggressive", "signals_only")


def suggest_preset_id(
    *,
    real_mode: bool,
    risk_tolerance: RiskTolerance,
    activity_level: ActivityLevel,
    account_size: AccountSize,
    execution_mode: str = "auto",
) -> str:
    """Map questionnaire answers to a built-in preset id."""
    if execution_mode == "consultive":
        return "signals_only"

    if not real_mode:
        return "recommended"

    if risk_tolerance == "low":
        return "conservative"
    if account_size == "small" and risk_tolerance != "high" and activity_level != "high":
        return "conservative"
    if activity_level == "high" and risk_tolerance == "high":
        return "aggressive"
    if risk_tolerance == "high" and activity_level in ("medium", "high"):
        return "aggressive"
    return "recommended"
