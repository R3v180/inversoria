from __future__ import annotations


def liquidate_all_to_usdt(db, exchange, reason: str = "manual_emergency_liquidation") -> dict:
    """Liquidación rápida: exchange + limpiar posiciones abiertas del bot."""
    result = exchange.liquidate_all_to_usdt()
    db.clear_open_positions()
    try:
        db.add_log(f"{reason}: liquidate_all_to_usdt result={result}")
    except Exception:
        pass
    return {"ok": True, "result": result}


def liquidate_all_with_accounting(
    db,
    exchange,
    trade_reason: str = "Liquidación Manual",
    log_fn=None,
) -> dict:
    """Liquidación con journal por símbolo (sidebar / flujos detallados)."""
    resultados = exchange.liquidate_all_to_usdt()
    for exito in resultados.get("exitos", []):
        sym = exito["symbol"]
        qty = exito["amount"]
        price = exito["price"]
        db.save_trade(sym, "sell", price, qty, trade_reason, 0.0)
        db.remove_open_position(sym)
        if log_fn:
            log_fn(f"✅ Liquidado: {qty:.4f} {sym} a {price:.2f}")
    db.clear_open_positions()
    try:
        db.add_log(
            f"liquidate_all: exitos={len(resultados.get('exitos', []))} "
            f"fallos={len(resultados.get('fallos', []))}"
        )
    except Exception:
        pass
    return resultados
