import ccxt
import time
import datetime
import json
import os
import threading
from config import (
    MODO_SIMULACION,
    PRESUPUESTO_INICIAL,
    BUY_SLIPPAGE_LIMIT,
    SELL_SLIPPAGE_LIMIT,
    get_setting,
)
from simulation_profiles import get_active_account_path

EXCHANGE_TIMEOUT_MS = 20000


class ExchangeHelper:
    def __init__(self, modo_simulacion=True):
        self.modo_simulacion = modo_simulacion
        self.virtual_balance = PRESUPUESTO_INICIAL
        self.virtual_portfolio = {} # symbol -> amount
        self.simulated_account_path = get_active_account_path() if self.modo_simulacion else 'simulated_account.json'
        self.private_exchange = None
        self.public_exchange = None
        self._order_lock = threading.RLock()
        
        if self.modo_simulacion:
            self._load_simulated_state()
            
        # La instancia expuesta es pública para que tickers/backtests no dependan de auth.
        try:
            self.public_exchange = self._build_cryptocom_exchange(authenticated=False)
            self.exchange = self.public_exchange
            self._ensure_public_markets()
            if not self.modo_simulacion and not self._has_credentials():
                self._log_exchange_warning("Aviso: credenciales Crypto.com incompletas; operaciones reales deshabilitadas")
        except Exception as e:
            print(f"Error al inicializar Exchange: {self._sanitize_error(e)}")

    def _get_private_credentials(self):
        api_key = (get_setting('CRYPTO_API_KEY', '') or '').strip()
        api_secret = (get_setting('CRYPTO_API_SECRET', '') or '').strip()
        return api_key, api_secret

    def _has_credentials(self):
        api_key, api_secret = self._get_private_credentials()
        return bool(api_key and api_secret)

    def _sanitize_error(self, error):
        text = str(error)
        for secret in self._get_private_credentials():
            if secret:
                text = text.replace(secret, "[redacted]")
        return text

    def _log_exchange_warning(self, message, error=None):
        suffix = f": {self._sanitize_error(error)}" if error is not None else ""
        print(f"{message}{suffix}")

    def _build_cryptocom_exchange(self, authenticated=False):
        exchange_config = {
            'enableRateLimit': True,
            'timeout': EXCHANGE_TIMEOUT_MS,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 10000,
            },
        }
        if authenticated:
            api_key, api_secret = self._get_private_credentials()
            if not api_key or not api_secret:
                raise RuntimeError("Credenciales Crypto.com incompletas; operaciones privadas deshabilitadas.")
            exchange_config.update({
                'apiKey': api_key,
                'secret': api_secret,
            })
        return ccxt.cryptocom(exchange_config)

    def _ensure_public_markets(self):
        if not self.public_exchange:
            self.public_exchange = self._build_cryptocom_exchange(authenticated=False)
            self.exchange = self.public_exchange
        if not self.public_exchange.markets:
            self.public_exchange.load_markets()
        return self.public_exchange.markets

    def _copy_public_markets_to_private(self):
        if not self.private_exchange:
            return
        try:
            self._ensure_public_markets()
            currencies = getattr(self.public_exchange, "currencies", None)
            if hasattr(self.private_exchange, "set_markets"):
                self.private_exchange.set_markets(self.public_exchange.markets, currencies)
            else:
                self.private_exchange.markets = self.public_exchange.markets
                self.private_exchange.markets_by_id = getattr(self.public_exchange, "markets_by_id", {})
                self.private_exchange.symbols = getattr(self.public_exchange, "symbols", [])
                self.private_exchange.currencies = currencies or {}
                self.private_exchange.currencies_by_id = getattr(self.public_exchange, "currencies_by_id", {})
        except Exception as e:
            self._log_exchange_warning("Aviso: no se pudieron copiar mercados públicos a la instancia privada", e)

    def _is_nonce_error(self, error):
        text = str(error or "").lower()
        return "invalid_nonce" in text or "10007" in text

    def _sync_exchange_clock(self, exchange):
        if not exchange:
            return
        if getattr(exchange, "id", "") == "cryptocom":
            return
        try:
            if hasattr(exchange, "load_time_difference"):
                exchange.load_time_difference()
        except Exception as e:
            self._log_exchange_warning("Aviso: no se pudo sincronizar reloj del exchange", e)

    def _reset_private_exchange(self):
        self.private_exchange = None

    def _get_private_exchange(self):
        if self.private_exchange is None:
            self.private_exchange = self._build_cryptocom_exchange(authenticated=True)
            self._copy_public_markets_to_private()
            self.private_exchange.check_required_credentials()
        self._sync_exchange_clock(self.private_exchange)
        return self.private_exchange

    def _call_private(self, fn, *args, **kwargs):
        """Ejecuta llamadas privadas con resync de nonce ante INVALID_NONCE."""
        last_error = None
        for attempt in range(2):
            try:
                exchange = self._get_private_exchange()
                return fn(exchange, *args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt == 0 and self._is_nonce_error(e):
                    self._reset_private_exchange()
                    time.sleep(0.35)
                    continue
                raise
        raise last_error

    def _save_simulated_state(self):
        path = self.simulated_account_path
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, 'w') as f:
            json.dump({
                'virtual_balance': self.virtual_balance,
                'virtual_portfolio': self.virtual_portfolio
            }, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def _load_simulated_state(self):
        if os.path.exists(self.simulated_account_path):
            try:
                with open(self.simulated_account_path, 'r') as f:
                    data = json.load(f)
                    self.virtual_balance = data.get('virtual_balance', PRESUPUESTO_INICIAL)
                    self.virtual_portfolio = data.get('virtual_portfolio', {})
            except Exception as e:
                print(f"Error cargando estado simulado: {e}")

    def _refresh_simulated_state(self):
        """Reload simulation state written by the daemon or another UI process."""
        if not self.modo_simulacion:
            return
        self.simulated_account_path = get_active_account_path()
        self._load_simulated_state()

    def get_usdt_balance(self):
        """Retorna solo el cash disponible (USDT)"""
        if self.modo_simulacion:
            self._refresh_simulated_state()
            return self.virtual_balance
        else:
            try:
                balance = self._call_private(lambda ex: ex.fetch_balance())
                return balance['free'].get('USDT', 0.0)
            except Exception as e:
                print(f"Error obteniendo balance USDT: {self._sanitize_error(e)}")
                return 0.0

    def get_balance(self):
        """Retorna la Equity Total (Cash + Valor de Criptos)"""
        if self.modo_simulacion:
            self._refresh_simulated_state()
            total = self.virtual_balance
            for sym, amount in self.virtual_portfolio.items():
                price = self.get_ticker(sym)
                if price: total += amount * price
            return total
        else:
            try:
                balance = self._call_private(lambda ex: ex.fetch_balance())
                total_equity = 0.0

                # Sumar valor de cada moneda en USDT
                for coin, amt in balance['total'].items():
                    if amt <= 0: continue
                    if coin in ['USDT', 'USD']:
                        total_equity += amt
                    else:
                        symbol = f"{coin}/USDT"
                        price = self.get_ticker(symbol)
                        if price:
                            total_equity += amt * price
                return total_equity
            except Exception as e:
                print(f"Error calculando equity total real: {self._sanitize_error(e)}")
                return 0.0

    def get_coin_balance(self, symbol):
        coin = symbol.split('/')[0]
        if self.modo_simulacion:
            self._refresh_simulated_state()
            return self.virtual_portfolio.get(symbol, 0.0)
        else:
            try:
                balance = self._call_private(lambda ex: ex.fetch_balance())
                return balance['total'].get(coin, 0.0)
            except Exception as e:
                print(f"Error obteniendo balance de {coin}: {self._sanitize_error(e)}")
                return 0.0

    def get_ticker(self, symbol):
        try:
            self._ensure_public_markets()
            if symbol not in self.public_exchange.markets:
                return None # Ignorar silenciosamente polvo sin mercado
        except Exception as e:
            self._log_exchange_warning("Aviso: no se pudieron validar mercados públicos", e)
                
        for attempt in range(2):
            try:
                ticker = self.public_exchange.fetch_ticker(symbol)
                return ticker['last']
            except Exception as e:
                if attempt == 1:
                    print(f"Error obteniendo ticker para {symbol}: {self._sanitize_error(e)}")
                    return None
                time.sleep(1) # Esperar un momento antes de reintentar

    def get_market_stats(self, symbol):
        for attempt in range(2):
            try:
                self._ensure_public_markets()
                ticker = self.public_exchange.fetch_ticker(symbol)
                return {
                    'change_24h': ticker.get('percentage'),
                    'vol_24h': ticker.get('quoteVolume')
                }
            except Exception as e:
                time.sleep(1)
        return {}

    def get_historical_data(self, symbol, timeframe='15m', limit=300):
        for attempt in range(3):
            try:
                self._ensure_public_markets()
                # fetch_ohlcv devuelve [timestamp, open, high, low, close, volume]
                ohlcv = self.public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                return ohlcv
            except Exception as e:
                if attempt == 2:
                    print(f"Error obteniendo datos históricos de {symbol}: {self._sanitize_error(e)}")
                    return []
                time.sleep(1.5) # Esperar 1.5s antes de reintentar

    def execute_order(self, symbol, side, amount, price=None, force_market=False):
        with self._order_lock:
            return self._execute_order_inner(symbol, side, amount, price, force_market)

    def _reconcile_created_order(self, exchange, symbol, order):
        order_id = order.get('id')
        if not order_id:
            return order
        deadline = time.time() + int(get_setting('ORDER_RECONCILE_TIMEOUT_SECONDS', 30) or 30)
        while str(order.get('status') or '').lower() == 'open' and time.time() < deadline:
            try:
                time.sleep(1.0)
                refreshed = exchange.fetch_order(order_id, symbol)
                if refreshed:
                    order.update(refreshed)
            except Exception as e:
                self._log_exchange_warning("Aviso: no se pudo reconciliar orden recién creada", e)
                break
        return self._normalize_order_status(order)

    def _normalize_order_status(self, order):
        status = str((order or {}).get('status') or '').lower()
        filled = float((order or {}).get('filled') or 0)
        if status == 'open' and filled > 0:
            order['status'] = 'partial'
        elif not status:
            order['status'] = 'partial' if filled > 0 else 'open'
        return order

    def reconcile_existing_order(self, symbol, exchange_order_id):
        if self.modo_simulacion:
            return {"status": "failed", "reason": "No reconciliation needed in simulation"}
        if not exchange_order_id:
            return {"status": "failed", "reason": "Missing exchange_order_id"}
        with self._order_lock:
            try:
                exchange = self._get_private_exchange()
                self._copy_public_markets_to_private()
                order = exchange.fetch_order(str(exchange_order_id), symbol)
                if not order:
                    return {"status": "failed", "reason": "Order not found"}
                return self._normalize_order_status(order)
            except Exception as e:
                return {"status": "failed", "reason": self._sanitize_error(e)}

    def _execute_order_inner(self, symbol, side, amount, price=None, force_market=False):
        """
        Ejecuta una orden. Si es simulación, actualiza los saldos virtuales.
        En simulación siempre asumimos que la orden se ejecuta al precio de mercado (ticker) actual.
        force_market=True omite el bloqueo de slippage para ventas manuales.
        """
        if self.modo_simulacion:
            self._refresh_simulated_state()
            if price is None:
                price = self.get_ticker(symbol)
            
            if side == 'buy':
                cost = amount * price
                if self.virtual_balance >= cost:
                    self.virtual_balance -= cost
                    self.virtual_portfolio[symbol] = self.virtual_portfolio.get(symbol, 0) + amount
                    self._save_simulated_state()
                    return {"status": "simulated", "side": side, "price": price, "amount": amount, "cost": cost}
                else:
                    return {"status": "failed", "reason": "Saldo virtual insuficiente"}
            elif side == 'sell':
                current_amount = self.virtual_portfolio.get(symbol, 0)
                if current_amount >= amount:
                    revenue = amount * price
                    self.virtual_balance += revenue
                    self.virtual_portfolio[symbol] -= amount
                    self._save_simulated_state()
                    return {"status": "simulated", "side": side, "price": price, "amount": amount, "filled": amount, "revenue": revenue}
                else:
                    return {"status": "failed", "reason": "Cantidad virtual insuficiente para vender"}
        else:
            max_retries = 3
            backoff = 2
            for attempt in range(max_retries):
                try:
                    exchange = self._get_private_exchange()
                    # Validaciones institucionales CCXT
                    self._copy_public_markets_to_private()
                    market = exchange.market(symbol)

                    # Venta real: nunca pedir más moneda base de la que hay LIBRE (fees/redondeo vs DB)
                    sell_amount_in = float(amount)
                    if side == "sell":
                        coin = symbol.split("/")[0]
                        bal = exchange.fetch_balance()
                        free_coin = float(bal.get("free", {}).get(coin) or 0)
                        if free_coin <= 0:
                            return {"status": "failed", "reason": "Saldo base libre insuficiente para vender"}
                        sell_amount_in = min(sell_amount_in, free_coin)
                        if sell_amount_in <= 0:
                            return {"status": "failed", "reason": "Saldo base libre insuficiente para vender"}
                        amount = sell_amount_in
                    
                    # Truncar cantidad a la precisión permitida
                    formatted_amount = float(exchange.amount_to_precision(symbol, amount))
                    if side == "sell":
                        if formatted_amount > free_coin:
                            formatted_amount = float(
                                exchange.amount_to_precision(symbol, free_coin * 0.9999)
                            )
                        if formatted_amount <= 0:
                            return {"status": "failed", "reason": "Ajuste de precisión: cantidad no vendible"}
                    
                    # Comprobar límites mínimos
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                    if min_amount and formatted_amount < min_amount:
                        return {"status": "failed", "reason": f"Cantidad {formatted_amount} menor al mínimo {min_amount}"}

                    # Control de Slippage: Comprobar el orderbook en lugar de ir a ciegas a mercado
                    ticker_price = price if price else self.get_ticker(symbol)
                    if ticker_price and not (force_market and side == "sell"):
                        orderbook = self.public_exchange.fetch_order_book(symbol, limit=5)
                        if side == 'buy':
                            asks = orderbook['asks']
                            if not asks:
                                raise Exception("Orderbook vacío en asks")
                            best_ask = asks[0][0]
                            slippage = abs(best_ask - ticker_price) / ticker_price
                            if slippage > BUY_SLIPPAGE_LIMIT:
                                return {"status": "failed", "reason": f"Slippage demasiado alto ({slippage*100:.2f}%)"}
                        elif side == 'sell':
                            bids = orderbook['bids']
                            if not bids:
                                raise Exception("Orderbook vacío en bids")
                            best_bid = bids[0][0]
                            slippage = abs(ticker_price - best_bid) / ticker_price
                            if slippage > SELL_SLIPPAGE_LIMIT:
                                return {"status": "failed", "reason": f"Slippage demasiado alto ({slippage*100:.2f}%)"}

                    # Ejecutar orden real
                    order = exchange.create_market_order(symbol, side, formatted_amount)
                    order = self._reconcile_created_order(exchange, symbol, order)
                    
                    # Validar estado
                    if order.get('status') in ['closed', 'partial', 'open']:
                        return order
                    else:
                        return {"status": "failed", "reason": f"Order status fallido: {order.get('status')}"}
                        
                except Exception as e:
                    error_msg = str(e).lower()
                    if self._is_nonce_error(e) and attempt < max_retries - 1:
                        self._reset_private_exchange()
                        time.sleep(0.35)
                        continue
                    if 'insufficient' in error_msg or 'balance' in error_msg:
                        print(f"Fondos insuficientes ejecutando orden real en {symbol}.")
                        return {"status": "failed", "reason": "Insufficient Funds"}

                    print(f"Error ejecutando orden real (Intento {attempt+1}/{max_retries}): {self._sanitize_error(e)}")
                    if attempt == max_retries - 1:
                        return {"status": "failed", "reason": self._sanitize_error(e)}
                    time.sleep(backoff)
                    backoff *= 2 # Exponential backoff

    def get_virtual_portfolio(self):
        self._refresh_simulated_state()
        return self.virtual_portfolio

    def liquidate_all_to_usdt(self):
        results = {"exitos": [], "fallos": []}
        if self.modo_simulacion:
            self._refresh_simulated_state()
            symbols_to_sell = list(self.virtual_portfolio.keys())
            for symbol in symbols_to_sell:
                amount = self.virtual_portfolio[symbol]
                if amount > 0:
                    price = self.get_ticker(symbol)
                    if price:
                        revenue = amount * price
                        self.virtual_balance += revenue
                        self.virtual_portfolio[symbol] = 0
                        results["exitos"].append({"symbol": symbol, "amount": amount, "price": price})
                    else:
                        results["fallos"].append({"symbol": symbol, "reason": "No se pudo obtener el precio"})
            # Eliminar monedas con saldo 0
            self.virtual_portfolio = {k: v for k, v in self.virtual_portfolio.items() if v > 0}
            self._save_simulated_state()
        else:
            try:
                exchange = self._get_private_exchange()
                self._copy_public_markets_to_private()
                balance = exchange.fetch_balance()
                free_balances = balance.get('free', {})
                for coin, amount in free_balances.items():
                    if coin in ['USDT', 'USD'] or amount <= 0:
                        continue
                    
                    symbol = f"{coin}/USDT"
                    try:
                        # Extraer limites del mercado
                        market = exchange.market(symbol)
                        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                        
                        # Formatear la cantidad a vender
                        formatted_amount = float(exchange.amount_to_precision(symbol, amount))
                        
                        if formatted_amount >= min_amount and formatted_amount > 0:
                            order = exchange.create_market_sell_order(symbol, formatted_amount)
                            price = order.get('price') or order.get('average') or self.get_ticker(symbol)
                            results["exitos"].append({"symbol": symbol, "amount": formatted_amount, "price": price})
                        else:
                            results["fallos"].append({"symbol": symbol, "reason": f"Polvo o cantidad demasiado pequeña: {formatted_amount} (min: {min_amount})"})
                    except Exception as e:
                        results["fallos"].append({"symbol": symbol, "reason": self._sanitize_error(e)})
            except Exception as e:
                print(f"Error obteniendo balances para liquidar: {self._sanitize_error(e)}")
                results["fallos"].append({"symbol": "ALL", "reason": f"Fallo al obtener balance: {self._sanitize_error(e)}"})
                
        return results

    def get_top_volume_symbols(self, limit=30):
        """Obtiene las monedas con más volumen de las últimas 24h en USDT"""
        try:
            self._ensure_public_markets()
            tickers = self.public_exchange.fetch_tickers()
            usdt_tickers = []
            
            for s, t in tickers.items():
                if s.endswith('/USDT'):
                    # Crypto.com a veces no mapea quoteVolume, lo sacamos de 'info' -> 'vv'
                    info = t.get('info', {})
                    volume = t.get('quoteVolume')
                    if volume is None:
                        volume = float(info.get('vv', 0))
                    
                    usdt_tickers.append({'symbol': s, 'volume': volume})
            
            # Ordenar por volumen de mayor a menor
            sorted_tickers = sorted(usdt_tickers, key=lambda x: x['volume'], reverse=True)
            return [t['symbol'] for t in sorted_tickers[:limit]]
        except Exception as e:
            print(f"Error obteniendo ranking de volumen: {self._sanitize_error(e)}")
            return []

    def get_spot_inventory_rows(self):
        """
        Inventario spot para la UI: moneda, libre, total, valor aprox. en USDT y par USDT si existe.
        """
        rows = []
        if self.modo_simulacion:
            rows.append({
                "coin": "USDT",
                "symbol": None,
                "free": float(self.virtual_balance),
                "total": float(self.virtual_balance),
                "usd_free": float(self.virtual_balance),
                "usd_total": float(self.virtual_balance),
            })
            for sym, amt in self.virtual_portfolio.items():
                amt = float(amt or 0)
                if amt <= 0:
                    continue
                coin = sym.split("/")[0]
                px = self.get_ticker(sym) or 0.0
                usd = amt * px
                rows.append({
                    "coin": coin,
                    "symbol": sym,
                    "free": amt,
                    "total": amt,
                    "usd_free": usd,
                    "usd_total": usd,
                })
            return sorted(rows, key=lambda x: -x["usd_total"])

        try:
            exchange = self._get_private_exchange()
            balance = exchange.fetch_balance()
            free_d = balance.get("free", {}) or {}
            tot_d = balance.get("total", {}) or {}
            coins = sorted(set(list(free_d.keys()) + list(tot_d.keys())))
            for coin in coins:
                free_c = float(free_d.get(coin) or 0)
                tot_c = float(tot_d.get(coin) or 0)
                if tot_c <= 0 and free_c <= 0:
                    continue
                sym = None
                if coin in ("USDT", "USD"):
                    px = 1.0
                else:
                    sym = f"{coin}/USDT"
                    px = self.get_ticker(sym) or 0.0
                    if not px and sym not in (self.public_exchange.markets or {}):
                        sym = None
                usd_tot = tot_c * px
                usd_fre = free_c * px
                rows.append({
                    "coin": coin,
                    "symbol": sym,
                    "free": free_c,
                    "total": tot_c,
                    "usd_free": usd_fre,
                    "usd_total": usd_tot,
                })
            return sorted(rows, key=lambda x: -x["usd_total"])
        except Exception as e:
            return [{"coin": "—", "symbol": None, "free": 0, "total": 0, "usd_free": 0, "usd_total": 0, "error": self._sanitize_error(e)}]

    def get_market_sell_constraints(self, symbol):
        """Límites del mercado CCXT para venta (cantidad mínima, coste mínimo, etc.)."""
        if not symbol or self.modo_simulacion:
            return None
        try:
            self._ensure_public_markets()
            if symbol not in self.public_exchange.markets:
                return None
            m = self.public_exchange.market(symbol)
            lim = m.get("limits") or {}
            amt_l = lim.get("amount") or {}
            cost_l = lim.get("cost") or {}
            prec = m.get("precision") or {}
            qty_step = prec.get("amount")
            info = m.get("info") or {}
            raw_min_qty = info.get("min_quantity") or info.get("minimum_order_quantity")
            raw_min_quote = (
                info.get("min_quote")
                or info.get("minimum_order_quote")
                or info.get("min_notional")
            )
            min_amount = amt_l.get("min")
            min_cost = cost_l.get("min")
            try:
                if min_amount is None and raw_min_qty is not None:
                    min_amount = float(raw_min_qty)
            except (TypeError, ValueError):
                pass
            try:
                if min_cost is None and raw_min_quote is not None:
                    min_cost = float(raw_min_quote)
            except (TypeError, ValueError):
                pass
            return {
                "symbol": symbol,
                "min_amount": min_amount,
                "max_amount": amt_l.get("max"),
                "min_cost": min_cost,
                "max_cost": cost_l.get("max"),
                "qty_step": qty_step,
                "amount_precision": prec.get("amount"),
                "price_precision": prec.get("price"),
            }
        except Exception:
            return None

    def prevalidate_market_sell(self, symbol, amount, price_hint=None, free_override=None, check_slippage=True):
        """
        Comprueba si una venta a mercado es viable (sin enviar orden).
        Devuelve dict: ok, errors[], info[], amount_after_precision (float|None)
        """
        out = {
            "ok": False,
            "errors": [],
            "info": [],
            "amount_after_precision": None,
            "requested_amount": None,
            "free_amount": None,
            "min_amount": None,
            "min_cost": None,
            "notional": None,
        }
        if amount is None or float(amount) <= 0:
            out["errors"].append("ZERO_AMOUNT")
            return out
        amount = float(amount)
        out["requested_amount"] = amount

        if self.modo_simulacion:
            have = float(self.virtual_portfolio.get(symbol, 0) or 0)
            if amount > have + 1e-12:
                out["errors"].append("INSUFFICIENT_VIRTUAL")
                return out
            out["free_amount"] = have
            out["amount_after_precision"] = amount
            out["ok"] = True
            out["info"].append("SIM_OK")
            return out

        if not symbol:
            out["errors"].append("NO_SYMBOL")
            return out

        coin = symbol.split("/")[0]
        try:
            if free_override is not None:
                free_c = float(free_override)
            else:
                exchange = self._get_private_exchange()
                bal = exchange.fetch_balance()
                free_c = float(bal.get("free", {}).get(coin) or 0)
            out["free_amount"] = free_c
        except Exception as e:
            out["errors"].append(f"BALANCE:{self._sanitize_error(e)}")
            return out

        capped = min(amount, free_c)
        if capped <= 0:
            out["errors"].append("NO_FREE_BALANCE")
            return out

        try:
            self._ensure_public_markets()
            if symbol not in self.public_exchange.markets:
                out["errors"].append("MARKET_NOT_LISTED")
                return out
            market = self.public_exchange.market(symbol)
            fmt = float(self.public_exchange.amount_to_precision(symbol, capped))
            out["amount_after_precision"] = fmt
            if fmt <= 0:
                out["errors"].append("PRECISION_ZERO")
                return out

            min_amt = (market.get("limits") or {}).get("amount", {}).get("min")
            out["min_amount"] = min_amt
            if min_amt is not None and fmt + 1e-12 < float(min_amt):
                out["errors"].append(f"BELOW_MIN_AMOUNT:{min_amt}")

            px = float(price_hint) if price_hint else (self.get_ticker(symbol) or 0.0)
            notional = fmt * px if px else 0.0
            out["notional"] = notional
            min_cost = (market.get("limits") or {}).get("cost", {}).get("min")
            out["min_cost"] = min_cost
            if min_cost is not None and notional + 1e-8 < float(min_cost):
                out["errors"].append(f"BELOW_MIN_COST:{min_cost}:{notional:.4f}")

            if out["errors"]:
                return out

            if check_slippage and px and px > 0:
                try:
                    ob = self.public_exchange.fetch_order_book(symbol, limit=5)
                    bids = ob.get("bids") or []
                    if bids:
                        best_bid = float(bids[0][0])
                        slip = abs(px - best_bid) / px
                        if slip > SELL_SLIPPAGE_LIMIT:
                            out["errors"].append(f"SLIPPAGE:{slip*100:.2f}%")
                except Exception:
                    pass

            if out["errors"]:
                return out

            out["ok"] = True
            out["info"].append(f"NOTIONAL_EST:{notional:.4f}")
            return out
        except Exception as e:
            out["errors"].append(self._sanitize_error(e))
            return out
