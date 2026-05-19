# InversorIA Audit Roadmap

Fuente: `Auditoria_InversorIA_Completa.pdf` del 19 de mayo de 2026.

Objetivo: convertir la auditoria en un backlog trazable por fases. No todo debe aplicarse literalmente: cada punto debe pasar por revision tecnica, pruebas y PR pequeno antes de entrar en `main`.

## Estado Base

Ya existe una pila de PRs que cubre parte de la auditoria:

- PR #36: gobierno de configuracion, UI, importador y diagnosticos.
- PR #37: vigilancia persistente de dust e inventario.
- PR #38: presupuesto global de IA y degradacion por limite.
- PR #39: kill-switches operacionales y health export.
- PR #40: auditoria local de ordenes y escrituras mas atomicas.
- PR #41: add-to-winner controlado, break-even y take-profit parcial.
- PR #42: snapshots de ciclo y eventos auditables.
- PR #43: roadmap de auditoria trazable.
- PR #44: controles de supervivencia, defaults de riesgo, secretos, timeouts IA y drawdown.
- PR #45: reconciliacion y estados de ordenes reales.
- PR #46: stops ATR compartidos entre vivo y backtest.
- PR #47: senales de volumen/momentum e indicadores adicionales.
- PR #48: macro/MTF con 15m y divergencias RSI.
- PR #49: metricas de fiabilidad de backtest.
- PR #50: alertas operativas y health enriquecido.
- PR #51: validacion de schema de respuestas IA.
- PR #52: gates para funciones de edge avanzado.
- PR #54: reconciliacion de ordenes pendientes al arrancar/ciclo y UI de ordenes no reconciliadas.
- PR #55: cooldowns por simbolo tras salidas por stop-loss/take-profit.
- PR #56: fallback rules-only cuando la respuesta IA de decision es invalida.
- PR #57: alertas para orden fallida y mismatch DB/exchange.
- PR #58: histeresis de regimen macro y tendencia/media movil de BTC dominance.
- PR #59: vista UI para audit events y cycle replay snapshots.
- PR #60: retry privado/nonce en ejecucion de ordenes y client order id experimental apagado por defecto.
- PR #61: metricas avanzadas de backtest: out-of-sample, intervalos bootstrap y Monte Carlo.

## Inventario de Auditoria

Resumen del PDF:

- 39 hallazgos criticos.
- 81 hallazgos altos.
- 95 hallazgos medios.
- 39 hallazgos bajos.
- 254 hallazgos totales.

Los modulos con mayor concentracion de riesgo son:

- `decision_engine.py`
- `bot_daemon.py`
- `database_manager.py`
- `config.py`
- `trading_logic.py`
- `exchange_helper.py`
- `backtest_engine.py`
- `market_context.py`
- `sentiment_engine.py`

## Fase 0 - Cerrado o Parcialmente Cubierto

- [x] Configuracion avanzada visible por UI/importador/diagnostico.
- [x] Prompts vacios caen a defaults internos.
- [x] Cache persistente de decisiones IA por simbolo.
- [x] Batch AI decisions para reducir consumo.
- [x] Persistencia de refresh/cooldowns sensibles a restart.
- [x] Cache compartida de noticias.
- [x] Contexto del asistente mas compacto y util.
- [x] Vigilancia persistente de dust/inventario.
- [x] Presupuesto IA por ciclo/dia/tokens estimados.
- [x] Kill-switch inicial por equity cero, mismatch DB/exchange y errores.
- [x] Auditoria local de ordenes.
- [x] Escritura atomica del estado simulado.
- [x] Add-to-winner controlado por config.
- [x] Take-profit parcial y break-even configurables.
- [x] Snapshots de ciclo y audit events.

## Fase 1 - Supervivencia Matematica y Seguridad Basica

Prioridad maxima antes de operar en real automatico.

