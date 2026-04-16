# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Phase 1 der Build-Pipeline: PyInstaller Core Build (SRP).
Kompiliert die Hauptanwendung (GUI & CLI) in strikt getrennte Verzeichnisse.
"""

import os
import shutil
import stat
import sys
import warnings
from pathlib import Path

import customtkinter
import PyInstaller.__main__

# WINDOWS-FIX: OS-Spracheinstellungen nur auf POSIX-Systemen erzwingen,
# da Windows-Codepages durch LANG="C" irritiert werden können.
if sys.platform != "win32":
    os.environ["LANG"] = "C"
    os.environ["LC_ALL"] = "C"

warnings.filterwarnings("ignore", category=DeprecationWarning, module="PyInstaller")

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build_temp"
CTK_PATH = Path(customtkinter.__file__).parent.resolve()


def _remove_readonly(func, path, _):
    """
    WINDOWS-FIX: Fehler-Handler für shutil.rmtree.
    Entfernt den Read-Only-Schutz von Dateien, die unter Windows (z.B. von git)
    schreibgeschützt angelegt wurden, damit rmtree nicht abstürzt.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clean_directories() -> None:
    """Bereinigt alte Build-Artefakte robust auf allen Systemen."""
    print("🧹 Bereinige alte Builds...")
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            # WINDOWS-FIX: onexc (Python 3.12+) ersetzt onerror und
            # behandelt hartnäckige Windows-Dateisperren.
            shutil.rmtree(d, onexc=_remove_readonly)


def build_gui() -> None:
    """Kompiliert die GUI-Version mit allen UI-Abhängigkeiten."""
    print("\n⚙️ Kompiliere PDF-A11y-GUI...")

    args = [
        str(ROOT_DIR / "app_gui.py"),
        "--name=pdf-a11y-gui",
        "--onedir",
        "--noconsole",
        "--clean",
        "--workpath",
        str(BUILD_DIR),
        "--distpath",
        str(DIST_DIR),
        # WINDOWS-FIX: os.pathsep garantiert ; auf Windows und : auf Linux
        f"--add-data={CTK_PATH}{os.pathsep}customtkinter/",
        f"--add-data={ROOT_DIR / 'config' / 'config.json'}{os.pathsep}config/",
        f"--add-data={ROOT_DIR / 'config' / 'nllb_mapping.json'}{os.pathsep}config/",
        f"--add-data={ROOT_DIR / 'static'}{os.pathsep}static/",
        f"--add-data={ROOT_DIR / 'README.md'}{os.pathsep}.",
        f"--add-data={ROOT_DIR / 'ARCHITECTURE.md'}{os.pathsep}.",
        "--hidden-import=PIL._tkinter_finder",
        "--hidden-import=pymupdf",
        "--hidden-import=fitz",
        "--exclude-module=tensorboard",
        "--noconfirm",
    ]
    PyInstaller.__main__.run(args)


def build_cli() -> None:
    """Kompiliert die headless CLI-Version (optimiert, ohne UI-Bloat)."""
    print("\n⚙️ Kompiliere PDF-A11y-CLI (Headless)...")

    args = [
        str(ROOT_DIR / "cli.py"),
        "--name=pdf-a11y-cli",
        "--onedir",
        "--console",
        "--clean",
        "--workpath",
        str(BUILD_DIR),
        "--distpath",
        str(DIST_DIR),
        f"--add-data={ROOT_DIR / 'config' / 'config.json'}{os.pathsep}config/",
        f"--add-data={ROOT_DIR / 'config' / 'nllb_mapping.json'}{os.pathsep}config/",
        f"--add-data={ROOT_DIR / 'static'}{os.pathsep}static/",
        f"--add-data={ROOT_DIR / 'README.md'}{os.pathsep}.",
        f"--add-data={ROOT_DIR / 'ARCHITECTURE.md'}{os.pathsep}.",
        "--hidden-import=pymupdf",
        "--hidden-import=fitz",
        "--exclude-module=customtkinter",
        "--exclude-module=tkinter",
        "--exclude-module=tensorboard",
        "--noconfirm",
    ]
    PyInstaller.__main__.run(args)


def main() -> None:
    print("🚀 Starte PyInstaller Phase 1 (Core Binaries)...")
    clean_directories()
    build_gui()
    build_cli()
    print("\n🎉 Phase 1 (Core Build) erfolgreich abgeschlossen!")


if __name__ == "__main__":
    main()
