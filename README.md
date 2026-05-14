<div align="center">

<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
<img src="https://img.shields.io/badge/Google_Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white"/>
<img src="https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white"/>
<img src="https://img.shields.io/badge/Crypto.com-002D74?style=for-the-badge&logo=cryptocom&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white"/>

# 🏛️ INVERSORIA
### Agente de Trading Autónomo con IA Híbrida — v5.1 [INTELLIGENCE UPGRADE]

*Fusión de análisis técnico institucional, inteligencia artificial generativa, memoria histórica de 2 años y gestión de riesgo adaptativa.*

</div>

---

## ¿Qué es Inversoria?

Inversoria es un **bot de trading autónomo** para Crypto.com que opera de forma continua tomando decisiones basadas en un pipeline de cuatro capas de inteligencia:

1. **Filtro Macro** — Analiza dominancia de BTC, sentimiento global y régimen de mercado (Risk-On/Off).
2. **Memoria Histórica (Backtest Engine)** — Consulta el Win Rate real de los últimos 2 años para cada moneda antes de decidir.
3. **Motor de IA Híbrida** — Gemini y Groq analizan la estructura técnica, noticias y sentimiento en tiempo real.
4. **Gestión de Riesgo** — Stop Loss, Trailing Stop dinámico y rotación de capital automática.

La UI Bloomberg-style en Streamlit permite monitorizar el patrimonio, ver gráficos interactivos de confluencia y chatear con el bot para entender sus decisiones.

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                         INVERSORIA                              │
│                                                                 │
│   ┌──────────────┐    SQLite (IPC)    ┌────────────────────┐   │
│   │   app.py     │◄──────────────────►│   bot_daemon.py    │   │
│   │  Streamlit   │                   │   Loop autónomo    │   │
│   │     UI       │                   │   cada 60 seg      │   │
│   └──────┬───────┘                   └────────┬───────────┘   │
│          │                                    │               │
│   ┌──────▼───────┐                   ┌────────▼───────────┐   │
│   │ ui_dashboard │                   │  decision_engine   │   │
│   │ ui_assistant │                   │  backtest_engine   │   │
│   │ ui_history   │                   │  sentiment_engine  │   │
│   │ ui_settings  │                   │  exchange_helper   │   │
│   │ ui_terminal  │                   └────────────────────┘   │
│   └──────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flujo de Decisión v5.1 (cada 60 segundos)

```
bot_daemon.py
│
├── 1. reload(config)  ← Sincronización en caliente de parámetros
│
├── 2. Backtest Semanal Automático (cada 7 días)
│      └── Simulación de 4 estrategias en 2 años de datos para cada moneda
│          └── Genera tabla de "Win Rate Histórico" en SQLite
│
├── 3. Actualizar Watchlist (cada 12h)
│      └── Top 30 por volumen → CurationAI filtra calidad
│
├── 4. Escaneo de Ciclo (por cada símbolo):
│      │
│      ├── Filtro Macro: ¿La dominancia de BTC permite operar Alts?
│      │
│      ├── Filtro Técnico: ¿Hay volatilidad (ADX) o es mercado lateral?
│      │
│      ├── Consulta Histórica: ¿Qué Win Rate tiene esta moneda en este contexto?
│      │     └── Si WR < 35% → VETO HISTÓRICO
│      │
│      ├── IA Híbrida: Análisis final de confluencia técnica + Noticias
│      │
│      └── Ejecución: Compra, Venta o Rotación (si slots llenos)
│
└── 5. Log Equity: Cálculo de PnL Real vs Saldo inicial capturado
```

---

## Nuevas Funcionalidades v5.1

### 🧠 Motor de Backtest Integrado
El bot ya no solo mira el presente. Al arrancar, descarga hasta **4380 velas (2 años)** y calcula qué estrategias funcionaron mejor en el pasado. Si una moneda tiene un historial perdedor en las condiciones actuales, el bot veta la entrada automáticamente.

### 🌍 Filtro Macro Avanzado
Detección automática de regímenes de mercado. Si la dominancia de Bitcoin es demasiado alta o el sentimiento global es de pánico, el bot entra en modo defensivo y protege tu capital en USDT.

### 📈 Dashboard Interactivo
- **Gráficos de Confluencia**: Visualización de EMAs, RSI y ATR en tiempo real.
- **Acceso Rápido**: Botones (📈) en las posiciones activas para saltar directamente al gráfico de esa moneda.
- **PnL Real**: Seguimiento exacto de ganancias/pérdidas basado en tu saldo real de Crypto.com al iniciar.

---

## Instalación y Configuración

### Prerrequisitos
- Python 3.11+
- Claves API de Crypto.com, Google Gemini y Groq.

### Configuración rápida
1. Clona el repositorio.
2. Instala dependencias: `pip install -r requirements.txt`
3. Configura tu `.env` con las claves necesarias.
4. Lanza la UI: `streamlit run app.py`
5. Lanza el Daemon: `python bot_daemon.py`

---

## Gestión de Riesgo

| Parámetro | Función |
|---|---|
| `STOP_LOSS_PCT` | Corte de pérdidas fijo por operación. |
| `TRAILING_STOP` | Asegura beneficios una vez la moneda sube un 2-5%. |
| `ROTATION` | Cierra la posición más débil para entrar en una de mayor confianza. |
| `MAX_POSITIONS` | Límite configurable de slots abiertos simultáneos (ahora hasta 5). |

---

<div align="center">

**INVERSORIA v5.1** · Inteligencia Híbrida · Licencia MIT

</div>