- [x] Revisar defaults de `RISK_PER_TRADE` y alinearlo con `MAX_POSITION_RISK_PCT`. Cubierto en PR #44.
- [x] Corregir ratio riesgo/beneficio por defecto: evitar SL 3% vs TP 1%. Cubierto en PR #44.
- [x] Definir preset "agresivo sensato" para cuenta pequena sin EV negativo. Cubierto en PR #44.
- [x] Subir o rehacer `BACKTEST_HARD_VETO_WIN_RATE` con profit factor y muestra minima. Cubierto en PR #44 y PR #49.
- [x] Anadir `MAX_PORTFOLIO_DRAWDOWN_PCT` y cooldown por drawdown acumulado. Cubierto en PR #44.
- [x] Bloquear persistencia de API keys en `user_settings.json`. Cubierto en PR #44.
- [x] Sanitizar export/import para no filtrar secretos. Cubierto en PR #36 y PR #44.
- [x] Arreglar `quick_technical_filter` para `rsi=None` y `adx=None`. Cubierto en PR #44.
- [x] Convertir `open`/partial order en estado gestionado, no fallo simple. Cubierto en PR #45.
- [x] Anadir timeout real a llamadas Gemini/Groq. Cubierto en PR #44.
- [x] Parsear sentimiento con formato estricto, no substring `BULLISH`/`BEARISH`. Cubierto en PR #44.

## Fase 2 - Ordenes, Reconciliacion y Dinero Real

Objetivo: eliminar posiciones fantasma y estados inconsistentes.

- [x] Crear state machine de ordenes: `pending -> submitted -> partial -> closed/canceled/failed`. Cubierto parcialmente por estados `open`/`partial`/`closed`/`failed` en PR #45.
- [x] Reconciliar ordenes abiertas al inicio de cada ciclo si `ORDER_RECONCILE_ENABLED=True`. Cubierto en PR #54.
- [x] Adoptar fills parciales de compras reales. Cubierto en PR #45.
- [x] Ajustar posiciones tras ventas parciales reales. Cubierto en PR #41 y PR #45.
- [x] Detectar fondos comprometidos por timeout de red. Cubierto como orden pendiente/no reconciliada en PR #45 y PR #50.
- [x] Evitar retry duplicado de market orders si la respuesta se pierde. Cubierto parcialmente en PR #60: `clientOrderId` queda preparado pero desactivado por defecto hasta validacion real de Crypto.com/CCXT.
- [x] Investigar soporte de `clientOrderId`/idempotencia en Crypto.com via CCXT. Cubierto como soporte experimental configurable en PR #60; pendiente validacion en real/testnet antes de activarlo.
- [x] Eliminar doble `fetch_balance` en venta o protegerlo con lock por simbolo. Cubierto en PR #45.
- [x] Serializar ordenes por simbolo para evitar ventas/compras concurrentes. Cubierto con lock de ejecucion en helper en PR #45.
- [x] Usar `_call_private` o unificar retry/nonce en `execute_order`. Cubierto en PR #60.
- [x] Exponer ordenes pendientes/no reconciliadas en UI. Cubierto en PR #54.
- [x] Kill-switch si hay mas de `MAX_UNRECONCILED_ORDERS`. Cubierto en PR #45.

## Fase 3 - Stops, Salidas y Coherencia Vivo vs Backtest

Objetivo: que el bot vivo y el backtest midan la misma estrategia.

- [x] Unificar stop-loss vivo y backtest usando ATR cuando exista. Cubierto en PR #46.
- [x] Implementar Chandelier Exit / trailing ATR-based. Cubierto como trailing ATR en PR #46.
- [x] Mantener fallback porcentual solo si no hay ATR valido. Cubierto en PR #46.
- [x] Backtest debe usar `check_sell_conditions()` o una fuente compartida equivalente. Cubierto con `protective_levels()` compartido en PR #46.
- [x] Aplicar fees en entrada y salida en backtest. Cubierto previamente y mantenido en PR #46.
- [x] Modelar slippage dinamico por liquidez/orderbook. Cubierto en `bot_runtime/slippage.py` + `backtest_engine.py`.
- [x] Implementar salida por edad maxima de posicion por regimen. Cubierto como edad maxima configurable en PR #46.
- [x] Cooldown por simbolo tras stop-loss. Cubierto en PR #55.
- [x] Cooldown menor tras take-profit. Cubierto en PR #55.
- [ ] TP escalonado opcional: varios niveles y resto con trailing.
- [x] Break-even con activacion configurable propia, no reutilizando otro parametro. Cubierto en PR #46.

