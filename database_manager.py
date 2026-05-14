import sqlite3
import time
import os
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
            
            # Cooldowns
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cooldowns (
                    symbol TEXT PRIMARY KEY,
                    timestamp REAL
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
            # Keep only last 50
            conn.execute('DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY timestamp DESC LIMIT 50)')
            conn.commit()

    def get_logs(self):
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT message FROM logs ORDER BY timestamp ASC')
            return [row['message'] for row in cursor.fetchall()]

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
            conn.execute('''
                INSERT INTO trades (symbol, side, price, amount, reason, pnl_pct, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, side, price, amount, reason, pnl_pct, timestamp))
            conn.commit()

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
        """Obtiene el historial de patrimonio para graficar"""
        with self._get_connection() as conn:
            df = pd.read_sql_query(f'SELECT * FROM equity_history ORDER BY timestamp ASC LIMIT {limit}', conn)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            return df
