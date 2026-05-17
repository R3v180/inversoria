import requests
import os
import time
import re
from datetime import datetime
from database_manager import DatabaseManager
from dotenv import load_dotenv
from i18n import _

load_dotenv()

class MacroAnalyzer:
    """
    Motor de análisis macroeconómico v6.0.
    Utiliza Alpha Vantage para obtener indicadores globales:
    - DXY (Dólar Index proxy via UUP)
    - SPY (S&P 500)
    - WTI (Petróleo)
    - GLD (Oro)
    """
    ASSETS = {
        "SPY": "S&P 500",
        "UUP": "DXY (Dólar)",
        "GLD": "Oro",
        "USO": "Petróleo",
        "VXX": "Volatilidad (VIX)",
    }
    STALE_AFTER_SECONDS = 6 * 60 * 60
    MIN_ATTEMPT_INTERVAL_SECONDS = 60 * 60
    RATE_LIMIT_COOLDOWN_SECONDS = 24 * 60 * 60
    PROVIDER = "alpha_vantage"
    PROVIDER_SCOPE = "global"

    def __init__(self, lang='es'):
        from dotenv import load_dotenv
        load_dotenv()
        self.api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.base_url = "https://www.alphavantage.co/query"
        self.db = DatabaseManager()
        self.u_lang = lang

    def _format_ts(self, ts):
        if not ts:
            return "N/A"
        return datetime.fromtimestamp(float(ts)).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def _sanitize_text(self, text):
        clean = str(text or "")
        if self.api_key:
            clean = clean.replace(str(self.api_key), "[REDACTED]")
        patterns = [
            (r"(API key as\s+)[A-Za-z0-9_\-]+", r"\1[REDACTED]"),
            (r"([?&]apikey=)[^&\s]+", r"\1[REDACTED]"),
            (r"\b(api[_\s-]?key|apikey|token|secret|password)\b\s*(?:as|=|:)?\s*[\"']?[^\"'\s,;]+", r"\1=[REDACTED]"),
        ]
        for pattern, replacement in patterns:
            clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)
        clean = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', "[REDACTED_EMAIL]", clean)
        return clean

    def _is_alpha_rate_limit(self, data):
        if not isinstance(data, dict):
            return False
        if "Note" in data or "Information" in data:
            return True
        joined = " ".join(str(value) for value in data.values()).lower()
        return any(
            token in joined
            for token in (
                "rate limit",
                "api call frequency",
                "25 requests",
                "standard api call frequency",
            )
        )

    def _macro_cache_status(self, macro_data):
        if not macro_data:
            return "sin cache macro disponible"
        oldest = min(float((row or {}).get('last_update') or 0) for row in macro_data.values())
        if time.time() - oldest >= self.STALE_AFTER_SECONDS:
            return "cache macro stale"
        return "cache macro vigente"

    def _set_provider_cooldown(self, *, last_attempt=None, last_error='', cooldown_seconds=None):
        attempt_ts = time.time() if last_attempt is None else float(last_attempt)
        seconds = self.MIN_ATTEMPT_INTERVAL_SECONDS if cooldown_seconds is None else float(cooldown_seconds)
        cooldown_until = attempt_ts + seconds
        self.db.set_provider_cooldown(
            self.PROVIDER,
            cooldown_until=cooldown_until,
            reason=self._sanitize_text(last_error),
            scope=self.PROVIDER_SCOPE,
            last_attempt=attempt_ts,
        )
        return cooldown_until

    def get_provider_refresh_state(self):
        """Estado persistente usado por el daemon para no disparar refresh al arrancar."""
        return self.db.get_provider_cooldown(self.PROVIDER, self.PROVIDER_SCOPE)

    def _should_skip_provider_attempt(self, now, macro_data):
        cooldown = self.get_provider_refresh_state()
        cooldown_until = float((cooldown or {}).get('cooldown_until') or 0)
        last_attempt = float((cooldown or {}).get('last_attempt') or 0)
        cache_status = self._macro_cache_status(macro_data)

        if cooldown_until > now:
            print(
                f"[Macro] Alpha Vantage cooldown hasta {self._format_ts(cooldown_until)}; "
                f"usando cache existente ({cache_status})."
            )
            return True

        if last_attempt and now - last_attempt < self.MIN_ATTEMPT_INTERVAL_SECONDS:
            next_attempt = last_attempt + self.MIN_ATTEMPT_INTERVAL_SECONDS
            print(
                f"[Macro] Skipping macro refresh: last attempt {self._format_ts(last_attempt)}; "
                f"próximo intento >= {self._format_ts(next_attempt)}; "
                f"usando cache existente ({cache_status})."
            )
            return True

        return False

    def fetch_global_market_status(self, max_assets=1):
        """Actualiza indicadores macro respetando cooldown persistente de Alpha Vantage."""
        if not self.api_key:
            print("[Macro] Error: ALPHA_VANTAGE_API_KEY no configurada.")
            return

        now = time.time()
        macro_data = self.db.get_all_macro_data()
        candidates = []
        for symbol, name in self.ASSETS.items():
            last_update = float((macro_data.get(symbol) or {}).get('last_update') or 0)
            age = now - last_update
            if age >= self.STALE_AFTER_SECONDS:
                candidates.append((last_update, symbol, name))

        if not candidates:
            print("  [OK] Macro cache vigente; no hay activos vencidos.")
            return

        if self._should_skip_provider_attempt(now, macro_data):
            return

        msg = "Actualizando indicadores globales..." if self.u_lang == 'es' else "Updating global indicators..."
        print(f"[Macro] {msg}")

        candidates.sort(key=lambda x: x[0])
        if max_assets is not None:
            candidates = candidates[:max(1, int(max_assets))]
        print(f"  [*] Processing {len(candidates)} stale asset(s)...")

        for _, symbol, name in candidates:
            attempt_ts = time.time()
            self._set_provider_cooldown(last_attempt=attempt_ts)
            try:
                params = {
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol,
                    "apikey": self.api_key
                }
                response = requests.get(self.base_url, params=params)
                data = response.json()

                if self._is_alpha_rate_limit(data):
                    reason = self._sanitize_text(data.get('Note', data.get('Information', data)))
                    cooldown_until = self._set_provider_cooldown(
                        last_attempt=attempt_ts,
                        last_error=reason,
                        cooldown_seconds=self.RATE_LIMIT_COOLDOWN_SECONDS,
                    )
                    print(f"  [Macro] Alpha Vantage cooldown set hasta {self._format_ts(cooldown_until)}")
                    print(f"  [!] Alpha Vantage API Limit: {reason}")
                    break

                quote = data.get('Global Quote', {})
                if quote:
                    price = float(quote.get('05. price', 0))
                    change_pct = quote.get('10. change percent', '0%').replace('%', '')
                    change_pct = float(change_pct)

                    self.db.set_macro_data(symbol, price, change_pct)
                    self._set_provider_cooldown(last_attempt=attempt_ts)
                    status_ok = "OK" if self.u_lang == "en" else "LISTO"
                    print(f"  [{status_ok}] {symbol} ({name}): ${price} ({change_pct:+.2f}%)")
                else:
                    reason = self._sanitize_text(data)
                    self._set_provider_cooldown(last_attempt=attempt_ts, last_error=reason)
                    print(f"  [?] {symbol}: No data in response (Check API Key or Symbol)")

            except Exception as e:
                err_msg = "Error fetching" if self.u_lang == "en" else "Error consultando"
                safe_error = self._sanitize_text(e)
                self._set_provider_cooldown(last_attempt=attempt_ts, last_error=safe_error)
                print(f"  [!] {err_msg} {symbol}: {safe_error}")

    def get_macro_summary(self):
        """Genera un resumen textual para la IA"""
        data = self.db.get_all_macro_data()
        if not data:
            return "No recent macroeconomic data available." if self.u_lang == 'en' else "Sin datos macroeconómicos recientes."

        lines = []
        for sym, d in data.items():
            if self.u_lang == 'en':
                status = "UP" if d['change_24h'] > 0 else "DOWN"
                lines.append(f"- {sym}: ${d['price']} ({d['change_24h']:+.2f}%) -> {status}")
            else:
                status = "ALZA" if d['change_24h'] > 0 else "BAJA"
                lines.append(f"- {sym}: ${d['price']} ({d['change_24h']:+.2f}%) -> {status}")

        header = "Global Macro Summary:\n" if self.u_lang == 'en' else "Resumen Macro Global:\n"
        return header + "\n".join(lines)

if __name__ == "__main__":
    analyzer = MacroAnalyzer()
    analyzer.fetch_global_market_status()
    print("\n" + analyzer.get_macro_summary())