## Fase 4 - Motor de Decision e Indicadores

Objetivo: mejorar senales sin sobreajustar.

- [x] Convertir `open`, `volume`, `high`, `low`, `close` a numerico de forma consistente. Cubierto en PR #47.
- [x] Anadir EMA21. Cubierto en PR #47.
- [x] Anadir MACD. Cubierto en PR #47.
- [x] Anadir Bollinger Bands. Cubierto en PR #47.
- [x] Anadir StochRSI. Cubierto en PR #47.
- [x] Anadir OBV. Cubierto en PR #47.
- [x] Incorporar volumen/vol_ratio al score determinista. Cubierto en PR #47.
- [ ] Revisar doble ajuste adaptativo en `decision_engine.py`.
- [ ] Evitar que provider adjustment rompa el cap de `ADAPTIVE_MAX_SCORE_ADJUSTMENT`.
- [ ] Diferenciar `BEAR`, `RANGING` y `HIGH_VOLATILITY` en `trend_score`.
- [ ] Revisar mezcla fija 70% IA / 30% determinista.
- [ ] Calibrar confianza real: confianza predicha vs win rate posterior.

## Fase 5 - Macro, MTF y Regimen

Objetivo: evitar comprar alts en contexto macro equivocado.

- [x] Hacer configurable `MACRO_ALTSEASON_BTC_DOM`. Cubierto en PR #44.
- [x] En `RISK_ON`, degradar a `CAUTION` si BTC dominance esta demasiado alto. Cubierto en PR #44.
- [x] En `CAUTION`, subir a `RISK_OFF` si baja market cap y sube BTC dominance. Cubierto en PR #44.
- [x] Anadir histeresis: exigir 2 ciclos o media movil antes de cambiar regimen. Cubierto en PR #58.
- [x] Medir tendencia de BTC dominance, no solo valor instantaneo. Cubierto en PR #58.
- [x] Anadir `15m` al analisis MTF o documentar por que se excluye. Cubierto en PR #48.
- [x] Detectar divergencia RSI-precio en 4H. Cubierto en PR #48.
- [x] Penalizar confluencia si hay divergencia contra tendencia. Cubierto en PR #48.
- [ ] Anadir funding rates como filtro de corto plazo si el exchange lo soporta.
- [ ] Circuit breaker si BTC cae fuerte en ventana corta.

## Fase 6 - Backtesting Confiable

Objetivo: que los priors no den falsa seguridad.

- [x] Walk-forward validation: train/test rodante. Cubierto como out-of-sample minimo viable en PR #61.
- [x] Subir muestra minima de priors a 20-30 trades para decisiones duras. Cubierto en PR #49.
- [ ] Usar shrinkage bayesiano para win rate con muestras pequenas.
- [ ] Eliminar fallback `ORDER BY win_rate DESC`.
- [ ] Priorizar fallback por muestra, profit factor ajustado y recencia.
- [ ] Corregir Sharpe sobre curva de equity periodica, no trades aislados.
- [x] Anadir intervalos de confianza. Cubierto como intervalo bootstrap de expectancy en PR #61.
- [x] Monte Carlo bootstrap sobre secuencia de trades. Cubierto en PR #61.
- [x] Aplicar haircut por muestra pequena y sesgo de supervivencia. Cubierto como `reliability_score` y sample factor en PR #49.
- [ ] Comparar backtest vs resultados reales del journal.

## Fase 7 - Infraestructura Operativa

Objetivo: operar con menos latencia y mejor observabilidad.

