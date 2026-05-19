from __future__ import annotations


def cap_size_to_capacity(symbol: str, amount_usdt: float, total_value: float, exposures: dict, bucket: str, limits: dict) -> tuple[float, dict]:
    amount_usdt = float(amount_usdt or 0)
    total_value = float(total_value or 0)
    if amount_usdt <= 0 or total_value <= 0:
        return 0.0, {}

    capacities = {
        "portfolio": max(0.0, (total_value * limits["max_portfolio"]) - exposures["total"]),
        "symbol": max(0.0, (total_value * limits["max_symbol"]) - exposures["symbols"].get(symbol, 0.0)),
        "bucket": max(0.0, (total_value * limits["max_bucket"]) - exposures["buckets"].get(bucket, 0.0)),
    }
    if bucket not in {"BTC", "ETH"}:
        capacities["alt"] = max(0.0, (total_value * limits["max_alt"]) - exposures["alt"])

    raw_capped = min(amount_usdt, *capacities.values())
    capped = max(0.0, raw_capped * 0.999) if raw_capped + 1e-8 < amount_usdt else amount_usdt
    return capped, {
        "bucket": bucket,
        "capacities": {key: round(value, 8) for key, value in capacities.items()},
        "original_amount_usdt": round(amount_usdt, 8),
        "capped_amount_usdt": round(capped, 8),
        "capped": capped + 1e-8 < amount_usdt,
    }

