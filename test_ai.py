import os
import time
from google import genai
from groq import Groq
from dotenv import load_dotenv

# Cargar llaves
load_dotenv()

def test_ai():
    print("🚀 IVERSORIA - Diagnóstico de Cerebros IA v3.1")
    print("-" * 50)

    # 1. TEST GEMINI 3.1 FLASH LITE
    print("\n[1] Probando GEMINI 3.1 FLASH LITE...")
    key_google = os.getenv("GOOGLE_API_KEY")
    if key_google:
        try:
            client = genai.Client(api_key=key_google)
            response = client.models.generate_content(
                model='gemini-flash-lite-latest',
                contents="Di 'HOLA' si me escuchas."
            )
            print(f"✅ ÉXITO: {response.text.strip()}")
        except Exception as e:
            print(f"❌ FALLO: {e}")
    else:
        print("⚠️ No hay GOOGLE_API_KEY en el .env")

    # 2. TEST GEMINI 3 FLASH
    print("\n[2] Probando GEMINI 3 FLASH...")
    if key_google:
        try:
            client = genai.Client(api_key=key_google)
            response = client.models.generate_content(
                model='gemini-flash-latest',
                contents="Di 'HOLA' si me escuchas."
            )
            print(f"✅ ÉXITO: {response.text.strip()}")
        except Exception as e:
            print(f"❌ FALLO: {e}")

    # 3. TEST GROQ (8B)
    print("\n[3] Probando GROQ (Llama-3.1-8b)...")
    key_groq = os.getenv("GROQ_API_KEY")
    if key_groq:
        try:
            client = Groq(api_key=key_groq)
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "Di 'HOLA'."}],
                temperature=0.1
            )
            print(f"✅ ÉXITO: {completion.choices[0].message.content.strip()}")
        except Exception as e:
            if "429" in str(e):
                print("⚠️ BLOQUEADO: Estás en el Rate Limit de Groq (esto es normal si has usado mucho el bot hoy).")
            else:
                print(f"❌ FALLO: {e}")
    else:
        print("⚠️ No hay GROQ_API_KEY en el .env")

    print("\n" + "-" * 50)
    print("🏁 Diagnóstico finalizado.")

if __name__ == "__main__":
    test_ai()
