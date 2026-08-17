#!/usr/bin/env python3
# PDF A11y Converter
# Lädt die notwendigen KI-Modelle direkt in das lokale Projektverzeichnis.

import sys
import subprocess
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("📦 Installiere huggingface_hub für den Download...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "huggingface_hub", "-q"]
    )
    from huggingface_hub import snapshot_download


def download_hf_model(repo_id: str, target_dir: Path):
    """Lädt ein HuggingFace Repository offline-fähig herunter."""
    print(f"\n📥 Lade '{repo_id}' herunter...\n   Ziel: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    print(f"✅ Download von {repo_id} abgeschlossen.")


def main():
    root = Path(__file__).resolve().parent.parent
    mdir = root / "resources" / "models"

    print("🚀 Starte Offline-Modell-Seed-Run...")

    # 1. BLIP Vision (Alt-Texte)
    download_hf_model("Salesforce/blip-image-captioning-base", mdir / "blip")

    # 2. NLLB Translation (Übersetzung)
    download_hf_model("facebook/nllb-200-distilled-600M", mdir / "nllb")

    # 3. Nougat (Mathematik)
    download_hf_model("facebook/nougat-small", mdir / "nougat")

    # 4. Table Transformer (Deep Learning Tabellenerkennung)
    # A) Detection (Findet die Tabelle auf der Seite)
    download_hf_model(
        "microsoft/table-transformer-detection", mdir / "tatr-det"
    )
    # B) Recognition (Findet Zeilen/Spalten innerhalb der Tabelle)
    download_hf_model(
        "microsoft/table-transformer-structure-recognition", mdir / "tatr-rec"
    )

    print("\n🎉 Alle Enterprise-Modelle erfolgreich lokal gespeichert!")


if __name__ == "__main__":
    main()
