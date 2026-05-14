"""
market_context.py — Capa 1: Contexto macro del mercado crypto
Actualización: cada 6 horas (guardado en SQLite via DatabaseManager)
Fuentes: CoinGecko (sin API key), Blockchain.info, Etherscan público,
         datos derivados de CCXT (ya disponible)
"""
import requests
import time
import json
from database_manager import DatabaseManager
from i18n import _


class MarketContext:
    """
    Recopila y sintetiza el estado global del mercado crypto sin APIs de pago.
    Todos los endpoints usados son públicos y no requieren registro.
    """

    COINGECKO_BASE = "https://api.coingecko.com/api/v3"
    BLOCKCHAIN_INFO = "https://blockchain.info"
    ETH_GAS_URL = "https://api.etherscan.io/api?module=gastracker&action=gasoracle"
    MEMPOOL_URL = "https://mempool.space/api"

    CACHE_TTL = 21600  # 6 horas en segundos

    def __init__(self, lang='es'):
        self.db = DatabaseManager()
        self.u_lang = lang
        self._cache = {}

    # ─────────────────────────────────────────────
    # MÉTRICAS GLOBALES (CoinGecko — sin API key)
    # ─────────────────────────────────────────────

    def get_global_metrics(self):
        """
        Obtiene métricas globales del mercado crypto.
        Retorna dict con dominancia BTC, cap total, volumen 24h, etc.
        """
        cache_key = 'global_metrics'
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            r = requests.get(f"{self.COINGECKO_BASE}/global", timeout=10)
            r.raise_for_status()
            data = r.json().get('data', {})

            result = {
                'btc_dominance': round(data.get('market_cap_percentage', {}).get('btc', 0), 2),
                'eth_dominance': round(data.get('market_cap_percentage', {}).get('eth', 0), 2),
                'total_market_cap_usd': data.get('total_market_cap', {}).get('usd', 0),
                'total_volume_24h_usd': data.get('total_volume', {}).get('usd', 0),
                'active_cryptos': data.get('active_cryptocurrencies', 0),
                'market_cap_change_24h_pct': round(data.get('market_cap_change_percentage_24h_usd', 0), 2),
                'timestamp': time.time()
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"[MarketContext] Error global metrics: {e}")
            return {}

    def get_sector_performance(self):
        """
        Obtiene rendimiento por sectores (DeFi, Layer2, Memes, etc.)
        para detectar qué narrativa está liderando el mercado.
        """
        cache_key = 'sector_performance'
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        sectors = {
            'defi': 'decentralized-finance-defi',
            'layer2': 'layer-2',
            'gaming': 'gaming',
            'ai_crypto': 'artificial-intelligence',
            'memes': 'meme-token'
        }

        result = {}
        for name, category_id in sectors.items():
            try:
                r = requests.get(
                    f"{self.COINGECKO_BASE}/coins/markets",
                    params={
                        'vs_currency': 'usd',
                        'category': category_id,
                        'order': 'market_cap_desc',
                        'per_page': 5,
                        'price_change_percentage': '24h'
                    },
                    timeout=8
                )
                if r.status_code == 200:
                    coins = r.json()
                    if coins:
                        avg_change = sum(
                            c.get('price_change_percentage_24h', 0) or 0
                            for c in coins
                        ) / len(coins)
                        result[name] = round(avg_change, 2)
                time.sleep(1.2)  # Respetar rate limit de CoinGecko gratuito
            except Exception as e:
                print(f"[MarketContext] Error sector {name}: {e}")

        self._set_cache(cache_key, result)
        return result

    # ─────────────────────────────────────────────
    # MÉTRICAS ON-CHAIN BITCOIN (blockchain.info — sin API key)
    # ─────────────────────────────────────────────

    def get_bitcoin_onchain(self):
        """
        Métricas on-chain de Bitcoin vía blockchain.info (completamente público).
        - n_tx: número de transacciones últimas 24h (proxy de actividad)
        - mempool_size: transacciones pendientes (presión en la red)
        - estimated_transaction_volume_usd: volumen real movido on-chain
        """
        cache_key = 'btc_onchain'
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        result = {}
        try:
            # Stats generales de la red Bitcoin
            r = requests.get(f"{self.BLOCKCHAIN_INFO}/stats?format=json", timeout=10)
            if r.status_code == 200:
                data = r.json()
                result['btc_tx_24h'] = data.get('n_tx', 0)
                result['btc_volume_usd'] = data.get('estimated_transaction_volume_usd', 0)
                result['btc_mempool_size'] = data.get('mempool_size', 0)
                result['btc_difficulty'] = data.get('difficulty', 0)

            # Interpretación del mempool
            # >50k tx pendientes = red congestionada = alta demanda = señal de actividad
            if result.get('btc_mempool_size', 0) > 50000:
                result['btc_network_pressure'] = 'HIGH'
            elif result.get('btc_mempool_size', 0) > 20000:
                result['btc_network_pressure'] = 'MEDIUM'
            else:
                result['btc_network_pressure'] = 'LOW'

            self._set_cache(cache_key, result)

        except Exception as e:
            print(f"[MarketContext] Error BTC on-chain: {e}")

        return result

    def get_ethereum_gas(self):
        """
        Gas de Ethereum como proxy de actividad DeFi.
        Gas alto = muchas transacciones = mercado activo.
        No requiere API key para consultas básicas.
        """
        cache_key = 'eth_gas'
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            r = requests.get(self.ETH_GAS_URL, timeout=8)
            if r.status_code == 200:
                data = r.json().get('result', {})
                safe_gas = 0
                if isinstance(data, dict):
                    safe_gas = int(data.get('SafeGasPrice', 0))
                else:
                    print(f"[MarketContext] ETH gas warning: {data}")
                    
                result = {
                    'eth_gas_gwei': safe_gas,
                    'eth_network_activity': (
                        'HIGH' if safe_gas > 50
                        else 'MEDIUM' if safe_gas > 20
                        else 'LOW'
                    )
                }
                self._set_cache(cache_key, result)
                return result
        except Exception as e:
            print(f"[MarketContext] Error ETH gas: {e}")

        return {}

    def get_mempool_space_stats(self):
        """
        Estadísticas del mempool de Bitcoin vía mempool.space (público, sin registro).
        Número de tx pendientes y fees medias como indicador de demanda real de BTC.
        """
        cache_key = 'mempool_space'
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            r = requests.get(f"{self.MEMPOOL_URL}/mempool", timeout=8)
            if r.status_code == 200:
                data = r.json()
                result = {
                    'pending_tx_count': data.get('count', 0),
                    'mempool_vsize_mb': round(data.get('vsize', 0) / 1_000_000, 2),
                }
                self._set_cache(cache_key, result)
                return result
        except Exception as e:
            print(f"[MarketContext] Error mempool.space: {e}")

        return {}

    # ─────────────────────────────────────────────
    # SÍNTESIS FINAL — LO QUE VA AL PROMPT DE LA IA
    # ─────────────────────────────────────────────

    def get_full_context_for_ai(self):
        """
        Método principal. Sintetiza todas las métricas en un bloque de texto
        estructurado y compacto listo para insertar en el prompt de la IA.
        También determina el MACRO_REGIME del mercado.
        """
        global_m = self.get_global_metrics()
        btc_chain = self.get_bitcoin_onchain()
        eth_gas = self.get_ethereum_gas()
        sectors = self.get_sector_performance()

        # ─── Determinar régimen macro ───
        btc_dom = global_m.get('btc_dominance', 50)
        market_cap_change = global_m.get('market_cap_change_24h_pct', 0)
        btc_pressure = btc_chain.get('btc_network_pressure', 'MEDIUM')

        # Lógica de régimen macro simplificada pero efectiva:
        # BTC dominancia alta + cap bajando = mercado temeroso / risk-off
        # BTC dominancia baja + cap subiendo = altseason / risk-on
        if btc_dom > 58 and market_cap_change < -2:
            macro_regime = 'RISK_OFF'       # Mal momento para altcoins
        elif btc_dom < 48 and market_cap_change > 2:
            macro_regime = 'ALTSEASON'      # Momento ideal para altcoins
        elif market_cap_change > 1:
            macro_regime = 'RISK_ON'        # Mercado en positivo
        elif market_cap_change < -1:
            macro_regime = 'CAUTION'        # Mercado en negativo leve
        else:
            macro_regime = 'NEUTRAL'        # Sin tendencia clara

        # ─── Sector líder ───
        leading_sector = max(sectors, key=lambda k: sectors.get(k, -999)) if sectors else 'unknown'
        leading_sector_change = sectors.get(leading_sector, 0)

        # ─── Macro Datos v6.0 (Alpha Vantage) ───
        macro_db_data = self.db.get_all_macro_data()
        macro_lines = []
        if macro_db_data:
            for sym, d in macro_db_data.items():
                macro_lines.append(f"{sym}: {d['price']} ({d['change_24h']:+.2f}%)")
        macro_str = " | ".join(macro_lines) if macro_lines else "N/A"

        # ─── Construir el bloque de texto para el prompt ───
        context_block = f"""
=== CONTEXTO MACRO GLOBAL (v6.0) ===
Régimen macro: {macro_regime}
Indicadores: {macro_str}
Dominancia BTC: {btc_dom}% | ETH: {global_m.get('eth_dominance', 0)}%
Cap. total 24h: {market_cap_change:+.2f}%
Sector líder: {leading_sector.upper()} ({leading_sector_change:+.2f}% 24h)
Sectores: { ' | '.join([f"{k}:{v:+.1f}%" for k,v in sectors.items()]) if sectors else 'N/A' }

=== ON-CHAIN SIGNALS ===
BTC transacciones 24h: {btc_chain.get('btc_tx_24h', 'N/A'):,}
BTC presión de red: {btc_pressure}
ETH actividad de red: {eth_gas.get('eth_network_activity', 'N/A')} ({eth_gas.get('eth_gas_gwei', 'N/A')} gwei)
""".strip()

        result = {
            'macro_regime': macro_regime,
            'btc_dominance': btc_dom,
            'market_cap_change_24h': market_cap_change,
            'leading_sector': leading_sector,
            'btc_network_pressure': btc_pressure,
            'eth_activity': eth_gas.get('eth_network_activity', 'MEDIUM'),
            'context_block': context_block,
            'sectors': sectors,
            'timestamp': time.time()
        }

        # Guardar en DB para que la UI lo pueda mostrar
        self.db.set_system_status('macro_context', json.dumps(result))

        return result

    def should_trade_altcoins(self, macro_context: dict) -> tuple[bool, str]:
        """
        Decisión binaria: ¿es buen momento macro para operar altcoins?
        Retorna (bool, razon_string)
        """
        regime = macro_context.get('macro_regime', 'NEUTRAL')
        btc_dom = macro_context.get('btc_dominance', 50)
        
        # Consultar datos de Alpha Vantage desde la DB
        macro_data = self.db.get_all_macro_data()
        
        # 1. Veto por DXY (Dólar fuerte = Riesgo en Cripto)
        dxy = macro_data.get('UUP') # Proxy del DXY
        if dxy and dxy['change_24h'] > 1.5:
            return False, f"{ _('MACRO_VETO_DXY', lang=self.u_lang) } (+{dxy['change_24h']}%)"

        # 2. Veto por SP500 (Pánico en Bolsa)
        spy = macro_data.get('SPY')
        if spy and spy['change_24h'] < -2.0:
            return False, f"{ _('MACRO_VETO_MARKET', lang=self.u_lang) } (SP500: {spy['change_24h']}%)"

        if regime == 'RISK_OFF':
            return False, f"RISK_OFF Mode: BTC Dom {btc_dom}%, risk-off market"
        if regime == 'CAUTION' and btc_dom > 55:
            print(f"[MarketContext] DEBUG: u_lang={self.u_lang}")
            reason = _('MACRO_VETO_DOM', lang=self.u_lang)
            return False, f"{reason} ({btc_dom}%)"

        return True, f"Macro OK: {regime}"

    # ─────────────────────────────────────────────
    # HELPERS DE CACHÉ INTERNA
    # ─────────────────────────────────────────────

    def _get_cache(self, key):
        entry = self._cache.get(key)
        if entry and time.time() - entry['ts'] < self.CACHE_TTL:
            return entry['data']
        return None

    def _set_cache(self, key, data):
        self._cache[key] = {'data': data, 'ts': time.time()}
