import time
import os
import json
import config 
from exchange_helper import ExchangeHelper
from sentiment_engine import SentimentEngine
from trading_logic import TradingLogic
from database_manager import DatabaseManager
from decision_engine import DecisionEngine
from market_context import MarketContext
from i18n import _

class BotDaemon:
    def __init__(self):
        self.db = DatabaseManager()
        self.exchange = ExchangeHelper()
        self.sentiment = SentimentEngine()
        
        # Cargar contexto de usuario v7.0
        self.u_name = self.db.get_system_status('user_name', 'User')
        self.u_lang = self.db.get_system_status('language', 'es')
        self.sentiment.set_user_context(self.u_name, self.u_lang)
        
        self.logic = TradingLogic()
        self.decision_engine = DecisionEngine(
            sentiment=self.sentiment,
            exchange=self.exchange,
            lang=self.u_lang
        )
        self.market_context = MarketContext(lang=self.u_lang)
        
        self.active_symbols = config.SYMBOLS
        self.last_watchlist_update = 0

        # Control del backtest automático semanal
        self.last_backtest_run = 0
        self.BACKTEST_INTERVAL = 604800  # 7 días en segundos

        # Control macro v6.0
        from macro_analyzer import MacroAnalyzer
        self.macro_analyzer = MacroAnalyzer()
        self.last_macro_update = 0
        self.MACRO_INTERVAL = 21600 # 6 horas

        self.log_message(_('LOG_DAEMON_INIT', lang=self.u_lang))

    def log_message(self, msg):
        print(f"[DAEMON] {msg}")
        self.db.add_log(msg)

    def update_dynamic_watchlist(self):
        self.log_message(_('LOG_SCANNING_RADAR', lang=self.u_lang))
        try:
            raw_top = self.exchange.get_top_volume_symbols(limit=30)
            if not raw_top:
                self.log_message("⚠️ No se pudo obtener el ranking del exchange.")
                return
            curated = self.decision_engine.curate_watchlist(raw_top)
            if curated:
                self.active_symbols = curated
                self.db.set_system_status('dynamic_watchlist', ",".join(curated))
                self.log_message(f"{ _('LOG_WATCHLIST_UPDATED', lang=self.u_lang) }: {', '.join(curated)}")
            else:
                self.log_message("⚠️ La IA no devolvió una lista válida.")
        except Exception as e:
            self.log_message(f"❌ Error crítico en radar: {e}")

    def load_active_watchlist(self):
        saved = self.db.get_system_status('dynamic_watchlist')
        if saved:
            self.active_symbols = [s.strip() for s in saved.split(',') if s.strip()]
        else:
            self.active_symbols = config.SYMBOLS

    def run_weekly_backtest(self):
        # ...
        from backtest_engine import BacktestEngine

        self.log_message(_('LOG_BACKTEST_START', lang=self.u_lang))
        bt = BacktestEngine(self.exchange, lang=self.u_lang)

        # Correr backtest para los primeros 5 símbolos de la watchlist activa
        # (limitar para no tardar demasiado en el primer ciclo)
        symbols_to_backtest = self.active_symbols[:5]

        for symbol in symbols_to_backtest:
            try:
                self.log_message(f"📊 Backtest {symbol} (4h · 2 { _('LOG_YEARS', lang=self.u_lang) })...")
                results = bt.run_full_backtest(symbol, timeframe='4h', years=2.0)
                if results:
                    best = max(results, key=lambda k: results[k].get('profit_factor', 0))
                    best_wr = results[best].get('win_rate', 0)
                    self.log_message(
                        f"✅ {symbol}: { _('LOG_BEST_STRAT_IS', lang=self.u_lang) } {best} "
                        f"(WR: {best_wr:.0%})"
                    )
            except Exception as e:
                self.log_message(f"❌ Error en backtest de {symbol}: {e}")

        self.last_backtest_run = time.time()
        self.log_message(_('LOG_BACKTEST_DONE', lang=self.u_lang))

    def run(self):
        self.load_active_watchlist()

        # Correr backtest inicial si no hay datos históricos
        now = time.time()
        if now - self.last_backtest_run > self.BACKTEST_INTERVAL:
            self.run_weekly_backtest()
            self.last_backtest_run = now

        while True:
            try:
                # Recargar configuración activa cada ciclo para captar cambios en UI
                import config
                import importlib
                importlib.reload(config)
                
                # Refrescar idioma v7.3
                self.u_lang = self.db.get_system_status('language', 'es')
                self.sentiment.set_user_context(self.u_name, self.u_lang)
                
                now = time.time()
                if now - self.last_watchlist_update > 43200:
                    self.update_dynamic_watchlist()
                    self.last_watchlist_update = now

                # Backtest semanal automático
                if now - self.last_backtest_run > self.BACKTEST_INTERVAL:
                    self.run_weekly_backtest()

                # Actualización Macro v6.0 (cada 6h)
                if now - self.last_macro_update > self.MACRO_INTERVAL:
                    from macro_analyzer import MacroAnalyzer
                    macro = MacroAnalyzer(lang=self.u_lang)
                    macro.fetch_global_market_status()
                    self.last_macro_update = now
                    
                is_running = self.db.get_system_status('is_running')
                if str(is_running).lower() == 'true':
                    is_sim_str = self.db.get_system_status('simulacion', 'true')
                    is_sim = str(is_sim_str).lower() == 'true'
                    if self.exchange.modo_simulacion != is_sim:
                        self.exchange = ExchangeHelper(modo_simulacion=is_sim)
                        # Recrear decision_engine con el nuevo exchange
                        self.decision_engine = DecisionEngine(
                            sentiment=self.sentiment,
                            exchange=self.exchange
                        )
                        mode_name = _('MODE_SIM', lang=self.u_lang) if is_sim else _('MODE_REAL', lang=self.u_lang)
                        self.log_message(f"{ _('LOG_MODE_CHANGED', lang=self.u_lang) } {mode_name}")
                
                # Asegurar que el saldo inicial REAL esté fijado si estamos en ese modo
                if not is_sim:
                    real_start = self.db.get_system_status('real_start_balance')
                    if not real_start:
                        current_equity = self.exchange.get_balance()
                        self.db.set_system_status('real_start_balance', current_equity)
                        self.log_message(f"{ _('LOG_INITIAL_REAL', lang=self.u_lang) } ${current_equity:.2f}")

                self.bot_iteration()
                time.sleep(60)
            except Exception as e:
                self.log_message(f"Error crítico en daemon: {e}")
                time.sleep(30)

    def bot_iteration(self):
        print("[DAEMON] --- Escaneo de Ciclo ---")
        
        # El balance total ya incluye el valor de todas las criptos en USDT
        total_value = self.exchange.get_balance()
        self.db.log_equity(total_value)
        
        # Límite dinámico basado en balance total (v6.1)
        self.dynamic_max = config.get_dynamic_max_positions(total_value)
        
        # Para el cálculo de cuánto podemos comprar, necesitamos el cash (USDT) disponible
        open_positions = self.db.get_open_positions()

        for symbol in self.active_symbols:
            current_price = self.exchange.get_ticker(symbol)
            if not current_price: continue
            
            # Adopción de posiciones externas
            if symbol not in open_positions:
                coin_amount = self.exchange.get_coin_balance(symbol)
                if (coin_amount * current_price) > 5.0:
                    self.db.add_open_position(symbol, current_price, current_price, coin_amount)
                    open_positions[symbol] = {'entry_price': current_price, 'amount': coin_amount}
                    self.log_message(f"[{symbol}] { _('LOG_POS_ADOPTED', lang=self.u_lang) }.")

            # Análisis
            ohlcv = self.exchange.get_historical_data(symbol)
            indicators = self.logic.calculate_indicators(ohlcv)
            if not indicators: continue
            
            is_open = symbol in open_positions
            decision = self.decision_engine.get_decision(symbol, current_price, indicators, ohlcv, len(open_positions), is_open)
            if not decision: continue
            
            provider = decision.get('provider', 'IA')
            # Guardar para UI
            self.db.set_system_status('last_ia_decision', json.dumps({
                'symbol': symbol,
                'reasoning': decision.get('reasoning', ''),
                'regime': decision.get('regime', 'N/A')
            }))
            # Mostrar progreso
            print(f"[DAEMON] {symbol}: {decision['action']} [{provider}] - {decision.get('reasoning')[:40]}...")
            
            # 1. Lógica de VENTA (Si ya está abierta)
            if is_open:
                pos = open_positions[symbol]
                
                # Actualizar precio máximo para Trailing Stop
                if current_price > pos.get('highest_price', 0):
                    self.db.update_highest_price(symbol, current_price)
                    pos['highest_price'] = current_price
                
                # Trailing Stop y AI Sell
                sell_res = self.logic.check_sell_conditions(symbol, current_price, pos, decision)
                if sell_res['should_sell']:
                    order_result = self.exchange.execute_order(symbol, 'sell', pos['amount'], current_price)
                    if order_result.get('status') in ['closed', 'simulated']:
                        closed = self.db.close_position(symbol, current_price, sell_res['reason'])
                        if closed:
                            self.log_message(f"{ _('LOG_SELL', lang=self.u_lang) } {symbol} @ {current_price:.4f} | { _('LOG_REASON', lang=self.u_lang) }: {sell_res['reason']}")
                            del open_positions[symbol]
                        else:
                            self.log_message(f"⚠️ Venta ejecutada pero posición {symbol} no encontrada en DB")
                    else:
                        self.log_message(f"❌ Fallo al vender {symbol}: {order_result.get('reason', 'Error desconocido')}")
            
            # 2. Lógica de COMPRA
            else:
                if decision['action'] == 'BUY':
                    # ¿Límite alcanzado? -> Evaluar ROTACIÓN
                    if len(open_positions) >= self.dynamic_max:
                        # Guardar estado para la UI (v7.10.1)
                        limit_reason = _('FILTER_POS_LIMIT', lang=self.u_lang)
                        self.db.set_system_status('last_ia_decision', json.dumps({
                            'symbol': symbol,
                            'reasoning': limit_reason,
                            'regime': 'LIMIT'
                        }))

                        if config.ROTATION_ENABLED:
                            # Preparar datos de posiciones actuales para comparar
                            pos_details = {}
                            for s, p in open_positions.items():
                                p_ticker = self.exchange.get_ticker(s)
                                profit_pct = ((p_ticker - p['entry_price']) / p['entry_price']) * 100 if p_ticker else 0
                                pos_details[s] = {'profit_pct': profit_pct, 'entry_confidence': p.get('entry_confidence', 0.65)}
                            
                            to_sacrifice = self.decision_engine.evaluate_rotation_potential(decision, pos_details)
                            if to_sacrifice:
                                sym_sac = to_sacrifice['symbol']
                                self.log_message(f"{ _('LOG_ROTATION', lang=self.u_lang) }: { _('LOG_SACRIFICING', lang=self.u_lang) } {sym_sac} (+{to_sacrifice['profit']:.2f}%) { _('LOG_FOR', lang=self.u_lang) } {symbol} (Conf: {decision['confidence']})")
                                sac_pos = open_positions[sym_sac]
                                sac_price = self.exchange.get_ticker(sym_sac)
                                if sac_price:
                                    self.exchange.execute_order(sym_sac, 'sell', sac_pos['amount'], sac_price)
                                    self.db.close_position(sym_sac, sac_price, "ROTACIÓN IA")
                                    del open_positions[sym_sac]
                                    self.log_message(f"{ _('LOG_ROTATION', lang=self.u_lang) } { _('LOG_EXECUTED', lang=self.u_lang) }: {sym_sac} { _('LOG_SOLD_AT', lang=self.u_lang) } {sac_price:.4f}")
                                else:
                                    self.log_message(f"⚠️ No se pudo obtener precio para rotar {sym_sac}, rotación cancelada")
                                    continue
                                # Proceder a comprar la nueva
                            else:
                                continue # No hubo rotación aprobada
                        else:
                            continue # Rotación desactivada
                    
                    # Re-obtener el balance real en cada compra para evitar sobrecompra
                    balance_usdt_actual = self.exchange.get_usdt_balance()
                    amount_usdt = balance_usdt_actual * config.RISK_PER_TRADE

                    if amount_usdt < 1.0:  # Guard mínimo: no comprar si quedan menos de 1 USDT
                        self.log_message(f"{ _('LOG_INSUFFICIENT', lang=self.u_lang) } ({balance_usdt_actual:.2f}) { _('LOG_FOR', lang=self.u_lang) } {symbol}")
                        continue
                    amount_coin = amount_usdt / current_price
                    res = self.exchange.execute_order(symbol, 'buy', amount_coin, current_price)
                    if res.get('status') in ['closed', 'simulated']:
                        decision['entry_confidence'] = decision.get('confidence', 0.7)
                        self.db.add_open_position(symbol, current_price, current_price, amount_coin, extra_data=json.dumps(decision))
                        open_positions[symbol] = {'entry_price': current_price, 'amount': amount_coin}
                        self.log_message(f"{ _('LOG_BUY', lang=self.u_lang) } {symbol} @ {current_price} [{provider}]")

if __name__ == "__main__":
    daemon = BotDaemon()
    daemon.run()
