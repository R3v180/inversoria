import requests
import json
import time
from google import genai
from groq import Groq
import config # Importar módulo completo

class SentimentEngine:
    def __init__(self):
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
        if not config.COINDESK_API_KEY: return []
        currency = symbol.split('/')[0]
        try:
            res = requests.get(self.coindesk_url, params={"api_key": config.COINDESK_API_KEY, "categories": currency, "sortOrder": "latest"})
            return [post['title'] for post in res.json().get('Data', [])[:limit]]
        except: return []

    def call_ai_hybrid(self, prompt, system_instruction=""):
        # 1. GEMINI 3.1 FLASH LITE
        if self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model='gemini-flash-lite-latest',
                    contents=f"{system_instruction}\n\n{prompt}"
                )
                if response and response.text:
                    return response.text.strip(), "Gemini-3.1-Lite"
            except Exception as e:
                print(f"[HYBRID] Gemini Lite falló: {e}")
                
            try:
                response = self.gemini_client.models.generate_content(
                    model='gemini-flash-latest',
                    contents=f"{system_instruction}\n\n{prompt}"
                )
                if response and response.text:
                    return response.text.strip(), "Gemini-3-Flash"
            except Exception as e:
                print(f"[HYBRID] Gemini Flash falló: {e}")

        # 3. GROQ (8B)
        if self.groq_client:
            try:
                completion = self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": f"{system_instruction}\n{prompt}"}],
                    temperature=0.1
                )
                return completion.choices[0].message.content.strip(), "Groq-8B"
            except Exception as e:
                print(f"[HYBRID] Groq falló: {e}")

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
        res, provider = self.call_ai_hybrid(prompt, system_instruction)
        if res:
            sentiment = "NEUTRAL"
            if "BULLISH" in res.upper(): sentiment = "BULLISH"
            elif "BEARISH" in res.upper(): sentiment = "BEARISH"
            final_text = f"[{provider}] {res}"
            self.cache[symbol] = {'sentiment': sentiment, 'text': final_text, 'timestamp': time.time()}
            return sentiment, final_text
        return "NEUTRAL", "Todas las IAs fuera de línea."