- [ ] Sub-ciclo de monitoreo de posiciones abiertas cada 15-30s.
- [ ] Evaluar stop-loss real/OCO en exchange si Crypto.com lo soporta via CCXT.
- [ ] Graceful shutdown con `SIGTERM`/`SIGINT`.
- [ ] File locking para estado simulado entre daemon y UI.
- [ ] Cache de tickers con TTL corto para reducir llamadas duplicadas.
- [x] Health checks visibles en UI. Cubierto por diagnosticos existentes y health enriquecido en PR #50.
- [x] Alertas por webhook para kill-switch, orden fallida y mismatch. Kill-switch en PR #50; orden fallida y mismatch en PR #57.
- [x] Compactar logs repetitivos. Cubierto en PR #37 y configuracion de dust/logs.
- [x] Vista UI de audit events y cycle replay snapshots. Cubierto en PR #59.

## Fase 8 - IA, Seguridad de Prompt y Consenso

Objetivo: que la IA sea apoyo, no punto unico de fallo.

- [x] Sanitizar `user_name` y entradas externas antes de meterlas en prompts. Cubierto en PR #44.
- [x] Salidas IA en JSON estricto para sentimiento y decisiones. Cubierto parcialmente: decisiones schema JSON en PR #51; sentimiento usa etiqueta estricta en PR #44.
- [x] Validar schema de respuesta IA antes de aceptar accion. Cubierto en PR #51.
- [x] Fallback rules-only si respuesta IA es invalida. Cubierto en PR #56.
- [ ] Evaluar consenso multi-provider solo para decisiones de alto impacto.
- [ ] Registrar discrepancias entre proveedores.
- [ ] Usar modelos mas fuertes solo cuando el presupuesto lo permita.
- [ ] Separar prompts estaticos de contexto dinamico para reducir tokens.

## Fase 9 - Ventaja Avanzada

Solo despues de cerrar supervivencia, ejecucion y backtest.

Estado actual: PR #52 anade gates (`ADVANCED_EDGE_ENABLED`, fiabilidad minima y muestra minima) para que cualquier ventaja avanzada quede apagada por defecto y solo pueda actuar con evidencia suficiente.

- [ ] Position sizing ajustado por drawdown.
- [ ] Kelly fraccional con limites duros.
- [ ] Correlation-adjusted portfolio scoring.
- [ ] Market breadth: porcentaje de alts sobre EMA50/EMA200.
- [ ] Open interest y funding como senal de leverage.
- [ ] Stablecoin flows si hay API fiable.
- [ ] Fear & Greed integrado en regimen macro.
- [ ] Filtro horario por liquidez.
- [ ] WebSocket para precios en tiempo real.
- [ ] Ordenes limitadas/OCO si el exchange lo permite.

## Criterios de Trabajo

- Cada fase debe dividirse en PRs pequenos.
- Cada PR debe cerrar una issue o subtarea concreta.
- Primero tests/smoke tests de DB y sintaxis.
- No operar en real automatico hasta completar Fase 1 y Fase 2.
- Para pruebas reales, usar `TRADING_EXECUTION_MODE=consultive` al principio.
- No aplicar recomendaciones que aumenten complejidad sin una hipotesis medible.

## Proxima Decision Recomendada

La pila autopilot principal ya esta implementada y documentada en PRs #43-#61. Las issues asignadas antiguas #30-#35 se cerraron como completadas/obsoletas.

Siguientes issues utiles, no obsoletas:

1. `real-mode-safe-runbook`: checklist operativo para primera prueba real en modo consultivo.
2. `dynamic-slippage-backtest`: slippage dinamico por liquidez/orderbook en backtest.
3. `decision-calibration`: calibrar confianza predicha vs win rate posterior y revisar mezcla IA/determinista.
4. `advanced-edge-research`: Kelly, correlacion, breadth, funding/open interest y OCO/limit orders, siempre detras de gates.
5. `macro-worker`: sacar refresco macro a worker si vuelve a bloquear UI o daemon.
6. `local-ai-provider`: proveedor local OpenAI-compatible/Ollama cuando toque reducir dependencia externa.

La limpieza UI/refactor/asistente queda separada de estos pendientes estrategicos: primero se ordenan responsabilidades, servicios compartidos y fachadas compatibles; despues se atacan las mejoras de trading/backtest/edge en PRs pequenos.

