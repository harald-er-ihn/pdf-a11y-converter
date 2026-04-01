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
    script_name = "verapdf.bat" if system == "windows" else "verapdf"

    # 1. Standard-Prüfung (Integrierte Ressourcen / _MEIPASS)
    script_path = get_resource_path(f"resources/verapdf/{script_name}")
    if script_path.exists() and script_path.is_file():
        return str(script_path)

    # 2. 🚀 Fallback für Standalone-Betrieb (Neben der .exe)
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    fallback_path = base_dir / "resources" / "verapdf" / script_name

    if fallback_path.exists() and fallback_path.is_file():
        return str(fallback_path)

    logger.error("❌ veraPDF Start-Skript nicht gefunden.")
    logger.error("   Gesucht in: %s", script_path)
    logger.error("   Fallback:   %s", fallback_path)
    return None
