import ccxt
import time
import datetime
import json
import os
from config import CRYPTO_API_KEY, CRYPTO_API_SECRET, MODO_SIMULACION, PRESUPUESTO_INICIAL

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
                return balance['total'].get('USDT', 0.0) # CCXT suele sumar todo en total['USDT'] si es la moneda base
            except Exception as e:
                print(f"Error obteniendo balance total: {e}")
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

    def execute_order(self, symbol, side, amount, price=None):
        """
        Ejecuta una orden. Si es simulación, actualiza los saldos virtuales.
        En simulación siempre asumimos que la orden se ejecuta al precio de mercado (ticker) actual.
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
                    return {"status": "simulated", "side": side, "price": price, "amount": amount, "revenue": revenue}
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
                    
                    # Truncar cantidad a la precisión permitida
                    formatted_amount = float(self.exchange.amount_to_precision(symbol, amount))
                    
                    # Comprobar límites mínimos
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                    if min_amount and formatted_amount < min_amount:
                        return {"status": "failed", "reason": f"Cantidad {formatted_amount} menor al mínimo {min_amount}"}

                    # Control de Slippage: Comprobar el orderbook en lugar de ir a ciegas a mercado
                    ticker_price = price if price else self.get_ticker(symbol)
                    if ticker_price:
                        orderbook = self.exchange.fetch_order_book(symbol, limit=5)
                        if side == 'buy':
                            asks = orderbook['asks']
                            if not asks:
                                raise Exception("Orderbook vacío en asks")
                            best_ask = asks[0][0]
                            slippage = abs(best_ask - ticker_price) / ticker_price
                            if slippage > 0.005: # > 0.5%
                                return {"status": "failed", "reason": f"Slippage demasiado alto ({slippage*100:.2f}%)"}
                        elif side == 'sell':
                            bids = orderbook['bids']
                            if not bids:
                                raise Exception("Orderbook vacío en bids")
                            best_bid = bids[0][0]
                            slippage = abs(ticker_price - best_bid) / ticker_price
                            if slippage > 0.005:
                                return {"status": "failed", "reason": f"Slippage demasiado alto ({slippage*100:.2f}%)"}

                    # Ejecutar orden real
                    order = self.exchange.create_market_order(symbol, side, formatted_amount)
                    
                    # Validar estado
                    if order.get('status') in ['closed', 'open']:
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
