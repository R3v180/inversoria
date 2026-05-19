# Plan maestro — InversorIA (continuación mayo 2026)

> **Uso en nuevas conversaciones (agentes / Cursor):** lee este archivo **antes** de explorar el repo. Contiene mapa de carpetas, significado de **GH-P1/P2/P3**, flujo Git, trabajo ya hecho, decisiones de producto y el backlog detallado (**checkpoints**, **launcher**, **asistente IA**). Evita búsquedas amplias si la respuesta está aquí.

**Repositorio:** https://github.com/R3v180/inversoria  
**Rama de trabajo actual (mayo 2026):** `feat/plan-execution-2026-05` → PR pendiente a `main` cuando el mantenedor lo pida.  
**Idioma UI por defecto:** español (`i18n`, claves ES+EN).

---

## 1. Cómo trabajamos (mantenedor + agente)

### 1.1 Reglas de oro

| Regla | Detalle |
|-------|---------|
| **No push a `main`** | Rama protegida. Siempre feature branch + PR ([`CONTRIBUTING.md`](../CONTRIBUTING.md)). |
| **No commit salvo petición** | El usuario pide explícitamente commit/PR; si no, solo cambios locales. |
| **Respuestas al usuario** | Español, prosa clara, sin sobrecargar con identificadores. |
| **Cambios mínimos** | No refactorizar fuera del alcance; reutilizar convenciones del repo. |
| **Modo real** | Nunca debilitar confirmaciones UI, import seguro ni guardrails sin explicar trade-off. |
| **Secretos** | `.env`, `user_settings.json`, `*.db`, logs → **nunca** al repo ([`.gitignore`](../.gitignore)). |
| **i18n** | Texto visible = `_('KEY')` en [`i18n.py`](../i18n.py) + ES/EN. Tras tocar `CONFIG_SCHEMA`: `python scripts/sync_cfg_i18n.py`. Ver [`docs/I18N.md`](I18N.md). |

### 1.2 Flujo Git típico

```bash
git switch main
git pull --ff-only
git switch feat/plan-execution-2026-05   # o crear nueva rama desde main
# ... cambios ...
git add <archivos concretos>             # evitar git add . si hay basura local
git commit -m "tipo: resumen en inglés o español coherente con el repo"
git push -u origin HEAD
# PR a main (gh pr create si está instalado; si no, compare URL en GitHub)
```

**Commits recientes en la rama (referencia):**

- Motor GH + UI: `1074888` — plan ejecución GH-P1/P2/P3
- `a5ea782` docs README/i18n
- `1b16f65` feat(i18n)
- `da3564f` feat(settings) 4 pestañas + plantillas
- `cb5881a` fix AI budget, posiciones dashboard
- `f2b5810` fix plantillas no tocan sim/real; reset = Recomendado
- `dd0f988` fix `st.container(border=bool)` en tarjetas plantilla

### 1.3 Verificación local estándar

```bash
cd d:\proyectos\IVERSORIA
python -m unittest discover -s tests -v
python scripts/audit_i18n.py --fail-on-warn
```

Checklist manual: [`docs/SMOKE_CHECKLIST.md`](SMOKE_CHECKLIST.md). Modo real: [`docs/REAL_MODE_RUNBOOK.md`](REAL_MODE_RUNBOOK.md).

### 1.4 Documentos del repo (índice rápido)

| Archivo | Para qué |
|---------|----------|
| [`README.md`](../README.md) | Documentación usuario (EN+ES), arquitectura, riesgo |
| [`ROADMAP_CONTINUACION.md`](../ROADMAP_CONTINUACION.md) | Fases 0–5 **ya hechas** en la rama (GH, UI, plantillas) |
| [`AUDIT_ROADMAP.md`](../AUDIT_ROADMAP.md) | Backlog auditoría PDF → PRs #36–#61 |
| [`docs/PLAN_MAESTRO.md`](PLAN_MAESTRO.md) | **Este archivo** — plan futuro checkpoints/launcher |
| [`docs/I18N.md`](I18N.md) | Convenciones i18n, scripts |
| [`docs/SMOKE_CHECKLIST.md`](SMOKE_CHECKLIST.md) | Pruebas tras cambios grandes |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Política PR y seguridad |
| [`.cursor/rules/i18n.md`](../.cursor/rules/i18n.md) | Regla Cursor para agentes (i18n) |
| `instruccionesia.md` | **Solo local** (gitignored) — notas IA del mantenedor; **no está en Git** |

