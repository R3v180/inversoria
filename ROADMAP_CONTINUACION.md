# Roadmap de continuación — InversorIA

Estado: **plan de ejecución completado** en rama `feat/plan-execution-2026-05` (mayo 2026).

## Fase 0 — UI
- [x] Limpieza `ui_assistant.py`, i18n, `ui_status.py`, caché unificado en páginas.

## Fase 1 — Motor / daemon
- [x] Fix adaptive post-IA, trend_score, protections, liquidity, sub-ciclo, runbook real.

## Fase 2 — GH-P1
- [x] Limit entry, TP escalonado, time-decay, funding veto, slippage dinámico backtest, pesos híbridos, journal vs backtest.

## Fase 3 — GH-P2
- [x] Webhook TradingView (`webhook_server.py`, cola DB, UI Señales TV, consumo en daemon).
- [x] Hyperopt-lite (`bot_runtime/hyperopt_lite.py`).
- [x] Inventory skew sizing.
- [x] Significancia de reglas Jesse (`rule_significance.py` en `decision_engine`).

## Fase 4 — GH-P3 y cierre
- [x] Replay visual de ciclos (`cycle_replay_viz.py` en Historial).
- [x] DCA/grid aislado (`dca_grid.py`).
- [x] Ollama fallback (`decision_runtime/ollama_provider.py` + `sentiment_engine`).
- [x] Sub-ciclo con ventas reales (`position_monitor.py`, `_execute_position_sell`).
- [x] Refactor parcial: `database_services/webhook_signals.py`, `decision_journal_queries.py`, ventas extraídas en daemon.
- [x] i18n Ajustes tab Avanzado + secciones GH-P2/P3.
- [x] `docs/SMOKE_CHECKLIST.md`.

## Verificación

```bash
python -m unittest discover -s tests -v
```

## Fase 5 — Configuración completa y plantillas (mayo 2026)

- [x] `CONFIG_SCHEMA` sincronizado con `DEFAULT_SETTINGS` (`config_schema_sync.py` + test paridad).
- [x] Plantillas completas: `config_presets.py` (recomendado / conservador / agresivo + guardar/importar).
- [x] UI Ajustes: tab **Motor** (schema groups) + panel **Plantillas** + importador JSON.
- [x] Asistente: contexto por intención + `[FETCH_CONTEXT]` + proveedores webhooks/plantilla activa.

### Perfil de simulación vs plantilla de estrategia

| Concepto | Dónde vive | Qué cambia |
|----------|------------|------------|
| **Perfil simulación** | `simulation_profiles` + sidebar | Capital inicial, DB `iversoria.db` del perfil, settings del perfil en modo sim |
| **Plantilla estrategia** | `config_presets` + Ajustes | Todos los parámetros de `CONFIG_SCHEMA` (prompts, riesgo, motor, IA) vía importador |

Aplicar una plantilla **no** cambia de perfil de simulación ni API keys.

PR a `main`: cuando el usuario lo solicite.
