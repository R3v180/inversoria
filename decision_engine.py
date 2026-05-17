import json
import time
import re
from sentiment_engine import SentimentEngine
import pandas as pd
import config # Importar el módulo completo para hot-reload
from market_context import MarketContext
from multi_timeframe import MultiTimeframeAnalyzer
from backtest_engine import BacktestEngine
from i18n import _


def _safe_float(value, default=0.0):
    try:
        f = float(value)
        if f != f:
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


class DecisionEngine:
    def __init__(self, sentiment=None, exchange=None, lang='es'):
        self.sentiment = sentiment if sentiment else SentimentEngine()
        self.current_lang = lang
        self.last_analysis = {}
        self.decision_cache = {}

        # Nuevas capas de inteligencia
        self.market_context = MarketContext(lang=self.current_lang)
        self.mtf_analyzer = MultiTimeframeAnalyzer(exchange) if exchange else None
        self.backtest_engine = BacktestEngine(exchange, lang=self.current_lang) if exchange else None

        # Cache del contexto macro (se actualiza cada 6h)
        self._macro_cache = None
        self._macro_cache_ts = 0
        self.MACRO_CACHE_TTL = 21600  # 6 horas

    def build_decision_score(self, indicators, macro_regime, confluence_score, prior):
        """Score determinista y auditable. La IA puede opinar, pero esta capa deja rastro cuantitativo."""
        rsi = _safe_float(indicators.get('rsi'), 50.0)
        adx = _safe_float(indicators.get('adx'), 0.0)
        trend = indicators.get('trend', 'BEAR')

        trend_score = 1.0 if trend == 'BULL' else 0.25
        if 45 <= rsi <= 62:
            rsi_score = 0.85
        elif 35 <= rsi < 45:
            rsi_score = 0.65
        elif 62 < rsi <= 70:
            rsi_score = 0.55
        elif 30 <= rsi < 35:
            rsi_score = 0.45
        else:
            rsi_score = 0.20

        if adx < 15:
            adx_score = 0.35
        elif adx < 25:
            adx_score = 0.70
        elif adx < 40:
            adx_score = 0.90
        else:
            adx_score = 0.70

        technical_score = _clamp((trend_score * 0.45) + (rsi_score * 0.35) + (adx_score * 0.20))
        macro_score = {
            'ALTSEASON': 0.95,
            'RISK_ON': 0.80,
            'NEUTRAL': 0.60,
            'CAUTION': 0.35,
            'RISK_OFF': 0.10,
        }.get(macro_regime, 0.55)
        mtf_score = _clamp(_safe_float(confluence_score, 0.5))

        if prior and prior.get('found'):
            win_rate = _safe_float(prior.get('win_rate'), 0.5)
            profit_factor = min(_safe_float(prior.get('profit_factor'), 1.0), 3.0)
            historical_score = _clamp((win_rate * 0.65) + ((profit_factor / 3.0) * 0.35))
        else:
            historical_score = 0.50

        final_score = _clamp(
            technical_score * 0.30
            + mtf_score * 0.25
            + historical_score * 0.20
            + macro_score * 0.15
            + 0.10  # reserva conservadora para no sobrepremiar una sola capa
        )
        components = {
            'technical': round(technical_score, 3),
            'mtf': round(mtf_score, 3),
            'historical': round(historical_score, 3),
            'macro': round(macro_score, 3),
        }
        return round(final_score, 3), components

    def build_rules_decision(self, score, components, indicators, strategy, macro_regime):
        threshold = _safe_float(config.MIN_AUTO_DECISION_SCORE, 0.62)
        action = "BUY" if score >= threshold else "HOLD"
        if score <= 0.30 and indicators.get('trend') == 'BEAR':
            action = "SELL"
        return {
            "regime": indicators.get('trend_regime', indicators.get('trend', 'RANGING')),
            "best_strategy": strategy,
            "action": action,
            "confidence": score,
            "position_size_multiplier": _clamp(0.75 + (score - threshold), 0.5, 1.25),
            "stop_loss_atr": 2.0,
            "take_profit_ratio": 2.0,
            "reasoning": (
                f"[RULE SCORE] score={score:.0%}, tech={components['technical']:.0%}, "
                f"MTF={components['mtf']:.0%}, histórico={components['historical']:.0%}, macro={macro_regime}"
            ),
            "provider": "RulesEngine",
            "decision_score": score,
            "score_components": components,
            "decision_mode": "rules",
            "macro_regime": macro_regime,
        }
        
    def quick_technical_filter(self, indicators, current_price):
        if not indicators: return False, _('FILTER_SIN_DATOS', lang=self.current_lang)
        rsi = indicators.get('rsi')
        trend = indicators.get('trend', 'UNKNOWN')
        adx = indicators.get('adx', 0)
        if rsi > 44 and rsi < 56 and adx < 15:
            return False, f"{ _('FILTER_SIDEWAYS', lang=self.current_lang) } (RSI: {rsi:.1f}, ADX: {adx:.1f})"
        return True, "Filtro OK"

    def analyze_with_ai_hybrid(self, symbol, current_price, indicators, ohlcv):
        """
        Análisis IA enriquecido con tres capas de contexto:
        1. Contexto macro del mercado (BTC dominance, sectores, on-chain)
        2. Análisis multi-timeframe (confluencia 1D + 4H)
        3. Prior histórico del backtest (win rate en condiciones similares)
        """
        now = time.time()

        # Invalidar caché si el idioma ha cambiado (v7.4)
        user_lang = self.sentiment.language
        if user_lang != self.current_lang:
            print(f"[DecisionEngine] Idioma cambiado de {self.current_lang} a {user_lang}. Limpiando caché...")
            self.last_analysis = {}
            self.decision_cache = {}
            self.current_lang = user_lang

        # Respetar intervalo de análisis por símbolo
        if symbol in self.last_analysis and now - self.last_analysis[symbol] < config.AI_ANALYSIS_INTERVAL:
            return self.decision_cache.get(symbol)

        # ─── CAPA 1: Contexto Macro (caché 6h) ───
        macro_text = ""
        macro_regime = "NEUTRAL"
        should_trade = True
        no_trade_reason = ""

        if now - self._macro_cache_ts > self.MACRO_CACHE_TTL:
            try:
                self._macro_cache = self.market_context.get_full_context_for_ai()
                self._macro_cache_ts = now
            except Exception as e:
                print(f"[DecisionEngine] Error actualizando macro context: {e}")

        if self._macro_cache:
            macro_text = self._macro_cache.get('context_block', '')
            macro_regime = self._macro_cache.get('macro_regime', 'NEUTRAL')
            should_trade, no_trade_reason = self.market_context.should_trade_altcoins(self._macro_cache, symbol=symbol)

        # Si el contexto macro dice no operar, devolver HOLD sin consumir tokens de IA
        if not should_trade:
            hold_decision = {
                "regime": macro_regime,
                "best_strategy": "HOLD",
                "action": "HOLD",
                "confidence": 0.0,
                "position_size_multiplier": 0.0,
                "stop_loss_atr": 2.0,
                "take_profit_ratio": 2.0,
                "reasoning": f"[{ _('MACRO_VETO_LABEL', lang=self.current_lang) }] {no_trade_reason}",
                "provider": "MacroFilter"
            }
            self.last_analysis[symbol] = now
            self.decision_cache[symbol] = hold_decision
            return hold_decision

        # ─── CAPA 2: Multi-Timeframe ───
        mtf_text = ""
        allow_long = True
        mtf_recommended_strategy = "TREND_FOLLOWING"
        confluence_score = 0.5

        if self.mtf_analyzer:
            try:
                mtf_result = self.mtf_analyzer.get_full_mtf_analysis(symbol)
                mtf_text = mtf_result.get('mtf_text', '')
                allow_long = mtf_result.get('allow_long', True)
                mtf_recommended_strategy = mtf_result.get('recommended_strategy', 'TREND_FOLLOWING')
                confluence_score = mtf_result.get('confluence_score', 0.5)
            except Exception as e:
                print(f"[DecisionEngine] Error MTF para {symbol}: {e}")

        # Si la confluencia MTF es muy bajista, no gastar tokens de IA
        if not allow_long:
            hold_decision = {
                "regime": "TRENDING_DOWN",
                "best_strategy": "HOLD",
                "action": "HOLD",
                "confidence": 0.0,
                "position_size_multiplier": 0.0,
                "stop_loss_atr": 2.0,
                "take_profit_ratio": 2.0,
                "reasoning": "[MTF VETO] Confluencia multi-timeframe bajista: 1D y 4H en tendencia descendente",
                "provider": "MTFFilter"
            }
            self.last_analysis[symbol] = now
            self.decision_cache[symbol] = hold_decision
            return hold_decision

        # ─── CAPA 3: Prior histórico del Backtest ───
        prior_text = ""
        hard_veto = False
        veto_reason = ""

        if self.backtest_engine:
            try:
                rsi_val = indicators.get('rsi', 50)
                adx_val = indicators.get('adx', 20)
                trend_val = indicators.get('trend', 'BULL')

                # Mapear valores actuales a buckets
                rsi_bucket = (
                    'OVERSOLD' if rsi_val < 30 else
                    'LOW' if rsi_val < 45 else
                    'NEUTRAL' if rsi_val < 55 else
                    'HIGH' if rsi_val < 65 else 'OVERBOUGHT'
                )
                adx_bucket = (
                    'WEAK' if adx_val < 15 else
                    'MODERATE' if adx_val < 25 else
                    'STRONG' if adx_val < 40 else 'EXTREME'
                )

                prior = self.backtest_engine.get_historical_prior(
                    symbol=symbol,
                    current_regime=indicators.get('trend_regime', 'RANGING'),
                    current_rsi_bucket=rsi_bucket,
                    current_adx_bucket=adx_bucket,
                    current_trend=trend_val,
                    proposed_strategy=mtf_recommended_strategy
                )

                prior_text = prior.get('prior_text', '')
                hard_veto = prior.get('hard_veto', False)
                veto_reason = prior.get('veto_reason', '')

            except Exception as e:
                print(f"[DecisionEngine] Error consultando backtest prior para {symbol}: {e}")

        # Aplicar veto duro del backtest
        if hard_veto:
            hold_decision = {
                "regime": indicators.get('trend', 'RANGING'),
                "best_strategy": "HOLD",
                "action": "HOLD",
                "confidence": 0.0,
                "position_size_multiplier": 0.0,
                "stop_loss_atr": 2.0,
                "take_profit_ratio": 2.0,
                "reasoning": veto_reason,
                "provider": "BacktestVeto"
            }
            self.last_analysis[symbol] = now
            self.decision_cache[symbol] = hold_decision
            return hold_decision

        decision_score, score_components = self.build_decision_score(
            indicators=indicators,
            macro_regime=macro_regime,
            confluence_score=confluence_score,
            prior=prior if 'prior' in locals() else None,
        )

        decision_mode = getattr(config, 'DECISION_MODE', 'hybrid')
        if decision_mode == 'rules':
            rules_decision = self.build_rules_decision(
                decision_score,
                score_components,
                indicators,
                mtf_recommended_strategy,
                macro_regime,
            )
            self.last_analysis[symbol] = now
            self.decision_cache[symbol] = rules_decision
            return rules_decision

        # ─── CONSTRUIR PROMPT ENRIQUECIDO ───
        df = pd.DataFrame(ohlcv[-100:], columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'])

        news = self.sentiment.get_news(symbol, limit=6)
        fng_value, fng_class = self.sentiment.get_fear_and_greed()

        system_instruction = config.PROMPT_DECISION
        lang_name = "English" if self.current_lang == 'en' else "Spanish"
        system_instruction += f"\nDEBES responder SIEMPRE en idioma {lang_name}."

        prompt = f"""Analiza {symbol} (${current_price:.6f}).

=== INDICADORES 15M ===
RSI: {indicators.get('rsi', 0):.1f} | ADX: {indicators.get('adx', 0):.1f} | Tendencia: {indicators.get('trend', 'N/A')}
EMA50: {indicators.get('ema50', 0):.4f} | EMA200: {indicators.get('ema200', 0):.4f} | ATR: {indicators.get('atr', 0):.6f}
Fear & Greed Index: {fng_value} ({fng_class})

{macro_text}

{mtf_text}

=== CONTEXTO HISTÓRICO ===
Estrategia sugerida por MTF: {mtf_recommended_strategy} (confluencia {confluence_score:.0%})
{prior_text}

=== SCORE DETERMINISTA ===
Score final: {decision_score:.0%}
Componentes: técnico {score_components['technical']:.0%}, MTF {score_components['mtf']:.0%}, histórico {score_components['historical']:.0%}, macro {score_components['macro']:.0%}
Modo de decisión configurado: {decision_mode}

=== NOTICIAS RECIENTES ===
{chr(10).join(news[:4]) if news else 'Sin noticias disponibles'}

Teniendo en cuenta TODO el contexto anterior (macro, multi-timeframe e histórico), responde SOLO con este JSON:
{{
  "regime": "TRENDING_UP | TRENDING_DOWN | RANGING | HIGH_VOLATILITY",
  "best_strategy": "{mtf_recommended_strategy}",
  "action": "BUY | SELL | HOLD",
  "confidence": 0.XX,
  "position_size_multiplier": 0.XX,
  "stop_loss_atr": X.X,
  "take_profit_ratio": X.X,
  "reasoning": "Máximo 2 frases justificando la decisión"
}}

Considera que el umbral mínimo de confianza para BUY es 0.52 (más agresivo que el estándar).
Si la confluencia MTF es fuerte ({confluence_score:.0%}), puedes aumentar position_size_multiplier hasta 1.5.
"""

        raw_content, provider = self.sentiment.call_ai_hybrid(prompt, system_instruction)

        if raw_content:
            try:
                match = re.search(r'\{.*\}', raw_content, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                    result['provider'] = provider
                    result['confluence_score'] = confluence_score
                    result['macro_regime'] = macro_regime
                    result['decision_score'] = decision_score
                    result['score_components'] = score_components
                    result['decision_mode'] = decision_mode
                    result['ai_action'] = result.get('action', 'HOLD')

                    # Ajuste de confianza por confluencia: si MTF es muy fuerte, boosteamos
                    if confluence_score >= 0.80 and result.get('action') == 'BUY':
                        original_conf = result.get('confidence', 0)
                        result['confidence'] = min(0.95, original_conf * 1.10)

                    if decision_mode == 'hybrid':
                        if result.get('action') == 'BUY' and decision_score < config.MIN_AUTO_DECISION_SCORE:
                            result['action'] = 'HOLD'
                            result['reasoning'] = (
                                f"[LOW RULE SCORE] {result.get('reasoning', '')} "
                                f"(score {decision_score:.0%} < {config.MIN_AUTO_DECISION_SCORE:.0%})"
                            )
                        else:
                            ai_conf = _safe_float(result.get('confidence'), 0.0)
                            result['confidence'] = round(_clamp((ai_conf * 0.70) + (decision_score * 0.30)), 3)

                    self.last_analysis[symbol] = now
                    self.decision_cache[symbol] = result
                    return result
            except Exception as e:
                print(f"[DecisionEngine] Error parseando respuesta IA para {symbol}: {e}")

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
        prompt = f"Filtra esta lista y devuelve solo los nombres de los elegidos separados por comas: {', '.join(raw_symbols)}"
        raw_content, provider = self.sentiment.call_ai_hybrid(prompt, system_instruction)
        if raw_content:
            # Extraer cualquier cosa que se parezca a un símbolo (ABC/USDT, ABC-USDT o solo ABC)
            potential = re.findall(r'([A-Z0-9]+)', raw_content.upper())
            found = []
            for p in potential:
                symbol = f"{p}/USDT" if "/" not in p and "-" not in p else p.replace("-", "/")
                if symbol in raw_symbols:
                    found.append(symbol)
            
            if found: return list(set(found))
        
        return raw_symbols[:15]

    def get_decision(self, symbol, current_price, indicators, ohlcv, open_positions_count, is_already_open=False):
        if not is_already_open:
            passes, reason = self.quick_technical_filter(indicators, current_price)
            if not passes:
                return {"action": "HOLD", "reasoning": reason, "confidence": 0.0, "provider": "TechnicalFilter"}

        decision = self.analyze_with_ai_hybrid(symbol, current_price, indicators, ohlcv)
        if not decision:
            return {"action": "HOLD", "reasoning": "AI offline", "confidence": 0.0}

        # Umbral bajado de 0.60 a 0.52 para más operaciones
        if decision.get("action") != "HOLD" and decision.get("confidence", 0) < 0.52:
            decision["action"] = "HOLD"
            decision["reasoning"] = (
                f"[LOW CONF] {decision.get('reasoning', '')} "
                f"(conf {decision.get('confidence', 0):.0%} < 52%)"
            )

        return decision
