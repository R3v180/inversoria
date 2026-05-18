import pandas as pd
import pandas_ta as ta

class TradingLogic:
    def __init__(self):
        pass

    def calculate_indicators(self, ohlcv_data):
        if not ohlcv_data or len(ohlcv_data) < 200:
            return None
        
        df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        
        # Repainting Fix
        df_closed = df.iloc[:-1].copy()
        
        if len(df_closed) < 200:
            return None

        df_closed['RSI_14'] = ta.rsi(df_closed['close'], length=14)
        df_closed['EMA_50'] = ta.ema(df_closed['close'], length=50)
        df_closed['EMA_200'] = ta.ema(df_closed['close'], length=200)
        df_closed['ATR_14'] = ta.atr(df_closed['high'], df_closed['low'], df_closed['close'], length=14)
        
        adx_df = ta.adx(df_closed['high'], df_closed['low'], df_closed['close'], length=14)
        if adx_df is not None and not adx_df.empty:
            df_closed['ADX_14'] = adx_df['ADX_14']
        else:
            df_closed['ADX_14'] = 0
        
        if df_closed.empty or df_closed['EMA_200'].isna().all():
            return None
            
        ema50 = df_closed['EMA_50'].iloc[-1]
        ema200 = df_closed['EMA_200'].iloc[-1]
        
        return {
            'rsi': df_closed['RSI_14'].iloc[-1],
            'ema50': ema50,
            'ema200': ema200,
            'atr': df_closed['ATR_14'].iloc[-1],
            'adx': df_closed['ADX_14'].iloc[-1],
            'trend': "BULL" if ema50 > ema200 else "BEAR"
        }

    def check_sell_conditions(self, symbol, current_price, position, ai_decision):
        """
        Condiciones de venta ADAPTATIVAS según el régimen de mercado detectado.
        Los parámetros de stop y trailing cambian dinámicamente según el contexto.
        """
        import config
        import json

        entry_price = position.get('entry_price', 0)
        highest_price = position.get('highest_price', entry_price)
        regime = ai_decision.get('regime', 'RANGING') if ai_decision else 'RANGING'
        strategy = ai_decision.get('best_strategy', 'TREND_FOLLOWING') if ai_decision else 'TREND_FOLLOWING'
        atr = position.get('atr', 0) or 0  # ATR en el momento de la entrada (si disponible)

        # ─── Parámetros adaptativos por régimen ───
        # En tendencia fuerte: stops más holgados para dejar correr ganancias
        # En lateral: stops ajustados, tomar ganancias rápido
        # En alta volatilidad: stops amplios pero activación de trailing antes

        regime_params = {
            'TRENDING_UP': {
                'sl_pct': config.STOP_LOSS_PCT,          # Stop normal
                'trailing_activation': 0.04,              # Activar trailing a +4%
                'trailing_distance': 0.025,               # Trailing de 2.5% desde máximo
            },
            'RANGING': {
                'sl_pct': config.STOP_LOSS_PCT * 0.7,    # Stop más ajustado en lateral
                'trailing_activation': 0.025,             # Activar trailing antes a +2.5%
                'trailing_distance': 0.012,               # Trailing más ajustado 1.2%
            },
            'HIGH_VOLATILITY': {
                'sl_pct': config.STOP_LOSS_PCT * 1.3,    # Stop más amplio por volatilidad
                'trailing_activation': 0.06,              # Esperar +6% antes de trailing
                'trailing_distance': 0.030,               # Trailing más holgado 3%
            },
            'TRENDING_DOWN': {
                'sl_pct': config.STOP_LOSS_PCT * 0.8,    # Stop más ajustado: salir rápido
                'trailing_activation': 0.02,
                'trailing_distance': 0.010,
            },
        }

        params = regime_params.get(regime, regime_params['RANGING'])
        aggressive = bool(getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False))
        if aggressive:
            params = dict(params)
            params['trailing_activation'] = params['trailing_activation'] * 0.75
            params['trailing_distance'] = params['trailing_distance'] * 0.85

        # ─── 1. Stop Loss adaptativo ───
        stop_loss_price = entry_price * (1 - params['sl_pct'])
        profit_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price else 0.0
        if bool(getattr(config, 'BREAK_EVEN_ENABLED', False)):
            activation_pct = float(getattr(config, 'ADD_MIN_PROFIT_PCT', 2.5) or 2.5)
            fee_buffer_pct = max(0.05, float(config.get_setting('MIN_PROFIT_NET', 1.0, float)) * 0.20)
            if profit_pct >= activation_pct:
                stop_loss_price = max(stop_loss_price, entry_price * (1 + fee_buffer_pct / 100))
        if current_price <= stop_loss_price:
            return {
                'should_sell': True,
                'reason': f"STOP LOSS [{regime}] ({params['sl_pct']*100:.1f}%)"
            }

        # ─── 2. Trailing Stop adaptativo ───
        trailing_activation = entry_price * (1 + params['trailing_activation'])
        if current_price >= trailing_activation:
            trailing_stop = highest_price * (1 - params['trailing_distance'])
            if current_price <= trailing_stop:
                profit_locked = ((highest_price - entry_price) / entry_price) * 100
                return {
                    'should_sell': True,
                    'reason': f"TRAILING STOP [{strategy}] | Máx asegurado: +{profit_locked:.1f}%"
                }

        # ─── 3. Señal SELL de la IA con confianza suficiente ───
        if ai_decision and ai_decision.get('action') == 'SELL':
            confidence = ai_decision.get('confidence', 0)
            # En tendencia fuerte necesitamos más convicción para salir antes de tiempo
            if bool(getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False)):
                sell_threshold = 0.62 if regime == 'TRENDING_UP' else 0.55
            else:
                sell_threshold = 0.75 if regime == 'TRENDING_UP' else 0.65
            if confidence >= sell_threshold:
                return {
                    'should_sell': True,
                    'reason': f"IA SELL [{ai_decision.get('provider', 'IA')}] conf:{confidence:.0%}"
                }

        min_profit_pct = float(config.get_setting('MIN_PROFIT_NET', 1.0, float))
        extra = {}
        try:
            extra = json.loads(position.get('extra_data') or '{}')
        except Exception:
            extra = {}
        if (
            bool(getattr(config, 'PARTIAL_TAKE_PROFIT_ENABLED', False))
            and not extra.get('partial_take_profit_done')
            and profit_pct >= min_profit_pct
        ):
            fraction = max(0.05, min(1.0, float(getattr(config, 'PARTIAL_TAKE_PROFIT_PCT', 50.0) or 50.0) / 100.0))
            return {
                'should_sell': True,
                'reason': f"PARTIAL TAKE PROFIT [{regime}] (+{profit_pct:.2f}% >= {min_profit_pct:.2f}%)",
                'sell_fraction': fraction,
            }
        if aggressive and profit_pct >= min_profit_pct:
            return {
                'should_sell': True,
                'reason': f"TAKE PROFIT [{regime}] (+{profit_pct:.2f}% >= {min_profit_pct:.2f}%)"
            }

        # ─── 4. Cambio de régimen macro (si la IA detecta un giro) ───
        if regime == 'TRENDING_DOWN' and ai_decision:
            profit_pct = ((current_price - entry_price) / entry_price) * 100
            # Si estamos en pérdidas y el régimen giró a bajista → salir
            if profit_pct < -1.0:
                return {
                    'should_sell': True,
                    'reason': f"REGIME CHANGE: {regime} con P&L {profit_pct:.1f}%"
                }

        return {'should_sell': False, 'reason': ''}
