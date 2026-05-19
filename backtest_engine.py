"""
backtest_engine.py — Motor de backtesting y base de conocimiento histórica
Descarga hasta 5 años de velas OHLCV via CCXT (sin APIs externas).
Genera una tabla de condiciones → win_rate que el bot consulta en cada decisión.
Actualización: manual o automática semanal.
"""
import pandas as pd
import pandas_ta as ta
import numpy as np
import json
import time
import sqlite3
import os
import config
from database_manager import DatabaseManager
from i18n import _
from trading_logic import TradingLogic


class BacktestEngine:
    """
    Dos responsabilidades:
    1. run_backtest(): descarga histórico y simula estrategias → guarda resultados en DB
    2. get_historical_prior(): consulta en tiempo real qué funcionó en condiciones similares
    """

    # Estrategias disponibles con sus parámetros
    STRATEGIES = {
        'TREND_FOLLOWING': {
            'description': 'Seguir tendencia establecida. EMA50>EMA200, ADX>25.',
            'trailing_pct': 0.025,    # Trailing más holgado para dejar correr
            'sl_atr_mult': 2.0,       # Stop Loss = 2x ATR
            'min_adx': 25,
            'rsi_buy_min': 45, 'rsi_buy_max': 65,
        },
        'BREAKOUT': {
            'description': 'Ruptura de resistencia con volumen. Movimientos rápidos.',
            'trailing_pct': 0.020,
            'sl_atr_mult': 1.5,
            'min_adx': 20,
            'rsi_buy_min': 55, 'rsi_buy_max': 75,
        },
        'MEAN_REVERSION': {
            'description': 'Rebote desde soporte en mercado lateral. ADX<20.',
            'trailing_pct': 0.010,    # Trailing ajustado, targets pequeños
            'sl_atr_mult': 1.2,
            'min_adx': 0, 'max_adx': 22,
            'rsi_buy_min': 30, 'rsi_buy_max': 45,  # Comprar en sobreventa
        },
        'MOMENTUM': {
            'description': 'RSI acelerando con volumen. Movimientos cortos y rápidos.',
            'trailing_pct': 0.015,
            'sl_atr_mult': 1.8,
            'min_adx': 15,
            'rsi_buy_min': 50, 'rsi_buy_max': 70,
        },
    }

    PROFIT_FACTOR_CAP = 10.0

    def __init__(self, exchange_helper, lang='es'):
        self.exchange = exchange_helper
        self.db = DatabaseManager()
        self.u_lang = lang
        self._init_backtest_tables()

    def _init_backtest_tables(self):
        """Crea las tablas de backtest en SQLite si no existen."""
        db_path = self.db.db_path
        with sqlite3.connect(db_path, timeout=10) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS backtest_conditions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timeframe TEXT,
                    regime TEXT,
                    strategy TEXT,
                    rsi_bucket TEXT,
                    adx_bucket TEXT,
                    trend TEXT,
                    win_rate REAL,
                    avg_profit_pct REAL,
                    avg_loss_pct REAL,
                    profit_factor REAL,
                    total_trades INTEGER,
                    avg_duration_hours REAL,
                    best_stop_loss_pct REAL,
                    best_trailing_pct REAL,
                    updated_at REAL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timeframe TEXT,
                    period_years REAL,
                    total_trades INTEGER,
                    win_rate REAL,
                    total_return_pct REAL,
                    max_drawdown_pct REAL,
                    sharpe_ratio REAL,
                    best_strategy TEXT,
                    run_timestamp REAL
                )
            ''')
            conn.commit()

    # ─────────────────────────────────────────────
    # DESCARGA DE DATOS HISTÓRICOS
    # ─────────────────────────────────────────────

    def download_historical_data(self, symbol: str, timeframe: str = '4h', years: float = 2.0, verbose: bool = True) -> pd.DataFrame:
        """
        Descarga datos históricos via CCXT en múltiples llamadas para superar el límite de 1000 velas.
        Para 2 años de velas 4h: ~4380 velas → ~5 llamadas de API.
        Para 5 años de velas 1D: ~1825 velas → ~2 llamadas de API.
        """
        if verbose:
            print(f"[Backtest] { _('BT_DOWNLOADING', lang=self.u_lang) } {symbol} ({timeframe} · {years} { _('LOG_YEARS', lang=self.u_lang) })...")

        # Calcular timestamp de inicio
        ms_per_candle = {
            '15m': 900_000, '1h': 3_600_000,
            '4h': 14_400_000, '1d': 86_400_000
        }
        ms = ms_per_candle.get(timeframe, 14_400_000)
        candles_needed = int((years * 365 * 24 * 3600 * 1000) / ms)
        since = int(time.time() * 1000) - (candles_needed * ms)

        all_candles = []
        current_since = since
        last_ts = 0

        while len(all_candles) < candles_needed:
            try:
                # Nota: Algunos exchanges como Crypto.com limitan a 300 velas por llamada
                candles = self.exchange.exchange.fetch_ohlcv(
                    symbol, timeframe, since=current_since, limit=1000
                )
                if not candles:
                    break
                
                # Si el exchange nos devuelve velas que ya tenemos (mismo TS), parar para evitar bucle infinito
                if candles[-1][0] == last_ts:
                    break
                
                all_candles.extend(candles)
                last_ts = candles[-1][0]
                current_since = last_ts + ms
                
                # Pequeña pausa para no saturar el rate limit
                time.sleep(0.2)
            except Exception as e:
                print(f"[Backtest] Error {symbol}: {e}")
                break

        if not all_candles:
            return pd.DataFrame()

        df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates('timestamp').sort_values('timestamp').reset_index(drop=True)
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)

        if verbose:
            print(f"[Backtest] {len(df)} { _('BT_CANDLES_LOADED', lang=self.u_lang) } ({df['timestamp'].iloc[0].date()} → {df['timestamp'].iloc[-1].date()})")
        return df

    def calculate_indicators_for_backtest(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula todos los indicadores técnicos necesarios para el backtest."""
        df = df.copy()

        # Indicadores principales
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['ema50'] = ta.ema(df['close'], length=50)
        df['ema200'] = ta.ema(df['close'], length=200)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        if adx_df is not None and not adx_df.empty:
            df['adx'] = adx_df['ADX_14']
        else:
            df['adx'] = 0

        # Volumen relativo (vs media 20 períodos)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()

        # Tendencia
        df['trend'] = np.where(df['ema50'] > df['ema200'], 'BULL', 'BEAR')

        # Régimen de mercado basado en indicadores
        df['regime'] = 'RANGING'
        df.loc[(df['adx'] > 25) & (df['trend'] == 'BULL'), 'regime'] = 'TRENDING_UP'
        df.loc[(df['adx'] > 25) & (df['trend'] == 'BEAR'), 'regime'] = 'TRENDING_DOWN'
        df.loc[df['atr'] / df['close'] > 0.04, 'regime'] = 'HIGH_VOLATILITY'

        # Buckets de RSI y ADX para la tabla de condiciones
        df['rsi_bucket'] = pd.cut(
            df['rsi'],
            bins=[0, 30, 45, 55, 65, 100],
            labels=['OVERSOLD', 'LOW', 'NEUTRAL', 'HIGH', 'OVERBOUGHT']
        )
        df['adx_bucket'] = pd.cut(
            df['adx'],
            bins=[0, 15, 25, 40, 100],
            labels=['WEAK', 'MODERATE', 'STRONG', 'EXTREME']
        )

        return df.dropna(subset=['ema200', 'rsi', 'adx'])

    # ─────────────────────────────────────────────
    # MOTOR DE SIMULACIÓN
    # ─────────────────────────────────────────────

    def simulate_strategy(self, df: pd.DataFrame, strategy_name: str,
                           initial_capital: float = 1000.0,
                           risk_per_trade: float = 0.10) -> dict:
        """
        Simula una estrategia sobre datos históricos.
        Implementa stops reales, trailing, y sizing dinámico.
        Retorna métricas completas de rendimiento.
        """
        params = self.STRATEGIES[strategy_name]
        trades = []
        equity_curve = [initial_capital]
        capital = initial_capital
        position = None  # Dict con datos de posición abierta
        live_logic = TradingLogic()
        fee_rate = float(getattr(config, "TRADING_FEE_RATE", 0.001) or 0.0)
        buy_slippage = float(getattr(config, "BUY_SLIPPAGE_LIMIT", 0.0) or 0.0)
        sell_slippage = float(getattr(config, "SELL_SLIPPAGE_LIMIT", 0.0) or 0.0)

        for i in range(200, len(df)):  # Empezar en 200 para tener indicadores calculados
            row = df.iloc[i]
            price = row['close']

            # ─── Gestión de posición abierta ───
            if position:
                # Actualizar máximo para el trailing
                if price > position['highest_price']:
                    position['highest_price'] = price

                levels = live_logic.protective_levels(
                    position['entry_price'],
                    position['highest_price'],
                    position.get('atr', 0),
                    position.get('regime', 'RANGING'),
                    aggressive=bool(getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False)),
                )
                stop_price = levels['stop_loss_price']
                trailing_price = levels['trailing_stop'] if price >= levels['trailing_activation'] else None

                # 3. Condición de salida
                exit_price = None
                exit_reason = None

                if price <= stop_price:
                    exit_price = stop_price
                    exit_reason = 'STOP_LOSS'
                elif trailing_price and price <= trailing_price:
                    exit_price = trailing_price
                    exit_reason = 'TRAILING_STOP'
                elif row.get('regime') in ['TRENDING_DOWN'] and strategy_name != 'MEAN_REVERSION':
                    # Régimen cambia a bajista → salir
                    exit_price = price
                    exit_reason = 'REGIME_CHANGE'

                if exit_price:
                    # Calcular resultado
                    entry_net = position['entry_price'] * (1 + fee_rate)
                    exit_net = exit_price * (1 - fee_rate - sell_slippage)
                    pnl_pct = (exit_net - entry_net) / entry_net
                    pnl_usd = position['position_size'] * pnl_pct
                    capital += pnl_usd
                    duration_hours = (i - position['entry_index']) * self._candle_hours(df)

                    trades.append({
                        'entry_idx': position['entry_index'],
                        'exit_idx': i,
                        'entry_price': position['entry_price'],
                        'exit_price': exit_price,
                        'pnl_pct': pnl_pct * 100,
                        'pnl_usd': pnl_usd,
                        'exit_reason': exit_reason,
                        'duration_hours': duration_hours,
                        'regime': position['regime'],
                        'rsi_bucket': str(position['rsi_bucket']),
                        'adx_bucket': str(position['adx_bucket']),
                        'trend': position['trend'],
                        'strategy': strategy_name,
                        'won': pnl_pct > 0
                    })
                    equity_curve.append(capital)
                    position = None

            # ─── Buscar señal de entrada ───
            elif not position:
                should_enter = self._check_entry_signal(row, params, strategy_name)

                if should_enter and capital > 0:
                    position_size = capital * risk_per_trade
                    entry_price = price * (1 + buy_slippage)
                    initial_sl = live_logic.protective_levels(
                        entry_price,
                        entry_price,
                        row.get('atr', 0),
                        str(row.get('regime', 'RANGING')),
                        aggressive=bool(getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False)),
                    )['stop_loss_price']
                    
                    position = {
                        'entry_price': entry_price,
                        'highest_price': entry_price,
                        'entry_stop': initial_sl,
                        'atr': row.get('atr', 0),
                        'position_size': position_size,
                        'entry_index': i,
                        'regime': str(row.get('regime', 'UNKNOWN')),
                        'rsi_bucket': str(row.get('rsi_bucket', 'NEUTRAL')),
                        'adx_bucket': str(row.get('adx_bucket', 'MODERATE')),
                        'trend': str(row.get('trend', 'BULL')),
                    }

        # ─── Métricas finales ───
        return self._calculate_metrics(trades, equity_curve, initial_capital, strategy_name, df)

    def _check_entry_signal(self, row, params: dict, strategy_name: str) -> bool:
        """Verifica si las condiciones de la vela actual cumplen con la señal de entrada."""
        rsi = row.get('rsi', 50)
        adx = row.get('adx', 0)
        regime = str(row.get('regime', ''))
        vol_ratio = row.get('vol_ratio', 1.0)

        # Filtros comunes: no entrar en tendencia bajista fuerte (salvo mean reversion)
        if regime == 'TRENDING_DOWN' and strategy_name != 'MEAN_REVERSION':
            return False

        # Filtros por estrategia
        rsi_ok = params.get('rsi_buy_min', 0) <= rsi <= params.get('rsi_buy_max', 100)
        adx_ok = adx >= params.get('min_adx', 0)
        adx_max_ok = adx <= params.get('max_adx', 100)

        # Volumen mínimo para confirmación (excepto mean reversion que opera en lateral)
        vol_ok = vol_ratio >= 1.1 if strategy_name in ['BREAKOUT', 'MOMENTUM'] else True

        return rsi_ok and adx_ok and adx_max_ok and vol_ok

    def _calculate_metrics(self, trades: list, equity_curve: list,
                            initial_capital: float, strategy_name: str,
                            df: pd.DataFrame) -> dict:
        """Calcula métricas completas de rendimiento del backtest."""
        if not trades:
            return {'total_trades': 0, 'win_rate': 0, 'strategy': strategy_name}

        wins = [t for t in trades if t['won']]
        losses = [t for t in trades if not t['won']]

        win_rate = len(wins) / len(trades) if trades else 0
        avg_profit = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
        expectancy = (win_rate * avg_profit) + ((1 - win_rate) * avg_loss)

        gross_profit = sum(t['pnl_usd'] for t in wins) if wins else 0
        gross_loss = abs(sum(t['pnl_usd'] for t in losses)) if losses else 0
        profit_factor = self._finite_profit_factor(gross_profit, gross_loss, len(trades))

        # Max drawdown
        equity_series = pd.Series(equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max * 100
        max_drawdown = drawdown.min()

        # Sharpe por operación, anualizado por frecuencia real de trades del histórico.
        returns = pd.Series([t['pnl_pct'] for t in trades])
        years = self._years_covered(df)
        trades_per_year = len(trades) / years if years > 0 else 0
        sharpe = (returns.mean() / returns.std() * np.sqrt(trades_per_year)) if returns.std() > 0 and trades_per_year > 0 else 0

        total_return = (equity_curve[-1] - initial_capital) / initial_capital * 100
        min_sample = int(getattr(config, "BACKTEST_MIN_SAMPLE_TRADES", 30) or 30)
        sample_factor = min(1.0, len(trades) / max(1, min_sample))
        drawdown_factor = max(0.0, 1.0 - (abs(max_drawdown) / 50.0))
        reliability_score = max(0.0, min(1.0, (sample_factor * 0.65) + (drawdown_factor * 0.35)))

        return {
            'strategy': strategy_name,
            'total_trades': len(trades),
            'win_rate': round(win_rate, 4),
            'avg_profit_pct': round(avg_profit, 2),
            'avg_loss_pct': round(avg_loss, 2),
            'expectancy_pct': round(expectancy, 3),
            'profit_factor': round(profit_factor, 2),
            'total_return_pct': round(total_return, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'reliability_score': round(reliability_score, 3),
            'sharpe_ratio': round(sharpe, 2),
            'avg_duration_hours': round(np.mean([t['duration_hours'] for t in trades]), 1),
            'trades_detail': trades  # Guardamos para la tabla de condiciones
        }

    def _candle_hours(self, df: pd.DataFrame) -> float:
        """Detecta automáticamente el timeframe del DataFrame en horas."""
        if len(df) < 2:
            return 4.0
        delta = (df['timestamp'].iloc[1] - df['timestamp'].iloc[0]).total_seconds()
        return delta / 3600

    def _years_covered(self, df: pd.DataFrame) -> float:
        if len(df) < 2 or 'timestamp' not in df:
            return 1.0
        delta = df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]
        try:
            days = delta.total_seconds() / 86400
        except AttributeError:
            days = 365.25
        return max(days / 365.25, 1 / 365.25)

    def _finite_profit_factor(self, gross_profit: float, gross_loss: float, total_trades: int) -> float:
        if gross_loss > 0:
            return min(gross_profit / gross_loss, self.PROFIT_FACTOR_CAP)
        if gross_profit <= 0:
            return 0.0
        # Sin pérdidas en pocas muestras suele indicar muestra escasa más que ventaja real.
        if total_trades < 8:
            return 1.5
        return self.PROFIT_FACTOR_CAP

    def _strategy_score(self, result: dict) -> float:
        trades = int(result.get('total_trades', 0) or 0)
        if trades <= 0:
            return -1.0
        pf = min(float(result.get('profit_factor', 0) or 0), self.PROFIT_FACTOR_CAP)
        win_rate = float(result.get('win_rate', 0) or 0)
        total_return = float(result.get('total_return_pct', 0) or 0) / 100.0
        drawdown_penalty = abs(float(result.get('max_drawdown_pct', 0) or 0)) / 100.0
        min_sample = int(getattr(config, "BACKTEST_MIN_SAMPLE_TRADES", 30) or 30)
        sample_factor = min(1.0, trades / max(1, min_sample))
        reliability = float(result.get('reliability_score', sample_factor) or sample_factor)
        return ((pf * 0.50) + (win_rate * 2.0) + total_return - drawdown_penalty) * min(sample_factor, reliability)

    # ─────────────────────────────────────────────
    # CONSTRUCCIÓN DE LA TABLA DE CONDICIONES
    # ─────────────────────────────────────────────

    def build_conditions_table(self, symbol: str, trades_detail: list, timeframe: str = '4h', verbose: bool = True):
        """
        Agrupa los trades por condición de mercado y calcula el win rate por bucket.
        Esto genera la 'base de conocimiento' que el bot consulta en tiempo real.
        """
        if not trades_detail:
            return

        df_trades = pd.DataFrame(trades_detail)
        db_path = self.db.db_path

        # Agrupar por combinación de condiciones
        groups = df_trades.groupby(['regime', 'strategy', 'rsi_bucket', 'adx_bucket', 'trend'])

        rows_to_insert = []
        for (regime, strategy, rsi_bucket, adx_bucket, trend), group in groups:
            min_bucket_trades = int(getattr(config, "BACKTEST_MIN_TRADES_PER_BUCKET", 5) or 5)
            if len(group) < min_bucket_trades:
                continue

            wins = group[group['won'] == True]
            losses = group[group['won'] == False]
            win_rate = len(wins) / len(group)

            gross_profit = wins['pnl_pct'].sum() if len(wins) > 0 else 0
            gross_loss = abs(losses['pnl_pct'].sum()) if len(losses) > 0 else 0
            profit_factor = self._finite_profit_factor(gross_profit, gross_loss, len(group))

            rows_to_insert.append((
                symbol, timeframe, str(regime), str(strategy),
                str(rsi_bucket), str(adx_bucket), str(trend),
                round(win_rate, 4),
                round(wins['pnl_pct'].mean() if len(wins) > 0 else 0, 2),
                round(losses['pnl_pct'].mean() if len(losses) > 0 else 0, 2),
                round(profit_factor, 2),
                len(group),
                round(group['duration_hours'].mean(), 1),
                0.0, 0.0,  # best_stop_loss y trailing (futuro)
                time.time()
            ))

        with sqlite3.connect(db_path, timeout=10) as conn:
            # Limpiar entradas anteriores para este símbolo
            conn.execute(
                'DELETE FROM backtest_conditions WHERE symbol = ? AND timeframe = ?',
                (symbol, timeframe)
            )
            conn.executemany('''
                INSERT INTO backtest_conditions
                (symbol, timeframe, regime, strategy, rsi_bucket, adx_bucket, trend,
                 win_rate, avg_profit_pct, avg_loss_pct, profit_factor, total_trades,
                 avg_duration_hours, best_stop_loss_pct, best_trailing_pct, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', rows_to_insert)
            conn.commit()

        if verbose:
            print(f"[Backtest] { _('ROTATION_MODULE', lang=self.u_lang) }: {len(rows_to_insert)} combinaciones para {symbol}")

    # ─────────────────────────────────────────────
    # CONSULTA EN TIEMPO REAL (el bot llama esto en cada decisión)
    # ─────────────────────────────────────────────

    def get_historical_prior(self, symbol: str, current_regime: str,
                              current_rsi_bucket: str, current_adx_bucket: str,
                              current_trend: str, proposed_strategy: str) -> dict:
        """
        Consulta qué pasó históricamente en condiciones similares a las actuales.
        Retorna un dict con win_rate, profit_factor, recomendación, y si debe vetarse la entrada.

        VETO DURO: si win_rate < 0.35 con al menos 5 trades históricos → bloquear entrada.
        """
        db_path = self.db.db_path
        default = {
            'found': False,
            'win_rate': 0.5,
            'profit_factor': 1.0,
            'total_trades': 0,
            'avg_profit_pct': 0,
            'avg_loss_pct': 0,
            'avg_duration_hours': 4,
            'hard_veto': False,
            'veto_reason': '',
            'prior_text': 'Sin datos históricos suficientes para este contexto.'
        }

        try:
            with sqlite3.connect(db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row

                # Buscar por condiciones exactas primero
                cursor = conn.execute('''
                    SELECT * FROM backtest_conditions
                    WHERE symbol = ?
                    AND regime = ?
                    AND strategy = ?
                    AND rsi_bucket = ?
                    AND adx_bucket = ?
                    AND trend = ?
                    AND total_trades >= 3
                    ORDER BY updated_at DESC LIMIT 1
                ''', (symbol, current_regime, proposed_strategy,
                      current_rsi_bucket, current_adx_bucket, current_trend))

                row = cursor.fetchone()

                # Si no hay match exacto, buscar por régimen + estrategia (más general)
                if not row:
                    cursor = conn.execute('''
                        SELECT * FROM backtest_conditions
                        WHERE symbol = ?
                        AND regime = ?
                        AND strategy = ?
                        AND total_trades >= 5
                        ORDER BY win_rate DESC LIMIT 1
                    ''', (symbol, current_regime, proposed_strategy))
                    row = cursor.fetchone()

                if not row:
                    return default

                win_rate = row['win_rate']
                profit_factor = row['profit_factor']
                total_trades = row['total_trades']

                # Aplicar veto duro solo con muestra suficiente.
                veto_floor = float(getattr(config, 'BACKTEST_HARD_VETO_WIN_RATE', 0.35))
                veto_min_trades = int(getattr(config, 'BACKTEST_HARD_VETO_MIN_TRADES', 20) or 20)
                if bool(getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False)):
                    veto_floor = min(veto_floor, 0.45)
                hard_veto = win_rate < veto_floor and total_trades >= veto_min_trades
                veto_reason = ''
                if hard_veto:
                    veto_reason = (
                        f"VETO HISTÓRICO: en régimen {current_regime} con estrategia "
                        f"{proposed_strategy}, win rate histórico = {win_rate:.0%} "
                        f"({total_trades} trades). Umbral mínimo: {veto_floor:.0%}."
                    )

                # Construir texto para el prompt de la IA
                prior_text = (
                    f"Historial en condiciones similares ({total_trades} trades): "
                    f"Win rate {win_rate:.0%} | "
                    f"Profit factor {profit_factor:.1f} | "
                    f"Ganancia media {row['avg_profit_pct']:+.1f}% / "
                    f"Pérdida media {row['avg_loss_pct']:+.1f}% | "
                    f"Duración media {row['avg_duration_hours']:.0f}h"
                )

                return {
                    'found': True,
                    'win_rate': win_rate,
                    'profit_factor': profit_factor,
                    'total_trades': total_trades,
                    'avg_profit_pct': row['avg_profit_pct'],
                    'avg_loss_pct': row['avg_loss_pct'],
                    'avg_duration_hours': row['avg_duration_hours'],
                    'hard_veto': hard_veto,
                    'veto_reason': veto_reason,
                    'prior_text': prior_text
                }

        except Exception as e:
            print(f"[Backtest] Error prior {symbol}: {e}")
            return default

    # ─────────────────────────────────────────────
    # MÉTODO PRINCIPAL: Correr backtest completo para un símbolo
    # ─────────────────────────────────────────────

    def run_full_backtest(self, symbol: str, timeframe: str = '4h',
                          years: float = 2.0, verbose: bool = True) -> dict:
        """
        Pipeline completo para un símbolo:
        1. Descarga datos históricos
        2. Calcula indicadores
        3. Simula todas las estrategias
        4. Guarda tabla de condiciones
        5. Retorna resumen comparativo

        Recomendación de timeframes:
        - '4h' + 2 años: mejor para encontrar patrones de swing trading (el uso principal del bot)
        - '1d' + 5 años: visión macro de largo plazo
        - '15m' + 0.5 años: patrones intraday (más ruidoso)
        """
        df_raw = self.download_historical_data(symbol, timeframe, years, verbose=verbose)
        if df_raw.empty:
            if verbose:
                print(f"[Backtest] Sin datos para {symbol}")
            return {}

        df = self.calculate_indicators_for_backtest(df_raw)
        if verbose:
            print(f"[Backtest] {len(df)} { _('BT_CANDLES_LOADED', lang=self.u_lang) } ({symbol})")

        results = {}
        all_trades = []

        for strategy_name in self.STRATEGIES:
            if verbose:
                print(f"[Backtest] { _('BT_SIMULATING', lang=self.u_lang) } {strategy_name} ({symbol})...")
            result = self.simulate_strategy(df, strategy_name)
            results[strategy_name] = result
            if result.get('trades_detail'):
                all_trades.extend(result['trades_detail'])

        # Construir tabla de condiciones con todos los trades de todas las estrategias
        self.build_conditions_table(symbol, all_trades, timeframe, verbose=verbose)

        # Guardar resumen del backtest en DB
        best_strategy = max(results, key=lambda k: self._strategy_score(results[k]))
        best = results[best_strategy]

        db_path = self.db.db_path
        with sqlite3.connect(db_path, timeout=10) as conn:
            conn.execute('DELETE FROM backtest_runs WHERE symbol = ? AND timeframe = ?', (symbol, timeframe))
            conn.execute('''
                INSERT INTO backtest_runs
                (symbol, timeframe, period_years, total_trades, win_rate,
                 total_return_pct, max_drawdown_pct, sharpe_ratio, best_strategy, run_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol, timeframe, years,
                best.get('total_trades', 0),
                best.get('win_rate', 0),
                best.get('total_return_pct', 0),
                best.get('max_drawdown_pct', 0),
                best.get('sharpe_ratio', 0),
                best_strategy,
                time.time()
            ))
            conn.commit()

        if verbose:
            print(f"\n[Backtest] === { _('BT_SUMMARY', lang=self.u_lang) } {symbol} ({timeframe} · {years} { _('LOG_YEARS', lang=self.u_lang) }) ===")
            for s, r in results.items():
                if r.get('total_trades', 0) > 0:
                    print(f"  {s}: {r['total_trades']} { _('BT_TRADES', lang=self.u_lang) } | WR {r['win_rate']:.0%} | "
                          f"PF {r['profit_factor']:.2f} | { _('BT_RETURN', lang=self.u_lang) } {r['total_return_pct']:+.1f}%")

        return results
