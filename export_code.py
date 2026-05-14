import os

# Configuraciones de exportación
allowed_extensions = {'.py', '.env', '.json', '.md', '.txt', '.sql'}
ignore_items = {'venv', '__pycache__', '.git', 'codigo_completo.txt', 'iversoria.db', 'iversoria_bot.log'}

output_file = "codigo_completo.txt"

print(f"Generando {output_file}...")

with open(output_file, 'w', encoding='utf-8') as outfile:
    for root, dirs, files in os.walk(os.getcwd()):
        # Evitar entrar en carpetas ignoradas
        dirs[:] = [d for d in dirs if d not in ignore_items]
        
        for filename in files:
            ext = os.path.splitext(filename)[1]
            if filename == '.env' or ext in allowed_extensions:
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
