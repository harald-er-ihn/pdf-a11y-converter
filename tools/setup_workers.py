#!/usr/bin/env python3
# PDF A11y Converter
# Initialisiert die isolierten Venvs für die lokale Entwicklung (Windows/Linux/macOS)

import subprocess
import sys
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent.parent
    workers_dir = root_dir / "workers"
    
    print("🚀 Starte lokales Setup der isolierten KI-Worker...\n")

    for worker_dir in workers_dir.iterdir():
        if worker_dir.is_dir() and (worker_dir / "requirements.txt").exists():
            print(f"📦 Erstelle Venv für: {worker_dir.name}")
            venv_dir = worker_dir / "venv"

            # 1. Venv erstellen
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir.resolve())], check=True)

            # 2. Plattformspezifischer Pfad zur Python.exe im neuen Venv
            if sys.platform == "win32":
                py_exe = venv_dir / "Scripts" / "python.exe"
            else:
                py_exe = venv_dir / "bin" / "python"

            # 3. Basis-Pakete aktualisieren
            subprocess.run([
                str(py_exe.resolve()), "-m", "pip", "install", 
                "--upgrade", "pip", "setuptools", "wheel", "-q"
            ], check=False)

            # 4. Requirements des Workers installieren
            print(f"   📥 Installiere Abhängigkeiten (das kann bei PyTorch dauern)...")
            try:
                subprocess.run([
                    str(py_exe.resolve()), "-m", "pip", "install", "-r", 
                    str((worker_dir / "requirements.txt").resolve())
                ], check=True, encoding="utf-8", errors="replace")
            except subprocess.CalledProcessError as e:
                print(f"❌ Fehler bei {worker_dir.name}!")
                sys.exit(1)
            
            print(f"   ✅ {worker_dir.name} bereit!\n")

    print("🎉 Alle Worker-Venvs wurden erfolgreich lokal eingerichtet!")

if __name__ == "__main__":
    main()
