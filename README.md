<div align="center">

<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
<img src="https://img.shields.io/badge/Google_Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white"/>
<img src="https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white"/>
<img src="https://img.shields.io/badge/Crypto.com-002D74?style=for-the-badge&logo=cryptocom&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white"/>

# 🏛️ INVERSORIA
### Agente de Trading Autónomo con IA Híbrida — v6.1 [GLOBAL MACRO & DYNAMIC UPGRADE]

*Fusión de análisis técnico institucional, inteligencia artificial generativa, memoria histórica de 2 años, análisis de mercados globales y gestión de capital dinámica.*

</div>

---

## ¿Qué es Inversoria?

Inversoria es un **bot de trading autónomo** para Crypto.com que opera de forma continua tomando decisiones basadas en un pipeline de cinco capas de inteligencia:

1. **Inteligencia Global (Alpha Vantage)** — Monitoriza el Dólar (DXY), Petróleo (WTI) y Bolsa (SP500) para detectar riesgos sistémicos.
2. **Filtro Macro Crypto** — Analiza dominancia de BTC y régimen de mercado (Risk-On/Off).
3. **Memoria Histórica (Backtest Engine)** — Consulta el Win Rate real de los últimos 2 años para cada moneda antes de decidir.
4. **Motor de IA Híbrida** — Gemini y Groq analizan la estructura técnica, noticias y sentimiento en tiempo real.
5. **Gestión Dinámica de Capital** — Ajusta automáticamente el número de posiciones según el balance total de la cuenta.

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
│   │ ui_assistant │                   │  macro_analyzer    │   │
│   │ ui_history   │                   │  backtest_engine   │   │
│   │ ui_settings  │                   │  exchange_helper   │   │
│   │ ui_terminal  │                   └────────────────────┘   │
│   └──────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flujo de Decisión v6.1 (cada 60 segundos)

```
bot_daemon.py
│
├── 1. Actualización Macro Global (cada 6h)
│      └── Consulta Alpha Vantage: DXY, SP500, WTI, GLD
│          └── Veto automático si hay pánico en bolsa o dólar fuerte
│
├── 2. Backtest Semanal Automático (cada 7 días)
│      └── Simulación de 2 años → Genera "Win Rate Histórico"
│
├── 3. Sizing Dinámico de Posiciones
│      └── <100€: 3 slots | 100-300€: 5 slots | >300€: 7-10 slots
│
├── 4. Escaneo de Ciclo (por cada símbolo):
│      ├── Veto Macro/Global: ¿El entorno mundial permite operar?
│      ├── Veto Técnico: ¿Hay volatilidad o es mercado lateral?
│      ├── Veto Histórico: ¿Esta moneda es ganadora en este contexto?
│      └── Ejecución: Compra, Venta o Rotación
│
└── 5. Log Equity: PnL Real vs Saldo inicial capturado en Crypto.com
```

---

## Nuevas Funcionalidades v6.1

### 🌍 Radar de Mercados Globales
Integración con **Alpha Vantage** para tener "ojos" en la economía real. El bot sabe si el petróleo sube por una guerra o si el dólar se fortalece, ajustando su agresividad en cripto de forma automática.

### 📈 Position Sizing Dinámico
El bot ya no usa un límite de posiciones fijo. Ahora escala contigo: a medida que tu balance crece, el bot desbloquea más "slots" de trading (de 3 hasta 10 posiciones), optimizando el pago de comisiones y la diversificación.

### 🧠 Asistente Macroeconómico
El chat de IA ahora tiene acceso a los datos de mercados globales. Puedes preguntarle sobre la situación del petróleo, el dólar o la bolsa, y te dará consejos de trading basados en el contexto mundial actual.

---

## Instalación y Configuración

### Prerrequisitos
- Python 3.11+
- Claves API: Crypto.com, Google Gemini, Groq y **Alpha Vantage**.

### Configuración rápida
1. Instala dependencias: `pip install -r requirements.txt`
2. Configura tu `.env` (añade `ALPHA_VANTAGE_API_KEY`).
3. Lanza la UI (`app.py`) y el Daemon (`bot_daemon.py`).

---

<div align="center">

**INVERSORIA v6.1** · Hecho con Python · Licencia MIT

</div>
