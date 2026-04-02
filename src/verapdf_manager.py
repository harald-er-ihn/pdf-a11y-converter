# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""Manager zum Auffinden der lokalen veraPDF Installation."""

import logging
import platform
import sys
from pathlib import Path

from src.config import get_resource_path

logger = logging.getLogger("pdf-converter")


def get_verapdf_path() -> str | None:
    """Sucht das ausführbare veraPDF Skript in der lokalen Installation."""
    system = platform.system().lower()
    # 🚀 FIX: VeraPDF ist global, nicht OS-spezifisch!
    script_name = "verapdf.bat" if system == "windows" else "verapdf"

    # 1. Standard-Prüfung (Integrierte Ressourcen / _MEIPASS)
    res_path = f"resources/verapdf/{script_name}"
    script_path = get_resource_path(res_path)

    if script_path.exists() and script_path.is_file():
        return str(script_path)

    # 2. Fallback für Standalone-Betrieb (Neben der .exe / dem Skript)
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path.cwd()

    fallback = base_dir / "resources" / "verapdf" / script_name

    if fallback.exists() and fallback.is_file():
        return str(fallback)

    logger.error("❌ veraPDF Start-Skript nicht gefunden.")
    logger.error("   Gesucht in: %s", script_path)
    logger.error("   Fallback:   %s", fallback)
    logger.error("💡 TIPP: Stelle sicher, dass veraPDF in 'resources/verapdf/' liegt.")
    return None
