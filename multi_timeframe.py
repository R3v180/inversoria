"""
multi_timeframe.py — Análisis multi-timeframe para confirmación de señales
Usa CCXT (ya disponible) para descargar velas de 1D y 4H además de las 15M.
Principio: la señal de entrada solo es válida si NO contradice la tendencia mayor.
"""
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
import config


def _safe_float(val, default=0.0):
    """Evita TypeError al comparar float con None/NaN (CCXT + pandas_ta a veces devuelven huecos)."""
    if val is None:
        return default
    try:
        f = float(val)
        if f != f or np.isinf(f):  # NaN o inf
            return default
        return f
    except (TypeError, ValueError):
        return default


class MultiTimeframeAnalyzer:
    """
    Analiza el mismo activo en tres timeframes:
    - 1D (largo plazo): ¿cuál es la tendencia macro del activo?
    - 4H (medio plazo): ¿en qué fase del ciclo estamos?
    - 15M (corto plazo): ¿hay señal de entrada ahora? (ya lo hace el bot)

    Principio de confluencia: BUY solo si 1D y 4H no están en BEAR.
    """

    TIMEFRAMES = ['1d', '4h']
    CANDLES_NEEDED = {'1d': 200, '4h': 200, '15m': 200}

    def __init__(self, exchange_helper):
        self.exchange = exchange_helper
        self._cache = {}
        self.CACHE_TTL = {'1d': 43200, '4h': 14400, '15m': 900}  # 12h, 4h y 15m

    def get_timeframe_analysis(self, symbol: str, timeframe: str) -> dict:
        """Descarga y analiza un timeframe específico para un símbolo."""
        cache_key = f"{symbol}_{timeframe}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached['ts'] < self.CACHE_TTL[timeframe]:
            return cached['data']

        try:
            limit = self.CANDLES_NEEDED[timeframe]
            ohlcv = self.exchange.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            if not ohlcv or len(ohlcv) < 50:
                return {'error': 'Datos insuficientes'}

            df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)

            # Indicadores (usando solo velas cerradas: iloc[:-1])
            df_closed = df.iloc[:-1].copy()

            df_closed['rsi'] = ta.rsi(df_closed['close'], length=14)
            df_closed['ema50'] = ta.ema(df_closed['close'], length=50)
            df_closed['ema200'] = ta.ema(df_closed['close'], length=200)
            df_closed['atr'] = ta.atr(df_closed['high'], df_closed['low'], df_closed['close'], length=14)

            adx_df = ta.adx(df_closed['high'], df_closed['low'], df_closed['close'], length=14)
            if adx_df is not None and not adx_df.empty and 'ADX_14' in adx_df.columns:
                df_closed['adx'] = adx_df['ADX_14']
            else:
                df_closed['adx'] = 0.0

            last = df_closed.iloc[-1]

            ema50 = _safe_float(last.get('ema50'), 0.0)
            ema200 = _safe_float(last.get('ema200'), 0.0)
            rsi_raw = _safe_float(last.get('rsi'), 50.0)
            adx_raw = _safe_float(last.get('adx'), 0.0)

            # Análisis de la vela actual (sin comparar float con None/NaN)
            if ema50 <= 0 or ema200 <= 0:
                trend = 'BULL'
            else:
                trend = 'BULL' if ema50 > ema200 else 'BEAR'
            rsi = round(rsi_raw, 1)
            adx = round(adx_raw, 1)

            # Momentum: ¿está el precio acelerando o desacelerando?
            recent_closes = df_closed['close'].tail(5)
            momentum = 'ACCELERATING' if recent_closes.iloc[-1] > recent_closes.mean() else 'DECELERATING'
            current_price = last['close']
            divergence = 'NONE'
            try:
                prev = df_closed.iloc[-10]
                prev_close = _safe_float(prev.get('close'), current_price)
                prev_rsi = _safe_float(prev.get('rsi'), rsi)
                if current_price > prev_close and rsi < prev_rsi - 3:
                    divergence = 'BEARISH_RSI'
                elif current_price < prev_close and rsi > prev_rsi + 3:
                    divergence = 'BULLISH_RSI'
            except Exception:
                divergence = 'NONE'

            # Soporte y resistencia dinámicos (últimos 20 períodos)
            recent_20 = df_closed.tail(20)
            dynamic_support = recent_20['low'].min()
            dynamic_resistance = recent_20['high'].max()
            position_in_range = (current_price - dynamic_support) / (dynamic_resistance - dynamic_support) if dynamic_resistance != dynamic_support else 0.5

            atr_safe = _safe_float(last.get('atr'), 0.0)

            result = {
                'timeframe': timeframe,
                'trend': trend,
                'rsi': rsi,
                'adx': adx,
                'ema50': round(ema50, 6),
                'ema200': round(ema200, 6),
                'atr': round(atr_safe, 6),
                'momentum': momentum,
                'dynamic_support': round(dynamic_support, 6),
                'dynamic_resistance': round(dynamic_resistance, 6),
                'position_in_range': round(position_in_range, 2),  # 0=soporte, 1=resistencia
                'regime': self._classify_regime(trend, adx, rsi),
                'divergence': divergence,
            }

            self._cache[cache_key] = {'data': result, 'ts': time.time()}
            return result

        except Exception as e:
            print(f"[MTF] Error analizando {symbol} {timeframe}: {e}")
            return {'error': str(e)}

    def _classify_regime(self, trend: str, adx: float, rsi: float) -> str:
        adx = _safe_float(adx, 0.0)
        rsi = _safe_float(rsi, 50.0)
        if adx > 30 and trend == 'BULL':
            return 'STRONG_UPTREND'
        elif adx > 30 and trend == 'BEAR':
            return 'STRONG_DOWNTREND'
        elif adx > 20 and trend == 'BULL':
            return 'MODERATE_UPTREND'
        elif adx > 20 and trend == 'BEAR':
            return 'MODERATE_DOWNTREND'
        elif adx < 15:
            return 'CONSOLIDATION'
        else:
            return 'RANGING'

    def get_full_mtf_analysis(self, symbol: str) -> dict:
        """
        Analiza el símbolo en todos los timeframes y devuelve:
        - Análisis por timeframe
        - Señal de confluencia (¿los timeframes están alineados?)
        - Recomendación de posicionamiento
        - Texto para el prompt de la IA
        """
        analyses = {}
        timeframes = list(self.TIMEFRAMES)
        if bool(getattr(config, 'MTF_INCLUDE_15M', True)):
            timeframes.append('15m')
        for tf in timeframes:
            analyses[tf] = self.get_timeframe_analysis(symbol, tf)
            time.sleep(0.3)  # Pequeña pausa entre llamadas

        # ─── Lógica de confluencia ───
        tf_1d = analyses.get('1d', {})
        tf_4h = analyses.get('4h', {})
        tf_15m = analyses.get('15m', {})

        daily_trend = tf_1d.get('trend', 'BULL')
        h4_trend = tf_4h.get('trend', 'BULL')
        m15_trend = tf_15m.get('trend', 'BULL')
        daily_regime = tf_1d.get('regime', 'RANGING')
        h4_regime = tf_4h.get('regime', 'RANGING')

        # Niveles de confluencia
        if daily_trend == 'BULL' and h4_trend == 'BULL':
            confluence = 'STRONG_BUY_BIAS'
            confluence_score = 0.85
        elif daily_trend == 'BULL' and h4_trend == 'BEAR':
            confluence = 'PULLBACK'  # Corrección en tendencia alcista mayor
            confluence_score = 0.55  # Puede ser oportunidad de compra
        elif daily_trend == 'BEAR' and h4_trend == 'BULL':
            confluence = 'COUNTER_TREND'  # Rebote en tendencia bajista mayor
            confluence_score = 0.30  # Peligroso
        else:
            confluence = 'STRONG_SELL_BIAS'
            confluence_score = 0.10

        divergences = [
            item.get('divergence')
            for item in (tf_1d, tf_4h, tf_15m)
            if item.get('divergence') and item.get('divergence') != 'NONE'
        ]
        if 'BEARISH_RSI' in divergences:
            confluence_score = max(0.05, confluence_score - float(getattr(config, 'MTF_DIVERGENCE_PENALTY', 0.15) or 0.15))
        if tf_15m and m15_trend == 'BEAR' and confluence_score > 0.25:
            confluence_score = max(0.25, confluence_score - 0.10)

        # ─── Recomendación de estrategia por contexto MTF ───
        adx_4h = _safe_float(tf_4h.get('adx'), 0.0)
        rsi_4h = _safe_float(tf_4h.get('rsi'), 50.0)
        pos_4h = _safe_float(tf_4h.get('position_in_range'), 0.5)

        if confluence == 'STRONG_BUY_BIAS' and adx_4h > 25:
            recommended_strategy = 'TREND_FOLLOWING'
        elif confluence == 'PULLBACK' and rsi_4h < 45:
            recommended_strategy = 'MEAN_REVERSION'  # Comprar el pullback
        elif confluence == 'STRONG_BUY_BIAS' and pos_4h > 0.7:
            recommended_strategy = 'BREAKOUT'  # Cerca de resistencia → esperar ruptura
        else:
            recommended_strategy = 'MOMENTUM'

        # ─── Texto para el prompt ───
        mtf_text = f"""
=== ANÁLISIS MULTI-TIMEFRAME ===
1D  → Tendencia: {daily_trend} | Régimen: {daily_regime} | RSI: {tf_1d.get('rsi', 'N/A')} | ADX: {tf_1d.get('adx', 'N/A')}
4H  → Tendencia: {h4_trend} | Régimen: {h4_regime} | RSI: {tf_4h.get('rsi', 'N/A')} | ADX: {tf_4h.get('adx', 'N/A')}
15m → Tendencia: {tf_15m.get('trend', 'N/A')} | Régimen: {tf_15m.get('regime', 'N/A')} | RSI: {tf_15m.get('rsi', 'N/A')} | ADX: {tf_15m.get('adx', 'N/A')}
Confluencia: {confluence} (score: {confluence_score:.0%})
Divergencias: {", ".join(divergences) if divergences else "Ninguna"}
Posición en rango 4H: {tf_4h.get('position_in_range', 0.5):.0%} (0=soporte, 100%=resistencia)
Estrategia sugerida por MTF: {recommended_strategy}
""".strip()

        return {
            'timeframes': analyses,
            'confluence': confluence,
            'confluence_score': confluence_score,
            'recommended_strategy': recommended_strategy,
            'daily_trend': daily_trend,
            'h4_trend': h4_trend,
            'm15_trend': m15_trend,
            'divergences': divergences,
            'allow_long': confluence not in ['STRONG_SELL_BIAS', 'COUNTER_TREND'],
            'mtf_text': mtf_text
        }
