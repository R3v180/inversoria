import hashlib
import json

import streamlit as st

import config
from i18n import _
from news_service import get_cached_crypto_news


@st.cache_data(ttl=900, show_spinner=False)
def _cached_news():
    return get_cached_crypto_news()


def _label_sentiment(value: str) -> str:
    return {
        "positive": _("NEWS_SENT_POS"),
        "negative": _("NEWS_SENT_NEG"),
        "neutral": _("NEWS_SENT_NEU"),
    }.get(value, value or "-")


def _label_impact(value: str) -> str:
    return {
        "high": _("NEWS_IMPACT_HIGH"),
        "medium": _("NEWS_IMPACT_MED"),
        "low": _("NEWS_IMPACT_LOW"),
    }.get(value, value or "-")


def _badge_colors(sentiment: str):
    return {
        "positive": ("var(--iv-accent)", "var(--iv-accent-soft)"),
        "negative": ("var(--iv-danger)", "rgba(255,68,68,0.12)"),
        "neutral": ("var(--iv-warning)", "rgba(255,209,102,0.12)"),
    }.get(sentiment, ("var(--iv-muted)", "rgba(156,163,175,0.12)"))


def _news_styles():
    st.markdown(
        """
        <style>
        .news-card {
            display: flex; gap: 14px; padding: 14px; margin-bottom: 14px;
            border: 1px solid var(--iv-border); border-radius: 12px; background: var(--iv-card-bg);
            color: var(--iv-text);
        }
        .news-card img {
            width: 150px; height: 96px; object-fit: cover; border-radius: 10px;
            border: 1px solid var(--iv-border); background: var(--iv-bg);
        }
        .news-thumb-empty {
            width: 150px; height: 96px; border-radius: 10px; border: 1px solid var(--iv-border);
            background: linear-gradient(135deg, var(--iv-accent-soft), rgba(58,134,255,.12));
            display: flex; align-items: center; justify-content: center; color: var(--iv-accent);
            font-weight: 700; font-size: 1.8em; flex-shrink: 0;
        }
        .news-body { flex: 1; min-width: 0; }
        .news-title { font-size: 1.05em; font-weight: 700; line-height: 1.25; margin-bottom: 7px; }
        .news-title a { color: var(--iv-text); }
        .news-meta { color: var(--iv-muted); font-size: .82em; margin-bottom: 8px; }
        .news-summary { color: var(--iv-text); font-size: .9em; line-height: 1.35; }
        .news-pill {
            display: inline-block; padding: 3px 8px; border-radius: 999px;
            font-size: .75em; font-weight: 700; margin-right: 5px; border: 1px solid currentColor;
        }
        .news-mini-card {
            display:flex; gap:10px; padding:10px; margin-bottom:9px; border-radius:10px;
            border:1px solid var(--iv-border); background:var(--iv-card-bg); color:var(--iv-text);
        }
        .news-mini-card img { width:72px; height:52px; object-fit:cover; border-radius:7px; flex-shrink:0; }
        .news-mini-empty {
            width:72px; height:52px; border-radius:7px; flex-shrink:0;
            background:linear-gradient(135deg, var(--iv-accent-soft), rgba(58,134,255,.12));
            color:var(--iv-accent); display:flex; align-items:center; justify-content:center; font-weight:800;
        }
        .news-mini-title { font-size:.88em; font-weight:700; line-height:1.25; margin-bottom:4px; }
        .news-mini-title a { color: var(--iv-text); }
        .news-mini-meta { color:var(--iv-muted); font-size:.72em; line-height:1.25; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_image_or_placeholder(item: dict, compact: bool = False):
    image_url = item.get("image_url")
    if image_url:
        cls = "news-mini-card" if compact else "news-card"
        # La clase se aplica al contenedor; el img toma estilos por selector descendente.
        return f'<img src="{image_url}" alt="news image" loading="lazy" />'
    cls = "news-mini-empty" if compact else "news-thumb-empty"
    source = (item.get("source") or "N")[:1].upper()
    return f'<div class="{cls}">{source}</div>'


def _news_key(item: dict) -> str:
    raw = f"{item.get('source')}|{item.get('title')}|{item.get('link')}"
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()[:10]


def _buy_amount_default(balance: float) -> float:
    if balance <= 0:
        return 0.0
    risk_amount = balance * float(config.get_setting("RISK_PER_TRADE", config.RISK_PER_TRADE, float))
    return min(balance, max(1.0, risk_amount))


def _save_manual_buy(db, symbol: str, price: float, amount: float, reason: str):
    positions = db.get_open_positions()
    existing = positions.get(symbol)
    if existing:
        old_amount = float(existing.get("amount") or 0)
        old_entry = float(existing.get("entry_price") or price)
        total_amount = old_amount + amount
        if total_amount > 0:
            entry = ((old_entry * old_amount) + (price * amount)) / total_amount
        else:
            entry = price
        highest = max(float(existing.get("highest_price") or price), price)
        entry_time = existing.get("entry_time")
        amount_to_store = total_amount
    else:
        entry = price
        highest = price
        entry_time = None
        amount_to_store = amount

    extra = json.dumps({"provider": "Noticias", "reason": reason}, ensure_ascii=False)
    db.add_open_position(symbol, entry, highest, amount_to_store, entry_time=entry_time, extra_data=extra)
    db.save_trade(symbol, "buy", price, amount, reason, 0.0)
    db.add_log(f"{reason}: {symbol} qty={amount} @ {price}")


def _render_manual_buy(exchange, db, item: dict):
    related = item.get("related_symbols") or []
    options = related + [s for s in config.SYMBOLS if s not in related]
    if not options:
        st.info(_("NEWS_NO_SYMBOLS"))
        return

    key = _news_key(item)
    balance = float(exchange.get_usdt_balance() or 0)
    symbol = st.selectbox(_("NEWS_BUY_SYMBOL"), options, key=f"news_buy_sym_{key}")
    amount_usdt = st.number_input(
        _("NEWS_BUY_USDT"),
        min_value=0.0,
        max_value=max(balance, 0.0),
        value=float(min(_buy_amount_default(balance), balance)),
        step=0.5,
        key=f"news_buy_usdt_{key}",
    )
    st.caption(_("NEWS_BUY_BALANCE").format(f"{balance:.2f}"))

    disabled = amount_usdt <= 0 or amount_usdt > balance or not symbol
    if st.button(_("NEWS_BUY_BUTTON"), key=f"news_buy_btn_{key}", type="primary", disabled=disabled):
        price = exchange.get_ticker(symbol)
        if not price or price <= 0:
            st.error(_("NEWS_BUY_NO_PRICE"))
            return
        amount_coin = float(amount_usdt) / float(price)
        res = exchange.execute_order(symbol, "buy", amount_coin, float(price))
        if res.get("status") in ("closed", "open", "simulated"):
            try:
                filled = float(res.get("filled") or res.get("amount") or amount_coin)
            except (TypeError, ValueError):
                filled = amount_coin
            reason = f"{_('NEWS_BUY_REASON')}: {item.get('title', '')[:120]}"
            _save_manual_buy(db, symbol, float(price), filled, reason)
            st.success(_("NEWS_BUY_OK").format(symbol, f"{price:.6g}"))
            st.rerun()
        else:
            st.error(f"{_('NEWS_BUY_FAIL')}: {res.get('reason', res)}")


def render_news():
    _news_styles()
    st.title(_("NEWS_TITLE"))
    st.caption(_("NEWS_INTRO"))

    col_a, col_b = st.columns([3, 1])
    with col_b:
        if st.button(_("NEWS_REFRESH"), width="stretch"):
            _cached_news.clear()
            st.rerun()

    with st.spinner(_("NEWS_LOADING")):
        items, errors = _cached_news()

    if errors:
        with st.expander(_("NEWS_SOURCE_ERRORS"), expanded=False):
            for err in errors:
                st.caption(err)

    if not items:
        st.info(_("NEWS_EMPTY"))
        return

    all_sources = sorted({x["source"] for x in items})
    all_symbols = sorted({s for x in items for s in x.get("related_symbols", [])})

    f1, f2, f3, f4 = st.columns(4)
    source = f1.selectbox(_("NEWS_FILTER_SOURCE"), [_("NEWS_ALL")] + all_sources)
    symbol = f2.selectbox(_("NEWS_FILTER_SYMBOL"), [_("NEWS_ALL")] + all_symbols)
    sentiment = f3.selectbox(
        _("NEWS_FILTER_SENTIMENT"),
        [_("NEWS_ALL"), _("NEWS_SENT_POS"), _("NEWS_SENT_NEU"), _("NEWS_SENT_NEG")],
    )
    only_watchlist = f4.checkbox(_("NEWS_ONLY_WATCHLIST"), value=False)

    filtered = items
    if source != _("NEWS_ALL"):
        filtered = [x for x in filtered if x["source"] == source]
    if symbol != _("NEWS_ALL"):
        filtered = [x for x in filtered if symbol in x.get("related_symbols", [])]
    if sentiment != _("NEWS_ALL"):
        reverse_sent = {
            _("NEWS_SENT_POS"): "positive",
            _("NEWS_SENT_NEU"): "neutral",
            _("NEWS_SENT_NEG"): "negative",
        }
        filtered = [x for x in filtered if x.get("sentiment") == reverse_sent.get(sentiment)]
    if only_watchlist:
        filtered = [x for x in filtered if x.get("related_symbols")]

    st.caption(_("NEWS_COUNT").format(len(filtered), len(items)))

    for item in filtered[:50]:
        symbols = item.get("related_symbols") or []
        symbols_txt = ", ".join(symbols) if symbols else _("NEWS_GLOBAL")
        when = item["published_at"].strftime("%Y-%m-%d %H:%M")
        title = item.get("title", "")
        sentiment = item.get("sentiment")
        color, bg = _badge_colors(sentiment)
        image_html = _render_image_or_placeholder(item)
        link = item.get("link")
        title_html = f'<a href="{link}" target="_blank">{title}</a>' if link else title
        summary = item.get("summary") or ""

        with st.container(border=True):
            st.markdown(
                f"""
                <div class="news-card">
                    {image_html}
                    <div class="news-body">
                        <div class="news-title">{title_html}</div>
                        <div class="news-meta">{item['source']} · {when} · {symbols_txt}</div>
                        <span class="news-pill" style="color:{color}; background:{bg};">
                            {_label_sentiment(sentiment)}
                        </span>
                        <span class="news-pill" style="color:var(--iv-info); background:rgba(147,197,253,.10);">
                            {_label_impact(item.get('impact'))}
                        </span>
                        <div class="news-summary">{summary}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            prompt_text = (
                f"Analiza esta noticia y dime si justifica una compra manual.\n"
                f"Titulo: {title}\n"
                f"Fuente: {item.get('source')}\n"
                f"Activos relacionados: {symbols_txt}\n"
                f"Resumen: {item.get('summary')}"
            )
            with st.expander(_("NEWS_ASSISTANT_CONTEXT"), expanded=False):
                st.code(prompt_text, language=None)

            with st.expander(_("NEWS_MANUAL_BUY"), expanded=False):
                st.warning(_("NEWS_BUY_WARNING"))
                _render_manual_buy(st.session_state.exchange, st.session_state.db, item)


def render_news_widget(symbols=None, limit: int = 5):
    """Widget compacto para incrustar titulares en el dashboard."""
    _news_styles()
    symbols = set(symbols or [])
    try:
        items, errors = _cached_news()
    except Exception as exc:
        st.info(f"{_('NEWS_EMPTY')} ({exc})")
        return

    if not items:
        st.info(_("NEWS_EMPTY"))
        return

    def score(item):
        related = set(item.get("related_symbols") or [])
        impact_weight = {"high": 3, "medium": 2, "low": 1}.get(item.get("impact"), 0)
        sentiment_weight = {"positive": 1, "neutral": 0, "negative": -1}.get(item.get("sentiment"), 0)
        relation_weight = 4 if related & symbols else 0
        return relation_weight + impact_weight + sentiment_weight

    ranked = sorted(items, key=score, reverse=True)[:limit]

    st.markdown(f"#### {_('NEWS_WIDGET_TITLE')}")
    if errors:
        st.caption(_("NEWS_WIDGET_SOURCE_WARN"))

    for item in ranked:
        related = item.get("related_symbols") or []
        symbols_txt = ", ".join(related[:3]) if related else _("NEWS_GLOBAL")
        title = item.get("title", "")
        link = item.get("link")
        sentiment = item.get("sentiment")
        color, bg = _badge_colors(sentiment)
        image_html = _render_image_or_placeholder(item, compact=True)
        title_html = f'<a href="{link}" target="_blank">{title}</a>' if link else title
        meta = (
            f"{item.get('source')} · {symbols_txt} · "
            f"{_label_sentiment(sentiment)} · {_label_impact(item.get('impact'))}"
        )
        st.markdown(
            f"""
            <div class="news-mini-card">
                {image_html}
                <div>
                    <div class="news-mini-title">{title_html}</div>
                    <div class="news-mini-meta">{meta}</div>
                    <span class="news-pill" style="color:{color}; background:{bg}; margin-top:4px;">
                        {_label_sentiment(sentiment)}
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _open_news_tab():
        st.session_state.main_nav_route = "news"

    st.button(
        _("NEWS_WIDGET_OPEN_FULL"),
        key="dashboard_news_open_full",
        width="stretch",
        on_click=_open_news_tab,
    )
