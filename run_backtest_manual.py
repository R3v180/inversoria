"""
run_backtest_manual.py — Ejecuta el backtest manualmente para uno o varios símbolos.

Uso:
    python run_backtest_manual.py                     # Usa los símbolos del config
    python run_backtest_manual.py BTC/USDT ETH/USDT  # Símbolos específicos
    python run_backtest_manual.py --years 5           # 5 años de histórico
    python run_backtest_manual.py --timeframe 1d      # Timeframe diario
"""
import sys
import argparse
import time
from exchange_helper import ExchangeHelper
from backtest_engine import BacktestEngine
import config


def main():
    parser = argparse.ArgumentParser(description='Inversoria — Backtest Manual')
    parser.add_argument('symbols', nargs='*', help='Símbolos a testear (ej: BTC/USDT ETH/USDT)')
    parser.add_argument('--years', type=float, default=2.0, help='Años de histórico (default: 2)')
    parser.add_argument('--timeframe', type=str, default='4h',
                        choices=['15m', '1h', '4h', '1d'], help='Timeframe (default: 4h)')
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else config.SYMBOLS
    years = args.years
    timeframe = args.timeframe

    print(f"\n{'='*60}")
    print(f"  INVERSORIA — Backtest Manual")
    print(f"  Símbolos: {', '.join(symbols)}")
    print(f"  Período: {years} años | Timeframe: {timeframe}")
    print(f"{'='*60}\n")

    exchange = ExchangeHelper(modo_simulacion=True)
    bt = BacktestEngine(exchange)

    all_results = {}

    for symbol in symbols:
        print(f"\n{'─'*40}")
        print(f"Analizando {symbol}...")
        print(f"{'─'*40}")

        try:
            results = bt.run_full_backtest(symbol, timeframe=timeframe, years=years)
            all_results[symbol] = results

            if results:
                print(f"\n📊 RESULTADOS {symbol}:")
                print(f"{'Estrategia':<20} {'Trades':>7} {'Win Rate':>9} {'Profit Factor':>14} {'Retorno':>9} {'Drawdown':>10}")
                print("-" * 75)

                for strategy, r in sorted(results.items(), key=lambda x: x[1].get('profit_factor', 0), reverse=True):
                    if r.get('total_trades', 0) > 0:
                        print(
                            f"{strategy:<20} "
                            f"{r['total_trades']:>7} "
                            f"{r['win_rate']:>8.0%} "
                            f"{r['profit_factor']:>14.2f} "
                            f"{r['total_return_pct']:>+8.1f}% "
                            f"{r['max_drawdown_pct']:>+9.1f}%"
                        )

        except Exception as e:
            print(f"❌ Error en {symbol}: {e}")

        time.sleep(2)  # Pausa entre símbolos para respetar rate limits

    print(f"\n{'='*60}")
    print("✅ Backtest completado. Resultados guardados en iversoria.db")
    print("El bot usará estos datos como prior en sus próximas decisiones.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
