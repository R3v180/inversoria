import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

def debug():
    exchange = ccxt.cryptocom({
        'apiKey': os.getenv('CRYPTO_API_KEY'),
        'secret': os.getenv('CRYPTO_API_SECRET'),
    })
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = [s for s in tickers.keys() if '/USDT' in s]
        if usdt_pairs:
            symbol = usdt_pairs[0]
            ticker = tickers[symbol]
            print(f"Keys for {symbol}: {ticker.keys()}")
            print(f"Full data for {symbol}: {ticker}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug()
