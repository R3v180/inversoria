# Smoke checklist — InversorIA

Ejecutar tras cambios grandes en `feat/plan-execution-2026-05` o antes de PR a `main`.

## Automático

```bash
cd d:\proyectos\IVERSORIA
python -m unittest discover -s tests -v
python -m py_compile bot_daemon.py decision_engine.py database_manager.py webhook_server.py config_presets.py config_schema_sync.py
```

Incluye `test_config_parity` (schema = defaults) y `test_config_presets` (builtins + preview).

## UI Streamlit

1. Arrancar app (`streamlit run app.py`).
2. Dashboard: métricas cargan, badge de caché visible.
3. Historial: filtros, journal vs backtest, replay visual de ciclos.
4. Señales TV: página vacía o cola con aprobar/rechazar.
5. Ajustes → **Configuración completa**: buscar `PROTECTION`, editar un campo, guardar (mensaje con N campos).
6. Importador → modo **Parche**, pegar `{"MIN_AUTO_DECISION_SCORE": 0.63}`, validar diff de 1 clave, aplicar.
7. Ajustes → Plantillas: vista previa diff, aplicar **Recomendado**, guardar plantilla personalizada, exportar JSON.
7. Asistente: preguntar "muéstrame los logs" y verificar respuesta con contexto de logs (no genérico vacío).
8. Cambio ES/EN en sidebar: revisar Ajustes (etiquetas de parámetros), Historial y Dashboard en ambos idiomas.
9. `python scripts/audit_i18n.py` sin claves `CFG_KEY_*` faltantes.
10. **Checkpoints:** Ajustes → Reset global → diálogo «Usar ahora» / «Solo guardarlo»; Historial → vista Global / Desde checkpoint; PnL coherente con equity del checkpoint.
11. Aplicar plantilla → checkpoint ofrecido (default «Solo guardarlo»); Dashboard muestra línea PnL estrategia si hay checkpoint activo.
12. Asistente: «¿cómo voy con esta estrategia?» incluye sección CHECKPOINTS.

## Daemon (simulación)

1. Start bot en simulación.
2. Log muestra ciclo sin traceback.
3. Sub-ciclo actualiza máximos; con ventas habilitadas ejecuta SELL si stop/trailing dispara.
4. Protecciones/liquidity/funding registran SKIP en log cuando aplican.
5. Ajustes → Plantillas → aplicar **Conservador** o **Agresivo**; tras un ciclo, `config` recargado refleja flags (p. ej. `PROTECTIONS_ENABLED`, `AGGRESSIVE_TRADING_PROFILE`).

## Webhook (opcional)

1. Activar `WEBHOOK_TRADINGVIEW_ENABLED` y puerto libre.
2. POST JSON: `{"passphrase":"SECRET","ticker":"BTCUSDT","action":"buy"}`.
3. Señal aparece en UI Señales TV; aprobar y ver consumo en siguiente ciclo.

## Modo real (solo si aplica)

Seguir `docs/REAL_MODE_RUNBOOK.md` completo antes de `TRADING_EXECUTION_MODE=auto`.
