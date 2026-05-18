import requests
import json
import re
import time
import hashlib
from datetime import datetime, timedelta, timezone
from google import genai
from groq import Groq
import config # Importar módulo completo
from database_manager import DatabaseManager
from news_service import relevant_news_lines

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


GEMINI_MODELS = (
    ("Lite", "gemini-flash-lite-latest", "Gemini-3.1-Lite"),
    ("Flash", "gemini-flash-latest", "Gemini-3-Flash"),
)

GEMINI_DAILY_QUOTA_MARKERS = (
    "generaterequestsperday",
    "generate requests per day",
    "requestsperday",
    "per day",
    "daily",
    "free tier",
    "cuota diaria",
)


def _nth_weekday(year, month, weekday, n):
    day = datetime(year, month, 1)
    days_until_weekday = (weekday - day.weekday()) % 7
    return day + timedelta(days=days_until_weekday + (n - 1) * 7)


def _fallback_pacific_offset_hours(utc_dt):
    """US Pacific DST approximation when zoneinfo data is unavailable."""
    year = utc_dt.year
    dst_start = _nth_weekday(year, 3, 6, 2).replace(hour=10, tzinfo=timezone.utc)
    dst_end = _nth_weekday(year, 11, 6, 1).replace(hour=9, tzinfo=timezone.utc)
    return -7 if dst_start <= utc_dt < dst_end else -8


def calculate_next_gemini_daily_reset_pt(now=None, safety_minutes=15):
    """Return the next Gemini daily quota reset, midnight Pacific + safety margin, in UTC."""
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    if ZoneInfo:
        try:
            pacific = ZoneInfo("America/Los_Angeles")
            now_pt = now_utc.astimezone(pacific)
            reset_pt = now_pt.replace(hour=0, minute=safety_minutes, second=0, microsecond=0)
            if now_pt >= reset_pt:
                reset_pt += timedelta(days=1)
            return reset_pt.astimezone(timezone.utc)
        except Exception:
            pass

    offset = _fallback_pacific_offset_hours(now_utc)
    pacific_tz = timezone(timedelta(hours=offset))
    now_pt = now_utc.astimezone(pacific_tz)
    reset_pt = now_pt.replace(hour=0, minute=safety_minutes, second=0, microsecond=0)
    if now_pt >= reset_pt:
        reset_pt += timedelta(days=1)
    reset_offset = _fallback_pacific_offset_hours(reset_pt.astimezone(timezone.utc))
    return reset_pt.replace(tzinfo=timezone(timedelta(hours=reset_offset))).astimezone(timezone.utc)


