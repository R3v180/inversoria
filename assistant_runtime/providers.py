from __future__ import annotations

from diagnostic_utils import read_recent_log_summary
from .context_sources import (
    compact_adaptive_edge_context,
    compact_backtest_context,
    compact_chat_context,
    compact_daemon_context,
    compact_decisions_context,
    compact_journal_context,
    compact_macro_context,
    compact_pending_orders_context,
    compact_periods_context,
    compact_positions_context,
    compact_priority_context,
    compact_settings_context,
    compact_wallet_context,
)
from .runtime import RuntimeContext, ContextProviderRegistry, build_default_action_registry

_ESSENTIAL_SECTIONS = frozenset({
    "PRIORIDAD / ESTADO CRÍTICO",
    "MEMORIA CHAT RECIENTE",
    "ACCIONES CONFIRMABLES",
})


def _provider_priority(ctx: RuntimeContext) -> str:
    return compact_priority_context(ctx.db, ctx.exchange)


def _provider_portfolio(ctx: RuntimeContext) -> str:
    return compact_positions_context(ctx.db, ctx.exchange)


def _provider_wallet(ctx: RuntimeContext) -> str:
    return compact_wallet_context(ctx.db, ctx.exchange)


def _provider_periods(ctx: RuntimeContext) -> str:
    return compact_periods_context(ctx.db, ctx.exchange)


def _provider_macro(ctx: RuntimeContext) -> str:
    return compact_macro_context(ctx.db)


def _provider_daemon(ctx: RuntimeContext) -> str:
    return compact_daemon_context(ctx.db)


def _provider_decisions(ctx: RuntimeContext) -> str:
    symbols = ctx.focus_symbols or list(ctx.db.get_open_positions().keys())[:12]
    return compact_decisions_context(ctx.db, symbols)


def _provider_journal(ctx: RuntimeContext) -> str:
    return compact_journal_context(ctx.db)


def _provider_adaptive_edge(ctx: RuntimeContext) -> str:
    return compact_adaptive_edge_context(ctx.db)


def _provider_backtest(ctx: RuntimeContext) -> str:
    return compact_backtest_context(ctx.db)


def _provider_news(ctx: RuntimeContext) -> str:
    try:
        from news_service import relevant_news_lines
        return "\n".join(relevant_news_lines(ctx.focus_symbols, limit=6)) or "Sin noticias relevantes."
    except Exception as exc:
        return f"Noticias no disponibles: {exc}"


def _provider_audit(ctx: RuntimeContext) -> str:
    lines = []
    if hasattr(ctx.db, "get_audit_events"):
        events = ctx.db.get_audit_events(limit=5)
        lines.extend(f"- audit {e.get('event_type')} {e.get('symbol') or ''}: {e.get('message')}" for e in events)
    if hasattr(ctx.db, "get_cycle_replay_snapshots"):
        snaps = ctx.db.get_cycle_replay_snapshots(limit=3)
        lines.extend(f"- replay {s.get('cycle_id')} {s.get('phase')}" for s in snaps)
    return "\n".join(lines) if lines else "Sin audit/replay reciente."


def _provider_logs(ctx: RuntimeContext) -> str:
    return read_recent_log_summary(db=ctx.db, tail_lines=60, focus_lines=40)


def _provider_actions(ctx: RuntimeContext) -> str:
    return build_default_action_registry().describe()


def _provider_chat(ctx: RuntimeContext) -> str:
    return compact_chat_context(ctx.db)


def _provider_settings(ctx: RuntimeContext) -> str:
    return compact_settings_context(ctx.exchange)


def _provider_watchlist(ctx: RuntimeContext) -> str:
    saved = ctx.db.get_system_status("dynamic_watchlist", "") or ""
    watchlist = [s.strip() for s in saved.split(",") if s.strip()]
    blocked = "USD, EUR, GBP, USDT, USDC, DAI, TUSD, FDUSD, PYUSD, BUSD"
    if not watchlist:
        return f"Sin radar activo. Bases bloqueadas: {blocked}"
    return f"Watchlist: {', '.join(watchlist[:24])}\nBases bloqueadas radar: {blocked}"


def _provider_pending_orders(ctx: RuntimeContext) -> str:
    return compact_pending_orders_context(ctx.db)


def _provider_webhooks(ctx: RuntimeContext) -> str:
    if not hasattr(ctx.db, "list_external_signals"):
        return "Webhooks no disponibles."
    pending = ctx.db.list_external_signals(status="pending", limit=10)
    lines = [f"Pendientes TV: {len(pending)}"]
    for row in pending[:8]:
        lines.append(f"- {row.get('symbol')} {row.get('action')} id={row.get('id')}")
    return "\n".join(lines) if lines else "Sin señales webhook pendientes."


