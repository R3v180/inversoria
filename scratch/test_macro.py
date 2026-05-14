import requests
import os
from dotenv import load_dotenv

load_dotenv()

def test_alpha_vantage():
    api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
    print(f"[*] Usando API Key: {api_key[:5]}...{api_key[-5:] if api_key else 'None'}")
    
    symbol = "SPY"
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    
    print(f"[*] Consultando {symbol}...")
    try:
        response = requests.get(url)
        data = response.json()
        print("[DEBUG] Respuesta completa de la API:")
        print(data)
        
        if "Global Quote" in data:
            print(f"OK: Precio de {symbol} es {data['Global Quote'].get('05. price')}")
        elif "Note" in data:
            print(f"LIMIT: {data['Note']}")
        elif "Error Message" in data:
            print(f"ERROR: {data['Error Message']}")
        else:
            print("UNKNOWN: No se reconoce el formato de respuesta.")
            
    except Exception as e:
        print(f"CRITICAL FAIL: {e}")

if __name__ == "__main__":
    test_alpha_vantage()
