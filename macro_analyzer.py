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
        from dotenv import load_dotenv
        load_dotenv()
        self.api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.base_url = "https://www.alphavantage.co/query"
        self.db = DatabaseManager()
        self.u_lang = lang

    def fetch_global_market_status(self):
        """Actualiza indicadores macro (SP500, Oro, Petróleo, etc.)"""
        msg = "Actualizando indicadores globales..." if self.u_lang == 'es' else "Updating global indicators..."
        print(f"[Macro] {msg}")
        
        # Activos macro clave
        assets = {
            "SPY": "S&P 500",
            "UUP": "DXY (Dólar)",
            "GLD": "Oro",
            "USO": "Petróleo",
            "VXX": "Volatilidad (VIX)"
        }
        
        print(f"  [*] Processing {len(assets)} assets...")
        
        if not self.api_key:
            print("[Macro] Error: ALPHA_VANTAGE_API_KEY no configurada.")
            return
        
        for symbol, name in assets.items():
            try:
                params = {
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol,
                    "apikey": self.api_key
                }
                response = requests.get(self.base_url, params=params)
                data = response.json()
                
                if "Note" in data:
                    print(f"  [!] Alpha Vantage API Limit: {data['Note']}")
                    break

                quote = data.get('Global Quote', {})
                if quote:
                    price = float(quote.get('05. price', 0))
                    change_pct = quote.get('10. change percent', '0%').replace('%', '')
                    change_pct = float(change_pct)
                    
                    self.db.set_macro_data(symbol, price, change_pct)
                    status_ok = "OK" if self.u_lang == "en" else "LISTO"
                    print(f"  [{status_ok}] {symbol} ({name}): ${price} ({change_pct:+.2f}%)")
                else:
                    print(f"  [?] {symbol}: No data in response (Check API Key or Symbol)")
                
                # Alpha Vantage Free Tier: 5 calls per minute
                time.sleep(15) 
                
            except Exception as e:
                err_msg = "Error fetching" if self.u_lang == "en" else "Error consultando"
                print(f"  [!] {err_msg} {symbol}: {e}")

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
