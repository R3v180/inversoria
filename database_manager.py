import sqlite3
import time
import os
import re
import json
import pandas as pd

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Forzar ruta absoluta para evitar que Daemon y UI miren archivos distintos
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, "iversoria.db")
        else:
            self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        # timeout=10 allows concurrent access by waiting for locks
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Status
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_status (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Positions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS open_positions (
                    symbol TEXT PRIMARY KEY,
                    entry_price REAL,
                    highest_price REAL,
                    amount REAL,
                    entry_time REAL,
                    extra_data TEXT
                )
            ''')
            
            # Migración: Añadir extra_data si la tabla es antigua
            try:
                cursor.execute('ALTER TABLE open_positions ADD COLUMN extra_data TEXT')
            except sqlite3.OperationalError:
                pass
            
            # Cooldowns
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cooldowns (
                    symbol TEXT PRIMARY KEY,
                    timestamp REAL
                )
            ''')

            # Chat History
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Trades
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    side TEXT,
                    price REAL,
                    amount REAL,
                    reason TEXT,
                    pnl_pct REAL,
                    timestamp REAL
                )
            ''')
            
            # Init is_running to false by default if empty
            cursor.execute('INSERT OR IGNORE INTO system_status (key, value) VALUES (?, ?)', ('is_running', 'false'))
            
            # Init logs (Optional UI tracking)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    message TEXT
                )
            ''')
            
            # Migrate old CSV
            cursor.execute('SELECT COUNT(*) FROM trades')
            if cursor.fetchone()[0] == 0 and os.path.exists('trades_history.csv'):
                try:
                    df_old = pd.read_csv('trades_history.csv')
                    for _, row in df_old.iterrows():
                        ts = time.time()
                        try:
                            if pd.notna(row.get('Date')):
                                ts = time.mktime(time.strptime(str(row['Date']), '%Y-%m-%d %H:%M:%S'))
                        except:
                            pass
                        cursor.execute('''
                            INSERT INTO trades (symbol, side, price, amount, reason, pnl_pct, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (str(row.get('Symbol', 'Unknown')), str(row.get('Side', 'unknown')), 
                              float(row.get('Price', 0.0)), float(row.get('Amount', 0.0)), 
                              str(row.get('Reason', '')), float(row.get('PnL_%', 0.0)), ts))
                    conn.commit()
                    os.rename('trades_history.csv', 'trades_history_migrated.csv')
                    print("Migración de trades_history.csv a SQLite completada.")
                except Exception as e:
                    print(f"Error migrando CSV a SQLite: {e}")
            
            # Equity History (Para la curva de patrimonio)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS equity_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_value REAL,
                    timestamp REAL
                )
            ''')
            
            # Macro Data (v6.0)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS macro_data (
                    symbol TEXT PRIMARY KEY,
                    price REAL,
                    change_24h REAL,
                    last_update REAL
                )
            ''')

            # Decision Journal (auditoría cuantitativa append/update por resultado)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decision_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    updated_at REAL,
                    symbol TEXT,
                    price REAL,
                    ai_action TEXT,
                    action_final TEXT,
                    executable_action TEXT,
                    provider TEXT,
                    decision_mode TEXT,
                    execution_mode TEXT,
                    regime TEXT,
                    strategy TEXT,
                    confidence REAL,
                    decision_score REAL,
                    score_components TEXT,
                    indicators TEXT,
                    sizing TEXT,
                    risk TEXT,
                    portfolio_bucket TEXT,
                    block_reason TEXT,
                    execution_status TEXT,
                    execution_side TEXT,
                    executed_price REAL,
                    executed_amount REAL,
                    realized_pnl_pct REAL,
                    exit_reason TEXT
                )
            ''')
            for idx_name, idx_cols in {
                'idx_decision_journal_symbol_ts': 'symbol, timestamp',
                'idx_decision_journal_provider': 'provider',
                'idx_decision_journal_regime': 'regime',
                'idx_decision_journal_action': 'action_final',
                'idx_decision_journal_status': 'execution_status',
            }.items():
                cursor.execute(
                    f'CREATE INDEX IF NOT EXISTS {idx_name} ON decision_journal ({idx_cols})'
                )
            
            conn.commit()

    # --- System Status ---
    def set_system_status(self, key, value):
        with self._get_connection() as conn:
            conn.execute('INSERT OR REPLACE INTO system_status (key, value) VALUES (?, ?)', (key, str(value)))
            conn.commit()

    def get_system_status(self, key, default=None):
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT value FROM system_status WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                return row['value']
            return default

    # --- Logs ---
    def add_log(self, message):
        with self._get_connection() as conn:
            conn.execute('INSERT INTO logs (timestamp, message) VALUES (?, ?)', (time.time(), message))
            # Keep only last 100
            conn.execute('DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY timestamp DESC LIMIT 300)')
            conn.commit()

    def get_logs(self):
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT timestamp, message FROM logs ORDER BY timestamp ASC')
            logs = []
            for row in cursor.fetchall():
                t_str = time.strftime('%H:%M:%S', time.localtime(row['timestamp']))
                logs.append(f"[{t_str}] {row['message']}")
            return logs

    # --- Open Positions ---
    def get_open_positions(self):
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT * FROM open_positions')
            return {row['symbol']: dict(row) for row in cursor.fetchall()}

    def add_open_position(self, symbol, entry_price, highest_price, amount, entry_time=None, extra_data=None):
        if entry_time is None:
            entry_time = time.time()
        with self._get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO open_positions (symbol, entry_price, highest_price, amount, entry_time, extra_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (symbol, entry_price, highest_price, amount, entry_time, extra_data))
            conn.commit()

    def update_highest_price(self, symbol, highest_price):
        with self._get_connection() as conn:
            conn.execute('UPDATE open_positions SET highest_price = ? WHERE symbol = ?', (highest_price, symbol))
            conn.commit()

    def remove_open_position(self, symbol):
        with self._get_connection() as conn:
            conn.execute('DELETE FROM open_positions WHERE symbol = ?', (symbol,))
            conn.commit()

    def close_position(self, symbol, exit_price, reason, sold_amount=None):
        """
        Cierra (total o parcialmente) una posición abierta: registra el trade y
        actualiza o elimina la fila en open_positions. sold_amount: cantidad
        vendida en exchange (si difiere de la DB por fees/redondeo).
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT entry_price, amount FROM open_positions WHERE symbol = ?',
                (symbol,)
            )
            row = cursor.fetchone()
            if not row:
                return False

            entry_price = float(row['entry_price'] or 0)
            db_amount = float(row['amount'] or 0)

            qty = float(sold_amount) if sold_amount is not None else db_amount
            qty = min(qty, db_amount)
            if qty <= 0:
                return False

            if entry_price and entry_price > 0:
                pnl_pct = ((float(exit_price) - entry_price) / entry_price) * 100
            else:
                pnl_pct = 0.0

            conn.execute('''
                INSERT INTO trades (symbol, side, price, amount, reason, pnl_pct, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, 'sell', float(exit_price), qty, reason, pnl_pct, time.time()))

            remaining = db_amount - qty
            dust_usd = remaining * float(exit_price) if exit_price else 0.0
            dust_ratio = (remaining / db_amount) if db_amount > 0 else 0.0

            if remaining <= 0 or dust_ratio < 1e-4 or dust_usd < 0.02:
                conn.execute('DELETE FROM open_positions WHERE symbol = ?', (symbol,))
            else:
                conn.execute(
                    'UPDATE open_positions SET amount = ? WHERE symbol = ?',
                    (remaining, symbol)
                )
            conn.commit()

        return True

    def clear_open_positions(self):
        with self._get_connection() as conn:
            conn.execute('DELETE FROM open_positions')
            conn.commit()

    # --- Cooldowns ---
    def get_cooldowns(self):
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT * FROM cooldowns')
            return {row['symbol']: row['timestamp'] for row in cursor.fetchall()}

    def add_cooldown(self, symbol, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        with self._get_connection() as conn:
            conn.execute('INSERT OR REPLACE INTO cooldowns (symbol, timestamp) VALUES (?, ?)', (symbol, timestamp))
            conn.commit()

    # --- Trades ---
    def save_trade(self, symbol, side, price, amount, reason, pnl_pct):
        timestamp = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO trades (symbol, side, price, amount, reason, pnl_pct, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, side, price, amount, reason, pnl_pct, timestamp))
            conn.commit()
            return cursor.lastrowid

    # --- Decision Journal ---
    def _json_or_none(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return json.dumps(str(value), ensure_ascii=False)

    def add_decision_journal(self, **payload):
        now = time.time()
        fields = {
            'timestamp': payload.get('timestamp', now),
            'updated_at': now,
            'symbol': payload.get('symbol'),
            'price': payload.get('price'),
            'ai_action': payload.get('ai_action'),
            'action_final': payload.get('action_final'),
            'executable_action': payload.get('executable_action'),
            'provider': payload.get('provider'),
            'decision_mode': payload.get('decision_mode'),
            'execution_mode': payload.get('execution_mode'),
            'regime': payload.get('regime'),
            'strategy': payload.get('strategy'),
            'confidence': payload.get('confidence'),
            'decision_score': payload.get('decision_score'),
            'score_components': self._json_or_none(payload.get('score_components')),
            'indicators': self._json_or_none(payload.get('indicators')),
            'sizing': self._json_or_none(payload.get('sizing')),
            'risk': self._json_or_none(payload.get('risk')),
            'portfolio_bucket': payload.get('portfolio_bucket'),
            'block_reason': payload.get('block_reason'),
            'execution_status': payload.get('execution_status', 'observed'),
            'execution_side': payload.get('execution_side'),
            'executed_price': payload.get('executed_price'),
            'executed_amount': payload.get('executed_amount'),
            'realized_pnl_pct': payload.get('realized_pnl_pct'),
            'exit_reason': payload.get('exit_reason'),
        }
        columns = ', '.join(fields.keys())
        placeholders = ', '.join(['?'] * len(fields))
        with self._get_connection() as conn:
            cursor = conn.execute(
                f'INSERT INTO decision_journal ({columns}) VALUES ({placeholders})',
                tuple(fields.values()),
            )
            conn.commit()
            return cursor.lastrowid

    def update_decision_journal(self, decision_id, **updates):
        if not decision_id or not updates:
            return False
        allowed = {
            'updated_at', 'action_final', 'executable_action', 'sizing', 'risk',
            'block_reason', 'execution_status', 'execution_side', 'executed_price',
            'executed_amount', 'realized_pnl_pct', 'exit_reason',
        }
        fields = {}
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key in {'sizing', 'risk'}:
                value = self._json_or_none(value)
            fields[key] = value
        if not fields:
            return False
        fields['updated_at'] = time.time()
        assignments = ', '.join(f'{key} = ?' for key in fields)
        with self._get_connection() as conn:
            conn.execute(
                f'UPDATE decision_journal SET {assignments} WHERE id = ?',
                tuple(fields.values()) + (int(decision_id),),
            )
            conn.commit()
        return True

    def get_decision_journal(self, limit=200):
        limit = max(1, min(int(limit), 5000))
        with self._get_connection() as conn:
            return pd.read_sql_query(
                '''
                SELECT * FROM decision_journal
                ORDER BY timestamp DESC
                LIMIT ?
                ''',
                conn,
                params=(limit,),
            )

    def get_decision_metrics(self, limit=500):
        df = self.get_decision_journal(limit=limit)
        if df.empty:
            return {
                'total_decisions': 0,
                'accepted_buys': 0,
                'blocked': 0,
                'provider_stats': pd.DataFrame(),
                'regime_stats': pd.DataFrame(),
            }

        status = df.get('execution_status', pd.Series(dtype=str)).fillna('')
        action = df.get('action_final', pd.Series(dtype=str)).fillna('')
        total = len(df)
        accepted_buys = int(((action == 'BUY') & status.isin(['executed', 'simulated', 'closed', 'open'])).sum())
        blocked = int(status.str.contains('blocked|consultive|score', case=False, na=False).sum())
        ai_action = df.get('ai_action', pd.Series(dtype=str)).fillna('')
        ai_aligned = int((ai_action == action).sum()) if len(ai_action) == len(action) else 0
        ai_alignment_pct = (ai_aligned / total * 100) if total else 0.0

        realized = pd.to_numeric(
            df['realized_pnl_pct'] if 'realized_pnl_pct' in df.columns else pd.Series([None] * len(df)),
            errors='coerce',
        )
        closed = df[realized.notna()].copy()
        def grouped_stats(group_col):
            if closed.empty or group_col not in closed.columns:
                return pd.DataFrame()
            rows = []
            for name, group in closed.groupby(group_col):
                pnl = pd.to_numeric(group['realized_pnl_pct'], errors='coerce').dropna()
                if pnl.empty:
                    continue
                wins = pnl[pnl > 0]
                losses = pnl[pnl <= 0]
                win_rate = len(wins) / len(pnl) * 100
                expectancy = pnl.mean()
                profit_sum = wins.sum()
                loss_sum = abs(losses.sum())
                profit_factor = profit_sum / loss_sum if loss_sum > 0 else (profit_sum if profit_sum > 0 else 0)
                rows.append({
                    group_col: name or 'N/A',
                    'trades': len(pnl),
                    'win_rate': round(win_rate, 1),
                    'expectancy_pct': round(expectancy, 2),
                    'profit_factor': round(profit_factor, 2),
                })
            return pd.DataFrame(rows).sort_values('trades', ascending=False) if rows else pd.DataFrame()

        return {
            'total_decisions': total,
            'accepted_buys': accepted_buys,
            'blocked': blocked,
            'ai_alignment_pct': round(ai_alignment_pct, 1),
            'provider_stats': grouped_stats('provider'),
            'regime_stats': grouped_stats('regime'),
        }

    def get_cost_basis(self, symbol: str, open_positions=None):
        """
        Precio medio de compra estimado (USDT por moneda base) y origen del dato.
        open_positions: dict opcional {symbol: row} para evitar reconsulta.
        """
        if open_positions is None:
            open_positions = self.get_open_positions()
        if symbol in open_positions:
            ep = float(open_positions[symbol].get('entry_price') or 0)
            if ep > 0:
                return {
                    'entry_price': ep,
                    'source': 'open_position',
                    'qty_tracked': float(open_positions[symbol].get('amount') or 0),
                }

        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT side, price, amount, timestamp FROM trades WHERE symbol = ? ORDER BY timestamp ASC',
                (symbol,),
            )
            rows = cursor.fetchall()

        if not rows:
            return {'entry_price': None, 'source': None, 'qty_tracked': 0.0}

        running_qty = 0.0
        running_cost = 0.0
        last_buy_price = None
        for row in rows:
            side = str(row['side']).lower()
            price = float(row['price'] or 0)
            amount = float(row['amount'] or 0)
            if side == 'buy' and amount > 0 and price > 0:
                running_cost += price * amount
                running_qty += amount
                last_buy_price = price
            elif side == 'sell' and amount > 0 and running_qty > 0:
                sold = min(amount, running_qty)
                share = sold / running_qty
                running_cost -= running_cost * share
                running_qty -= sold

        if running_qty > 1e-12 and running_cost > 0:
            return {
                'entry_price': running_cost / running_qty,
                'source': 'avg_trades',
                'qty_tracked': running_qty,
            }
        if last_buy_price:
            return {
                'entry_price': last_buy_price,
                'source': 'last_buy',
                'qty_tracked': 0.0,
            }

        log_basis = self._cost_basis_from_logs(symbol)
        if log_basis:
            return log_basis

        sell_basis = self._cost_basis_from_sell_pnl(symbol)
        if sell_basis:
            return sell_basis

        return {'entry_price': None, 'source': None, 'qty_tracked': 0.0}

    def _cost_basis_from_logs(self, symbol: str):
        """Último precio en logs del daemon (🚀 COMPRA / BUY SYMBOL @ price)."""
        sym = symbol.strip()
        pattern = re.compile(
            rf'(?:COMPRA|BUY)\s+{re.escape(sym)}\s+@\s+([0-9.eE+-]+)',
            re.IGNORECASE,
        )
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT message FROM logs WHERE message LIKE ? ORDER BY timestamp DESC LIMIT 80',
                (f'%{sym}%',),
            )
            for row in cursor.fetchall():
                msg = row['message'] or ''
                m = pattern.search(msg)
                if m:
                    try:
                        price = float(m.group(1))
                    except (TypeError, ValueError):
                        continue
                    if price > 0:
                        return {
                            'entry_price': price,
                            'source': 'log',
                            'qty_tracked': 0.0,
                        }
        return None

    def _cost_basis_from_sell_pnl(self, symbol: str):
        """Infiere entry desde la última venta del bot (close_position guarda pnl_pct)."""
        with self._get_connection() as conn:
            row = conn.execute(
                '''
                SELECT price, pnl_pct FROM trades
                WHERE symbol = ? AND lower(side) = 'sell' AND price > 0
                ORDER BY timestamp DESC LIMIT 1
                ''',
                (symbol,),
            ).fetchone()
        if not row or row['pnl_pct'] is None:
            return None
        try:
            exit_p = float(row['price'])
            pnl_pct = float(row['pnl_pct'])
        except (TypeError, ValueError):
            return None
        if exit_p <= 0:
            return None
        denom = 1.0 + (pnl_pct / 100.0)
        if denom <= 0:
            return None
        entry = exit_p / denom
        if entry <= 0:
            return None
        return {
            'entry_price': entry,
            'source': 'sell_pnl',
            'qty_tracked': 0.0,
        }

    def get_trades_history(self):
        with self._get_connection() as conn:
            df = pd.read_sql_query('SELECT * FROM trades ORDER BY timestamp ASC', conn)
            if not df.empty:
                df.rename(columns={
                    'timestamp': 'Date',
                    'symbol': 'Symbol',
                    'side': 'Side',
                    'price': 'Price',
                    'amount': 'Amount',
                    'pnl_pct': 'PnL_%',
                    'reason': 'Reason'
                }, inplace=True)
                df['Date'] = pd.to_datetime(df['Date'], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                df = pd.DataFrame(columns=['Date', 'Symbol', 'Side', 'Price', 'Amount', 'PnL_%', 'Reason'])
            return df

    # --- Equity Tracking ---
    def log_equity(self, total_value):
        """Graba el valor total de la cuenta para la curva de patrimonio"""
        with self._get_connection() as conn:
            conn.execute('INSERT INTO equity_history (total_value, timestamp) VALUES (?, ?)', (total_value, time.time()))
            conn.commit()

    def get_equity_history(self, limit=100):
        """Obtiene el historial de patrimonio para graficar (Últimos 100 puntos)"""
        with self._get_connection() as conn:
            # Leemos los últimos N puntos y luego los re-ordenamos para el gráfico
            df = pd.read_sql_query(f'''
                SELECT * FROM (
                    SELECT * FROM equity_history ORDER BY timestamp DESC LIMIT {limit}
                ) ORDER BY timestamp ASC
            ''', conn)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            return df

    def get_equity_reference_since(self, seconds=86400):
        """Primer punto de equity dentro de la ventana indicada; útil para límites diarios."""
        since_ts = time.time() - float(seconds)
        with self._get_connection() as conn:
            row = conn.execute(
                '''
                SELECT total_value, timestamp FROM equity_history
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT 1
                ''',
                (since_ts,),
            ).fetchone()
        if not row:
            return None
        return {
            'total_value': float(row['total_value'] or 0),
            'timestamp': float(row['timestamp'] or 0),
        }

    # --- Chat History ---
    def save_chat_message(self, role, content):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
            conn.commit()

    def get_chat_history(self, limit=50):
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT role, content, timestamp FROM chat_history ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def clear_chat_history(self):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM chat_history")
            conn.commit()

    # --- Macro Data (v6.0) ---
    def set_macro_data(self, symbol, price, change_24h):
        with self._get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO macro_data (symbol, price, change_24h, last_update)
                VALUES (?, ?, ?, ?)
            ''', (symbol, price, change_24h, time.time()))
            conn.commit()

    def get_all_macro_data(self):
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT * FROM macro_data')
            return {row['symbol']: dict(row) for row in cursor.fetchall()}
