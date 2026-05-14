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

[English](#english) | [Español](#español)

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

### 🚀 Step-by-Step Installation

#### 1. Prerequisites
- **Python 3.11+** installed.
- Active **Crypto.com Exchange** account (with API permissions enabled).
- API keys for LLMs (Gemini, Groq).
- **Alpha Vantage API Key** (Free at alphavantage.co).

#### 2. Setup
```bash
git clone https://github.com/R3v180/inversoria
cd inversoria
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

#### 3. Execution
**Terminal A (UI):** `python -m streamlit run app.py`
**Terminal B (Daemon):** `python bot_daemon.py`

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

### 🚀 Instalación Paso a Paso

#### 1. Prerrequisitos
- **Python 3.11+** instalado.
- Cuenta en **Crypto.com Exchange**.
- Claves API de **Gemini** y **Groq**.
- Clave de **Alpha Vantage** (gratis en alphavantage.co).

#### 2. Preparación
```bash
git clone https://github.com/R3v180/inversoria
cd inversoria
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

#### 3. Ejecución
**Terminal A (Interfaz):** `python -m streamlit run app.py`
**Terminal B (Cerebro):** `python bot_daemon.py`

---

## 🛡️ Risk Management / Gestión de Riesgo

| Parameter / Parámetro | Function / Función |
|---|---|
| `STOP_LOSS_PCT` | Automatic loss cut per trade / Corte de pérdidas automático. |
| `TRAILING_STOP` | Dynamic profit protection / Asegura beneficios dinámicamente. |
| `ROTATION` | Portfolio rotation logic / Lógica de rotación de cartera. |
| `DYNAMIC_SLOTS` | Dynamic position scaling (v6.1) / Límite dinámico (v6.1). |

---

<div align="center">

**INVERSORIA v6.1** · MIT License

</div>
