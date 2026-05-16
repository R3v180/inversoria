import ccxt
import time
import datetime
import json
import os
from config import (
    CRYPTO_API_KEY,
    CRYPTO_API_SECRET,
    MODO_SIMULACION,
    PRESUPUESTO_INICIAL,
    BUY_SLIPPAGE_LIMIT,
    SELL_SLIPPAGE_LIMIT,
)

class ExchangeHelper:
    def __init__(self, modo_simulacion=True):
        self.modo_simulacion = modo_simulacion
        self.virtual_balance = PRESUPUESTO_INICIAL
        self.virtual_portfolio = {} # symbol -> amount
        
        if self.modo_simulacion:
            self._load_simulated_state()
            
        # Inicializar CCXT para Crypto.com
        try:
            self.exchange = ccxt.cryptocom({
                'apiKey': CRYPTO_API_KEY,
                'secret': CRYPTO_API_SECRET,
                'enableRateLimit': True,
            })
            self.exchange.load_markets()
            if not self.modo_simulacion:
                self.exchange.check_required_credentials()
        except Exception as e:
            print(f"Error al inicializar Exchange: {e}")

    def _save_simulated_state(self):
        with open('simulated_account.json', 'w') as f:
            json.dump({
                'virtual_balance': self.virtual_balance,
                'virtual_portfolio': self.virtual_portfolio
            }, f)

    def _load_simulated_state(self):
        if os.path.exists('simulated_account.json'):
            try:
                with open('simulated_account.json', 'r') as f:
                    data = json.load(f)
                    self.virtual_balance = data.get('virtual_balance', PRESUPUESTO_INICIAL)
                    self.virtual_portfolio = data.get('virtual_portfolio', {})
            except Exception as e:
                print(f"Error cargando estado simulado: {e}")

    def get_usdt_balance(self):
        """Retorna solo el cash disponible (USDT)"""
        if self.modo_simulacion:
            return self.virtual_balance
        else:
            try:
                balance = self.exchange.fetch_balance()
                return balance['free'].get('USDT', 0.0)
            except Exception as e:
                print(f"Error obteniendo balance USDT: {e}")
                return 0.0

    def get_balance(self):
        """Retorna la Equity Total (Cash + Valor de Criptos)"""
        if self.modo_simulacion:
            total = self.virtual_balance
            for sym, amount in self.virtual_portfolio.items():
                price = self.get_ticker(sym)
                if price: total += amount * price
            return total
        else:
            try:
                balance = self.exchange.fetch_balance()
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
                print(f"Error calculando equity total real: {e}")
                return 0.0

    def get_coin_balance(self, symbol):
        coin = symbol.split('/')[0]
        if self.modo_simulacion:
            return self.virtual_portfolio.get(symbol, 0.0)
        else:
            try:
                balance = self.exchange.fetch_balance()
                return balance['total'].get(coin, 0.0)
            except Exception as e:
                print(f"Error obteniendo balance de {coin}: {e}")
                return 0.0

    def get_ticker(self, symbol):
        if not self.modo_simulacion:
            try:
                if not self.exchange.markets:
                    self.exchange.load_markets()
                if symbol not in self.exchange.markets:
                    return None # Ignorar silenciosamente polvo sin mercado
            except Exception:
                pass
                
        for attempt in range(2):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                return ticker['last']
            except Exception as e:
                if attempt == 1:
                    print(f"Error obteniendo ticker para {symbol}: {e}")
                    return None
                time.sleep(1) # Esperar un momento antes de reintentar

    def get_market_stats(self, symbol):
        for attempt in range(2):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
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
                # fetch_ohlcv devuelve [timestamp, open, high, low, close, volume]
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                return ohlcv
            except Exception as e:
                if attempt == 2:
                    print(f"Error obteniendo datos históricos de {symbol}: {e}")
                    return []
                time.sleep(1.5) # Esperar 1.5s antes de reintentar

    def execute_order(self, symbol, side, amount, price=None, force_market=False):
        """
        Ejecuta una orden. Si es simulación, actualiza los saldos virtuales.
        En simulación siempre asumimos que la orden se ejecuta al precio de mercado (ticker) actual.
        force_market=True omite el bloqueo de slippage para ventas manuales.
        """
        if self.modo_simulacion:
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
                    # Validaciones institucionales CCXT
                    self.exchange.load_markets()
                    market = self.exchange.market(symbol)

                    # Venta real: nunca pedir más moneda base de la que hay LIBRE (fees/redondeo vs DB)
                    sell_amount_in = float(amount)
                    if side == "sell":
                        coin = symbol.split("/")[0]
                        bal = self.exchange.fetch_balance()
                        free_coin = float(bal.get("free", {}).get(coin) or 0)
                        if free_coin <= 0:
                            return {"status": "failed", "reason": "Saldo base libre insuficiente para vender"}
                        sell_amount_in = min(sell_amount_in, free_coin)
                        if sell_amount_in <= 0:
                            return {"status": "failed", "reason": "Saldo base libre insuficiente para vender"}
                        amount = sell_amount_in
                    
                    # Truncar cantidad a la precisión permitida
                    formatted_amount = float(self.exchange.amount_to_precision(symbol, amount))
                    if side == "sell":
                        bal2 = self.exchange.fetch_balance()
                        free2 = float(bal2.get("free", {}).get(coin) or 0)
                        if formatted_amount > free2:
                            formatted_amount = float(
                                self.exchange.amount_to_precision(symbol, free2 * 0.9999)
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
                        orderbook = self.exchange.fetch_order_book(symbol, limit=5)
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
                    order = self.exchange.create_market_order(symbol, side, formatted_amount)
                    
                    # Validar estado
                    if order.get('status') in ['closed', 'open'] or order.get('id'):
                        if not order.get('status'):
                            order['status'] = 'closed'
                        return order
                    else:
                        return {"status": "failed", "reason": f"Order status fallido: {order.get('status')}"}
                        
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'insufficient' in error_msg or 'balance' in error_msg:
                        print(f"Fondos insuficientes ejecutando orden real en {symbol}.")
                        return {"status": "failed", "reason": "Insufficient Funds"}
                    
                    print(f"Error ejecutando orden real (Intento {attempt+1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        return {"status": "failed", "reason": str(e)}
                    time.sleep(backoff)
                    backoff *= 2 # Exponential backoff

    def get_virtual_portfolio(self):
        return self.virtual_portfolio

    def liquidate_all_to_usdt(self):
        results = {"exitos": [], "fallos": []}
        if self.modo_simulacion:
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
                self.exchange.load_markets() # Asegurar mercados cargados
                balance = self.exchange.fetch_balance()
                free_balances = balance.get('free', {})
                for coin, amount in free_balances.items():
                    if coin in ['USDT', 'USD'] or amount <= 0:
                        continue
                    
                    symbol = f"{coin}/USDT"
                    try:
                        # Extraer limites del mercado
                        market = self.exchange.market(symbol)
                        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                        
                        # Formatear la cantidad a vender
                        formatted_amount = float(self.exchange.amount_to_precision(symbol, amount))
                        
                        if formatted_amount >= min_amount and formatted_amount > 0:
                            order = self.exchange.create_market_sell_order(symbol, formatted_amount)
                            price = order.get('price') or order.get('average') or self.get_ticker(symbol)
                            results["exitos"].append({"symbol": symbol, "amount": formatted_amount, "price": price})
                        else:
                            results["fallos"].append({"symbol": symbol, "reason": f"Polvo o cantidad demasiado pequeña: {formatted_amount} (min: {min_amount})"})
                    except Exception as e:
                        results["fallos"].append({"symbol": symbol, "reason": str(e)})
            except Exception as e:
                print(f"Error obteniendo balances para liquidar: {e}")
                results["fallos"].append({"symbol": "ALL", "reason": f"Fallo al obtener balance: {e}"})
                
        return results

    def get_top_volume_symbols(self, limit=30):
        """Obtiene las monedas con más volumen de las últimas 24h en USDT"""
        try:
            tickers = self.exchange.fetch_tickers()
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
            print(f"Error obteniendo ranking de volumen: {e}")
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
            balance = self.exchange.fetch_balance()
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
                    if not px and sym not in (self.exchange.markets or {}):
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
            return [{"coin": "—", "symbol": None, "free": 0, "total": 0, "usd_free": 0, "usd_total": 0, "error": str(e)}]

    def get_market_sell_constraints(self, symbol):
        """Límites del mercado CCXT para venta (cantidad mínima, coste mínimo, etc.)."""
        if not symbol or self.modo_simulacion:
            return None
        try:
            if not self.exchange.markets:
                self.exchange.load_markets()
            if symbol not in self.exchange.markets:
                return None
            m = self.exchange.market(symbol)
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

    def prevalidate_market_sell(self, symbol, amount, price_hint=None, free_override=None):
        """
        Comprueba si una venta a mercado es viable (sin enviar orden).
        Devuelve dict: ok, errors[], info[], amount_after_precision (float|None)
        """
        out = {"ok": False, "errors": [], "info": [], "amount_after_precision": None}
        if amount is None or float(amount) <= 0:
            out["errors"].append("ZERO_AMOUNT")
            return out
        amount = float(amount)

        if self.modo_simulacion:
            have = float(self.virtual_portfolio.get(symbol, 0) or 0)
            if amount > have + 1e-12:
                out["errors"].append("INSUFFICIENT_VIRTUAL")
                return out
            out["amount_after_precision"] = amount
            out["ok"] = True
            out["info"].append("SIM_OK")
            return out

        if not symbol:
            out["errors"].append("NO_SYMBOL")
            return out

        coin = symbol.split("/")[0]
        try:
            bal = self.exchange.fetch_balance()
            free_c = float(free_override) if free_override is not None else float(bal.get("free", {}).get(coin) or 0)
        except Exception as e:
            out["errors"].append(f"BALANCE:{e}")
            return out

        capped = min(amount, free_c)
        if capped <= 0:
            out["errors"].append("NO_FREE_BALANCE")
            return out

        try:
            if not self.exchange.markets:
                self.exchange.load_markets()
            if symbol not in self.exchange.markets:
                out["errors"].append("MARKET_NOT_LISTED")
                return out
            market = self.exchange.market(symbol)
            fmt = float(self.exchange.amount_to_precision(symbol, capped))
            out["amount_after_precision"] = fmt
            if fmt <= 0:
                out["errors"].append("PRECISION_ZERO")
                return out

            min_amt = (market.get("limits") or {}).get("amount", {}).get("min")
            if min_amt is not None and fmt + 1e-12 < float(min_amt):
                out["errors"].append(f"BELOW_MIN_AMOUNT:{min_amt}")

            px = float(price_hint) if price_hint else (self.get_ticker(symbol) or 0.0)
            notional = fmt * px if px else 0.0
            min_cost = (market.get("limits") or {}).get("cost", {}).get("min")
            if min_cost is not None and notional + 1e-8 < float(min_cost):
                out["errors"].append(f"BELOW_MIN_COST:{min_cost}:{notional:.4f}")

            if out["errors"]:
                return out

            if px and px > 0:
                try:
                    ob = self.exchange.fetch_order_book(symbol, limit=5)
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
            out["errors"].append(str(e))
            return out
