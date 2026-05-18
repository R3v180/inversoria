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
        self.last_watchlist_update = self._status_float('last_watchlist_update', 0.0)

        # Control del backtest automático semanal
        self.last_backtest_run = self._status_float('last_backtest_run', 0.0)
        self.BACKTEST_INTERVAL = 604800  # 7 días en segundos

        # Control macro v6.0
        from macro_analyzer import MacroAnalyzer
        self.macro_analyzer = MacroAnalyzer()
        self.last_macro_update = 0
        self.MACRO_INTERVAL = 900 # 15 min: actualiza 1 activo vencido por ciclo, sin bloquear
        self._last_idle_log = 0
        try:
            self._launcher_arm_until = float(os.getenv("INVERSORIA_LAUNCHER_ARM_UNTIL", "0") or 0)
        except (TypeError, ValueError):
            self._launcher_arm_until = 0

        self.log_message(_('LOG_DAEMON_INIT', lang=self.u_lang))

    def log_message(self, msg):
        text = f"[DAEMON] {msg}"
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            safe_text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(safe_text, flush=True)
        self.db.add_log(msg)

    def _macro_cache_status(self):
        macro_data = self.db.get_all_macro_data()
        if not macro_data:
            return "sin cache"
        oldest = min(float((row or {}).get('last_update') or 0) for row in macro_data.values())
        if time.time() - oldest >= self.macro_analyzer.STALE_AFTER_SECONDS:
            return "cache stale"
        return "cache vigente"

    def _macro_provider_blocked(self, now):
        state = self.macro_analyzer.get_provider_refresh_state()
        cooldown_until = float((state or {}).get('cooldown_until') or 0)
        last_attempt = float((state or {}).get('last_attempt') or 0)
        if cooldown_until > now:
            self.log_message(
                f"[Macro] Alpha Vantage cooldown hasta {self.macro_analyzer._format_ts(cooldown_until)}; "
                f"usando cache existente ({self._macro_cache_status()})."
            )
            return True
        min_interval = self.macro_analyzer.MIN_ATTEMPT_INTERVAL_SECONDS
        if last_attempt and now - last_attempt < min_interval:
            next_attempt = last_attempt + min_interval
            self.log_message(
                f"[Macro] Skipping macro refresh: last attempt {self.macro_analyzer._format_ts(last_attempt)}; "
                f"próximo intento >= {self.macro_analyzer._format_ts(next_attempt)}; "
                f"usando cache existente ({self._macro_cache_status()})."
            )
            return True
        return False

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
        now = time.time()
        watchlist_ttl = int(getattr(config, 'WATCHLIST_UPDATE_SECONDS', 14400))
        payload.update({
            "last_watchlist_update": self.last_watchlist_update,
            "watchlist_next_refresh_in": max(0, int((self.last_watchlist_update + watchlist_ttl) - now)),
            "last_backtest_run": self.last_backtest_run,
            "backtest_next_run_in": max(0, int((self.last_backtest_run + self.BACKTEST_INTERVAL) - now)),
        })
        ai_cooldowns = {}
        for provider in ("Gemini", "Groq"):
            state_info = self.db.get_provider_cooldown(provider, "ai")
            cooldown_until = float((state_info or {}).get("cooldown_until") or 0)
            ai_cooldowns[provider] = {
                "cooldown_in": max(0, int(cooldown_until - now)),
                "reason": (state_info or {}).get("reason", ""),
            }
        payload["ai_provider_cooldowns"] = ai_cooldowns
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

    def _status_float(self, key, default=0.0):
        return self._safe_float(self.db.get_system_status(key, default), default)

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

    def _sell_confidence_threshold(self, decision):
        regime = (decision or {}).get('regime', 'RANGING')
        return 0.75 if regime == 'TRENDING_UP' else 0.65

    def _is_expected_order_block(self, reason):
        text = str(reason or "").lower()
        expected = (
            "slippage",
            "insufficient",
            "saldo",
            "balance",
            "fondos",
            "mínimo",
            "minimo",
            "menor al mínimo",
            "cantidad virtual insuficiente",
            "no vendible",
        )
        return any(token in text for token in expected)

    def _sell_notional_floor(self, symbol, price=None, validation=None):
        floor = self._safe_float(getattr(config, "MIN_POSITION_USDT", 1.0), 1.0)
        validation = validation or {}
        min_cost = self._safe_float(validation.get("min_cost"), 0.0)
        if min_cost > 0:
            floor = max(floor, min_cost)
        min_amount = self._safe_float(validation.get("min_amount"), 0.0)
        px = self._safe_float(price, 0.0)
        if min_amount > 0 and px > 0:
            floor = max(floor, min_amount * px)
        try:
            constraints = self.exchange.get_market_sell_constraints(symbol)
        except Exception:
            constraints = None
        if constraints:
            min_cost = self._safe_float(constraints.get("min_cost"), 0.0)
            if min_cost > 0:
                floor = max(floor, min_cost)
            min_amount = self._safe_float(constraints.get("min_amount"), 0.0)
            if min_amount > 0 and px > 0:
                floor = max(floor, min_amount * px)
        return floor

    def _balance_is_below_sell_minimum(self, value_usdt, min_notional, validation=None):
        errors = validation.get("errors") if validation else []
        below_market_min = any(
            str(err).startswith(("BELOW_MIN_AMOUNT", "BELOW_MIN_COST", "PRECISION_ZERO", "ZERO_AMOUNT"))
            for err in (errors or [])
        )
        return self._safe_float(value_usdt, 0.0) < self._safe_float(min_notional, 0.0) or below_market_min

    def _sellable_balance_snapshot(self, symbol, current_price=None, amount_override=None, check_slippage=False):
        try:
            amount = self._safe_float(
                amount_override if amount_override is not None else self.exchange.get_coin_balance(symbol),
                0.0,
            )
        except Exception:
            amount = 0.0
        price = self._safe_float(current_price, 0.0)
        if price <= 0:
            try:
                price = self._safe_float(self.exchange.get_ticker(symbol), 0.0)
            except Exception:
                price = 0.0
        value = amount * price if amount > 0 and price > 0 else 0.0
        validation = None
        if amount > 0:
            try:
                validation = self.exchange.prevalidate_market_sell(
                    symbol,
                    amount,
                    price_hint=price or None,
                    free_override=amount,
                    check_slippage=check_slippage,
                )
            except Exception as exc:
                validation = {"ok": False, "errors": [f"PREVALIDATION:{exc}"]}
        min_notional = self._sell_notional_floor(symbol, price=price, validation=validation)
        if amount <= 0:
            status = "NO_SELLABLE_BALANCE"
        elif self._balance_is_below_sell_minimum(value, min_notional, validation):
            status = "DUST_BELOW_MIN_ORDER"
        elif validation and not validation.get("ok"):
            status = "SELL_PREVALIDATION"
        else:
            status = "SELLABLE_ADOPTABLE_BALANCE"
        return {
            "status": status,
            "amount": amount,
            "price": price,
            "value": value,
            "min_notional": min_notional,
            "validation": validation or {},
        }

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
            small_account = float(total_value or 0) < float(
                getattr(config, 'SMALL_ACCOUNT_USDT_THRESHOLD', 150.0)
            )
            max_stop_pct = float(getattr(config, 'SMALL_ACCOUNT_MAX_STOP_DISTANCE_PCT', 8.0)) / 100.0
            if small_account and max_stop_pct > 0:
                stop_distance_pct = min(stop_distance_pct, max_stop_pct)
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
        min_order = float(config.MIN_POSITION_USDT)
        if (
            bool(getattr(config, 'SMALL_ACCOUNT_FORCE_MIN_ORDER', True))
            and float(total_value or 0) < float(getattr(config, 'SMALL_ACCOUNT_USDT_THRESHOLD', 150.0))
            and score >= float(config.MIN_AUTO_DECISION_SCORE)
            and balance_usdt >= min_order
            and amount_usdt > 0
            and amount_usdt < min_order
        ):
            amount_usdt = min(min_order, balance_usdt * 0.98)
            reason = f"{reason}_min_floor"
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

    def cap_size_to_risk_capacity(self, symbol, amount_usdt, total_value, open_positions):
        """Reduce el tamaño al máximo permitido por exposición en vez de bloquear toda la señal."""
        amount_usdt = self._safe_float(amount_usdt, 0.0)
        if amount_usdt <= 0 or total_value <= 0:
            return 0.0, {}
        exposures = self.portfolio_exposures(open_positions)
        bucket = self.portfolio_bucket(symbol)
        capacities = {
            "portfolio": max(0.0, (total_value * config.MAX_PORTFOLIO_EXPOSURE_PCT) - exposures["total"]),
            "symbol": max(0.0, (total_value * config.MAX_SYMBOL_EXPOSURE_PCT) - exposures["symbols"].get(symbol, 0.0)),
            "bucket": max(0.0, (total_value * config.MAX_BUCKET_EXPOSURE_PCT) - exposures["buckets"].get(bucket, 0.0)),
        }
        if bucket not in {"BTC", "ETH"}:
            capacities["alt"] = max(0.0, (total_value * config.MAX_ALT_EXPOSURE_PCT) - exposures["alt"])
        capped = min(amount_usdt, *capacities.values())
        # Tiny buffer avoids equality/rounding turning an exactly-at-limit size into a guard violation.
        capped = max(0.0, capped * 0.999)
        return capped, {
            "bucket": bucket,
            "capacities": {key: round(value, 8) for key, value in capacities.items()},
            "original_amount_usdt": round(amount_usdt, 8),
            "capped_amount_usdt": round(capped, 8),
            "capped": capped + 1e-8 < amount_usdt,
        }

    def _record_adopted_position(self, symbol, price, amount, notional, open_positions):
        mode_label = "simulated" if self.exchange.modo_simulacion else "real"
        extra = {
            "external_adopted": True,
            "provider": "ExchangeBalance" if not self.exchange.modo_simulacion else "SimulatedBalance",
            "reasoning": f"Saldo {mode_label} vendible adoptado para protección automática.",
            "decision_mode": getattr(config, "DECISION_MODE", "hybrid"),
            "execution_mode": getattr(config, "TRADING_EXECUTION_MODE", "auto"),
        }
        entry_time = time.time()
        extra_data = json.dumps(extra, ensure_ascii=False)
        self.db.add_open_position(
            symbol,
            price,
            price,
            amount,
            entry_time=entry_time,
            extra_data=extra_data,
        )
        open_positions[symbol] = {
            "symbol": symbol,
            "entry_price": price,
            "highest_price": price,
            "amount": amount,
            "entry_time": entry_time,
            "extra_data": extra_data,
        }
        self.log_message(
            f"[ADOPT] {symbol} {mode_label} balance managed | qty={amount:.8g} | "
            f"value={notional:.2f} USDT | reason=sellable_exchange_balance"
        )

    def adopt_sellable_positions(self, open_positions):
        """Adopta saldos vendibles aunque no pertenezcan al universo de nuevas compras."""
        adopted = []
        skipped = {}
        ignored_coins = {"USDT", "USD", "EUR", "USDC", "DAI", "TUSD", "BUSD", "PYUSD"}
        try:
            rows = self.exchange.get_spot_inventory_rows()
        except Exception as exc:
            self.log_message(f"[WARN] Adoption scan failed | reason={exc}")
            return adopted, {"ADOPT_SCAN_ERROR": 1}

        for row in rows:
            coin = str(row.get("coin") or "").upper()
            symbol = row.get("symbol")
            if not symbol or coin in ignored_coins:
                continue
            if symbol in open_positions:
                continue

            try:
                free_amount = float(row.get("free") or 0)
                usd_free = float(row.get("usd_free") or 0)
            except (TypeError, ValueError):
                skipped["ADOPT_BAD_BALANCE"] = skipped.get("ADOPT_BAD_BALANCE", 0) + 1
                continue
            price = (usd_free / free_amount) if free_amount > 0 else 0.0
            if free_amount <= 0 or price <= 0:
                skipped["ADOPT_NO_VALUE"] = skipped.get("ADOPT_NO_VALUE", 0) + 1
                continue

            balance_state = self._sellable_balance_snapshot(
                symbol,
                current_price=price,
                amount_override=free_amount,
                check_slippage=False,
            )
            min_notional = self._safe_float(balance_state.get("min_notional"), config.MIN_POSITION_USDT)
            notional_est = self._safe_float(balance_state.get("value"), usd_free)
            if balance_state.get("status") == "DUST_BELOW_MIN_ORDER":
                skipped["ADOPT_DUST_BELOW_MIN_ORDER"] = skipped.get("ADOPT_DUST_BELOW_MIN_ORDER", 0) + 1
                self.log_message(
                    f"[SKIP] {symbol} adopt ignored | reason=DUST_BELOW_MIN_ORDER | "
                    f"value={notional_est:.4f} < min={min_notional:.4f} | qty={free_amount:.8g}"
                )
                continue

            if self.exchange.modo_simulacion:
                amount = free_amount
                notional = amount * price
            else:
                validation = balance_state.get("validation") or {}
                if not validation.get("ok"):
                    errors = ",".join(validation.get("errors") or ["UNKNOWN"])
                    skipped["ADOPT_UNSELLABLE"] = skipped.get("ADOPT_UNSELLABLE", 0) + 1
                    self.log_message(
                        f"[SKIP] {symbol} adopt ignored | reason=ADOPT_UNSELLABLE | "
                        f"errors={errors} | value={notional_est:.4f} | min={min_notional:.4f} | qty={free_amount:.8g}"
                    )
                    continue
                amount = self._safe_float(validation.get("amount_after_precision"), free_amount)
                notional = self._safe_float(validation.get("notional"), amount * price)
            if amount <= 0 or notional <= 0:
                skipped["ADOPT_ZERO_AFTER_PRECISION"] = skipped.get("ADOPT_ZERO_AFTER_PRECISION", 0) + 1
                continue

            self._record_adopted_position(symbol, price, amount, notional, open_positions)
            adopted.append(symbol)

        return adopted, skipped

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
        self.db.set_system_status('last_backtest_run', self.last_backtest_run)
        self.log_message(_('LOG_BACKTEST_DONE', lang=self.u_lang))

    def run(self):
        self.load_active_watchlist()

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
                is_running = self.db.get_system_status('is_running')
                if str(is_running).lower() != 'true':
                    try:
                        armed_until = float(self.db.get_system_status('launcher_start_armed_until', '0') or 0)
                    except (TypeError, ValueError):
                        armed_until = 0
                    env_armed = getattr(self, "_launcher_arm_until", 0) > time.time()
                    if armed_until > time.time() or env_armed:
                        self.db.set_system_status('is_running', 'true')
                        is_running = 'true'
                        self.log_message("[ARMED] Launcher start detected; trading rearmado.")
                        self._launcher_arm_until = 0
                if str(is_running).lower() != 'true':
                    if time.time() - getattr(self, "_last_idle_log", 0) > 300:
                        self.log_message("[IDLE] Trading pausado: is_running=false. Esperando Start/Arrancar bot.")
                        self._last_idle_log = time.time()
                    self.update_daemon_status(
                        "idle",
                        execution_mode=getattr(config, "TRADING_EXECUTION_MODE", "auto"),
                        decision_mode=getattr(config, "DECISION_MODE", "hybrid"),
                    )
                    time.sleep(60)
                    continue
                watchlist_ttl = int(getattr(config, 'WATCHLIST_UPDATE_SECONDS', 14400))
                if now - self.last_watchlist_update > watchlist_ttl:
                    self.update_dynamic_watchlist()
                    self.last_watchlist_update = now
                    self.db.set_system_status('last_watchlist_update', self.last_watchlist_update)

                # Backtest semanal automático
                if now - self.last_backtest_run > self.BACKTEST_INTERVAL:
                    self.run_weekly_backtest()

                # Actualización macro incremental: 1 activo vencido cada intervalo
                if now - self.last_macro_update > self.MACRO_INTERVAL:
                    if self._macro_provider_blocked(now):
                        self.last_macro_update = now
                    else:
                        self.update_daemon_status("macro_refresh")
                        from macro_analyzer import MacroAnalyzer
                        macro = MacroAnalyzer(lang=self.u_lang)
                        macro.fetch_global_market_status(max_assets=1)
                        self.macro_analyzer = macro
                    self.last_macro_update = now
                    
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
                    cycle_sleep = max(15, int(getattr(config, 'DAEMON_CYCLE_SECONDS', 60)))
                    self.update_daemon_status("sleeping", next_cycle_in=cycle_sleep)
                else:
                    if time.time() - getattr(self, "_last_idle_log", 0) > 300:
                        self.log_message("[IDLE] Trading pausado: is_running=false. Esperando Start/Arrancar bot.")
                        self._last_idle_log = time.time()
                    self.update_daemon_status(
                        "idle",
                        execution_mode=getattr(config, "TRADING_EXECUTION_MODE", "auto"),
                        decision_mode=getattr(config, "DECISION_MODE", "hybrid"),
                    )
                cycle_sleep = max(15, int(getattr(config, 'DAEMON_CYCLE_SECONDS', 60)))
                time.sleep(cycle_sleep)
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
        adopted_symbols, adoption_skipped = self.adopt_sellable_positions(open_positions)
        for reason, count in adoption_skipped.items():
            skipped[reason] = skipped.get(reason, 0) + count
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
            capped_amount, cap_info = self.cap_size_to_risk_capacity(sym, amount_usdt, total_value, open_positions)
            if cap_info.get("capped"):
                sizing["original_amount_usdt"] = cap_info.get("original_amount_usdt")
                sizing["amount_usdt"] = round(capped_amount, 8)
                sizing["risk_cap"] = cap_info
                sizing["sizing_reason"] = f"{sizing.get('sizing_reason', 'unknown')}_risk_capped"
                amount_usdt = capped_amount
                self.log_message(
                    f"[SIZE] {sym} capped {cap_info.get('original_amount_usdt'):.2f}->{amount_usdt:.2f} USDT | "
                    f"bucket={cap_info.get('bucket')} | caps={cap_info.get('capacities')}"
                )

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

            quote_balance = self._safe_float(sizing.get('balance_usdt'), 0.0)
            if amount_usdt < config.MIN_POSITION_USDT:
                block_reason = "INSUFFICIENT_QUOTE_BALANCE" if quote_balance < config.MIN_POSITION_USDT else "MIN_POSITION"
                self.log_message(
                    f"[BLOCK] {sym} BUY->HOLD | reason={block_reason} | "
                    f"amount={amount_usdt:.4f} < min={config.MIN_POSITION_USDT:.4f} | "
                    f"quote_balance={quote_balance:.2f}"
                )
                if decision_journal_id:
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status="blocked_balance" if block_reason == "INSUFFICIENT_QUOTE_BALANCE" else "blocked_min_size",
                        block_reason=(
                            f"{block_reason}: amount_usdt {amount_usdt:.4f} < "
                            f"MIN_POSITION_USDT {config.MIN_POSITION_USDT:.4f}; quote_balance {quote_balance:.4f}"
                        ),
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
                trade_reason = (
                    f"BOT [{provider}] | score={self._safe_float(decision.get('decision_score'), 0):.2f} | "
                    f"conf={self._safe_float(decision.get('confidence'), 0):.2f} | "
                    f"regime={decision.get('regime', 'N/A')} | "
                    f"strategy={decision.get('best_strategy', 'N/A')} | "
                    f"{self._short_reason(decision.get('reasoning', ''), 160)}"
                )
                trade_id = self.db.save_trade(
                    sym, 'buy', float(price), float(amount_coin),
                    trade_reason, 0.0,
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

            fail_reason = str(res.get('reason', res))
            tag = "[BLOCK]" if self._is_expected_order_block(fail_reason) else "[ERROR]"
            self.log_message(
                f"{tag} {sym} BUY failed | reason={fail_reason} | "
                f"amount={amount_usdt:.2f} USDT | qty={amount_coin:.8g}"
            )
            if decision_journal_id:
                self.db.update_decision_journal(
                    decision_journal_id,
                    execution_status="failed",
                    block_reason=fail_reason,
                    sizing=sizing,
                    risk=candidate_risk,
                )
            return False

        scan_symbols = []
        for symbol in list(self.active_symbols or []) + list(open_positions.keys()):
            if symbol not in scan_symbols:
                scan_symbols.append(symbol)

        for symbol in scan_symbols:
            current_price = self.exchange.get_ticker(symbol)
            if not current_price:
                skipped["NO_PRICE"] = skipped.get("NO_PRICE", 0) + 1
                continue
            scanned += 1
            
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
            action = str(decision.get('action', 'HOLD')).upper()
            raw_action = str(decision.get('ai_action', action)).upper()
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
                    validation = self.exchange.prevalidate_market_sell(
                        symbol,
                        pos['amount'],
                        price_hint=current_price,
                    )
                    if not validation.get("ok"):
                        errors = ",".join(validation.get("errors") or ["UNKNOWN"])
                        reason = "NO_SELLABLE_BALANCE" if any(
                            err in errors for err in ("NO_FREE_BALANCE", "INSUFFICIENT_VIRTUAL", "ZERO_AMOUNT")
                        ) else "SELL_PREVALIDATION"
                        self.log_message(
                            f"[BLOCK] {symbol} SELL ignored | reason={reason} | "
                            f"errors={errors} | requested={self._safe_float(pos.get('amount')):.8g} | "
                            f"free={self._safe_float(validation.get('free_amount')):.8g} | "
                            f"notional={self._safe_float(validation.get('notional')):.4f}"
                        )
                        self.db.update_decision_journal(
                            decision_journal_id,
                            execution_status="blocked_sell_prevalidation",
                            execution_side="sell",
                            block_reason=errors,
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
                elif raw_action == "SELL":
                    confidence = self._safe_float(decision.get('confidence'), 0.0)
                    threshold = self._sell_confidence_threshold(decision)
                    if confidence < threshold:
                        self.log_message(
                            f"[SKIP] {symbol} SELL ignored | reason=CONF_BELOW_SELL_THRESHOLD | "
                            f"conf={confidence:.2f} < threshold={threshold:.2f} | "
                            f"regime={decision.get('regime', 'N/A')} | protective=false"
                        )
                        self.db.update_decision_journal(
                            decision_journal_id,
                            execution_status="ignored_low_sell_confidence",
                            execution_side="sell",
                            block_reason=f"SELL confidence {confidence:.2f} < threshold {threshold:.2f}; no protective trigger",
                        )
            
            # 2. Lógica de COMPRA
            else:
                if raw_action == 'SELL' or action == 'SELL':
                    balance_state = self._sellable_balance_snapshot(symbol, current_price=current_price, check_slippage=False)
                    sellable_balance = self._safe_float(balance_state.get("amount"), 0.0)
                    value_usdt = self._safe_float(balance_state.get("value"), 0.0)
                    min_notional = self._safe_float(balance_state.get("min_notional"), config.MIN_POSITION_USDT)
                    status = balance_state.get("status")
                    if status == "NO_SELLABLE_BALANCE":
                        reason = "NO_OPEN_POSITION_OR_SELLABLE_BALANCE"
                        self.log_message(
                            f"[SKIP] {symbol} SELL ignored | reason={reason} | "
                            f"open_position=false | sellable_balance=0 | value=0.0000 | "
                            f"conf={self._safe_float(decision.get('confidence'), 0):.2f}"
                        )
                    elif status == "DUST_BELOW_MIN_ORDER":
                        reason = "DUST_BELOW_MIN_ORDER"
                        self.log_message(
                            f"[SKIP] {symbol} SELL ignored | reason={reason} | "
                            f"open_position=false | sellable_balance={sellable_balance:.8g} | "
                            f"value={value_usdt:.4f} < min={min_notional:.4f} | "
                            f"conf={self._safe_float(decision.get('confidence'), 0):.2f}"
                        )
                    elif status == "SELL_PREVALIDATION":
                        validation = balance_state.get("validation") or {}
                        errors = ",".join(validation.get("errors") or ["UNKNOWN"])
                        reason = "SELL_PREVALIDATION"
                        self.log_message(
                            f"[BLOCK] {symbol} SELL ignored | reason={reason} | "
                            f"open_position=false | errors={errors} | sellable_balance={sellable_balance:.8g} | "
                            f"value={value_usdt:.4f} | min={min_notional:.4f}"
                        )
                    else:
                        reason = "ADOPTABLE_BALANCE_MANAGED"
                        self._record_adopted_position(
                            symbol,
                            self._safe_float(balance_state.get("price"), current_price),
                            sellable_balance,
                            value_usdt,
                            open_positions,
                        )
                        adopted_symbols.append(symbol)
                        confidence = self._safe_float(decision.get('confidence'), 0.0)
                        threshold = self._sell_confidence_threshold(decision)
                        if confidence < threshold:
                            reason = "CONF_BELOW_SELL_THRESHOLD"
                            self.log_message(
                                f"[SKIP] {symbol} SELL ignored | reason={reason} | "
                                f"open_position=adopted | sellable_balance={sellable_balance:.8g} | "
                                f"value={value_usdt:.4f} >= min={min_notional:.4f} | "
                                f"conf={confidence:.2f} < threshold={threshold:.2f} | protective=false"
                            )
                        else:
                            self.log_message(
                                f"[SKIP] {symbol} SELL deferred | reason=ADOPTED_EVALUATE_NEXT_CYCLE | "
                                f"open_position=adopted | sellable_balance={sellable_balance:.8g} | "
                                f"value={value_usdt:.4f} >= min={min_notional:.4f} | conf={confidence:.2f}"
                            )
                    self.log_message(
                        f"[BALANCE] {symbol} no_open_position_sell | state={status} | "
                        f"reason={reason} | qty={sellable_balance:.8g} | value={value_usdt:.4f} | min={min_notional:.4f}"
                    )
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status="adopted_balance" if reason == "ADOPTABLE_BALANCE_MANAGED" else "ignored_no_open_position",
                        execution_side="sell",
                        block_reason=(
                            f"{reason}; sellable_balance={sellable_balance:.8g}; "
                            f"value_usdt={value_usdt:.4f}; min_notional={min_notional:.4f}"
                        ),
                    )
                    continue

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
                skipped["MAX_OPEN_POSITIONS"] = skipped.get("MAX_OPEN_POSITIONS", 0) + 1
                self.log_message(
                    f"[SKIP] {candidate['symbol']} BUY skipped | reason=MAX_OPEN_POSITIONS | "
                    f"open={len(open_positions)} | max={self.dynamic_max} | "
                    f"rank={candidate['score']:.3f} | score={self._safe_float(candidate['decision'].get('decision_score'), 0):.2f}"
                )
                decision_journal_id = candidate.get('decision_journal_id')
                if decision_journal_id:
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status="blocked_slots",
                        block_reason=f"MAX_OPEN_POSITIONS open={len(open_positions)} max={self.dynamic_max}",
                    )
                continue
            if candidate['symbol'] in open_positions:
                skipped["DUPLICATE_POSITION"] = skipped.get("DUPLICATE_POSITION", 0) + 1
                self.log_message(
                    f"[SKIP] {candidate['symbol']} BUY skipped | reason=DUPLICATE_POSITION | "
                    f"open={len(open_positions)} | rank={candidate['score']:.3f}"
                )
                decision_journal_id = candidate.get('decision_journal_id')
                if decision_journal_id:
                    self.db.update_decision_journal(
                        decision_journal_id,
                        execution_status="blocked_duplicate",
                        block_reason="Symbol already has an open position",
                    )
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
                new_conf = self._safe_float(decision.get('confidence'), 0.0)
                if new_conf < config.ROTATION_MIN_NEW_CONFIDENCE:
                    self.log_message(
                        f"[ROTATION] skipped candidate={candidate['symbol']} | reason=CONF_BELOW_MIN | "
                        f"conf={new_conf:.2f} < min={config.ROTATION_MIN_NEW_CONFIDENCE:.2f} | "
                        f"rank={candidate['score']:.3f}"
                    )
                    continue
                to_sacrifice = self.decision_engine.evaluate_rotation_potential(decision, pos_details)
                if not to_sacrifice:
                    self.log_message(
                        f"[ROTATION] skipped candidate={candidate['symbol']} | reason=NO_WEAKER_POSITION | "
                        f"conf={new_conf:.2f} | min_profit={config.ROTATION_MIN_PROFIT:.2f}% | "
                        f"gap_required={config.ROTATION_CONFIDENCE_GAP:.2f} | open={len(pos_details)}"
                    )
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
            "adopted_real_positions": adopted_symbols,
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
