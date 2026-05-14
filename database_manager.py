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
            conn.execute('DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY timestamp DESC LIMIT 100)')
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
