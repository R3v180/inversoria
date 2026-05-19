"""Fuentes de contexto compacto para el asistente IA (post-refactor)."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime

import config
from config_importer import CONFIG_SCHEMA


def safe_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def json_loads(raw, default=None):
    if default is None:
        default = {}
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def compact_priority_context(db, exchange) -> str:
    positions = db.get_open_positions()
    diag = json_loads(db.get_system_status("daemon_diagnostics", "{}"))
    risk_guards = diag.get("risk_guards") or {}
    mode = "simulación" if exchange.modo_simulacion else "REAL"
    lines = [
        f"Modo={mode}; equity={safe_float(exchange.get_balance()):.2f} USDT; "
        f"USDT libre={safe_float(exchange.get_usdt_balance()):.2f}; "
        f"posiciones={len(positions)}; bot_state={diag.get('state', '-')}; "
        f"ejecución={diag.get('execution_mode', '-')}",
    ]
    if diag.get("unreconciled_orders_count"):
        lines.append(f"Órdenes no reconciliadas: {diag.get('unreconciled_orders_count')}")
    if risk_guards:
        lines.append(
            f"Risk ok={risk_guards.get('ok')} daily_loss={risk_guards.get('daily_loss_pct', 0)}% "
            f"exposure={risk_guards.get('exposure_pct', 0)}% alt={risk_guards.get('alt_exposure_pct', 0)}% "
            f"reasons={risk_guards.get('reasons', [])}"
        )
    if diag.get("skipped"):
        lines.append("Bloqueos recientes: " + ", ".join(f"{k}:{v}" for k, v in diag.get("skipped", {}).items()))
    if diag.get("hold_reasons"):
        top_hold = list(diag.get("hold_reasons", {}).items())[:3]
        lines.append("HOLD principales: " + " | ".join(f"{v}x {k}" for k, v in top_hold))
    cooldowns = diag.get("ai_provider_cooldowns") or {}
    if cooldowns:
        lines.append(
            "Cooldown IA: "
            + ", ".join(f"{k}={v.get('cooldown_in', 0)}s" for k, v in cooldowns.items())
        )
    return "\n".join(lines)


def compact_settings_context(exchange) -> str:
    mode = "simulación" if exchange.modo_simulacion else "REAL"
    effective = config.get_effective_max_positions(safe_float(exchange.get_balance()))
    allowed_config = ", ".join(CONFIG_SCHEMA.keys())
    return "\n".join([
        f"Modo={mode}",
        f"TRADING_EXECUTION_MODE={getattr(config, 'TRADING_EXECUTION_MODE', 'auto')}; "
        f"DECISION_MODE={getattr(config, 'DECISION_MODE', 'hybrid')}; "
        f"MIN_AUTO_DECISION_SCORE={getattr(config, 'MIN_AUTO_DECISION_SCORE', 0.62):.2f}",
        f"RISK_PER_TRADE={config.RISK_PER_TRADE:.2%}",
        f"VOLATILITY_SIZING_ENABLED={getattr(config, 'VOLATILITY_SIZING_ENABLED', True)}; "
        f"MAX_POSITION_RISK={getattr(config, 'MAX_POSITION_RISK_PCT', 0):.2%}; "
        f"MIN_POSITION_USDT={getattr(config, 'MIN_POSITION_USDT', 1.0):.2f}",
        f"MAX_DAILY_LOSS={getattr(config, 'MAX_DAILY_LOSS_PCT', 0):.2%}; "
        f"MAX_PORTFOLIO_EXPOSURE={getattr(config, 'MAX_PORTFOLIO_EXPOSURE_PCT', 0):.2%}; "
        f"MAX_SYMBOL_EXPOSURE={getattr(config, 'MAX_SYMBOL_EXPOSURE_PCT', 0):.2%}; "
        f"MAX_ALT_EXPOSURE={getattr(config, 'MAX_ALT_EXPOSURE_PCT', 0):.2%}; "
        f"MAX_BUCKET_EXPOSURE={getattr(config, 'MAX_BUCKET_EXPOSURE_PCT', 0):.2%}",
        f"ADAPTIVE_SCORING_ENABLED={getattr(config, 'ADAPTIVE_SCORING_ENABLED', True)}; "
        f"ADAPTIVE_MIN_TRADES={getattr(config, 'ADAPTIVE_MIN_TRADES', 5)}; "
        f"ADAPTIVE_MAX_SCORE_ADJUSTMENT={getattr(config, 'ADAPTIVE_MAX_SCORE_ADJUSTMENT', 0.12):.2f}",
        f"MAX_OPEN_POSITIONS={config.MAX_OPEN_POSITIONS}; límite efectivo={effective}; "
        f"prioridad manual={config.get_setting('MANUAL_MAX_POSITIONS_PRIORITY', False, bool)}",
        f"MIN_PROFIT_NET={config.get_setting('MIN_PROFIT_NET', 1.0, float):.2f}%",
        f"ROTATION_ENABLED={config.ROTATION_ENABLED}; ROTATION_MIN_PROFIT={config.ROTATION_MIN_PROFIT:.2f}%; "
        f"GAP={config.ROTATION_CONFIDENCE_GAP:.2f}; MIN_NEW_CONF={config.ROTATION_MIN_NEW_CONFIDENCE:.2f}",
        f"BUY_SLIPPAGE_LIMIT={config.BUY_SLIPPAGE_LIMIT:.2%}; SELL_SLIPPAGE_LIMIT={config.SELL_SLIPPAGE_LIMIT:.2%}; "
        f"TRADING_FEE_RATE={config.TRADING_FEE_RATE:.3%}",
        f"AI_ANALYSIS_INTERVAL={config.AI_ANALYSIS_INTERVAL}s",
        f"CONFIG_IMPORT_KEYS_PERMITIDAS={allowed_config}",
    ])


def compact_positions_context(db, exchange, max_items=10) -> str:
    positions = db.get_open_positions()
    if not positions:
        return "Sin posiciones abiertas gestionadas por el bot."
    lines = []
    for sym, pos in list(positions.items())[:max_items]:
        entry = safe_float(pos.get("entry_price"))
        amount = safe_float(pos.get("amount"))
        px = safe_float(exchange.get_ticker(sym), entry)
        value = amount * px
        pnl = ((px - entry) / entry * 100.0) if entry > 0 else 0.0
        lines.append(
            f"{sym}: qty={amount:.8g}; entry={entry:.8g}; px={px:.8g}; "
            f"valor~{value:.2f} USDT; PnL={pnl:+.2f}%"
        )
    return "\n".join(lines)


def compact_wallet_context(db, exchange, max_rows=8) -> str:
    try:
        rows = exchange.get_spot_inventory_rows()
    except Exception as exc:
        return f"No se pudo leer cartera exchange: {exc}"
    if not rows or rows[0].get("error"):
        err = rows[0].get("error") if rows else "sin datos"
        return f"Cartera exchange no disponible: {err}"

    open_pos = db.get_open_positions()
    recoverable = []
    bot_assets = []
    blocked = []
    untracked_value = 0.0

    for row in rows:
        sym = row.get("symbol")
        coin = row.get("coin")
        if coin in ("USDT", "USD") or not sym:
            continue
        free = safe_float(row.get("free"))
        usd_free = safe_float(row.get("usd_free"))
        if usd_free > 0 and sym not in open_pos:
            untracked_value += usd_free
        if free <= 0:
            continue
        if sym in open_pos:
            bot_assets.append((usd_free, f"{sym}: libre~{usd_free:.2f} USDT (posición bot)"))
            continue
        px = safe_float(exchange.get_ticker(sym))
        pv = exchange.prevalidate_market_sell(sym, free, px, free_override=free)
        if pv.get("ok"):
            recoverable.append((usd_free, f"{sym}: recuperable libre~{usd_free:.2f} USDT"))
        else:
            errs = ",".join(pv.get("errors", [])[:2])
            blocked.append((usd_free, f"{sym}: no vendible ahora libre~{usd_free:.2f} USDT ({errs})"))

    def top_text(items):
        items = sorted(items, key=lambda x: -x[0])[:max_rows]
        return "\n".join(x[1] for x in items) if items else "(ninguno)"

    return "\n".join([
        f"Valor libre no gestionado aprox: {untracked_value:.2f} USDT",
        "Recuperables sin posición bot:",
        top_text(recoverable),
        "Saldos libres en posición bot:",
        top_text(bot_assets),
        "No vendibles principales:",
        top_text(blocked),
    ])


def compact_daemon_context(db) -> str:
    diag = json_loads(db.get_system_status("daemon_diagnostics", "{}"))
    if not diag:
        return "Sin diagnóstico del daemon todavía."

    state = diag.get("state", "-")
    scanned = diag.get("scanned", 0)
    actions = diag.get("actions", {})
    providers = diag.get("providers", {})
    holds = diag.get("hold_reasons", {})
    skipped = diag.get("skipped", {})
    open_pos = diag.get("open_positions", 0)
    dyn_max = diag.get("dynamic_max", "-")
    cycle_age = "-"
    if diag.get("cycle_ts"):
        cycle_age = f"{max(0, int(time.time() - float(diag.get('cycle_ts'))))}s"

    lines = [
        f"Estado={state}; último ciclo={cycle_age}; escaneados={scanned}; posiciones={open_pos}/{dyn_max}",
        "Acciones ciclo: " + (", ".join(f"{k}:{v}" for k, v in actions.items()) if actions else "N/A"),
        "Providers: " + (", ".join(f"{k}:{v}" for k, v in providers.items()) if providers else "N/A"),
    ]
    if skipped:
        lines.append("Skipped: " + ", ".join(f"{k}:{v}" for k, v in skipped.items()))
    if diag.get("top_buy_candidates"):
        lines.append(
            "Top BUY candidates: "
            + " | ".join(
                f"{c.get('symbol')} score={c.get('score')} "
                f"decision={float(c.get('decision_score', 0)):.0%} conf={float(c.get('confidence', 0)):.0%}"
                for c in diag.get("top_buy_candidates", [])[:5]
            )
        )
    if diag.get("risk_guards"):
        rg = diag.get("risk_guards", {})
        lines.append(
            f"Risk guards: ok={rg.get('ok')} daily_loss={rg.get('daily_loss_pct', 0)}% "
            f"exposure={rg.get('exposure_pct', 0)}% alt={rg.get('alt_exposure_pct', 0)}% "
            f"bucket={rg.get('bucket_exposure_pct', 0)}% reasons={rg.get('reasons', [])}"
        )
    if holds:
        top = list(holds.items())[:5]
        lines.append("Top HOLD reasons: " + " | ".join(f"{v}x {k}" for k, v in top))
    if diag.get("symbol_cooldowns"):
        lines.append(f"Cooldowns símbolo: {diag.get('symbol_cooldowns')}")
    if diag.get("order_reconcile"):
        lines.append(f"Order reconcile: {diag.get('order_reconcile')}")
    return "\n".join(lines)


def compact_macro_context(db) -> str:
    lines = []
    macro = json_loads(db.get_system_status("macro_context", "{}"))
    if macro:
        for key in (
            "macro_regime",
            "btc_dominance",
            "btc_dominance_trend",
            "market_cap_change_24h",
            "leading_sector",
        ):
            if macro.get(key) is not None:
                lines.append(f"{key}={macro.get(key)}")
    try:
        macro_db = db.get_all_macro_data()
        for sym in ("UUP", "SPY"):
            if sym in macro_db:
                d = macro_db[sym]
                ch = d.get("change_24h")
                ch_txt = f"{float(ch):+.2f}%" if ch is not None else "N/A"
                lines.append(f"{sym}: price={d.get('price')} change_24h={ch_txt}")
    except Exception as exc:
        lines.append(f"macro_db no disponible: {exc}")
    return "\n".join(lines) if lines else "Sin macro_context disponible."


def compact_decisions_context(db, symbols) -> str:
    lines = []
    seen = []
    for sym in symbols:
        if sym and sym not in seen:
            seen.append(sym)
    for sym in seen[:12]:
        raw = db.get_system_status(f"decision_{sym}")
        if not raw:
            continue
        dec = json_loads(raw)
        reason = str(dec.get("reasoning", ""))[:100]
        lines.append(
            f"{sym}: {dec.get('action', 'HOLD')} conf={safe_float(dec.get('confidence')):.0%} "
            f"exec={dec.get('executable_action', dec.get('action', 'HOLD'))} "
            f"score={safe_float(dec.get('decision_score')):.0%} "
            f"regime={dec.get('regime', '-')} strategy={dec.get('best_strategy', '-')} reason={reason}"
        )
    return "\n".join(lines) if lines else "Sin decisiones recientes por símbolo."


def compact_journal_context(db) -> str:
    if not hasattr(db, "get_decision_metrics"):
        return "Decision journal no disponible."
    try:
        metrics = db.get_decision_metrics(limit=500)
    except Exception as exc:
        return f"Decision journal no disponible: {exc}"
    lines = [
        f"Decisiones journal={metrics.get('total_decisions', 0)}; "
        f"BUY ejecutadas={metrics.get('accepted_buys', 0)}; "
        f"bloqueos/señales={metrics.get('blocked', 0)}; "
        f"IA alineada={metrics.get('ai_alignment_pct', 0):.1f}%",
    ]
    provider_stats = metrics.get("provider_stats")
    if provider_stats is not None and not provider_stats.empty:
        top = provider_stats.head(5)
        lines.append(
            "Provider stats: "
            + " | ".join(
                f"{r.get('provider', 'N/A')} trades={r.get('trades')} "
                f"WR={r.get('win_rate')}% exp={r.get('expectancy_pct')}%"
                for _, r in top.iterrows()
            )
        )
    regime_stats = metrics.get("regime_stats")
    if regime_stats is not None and not regime_stats.empty:
        top = regime_stats.head(5)
        lines.append(
            "Regime stats: "
            + " | ".join(
                f"{r.get('regime', 'N/A')} trades={r.get('trades')} "
                f"WR={r.get('win_rate')}% exp={r.get('expectancy_pct')}%"
                for _, r in top.iterrows()
            )
        )
    return "\n".join(lines)


def compact_adaptive_edge_context(db) -> str:
    if not hasattr(db, "get_adaptive_edge_snapshot"):
        return "Adaptive edge no disponible."
    try:
        edge = db.get_adaptive_edge_snapshot(limit=1000, min_trades=5)
    except Exception as exc:
        return f"Adaptive edge no disponible: {exc}"
    if not edge.get("enabled"):
        return "Adaptive edge sin muestra cerrada suficiente."
    g = edge.get("global") or {}
    lines = [
        f"Global: trades={g.get('trades')} WR={g.get('win_rate')}% "
        f"exp={g.get('expectancy_pct')}% PF={g.get('profit_factor')} adj={g.get('adjustment')}",
        f"Rolling exp={edge.get('rolling_expectancy_pct')}% decay={edge.get('edge_decay_pct')}%",
    ]
    for label, bucket in (("Provider", edge.get("by_provider")), ("Regime", edge.get("by_regime"))):
        if not bucket:
            continue
        top = sorted(bucket.items(), key=lambda x: -x[1].get("trades", 0))[:4]
        lines.append(
            f"{label} edge: "
            + " | ".join(
                f"{name} trades={s.get('trades')} exp={s.get('expectancy_pct')}% adj={s.get('adjustment')}"
                for name, s in top
            )
        )
    return "\n".join(lines)


def compact_backtest_context(db) -> str:
    try:
        with sqlite3.connect(db.db_path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            runs = conn.execute(
                "SELECT symbol, timeframe, win_rate, best_strategy "
                "FROM backtest_runs ORDER BY run_timestamp DESC LIMIT 5"
            ).fetchall()
        if not runs:
            return "Sin datos de backtest."
        return ", ".join(
            f"{r['symbol']} {r['timeframe']} WR:{r['win_rate']:.0%} best:{r['best_strategy']}"
            for r in runs
        )
    except Exception as exc:
        return f"Backtest no disponible: {exc}"


def compact_chat_context(db, limit=6) -> str:
    try:
        rows = db.get_chat_history(limit=limit)
    except Exception as exc:
        return f"Historial no disponible: {exc}"
    if not rows:
        return "Sin conversación previa relevante."
    lines = []
    for row in rows[-limit:]:
        role = str(row.get("role") or "-")[:12]
        content = " ".join(str(row.get("content") or "").split())
        if content:
            lines.append(f"{role}: {content[:260]}")
    return "\n".join(lines) if lines else "Sin conversación previa relevante."


def compact_pending_orders_context(db) -> str:
    diag = json_loads(db.get_system_status("daemon_diagnostics", "{}"))
    count = int(diag.get("unreconciled_orders_count") or 0)
    if count <= 0:
        return "Sin órdenes pendientes de reconciliación."
    lines = [f"Órdenes no reconciliadas: {count}"]
    for row in (diag.get("unreconciled_orders") or [])[:8]:
        lines.append(
            f"{row.get('symbol')} side={row.get('side')} status={row.get('status')} "
            f"id={row.get('local_order_id') or row.get('exchange_order_id')}"
        )
    return "\n".join(lines)


def compact_periods_context(db, exchange) -> str:
    from ui_services.performance_period import compute_period_performance, preset_start_datetime

    now = datetime.now()
    lines = []
    balance = safe_float(exchange.get_balance())
    for label in ("Hoy 00:00", "Última hora", "Últimas 24h"):
        perf = compute_period_performance(db, balance, preset_start_datetime(label, now))
        if perf.get("ok"):
            lines.append(
                f"{label}: {perf['pnl_usd']:+.2f} USDT ({perf['pnl_pct']:+.2f}%) desde {perf['start_ts']}"
            )
    return "\n".join(lines) if lines else "Sin equity_history suficiente."