def _provider_presets(ctx: RuntimeContext) -> str:
    try:
        from config_presets import get_active_preset_id, get_preset, list_presets

        active = get_active_preset_id()
        names = ", ".join(p["id"] for p in list_presets()[:12])
        if not active:
            return f"Plantillas disponibles: {names}. Ninguna marcada como activa."
        preset = get_preset(active)
        return (
            f"Plantilla activa: {active} ({preset.get('name') if preset else '?'})\n"
            f"Disponibles: {names}"
        )
    except Exception as exc:
        return f"Plantillas: {exc}"


def build_default_context_registry() -> ContextProviderRegistry:
    return (
        ContextProviderRegistry()
        .register("PRIORIDAD / ESTADO CRÍTICO", _provider_priority, priority=10)
        .register("MEMORIA CHAT RECIENTE", _provider_chat, priority=15, max_chars=900)
        .register("MODO / CONFIG", _provider_settings, priority=18, max_chars=900)
        .register("CARTERA / POSICIONES BOT", _provider_portfolio, priority=20)
        .register("CARTERA EXCHANGE / DUST", _provider_wallet, priority=30)
        .register("RENDIMIENTO POR PERIODO", _provider_periods, priority=40)
        .register("MACRO", _provider_macro, priority=50)
        .register("DAEMON", _provider_daemon, priority=60)
        .register("RADAR / WATCHLIST", _provider_watchlist, priority=65, max_chars=700)
        .register("ÓRDENES PENDIENTES", _provider_pending_orders, priority=68, max_chars=800)
        .register("DECISIONES RECIENTES", _provider_decisions, priority=70)
        .register("DECISION JOURNAL / MÉTRICAS", _provider_journal, priority=80, max_chars=1400)
        .register("ADAPTIVE EDGE", _provider_adaptive_edge, priority=85, max_chars=900)
        .register("BACKTEST", _provider_backtest, priority=90)
        .register("NOTICIAS RELEVANTES", _provider_news, priority=100)
        .register("AUDIT / REPLAY", _provider_audit, priority=110)
        .register("ACCIONES CONFIRMABLES", _provider_actions, priority=120)
        .register("WEBHOOKS / SEÑALES", _provider_webhooks, priority=125, max_chars=600)
        .register("PLANTILLA ACTIVA", _provider_presets, priority=127, max_chars=500)
        .register("ÚLTIMOS LOGS", _provider_logs, priority=130, max_chars=1800)
    )


_SECTION_CHAR_BOOST = {
    "ÚLTIMOS LOGS": 4500,
    "NOTICIAS RELEVANTES": 2500,
    "DECISION JOURNAL / MÉTRICAS": 2200,
    "AUDIT / REPLAY": 1500,
    "WEBHOOKS / SEÑALES": 800,
}


def build_assistant_context(
    ctx: RuntimeContext,
    registry: ContextProviderRegistry | None = None,
    *,
    priority_sections: set[str] | None = None,
) -> str:
    registry = registry or build_default_context_registry()
    header = "=== CONTEXTO OPERATIVO COMPACTO INVERSORIA ==="
    if priority_sections:
        for provider in registry._providers.values():
            if provider.provider_id in priority_sections:
                boost = _SECTION_CHAR_BOOST.get(provider.provider_id)
                if boost:
                    provider.max_chars = max(provider.max_chars, boost)

    sections = registry.build_sections(ctx)
    if priority_sections:
        allowed = set(_ESSENTIAL_SECTIONS) | set(priority_sections)
        sections = [(t, c) for t, c in sections if t in allowed]

    blocks = [(title, f"{title}:\n{content}") for title, content in sections]

    def assembled(selected):
        return header + "\n\n" + "\n\n".join(block for _, block in selected)

    if not blocks:
        return header

    selected = list(blocks)
    while len(assembled(selected)) > ctx.max_chars and len(selected) > 1:
        removed = False
        for idx in range(len(selected) - 1, -1, -1):
            if selected[idx][0] not in _ESSENTIAL_SECTIONS:
                selected.pop(idx)
                removed = True
                break
        if not removed:
            title, block = selected[-1]
            if title in _ESSENTIAL_SECTIONS:
                break
            over = len(assembled(selected)) - ctx.max_chars
            body = block.split("\n", 1)
            if len(body) == 2 and len(body[1]) > over + 20:
                trimmed = body[1][: max(0, len(body[1]) - over - 20)].rstrip()
                selected[-1] = (title, f"{body[0]}\n{trimmed}\n...[recortado por límite]")
            break

    omitted = [title for title, _ in blocks if title not in {t for t, _ in selected}]
    text = assembled(selected)
    if omitted:
        text += "\n\nSECCIONES OMITIDAS POR LÍMITE: " + ", ".join(omitted)
    return text

