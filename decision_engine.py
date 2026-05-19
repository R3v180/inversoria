import json
import time
import re
import ast
import hashlib
from sentiment_engine import SentimentEngine
import pandas as pd
import config # Importar el módulo completo para hot-reload
from market_context import MarketContext
from multi_timeframe import MultiTimeframeAnalyzer
from backtest_engine import BacktestEngine
from database_manager import DatabaseManager
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


DECISION_REQUIRED_FIELDS = {
    "regime",
    "best_strategy",
    "action",
    "confidence",
    "position_size_multiplier",
    "stop_loss_atr",
    "take_profit_ratio",
    "reasoning",
}

DECISION_JSON_KEYS = (
    "regime",
    "best_strategy",
    "action",
    "confidence",
    "position_size_multiplier",
    "stop_loss_atr",
    "take_profit_ratio",
    "reasoning",
)

ALLOWED_AI_REGIMES = {
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGING",
    "HIGH_VOLATILITY",
    "STRONG_UPTREND",
    "STRONG_DOWNTREND",
    "MODERATE_UPTREND",
    "MODERATE_DOWNTREND",
    "CONSOLIDATION",
}

ALLOWED_AI_STRATEGIES = {
    "TREND_FOLLOWING",
    "BREAKOUT",
    "MEAN_REVERSION",
    "MOMENTUM",
    "HOLD",
}


def _strip_markdown_fences(text):
    cleaned = str(text or "").strip().lstrip("\ufeff")
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return cleaned.strip()


def _extract_first_json_object(text):
    cleaned = _strip_markdown_fences(text)
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    quote = ""
    for idx in range(start, len(cleaned)):
        char = cleaned[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_string = False
            continue
        if char in ('"', "'"):
            in_string = True
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start:idx + 1].strip()
    return None


def _remove_json_comments(text):
    out = []
    i = 0
    in_string = False
    escape = False
    quote = ""
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_string = False
            i += 1
            continue
        if char in ('"', "'"):
            in_string = True
            quote = char
            out.append(char)
            i += 1
            continue
        if char == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if char == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _repair_common_json_issues(text):
    repaired = str(text or "").strip()
    repaired = repaired.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    repaired = _remove_json_comments(repaired)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(
        r'(?<=[0-9}"\]])\s+(?="(?:' + "|".join(DECISION_JSON_KEYS) + r')"\s*:)',
        ", ",
        repaired,
    )
    # Reparar claves conocidas sin comillas, preservando el prefijo capturado.
    for key in DECISION_JSON_KEYS:
        repaired = re.sub(rf'([{{,]\s*){key}\s*:', rf'\1"{key}":', repaired)
    repaired = re.sub(
        r'(?<=[0-9}"\]])\s+(?="(?:' + "|".join(DECISION_JSON_KEYS) + r')"\s*:)',
        ", ",
        repaired,
    )
    return repaired


