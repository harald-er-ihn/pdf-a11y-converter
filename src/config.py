# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Konfigurations-Modul für zentrale Einstellungen und Pfad-Auflösungen.
Integriert das deterministische Offline-Modellverzeichnis.
"""

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("pdf-converter")


def _get_app_base_dir() -> Path:
    """Ermittelt das echte Basisverzeichnis der App (Skript oder kompiliert)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Ermittelt den Pfad für PyInstaller-gebündelte Ressourcen (_MEIPASS)."""
    base_path = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return base_path / relative_path


# --- NEU: Globale Modell-Konstanten ---
MODEL_DIR = get_resource_path("resources/models")


def get_model_path(name: str) -> Path:
    """Gibt den absoluten Pfad zu einem lokalen Modell zurück."""
    return MODEL_DIR / name


# --------------------------------------


def get_worker_python(worker_name: str) -> Path:
    """Sucht den Python-Interpreter des jeweiligen isolierten Workers."""
    base_dir = _get_app_base_dir()
    worker_venv = base_dir / "workers" / worker_name / "venv"

    if sys.platform == "win32":
        py_exe = worker_venv / "Scripts" / "python.exe"
    else:
        py_exe = worker_venv / "bin" / "python"

    if not py_exe.exists():
        logger.warning(
            "Worker-Venv nicht gefunden: %s. Nutze System-Python.", py_exe
        )
        return Path(sys.executable)

    return py_exe


def get_model_cache_dir() -> Path:
    """Fallback-Cache-Verzeichnis (sollte für Modelle nicht mehr primär genutzt werden)."""
    return Path(
        os.environ.get("MODEL_CACHE_DIR", Path.home() / ".pdf-a11y-models")
    )


def _load_config_json() -> dict:
    """Lädt config/config.json robust; bei Fehlern wird ein leeres Dict geliefert."""
    config_path = get_resource_path("config/config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Konnte config.json nicht laden: %s", e)

    return {}


def _platform_key() -> str:
    """Normalisiert sys.platform auf die Schlüssel der config.json."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "default"


def _resolve_configured_path(raw_path: str | Path) -> Path:
    """Expandiert Umgebungsvariablen und ~ in konfigurierten Pfaden."""
    expanded = os.path.expandvars(os.path.expanduser(str(raw_path)))
    return Path(expanded)


def get_configured_path(path_key: str, fallback: str | Path) -> Path:
    """
    Liest paths.<path_key> aus config/config.json.

    Unterstützt pro Pfad entweder:
    - einen einfachen String
    - oder ein Dict mit windows/linux/default

    Zusätzlich kann per Environment überschrieben werden:
    PDF_A11Y_<PATH_KEY>
    Beispiel:
    PDF_A11Y_JOB_DIR=/tmp/pdf-a11y-jobs
    """
    env_key = f"PDF_A11Y_{path_key.upper()}"
    env_value = os.environ.get(env_key)
    if env_value:
        return _resolve_configured_path(env_value)

    cfg = _load_config_json()
    paths = cfg.get("paths", {})
    raw_value = paths.get(path_key)

    if isinstance(raw_value, dict):
        selected = raw_value.get(_platform_key()) or raw_value.get("default")
        if selected:
            return _resolve_configured_path(selected)

    if isinstance(raw_value, str):
        return _resolve_configured_path(raw_value)

    return _resolve_configured_path(fallback)


def get_job_root_dir() -> Path:
    """
    Liefert das Root-Verzeichnis für temporäre/diagnostische Job-Artefakte.

    Darunter legt der Orchestrator pro Lauf ein job_<id>-Verzeichnis an.
    """
    fallback = Path(tempfile.gettempdir()) / "pdf-a11y-jobs"
    return get_configured_path("job_dir", fallback)


def inject_windows_dlls() -> None:
    """WINDOWS-FIX: Injiziert gebündelte GTK3/Pango/Cairo DLLs in den Python-Prozess."""
    if sys.platform == "win32":
        base_path = get_resource_path("resources/windows/gtk3")
        gtk_bin_path = base_path / "bin"
        gtk_etc_path = base_path / "etc" / "fonts"

        os.environ["GIO_USE_VOLUME_MONITOR"] = "unix"
        os.environ["G_MESSAGES_DEBUG"] = "none"

        if gtk_bin_path.exists():
            os.environ["PATH"] = (
                f"{gtk_bin_path}{os.pathsep}{os.environ.get('PATH', '')}"
            )
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(gtk_bin_path))

        if gtk_etc_path.exists():
            os.environ["FONTCONFIG_PATH"] = str(gtk_etc_path)
            os.environ["FONTCONFIG_FILE"] = str(gtk_etc_path / "fonts.conf")