---

## 2. Qué significa GH (no confundir con GitHub)

En este proyecto **GH = fases del plan de motor “Gepeto/Hardening”** (auditoría + roadmap interno), **no** “GitHub”.

| Fase | Nombre UI (Ajustes) | Módulos principales |
|------|---------------------|---------------------|
| **GH-P1** | `CFG_GROUP_MOTOR_GH1` — Motor GH-P1 | [`bot_runtime/protections.py`](../bot_runtime/protections.py), [`limit_entry.py`](../bot_runtime/limit_entry.py), [`funding.py`](../bot_runtime/funding.py), [`liquidity.py`](../bot_runtime/liquidity.py), [`position_monitor.py`](../bot_runtime/position_monitor.py), TP escalonado, time-decay en config |
| **GH-P2** | `CFG_GROUP_EDGE_GH2` — Edge GH-P2/P3 (parte 2) | [`webhook_server.py`](../webhook_server.py), [`bot_runtime/hyperopt_lite.py`](../bot_runtime/hyperopt_lite.py), [`inventory_skew.py`](../bot_runtime/inventory_skew.py), [`rule_significance.py`](../bot_runtime/rule_significance.py), [`ui_webhooks.py`](../ui_webhooks.py), [`database_services/webhook_signals.py`](../database_services/webhook_signals.py) |
| **GH-P3** | Mismo grupo + replay/DCA/Ollama | [`ui_services/cycle_replay_viz.py`](../ui_services/cycle_replay_viz.py), [`bot_runtime/dca_grid.py`](../bot_runtime/dca_grid.py), [`decision_runtime/ollama_provider.py`](../decision_runtime/ollama_provider.py) |

**Dónde se configura en UI:** pestaña **Avanzado** en Ajustes → expanders por sección ([`ui_services/config_form.py`](../ui_services/config_form.py) → `_UI_SECTION_DEFS`).

**Dónde se ejecuta:** [`bot_daemon.py`](../bot_daemon.py) importa y llama runtime en `bot_runtime/*`; decisiones IA en [`decision_engine.py`](../decision_engine.py).

---

## 3. Arquitectura en 30 segundos

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  launcher.py    │     │  app.py          │     │  bot_daemon.py  │
│  (Windows exe)  │     │  Streamlit UI    │     │  ciclo 60s      │
└────────┬────────┘     └────────┬─────────┘     └────────┬────────┘
         │                       │                          │
         │    user_settings.json │    iversoria.db (SQLite) │
         │    .env (secretos)    │    equity_history, etc.  │
         └───────────────────────┴──────────────────────────┘
