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

- [ ] Revisar defaults de `RISK_PER_TRADE` y alinearlo con `MAX_POSITION_RISK_PCT`.
- [ ] Corregir ratio riesgo/beneficio por defecto: evitar SL 3% vs TP 1%.
- [ ] Definir preset "agresivo sensato" para cuenta pequena sin EV negativo.
- [ ] Subir o rehacer `BACKTEST_HARD_VETO_WIN_RATE` con profit factor y muestra minima.
- [ ] Anadir `MAX_PORTFOLIO_DRAWDOWN_PCT` y cooldown por drawdown acumulado.
- [ ] Bloquear persistencia de API keys en `user_settings.json`.
- [ ] Sanitizar export/import para no filtrar secretos.
- [ ] Arreglar `quick_technical_filter` para `rsi=None` y `adx=None`.
- [ ] Convertir `open`/partial order en estado gestionado, no fallo simple.
- [ ] Anadir timeout real a llamadas Gemini/Groq.
- [ ] Parsear sentimiento con formato estricto, no substring `BULLISH`/`BEARISH`.

## Fase 2 - Ordenes, Reconciliacion y Dinero Real

Objetivo: eliminar posiciones fantasma y estados inconsistentes.

- [ ] Crear state machine de ordenes: `pending -> submitted -> partial -> closed/canceled/failed`.
- [ ] Reconciliar ordenes abiertas al inicio de cada ciclo si `ORDER_RECONCILE_ENABLED=True`.
- [ ] Adoptar fills parciales de compras reales.
- [ ] Ajustar posiciones tras ventas parciales reales.
- [ ] Detectar fondos comprometidos por timeout de red.
- [ ] Evitar retry duplicado de market orders si la respuesta se pierde.
- [ ] Investigar soporte de `clientOrderId`/idempotencia en Crypto.com via CCXT.
- [ ] Eliminar doble `fetch_balance` en venta o protegerlo con lock por simbolo.
- [ ] Serializar ordenes por simbolo para evitar ventas/compras concurrentes.
- [ ] Usar `_call_private` o unificar retry/nonce en `execute_order`.
- [ ] Exponer ordenes pendientes/no reconciliadas en UI.
- [ ] Kill-switch si hay mas de `MAX_UNRECONCILED_ORDERS`.

## Fase 3 - Stops, Salidas y Coherencia Vivo vs Backtest

Objetivo: que el bot vivo y el backtest midan la misma estrategia.

- [ ] Unificar stop-loss vivo y backtest usando ATR cuando exista.
- [ ] Implementar Chandelier Exit / trailing ATR-based.
- [ ] Mantener fallback porcentual solo si no hay ATR valido.
- [ ] Backtest debe usar `check_sell_conditions()` o una fuente compartida equivalente.
- [ ] Aplicar fees en entrada y salida en backtest.
- [ ] Modelar slippage dinamico por liquidez/orderbook.
- [ ] Implementar salida por edad maxima de posicion por regimen.
- [ ] Cooldown por simbolo tras stop-loss.
- [ ] Cooldown menor tras take-profit.
- [ ] TP escalonado opcional: varios niveles y resto con trailing.
- [ ] Break-even con activacion configurable propia, no reutilizando otro parametro.

## Fase 4 - Motor de Decision e Indicadores

Objetivo: mejorar senales sin sobreajustar.

- [ ] Convertir `open`, `volume`, `high`, `low`, `close` a numerico de forma consistente.
- [ ] Anadir EMA21.
- [ ] Anadir MACD.
- [ ] Anadir Bollinger Bands.
- [ ] Anadir StochRSI.
- [ ] Anadir OBV.
- [ ] Incorporar volumen/vol_ratio al score determinista.
- [ ] Revisar doble ajuste adaptativo en `decision_engine.py`.
- [ ] Evitar que provider adjustment rompa el cap de `ADAPTIVE_MAX_SCORE_ADJUSTMENT`.
- [ ] Diferenciar `BEAR`, `RANGING` y `HIGH_VOLATILITY` en `trend_score`.
- [ ] Revisar mezcla fija 70% IA / 30% determinista.
- [ ] Calibrar confianza real: confianza predicha vs win rate posterior.

