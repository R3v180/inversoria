import datetime as dt
import email.utils
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

from config import SYMBOLS
from database_manager import DatabaseManager


NEWS_SOURCES = [
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("NewsBTC", "https://www.newsbtc.com/feed/"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
]

POSITIVE_WORDS = {
    "adoption", "approve", "approved", "approval", "bull", "bullish", "breakout",
    "partnership", "launch", "upgrade", "surge", "rally", "record", "listing",
    "integrates", "growth", "inflow", "wins", "expand", "raises",
}
NEGATIVE_WORDS = {
    "hack", "exploit", "lawsuit", "ban", "bear", "bearish", "crash", "dump",
    "outflow", "probe", "charges", "fraud", "scam", "delay", "reject",
    "liquidation", "slump", "warning", "risk",
}
HIGH_IMPACT_WORDS = {
    "etf", "sec", "fed", "rate", "lawsuit", "hack", "exploit", "listing",
    "mainnet", "upgrade", "partnership", "acquisition", "regulation",
}


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed and parsed.tzinfo:
            parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _text_from_child(item, names):
    for name in names:
        child = item.find(name)
        if child is not None and child.text:
            return child.text
    return ""


def _link_from_item(item):
    direct = _text_from_child(item, ["link"])
    if direct:
        return direct.strip()
    for child in item:
        if child.tag.endswith("link"):
            href = child.attrib.get("href")
            if href:
                return href
    return ""


def _image_from_item(item, summary: str = ""):
    for child in item.iter():
        tag = child.tag.lower()
        attrs = child.attrib or {}
        if tag.endswith("thumbnail") or tag.endswith("content") or tag.endswith("enclosure"):
            url = attrs.get("url") or attrs.get("href")
            medium = (attrs.get("medium") or "").lower()
            typ = (attrs.get("type") or "").lower()
            if url and (medium == "image" or typ.startswith("image/") or re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", url, re.I)):
                return url
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary or "", re.I)
    if match:
        return html.unescape(match.group(1))
    return ""


def _watched_bases():
    bases = []
    for sym in SYMBOLS:
        base = sym.split("/", 1)[0].upper().strip()
        if base and base not in bases:
            bases.append(base)
    return bases


def _infer_symbols(text: str):
    upper = f" {text.upper()} "
    found = []
    for base in _watched_bases():
        if base in {"USD", "USDT"}:
            continue
        if re.search(rf"(?<![A-Z0-9]){re.escape(base)}(?![A-Z0-9])", upper):
            found.append(f"{base}/USDT")
    if "BITCOIN" in upper and "BTC/USDT" not in found:
        found.append("BTC/USDT")
    if "ETHEREUM" in upper and "ETH/USDT" not in found:
        found.append("ETH/USDT")
    return found


def _classify(text: str):
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    if pos > neg:
        sentiment = "positive"
    elif neg > pos:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    impact_hits = len(words & HIGH_IMPACT_WORDS)
    if impact_hits >= 2:
        impact = "high"
    elif impact_hits == 1 or pos + neg >= 2:
        impact = "medium"
    else:
        impact = "low"
    return sentiment, impact


def _parse_feed(source_name: str, xml_text: str):
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    out = []
    for item in items:
        title = _strip_html(_text_from_child(item, ["title", "{http://www.w3.org/2005/Atom}title"]))
        raw_summary = _text_from_child(item, [
            "description",
            "summary",
            "{http://www.w3.org/2005/Atom}summary",
            "{http://purl.org/rss/1.0/modules/content/}encoded",
        ])
        summary = _strip_html(raw_summary)
        link = _link_from_item(item)
        image_url = _image_from_item(item, raw_summary)
        published_raw = _text_from_child(item, [
            "pubDate",
            "published",
            "updated",
            "{http://www.w3.org/2005/Atom}published",
            "{http://www.w3.org/2005/Atom}updated",
        ])
        published_at = _parse_date(published_raw) or dt.datetime.utcnow()
        full_text = f"{title} {summary}"
        sentiment, impact = _classify(full_text)
        related = _infer_symbols(full_text)
        if title:
            out.append({
                "source": source_name,
                "title": title,
                "summary": summary[:420],
                "link": link,
                "image_url": image_url,
                "published_at": published_at,
                "related_symbols": related,
                "sentiment": sentiment,
                "impact": impact,
            })
    return out


def fetch_crypto_news(limit_per_source: int = 12):
    headers = {"User-Agent": "InversorIA/1.0 (+local dashboard)"}
    all_news = []
    errors = []
    for source_name, url in NEWS_SOURCES:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            all_news.extend(_parse_feed(source_name, raw)[:limit_per_source])
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")

    seen = set()
    unique = []
    for item in sorted(all_news, key=lambda x: x["published_at"], reverse=True):
        key = (item["source"], item["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique, errors


def _serialize_item(item: dict) -> dict:
    out = dict(item or {})
    published = out.get("published_at")
    if isinstance(published, dt.datetime):
        out["published_at"] = published.isoformat()
    return out


def _deserialize_item(item: dict) -> dict:
    out = dict(item or {})
    published = out.get("published_at")
    if isinstance(published, str):
        try:
            out["published_at"] = dt.datetime.fromisoformat(published)
        except Exception:
            out["published_at"] = dt.datetime.utcnow()
    return out


def get_cached_crypto_news(ttl_seconds: int = 900, db=None):
    """
    Cache compartida en SQLite para que daemon, dashboard y asistente usen la
    misma foto de noticias sin refetch tras cada reinicio/proceso.
    """
    db = db or DatabaseManager()
    now = dt.datetime.utcnow().timestamp()
    raw = db.get_system_status("shared_news_cache")
    if raw:
        try:
            cached = json.loads(raw)
            ts = float(cached.get("timestamp") or 0)
            if now - ts < ttl_seconds:
                items = [_deserialize_item(item) for item in cached.get("items", [])]
                return items, cached.get("errors", [])
        except Exception:
            pass

    items, errors = fetch_crypto_news()
    payload = {
        "timestamp": now,
        "items": [_serialize_item(item) for item in items],
        "errors": errors,
    }
    try:
        db.set_system_status("shared_news_cache", json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass
    return items, errors


def relevant_news_lines(symbols, limit: int = 5, ttl_seconds: int = 900, db=None):
    items, errors = get_cached_crypto_news(ttl_seconds=ttl_seconds, db=db)
    symbol_set = {str(s).upper() for s in (symbols or [])}

    def score(item):
        related = {str(s).upper() for s in (item.get("related_symbols") or [])}
        impact_weight = {"high": 3, "medium": 2, "low": 1}.get(item.get("impact"), 0)
        sentiment_weight = {"positive": 1, "neutral": 0, "negative": -1}.get(item.get("sentiment"), 0)
        relation_weight = 4 if related & symbol_set else 0
        return relation_weight + impact_weight + sentiment_weight

    ranked = sorted(items, key=score, reverse=True)[:limit]
    lines = []
    for item in ranked:
        related = ",".join(item.get("related_symbols") or []) or "global"
        lines.append(
            f"{item.get('source')}: {item.get('title')} "
            f"[{related}; {item.get('sentiment')}; {item.get('impact')}]"
        )
    if errors and not lines:
        lines.append("News cache errors: " + "; ".join(errors[:2]))
    return lines
