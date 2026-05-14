import time
import os
import json
import config 
from exchange_helper import ExchangeHelper
from sentiment_engine import SentimentEngine
from trading_logic import TradingLogic
from database_manager import DatabaseManager
from decision_engine import DecisionEngine

class BotDaemon:
    def __init__(self):
        self.db = DatabaseManager()
        self.exchange = ExchangeHelper()
        self.sentiment = SentimentEngine()
        self.logic = TradingLogic()
        self.decision_engine = DecisionEngine()
        self.active_symbols = config.SYMBOLS
        self.last_watchlist_update = 0
        self.log_message("Bot Daemon v3.5 [ROTACIÓN INTELIGENTE] Inicializado.")

    def log_message(self, msg):
        print(f"[DAEMON] {msg}")
        self.db.add_log(msg)

    def update_dynamic_watchlist(self):
        self.log_message("🛰️ Escaneando radar de mercado (Top Volumen)...")
        try:
            raw_top = self.exchange.get_top_volume_symbols(limit=30)
            if not raw_top:
                self.log_message("⚠️ No se pudo obtener el ranking del exchange.")
                return
            curated = self.decision_engine.curate_watchlist(raw_top)
            if curated:
                self.active_symbols = curated
                self.db.set_system_status('dynamic_watchlist', ",".join(curated))
                self.log_message(f"✅ Watchlist actualizada: {', '.join(curated)}")
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

    def run(self):
        self.load_active_watchlist()
        while True:
            try:
                # Recargar configuración activa cada ciclo para captar cambios en UI
                import config
                import importlib
                importlib.reload(config)
                
                now = time.time()
                if now - self.last_watchlist_update > 43200:
                    self.update_dynamic_watchlist()
                    self.last_watchlist_update = now
                    
                is_running = self.db.get_system_status('is_running')
                if str(is_running).lower() == 'true':
                    is_sim_str = self.db.get_system_status('simulacion', 'true')
                    is_sim = str(is_sim_str).lower() == 'true'
                    if self.exchange.modo_simulacion != is_sim:
                        self.exchange = ExchangeHelper(modo_simulacion=is_sim)
                        self.log_message(f"Modo cambiado a {'Simulación' if is_sim else 'REAL'}.")
                    self.bot_iteration()
                time.sleep(60)
            except Exception as e:
                self.log_message(f"Error crítico en daemon: {e}")
                time.sleep(30)

    def bot_iteration(self):
        self.log_message("--- Escaneo de Ciclo ---")
        
        # El balance total ya incluye el valor de todas las criptos en USDT
        total_value = self.exchange.get_balance()
        self.db.log_equity(total_value)
        
        # Para el cálculo de cuánto podemos comprar, necesitamos el cash (USDT) disponible
        balance_usdt = self.exchange.get_usdt_balance()
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
                    self.log_message(f"[{symbol}] Posición adoptada.")

            # Análisis
            ohlcv = self.exchange.get_historical_data(symbol)
            indicators = self.logic.calculate_indicators(ohlcv)
            if not indicators: continue
            
            is_open = symbol in open_positions
            decision = self.decision_engine.get_decision(symbol, current_price, indicators, ohlcv, len(open_positions), is_open)
            if not decision: continue
            
            provider = decision.get('provider', 'IA')
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
                    self.exchange.execute_order(symbol, 'sell', pos['amount'], current_price)
                    self.db.close_position(symbol, current_price, sell_res['reason'])
                    self.log_message(f"💰 VENTA {symbol} @ {current_price} - Motivo: {sell_res['reason']}")
                    del open_positions[symbol]
            
            # 2. Lógica de COMPRA
            else:
                if decision['action'] == 'BUY':
                    # ¿Límite alcanzado? -> Evaluar ROTACIÓN
                    if len(open_positions) >= config.MAX_OPEN_POSITIONS:
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
                                self.log_message(f"🔄 ROTACIÓN: Sacrificando {sym_sac} (+{to_sacrifice['profit']:.2f}%) por {symbol} (Conf: {decision['confidence']})")
                                sac_pos = open_positions[sym_sac]
                                self.exchange.execute_order(sym_sac, 'sell', sac_pos['amount'], self.exchange.get_ticker(sym_sac))
                                self.db.close_position(sym_sac, self.exchange.get_ticker(sym_sac), "ROTACIÓN IA")
                                del open_positions[sym_sac]
                                # Proceder a comprar la nueva
                            else:
                                continue # No hubo rotación aprobada
                        else:
                            continue # Rotación desactivada
                    
                    # Ejecutar Compra
                    amount_usdt = balance * config.RISK_PER_TRADE
                    amount_coin = amount_usdt / current_price
                    res = self.exchange.execute_order(symbol, 'buy', amount_coin, current_price)
                    if res.get('status') in ['closed', 'simulated']:
                        decision['entry_confidence'] = decision.get('confidence', 0.7)
                        self.db.add_open_position(symbol, current_price, current_price, amount_coin, extra_data=json.dumps(decision))
                        open_positions[symbol] = {'entry_price': current_price, 'amount': amount_coin}
                        self.log_message(f"🚀 COMPRA {symbol} @ {current_price} [{provider}]")

if __name__ == "__main__":
    daemon = BotDaemon()
    daemon.run()
