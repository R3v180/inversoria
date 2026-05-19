import pandas as pd
import pandas_ta as ta
import time

class TradingLogic:
    def __init__(self):
        pass

    def calculate_indicators(self, ohlcv_data):
        if not ohlcv_data or len(ohlcv_data) < 200:
            return None
        
        df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['open'] = pd.to_numeric(df['open'], errors='coerce')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        
        # Repainting Fix
        df_closed = df.iloc[:-1].copy()
        
        if len(df_closed) < 200:
            return None

        df_closed['RSI_14'] = ta.rsi(df_closed['close'], length=14)
        df_closed['EMA_21'] = ta.ema(df_closed['close'], length=21)
        df_closed['EMA_50'] = ta.ema(df_closed['close'], length=50)
        df_closed['EMA_200'] = ta.ema(df_closed['close'], length=200)
        df_closed['ATR_14'] = ta.atr(df_closed['high'], df_closed['low'], df_closed['close'], length=14)
        df_closed['VOLUME_SMA_20'] = ta.sma(df_closed['volume'], length=20)

        macd_df = ta.macd(df_closed['close'], fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            for col in macd_df.columns:
                df_closed[col] = macd_df[col]

        bb_df = ta.bbands(df_closed['close'], length=20, std=2)
        if bb_df is not None and not bb_df.empty:
            for col in bb_df.columns:
                df_closed[col] = bb_df[col]

        stochrsi_df = ta.stochrsi(df_closed['close'], length=14)
        if stochrsi_df is not None and not stochrsi_df.empty:
            for col in stochrsi_df.columns:
                df_closed[col] = stochrsi_df[col]

        obv = ta.obv(df_closed['close'], df_closed['volume'])
        if obv is not None:
            df_closed['OBV'] = obv
        
        adx_df = ta.adx(df_closed['high'], df_closed['low'], df_closed['close'], length=14)
        if adx_df is not None and not adx_df.empty:
            df_closed['ADX_14'] = adx_df['ADX_14']
        else:
            df_closed['ADX_14'] = 0
        
        if df_closed.empty or df_closed['EMA_200'].isna().all():
            return None
            
        ema50 = df_closed['EMA_50'].iloc[-1]
        ema200 = df_closed['EMA_200'].iloc[-1]
        
        def latest(col, default=0.0):
            try:
                value = df_closed[col].iloc[-1]
                if pd.isna(value):
                    return default
                return float(value)
            except Exception:
                return default

        volume_sma = latest('VOLUME_SMA_20', 0.0)
        volume_ratio = latest('volume', 0.0) / volume_sma if volume_sma > 0 else 1.0
        obv_now = latest('OBV', 0.0)
        try:
            obv_prev = float(df_closed['OBV'].iloc[-6])
        except Exception:
            obv_prev = obv_now
        obv_slope = 0.0 if obv_prev == 0 else (obv_now - obv_prev) / abs(obv_prev)

        return {
            'rsi': df_closed['RSI_14'].iloc[-1],
            'ema21': latest('EMA_21', ema50),
            'ema50': ema50,
            'ema200': ema200,
            'atr': df_closed['ATR_14'].iloc[-1],
            'adx': df_closed['ADX_14'].iloc[-1],
            'volume_ratio': volume_ratio,
            'macd': latest('MACD_12_26_9', 0.0),
            'macd_signal': latest('MACDs_12_26_9', 0.0),
            'macd_hist': latest('MACDh_12_26_9', 0.0),
            'bb_percent': latest('BBP_20_2.0', 0.5),
            'bb_width': latest('BBB_20_2.0', 0.0),
            'stochrsi_k': latest('STOCHRSIk_14_14_3_3', 50.0),
            'stochrsi_d': latest('STOCHRSId_14_14_3_3', 50.0),
            'obv_slope': obv_slope,
            'trend': "BULL" if ema50 > ema200 else "BEAR"
        }

    def protective_levels(self, entry_price, highest_price, atr, regime='RANGING', aggressive=False):
        import config

        entry_price = float(entry_price or 0)
        highest_price = float(highest_price or entry_price or 0)
        atr = float(atr or 0)

        regime_params = {
            'TRENDING_UP': {'sl_pct': config.STOP_LOSS_PCT, 'trailing_activation': 0.04, 'trailing_distance': 0.025},
            'RANGING': {'sl_pct': config.STOP_LOSS_PCT * 0.7, 'trailing_activation': 0.025, 'trailing_distance': 0.012},
            'HIGH_VOLATILITY': {'sl_pct': config.STOP_LOSS_PCT * 1.3, 'trailing_activation': 0.06, 'trailing_distance': 0.030},
            'TRENDING_DOWN': {'sl_pct': config.STOP_LOSS_PCT * 0.8, 'trailing_activation': 0.02, 'trailing_distance': 0.010},
        }
        params = dict(regime_params.get(regime, regime_params['RANGING']))
        if aggressive:
            params['trailing_activation'] *= 0.75
            params['trailing_distance'] *= 0.85

        pct_stop = entry_price * (1 - params['sl_pct']) if entry_price > 0 else 0
        atr_stop = 0
        if bool(getattr(config, 'ATR_STOP_ENABLED', True)) and atr > 0 and entry_price > 0:
            atr_stop = entry_price - (atr * float(getattr(config, 'STOP_LOSS_ATR_MULT', 1.5) or 1.5))
        stop_loss_price = max(pct_stop, atr_stop) if atr_stop > 0 else pct_stop

        activation_pct = float(getattr(config, 'TRAILING_ACTIVATION_PCT', 2.0) or 2.0) / 100.0
        trailing_activation = entry_price * (1 + activation_pct) if entry_price > 0 else 0
        trailing_stop = 0
        if highest_price >= trailing_activation and entry_price > 0:
            if bool(getattr(config, 'ATR_TRAILING_ENABLED', True)) and atr > 0:
                trailing_stop = highest_price - (atr * float(getattr(config, 'TRAILING_ATR_MULT', 2.5) or 2.5))
            else:
                trailing_stop = highest_price * (1 - params['trailing_distance'])

        return {
            'stop_loss_price': stop_loss_price,
            'trailing_activation': trailing_activation,
            'trailing_stop': trailing_stop,
            'params': params,
            'atr_stop_price': atr_stop,
            'pct_stop_price': pct_stop,
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
        aggressive = bool(getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False))
        extra = {}
        try:
            extra = json.loads(position.get('extra_data') or '{}')
        except Exception:
            extra = {}
        atr = position.get('atr') or position.get('atr_at_entry') or extra.get('atr_at_entry') or (extra.get('sizing') or {}).get('atr') or 0
        levels = self.protective_levels(entry_price, highest_price, atr, regime, aggressive)

        # ─── 1. Stop Loss adaptativo ───
        stop_loss_price = levels['stop_loss_price']
        profit_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price else 0.0
        if bool(getattr(config, 'BREAK_EVEN_ENABLED', False)):
            activation_pct = float(getattr(config, 'BREAK_EVEN_ACTIVATION_PCT', 1.5) or 1.5)
            fee_buffer_pct = max(0.05, float(config.get_setting('MIN_PROFIT_NET', 1.0, float)) * 0.20)
            if profit_pct >= activation_pct:
                stop_loss_price = max(stop_loss_price, entry_price * (1 + fee_buffer_pct / 100))
        if current_price <= stop_loss_price:
            return {
                'should_sell': True,
                'reason': f"STOP LOSS [{regime}] ({((entry_price-stop_loss_price)/entry_price)*100:.1f}%)"
            }

        # ─── 2. Trailing Stop adaptativo ───
        if levels['trailing_stop'] > 0 and current_price >= levels['trailing_activation']:
            if current_price <= levels['trailing_stop']:
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

        entry_time = float(position.get('entry_time') or 0)
        max_age_hours = int(getattr(config, 'MAX_POSITION_AGE_HOURS', 0) or 0)
        if entry_time > 0 and max_age_hours > 0:
            age_hours = (time.time() - entry_time) / 3600
            if age_hours >= max_age_hours:
                return {
                    'should_sell': True,
                    'reason': f"MAX POSITION AGE ({age_hours:.1f}h >= {max_age_hours}h)"
                }

        return {'should_sell': False, 'reason': ''}
