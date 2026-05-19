from __future__ import annotations


def position_balance_mismatches(open_positions, exchange, safe_float, tolerance_pct: float = 1.0, min_usdt: float = 0.25):
    mismatches = []
    if exchange.modo_simulacion:
        return mismatches

    tolerance_pct = max(0.0, safe_float(tolerance_pct, 1.0)) / 100.0
    min_usdt = max(0.0, safe_float(min_usdt, 0.25))
    for symbol, pos in (open_positions or {}).items():
        expected = safe_float(pos.get("amount"), 0.0)
        if expected <= 0:
            continue
        try:
            actual = safe_float(exchange.get_coin_balance(symbol), 0.0)
        except Exception as exc:
            mismatches.append({"symbol": symbol, "reason": f"BALANCE_ERROR:{exc}"})
            continue

        diff = max(0.0, expected - actual)
        tolerance = max(1e-8, expected * tolerance_pct)
        if min_usdt > 0:
            price = safe_float(exchange.get_ticker(symbol), 0.0)
            if price > 0:
                tolerance = max(tolerance, min_usdt / price)
        if diff > tolerance:
            mismatches.append(
                {
                    "symbol": symbol,
                    "db_amount": round(expected, 10),
                    "exchange_amount": round(actual, 10),
                    "diff_amount": round(diff, 10),
                    "tolerance_amount": round(tolerance, 10),
                    "diff_pct": round((diff / expected) * 100, 4) if expected > 0 else 0.0,
                }
            )
    return mismatches