class DecisionEngine:
    def __init__(self, sentiment=None, exchange=None, lang='es'):
        self.sentiment = sentiment if sentiment else SentimentEngine()
        self.current_lang = lang
        self.last_analysis = {}
        self.decision_cache = {}
        self.db = DatabaseManager()

        # Nuevas capas de inteligencia
        self.market_context = MarketContext(lang=self.current_lang)
        self.mtf_analyzer = MultiTimeframeAnalyzer(exchange) if exchange else None
        self.backtest_engine = BacktestEngine(exchange, lang=self.current_lang) if exchange else None

        # Cache del contexto macro (se actualiza cada 6h)
        self._macro_cache = None
        self._macro_cache_ts = 0
        self.MACRO_CACHE_TTL = 21600  # 6 horas
        self._adaptive_cache = None
        self._adaptive_cache_ts = 0
        self.ADAPTIVE_CACHE_TTL = 900  # 15 minutos

    def _decision_cache_signature(self):
        keys = {
            'decision_mode': getattr(config, 'DECISION_MODE', 'hybrid'),
            'min_score': getattr(config, 'MIN_AUTO_DECISION_SCORE', 0.62),
            'min_conf': getattr(config, 'MIN_CONFIDENCE_ENTRY', 0.52),
            'aggressive': getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False),
            'macro_veto': getattr(config, 'MACRO_VETO_ALTS_IN_RISK_OFF', True),
            'mtf_counter': getattr(config, 'MTF_ALLOW_COUNTER_TREND', False),
            'prompt': getattr(config, 'PROMPT_DECISION', ''),
            'lang': self.current_lang,
        }
        raw = json.dumps(keys, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _decision_cache_key(self, symbol):
        safe_symbol = str(symbol or '').replace('/', '_').replace(':', '_')
        return f"ai_decision_cache_{safe_symbol}"

    def _load_persistent_decision(self, symbol, now):
        raw = self.db.get_system_status(self._decision_cache_key(symbol))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        if payload.get('signature') != self._decision_cache_signature():
            return None
        ts = _safe_float(payload.get('timestamp'), 0.0)
        if now - ts >= getattr(config, 'AI_ANALYSIS_INTERVAL', 1200):
            return None
        decision = payload.get('decision')
        if not isinstance(decision, dict):
            return None
        decision = dict(decision)
        decision['cache_hit'] = 'persistent'
        return decision

    def _store_persistent_decision(self, symbol, decision, now):
        if not decision:
            return
        payload = {
            'timestamp': now,
            'signature': self._decision_cache_signature(),
            'decision': decision,
        }
        try:
            self.db.set_system_status(
                self._decision_cache_key(symbol),
                json.dumps(payload, ensure_ascii=False),
            )
        except Exception:
            pass

    def _remember_decision(self, symbol, decision, now, persist=True):
        self.last_analysis[symbol] = now
        self.decision_cache[symbol] = decision
        if persist:
            self._store_persistent_decision(symbol, decision, now)
        return decision

    def _dynamic_score_weights(self, indicators, macro_regime):
        regime = str(indicators.get('trend_regime') or indicators.get('trend') or '').upper()
        macro = str(macro_regime or '').upper()
        if macro in {'RISK_OFF', 'CAUTION'}:
            weights = {'technical': 0.22, 'mtf': 0.22, 'historical': 0.16, 'macro': 0.25, 'adaptive': 0.15}
        elif regime in {'TRENDING_UP', 'BULL'}:
            weights = {'technical': 0.30, 'mtf': 0.30, 'historical': 0.15, 'macro': 0.10, 'adaptive': 0.15}
        elif regime in {'HIGH_VOLATILITY'}:
            weights = {'technical': 0.20, 'mtf': 0.25, 'historical': 0.15, 'macro': 0.25, 'adaptive': 0.15}
        elif regime in {'RANGING'}:
            weights = {'technical': 0.25, 'mtf': 0.20, 'historical': 0.25, 'macro': 0.10, 'adaptive': 0.20}
        else:
            weights = {'technical': 0.28, 'mtf': 0.25, 'historical': 0.20, 'macro': 0.12, 'adaptive': 0.15}
        total = sum(weights.values()) or 1.0
        return {key: value / total for key, value in weights.items()}

    def _adaptive_snapshot(self):
        if not getattr(config, 'ADAPTIVE_SCORING_ENABLED', True):
            return {}
        now = time.time()
        if self._adaptive_cache is not None and now - self._adaptive_cache_ts < self.ADAPTIVE_CACHE_TTL:
            return self._adaptive_cache
        try:
            from database_manager import DatabaseManager
            db = DatabaseManager()
            self._adaptive_cache = db.get_adaptive_edge_snapshot(
                limit=1000,
                min_trades=getattr(config, 'ADAPTIVE_MIN_TRADES', 5),
            )
            self._adaptive_cache_ts = now
        except Exception as exc:
            print(f"[DecisionEngine] Adaptive edge unavailable: {exc}")
            self._adaptive_cache = {}
            self._adaptive_cache_ts = now
        return self._adaptive_cache or {}

    def _edge_adjustment(self, snapshot, *, symbol=None, regime=None, strategy=None, provider=None):
        if not snapshot or not snapshot.get('enabled'):
            return 0.0, {}
        max_adj = abs(_safe_float(getattr(config, 'ADAPTIVE_MAX_SCORE_ADJUSTMENT', 0.12), 0.12))
        weighted = []

        def add(bucket, key, weight):
            if not key:
                return
            stats = (snapshot.get(bucket) or {}).get(str(key))
            if stats:
                weighted.append((weight, _safe_float(stats.get('adjustment')), bucket, str(key), stats))

        global_stats = snapshot.get('global')
        if global_stats and _safe_float(global_stats.get('trades')) >= getattr(config, 'ADAPTIVE_MIN_TRADES', 5):
            weighted.append((0.15, _safe_float(global_stats.get('adjustment')), 'global', 'ALL', global_stats))
        add('by_regime', regime, 0.25)
        add('by_strategy', strategy, 0.20)
        add('by_symbol', symbol, 0.20)
        add('by_provider', provider, 0.30)
        if not weighted:
            return 0.0, {}
        weight_sum = sum(w for w, *_ in weighted) or 1.0
        raw = sum(w * adj for w, adj, *_ in weighted) / weight_sum
        adjustment = _clamp(raw, -max_adj, max_adj)
        evidence = {
            'adjustment': round(adjustment, 4),
            'max_adjustment': round(max_adj, 4),
            'rolling_expectancy_pct': snapshot.get('rolling_expectancy_pct'),
            'edge_decay_pct': snapshot.get('edge_decay_pct'),
            'sources': [
                {
                    'type': bucket,
                    'key': key,
                    'weight': weight,
                    'trades': stats.get('trades'),
                    'expectancy_pct': stats.get('expectancy_pct'),
                    'profit_factor': stats.get('profit_factor'),
                    'win_rate': stats.get('win_rate'),
                    'source_adjustment': stats.get('adjustment'),
                }
                for weight, _, bucket, key, stats in weighted
            ],
        }
        return adjustment, evidence

    def _apply_adaptive_adjustment(self, score, components, evidence):
        adjustment = _safe_float((evidence or {}).get('adjustment'), 0.0)
        adjusted = _clamp(score + adjustment)
        components = dict(components or {})
        components['adaptive'] = round(_clamp(0.5 + adjustment * 3.0), 3)
        components['adaptive_adjustment'] = round(adjustment, 4)
        components['adaptive_evidence'] = evidence or {}
        return round(adjusted, 3), components

    def _parse_ai_decision_json(self, raw_content):
        raw_object = _extract_first_json_object(raw_content)
        if not raw_object:
            raise ValueError("No JSON object found")

        attempts = [
            ("raw", raw_object),
            ("repaired", _repair_common_json_issues(raw_object)),
        ]
        last_error = None
        for mode, candidate in attempts:
            try:
                parsed = json.loads(candidate)
                return parsed, mode
            except json.JSONDecodeError as exc:
                last_error = exc

        try:
            parsed = ast.literal_eval(_repair_common_json_issues(raw_object))
            if isinstance(parsed, dict):
                return parsed, "literal_eval"
        except (SyntaxError, ValueError) as exc:
            last_error = exc

        raise ValueError(str(last_error or "Invalid JSON"))

    def _parse_ai_batch_json(self, raw_content):
        raw_object = _extract_first_json_object(raw_content)
        if not raw_object:
            raise ValueError("No JSON object found")
        attempts = [
            ("raw", raw_object),
            ("repaired", _repair_common_json_issues(raw_object)),
        ]
        last_error = None
        for mode, candidate in attempts:
            try:
                parsed = json.loads(candidate)
                return parsed, mode
            except json.JSONDecodeError as exc:
                last_error = exc
        try:
            parsed = ast.literal_eval(_repair_common_json_issues(raw_object))
            if isinstance(parsed, dict):
                return parsed, "literal_eval"
        except (SyntaxError, ValueError) as exc:
            last_error = exc
        raise ValueError(str(last_error or "Invalid batch JSON"))

    def _validate_ai_decision(self, result):
        if not isinstance(result, dict):
            raise ValueError("AI JSON is not an object")
        missing = sorted(DECISION_REQUIRED_FIELDS - set(result.keys()))
        if missing:
            raise ValueError(f"AI JSON missing fields: {','.join(missing)}")

        result = dict(result)
        result['action'] = str(result.get('action', 'HOLD')).upper()
        if result['action'] not in {"BUY", "SELL", "HOLD"}:
            raise ValueError(f"Invalid action: {result['action']}")
        result['regime'] = str(result.get('regime', 'RANGING')).upper()
        if result['regime'] not in ALLOWED_AI_REGIMES:
            result['regime'] = 'RANGING'
        result['confidence'] = round(_clamp(_safe_float(result.get('confidence'), 0.0)), 3)
        max_size_mult = float(getattr(config, 'AI_MAX_POSITION_SIZE_MULTIPLIER', 1.5) or 1.5)
        result['position_size_multiplier'] = round(_clamp(_safe_float(result.get('position_size_multiplier'), 1.0), 0.0, max_size_mult), 3)
        result['stop_loss_atr'] = round(_clamp(_safe_float(result.get('stop_loss_atr'), 2.0), 0.5, 6.0), 3)
        result['take_profit_ratio'] = round(_clamp(_safe_float(result.get('take_profit_ratio'), 2.0), 0.5, 8.0), 3)
        result['best_strategy'] = str(result.get('best_strategy') or 'HOLD').upper()
        if result['best_strategy'] not in ALLOWED_AI_STRATEGIES:
            result['best_strategy'] = 'HOLD'
        result['reasoning'] = " ".join(str(result.get('reasoning') or '').split())[:500]
        return result

    def build_decision_score(self, indicators, macro_regime, confluence_score, prior, symbol=None, strategy=None):
        """Score determinista y auditable. La IA puede opinar, pero esta capa deja rastro cuantitativo."""
        rsi = _safe_float(indicators.get('rsi'), 50.0)
        adx = _safe_float(indicators.get('adx'), 0.0)
        trend = indicators.get('trend', 'BEAR')
        volume_ratio = _safe_float(indicators.get('volume_ratio'), 1.0)
        macd_hist = _safe_float(indicators.get('macd_hist'), 0.0)
        macd = _safe_float(indicators.get('macd'), 0.0)
        macd_signal = _safe_float(indicators.get('macd_signal'), 0.0)
        bb_percent = _safe_float(indicators.get('bb_percent'), 0.5)
        stoch_k = _safe_float(indicators.get('stochrsi_k'), 50.0)
        obv_slope = _safe_float(indicators.get('obv_slope'), 0.0)

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

        if volume_ratio >= 1.5:
            volume_score = 0.90
        elif volume_ratio >= 1.0:
            volume_score = 0.70
        elif volume_ratio >= 0.7:
            volume_score = 0.45
        else:
            volume_score = 0.25

        macd_score = 0.75 if macd_hist > 0 and macd >= macd_signal else 0.35
        if macd_hist > 0 and obv_slope > 0:
            macd_score = min(0.95, macd_score + 0.10)
        if 0.20 <= bb_percent <= 0.85:
            bb_score = 0.70
        elif bb_percent < 0.20:
            bb_score = 0.55
        else:
            bb_score = 0.35
        if 20 <= stoch_k <= 80:
            stoch_score = 0.65
        elif stoch_k < 20:
            stoch_score = 0.50
        else:
            stoch_score = 0.30
        momentum_score = _clamp((macd_score * 0.45) + (bb_score * 0.25) + (stoch_score * 0.20) + ((0.75 if obv_slope > 0 else 0.35) * 0.10))

        technical_score = _clamp(
            (trend_score * 0.30)
            + (rsi_score * 0.20)
            + (adx_score * 0.15)
            + (volume_score * 0.15)
            + (momentum_score * 0.20)
        )
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

        snapshot = self._adaptive_snapshot()
        adaptive_adjustment, adaptive_evidence = self._edge_adjustment(
            snapshot,
            symbol=symbol,
            regime=indicators.get('trend_regime', indicators.get('trend')),
            strategy=strategy,
        )
        adaptive_score = _clamp(0.5 + adaptive_adjustment * 3.0)
        weights = self._dynamic_score_weights(indicators, macro_regime)
        final_score = _clamp(
            technical_score * weights['technical']
            + mtf_score * weights['mtf']
            + historical_score * weights['historical']
            + macro_score * weights['macro']
            + adaptive_score * weights['adaptive']
        )
        components = {
            'technical': round(technical_score, 3),
            'mtf': round(mtf_score, 3),
            'historical': round(historical_score, 3),
            'macro': round(macro_score, 3),
            'volume': round(volume_score, 3),
            'momentum': round(momentum_score, 3),
            'adaptive': round(adaptive_score, 3),
            'historical_trades': int((prior or {}).get('total_trades', 0) or 0),
            'historical_reliability': round(_safe_float((prior or {}).get('reliability_score'), 0.0), 3),
            'adaptive_adjustment': round(adaptive_adjustment, 4),
            'weights': {key: round(value, 3) for key, value in weights.items()},
            'adaptive_evidence': adaptive_evidence,
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
                f"MTF={components['mtf']:.0%}, histórico={components['historical']:.0%}, "
                f"adaptativo={components.get('adaptive', 0.5):.0%}, macro={macro_regime}"
            ),
            "provider": "RulesEngine",
            "decision_score": score,
            "score_components": components,
            "adaptive_adjustment": components.get('adaptive_adjustment', 0.0),
            "adaptive_evidence": components.get('adaptive_evidence', {}),
            "decision_mode": "rules",
            "macro_regime": macro_regime,
        }
        
    def quick_technical_filter(self, indicators, current_price):
        if not indicators: return False, _('FILTER_SIN_DATOS', lang=self.current_lang)
        rsi = _safe_float(indicators.get('rsi'), 50.0)
        adx = _safe_float(indicators.get('adx'), 0.0)
        aggressive = bool(getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False))
        if aggressive:
            if 48 < rsi < 52 and adx < 10:
                return False, f"{ _('FILTER_SIDEWAYS', lang=self.current_lang) } (RSI: {rsi:.1f}, ADX: {adx:.1f})"
        elif rsi > 44 and rsi < 56 and adx < 15:
            return False, f"{ _('FILTER_SIDEWAYS', lang=self.current_lang) } (RSI: {rsi:.1f}, ADX: {adx:.1f})"
        return True, "Filtro OK"

    def analyze_with_ai_hybrid(self, symbol, current_price, indicators, ohlcv, return_context_only=False):
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
        persisted = self._load_persistent_decision(symbol, now)
        if persisted:
            self.last_analysis[symbol] = now
            self.decision_cache[symbol] = persisted
            return persisted

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
            return self._remember_decision(symbol, hold_decision, now, persist=False)

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

        allow_counter = bool(getattr(config, 'MTF_ALLOW_COUNTER_TREND', False)) or bool(
            getattr(config, 'AGGRESSIVE_TRADING_PROFILE', False)
        )
        if not allow_long and not allow_counter:
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
            return self._remember_decision(symbol, hold_decision, now, persist=False)
        if not allow_long and allow_counter:
            confluence_score = min(confluence_score, 0.38)
            mtf_text = (mtf_text or "") + "\n[MTF] Counter-trend permitido (perfil agresivo); confluencia reducida."

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
            return self._remember_decision(symbol, hold_decision, now, persist=False)

        decision_score, score_components = self.build_decision_score(
            indicators=indicators,
            macro_regime=macro_regime,
            confluence_score=confluence_score,
            prior=prior if 'prior' in locals() else None,
            symbol=symbol,
            strategy=mtf_recommended_strategy,
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
            return self._remember_decision(symbol, rules_decision, now, persist=False)

        # ─── CONSTRUIR PROMPT ENRIQUECIDO ───
        df = pd.DataFrame(ohlcv[-100:], columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'])

        news = self.sentiment.get_news(symbol, limit=6)
        fng_value, fng_class = self.sentiment.get_fear_and_greed()

        system_instruction = config.PROMPT_DECISION
        lang_name = "English" if self.current_lang == 'en' else "Spanish"
        system_instruction += f"\nDEBES responder SIEMPRE en idioma {lang_name}."
        system_instruction += (
            "\nFORMATO OBLIGATORIO: devuelve exclusivamente un objeto JSON válido. "
            "Sin markdown, sin ``` fences, sin texto antes/después, sin comentarios. "
            "Usa comillas dobles en todas las claves y strings. Incluye todos los campos requeridos: "
            "regime, best_strategy, action, confidence, position_size_multiplier, stop_loss_atr, "
            "take_profit_ratio, reasoning. No uses NaN, Infinity ni trailing commas."
        )

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
Componentes: técnico {score_components['technical']:.0%}, MTF {score_components['mtf']:.0%}, histórico {score_components['historical']:.0%}, macro {score_components['macro']:.0%}, adaptativo {score_components.get('adaptive', 0.5):.0%}
Pesos dinámicos: {score_components.get('weights', {})}
Edge adaptativo: ajuste {score_components.get('adaptive_adjustment', 0):+.2%}; evidencia {score_components.get('adaptive_evidence', {})}
Modo de decisión configurado: {decision_mode}

=== NOTICIAS RECIENTES ===
{chr(10).join(news[:4]) if news else 'Sin noticias disponibles'}

Teniendo en cuenta TODO el contexto anterior (macro, multi-timeframe e histórico), responde SOLO con un JSON válido exactamente con estas claves:
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

Reglas estrictas de salida:
- Primer caracter: {{ y último caracter: }}.
- No incluyas markdown, comentarios, explicaciones, viñetas ni texto fuera del JSON.
- Usa solo comillas dobles. No dejes comas finales. No omitas comas entre campos.
- Todos los campos son obligatorios aunque la decisión sea HOLD.

Considera que el umbral mínimo de confianza para BUY es 0.52 (más agresivo que el estándar).
Si la confluencia MTF es fuerte ({confluence_score:.0%}), puedes aumentar position_size_multiplier hasta 1.5.
"""

        if return_context_only:
            return {
                "_batch_context": True,
                "symbol": symbol,
                "prompt": prompt,
                "system_instruction": system_instruction,
                "confluence_score": confluence_score,
                "macro_regime": macro_regime,
                "decision_score": decision_score,
                "score_components": score_components,
                "decision_mode": decision_mode,
            }

        raw_content, provider = self.sentiment.call_ai_hybrid(
            prompt,
            system_instruction,
            feature="decision_single",
        )

        if raw_content:
            try:
                result, parse_mode = self._parse_ai_decision_json(raw_content)
                result = self._validate_ai_decision(result)
                if parse_mode != "raw":
                    print(
                        f"[DecisionEngine] JSON parse fallback OK para {symbol} | "
                        f"provider={provider} | mode={parse_mode}"
                    )
                result['provider'] = provider
                result['confluence_score'] = confluence_score
                result['macro_regime'] = macro_regime
                result['decision_score'] = decision_score
                result['score_components'] = score_components
                result['decision_mode'] = decision_mode
                result['ai_action'] = result.get('action', 'HOLD')
                result['adaptive_adjustment'] = score_components.get('adaptive_adjustment', 0.0)
                result['adaptive_evidence'] = score_components.get('adaptive_evidence', {})

                snapshot = self._adaptive_snapshot()
                provider_stats = (snapshot.get('by_provider') or {}).get(str(provider)) if snapshot else None
                provider_adjustment = 0.0
                provider_evidence = {}
                if provider_stats:
                    max_adj = abs(_safe_float(getattr(config, 'ADAPTIVE_MAX_SCORE_ADJUSTMENT', 0.12), 0.12))
                    provider_adjustment = _clamp(_safe_float(provider_stats.get('adjustment')), -max_adj, max_adj)
                    provider_evidence = {
                        'adjustment': round(provider_adjustment, 4),
                        'max_adjustment': round(max_adj, 4),
                        'sources': [{
                            'type': 'by_provider',
                            'key': str(provider),
                            'weight': 1.0,
                            'trades': provider_stats.get('trades'),
                            'expectancy_pct': provider_stats.get('expectancy_pct'),
                            'profit_factor': provider_stats.get('profit_factor'),
                            'win_rate': provider_stats.get('win_rate'),
                            'source_adjustment': provider_stats.get('adjustment'),
                        }],
                    }
                if provider_evidence:
                    result['decision_score'], result['score_components'] = self._apply_adaptive_adjustment(
                        result['decision_score'],
                        result['score_components'],
                        provider_evidence,
                    )
                    result['adaptive_adjustment'] = result['score_components'].get('adaptive_adjustment', provider_adjustment)
                    result['adaptive_evidence'] = provider_evidence

                # Ajuste de confianza por confluencia: si MTF es muy fuerte, boosteamos
                if confluence_score >= 0.80 and result.get('action') == 'BUY':
                    original_conf = result.get('confidence', 0)
                    result['confidence'] = min(0.95, original_conf * 1.10)

                if decision_mode == 'hybrid':
                    effective_score = _safe_float(result.get('decision_score'), decision_score)
                    if result.get('action') == 'BUY' and effective_score < config.MIN_AUTO_DECISION_SCORE:
                        result['action'] = 'HOLD'
                        result['reasoning'] = (
                            f"[LOW RULE SCORE] {result.get('reasoning', '')} "
                            f"(score {effective_score:.0%} < {config.MIN_AUTO_DECISION_SCORE:.0%})"
                        )
                    else:
                        ai_conf = _safe_float(result.get('confidence'), 0.0)
                        result['confidence'] = round(_clamp((ai_conf * 0.70) + (effective_score * 0.30)), 3)

                return self._remember_decision(symbol, result, now, persist=True)
            except Exception as e:
                print(f"[DecisionEngine] Error parseando respuesta IA para {symbol}: {e}")

        return self.decision_cache.get(symbol)

    def analyze_batch_with_ai(self, items):
        """
        Precalienta decision_cache para varios símbolos con una sola llamada IA.
        Si algo falla, el flujo individual existente sigue siendo el fallback.
        """
        now = time.time()
        contexts = []
        by_symbol = {}
        for item in items or []:
            symbol = item.get('symbol')
            if not symbol:
                continue
            if symbol in self.last_analysis and now - self.last_analysis[symbol] < config.AI_ANALYSIS_INTERVAL:
                continue
            persisted = self._load_persistent_decision(symbol, now)
            if persisted:
                self._remember_decision(symbol, persisted, now, persist=False)
                continue
            if not item.get('is_open'):
                passes, reason = self.quick_technical_filter(item.get('indicators') or {}, item.get('price'))
                if not passes:
                    continue
            prepared = self.analyze_with_ai_hybrid(
                symbol,
                item.get('price'),
                item.get('indicators') or {},
                item.get('ohlcv') or [],
                return_context_only=True,
            )
            if isinstance(prepared, dict) and prepared.get('_batch_context'):
                contexts.append(prepared)
                by_symbol[symbol] = prepared

        if not contexts:
            return {}

        shared_instruction = (
            f"{config.PROMPT_DECISION}\n"
            "DEBES responder SOLO JSON válido con esta forma exacta: "
            "{\"decisions\":[{\"symbol\":\"BTC/USDT\",\"regime\":\"...\",\"best_strategy\":\"...\","
            "\"action\":\"BUY|SELL|HOLD\",\"confidence\":0.0,\"position_size_multiplier\":1.0,"
            "\"stop_loss_atr\":2.0,\"take_profit_ratio\":2.0,\"reasoning\":\"máximo 1 frase\"}]}."
            " No incluyas markdown ni texto fuera del JSON."
        )
        prompt_parts = [
            "Analiza estos activos como un lote. Mantén cada decisión independiente y devuelve una entrada por símbolo.",
        ]
        for ctx in contexts:
            prompt_parts.append(f"\n--- SYMBOL_CONTEXT {ctx['symbol']} ---\n{ctx['prompt']}")
        raw_content, provider = self.sentiment.call_ai_hybrid(
            "\n".join(prompt_parts),
            shared_instruction,
            feature="decision_batch",
        )
        if not raw_content:
            return {}

        try:
            parsed, parse_mode = self._parse_ai_batch_json(raw_content)
            decisions = parsed.get('decisions') if isinstance(parsed, dict) else None
            if not isinstance(decisions, list):
                return {}
            if parse_mode != "raw":
                print(f"[DecisionEngine] JSON parse fallback OK para batch | provider={provider} | mode={parse_mode}")
        except Exception as exc:
            print(f"[DecisionEngine] Error parseando batch IA: {exc}")
            return {}

        out = {}
        for raw_decision in decisions:
            if not isinstance(raw_decision, dict):
                continue
            symbol = str(raw_decision.get('symbol') or '').upper()
            ctx = by_symbol.get(symbol)
            if not ctx:
                continue
            raw_decision = dict(raw_decision)
            raw_decision.pop('symbol', None)
            try:
                result = self._validate_ai_decision(raw_decision)
            except Exception as exc:
                print(f"[DecisionEngine] Decisión batch inválida para {symbol}: {exc}")
                continue
            result['provider'] = provider or 'BatchAI'
            result['confluence_score'] = ctx.get('confluence_score', 0.5)
            result['macro_regime'] = ctx.get('macro_regime', 'NEUTRAL')
            result['decision_score'] = ctx.get('decision_score', 0.0)
            result['score_components'] = ctx.get('score_components', {})
            result['decision_mode'] = ctx.get('decision_mode', getattr(config, 'DECISION_MODE', 'hybrid'))
            result['ai_action'] = result.get('action', 'HOLD')
            result['adaptive_adjustment'] = result.get('score_components', {}).get('adaptive_adjustment', 0.0)
            result['adaptive_evidence'] = result.get('score_components', {}).get('adaptive_evidence', {})
            result['batch_ai'] = True

            if result['decision_mode'] == 'hybrid':
                effective_score = _safe_float(result.get('decision_score'), 0.0)
                if result.get('action') == 'BUY' and effective_score < config.MIN_AUTO_DECISION_SCORE:
                    result['action'] = 'HOLD'
                    result['reasoning'] = (
                        f"[LOW RULE SCORE] {result.get('reasoning', '')} "
                        f"(score {effective_score:.0%} < {config.MIN_AUTO_DECISION_SCORE:.0%})"
                    )
                else:
                    ai_conf = _safe_float(result.get('confidence'), 0.0)
                    result['confidence'] = round(_clamp((ai_conf * 0.70) + (effective_score * 0.30)), 3)

            self._remember_decision(symbol, result, now, persist=True)
            out[symbol] = result
        return out

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
        raw_content, provider = self.sentiment.call_ai_hybrid(
            prompt,
            system_instruction,
            feature="radar_curation",
        )
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

        min_conf = float(getattr(config, 'MIN_CONFIDENCE_ENTRY', 0.52))
        if decision.get("action") != "HOLD" and decision.get("confidence", 0) < min_conf:
            decision["action"] = "HOLD"
            decision["reasoning"] = (
                f"[LOW CONF] {decision.get('reasoning', '')} "
                f"(conf {decision.get('confidence', 0):.0%} < {min_conf:.0%})"
            )

        return decision
