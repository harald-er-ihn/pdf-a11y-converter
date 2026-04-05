# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Konfigurations-Modul für zentrale Einstellungen und Pfad-Auflösungen.
Unterstützt Venvs (Linux/Mac) und Portable Python (Windows).
"""

import json
import logging
import os
import platform
import sys
from pathlib import Path

logger = logging.getLogger("pdf-converter")


def _get_app_base_dir() -> Path:
    """Ermittelt das Basisverzeichnis der App (Skript oder kompiliert)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Ermittelt den Pfad für PyInstaller-gebündelte Ressourcen."""
    base_path = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return base_path / relative_path


def get_worker_python(worker_name: str) -> Path:
    """Sucht den Python-Interpreter des isolierten Workers."""
    base_dir = _get_app_base_dir()

    # 1. Produktionspfad (Kompiliert via PyInstaller)
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            py_exe = base_dir / "workers" / worker_name / "python_env" / "python.exe"
        else:
            py_exe = base_dir / "workers" / worker_name / "venv" / "bin" / "python"

    # 2. Entwicklerpfad (Lokaler Quellcode)
    else:
        if sys.platform == "win32":
            py_exe = (
                base_dir / "workers" / worker_name / "venv" / "Scripts" / "python.exe"
            )
        else:
            py_exe = base_dir / "workers" / worker_name / "venv" / "bin" / "python"

    if not py_exe.exists():
        if getattr(sys, "frozen", False):
            raise FileNotFoundError(
                f"Portable Python fehlt für {worker_name}! Gesucht unter: {py_exe}"
            )
        logger.warning("Nutze System-Python für %s.", worker_name)
        return Path(sys.executable)

    return py_exe


def get_model_cache_dir() -> Path:
    """Liest den OS-spezifischen Modell-Cache-Pfad aus der config.json."""
    config_path = get_resource_path("config/config.json")

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                cache_setting = config["paths"]["model_cache_dir"]

                if isinstance(cache_setting, dict):
                    sys_name = platform.system().lower()
                    path_str = cache_setting.get(
                        sys_name, cache_setting.get("default", "~/.pdf-a11y-models")
                    )
                else:
                    path_str = cache_setting

                resolved_path = os.path.expandvars(os.path.expanduser(path_str))
                return Path(resolved_path)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Fehler beim Lesen der config.json: %s", e)

    return Path(os.environ.get("MODEL_CACHE_DIR", Path.home() / ".pdf-a11y-models"))