```

| Proceso | Entrada | Persistencia |
|---------|---------|--------------|
| **Streamlit** | `python -m streamlit run app.py` | Lee/escribe `user_settings.json`; DB según modo/perfil |
| **Daemon** | `python bot_daemon.py` | `iversoria.db` o `simulations/<profile>/iversoria.db` |
| **Launcher** | `InversorIA.exe` / `launcher.py` | Arranca ambos; logs en `launcher_logs/` (gitignored) |

**Modos:**

- **Simulación:** perfiles en [`simulation_profiles.py`](../simulation_profiles.py) → carpeta `simulations/`, cuenta en `simulated_account.json`.
- **Real:** Crypto.com vía [`exchange_helper.py`](../exchange_helper.py); baseline dashboard = `real_start_balance` en `system_status` (primera vez en real).

---

## 4. Mapa de archivos críticos (no buscar a ciegas)

### 4.1 UI Streamlit (`ui_*.py` + `ui_services/`)

| Archivo | Responsabilidad |
|---------|-----------------|
| [`app.py`](../app.py) | Shell, sidebar (modo, perfil sim, bot on/off), routing páginas |
| [`ui_dashboard.py`](../ui_dashboard.py) | Cockpit, posiciones, PnL vs baseline |
| [`ui_history.py`](../ui_history.py) | Trades, **rendimiento por periodo**, replay, journal |
| [`ui_settings.py`](../ui_settings.py) | **4 pestañas** Ajustes + plantillas fuera del form |
| [`ui_assistant.py`](../ui_assistant.py) | Chat IA, órdenes/config pendientes |
| [`ui_wallet.py`](../ui_wallet.py) | Cartera exchange, dust, venta manual |
| [`ui_terminal.py`](../ui_terminal.py) | Gráfico técnico + logs filtrados i18n |
| [`ui_webhooks.py`](../ui_webhooks.py) | Cola señales TradingView |
| [`ui_services/config_form.py`](../ui_services/config_form.py) | Schema UI por sección/tab |
| [`ui_services/config_presets_ui.py`](../ui_services/config_presets_ui.py) | Tarjetas plantillas + asistente «¿Qué perfil soy?» |
| [`ui_services/config_preset_assistant.py`](../ui_services/config_preset_assistant.py) | Lógica sugerencia preset |
| [`ui_services/config_io_panel.py`](../ui_services/config_io_panel.py) | Import/export JSON colapsado |
| [`ui_services/performance_period.py`](../ui_services/performance_period.py) | **PnL por periodo** (hoy, 1h, 24h, custom) — base para checkpoints |
| [`ui_services/position_display.py`](../ui_services/position_display.py) | Coste invertido, valor actual, qty exchange |
| [`ui_services/portfolio_summary.py`](../ui_services/portfolio_summary.py) | Baseline dashboard (`real_start` / presupuesto) |
| [`ui_services/log_display.py`](../ui_services/log_display.py) | Tags log traducidos en terminal |

### 4.2 Configuración y plantillas

| Archivo | Responsabilidad |
|---------|-----------------|
| [`config.py`](../config.py) | `DEFAULT_SETTINGS`, `get_setting`, `save_settings`, **`reset_to_defaults()`** → llama Recomendado |
| [`config_importer.py`](../config_importer.py) | `CONFIG_SCHEMA`, validación, diff, apply |
| [`config_presets.py`](../config_presets.py) | Plantillas builtin; **`PRESET_LOCKED_KEYS`** (no tocar sim/real/perfil) |
| [`config_schema_sync.py`](../config_schema_sync.py) | Paridad schema ↔ defaults |
| `config_presets/user_presets.json` | Plantillas usuario (gitignored vía `*.json`) |

### 4.3 Asistente IA

| Archivo | Responsabilidad |
|---------|-----------------|
| [`assistant_runtime/providers.py`](../assistant_runtime/providers.py) | Registry contexto (cartera, periodos, logs, presets…) |
| [`assistant_runtime/context_sources.py`](../assistant_runtime/context_sources.py) | Compactadores (incl. `compact_periods_context`) |
| [`assistant_runtime/intent.py`](../assistant_runtime/intent.py) | Detección intención + `[FETCH_CONTEXT]` |
| [`sentiment_engine.py`](../sentiment_engine.py) | Gemini/Groq/SambaNova/Ollama |
| [`diagnostic_utils.py`](../diagnostic_utils.py) | Paquete diagnóstico seguro, resumen logs |

### 4.4 Daemon y motor

| Archivo | Responsabilidad |
|---------|-----------------|
| [`bot_daemon.py`](../bot_daemon.py) | Ciclo principal, sync posiciones, órdenes, snapshots |
| [`decision_engine.py`](../decision_engine.py) | IA híbrida, macro, MTF, fallback reglas |
| [`database_manager.py`](../database_manager.py) | SQLite, tablas, `system_status` |
| [`bot_runtime/*`](../bot_runtime/) | Protecciones, monitor posiciones, webhook processor, etc. |

### 4.5 Launcher

| Archivo | Responsabilidad |
|---------|-----------------|
| [`launcher.py`](../launcher.py) | UI CustomTkinter, arranque streamlit+daemon, **solo log daemon visible** |
| `launcher_logs/daemon.log` | Log daemon (se **sobrescribe** `"w"` cada arranque) |
| `launcher_logs/streamlit.log` | Log web (append) |
| `launcher_logs/health.json` | Salud daemon (si existe) |

---

## 5. Trabajo ya completado (contexto conversaciones mayo 2026)

### 5.1 UI Ajustes (4 pestañas)

- **Operación:** modo, monedas, IA, filtros liquidez.
- **Riesgo y límites:** posiciones, exposición, stops, rotación.
- **Conexiones:** solo API keys.
- **Avanzado:** prompts, macro, GH-P1/P2, búsqueda ~168 claves.
- **Plantillas:** arriba del form (botones Streamlit); asistente perfil; gestión colapsada.
- **Import/export:** expander al final ([`config_io_panel.py`](../ui_services/config_io_panel.py)).

### 5.2 Plantillas — reglas actuales (importante)

- Builtin = **solo deltas** de estrategia (no copia entera `DEFAULT_SETTINGS`).
- **`PRESET_LOCKED_KEYS`:** `MODO_SIMULACION`, `SIMULATION_PROFILE_ID`, `PRESUPUESTO_INICIAL` — nunca en apply/preview/guardar.
- **Conservador** incluye `TRADING_EXECUTION_MODE=consultive`; **Recomendado/Agresivo** = `auto`.
- **Reset global** = fábrica + plantilla **Recomendado**, conserva sim/real y perfil.
- Asistente «¿Qué perfil soy?» **no pregunta** auto vs consultive → puede sugerir Conservador en cuenta pequeña aunque el usuario use auto (mejora pendiente: pregunta ejecución o desacoplar consultive del preset).

### 5.3 IA y presupuesto

- `AI_ENABLE_LOCAL_BUDGET=False` por defecto (límites del proveedor).
- Fallback a reglas: `AI_RULES_ONLY_ON_BUDGET_EXHAUSTED`, respuesta inválida, etc. ([`decision_engine.py`](../decision_engine.py), tests en `tests/test_ai_budget_and_fallback.py`).

### 5.4 Dashboard posiciones

- Inversión (coste), valor actual, cantidad alineada exchange ([`position_display.py`](../ui_services/position_display.py)).
- Sync cantidades en daemon (`sync_open_positions_with_exchange`).

### 5.5 Rendimiento temporal (existente, **sin checkpoints**)

- [`ui_history.py`](../ui_history.py) + [`performance_period.py`](../ui_services/performance_period.py):
  - Presets: `today`, `last_hour`, `last_24h`, `earliest`, `custom`.
  - Usa tabla `equity_history` + equity actual.
- **Dashboard PnL** sigue siendo baseline global (`real_start_balance` o presupuesto sim), **no** “desde último reset”.

---

## 6. Problema de producto que motiva el plan (checkpoints)

El usuario quiere:

1. **Histórico global** intacto (desde primer arranque del bot).
2. **Vista de evaluación** desde un momento (“nueva estrategia”): PnL ≈ 0 % en ese instante, equity actual como referencia.
3. Disparadores: reset global, aplicar plantilla, cambio sim/real (y opcional import grande).
4. Al cambiar: **preguntar** si activar vista en el nuevo checkpoint o solo guardarlo y seguir en la vista anterior.
5. **Asistente IA** debe entender “cómo voy con esta estrategia” vs “cómo voy en toda la vida del bot”.
6. **Daemon no necesita** checkpoints para operar (solo config viva).

**Workaround hoy:** Historial → periodo **personalizado** → fecha/hora del reset (manual, fácil de olvidar).

---

## 7. Diseño detallado: sistema de checkpoints

### 7.1 Modelo de datos (propuesta)

**Tabla nueva** `strategy_checkpoints` (recomendado) o JSON en `system_status` (MVP):

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | TEXT PK | UUID o slug+timestamp |
| `created_at` | REAL/TEXT | ISO timestamp |
| `event_type` | TEXT | `reset_global`, `preset_applied`, `mode_change`, `config_import`, `profile_reset`, `manual` |
| `label` | TEXT | Humano: "Reset + Recomendado" |
| `equity_usdt` | REAL | Equity en el momento |
| `modo_simulacion` | BOOL | |
| `simulation_profile_id` | TEXT | null en real |
| `preset_id` | TEXT | opcional |
| `config_diff_summary` | TEXT/JSON | Top N claves cambiadas (opcional) |

**Estado de vista (separado):**

| Clave `system_status` | Valor |
|----------------------|-------|
| `active_evaluation_checkpoint_id` | id o vacío = **vista global** |

**Alcance (decisión recomendada):** un checkpoint activo por **universo** `(MODO_SIMULACION, SIMULATION_PROFILE_ID)` — no mezclar perfil sim A con B.

### 7.2 Eventos que CREAN checkpoint

| Evento | ¿Checkpoint? | ¿Diálogo? |
|--------|--------------|-----------|
| Reset global | Sí | Sí |
| Aplicar plantilla (confirmado) | Sí | Sí |
| Vista previa plantilla | **No** | — |
| Cambio sim ↔ real (sidebar o launcher) | Sí | Sí |
| Import JSON (muchas claves) | Sí (umbral) | Sí |
| Guardar formulario Ajustes | No | — |
| Arranque daemon | No | — |
| Checkpoint manual | Sí | Opcional nombre |

### 7.3 Diálogo post-cambio (copy UX)

```
Se ha registrado el checkpoint «{label}» ({equity} USDT).

¿Cómo quieres ver el rendimiento?
  [ Usar este checkpoint ahora ]     → active_evaluation_checkpoint_id = nuevo
  [ Solo guardarlo ]                 → crea; mantiene vista actual
  [ Cancelar ]                       → solo donde tenga sentido revertir el cambio
```

**Defaults sugeridos:**

- Reset global → botón principal “Usar ahora” (usuario suele querer empezar métricas de cero).
- Aplicar plantilla → “Solo guardar” si ya estaba evaluando otra cosa.

### 7.4 Cálculo de métricas desde checkpoint

Reutilizar [`compute_period_performance`](ui_services/performance_period.py):

- `start_dt` = `checkpoint.created_at`
- `start_equity` = `checkpoint.equity_usdt` (fijado, no primer punto equity_history después — evita huecos si no hay tick exacto)
- `current_equity` = balance actual

**Trades cerrados (Historial):** filtrar `trades` / journal con `closed_at >= checkpoint.created_at` cuando vista ≠ global.

**No borrar** filas de `equity_history`.

### 7.5 UI — Historial (prioridad 1)

Barra fija superior:

```
Ver rendimiento:  (•) Global  ( ) Desde checkpoint  [ ▼ lista checkpoints ]
Métricas: inicio $X → actual $Y  (Δ $ / %)
[ Ver todos los checkpoints ]  [ Marcar checkpoint ahora… ]
```

- Nuevo preset periodo: **`from_active_checkpoint`** además de today/1h/24h/custom.
- Lista: fecha, evento, equity, botón “Activar vista”.

### 7.6 UI — Dashboard (prioridad 2)

- Toggle o segunda línea métricas: **PnL global** vs **PnL estrategia (checkpoint X)**.
- Caption claro para no confundir con `real_start_balance`.

### 7.7 UI — Ajustes

- Tras reset/plantilla: modal Streamlit (fuera del `st.form` de plantillas).
- Hint permanente: plantillas no cambian sim/real; checkpoints marcan evaluación.

### 7.8 Asistente IA (prioridad 1 en valor)

Nuevo provider en [`assistant_runtime/providers.py`](../assistant_runtime/providers.py):

- `CHECKPOINTS / EVALUACIÓN ESTRATEGIA`
- Contenido: activo, PnL desde activo, últimos 3 checkpoints, plantilla activa.
- Extender `compact_periods_context` con línea “Desde checkpoint activo: …”.
- `[FETCH_CONTEXT] sections=checkpoints` (opcional).

**El daemon no lee checkpoints.**

### 7.9 Mejoras relacionadas pendientes (plantillas + asistente)

- Pregunta en asistente: **¿Ejecución auto o solo consultivo (señales)?**
- O: **Conservador con `auto`** + filtros estrictos; consultive como plantilla aparte “Solo señales”.
- No sugerir Conservador por cuenta pequeña si el usuario eligió “alta actividad + auto”.

---

## 8. Diseño detallado: Launcher v2

### 8.1 Estado actual (gaps)

| Gap | Detalle |
|-----|---------|
| Perfil sim | Menú existe pero arranque no resume “arrancarás con perfil X” |
| Perfil en real | UI muestra bloque sim (ruido) |
| Checkpoint vista | No existe |
| Logs | Solo daemon ~220 líneas; `streamlit.log` no visible; daemon.log truncado cada arranque |
| Desync | Cambio perfil/modo en web vs launcher hasta reinicio |
| DB path | No visible: `simulations/<id>/iversoria.db` vs raíz |

### 8.2 Flujo objetivo “Antes de arrancar”

```
1. Modo: [ Simulación | Real ]  (+ confirmación real)
2. Si Sim → Perfil: [ dropdown ]  Crear / Reset perfil
3. Vista evaluación: [ Global | Checkpoint ▼ ]   ← solo lectura/escritura system_status
4. Resumen: ruta DB · APIs · plantilla activa · último equity
5. [ Iniciar sistema ]  [ Solo web ]  [ Solo daemon ]  (avanzado)
```

- **Checkpoint al arranque:** solo fija qué checkpoint está **activo para la UI**; no restaura config histórica (fase futura peligrosa en real).
- **Real:** ocultar filas de perfil sim.

### 8.3 Logs — dos capas

| Capa | Audiencia | Contenido |
|------|-----------|-----------|
| **Operativo** | Usuario | Tail daemon filtrado (DECISION, BUY, SELL, SKIP, CYCLE, BLOCK) |
| **Técnico** | Dev / soporte | Pestañas Daemon + Streamlit, tail completo, rotación, `health.json` |

Acciones:

- `daemon.log` → **append** + rotación (`daemon.log.1`), no `"w"` destructivo.
- Botones: “Copiar visible” vs “Copiar paquete técnico”.
- Cabecera sesión: modo, perfil, PID, timestamp.

### 8.4 Sincronización launcher ↔ Streamlit

- Fuente verdad modo/perfil: `user_settings.json` + `simulation_profiles.json`.
- Al arrancar launcher: escribir `system_status` coherente.
- Cambio perfil en launcher: mantener `_restart_runtime_after_profile_change()` (mata streamlit+daemon).

### 8.5 Qué NO hace el launcher

- No aplicar plantillas ni reset (queda en Ajustes + diálogo checkpoint).
- No sustituir Terminal/Historial de la web.

---

## 9. `instruccionesia.md` (archivo local)

- **Ruta:** raíz del proyecto `instruccionesia.md`
- **Git:** ignorado (`.gitignore` línea `instruccionesia.md`) — **cada máquina puede tener el suyo**
- **Uso típico:** instrucciones privadas para exportar contexto a ChatGPT/Claude, prompts internos, notas de trading del mantenedor
- **Agente:** si no existe el archivo, no inventar; usar `README.md`, este plan y `diagnostic_utils.build_safe_diagnostic_package()`
- **Relación con bot:** el asistente **dentro** de la app usa `assistant_runtime`, no lee `instruccionesia.md`

---

## 10. Fases de implementación recomendadas

| Fase | Entregable | Archivos tocados (orientativo) |
|------|------------|--------------------------------|
| **A — Datos** | Tabla/API checkpoints, tests PnL | `database_manager.py`, nuevo `strategy_checkpoints.py` o módulo en `database_services/` |
| **B — Historial + diálogos** | Selector, modal post-reset/preset | `ui_history.py`, `ui_settings.py`, `config_presets.py`, `i18n.py` |
| **C — Asistente** | Provider checkpoints | `assistant_runtime/providers.py`, `context_sources.py` |
| **D — Dashboard** | Toggle PnL global/estrategia | `ui_dashboard.py`, `portfolio_summary.py` |
| **E — Launcher v2** | Pre-arranque, logs técnicos | `launcher.py`, textos TEXT{} |
| **F — Pulido** | Manual checkpoint, export diagnóstico, Conservador/auto UX | varios |

**Orden:** A → B → C → E (paralelo posible con C) → D → F.

**PRs sugeridos:** uno por fase o B+C juntos; no mezclar launcher masivo con schema DB sin necesidad.

---

## 11. Decisiones abiertas (cerrar con el mantenedor)

1. **Scope checkpoint:** ¿por `(modo, profile_id)` o un solo activo global?
2. **Reset perfil sim en launcher:** ¿checkpoint automático?
3. **¿Restaurar config desde checkpoint antiguo?** (recomendación: **no** en v1)
4. **Conservador:** ¿separar consultive de “riesgo bajo” con auto?
5. **¿Dashboard en v1 o solo Historial?**

---

## 12. Tests a añadir (cuando se implemente)

- Crear checkpoint no altera `MODO_SIMULACION`.
- `compute_period_performance` con `start_equity` fijado del checkpoint.
- Diálogo: “solo guardar” no cambia `active_evaluation_checkpoint_id`.
- Lista checkpoints filtrada por perfil sim activo.
- Asistente incluye sección checkpoint cuando activo.

---

## 13. Comandos y rutas Windows (referencia rápida)

```powershell
cd d:\proyectos\IVERSORIA
.\venv\Scripts\Activate.ps1
python -m streamlit run app.py
# otra terminal:
python bot_daemon.py
# o:
.\InversorIA.exe   # launcher desde raíz tras build_launcher.bat
```

| Ruta | Contenido |
|------|-----------|
| `d:\proyectos\IVERSORIA\iversoria.db` | DB real (gitignored) |
| `d:\proyectos\IVERSORIA\simulations\<profile_id>\` | DB + cuenta sim del perfil |
| `d:\proyectos\IVERSORIA\user_settings.json` | Config UI (gitignored) |
| `d:\proyectos\IVERSORIA\.env` | API keys (gitignored) |
| `d:\proyectos\IVERSORIA\launcher_logs\` | Logs launcher (gitignored) |

---

## 14. Mensaje para el agente en la próxima conversación

Copia/pega al inicio si hace falta:

> Continúa InversorIA según `docs/PLAN_MAESTRO.md`. Rama `feat/plan-execution-2026-05`. Implementa la fase que indique el usuario (checkpoints / launcher / asistente). GH-P1/P2/P3 ya están en `bot_runtime/` y pestaña Avanzado. Plantillas: no tocar `PRESET_LOCKED_KEYS`. Lee ROADMAP_CONTINUACION.md solo para histórico de lo ya hecho. No commit hasta que lo pida el usuario.

---

*Última actualización del plan: mayo 2026 — tras acuerdos de producto sobre checkpoints, launcher, plantillas y evaluación de rendimiento.*