## Fase 5 - Macro, MTF y Regimen

Objetivo: evitar comprar alts en contexto macro equivocado.

- [ ] Hacer configurable `MACRO_ALTSEASON_BTC_DOM`.
- [ ] En `RISK_ON`, degradar a `CAUTION` si BTC dominance esta demasiado alto.
- [ ] En `CAUTION`, subir a `RISK_OFF` si baja market cap y sube BTC dominance.
- [ ] Anadir histeresis: exigir 2 ciclos o media movil antes de cambiar regimen.
- [ ] Medir tendencia de BTC dominance, no solo valor instantaneo.
- [ ] Anadir `15m` al analisis MTF o documentar por que se excluye.
- [ ] Detectar divergencia RSI-precio en 4H.
- [ ] Penalizar confluencia si hay divergencia contra tendencia.
- [ ] Anadir funding rates como filtro de corto plazo si el exchange lo soporta.
- [ ] Circuit breaker si BTC cae fuerte en ventana corta.

## Fase 6 - Backtesting Confiable

Objetivo: que los priors no den falsa seguridad.

- [ ] Walk-forward validation: train/test rodante.
- [ ] Subir muestra minima de priors a 20-30 trades para decisiones duras.
- [ ] Usar shrinkage bayesiano para win rate con muestras pequenas.
- [ ] Eliminar fallback `ORDER BY win_rate DESC`.
- [ ] Priorizar fallback por muestra, profit factor ajustado y recencia.
- [ ] Corregir Sharpe sobre curva de equity periodica, no trades aislados.
- [ ] Anadir intervalos de confianza.
- [ ] Monte Carlo bootstrap sobre secuencia de trades.
- [ ] Aplicar haircut por muestra pequena y sesgo de supervivencia.
- [ ] Comparar backtest vs resultados reales del journal.

## Fase 7 - Infraestructura Operativa

Objetivo: operar con menos latencia y mejor observabilidad.

- [ ] Sub-ciclo de monitoreo de posiciones abiertas cada 15-30s.
- [ ] Evaluar stop-loss real/OCO en exchange si Crypto.com lo soporta via CCXT.
- [ ] Graceful shutdown con `SIGTERM`/`SIGINT`.
- [ ] File locking para estado simulado entre daemon y UI.
- [ ] Cache de tickers con TTL corto para reducir llamadas duplicadas.
- [ ] Health checks visibles en UI.
- [ ] Alertas por webhook para kill-switch, orden fallida y mismatch.
- [ ] Compactar logs repetitivos.
- [ ] Vista UI de audit events y cycle replay snapshots.

## Fase 8 - IA, Seguridad de Prompt y Consenso

Objetivo: que la IA sea apoyo, no punto unico de fallo.

- [ ] Sanitizar `user_name` y entradas externas antes de meterlas en prompts.
- [ ] Salidas IA en JSON estricto para sentimiento y decisiones.
- [ ] Validar schema de respuesta IA antes de aceptar accion.
- [ ] Fallback rules-only si respuesta IA es invalida.
- [ ] Evaluar consenso multi-provider solo para decisiones de alto impacto.
- [ ] Registrar discrepancias entre proveedores.
- [ ] Usar modelos mas fuertes solo cuando el presupuesto lo permita.
- [ ] Separar prompts estaticos de contexto dinamico para reducir tokens.

## Fase 9 - Ventaja Avanzada

Solo despues de cerrar supervivencia, ejecucion y backtest.

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

Crear issues de GitHub desde este roadmap y empezar por Fase 1:

1. `survival-config-risk-defaults`
2. `secure-secret-persistence`
3. `safe-technical-filter-and-sentiment-parser`
4. `ai-provider-timeouts`
5. `macro-regime-btc-dominance-fixes`
6. `portfolio-drawdown-kill-switch`

