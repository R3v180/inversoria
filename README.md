<div align="center">

<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
<img src="https://img.shields.io/badge/Google_Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white"/>
<img src="https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white"/>
<img src="https://img.shields.io/badge/Crypto.com-002D74?style=for-the-badge&logo=cryptocom&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white"/>

# 🏛️ INVERSORIA
### Autonomous Trading Agent with Hybrid AI — v6.1 [GLOBAL MACRO & DYNAMIC UPGRADE]

*Fusion of institutional technical analysis, generative AI, 2-year historical memory, global market analysis, and dynamic capital management.*

[English Version](#english) | [Versión en Español](#español)

</div>

---

<a name="english"></a>

## 🇺🇸 English Version

### What is Inversoria?
Inversoria is an **autonomous trading bot** for Crypto.com that operates continuously, making decisions based on a five-layer intelligence pipeline:

1. **Global Intelligence (Alpha Vantage)** — Monitors the Dollar (DXY), Oil (WTI), and Stock Market (SP500) to detect systemic risks.
2. **Crypto Macro Filter** — Analyzes BTC dominance and market regime (Risk-On/Off).
3. **Historical Memory (Backtest Engine)** — Consults the real Win Rate of the last 2 years for each coin before deciding.
4. **Hybrid AI Engine** — Gemini and Groq analyze technical structure, news, and sentiment in real-time.
5. **Dynamic Capital Management** — Automatically adjusts the number of positions based on the account's total balance.

The Bloomberg-style UI in Streamlit allows you to monitor equity, view interactive confluence charts, and chat with the bot to understand its decisions.

---

### System Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                         INVERSORIA                              │
│                                                                 │
│   ┌──────────────┐    SQLite (IPC)    ┌────────────────────┐   │
│   │   app.py     │◄──────────────────►│   bot_daemon.py    │   │
│   │  Streamlit   │                   │   Autonomous Loop  │   │
│   │     UI       │                   │   every 60 sec     │   │
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

### v6.1 Decision Flow (Every 60 Seconds)
```
bot_daemon.py
│
├── 1. Global Macro Update (Every 6h)
│      └── Consult Alpha Vantage: DXY, SP500, WTI, GLD
│          └── Automatic Veto if market panic or strong Dollar is detected
│
├── 2. Automatic Weekly Backtest (Every 7 days)
│      └── 2-year simulation → Generates "Historical Win Rate" in SQLite
│
├── 3. Dynamic Position Sizing
│      └── <100€: 3 slots | 100-300€: 5 slots | >300€: 7-10 slots
│
├── 4. Cycle Scan (For each symbol):
│      ├── Global Macro Veto: Does the global environment allow trading?
│      ├── Technical Filter: Is there volatility (ADX) or is it a sideways market?
│      ├── Historical Context: Is this coin a winner in this context?
│      ├── Hybrid AI: Final technical confluence analysis + News
│      └── Execution: Buy, Sell, or Rotation
│
└── 5. Log Equity: Real PnL calculation vs Real Initial Balance captured
```

---

### New v6.1 Features

#### 🌍 Global Markets Radar
Integration with **Alpha Vantage** to have "eyes" on the real economy. The bot knows if oil prices rise due to geopolitical tension or if the dollar strengthens, automatically adjusting its crypto aggressiveness.

#### 📈 Dynamic Position Sizing
The bot no longer uses a fixed position limit. It scales with you: as your balance grows, the bot unlocks more trading "slots" (from 3 to 10 positions), optimizing fees and diversification.

#### 🧠 Macroeconomic Assistant
The AI chat now has access to global market data. You can ask about the situation of oil, the dollar, or the stock market, and it will provide trading advice based on the current world context.

---

### 🚀 Step-by-Step Installation

#### 1. Prerequisites
- **Python 3.11+** installed.
- Active **Crypto.com Exchange** account (with API permissions enabled).
- API keys for LLMs (**Gemini** at aistudio.google.com and **Groq** at console.groq.com).
- **Alpha Vantage API Key** (Free at alphavantage.co).

#### 2. Environment Setup
```bash
# Clone repository
git clone https://github.com/R3v180/inversoria
cd inversoria

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### 3. Credentials Configuration (.env)
Copy the example file and fill in your keys:
```bash
cp .env.example .env
```

#### 4. Launching the Institutional Terminals
Inversoria runs via two independent processes:

**Terminal A (Visual Interface):**
```bash
python -m streamlit run app.py
```

**Terminal B (Bot Brain):**
```bash
python bot_daemon.py
```

---

### 🛠️ Control Panel (Hot-Reload)
Change your strategy in real-time via the **Settings** panel in the UI:
- **Risk Limit**: Capital percentage per trade.
- **Simulation Mode**: Enable/Disable real money trading.
- **AI Interval**: Frequency of deep analysis.
- **Watchlist**: Coins for the bot to monitor.

---

<a name="español"></a>

## 🇪🇸 Versión en Español

### ¿Qué es Inversoria?
Inversoria es un **bot de trading autónomo** para Crypto.com que opera de forma continua tomando decisiones basadas en un pipeline de cinco capas de inteligencia:

1. **Inteligencia Global (Alpha Vantage)** — Monitoriza el Dólar (DXY), Petróleo (WTI) y Bolsa (SP500) para detectar riesgos sistémicos.
2. **Filtro Macro Crypto** — Analiza dominancia de BTC y régimen de mercado (Risk-On/Off).
3. **Memoria Histórica (Backtest Engine)** — Consulta el Win Rate real de los últimos 2 años para cada moneda antes de decidir.
4. **Motor de IA Híbrida** — Gemini y Groq analizan la estructura técnica, noticias y sentimiento en tiempo real.
5. **Gestión Dinámica de Capital** — Ajusta automáticamente el número de posiciones según el balance total de la cuenta.

La UI tipo Bloomberg en Streamlit permite monitorizar el patrimonio, ver gráficos de confluencia y chatear con el bot para entender sus decisiones.

---

### Arquitectura del Sistema
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

### Flujo de Decisión v6.1 (Cada 60 Segundos)
```
bot_daemon.py
│
├── 1. Actualización Macro Global (Cada 6h)
│      └── Consulta Alpha Vantage: DXY, SP500, WTI, GLD
│          └── Veto automático si hay pánico en bolsa o dólar fuerte
│
├── 2. Backtest Semanal Automático (Cada 7 días)
│      └── Simulación de 2 años → Genera "Win Rate Histórico" en SQLite
│
├── 3. Sizing Dinámico de Posiciones
│      └── <100€: 3 slots | 100-300€: 5 slots | >300€: 7-10 slots
│
├── 4. Escaneo de Ciclo (Por cada símbolo):
│      ├── Veto Macro Global: ¿El entorno mundial permite operar?
│      ├── Filtro Técnico: ¿Hay volatilidad (ADX) o es mercado lateral?
│      ├── Contexto Histórico: ¿Esta moneda es ganadora en este contexto?
│      ├── IA Híbrida: Análisis final de confluencia técnica + Noticias
│      └── Ejecución: Compra, Venta o Rotación
│
└── 5. Log Equity: Cálculo de PnL Real vs Saldo Inicial Real capturado
```

---

### Nuevas Funcionalidades v6.1

#### 🌍 Radar de Mercados Globales
Integración con **Alpha Vantage** para tener "ojos" en la economía real. El bot sabe si el petróleo sube por tensiones geopolíticas o si el dólar se fortalece, ajustando su agresividad automáticamente.

#### 📈 Position Sizing Dinámico
El bot ya no usa un límite de posiciones fijo. Escala contigo: a medida que tu balance crece, el bot desbloquea más "slots" de trading (de 3 hasta 10 posiciones), optimizando comisiones y diversificación.

#### 🧠 Asistente Macroeconómico
El chat de IA ahora tiene acceso a datos mundiales. Puedes preguntarle sobre el petróleo, el dólar o la bolsa, y te dará consejos basados en el contexto global actual.

---

### 🚀 Instalación Paso a Paso

#### 1. Prerrequisitos
- **Python 3.11+** instalado.
- Cuenta en **Crypto.com Exchange** (con APIs habilitadas).
- Claves API de **Gemini** (aistudio.google.com) y **Groq** (console.groq.com).
- Clave de **Alpha Vantage** (gratis en alphavantage.co).

#### 2. Preparar el Entorno
```bash
# Clonar repositorio
git clone https://github.com/R3v180/inversoria
cd inversoria

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

#### 3. Configurar Credenciales (.env)
Copia el archivo de ejemplo y rellena tus claves:
```bash
cp .env.example .env
```

#### 4. Lanzar las Terminales
Inversoria funciona mediante dos procesos independientes:

**Terminal A (Interfaz Visual):**
```bash
python -m streamlit run app.py
```

**Terminal B (Cerebro del Bot):**
```bash
python bot_daemon.py
```

---

### 🛠️ Panel de Control (Hot-Reload)
Cambia tu estrategia en tiempo real desde el panel de **Settings** en la UI:
- **Límite de Riesgo**: Porcentaje de capital por trade.
- **Modo Simulación**: Activa/Desactiva el trading real.
- **Intervalo IA**: Frecuencia de los análisis profundos.
- **Watchlist**: Monedas que el bot debe vigilar.

---

## 🛡️ Risk Management / Gestión de Riesgo

| Parameter / Parámetro | Function / Función |
|---|---|
| `STOP_LOSS_PCT` | Automatic loss cut / Corte de pérdidas automático. |
| `TRAILING_STOP` | Dynamic profit protection / Asegura beneficios. |
| `ROTATION` | Portfolio rotation logic / Lógica de rotación de cartera. |
| `DYNAMIC_SLOTS` | Dynamic position scaling (v6.1) / Límite dinámico. |

---

<div align="center">

**INVERSORIA v6.1** · MIT License

</div>
