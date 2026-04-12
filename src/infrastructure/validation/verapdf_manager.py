# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later

import logging
import platform

from src.config import get_resource_path

logger = logging.getLogger("pdf-converter")


def get_verapdf_path() -> str | None:
    """Sucht das ausführbare veraPDF Skript in der lokalen Installation."""
    base_dir = get_resource_path("resources")
    verapdf_dir = base_dir / "verapdf"

    system = platform.system().lower()
    script_name = "verapdf.bat" if system == "windows" else "verapdf"

    # Das Skript liegt bei Greenfield 1.28 direkt im root-Verzeichnis
    script_path = verapdf_dir / script_name

    if script_path.exists() and script_path.is_file():
        return str(script_path)

    logger.error(f"❌ veraPDF Start-Skript nicht gefunden: {script_path}")
    return None
