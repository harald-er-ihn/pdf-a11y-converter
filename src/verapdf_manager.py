# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""Manager zum Auffinden der lokalen veraPDF Installation."""

import logging
import platform

from src.config import get_resource_path

logger = logging.getLogger("pdf-converter")


def get_verapdf_path() -> str | None:
    """Sucht das ausführbare veraPDF Skript in der lokalen Installation."""
    system = platform.system().lower()
    script_name = "verapdf.bat" if system == "windows" else "verapdf"

    # 🚀 FIX: Greift exakt auf den Ordner resources/verapdf/ zu
    script_path = get_resource_path(f"resources/verapdf/{script_name}")

    if script_path.exists() and script_path.is_file():
        return str(script_path)

    logger.error("❌ veraPDF Start-Skript nicht gefunden: %s", script_path)
    return None
