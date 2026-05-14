import json
import time
import re
from sentiment_engine import SentimentEngine
import pandas as pd
import config # Importar el módulo completo para hot-reload

class DecisionEngine:
    def __init__(self):
        self.sentiment = SentimentEngine()
        self.last_analysis = {}    # symbol -> timestamp
        self.decision_cache = {}   # symbol -> last_valid_json_decision
        
    def quick_technical_filter(self, indicators, current_price):
        if not indicators: return False, "Sin datos"
        rsi = indicators.get('rsi')
        trend = indicators.get('trend', 'UNKNOWN')
        adx = indicators.get('adx', 0)
        if rsi > 40 and rsi < 60 and adx < 20:
            return False, f"Mercado lateral (RSI: {rsi:.1f})"
        return True, "Filtro OK"

    def analyze_with_ai_hybrid(self, symbol, current_price, indicators, ohlcv):
        now = time.time()
        if symbol in self.last_analysis and now - self.last_analysis[symbol] < config.AI_ANALYSIS_INTERVAL:
            return self.decision_cache.get(symbol)
            
        df = pd.DataFrame(ohlcv[-100:], columns=['ts','open','high','low','close','volume'])
        df['close'] = pd.to_numeric(df['close'])
        news = self.sentiment.get_news(symbol, limit=8)
        fng_value, fng_class = self.sentiment.get_fear_and_greed()
        
        # Leemos el prompt en tiempo real
        system_instruction = config.PROMPT_DECISION
        
        prompt = f"""Analiza {symbol} (${current_price:.4f}). 
        RSI: {indicators.get('rsi'):.1f}, ADX: {indicators.get('adx'):.1f}, Trend: {indicators.get('trend')}.
        F&G Index: {fng_value}.
        Noticias: {news[:4]}
        
        Responde este JSON exacto:
        {{
          "regime": "TRENDING_UP | TRENDING_DOWN | RANGING | HIGH_VOLATILITY",
          "best_strategy": "TREND_FOLLOWING | MEAN_REVERSION | BREAKOUT | MOMENTUM",
          "action": "BUY | SELL | HOLD",
          "confidence": 0.XX,
          "position_size_multiplier": 0.XX,
          "stop_loss_atr": 1.X,
          "take_profit_ratio": 2.X,
          "reasoning": "Breve justificación"
        }}"""

        raw_content, provider = self.sentiment.call_ai_hybrid(prompt, system_instruction)
        if raw_content:
            try:
                match = re.search(r'\{.*\}', raw_content, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                    result['provider'] = provider
                    self.last_analysis[symbol] = now
                    self.decision_cache[symbol] = result
                    return result
            except: pass
        return self.decision_cache.get(symbol)

    def evaluate_rotation_potential(self, new_signal, open_positions_details):
        if not new_signal or new_signal.get('action') != 'BUY': return None
        new_conf = new_signal.get('confidence', 0)
        
        # Leemos los parámetros de rotación en tiempo real
        if new_conf < config.ROTATION_MIN_NEW_CONFIDENCE: return None
        
        weakest = None
        for sym, pos in open_positions_details.items():
            profit = pos.get('profit_pct', 0)
            entry_conf = pos.get('entry_confidence', 0.6)
            
            if profit >= config.ROTATION_MIN_PROFIT:
                if new_conf - entry_conf >= config.ROTATION_CONFIDENCE_GAP:
                    if not weakest or entry_conf < weakest['entry_confidence']:
                        weakest = {'symbol': sym, 'entry_confidence': entry_conf, 'profit': profit}
        
        return weakest

    def curate_watchlist(self, raw_symbols):
        system_instruction = config.PROMPT_CURATION
        prompt = f"Filtra esta lista: {', '.join(raw_symbols)}"
        raw_content, provider = self.sentiment.call_ai_hybrid(prompt, system_instruction)
        if raw_content:
            found = re.findall(r'(\w+/USDT)', raw_content)
            if found: return list(set(found))
        return raw_symbols[:15]

    def get_decision(self, symbol, current_price, indicators, ohlcv, open_positions_count, is_already_open=False):
        if not is_already_open:
            passes, reason = self.quick_technical_filter(indicators, current_price)
            if not passes:
                return {"action": "HOLD", "reasoning": reason, "confidence": 0.0}
        
        decision = self.analyze_with_ai_hybrid(symbol, current_price, indicators, ohlcv)
        if not decision: return {"action": "HOLD", "reasoning": "IA fuera de línea", "confidence": 0.0}
        if decision.get("confidence", 0) < 0.60: decision["action"] = "HOLD"
        return decision
