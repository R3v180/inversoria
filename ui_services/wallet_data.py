from __future__ import annotations


def build_wallet_snapshot(db, exchange):
    open_pos = db.get_open_positions()
    rows = exchange.get_spot_inventory_rows()
    equity = float(exchange.get_balance() or 0)
    symbols = [r.get("symbol") for r in rows if r.get("symbol")] + list(open_pos.keys())
    exchange.prefetch_tickers(list(dict.fromkeys(s for s in symbols if s)))

    tracked_usd = 0.0
    for sym, pos in open_pos.items():
        px = exchange.get_ticker(sym) or float(pos.get("entry_price") or 0)
        tracked_usd += float(pos.get("amount") or 0) * float(px or 0)

    sum_rows_usd = sum(float(r.get("usd_total") or 0) for r in rows)
    untracked = max(0.0, sum_rows_usd - tracked_usd)

    watch_rows = []
    if hasattr(db, "get_exchange_balance_watch"):
        try:
            watch_rows = db.get_exchange_balance_watch(limit=200)
        except Exception:
            watch_rows = []

    return {
        "rows": rows,
        "open_pos": open_pos,
        "equity": equity,
        "tracked_usd": tracked_usd,
        "untracked": untracked,
        "watch_rows": watch_rows,
    }
