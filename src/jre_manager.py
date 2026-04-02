# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Manager für die lokale, eingebettete Java-Laufzeitumgebung.
(100% Offline, kein Download zur Laufzeit).
"""

import logging
import platform
from typing import Tuple, Optional
from src.config import get_resource_path

logger = logging.getLogger("pdf-converter")


def get_java_paths() -> Tuple[Optional[str], Optional[str]]:
    """Sucht Java ausschließlich im mitgelieferten Ordner."""
    system = platform.system().lower()

    os_folder = "macos" if system == "darwin" else system
    jre_root = get_resource_path(f"resources/{os_folder}/jre")

    if not jre_root.exists():
        logger.error("❌ Eingebettetes JRE nicht gefunden: %s", jre_root)
        return None, None

    exe_name = "java.exe" if system == "windows" else "java"

    for java_exe in jre_root.rglob(exe_name):
        if "bin" in java_exe.parts:
            return str(java_exe), str(java_exe.parent.parent)

    logger.error("❌ Keine %s im JRE-Ordner gefunden.", exe_name)
    return None, None
