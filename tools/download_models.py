#!/usr/bin/env python3
# PDF A11y Converter
# Lädt die notwendigen KI-Modelle direkt in den deterministischen lokalen Projektordner.

import sys
import os
from pathlib import Path

# Sicherstellen, dass das 'huggingface_hub' Modul für den Download da ist
try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("❌ huggingface_hub fehlt! Installiere es mit: pip install huggingface_hub")
    sys.exit(1)

def download_hf_model(repo_id: str, target_dir: Path):
    """Lädt ein HuggingFace Repository direkt in den Zielordner herunter."""
    print(f"\n📥 Lade '{repo_id}' herunter...\n   Ziel: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # local_dir_use_symlinks=False ist entscheidend für Windows! Es zwingt HF, 
    # die ECHTEN Dateien (.safetensors, .json) dorthin zu legen, statt kryptische Cache-Symlinks.
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
        resume_download=True
    )
    print(f"✅ Download von {repo_id} abgeschlossen.")

def main():
    root_dir = Path(__file__).resolve().parent.parent
    models_dir = root_dir / "resources" / "models"

    print(f"🚀 Starte Offline-Modell-Seed-Run...")
    print(f"📂 Speicherort: {models_dir}\n")

    # 1. BLIP Vision Modell
    download_hf_model("Salesforce/blip-image-captioning-base", models_dir / "blip")

    # 2. NLLB Translation Modell
    download_hf_model("facebook/nllb-200-distilled-600M", models_dir / "nllb")

    # 3. Nougat Modell (Optional, falls Nougat direkt HF benutzt)
    # Nougat nutzt standardmäßig facebook/nougat-small
    download_hf_model("facebook/nougat-small", models_dir / "nougat")

    print("\n🎉 Alle Modelle wurden erfolgreich in 'resources/models' gespeichert!")
    print("Du kannst dieses Verzeichnis (oder das gebaute Release) nun auf 100% isolierten Offline-Maschinen ausführen.")

if __name__ == "__main__":
    main()
