# 🏛️ IVERSORIA AI - Trading Engine v4.0

**IVERSORIA AI** es un motor de trading autónomo de grado institucional diseñado para operar en el mercado de criptomonedas (Crypto.com) utilizando inteligencia artificial de vanguardia y análisis técnico avanzado.

![Dashboard Preview](https://github.com/R3v180/inversoria/raw/main/preview.png) *(Sube la foto que me pasaste aquí)*

## 🚀 Características Principales (v4.0)

### 1. 🧠 Cerebro Híbrido (IA de Última Generación)
- **Análisis de Sentimiento Dinámico**: Utiliza modelos **Gemini 1.5 Flash/Pro** y **Groq (Llama 3)** para interpretar el contexto del mercado.
- **Resiliencia Híbrida**: Sistema de fallback automático ante fallos de API para garantizar que el bot nunca deje de operar.
- **Prompts Personalizables**: Control total sobre el "razonamiento" de la IA desde el panel de ajustes.

### 2. 🛰️ Radar Dinámico & Rotación Inteligente
- **Watchlist Autónoma**: Escanea las monedas con mayor volumen de mercado cada 12 horas para estar siempre donde está la acción.
- **Rotación de Capital**: Capacidad de sacrificar posiciones de baja confianza para entrar en nuevas oportunidades de alto potencial.
- **Hot-Reload**: Ajustes de parámetros en tiempo real sin necesidad de reiniciar el bot.

### 3. 🛡️ Gestión de Riesgo Institucional
- **Trailing Stop Loss Dinámico**: Protege tus beneficios siguiendo el máximo histórico de cada trade.
- **Stop Loss basado en ATR**: Ajusta los límites de pérdida según la volatilidad real del activo.
- **Filtros Técnicos**: Validación mediante RSI, EMAs (50/200) y ADX antes de cualquier ejecución.

### 4. 💻 Terminal de Mando "Command Center"
- **Dashboard Dual**: Visualización simultánea de la Curva de Patrimonio y Gráficos de Mercado en tiempo real.
- **Radar de Oportunidades**: Panel de "Top Movers" integrado para detectar tendencias al instante.
- **Modo Vigilancia**: Sistema de auto-refresco configurable para monitoreo remoto.

## 🛠️ Stack Tecnológico
- **Lenguaje**: Python 3.10+
- **Interfaz**: Streamlit (Premium Dark Mode)
- **Conectividad**: CCXT (Crypto.com Exchange)
- **Base de Datos**: SQLite (Persistencia de trades y equity)
- **Gráficos**: Plotly / Candlestick Charts

## ⚙️ Configuración Rápida
1. Clona el repositorio.
2. Configura tus llaves API en el archivo `.env`.
3. Instala las dependencias: `pip install -r requirements.txt`.
4. Lanza la interfaz: `streamlit run app.py`.
5. Inicia el motor: `python bot_daemon.py`.

---
**Aviso Legal**: *Este software es una herramienta de automatización. El trading de criptomonedas conlleva un riesgo significativo. Úsalo bajo tu propia responsabilidad.*
