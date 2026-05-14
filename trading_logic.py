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
        Evalúa si se debe cerrar una posición.
        Retorna {'should_sell': bool, 'reason': str}
        """
        import config # Hot reload support
        
        entry_price = position.get('entry_price', 0)
        highest_price = position.get('highest_price', entry_price)
        
        # 1. Stop Loss Fijo (Configurable)
        stop_loss_price = entry_price * (1 - config.STOP_LOSS_PCT)
        if current_price <= stop_loss_price:
            return {'should_sell': True, 'reason': f"STOP LOSS Fijo ({config.STOP_LOSS_PCT*100}%)"}
            
        # 2. Trailing Stop Loss
        # Si el precio actual es mayor al máximo registrado, actualizamos el máximo (esto se hace en el Daemon)
        # Aquí comprobamos si ha caído desde el pico
        trailing_activation_price = entry_price * (1 + 0.05) # Activar a partir de +5%
        if current_price >= trailing_activation_price:
            # Si cae un 1.5% desde el máximo histórico del trade, vendemos
            if current_price <= highest_price * (1 - 0.015):
                return {'should_sell': True, 'reason': "TRAILING STOP (Caja asegurada)"}

        # 3. Take Profit por AI (Si la IA dice SELL con alta confianza)
        if ai_decision and ai_decision.get('action') == 'SELL':
            if ai_decision.get('confidence', 0) >= 0.80:
                return {'should_sell': True, 'reason': "IA SELL Signal (Alta Confianza)"}
        
        return {'should_sell': False, 'reason': ""}
