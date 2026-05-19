from __future__ import annotations


def build_invalid_ai_fallback_decision(base_rules_decision: dict, provider: str | None, error) -> dict:
    result = dict(base_rules_decision or {})
    result["provider"] = "RulesFallback"
    result["ai_provider"] = provider or "unknown"
    result["ai_action"] = "INVALID"
    result["decision_mode"] = "rules_fallback"
    result["reasoning"] = (
        f"[AI_INVALID_RESPONSE] rules-only fallback: {result.get('reasoning', '')} "
        f"(provider={provider or 'unknown'}, error={str(error)[:120]})"
    )
    result["fallback_reason"] = "AI_INVALID_RESPONSE"
    return result

