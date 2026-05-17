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
        self._last_idle_log = 0

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

    def is_consultive_mode(self):
        return getattr(config, "TRADING_EXECUTION_MODE", "auto") == "consultive"

    def _safe_float(self, value, default=0.0):
        try:
            f = float(value)
            if f != f:
                return default
            return f
        except (TypeError, ValueError):
            return default

    def _clamp(self, value, low, high):
        return max(low, min(high, value))

    def _fmt_pct(self, value, decimals=0, signed=False):
        val = self._safe_float(value, 0.0) * 100 if abs(self._safe_float(value, 0.0)) <= 1 else self._safe_float(value, 0.0)
        sign = "+" if signed else ""
        return f"{val:{sign}.{decimals}f}%"

    def _short_reason(self, text, max_len=72):
        clean = " ".join(str(text or "").split())
        if len(clean) <= max_len:
            return clean or "-"
        return clean[: max_len - 1].rstrip() + "…"

    def _backtest_status(self, result):
        pf = self._safe_float((result or {}).get('profit_factor'), 0.0)
        ret = self._safe_float((result or {}).get('total_return_pct'), 0.0)
        wr = self._safe_float((result or {}).get('win_rate'), 0.0)
        if pf >= 1.20 and ret > 0 and wr >= 0.45:
            return "strong"
        if pf >= 1.00 and ret >= 0:
            return "ok"
        if pf >= 0.85 or ret > -3:
            return "weak"
        return "poor"

    def _decision_log_line(self, symbol, decision, executable_action, provider):
        action = str(decision.get('action', 'HOLD')).upper()
        score = self._safe_float(decision.get('decision_score'), self._safe_float(decision.get('confidence'), 0.0))
        conf = self._safe_float(decision.get('confidence'), 0.0)
        adaptive = self._safe_float(decision.get('adaptive_adjustment'), 0.0)
        regime = decision.get('regime', 'N/A')
        strategy = decision.get('best_strategy', 'N/A')
        reason = self._short_reason(decision.get('reasoning', ''), 78)
        return (
            f"[DECISION] {symbol} {action} | exec={executable_action} | "
            f"score={score:.2f} | conf={conf:.2f} | adaptive={adaptive:+.3f} | "
            f"provider={provider} | regime={regime} | strategy={strategy} | reason={reason}"
        )

    def _position_extra(self, pos):
        raw = (pos or {}).get('extra_data')
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def portfolio_bucket(self, symbol):
        base = str(symbol or "").split("/", 1)[0].upper()
        for bucket, symbols in (getattr(config, "PORTFOLIO_BUCKETS", {}) or {}).items():
            if base in {str(s).upper() for s in symbols}:
                return str(bucket).upper()
        if base in {"BTC", "ETH"}:
            return base
        return "OTHER"

    def _open_exposure_usdt(self, open_positions):
        exposure = 0.0
        for sym, pos in (open_positions or {}).items():
            price = self.exchange.get_ticker(sym) or pos.get('entry_price') or 0
            exposure += float(pos.get('amount') or 0) * float(price or 0)
        return exposure

    def portfolio_exposures(self, open_positions):
        out = {"total": 0.0, "alt": 0.0, "symbols": {}, "buckets": {}}
        for sym, pos in (open_positions or {}).items():
            price = self.exchange.get_ticker(sym) or pos.get('entry_price') or 0
            value = self._safe_float(pos.get('amount')) * self._safe_float(price)
            if value <= 0:
                continue
            bucket = self.portfolio_bucket(sym)
            out["total"] += value
            out["symbols"][sym] = out["symbols"].get(sym, 0.0) + value
            out["buckets"][bucket] = out["buckets"].get(bucket, 0.0) + value
            if bucket not in {"BTC", "ETH"}:
                out["alt"] += value
        return out

    def evaluate_risk_guards(self, total_value, open_positions, pending_buy_usdt=0.0, pending_symbol=None):
        guards = {
            "ok": True,
            "reasons": [],
            "daily_loss_pct": 0.0,
            "exposure_pct": 0.0,
            "symbol_exposure_pct": 0.0,
            "alt_exposure_pct": 0.0,
            "bucket_exposure_pct": 0.0,
        }
        if total_value <= 0:
            guards["ok"] = False
            guards["reasons"].append("NO_EQUITY")
            return guards

        ref = self.db.get_equity_reference_since(86400)
        if ref and ref.get("total_value", 0) > 0:
            daily_loss_pct = ((float(ref["total_value"]) - float(total_value)) / float(ref["total_value"])) * 100
            guards["daily_loss_pct"] = round(max(0.0, daily_loss_pct), 2)
            if daily_loss_pct >= config.MAX_DAILY_LOSS_PCT * 100:
                guards["ok"] = False
                guards["reasons"].append(
                    f"DAILY_LOSS {daily_loss_pct:.2f}% >= {config.MAX_DAILY_LOSS_PCT * 100:.2f}%"
                )

        exposures = self.portfolio_exposures(open_positions)
        exposure = exposures["total"] + float(pending_buy_usdt or 0)
        exposure_pct = (exposure / float(total_value)) * 100 if total_value else 0.0
        guards["exposure_pct"] = round(exposure_pct, 2)
        if exposure_pct > config.MAX_PORTFOLIO_EXPOSURE_PCT * 100:
            guards["ok"] = False
            guards["reasons"].append(
                f"EXPOSURE {exposure_pct:.2f}% > {config.MAX_PORTFOLIO_EXPOSURE_PCT * 100:.2f}%"
            )
        guards["alt_exposure_pct"] = round((exposures["alt"] / float(total_value)) * 100, 2) if total_value else 0.0
        if exposures["buckets"] and total_value:
            guards["bucket_exposure_pct"] = round(
                max(exposures["buckets"].values()) / float(total_value) * 100,
                2,
            )
        if pending_symbol:
            bucket = self.portfolio_bucket(pending_symbol)
            symbol_value = exposures["symbols"].get(pending_symbol, 0.0) + float(pending_buy_usdt or 0)
            symbol_pct = (symbol_value / float(total_value)) * 100 if total_value else 0.0
            guards["symbol_exposure_pct"] = round(symbol_pct, 2)
            if symbol_pct > config.MAX_SYMBOL_EXPOSURE_PCT * 100:
                guards["ok"] = False
                guards["reasons"].append(
                    f"SYMBOL_EXPOSURE {pending_symbol} {symbol_pct:.2f}% > {config.MAX_SYMBOL_EXPOSURE_PCT * 100:.2f}%"
                )

            alt_value = exposures["alt"]
            if bucket not in {"BTC", "ETH"}:
                alt_value += float(pending_buy_usdt or 0)
            alt_pct = (alt_value / float(total_value)) * 100 if total_value else 0.0
            guards["alt_exposure_pct"] = round(alt_pct, 2)
            if alt_pct > config.MAX_ALT_EXPOSURE_PCT * 100:
                guards["ok"] = False
                guards["reasons"].append(
                    f"ALT_EXPOSURE {alt_pct:.2f}% > {config.MAX_ALT_EXPOSURE_PCT * 100:.2f}%"
                )

            bucket_value = exposures["buckets"].get(bucket, 0.0) + float(pending_buy_usdt or 0)
            bucket_pct = (bucket_value / float(total_value)) * 100 if total_value else 0.0
            guards["bucket"] = bucket
            guards["bucket_exposure_pct"] = round(bucket_pct, 2)
            if bucket_pct > config.MAX_BUCKET_EXPOSURE_PCT * 100:
                guards["ok"] = False
                guards["reasons"].append(
                    f"BUCKET_EXPOSURE {bucket} {bucket_pct:.2f}% > {config.MAX_BUCKET_EXPOSURE_PCT * 100:.2f}%"
                )
        return guards

    def calculate_position_size(self, symbol, price, indicators, decision, total_value, open_positions):
        balance_usdt = self.exchange.get_usdt_balance()
        base_amount = balance_usdt * config.RISK_PER_TRADE
        score = self._safe_float(decision.get('decision_score'), self._safe_float(decision.get('confidence'), 0.0))
        size_mult = self._safe_float(decision.get('position_size_multiplier'), 1.0)
        size_mult = self._clamp(size_mult, 0.25, config.MAX_VOLATILITY_POSITION_MULTIPLIER)
        adaptive_adjustment = self._safe_float(decision.get('adaptive_adjustment'), 0.0)
        adaptive_size_mult = self._clamp(1.0 + (adaptive_adjustment * 2.0), 0.75, 1.20)
        cap_amount = base_amount * max(0.1, config.MAX_VOLATILITY_POSITION_MULTIPLIER)

        atr = self._safe_float(indicators.get('atr'), 0.0)
        stop_mult = self._safe_float(decision.get('stop_loss_atr'), 2.0)
        stop_distance_pct = 0.0
        volatility_amount = base_amount
        reason = "fixed_risk"

        if config.VOLATILITY_SIZING_ENABLED and price > 0 and atr > 0 and stop_mult > 0:
            stop_distance_pct = (atr * stop_mult) / float(price)
            risk_budget = float(total_value or 0) * config.MAX_POSITION_RISK_PCT
            if stop_distance_pct > 0:
                volatility_amount = risk_budget / stop_distance_pct
            score_mult = self._clamp(0.75 + (score - config.MIN_AUTO_DECISION_SCORE), 0.5, 1.15)
            raw_amount = min(volatility_amount, cap_amount) * size_mult * score_mult * adaptive_size_mult
            reason = "volatility_atr"
        else:
            raw_amount = base_amount * size_mult * adaptive_size_mult

        amount_usdt = min(raw_amount, cap_amount, balance_usdt)
        amount_usdt = max(0.0, amount_usdt)
        risk_amount = amount_usdt * stop_distance_pct if stop_distance_pct else amount_usdt * config.STOP_LOSS_PCT
        return {
            "amount_usdt": round(amount_usdt, 8),
            "base_amount_usdt": round(base_amount, 8),
            "balance_usdt": round(balance_usdt, 8),
            "atr": atr,
            "stop_loss_atr": stop_mult,
            "stop_distance_pct": round(stop_distance_pct * 100, 4),
            "risk_amount_usdt": round(risk_amount, 8),
            "position_size_multiplier": round(size_mult, 4),
            "adaptive_size_multiplier": round(adaptive_size_mult, 4),
            "adaptive_adjustment": round(adaptive_adjustment, 4),
            "sizing_reason": reason,
            "portfolio_bucket": self.portfolio_bucket(symbol),
        }

    def resolve_executable_action(self, decision):
        action = str(decision.get('action', 'HOLD')).upper()
        score = self._safe_float(decision.get('decision_score'), self._safe_float(decision.get('confidence'), 0.0))
        if action == "BUY" and getattr(config, "DECISION_MODE", "hybrid") != "ai_aggressive":
            if score < config.MIN_AUTO_DECISION_SCORE:
                return "HOLD", f"LOW_DECISION_SCORE {score:.2f} < {config.MIN_AUTO_DECISION_SCORE:.2f}"
        return action, ""

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
                results = bt.run_full_backtest(symbol, timeframe='4h', years=2.0, verbose=False)
                if results:
                    best = max(results, key=lambda k: bt._strategy_score(results[k]))
                    best_result = results[best]
                    status = self._backtest_status(best_result)
                    self.log_message(
                        f"[BACKTEST] {symbol} best={best} | "
                        f"trades={int(best_result.get('total_trades', 0) or 0)} | "
                        f"WR={self._fmt_pct(best_result.get('win_rate', 0))} | "
                        f"PF={self._safe_float(best_result.get('profit_factor'), 0):.2f} | "
                        f"return={self._safe_float(best_result.get('total_return_pct'), 0):+.1f}% | "
                        f"status={status}"
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
                is_sim_str = self.db.get_system_status('simulacion', 'true')
                is_sim = str(is_sim_str).lower() == 'true'
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

                if str(is_running).lower() == 'true':
                    self.bot_iteration()
                    self.update_daemon_status("sleeping", next_cycle_in=60)
                else:
                    if time.time() - getattr(self, "_last_idle_log", 0) > 300:
                        self.log_message("[IDLE] Trading pausado: is_running=false. Esperando Start/Arrancar bot.")
                        self._last_idle_log = time.time()
                    self.update_daemon_status(
                        "idle",
                        execution_mode=getattr(config, "TRADING_EXECUTION_MODE", "auto"),
                        decision_mode=getattr(config, "DECISION_MODE", "hybrid"),
                    )
                time.sleep(60)
            except Exception as e:
                self.update_daemon_status("error", error=str(e))
                self.log_message(f"Error crítico en daemon: {e}")
                time.sleep(30)

    def bot_iteration(self):
        cycle_start = time.time()
        self.update_daemon_status("scanning", cycle_started_at=cycle_start)
        action_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
        providers = {}
        hold_reasons = {}
        scanned = 0
        skipped = {}
        consultive_mode = self.is_consultive_mode()
        
        # El balance total ya incluye el valor de todas las criptos en USDT
        total_value = self.exchange.get_balance()
        self.db.log_equity(total_value)
        
        # Límite dinámico basado en balance total (v6.1)
        self.dynamic_max = config.get_effective_max_positions(total_value)
        
        # Para el cálculo de cuánto podemos comprar, necesitamos el cash (USDT) disponible
        open_positions = self.db.get_open_positions()
        buy_candidates = []
        cycle_risk = self.evaluate_risk_guards(total_value, open_positions)
        if not cycle_risk["ok"]:
            self.log_message(
                f"[RISK] cycle ok=false | reasons={'; '.join(cycle_risk['reasons'])} | "
                f"daily_loss={cycle_risk.get('daily_loss_pct', 0):.2f}% | "
                f"exposure={cycle_risk.get('exposure_pct', 0):.2f}%"
            )

        def candidate_score(item):
            decision = item.get('decision') or {}
            confidence = float(decision.get('confidence') or 0)
            confluence = float(decision.get('confluence_score') or 0)
            size_mult = float(decision.get('position_size_multiplier') or 1.0)
            decision_score = float(decision.get('decision_score') or confidence)
            # El score determinista manda; confianza IA, MTF y sizing desempatan sin dominar.
            return decision_score + (confidence * 0.20) + (confluence * 0.10) + (size_mult * 0.03)

        def execute_buy_candidate(item):
            sym = item['symbol']
            price = float(item['price'])
            decision = item['decision']
            provider = item['provider']
            indicators = item.get('indicators') or {}
            decision_journal_id = item.get('decision_journal_id')

            sizing = self.calculate_position_size(sym, price, indicators, decision, total_value, open_positions)
            amount_usdt = float(sizing.get("amount_usdt") or 0)

            candidate_risk = self.evaluate_risk_guards(
                total_value,
                open_positions,
                pending_buy_usdt=amount_usdt,
                pending_symbol=sym,
            )
            if decision_journal_id:
                self.db.update_decision_journal(
                    decision_journal_id,
                    sizing=sizing,
                    risk=candidate_risk,
                    execution_status="candidate",
                )
            if not candidate_risk["ok"]:
                self.log_message(
                    f"[BLOCK] {sym} BUY->HOLD | reason=RISK_GUARD | "
                    f"details={'; '.join(candidate_risk['reasons'])} | "
                    f"amount={amount_usdt:.2f} USDT | bucket={candidate_risk.get('bucket', self.portfolio_bucket(sym))} | "
                    f"exposure={candidate_risk.get('exposure_pct', 0):.2f}%"
                )
                if decision_journal_id:
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status="blocked_risk",
                        block_reason=", ".join(candidate_risk["reasons"]),
                    )
                return False

            if consultive_mode:
                self.log_message(
                    f"[CONSULTIVE] {sym} BUY | px={price:.6g} | "
                    f"score={self._safe_float(decision.get('decision_score'), 0):.2f} | "
                    f"rank={item['score']:.3f} | conf={self._safe_float(decision.get('confidence'), 0):.2f} | "
                    f"amount={amount_usdt:.2f} USDT"
                )
                if decision_journal_id:
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status="consultive",
                        block_reason="TRADING_EXECUTION_MODE=consultive",
                    )
                return False

            if amount_usdt < config.MIN_POSITION_USDT:
                self.log_message(
                    f"[BLOCK] {sym} BUY->HOLD | reason=MIN_POSITION | "
                    f"amount={amount_usdt:.4f} < min={config.MIN_POSITION_USDT:.4f} | "
                    f"balance={sizing.get('balance_usdt', 0):.2f}"
                )
                if decision_journal_id:
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status="blocked_min_size",
                        block_reason=f"amount_usdt {amount_usdt:.4f} < MIN_POSITION_USDT {config.MIN_POSITION_USDT:.4f}",
                    )
                return False

            amount_coin = amount_usdt / price
            res = self.exchange.execute_order(sym, 'buy', amount_coin, price)
            if res.get('status') in ['closed', 'simulated']:
                decision['entry_confidence'] = decision.get('confidence', 0.7)
                decision['entry_decision_id'] = decision_journal_id
                decision['atr_at_entry'] = sizing.get('atr', 0)
                decision['sizing'] = sizing
                self.db.add_open_position(sym, price, price, amount_coin, extra_data=json.dumps(decision))
                open_positions[sym] = {
                    'entry_price': price,
                    'highest_price': price,
                    'amount': amount_coin,
                    'entry_confidence': decision.get('entry_confidence', 0.7),
                    'extra_data': json.dumps(decision),
                }
                trade_id = self.db.save_trade(
                    sym, 'buy', float(price), float(amount_coin),
                    f"BOT [{provider}]", 0.0,
                )
                if decision_journal_id:
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status=res.get('status', 'executed'),
                        execution_side="buy",
                        executed_price=float(price),
                        executed_amount=float(amount_coin),
                        sizing=sizing,
                        risk=candidate_risk,
                        block_reason=f"trade_id={trade_id}",
                    )
                self.log_message(
                    f"[BUY] {sym} amount={amount_usdt:.2f} USDT | px={price:.6g} | "
                    f"qty={amount_coin:.8g} | score={self._safe_float(decision.get('decision_score'), 0):.2f} | "
                    f"conf={self._safe_float(decision.get('confidence'), 0):.2f} | "
                    f"sizing={sizing.get('sizing_reason')} | risk={sizing.get('risk_amount_usdt', 0):.4f} USDT | "
                    f"provider={provider}"
                )
                return True

            self.log_message(f"[ERROR] {sym} BUY failed | reason={res.get('reason', res)}")
            if decision_journal_id:
                self.db.update_decision_journal(
                    decision_journal_id,
                    execution_status="failed",
                    block_reason=str(res.get('reason', res)),
                    sizing=sizing,
                    risk=candidate_risk,
                )
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
            executable_action, execution_block = self.resolve_executable_action(decision)
            action_counts[action] = action_counts.get(action, 0) + 1
            providers[provider] = providers.get(provider, 0) + 1
            if action == "HOLD":
                reason = str(decision.get('reasoning', 'HOLD')).split("...")[0][:80]
                hold_reasons[reason] = hold_reasons.get(reason, 0) + 1
            decision_journal_id = self.db.add_decision_journal(
                symbol=symbol,
                price=float(current_price),
                ai_action=decision.get('ai_action', action),
                action_final=action,
                executable_action=executable_action,
                provider=provider,
                decision_mode=decision.get('decision_mode', getattr(config, 'DECISION_MODE', 'hybrid')),
                execution_mode=getattr(config, 'TRADING_EXECUTION_MODE', 'auto'),
                regime=decision.get('regime', 'N/A'),
                strategy=decision.get('best_strategy', 'N/A'),
                confidence=float(decision.get('confidence') or 0),
                decision_score=float(decision.get('decision_score') or 0),
                score_components=decision.get('score_components', {}),
                indicators=indicators,
                portfolio_bucket=self.portfolio_bucket(symbol),
                block_reason=execution_block,
                execution_status="observed" if executable_action == "HOLD" else "signal",
            )
            # Guardar para UI (Global y por Símbolo)
            decision_json = json.dumps({
                'symbol': symbol,
                'reasoning': decision.get('reasoning', ''),
                'regime': decision.get('regime', 'N/A'),
                'best_strategy': decision.get('best_strategy', 'N/A'),
                'confidence': decision.get('confidence', 0),
                'action': decision.get('action', 'HOLD'),
                'executable_action': executable_action,
                'decision_score': decision.get('decision_score', 0),
                'score_components': decision.get('score_components', {}),
                'adaptive_adjustment': decision.get('adaptive_adjustment', decision.get('score_components', {}).get('adaptive_adjustment', 0)),
                'adaptive_evidence': decision.get('adaptive_evidence', decision.get('score_components', {}).get('adaptive_evidence', {})),
                'decision_mode': decision.get('decision_mode', getattr(config, 'DECISION_MODE', 'hybrid')),
                'execution_mode': getattr(config, 'TRADING_EXECUTION_MODE', 'auto'),
                'provider': provider,
            })
            self.db.set_system_status('last_ia_decision', decision_json)
            self.db.set_system_status(f'decision_{symbol}', decision_json)
            print(self._decision_log_line(symbol, decision, executable_action, provider))
            
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
                    if consultive_mode:
                        self.log_message(
                            f"[CONSULTIVE] {symbol} SELL | px={current_price:.6g} | "
                            f"reason={self._short_reason(sell_res['reason'], 80)} | "
                            f"score={self._safe_float(decision.get('decision_score'), 0):.2f}"
                        )
                        self.db.update_decision_journal(
                            decision_journal_id,
                            execution_status="consultive",
                            execution_side="sell",
                            block_reason="TRADING_EXECUTION_MODE=consultive",
                            exit_reason=sell_res['reason'],
                        )
                        continue
                    order_result = self.exchange.execute_order(symbol, 'sell', pos['amount'], current_price)
                    if order_result.get('status') in ['closed', 'simulated']:
                        try:
                            sold = float(order_result.get('filled') or 0)
                        except (TypeError, ValueError):
                            sold = 0.0
                        if sold <= 0:
                            sold = float(pos['amount'])
                        sold = min(sold, float(pos['amount']))
                        entry_extra = self._position_extra(pos)
                        entry_decision_id = entry_extra.get('entry_decision_id')
                        entry_price = float(pos.get('entry_price') or current_price)
                        realized_pnl = ((float(current_price) - entry_price) / entry_price) * 100 if entry_price else 0.0
                        closed = self.db.close_position(symbol, current_price, sell_res['reason'], sold_amount=sold)
                        if closed:
                            self.db.update_decision_journal(
                                decision_journal_id,
                                execution_status=order_result.get('status', 'executed'),
                                execution_side="sell",
                                executed_price=float(current_price),
                                executed_amount=float(sold),
                                realized_pnl_pct=realized_pnl,
                                exit_reason=sell_res['reason'],
                            )
                            if entry_decision_id:
                                self.db.update_decision_journal(
                                    entry_decision_id,
                                    realized_pnl_pct=realized_pnl,
                                    exit_reason=sell_res['reason'],
                                )
                            still = self.db.get_open_positions().get(symbol)
                            if still:
                                open_positions[symbol] = still
                            else:
                                del open_positions[symbol]
                            self.log_message(
                                f"[SELL] {symbol} qty={sold:.8g} | px={current_price:.6g} | "
                                f"pnl={realized_pnl:+.2f}% | reason={self._short_reason(sell_res['reason'], 80)} | "
                                f"provider={provider}"
                            )
                        else:
                            self.log_message(f"[WARN] {symbol} SELL executed but DB position was not found")
                    else:
                        self.log_message(f"[ERROR] {symbol} SELL failed | reason={order_result.get('reason', 'Error desconocido')}")
                        self.db.update_decision_journal(
                            decision_journal_id,
                            execution_status="failed",
                            execution_side="sell",
                            block_reason=str(order_result.get('reason', 'Error desconocido')),
                        )
            
            # 2. Lógica de COMPRA
            else:
                if action == 'BUY':
                    if executable_action != "BUY":
                        skipped["LOW_DECISION_SCORE"] = skipped.get("LOW_DECISION_SCORE", 0) + 1
                        self.log_message(
                            f"[BLOCK] {symbol} BUY->HOLD | reason={execution_block or 'NOT_EXECUTABLE'} | "
                            f"score={self._safe_float(decision.get('decision_score'), 0):.2f} | "
                            f"conf={self._safe_float(decision.get('confidence'), 0):.2f}"
                        )
                        self.db.update_decision_journal(
                            decision_journal_id,
                            execution_status="blocked_score",
                            block_reason=execution_block,
                        )
                        continue
                    item = {
                        'symbol': symbol,
                        'price': current_price,
                        'decision': decision,
                        'provider': provider,
                        'indicators': indicators,
                        'decision_journal_id': decision_journal_id,
                    }
                    item['score'] = candidate_score(item)
                    buy_candidates.append(item)

        buy_candidates.sort(key=lambda item: item['score'], reverse=True)
        if buy_candidates:
            top_preview = ", ".join(
                f"{c['symbol']} rank={c['score']:.3f} score={self._safe_float(c['decision'].get('decision_score'), 0):.2f}"
                for c in buy_candidates[:5]
            )
            self.log_message(f"[CANDIDATES] BUY top={top_preview}")

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

        if config.ROTATION_ENABLED and not consultive_mode and len(open_positions) >= self.dynamic_max and remaining_candidates:
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
                    f"[ROTATION] plan sell={sym_sac} pnl={to_sacrifice['profit']:+.2f}% "
                    f"for={candidate['symbol']} conf={self._safe_float(decision.get('confidence'), 0):.2f}"
                )
                sac_pos = open_positions[sym_sac]
                sac_price = self.exchange.get_ticker(sym_sac)
                if not sac_price:
                    self.log_message(f"[WARN] {sym_sac} rotation cancelled | reason=NO_PRICE")
                    break

                rot_res = self.exchange.execute_order(sym_sac, 'sell', sac_pos['amount'], sac_price)
                if rot_res.get('status') not in ['closed', 'simulated']:
                    self.log_message(f"[ERROR] {sym_sac} rotation sell failed | reason={rot_res.get('reason', rot_res)}")
                    break

                try:
                    sold = float(rot_res.get('filled') or 0)
                except (TypeError, ValueError):
                    sold = 0.0
                if sold <= 0:
                    sold = float(sac_pos['amount'])
                sold = min(sold, float(sac_pos['amount']))
                sac_extra = self._position_extra(sac_pos)
                sac_entry_decision_id = sac_extra.get('entry_decision_id')
                sac_entry_price = float(sac_pos.get('entry_price') or sac_price)
                sac_pnl = ((float(sac_price) - sac_entry_price) / sac_entry_price) * 100 if sac_entry_price else 0.0
                self.db.close_position(sym_sac, sac_price, "ROTACIÓN IA", sold_amount=sold)
                if sac_entry_decision_id:
                    self.db.update_decision_journal(
                        sac_entry_decision_id,
                        realized_pnl_pct=sac_pnl,
                        exit_reason=f"ROTACIÓN IA -> {candidate['symbol']}",
                    )
                still_sac = self.db.get_open_positions().get(sym_sac)
                if still_sac:
                    open_positions[sym_sac] = still_sac
                else:
                    del open_positions[sym_sac]
                self.log_message(
                    f"[ROTATION] executed sell={sym_sac} px={sac_price:.6g} pnl={sac_pnl:+.2f}% "
                    f"buy_candidate={candidate['symbol']}"
                )
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
            "execution_mode": getattr(config, "TRADING_EXECUTION_MODE", "auto"),
            "decision_mode": getattr(config, "DECISION_MODE", "hybrid"),
            "risk_guards": cycle_risk,
            "top_buy_candidates": [
                {
                    "symbol": c['symbol'],
                    "score": round(c['score'], 3),
                    "confidence": round(float(c['decision'].get('confidence') or 0), 3),
                    "decision_score": round(float(c['decision'].get('decision_score') or 0), 3),
                }
                for c in buy_candidates[:5]
            ],
            "open_positions": len(open_positions),
            "dynamic_max": getattr(self, "dynamic_max", None),
        }
        self.update_daemon_status("cycle_done", **diag)
        top_summary = ", ".join(
            f"{c['symbol']} {c['score']:.3f}"
            for c in buy_candidates[:3]
        ) or "-"
        risk_ok = str(bool(cycle_risk.get("ok"))).lower()
        self.log_message(
            f"[CYCLE] scanned={scanned} | buy={action_counts.get('BUY', 0)} "
            f"sell={action_counts.get('SELL', 0)} hold={action_counts.get('HOLD', 0)} | "
            f"candidates={len(buy_candidates)} | top={top_summary} | "
            f"risk_ok={risk_ok} | mode={'REAL' if not self.exchange.modo_simulacion else 'SIM'}/"
            f"{getattr(config, 'TRADING_EXECUTION_MODE', 'auto')}/{getattr(config, 'DECISION_MODE', 'hybrid')}"
        )

if __name__ == "__main__":
    daemon = BotDaemon()
    daemon.run()
