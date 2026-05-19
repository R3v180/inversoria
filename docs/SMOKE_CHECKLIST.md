# Smoke checklist — InversorIA

Ejecutar tras cambios grandes en `feat/plan-execution-2026-05` o antes de PR a `main`.

## Automático

```bash
cd d:\proyectos\IVERSORIA
python -m unittest discover -s tests -v
python -m py_compile bot_daemon.py decision_engine.py database_manager.py webhook_server.py
```

## UI Streamlit

1. Arrancar app (`streamlit run app.py`).
2. Dashboard: métricas cargan, badge de caché visible.
3. Historial: filtros, journal vs backtest, replay visual de ciclos.
4. Señales TV: página vacía o cola con aprobar/rechazar.
5. Ajustes → Avanzado: guardar toggles webhook/hyperopt/Ollama sin error.
6. Cambio ES/EN en sidebar persiste.

## Daemon (simulación)

1. Start bot en simulación.
2. Log muestra ciclo sin traceback.
3. Sub-ciclo actualiza máximos; con ventas habilitadas ejecuta SELL si stop/trailing dispara.
4. Protecciones/liquidity/funding registran SKIP en log cuando aplican.

## Webhook (opcional)

1. Activar `WEBHOOK_TRADINGVIEW_ENABLED` y puerto libre.
2. POST JSON: `{"passphrase":"SECRET","ticker":"BTCUSDT","action":"buy"}`.
3. Señal aparece en UI Señales TV; aprobar y ver consumo en siguiente ciclo.

## Modo real (solo si aplica)

Seguir `docs/REAL_MODE_RUNBOOK.md` completo antes de `TRADING_EXECUTION_MODE=auto`.
