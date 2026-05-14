import requests
import os
import time
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
    
    def __init__(self, lang='es'):
        self.api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.db = DatabaseManager()
        self.u_lang = lang
        self.base_url = "https://www.alphavantage.co/query"

    def fetch_global_market_status(self):
        """Descarga los indicadores macro principales"""
        if not self.api_key:
            print("[Macro] Error: ALPHA_VANTAGE_API_KEY no configurada.")
            return

        # Lista de activos a monitorizar
        assets = {
            'SPY': 'S&P 500' if self.u_lang == 'en' else 'S&P 500 (Bolsa USA)',
            'UUP': 'DXY Proxy' if self.u_lang == 'en' else 'DXY Proxy (Dólar)',
            'GLD': 'Gold' if self.u_lang == 'en' else 'Oro (Refugio)',
            'USO': 'Oil' if self.u_lang == 'en' else 'Petróleo (Energía)'
        }

        print(f"[Macro] { _('MACRO_UPDATING', lang=self.u_lang) }")
        
        for symbol, name in assets.items():
            try:
                params = {
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol,
                    "apikey": self.api_key
                }
                response = requests.get(self.base_url, params=params)
                data = response.json()
                
                quote = data.get('Global Quote', {})
                if quote:
                    price = float(quote.get('05. price', 0))
                    change_pct = quote.get('10. change percent', '0%').replace('%', '')
                    change_pct = float(change_pct)
                    
                    self.db.set_macro_data(symbol, price, change_pct)
                    print(f"  [OK] {symbol} ({name}): ${price} ({change_pct:+.2f}%)")
                
                # Alpha Vantage Free Tier: 5 calls per minute
                time.sleep(15) 
                
            except Exception as e:
                print(f"  [!] Error consultando {symbol}: {e}")

    def get_macro_summary(self):
        """Genera un resumen textual para la IA"""
        data = self.db.get_all_macro_data()
        if not data:
            return "Sin datos macroeconómicos recientes."
        
        lines = []
        for sym, d in data.items():
            status = "ALZA" if d['change_24h'] > 0 else "BAJA"
            lines.append(f"- {sym}: ${d['price']} ({d['change_24h']:+.2f}%) -> {status}")
        
        return "Resumen Macro Global:\n" + "\n".join(lines)

if __name__ == "__main__":
    analyzer = MacroAnalyzer()
    analyzer.fetch_global_market_status()
    print("\n" + analyzer.get_macro_summary())
