import time
import os
import json
import sys
import config 
from exchange_helper import ExchangeHelper
from sentiment_engine import SentimentEngine
from trading_logic import TradingLogic
from database_manager import DatabaseManager
from decision_engine import DecisionEngine
from market_context import MarketContext
from i18n import _


def _configure_console_encoding():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_console_encoding()


BLOCKED_RADAR_BASES = {
    # Fiat / cash-like assets should never consume trading slots.
    "USD", "EUR", "GBP", "AUD", "CAD", "CHF", "JPY",
    # Stablecoins and wrapped cash proxies.
    "USDT", "USDC", "DAI", "TUSD", "FDUSD", "PYUSD", "BUSD", "USDP", "EURC",
}


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
        self.MACRO_INTERVAL = 900 # 15 min: actualiza 1 activo vencido por ciclo, sin bloquear

        self.log_message(_('LOG_DAEMON_INIT', lang=self.u_lang))

    def log_message(self, msg):
        text = f"[DAEMON] {msg}"
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            safe_text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(safe_text, flush=True)
        self.db.add_log(msg)

    def update_daemon_status(self, state, **extra):
        try:
            payload = json.loads(self.db.get_system_status("daemon_diagnostics", "{}") or "{}")
        except Exception:
            payload = {}
        payload.update({
            "state": state,
            "state_ts": time.time(),
            "lang": getattr(self, "u_lang", "es"),
            "watchlist_size": len(getattr(self, "active_symbols", []) or []),
        })
        if state == "cycle_done":
            payload["cycle_ts"] = payload["state_ts"]
        payload.update(extra)
        self.db.set_system_status("daemon_diagnostics", json.dumps(payload))

    def is_allowed_radar_symbol(self, symbol):
        try:
            base, quote = str(symbol).strip().upper().split("/", 1)
        except ValueError:
            return False
        if quote != "USDT":
            return False
        return base not in BLOCKED_RADAR_BASES

    def sanitize_watchlist(self, symbols):
        cleaned = []
        blocked = []
        for symbol in symbols or []:
            sym = str(symbol).strip().upper()
            if not sym:
                continue
            if "/" not in sym:
                sym = f"{sym}/USDT"
            if not self.is_allowed_radar_symbol(sym):
                blocked.append(sym)
                continue
            if sym not in cleaned:
                cleaned.append(sym)
        return cleaned, blocked

    def update_dynamic_watchlist(self):
        self.log_message(_('LOG_SCANNING_RADAR', lang=self.u_lang))
        try:
            raw_top = self.exchange.get_top_volume_symbols(limit=30)
            if not raw_top:
                self.log_message("⚠️ No se pudo obtener el ranking del exchange.")
                return
            curated = self.decision_engine.curate_watchlist(raw_top)
            curated, blocked = self.sanitize_watchlist(curated)
            if blocked:
                self.log_message(f"⚠️ Radar filtrado: excluidos {', '.join(blocked[:8])}")
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
            self.active_symbols, blocked = self.sanitize_watchlist(saved.split(','))
            if blocked:
                self.db.set_system_status('dynamic_watchlist', ",".join(self.active_symbols))
                self.log_message(f"⚠️ Radar guardado limpiado: excluidos {', '.join(blocked[:8])}")
        else:
            self.active_symbols, _ = self.sanitize_watchlist(config.SYMBOLS)

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
                
                # Refrescar idioma v7.14 (Forzar sincronización en cada ciclo)
                self.u_lang = self.db.get_system_status('language', 'es')
                self.sentiment.set_user_context(self.u_name, self.u_lang)
                self.decision_engine.current_lang = self.u_lang
                if hasattr(self.decision_engine, 'market_context'):
                    self.decision_engine.market_context.u_lang = self.u_lang
                self.market_context.u_lang = self.u_lang
                if hasattr(self.decision_engine, 'backtest_engine') and self.decision_engine.backtest_engine:
                    self.decision_engine.backtest_engine.u_lang = self.u_lang
                
                # Si detectamos cambio REAL, limpiamos caché
                if 'last_lang_check' not in locals() or last_lang_check != self.u_lang:
                    self.decision_engine.decision_cache = {}
                    last_lang_check = self.u_lang
                
                now = time.time()
                if now - self.last_watchlist_update > 43200:
                    self.update_dynamic_watchlist()
                    self.last_watchlist_update = now

                # Backtest semanal automático
                if now - self.last_backtest_run > self.BACKTEST_INTERVAL:
                    self.run_weekly_backtest()

                # Actualización macro incremental: 1 activo vencido cada intervalo
                if now - self.last_macro_update > self.MACRO_INTERVAL:
                    self.update_daemon_status("macro_refresh")
                    from macro_analyzer import MacroAnalyzer
                    macro = MacroAnalyzer(lang=self.u_lang)
                    macro.fetch_global_market_status(max_assets=1)
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
                self.update_daemon_status("sleeping", next_cycle_in=60)
                time.sleep(60)
            except Exception as e:
                self.update_daemon_status("error", error=str(e))
                self.log_message(f"Error crítico en daemon: {e}")
                time.sleep(30)

    def bot_iteration(self):
        print("[DAEMON] --- Escaneo de Ciclo ---")
        cycle_start = time.time()
        self.update_daemon_status("scanning", cycle_started_at=cycle_start)
        action_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
        providers = {}
        hold_reasons = {}
        scanned = 0
        skipped = {}
        
        # El balance total ya incluye el valor de todas las criptos en USDT
        total_value = self.exchange.get_balance()
        self.db.log_equity(total_value)
        
        # Límite dinámico basado en balance total (v6.1)
        self.dynamic_max = config.get_effective_max_positions(total_value)
        
        # Para el cálculo de cuánto podemos comprar, necesitamos el cash (USDT) disponible
        open_positions = self.db.get_open_positions()
        buy_candidates = []

        def candidate_score(item):
            decision = item.get('decision') or {}
            confidence = float(decision.get('confidence') or 0)
            confluence = float(decision.get('confluence_score') or 0)
            size_mult = float(decision.get('position_size_multiplier') or 1.0)
            # La confianza manda; MTF y sizing desempatan sin dominar.
            return confidence + (confluence * 0.15) + (size_mult * 0.03)

        def execute_buy_candidate(item):
            sym = item['symbol']
            price = float(item['price'])
            decision = item['decision']
            provider = item['provider']

            balance_usdt_actual = self.exchange.get_usdt_balance()
            amount_usdt = balance_usdt_actual * config.RISK_PER_TRADE

            if amount_usdt < 1.0:
                self.log_message(f"{ _('LOG_INSUFFICIENT', lang=self.u_lang) } ({balance_usdt_actual:.2f}) { _('LOG_FOR', lang=self.u_lang) } {sym}")
                return False

            amount_coin = amount_usdt / price
            res = self.exchange.execute_order(sym, 'buy', amount_coin, price)
            if res.get('status') in ['closed', 'simulated']:
                decision['entry_confidence'] = decision.get('confidence', 0.7)
                self.db.add_open_position(sym, price, price, amount_coin, extra_data=json.dumps(decision))
                open_positions[sym] = {'entry_price': price, 'amount': amount_coin}
                self.db.save_trade(
                    sym, 'buy', float(price), float(amount_coin),
                    f"BOT [{provider}]", 0.0,
                )
                self.log_message(
                    f"{ _('LOG_BUY', lang=self.u_lang) } {sym} @ {price} "
                    f"[{provider}] score={item['score']:.3f} conf={float(decision.get('confidence') or 0):.2f}"
                )
                return True

            self.log_message(f"❌ Fallo compra {sym}: {res.get('reason', res)}")
            return False

        for symbol in self.active_symbols:
            current_price = self.exchange.get_ticker(symbol)
            if not current_price:
                skipped["NO_PRICE"] = skipped.get("NO_PRICE", 0) + 1
                continue
            scanned += 1
            
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
            if not indicators:
                skipped["NO_INDICATORS"] = skipped.get("NO_INDICATORS", 0) + 1
                continue
            
            is_open = symbol in open_positions
            decision = self.decision_engine.get_decision(symbol, current_price, indicators, ohlcv, len(open_positions), is_open)
            if not decision:
                skipped["NO_DECISION"] = skipped.get("NO_DECISION", 0) + 1
                continue
            
            provider = decision.get('provider', 'IA')
            action = decision.get('action', 'HOLD')
            action_counts[action] = action_counts.get(action, 0) + 1
            providers[provider] = providers.get(provider, 0) + 1
            if action == "HOLD":
                reason = str(decision.get('reasoning', 'HOLD')).split("...")[0][:80]
                hold_reasons[reason] = hold_reasons.get(reason, 0) + 1
            # Guardar para UI (Global y por Símbolo)
            decision_json = json.dumps({
                'symbol': symbol,
                'reasoning': decision.get('reasoning', ''),
                'regime': decision.get('regime', 'N/A'),
                'best_strategy': decision.get('best_strategy', 'N/A'),
                'confidence': decision.get('confidence', 0),
                'action': decision.get('action', 'HOLD')
            })
            self.db.set_system_status('last_ia_decision', decision_json)
            self.db.set_system_status(f'decision_{symbol}', decision_json)
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
                        try:
                            sold = float(order_result.get('filled') or 0)
                        except (TypeError, ValueError):
                            sold = 0.0
                        if sold <= 0:
                            sold = float(pos['amount'])
                        sold = min(sold, float(pos['amount']))
                        closed = self.db.close_position(symbol, current_price, sell_res['reason'], sold_amount=sold)
                        if closed:
                            still = self.db.get_open_positions().get(symbol)
                            if still:
                                open_positions[symbol] = still
                            else:
                                del open_positions[symbol]
                            self.log_message(f"{ _('LOG_SELL', lang=self.u_lang) } {symbol} @ {current_price:.4f} | { _('LOG_REASON', lang=self.u_lang) }: {sell_res['reason']}")
                        else:
                            self.log_message(f"⚠️ Venta ejecutada pero posición {symbol} no encontrada en DB")
                    else:
                        self.log_message(f"❌ Fallo al vender {symbol}: {order_result.get('reason', 'Error desconocido')}")
            
            # 2. Lógica de COMPRA
            else:
                if decision['action'] == 'BUY':
                    item = {
                        'symbol': symbol,
                        'price': current_price,
                        'decision': decision,
                        'provider': provider,
                    }
                    item['score'] = candidate_score(item)
                    buy_candidates.append(item)

        buy_candidates.sort(key=lambda item: item['score'], reverse=True)
        if buy_candidates:
            top_preview = ", ".join(
                f"{c['symbol']}({c['score']:.3f}/{float(c['decision'].get('confidence') or 0):.2f})"
                for c in buy_candidates[:5]
            )
            self.log_message(f"🧮 Candidatos BUY rankeados: {top_preview}")

        executed_symbols = set()
        for candidate in buy_candidates:
            if len(open_positions) >= self.dynamic_max:
                break
            if candidate['symbol'] in open_positions:
                continue
            if execute_buy_candidate(candidate):
                executed_symbols.add(candidate['symbol'])

        remaining_candidates = [
            c for c in buy_candidates
            if c['symbol'] not in executed_symbols and c['symbol'] not in open_positions
        ]

        if config.ROTATION_ENABLED and len(open_positions) >= self.dynamic_max and remaining_candidates:
            pos_details = {}
            for s, p in open_positions.items():
                p_ticker = self.exchange.get_ticker(s)
                profit_pct = ((p_ticker - p['entry_price']) / p['entry_price']) * 100 if p_ticker else 0
                pos_details[s] = {'profit_pct': profit_pct, 'entry_confidence': p.get('entry_confidence', 0.65)}

            for candidate in remaining_candidates:
                decision = candidate['decision']
                to_sacrifice = self.decision_engine.evaluate_rotation_potential(decision, pos_details)
                if not to_sacrifice:
                    continue

                sym_sac = to_sacrifice['symbol']
                self.log_message(
                    f"{ _('LOG_ROTATION', lang=self.u_lang) }: { _('LOG_SACRIFICING', lang=self.u_lang) } "
                    f"{sym_sac} (+{to_sacrifice['profit']:.2f}%) { _('LOG_FOR', lang=self.u_lang) } "
                    f"{candidate['symbol']} (Conf: {decision.get('confidence')})"
                )
                sac_pos = open_positions[sym_sac]
                sac_price = self.exchange.get_ticker(sym_sac)
                if not sac_price:
                    self.log_message(f"⚠️ No se pudo obtener precio para rotar {sym_sac}, rotación cancelada")
                    break

                rot_res = self.exchange.execute_order(sym_sac, 'sell', sac_pos['amount'], sac_price)
                if rot_res.get('status') not in ['closed', 'simulated']:
                    self.log_message(f"❌ Fallo venta rotación {sym_sac}: {rot_res.get('reason', rot_res)}")
                    break

                try:
                    sold = float(rot_res.get('filled') or 0)
                except (TypeError, ValueError):
                    sold = 0.0
                if sold <= 0:
                    sold = float(sac_pos['amount'])
                sold = min(sold, float(sac_pos['amount']))
                self.db.close_position(sym_sac, sac_price, "ROTACIÓN IA", sold_amount=sold)
                still_sac = self.db.get_open_positions().get(sym_sac)
                if still_sac:
                    open_positions[sym_sac] = still_sac
                else:
                    del open_positions[sym_sac]
                self.log_message(f"{ _('LOG_ROTATION', lang=self.u_lang) } { _('LOG_EXECUTED', lang=self.u_lang) }: {sym_sac} { _('LOG_SOLD_AT', lang=self.u_lang) } {sac_price:.4f}")
                execute_buy_candidate(candidate)
                break

        diag = {
            "cycle_duration_s": round(time.time() - cycle_start, 2),
            "scanned": scanned,
            "actions": action_counts,
            "providers": providers,
            "hold_reasons": dict(sorted(hold_reasons.items(), key=lambda kv: kv[1], reverse=True)[:5]),
            "skipped": skipped,
            "buy_candidates": len(buy_candidates),
            "top_buy_candidates": [
                {
                    "symbol": c['symbol'],
                    "score": round(c['score'], 3),
                    "confidence": round(float(c['decision'].get('confidence') or 0), 3),
                }
                for c in buy_candidates[:5]
            ],
            "open_positions": len(open_positions),
            "dynamic_max": getattr(self, "dynamic_max", None),
        }
        self.update_daemon_status("cycle_done", **diag)

if __name__ == "__main__":
    daemon = BotDaemon()
    daemon.run()
