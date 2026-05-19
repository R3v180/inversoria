# Runbook — primera prueba en modo real (consultivo)

## Antes de arrancar

1. API Crypto.com dedicada, **sin retiros**.
2. `.env` con claves; probar en launcher.
3. `TRADING_EXECUTION_MODE=consultive` en configuración.
4. `MODO_SIMULACION=False` solo tras revisar diagnóstico en simulación.

## Checklist

- [ ] Kill-switches activos (`KILL_SWITCH_ENABLED`).
- [ ] `MAX_DAILY_LOSS_PCT` y `MAX_PORTFOLIO_EXPOSURE_PCT` conservadores.
- [ ] Revisar órdenes no reconciliadas en Dashboard.
- [ ] Un ciclo daemon en consultivo: logs `[CONSULTIVE]` sin `[BUY]`/`[SELL]` ejecutados.
- [ ] Pasar a `auto` solo con capital mínimo y un símbolo si se desea.

## Si algo falla

- Pausar bot en sidebar (`is_running=false`).
- Revisar `audit_events` en Historial.
- No reactivar `clientOrderId` hasta validación testnet.

*Issue GitHub sugerida: #5 Document safe real-mode setup.*
