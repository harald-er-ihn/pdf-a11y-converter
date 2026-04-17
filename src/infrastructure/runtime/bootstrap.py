# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Lizenziert unter der GNU General Public License v3 oder später
"""
Enterprise Runtime Bootstrapper.
Führt Just-In-Time (JIT) Patching von virtuellen Umgebungen durch,
um Portabilität auf isolierten Windows-Systemen zu garantieren.
"""

import logging
import sys
from pathlib import Path

from src.config import get_resource_path

logger = logging.getLogger("pdf-converter")


class VenvPatcher:
    """Heilt hardcodierte absolute Pfade in Windows Venvs dynamisch."""

    @classmethod
    def patch_all_venvs(cls) -> None:
        """Scannt alle Worker und patcht deren pyvenv.cfg (Nur Windows)."""
        if sys.platform != "win32":
            return

        runtime_dir = get_resource_path("python_runtime")
        if not runtime_dir.exists():
            logger.warning("Keine Embedded Runtime gefunden. Nutze System-Python.")
            return

        # Basis-Verzeichnis, in dem die Worker zur Laufzeit liegen
        workers_dir = get_resource_path("workers")
        if not workers_dir.exists():
            return

        expected_home = str(runtime_dir.resolve())
        expected_exe = str((runtime_dir / "python.exe").resolve())

        for worker_dir in workers_dir.iterdir():
            if not worker_dir.is_dir() or worker_dir.name == "common":
                continue

            cfg_path = worker_dir / "venv" / "pyvenv.cfg"
            if cfg_path.exists():
                cls._patch_cfg_file(cfg_path, expected_home, expected_exe)

    @classmethod
    def _patch_cfg_file(
        cls, cfg_path: Path, expected_home: str, expected_exe: str
    ) -> None:
        """Überschreibt die Pfade in einer pyvenv.cfg deterministisch."""
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            needs_update = False
            new_lines =[]

            for line in lines:
                if line.startswith("home ="):
                    current_home = line.split("=", 1)[1].strip()
                    if current_home != expected_home:
                        needs_update = True
                    new_lines.append(f"home = {expected_home}\n")
                
                elif line.startswith("executable ="):
                    new_lines.append(f"executable = {expected_exe}\n")
                
                else:
                    new_lines.append(line)

            # Defensive Programming: I/O Operation nur durchführen, wenn nötig.
            if needs_update:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                logger.debug("🔄 Venv JIT-Patch erfolgreich für: %s", cfg_path.parent)

        except Exception as e:
            logger.error("❌ Kritischer Fehler beim Patchen von %s: %s", cfg_path, e)
