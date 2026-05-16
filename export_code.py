import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Configuraciones de exportación
parser = argparse.ArgumentParser(description="Exporta el código del proyecto a un TXT.")
parser.add_argument(
    "--include-env",
    action="store_true",
    help="Incluye .env explícitamente. Peligroso: puede contener claves/API secrets.",
)
args = parser.parse_args()

allowed_extensions = {'.py', '.json', '.md', '.txt', '.sql', '.example'}
ignore_items = {
    'venv', '__pycache__', '.git', 'codigo_completo.txt', 'iversoria.db',
    'iversoria_bot.log', '.env',
}
if args.include_env:
    ignore_items.discard('.env')

output_file = "codigo_completo.txt"

print(f"Generando {output_file}...")
if not args.include_env:
    print("Modo seguro: .env queda excluido. Usa --include-env solo si sabes lo que haces.")

with open(output_file, 'w', encoding='utf-8') as outfile:
    for root, dirs, files in os.walk(os.getcwd()):
        # Evitar entrar en carpetas ignoradas
        dirs[:] = [d for d in dirs if d not in ignore_items]
        
        for filename in files:
            ext = os.path.splitext(filename)[1]
            if ext in allowed_extensions or (args.include_env and filename == '.env'):
                if filename in ignore_items:
                    continue
                
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, os.getcwd())
                
                outfile.write("="*80 + "\n")
                outfile.write(f"ARCHIVO: {rel_path}\n")
                outfile.write(f"UBICACIÓN: {filepath}\n")
                outfile.write("="*80 + "\n\n")
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"--- No se pudo leer el contenido: {e} ---\n")
                
                outfile.write("\n\n")

print(f"✅ Exportación completada con éxito.")
