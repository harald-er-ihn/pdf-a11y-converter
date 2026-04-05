# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Bootstrap Loader für die Shared AI Runtime.
Entpackt die komprimierte Master-Umgebung beim ersten Programmstart
in den globalen AppData-Ordner (Enterprise Split Distribution).
Unterstützt auch den lokalen Dev-Modus.
"""

import os
import sys
import zipfile
from pathlib import Path


def get_global_runtime_dir() -> Path:
    """Ermittelt das OS-spezifische, globale Verzeichnis für die AI Runtime."""
    if sys.platform == "win32":
        base = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
        return Path(base) / "PDF-A11y" / "runtime"
    return Path.home() / ".pdf-a11y" / "runtime"


def ensure_runtime() -> None:
    """Prüft und entpackt die AI-Runtime beim allerersten Start."""
    # 1. Prüfen, ob wir aus dem Quellcode laufen (Dev-Modus)
    is_frozen = getattr(sys, "frozen", False)
    app_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

    local_dev_runtime = app_base / "runtime" / "ai_env"

    if not is_frozen and local_dev_runtime.exists():
        # Wir sind im Source-Code und die Dev-Umgebung wurde gebaut.
        # Kein Entpacken nötig, wir nutzen die lokale Kopie.
        return

    # 2. Produktions-Modus (Kompiliert)
    runtime_dir = get_global_runtime_dir()
    ai_env_dir = runtime_dir / "ai_env"

    if ai_env_dir.exists():
        return  # Runtime ist bereits global installiert!

    print("\n📦 Erster Start erkannt: Initialisiere AI Runtime...")
    print("⏳ Dies kann einen Moment dauern. Bitte warten...\n")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    archive_path = app_base / "runtime" / "ai_env.zip"

    if not archive_path.exists():
        print(f"⚠️ Warnung: Runtime-Archiv nicht gefunden unter {archive_path}")
        print("💡 TIPP FÜR ENTWICKLER: Führe 'python tools/setup_dev_env.py' aus,")
        print("   um die lokale Runtime zu generieren!")
        return

    try:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(runtime_dir)
        print("✅ AI Runtime erfolgreich installiert!\n")
    except Exception as e:
        print(f"❌ Fehler beim Entpacken der Runtime: {e}")
