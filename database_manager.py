import sqlite3
import time
import os
import re
import json
import pandas as pd
from simulation_profiles import get_database_path_for_current_mode

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = get_database_path_for_current_mode()
        else:
            self.db_path = db_path
        self._init_db()
        self._seed_profile_status()

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

            # Provider Cooldowns (rate limits / API backoff persisted across restarts)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS provider_cooldowns (
                    provider TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    last_attempt REAL,
                    last_error TEXT,
                    cooldown_until REAL,
                    PRIMARY KEY (provider, scope)
                )
            ''')
            for column_name, column_def in {
                'last_attempt': 'REAL',
                'last_error': 'TEXT',
                'cooldown_until': 'REAL',
            }.items():
                try:
                    cursor.execute(f'ALTER TABLE provider_cooldowns ADD COLUMN {column_name} {column_def}')
                except sqlite3.OperationalError:
                    pass

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

            # Exchange Balance Watch: inventario real/simulado observado por el daemon.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exchange_balance_watch (
                    symbol TEXT PRIMARY KEY,
                    coin TEXT,
                    free REAL,
                    total REAL,
                    usd_free REAL,
                    usd_total REAL,
                    status TEXT,
                    min_amount REAL,
                    min_cost REAL,
                    missing_qty REAL,
                    target_price REAL,
                    in_open_position INTEGER,
                    first_seen REAL,
                    last_seen REAL,
                    last_transition REAL,
                    details TEXT
                )
            ''')
            for idx_name, idx_cols in {
                'idx_exchange_balance_watch_status': 'status',
                'idx_exchange_balance_watch_seen': 'last_seen',
            }.items():
                cursor.execute(
                    f'CREATE INDEX IF NOT EXISTS {idx_name} ON exchange_balance_watch ({idx_cols})'
                )

            # AI Usage Events: presupuesto preventivo de requests/tokens estimados.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    provider TEXT,
                    feature TEXT,
                    prompt_hash TEXT,
                    estimated_input_tokens INTEGER,
                    estimated_output_tokens INTEGER,
                    success INTEGER,
                    blocked_reason TEXT
                )
            ''')
            for idx_name, idx_cols in {
                'idx_ai_usage_ts': 'timestamp',
                'idx_ai_usage_provider_feature': 'provider, feature',
            }.items():
                cursor.execute(
                    f'CREATE INDEX IF NOT EXISTS {idx_name} ON ai_usage_events ({idx_cols})'
                )
            
            conn.commit()

    def _seed_profile_status(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        main_db = os.path.join(base_dir, "iversoria.db")
        if os.path.abspath(self.db_path) == os.path.abspath(main_db) or not os.path.exists(main_db):
            return
        keys = ['user_name', 'language', 'risk_profile', 'onboarding_completed']
        try:
            with self._get_connection() as target, sqlite3.connect(main_db, timeout=5) as source:
                target_count = target.execute(
                    "SELECT COUNT(*) FROM system_status WHERE key IN ({})".format(",".join("?" for _ in keys)),
                    keys,
                ).fetchone()[0]
                if target_count:
                    return
                rows = source.execute(
                    "SELECT key, value FROM system_status WHERE key IN ({})".format(",".join("?" for _ in keys)),
                    keys,
                ).fetchall()
                if rows:
                    target.executemany(
                        "INSERT OR REPLACE INTO system_status (key, value) VALUES (?, ?)",
                        [(row[0], row[1]) for row in rows],
                    )
                    target.commit()
        except Exception:
            pass

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

    def upsert_exchange_balance_watch(self, payload):
        now = time.time()
        symbol = str(payload.get('symbol') or '').strip().upper()
        if not symbol:
            coin = str(payload.get('coin') or '').strip().upper() or 'UNKNOWN'
            symbol = f"UNROUTABLE:{coin}"
        status = str(payload.get('status') or 'UNKNOWN')
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT status, first_seen, last_transition FROM exchange_balance_watch WHERE symbol = ?',
                (symbol,),
            ).fetchone()
            first_seen = float(row['first_seen']) if row and row['first_seen'] else now
            previous_status = row['status'] if row else None
            last_transition = float(row['last_transition']) if row and row['last_transition'] else now
            transitioned = bool(previous_status and previous_status != status)
            if transitioned:
                last_transition = now
            conn.execute(
                '''
                INSERT OR REPLACE INTO exchange_balance_watch
                    (symbol, coin, free, total, usd_free, usd_total, status,
                     min_amount, min_cost, missing_qty, target_price, in_open_position,
                     first_seen, last_seen, last_transition, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    symbol,
                    str(payload.get('coin') or ''),
                    float(payload.get('free') or 0),
                    float(payload.get('total') or 0),
                    float(payload.get('usd_free') or 0),
                    float(payload.get('usd_total') or 0),
                    status,
                    float(payload.get('min_amount') or 0),
                    float(payload.get('min_cost') or 0),
                    float(payload.get('missing_qty') or 0),
                    float(payload.get('target_price') or 0),
                    1 if payload.get('in_open_position') else 0,
                    first_seen,
                    now,
                    last_transition,
                    self._json_or_none(payload.get('details') or {}),
                ),
            )
            conn.commit()
        return {
            'symbol': symbol,
            'previous_status': previous_status,
            'status': status,
            'transitioned': transitioned,
        }

    def get_exchange_balance_watch(self, limit=500):
        limit = max(1, min(int(limit), 5000))
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''
                SELECT * FROM exchange_balance_watch
                ORDER BY usd_total DESC, last_seen DESC
                LIMIT ?
                ''',
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_exchange_balance_watch_summary(self):
        with self._get_connection() as conn:
            rows = conn.execute(
                '''
                SELECT status, COUNT(*) AS count, SUM(usd_total) AS usd_total
                FROM exchange_balance_watch
                GROUP BY status
                '''
            ).fetchall()
        return {
            row['status']: {
                'count': int(row['count'] or 0),
                'usd_total': float(row['usd_total'] or 0),
            }
            for row in rows
        }

    def record_ai_usage(
        self,
        provider,
        feature,
        prompt_hash,
        estimated_input_tokens=0,
        estimated_output_tokens=0,
        success=True,
        blocked_reason='',
        timestamp=None,
    ):
        ts = time.time() if timestamp is None else float(timestamp)
        with self._get_connection() as conn:
            conn.execute(
                '''
                INSERT INTO ai_usage_events
                    (timestamp, provider, feature, prompt_hash, estimated_input_tokens,
                     estimated_output_tokens, success, blocked_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    ts,
                    str(provider or ''),
                    str(feature or 'general'),
                    str(prompt_hash or ''),
                    int(estimated_input_tokens or 0),
                    int(estimated_output_tokens or 0),
                    1 if success else 0,
                    str(blocked_reason or ''),
                ),
            )
            conn.commit()

    def get_ai_usage_summary(self, since_ts=None):
        if since_ts is None:
            since_ts = time.time() - 86400
        with self._get_connection() as conn:
            row = conn.execute(
                '''
                SELECT
                    COUNT(*) AS requests,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS blocked,
                    SUM(estimated_input_tokens) AS input_tokens,
                    SUM(estimated_output_tokens) AS output_tokens
                FROM ai_usage_events
                WHERE timestamp >= ?
                ''',
                (float(since_ts),),
            ).fetchone()
            by_feature = conn.execute(
                '''
                SELECT feature, COUNT(*) AS requests,
                       SUM(estimated_input_tokens + estimated_output_tokens) AS tokens
                FROM ai_usage_events
                WHERE timestamp >= ?
                GROUP BY feature
                ''',
                (float(since_ts),),
            ).fetchall()
        return {
            'requests': int(row['requests'] or 0) if row else 0,
            'successes': int(row['successes'] or 0) if row else 0,
            'blocked': int(row['blocked'] or 0) if row else 0,
            'input_tokens': int(row['input_tokens'] or 0) if row else 0,
            'output_tokens': int(row['output_tokens'] or 0) if row else 0,
            'estimated_tokens': int((row['input_tokens'] or 0) + (row['output_tokens'] or 0)) if row else 0,
            'by_feature': {
                item['feature']: {
                    'requests': int(item['requests'] or 0),
                    'tokens': int(item['tokens'] or 0),
                }
                for item in by_feature
            },
        }

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

    def get_provider_cooldown(self, provider, scope='global'):
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''
                SELECT provider, scope, last_attempt, last_error, cooldown_until
                FROM provider_cooldowns
                WHERE provider = ? AND scope = ?
                ''',
                (provider, scope),
            )
            row = cursor.fetchone()
            if not row and str(scope or 'global') == 'global':
                row = conn.execute(
                    '''
                    SELECT provider, scope, last_attempt, last_error, cooldown_until
                    FROM provider_cooldowns
                    WHERE provider = ? AND scope = ''
                    ''',
                    (provider,),
                ).fetchone()
            if not row:
                return {
                    'provider': provider,
                    'scope': scope,
                    'last_attempt': 0.0,
                    'last_error': '',
                    'cooldown_until': 0.0,
                }
            data = dict(row)
            data['last_attempt'] = float(data.get('last_attempt') or 0)
            data['cooldown_until'] = float(data.get('cooldown_until') or 0)
            data['last_error'] = data.get('last_error') or ''
            data['reason'] = data['last_error']
            data['updated_at'] = data['last_attempt']
            return data

    def set_provider_cooldown(
        self,
        provider,
        cooldown_until=0,
        reason='',
        scope='global',
        last_attempt=None,
        last_error=None,
    ):
        if last_attempt is None:
            last_attempt = time.time()
        if last_error is not None:
            reason = last_error
        with self._get_connection() as conn:
            conn.execute(
                '''
                INSERT OR REPLACE INTO provider_cooldowns
                    (provider, scope, last_attempt, last_error, cooldown_until)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    str(provider),
                    str(scope or 'global'),
                    float(last_attempt or 0),
                    str(reason or ''),
                    float(cooldown_until or 0),
                ),
            )
            conn.commit()

    def clear_provider_cooldown(self, provider, scope='global'):
        with self._get_connection() as conn:
            conn.execute(
                'DELETE FROM provider_cooldowns WHERE provider = ? AND scope = ?',
                (str(provider), str(scope or 'global')),
            )
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

    def get_adaptive_edge_snapshot(self, limit=1000, min_trades=5):
        """
        Resume el edge realizado del decision_journal para ajustar el score de forma conservadora.
        Devuelve solo datos con muestra mínima suficiente; si no hay datos, el motor no cambia.
        """
        df = self.get_decision_journal(limit=limit)
        if df.empty:
            return {
                'enabled': False,
                'global': None,
                'by_provider': {},
                'by_regime': {},
                'by_strategy': {},
                'by_symbol': {},
            }

        realized = pd.to_numeric(
            df['realized_pnl_pct'] if 'realized_pnl_pct' in df.columns else pd.Series([None] * len(df)),
            errors='coerce',
        )
        closed = df[realized.notna()].copy()
        if closed.empty:
            return {
                'enabled': False,
                'global': None,
                'by_provider': {},
                'by_regime': {},
                'by_strategy': {},
                'by_symbol': {},
            }
        closed['realized_pnl_pct'] = pd.to_numeric(closed['realized_pnl_pct'], errors='coerce')
        closed = closed.dropna(subset=['realized_pnl_pct'])
        if closed.empty:
            return {
                'enabled': False,
                'global': None,
                'by_provider': {},
                'by_regime': {},
                'by_strategy': {},
                'by_symbol': {},
            }

        def summarize(group):
            pnl = pd.to_numeric(group['realized_pnl_pct'], errors='coerce').dropna()
            trades = len(pnl)
            wins = pnl[pnl > 0]
            losses = pnl[pnl <= 0]
            win_rate = len(wins) / trades * 100 if trades else 0.0
            expectancy = pnl.mean() if trades else 0.0
            profit_sum = wins.sum()
            loss_sum = abs(losses.sum())
            profit_factor = profit_sum / loss_sum if loss_sum > 0 else (profit_sum if profit_sum > 0 else 0.0)
            # Ajuste deliberadamente pequeño: convierte edge realizado a una señal [-0.12, +0.12] aprox.
            adjustment = (expectancy / 25.0) + ((min(profit_factor, 3.0) - 1.0) * 0.035) + ((win_rate - 50.0) / 1000.0)
            adjustment = max(-0.20, min(0.20, adjustment))
            return {
                'trades': int(trades),
                'win_rate': round(win_rate, 1),
                'expectancy_pct': round(expectancy, 3),
                'profit_factor': round(float(profit_factor), 3),
                'adjustment': round(float(adjustment), 4),
            }

        def grouped(column):
            if column not in closed.columns:
                return {}
            out = {}
            for name, group in closed.groupby(column):
                key = str(name or '').strip()
                if not key:
                    continue
                stats = summarize(group)
                if stats['trades'] >= int(min_trades):
                    out[key] = stats
            return out

        closed_sorted = closed.sort_values('timestamp') if 'timestamp' in closed.columns else closed
        window = max(int(min_trades), min(50, len(closed_sorted)))
        recent = closed_sorted.tail(window)
        older = closed_sorted.iloc[:-window]
        recent_exp = float(pd.to_numeric(recent['realized_pnl_pct'], errors='coerce').mean()) if not recent.empty else 0.0
        older_exp = float(pd.to_numeric(older['realized_pnl_pct'], errors='coerce').mean()) if not older.empty else recent_exp

        return {
            'enabled': True,
            'min_trades': int(min_trades),
            'global': summarize(closed),
            'rolling_expectancy_pct': round(recent_exp, 3),
            'edge_decay_pct': round(recent_exp - older_exp, 3),
            'by_provider': grouped('provider'),
            'by_regime': grouped('regime'),
            'by_strategy': grouped('strategy'),
            'by_symbol': grouped('symbol'),
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