def _extract_retry_delay_seconds(message):
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", message, re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"retry_delay.*?seconds['\"]?\s*[:=]\s*(\d+(?:\.\d+)?)", message, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _looks_like_gemini_daily_quota(message):
    lower = message.lower()
    if not any(marker in lower for marker in GEMINI_DAILY_QUOTA_MARKERS):
        return False
    return "quota" in lower or "resource_exhausted" in lower or "429" in lower


def _looks_like_gemini_quota_error(message):
    lower = message.lower()
    return "429" in lower or "resource_exhausted" in lower or "quota" in lower

class SentimentEngine:
    def __init__(self):
        self.db = DatabaseManager()
        # 1. Gemini
        self.gemini_client = None
        if config.GOOGLE_API_KEY:
            try:
                self.gemini_client = genai.Client(api_key=config.GOOGLE_API_KEY)
            except Exception as e: print(f"Error inicializando Gemini: {e}")

        # 2. Groq
        self.groq_client = None
        if config.GROQ_API_KEY:
            try:
                self.groq_client = Groq(api_key=config.GROQ_API_KEY)
            except Exception as e: print(f"Error inicializando Groq: {e}")

        self.coindesk_url = "https://min-api.cryptocompare.com/data/v2/news/"
        self.cache = {}
        self.fng_cache = {'value': 'Unknown', 'classification': 'Unknown', 'timestamp': 0}
        self.user_name = "User"
        self.language = "es"
        self.gemini_cooldown_until = 0
        self.gemini_cooldown_reason = ""
        self.gemini_cooldown_last_log = 0
        self.gemini_cooldown_log_interval = 300
        self._load_ai_cooldowns()

    def set_user_context(self, user_name, language):
        self.user_name = user_name
        self.language = language

    def get_fear_and_greed(self):
        if time.time() - self.fng_cache['timestamp'] < 86400:
            return self.fng_cache['value'], self.fng_cache['classification']
        try:
            res = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
            data = res.json()
            if data and "data" in data:
                item = data["data"][0]
                self.fng_cache = {'value': item['value'], 'classification': item['value_classification'], 'timestamp': time.time()}
        except: pass
        return self.fng_cache['value'], self.fng_cache['classification']

    def get_news(self, symbol, limit=15):
        cached = relevant_news_lines([symbol], limit=limit, db=self.db)
        if cached:
            return cached
        if not config.COINDESK_API_KEY: return []
        currency = symbol.split('/')[0]
        try:
            res = requests.get(self.coindesk_url, params={"api_key": config.COINDESK_API_KEY, "categories": currency, "sortOrder": "latest"})
            return [post['title'] for post in res.json().get('Data', [])[:limit]]
        except: return []

    def _safe_error_message(self, error):
        message = str(error)
        for secret in (config.GOOGLE_API_KEY, config.GROQ_API_KEY):
            if secret and len(secret) >= 6:
                message = message.replace(secret, "[REDACTED]")
        return message

    def _load_ai_cooldowns(self):
        try:
            state = self.db.get_provider_cooldown('Gemini', 'ai')
            self.gemini_cooldown_until = float(state.get('cooldown_until') or 0)
            self.gemini_cooldown_reason = state.get('reason') or ''
        except Exception:
            self.gemini_cooldown_until = 0
            self.gemini_cooldown_reason = ""

    def _set_ai_cooldown(self, provider, until, reason):
        try:
            self.db.set_provider_cooldown(
                provider,
                cooldown_until=until,
                reason=self._safe_error_message(reason),
                scope='ai',
            )
        except Exception:
            pass

    def _provider_in_cooldown(self, provider, now=None):
        try:
            state = self.db.get_provider_cooldown(provider, 'ai')
            return (now or time.time()) < float(state.get('cooldown_until') or 0)
        except Exception:
            return False

    def _estimate_tokens(self, text):
        # Estimación conservadora y barata: 1 token ~= 4 caracteres en español/inglés.
        return max(1, int(len(str(text or "")) / 4) + 1)

    def _prompt_hash(self, prompt, system_instruction):
        raw = f"{system_instruction or ''}\n{prompt or ''}"
        return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

    def _ai_budget_check(self, prompt, system_instruction, feature):
        input_tokens = self._estimate_tokens(f"{system_instruction or ''}\n{prompt or ''}")
        output_tokens = int(getattr(config, 'AI_MAX_OUTPUT_TOKENS', 700) or 700)
        prompt_hash = self._prompt_hash(prompt, system_instruction)
        now = time.time()
        cycle_window = max(15, int(getattr(config, 'DAEMON_CYCLE_SECONDS', 60) or 60))
        try:
            cycle = self.db.get_ai_usage_summary(since_ts=now - cycle_window)
            day = self.db.get_ai_usage_summary(since_ts=now - 86400)
        except Exception:
            return True, "", input_tokens, output_tokens, prompt_hash

        limits = [
            (
                int(getattr(config, 'AI_MAX_REQUESTS_PER_CYCLE', 0) or 0),
                cycle.get('requests', 0),
                'AI_MAX_REQUESTS_PER_CYCLE',
            ),
            (
                int(getattr(config, 'AI_MAX_REQUESTS_PER_DAY', 0) or 0),
                day.get('requests', 0),
                'AI_MAX_REQUESTS_PER_DAY',
            ),
            (
                int(getattr(config, 'AI_MAX_EST_TOKENS_PER_DAY', 0) or 0),
                day.get('estimated_tokens', 0) + input_tokens + output_tokens,
                'AI_MAX_EST_TOKENS_PER_DAY',
            ),
        ]
        for limit, used, label in limits:
            if limit > 0 and used >= limit:
                reason = f"{label} reached ({used}/{limit})"
                self.db.record_ai_usage(
                    provider='budget',
                    feature=feature,
                    prompt_hash=prompt_hash,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=output_tokens,
                    success=False,
                    blocked_reason=reason,
                )
                return False, reason, input_tokens, output_tokens, prompt_hash
        return True, "", input_tokens, output_tokens, prompt_hash

    def _format_cooldown_until(self):
        until = datetime.fromtimestamp(self.gemini_cooldown_until, timezone.utc).astimezone()
        return until.strftime("%Y-%m-%d %H:%M:%S %Z").strip()

    def _gemini_in_cooldown(self, now=None):
        return (now or time.time()) < self.gemini_cooldown_until

    def _log_gemini_cooldown(self, now=None, force=False):
        now = now or time.time()
        if not force and now - self.gemini_cooldown_last_log < self.gemini_cooldown_log_interval:
            return
        self.gemini_cooldown_last_log = now
        reason = self.gemini_cooldown_reason or "rate limit"
        print(f"[AI] Gemini en cooldown hasta {self._format_cooldown_until()} ({reason}); usando Groq fallback.")

    def _apply_gemini_cooldown_from_error(self, model_label, error):
        message = self._safe_error_message(error)
        now = time.time()
        if not _looks_like_gemini_quota_error(message):
            print(f"[HYBRID] Gemini {model_label} falló: {message}")
            return False

        retry_delay = _extract_retry_delay_seconds(message)
        if _looks_like_gemini_daily_quota(message):
            reset_at = calculate_next_gemini_daily_reset_pt()
            self.gemini_cooldown_until = max(self.gemini_cooldown_until, reset_at.timestamp())
            self.gemini_cooldown_reason = "cuota diaria agotada"
        else:
            cooldown_seconds = max(60, min((retry_delay or 300) + 15, 900))
            self.gemini_cooldown_until = max(self.gemini_cooldown_until, now + cooldown_seconds)
            self.gemini_cooldown_reason = "rate limit temporal"

        self._set_ai_cooldown('Gemini', self.gemini_cooldown_until, self.gemini_cooldown_reason)
        self._log_gemini_cooldown(now=now, force=True)
        return True

    def call_ai_hybrid(self, prompt, system_instruction="", feature="general"):
        allowed, block_reason, input_tokens, output_tokens, prompt_hash = self._ai_budget_check(
            prompt,
            system_instruction,
            feature,
        )
        if not allowed:
            print(f"[AI] Presupuesto IA agotado ({block_reason}); usando fallback sin llamada externa.")
            return None, None

        # 1. GEMINI
        if self.gemini_client:
            now = time.time()
            if self._gemini_in_cooldown(now):
                self._log_gemini_cooldown(now=now)
            else:
                for model_label, model_name, provider_name in GEMINI_MODELS:
                    try:
                        response = self.gemini_client.models.generate_content(
                            model=model_name,
                            contents=f"{system_instruction}\n\n{prompt}"
                        )
                        if response and response.text:
                            self.db.record_ai_usage(
                                provider=provider_name,
                                feature=feature,
                                prompt_hash=prompt_hash,
                                estimated_input_tokens=input_tokens,
                                estimated_output_tokens=self._estimate_tokens(response.text),
                                success=True,
                            )
                            return response.text.strip(), provider_name
                    except Exception as e:
                        if self._apply_gemini_cooldown_from_error(model_label, e):
                            break

        # 3. GROQ (8B)
        if self.groq_client and not self._provider_in_cooldown('Groq'):
            try:
                completion = self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": f"{system_instruction}\n{prompt}"}],
                    temperature=0.1,
                    max_tokens=int(getattr(config, 'AI_MAX_OUTPUT_TOKENS', 700) or 700),
                )
                text = completion.choices[0].message.content.strip()
                self.db.record_ai_usage(
                    provider="Groq-8B",
                    feature=feature,
                    prompt_hash=prompt_hash,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=self._estimate_tokens(text),
                    success=True,
                )
                return text, "Groq-8B"
            except Exception as e:
                safe = self._safe_error_message(e)
                self._set_ai_cooldown('Groq', time.time() + 300, safe)
                print(f"[HYBRID] Groq falló: {safe}")

        return None, None

    def analyze_sentiment(self, symbol, titles, market_stats=None):
        if symbol in self.cache and time.time() - self.cache[symbol]['timestamp'] < 1200:
            return self.cache[symbol]['sentiment'], self.cache[symbol]['text']
        if not titles: return "NEUTRAL", "Sin noticias."
        fng_val, fng_class = self.get_fear_and_greed()
        stats_str = f"24h Change: {market_stats.get('change_24h')}%" if market_stats else ""
        
        # Leemos el prompt en tiempo real
        lang_name = "Spanish" if self.language == 'es' else "English"
        system_instruction = f"User: {self.user_name}. Language: {lang_name}. " + config.PROMPT_SENTIMENT
        
        prompt = f"Activo: {symbol}\nF&G Index: {fng_val}\n{stats_str}\nNoticias:\n" + "\n".join(titles)
        res, provider = self.call_ai_hybrid(prompt, system_instruction, feature="sentiment")
        if res:
            sentiment = "NEUTRAL"
            if "BULLISH" in res.upper(): sentiment = "BULLISH"
            elif "BEARISH" in res.upper(): sentiment = "BEARISH"
            final_text = f"[{provider}] {res}"
            self.cache[symbol] = {'sentiment': sentiment, 'text': final_text, 'timestamp': time.time()}
            return sentiment, final_text
        return "NEUTRAL", "Todas las IAs fuera de línea."
