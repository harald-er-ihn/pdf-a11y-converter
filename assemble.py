# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
"""
Phase 2 der Build-Pipeline: Runtime Assembly (SRP).
Kopiert Worker-Skripte, richtet isolierte Venvs ein und kopiert
Ressourcen (veraPDF, KI-Modelle) in die Zielverzeichnisse.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
TARGETS = ["pdf-a11y-gui", "pdf-a11y-cli"]


def assemble_target(target_name: str) -> None:
    """Baut die isolierte Laufzeitumgebung für das angegebene Target zusammen."""
    print(f"\n📦 Assembly Phase für '{target_name}'...")
    target_dir = DIST_DIR / target_name

    # PyInstaller >= 6.0 mit --onedir nutzt "_internal" für Ressourcen
    internal_dir = target_dir / "_internal"

    # 1. Ressourcen kopieren (veraPDF, YOLO, GTK)
    src_resources = ROOT_DIR / "resources"
    dst_resources = internal_dir / "resources"

    if src_resources.exists():
        print("  -> Kopiere Ressourcen (veraPDF, Modelle, GTK)...")
        shutil.copytree(src_resources, dst_resources, dirs_exist_ok=True)
    else:
        print("  ⚠️ WARNUNG: Quell-Ordner 'resources' nicht gefunden!")

    # 2. Worker kopieren und Venvs einrichten
    # Die Engine sucht die Worker via Path(sys.executable).parent / "workers"
    src_workers = ROOT_DIR / "workers"
    dst_workers = target_dir / "workers"

    if src_workers.exists():
        print("  -> Kopiere Worker-Strukturen...")
        # Venvs und Caches vom Host-System strikt ignorieren!
        shutil.copytree(
            src_workers,
            dst_workers,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("venv", ".venv", "__pycache__"),
        )

        print("  -> Erstelle isolierte Venvs für Worker...")
        for worker_dir in dst_workers.iterdir():
            if worker_dir.is_dir() and (worker_dir / "requirements.txt").exists():
                print(f"     * Setup [{worker_dir.name}]...")
                venv_dir = worker_dir / "venv"

                # Venv erzeugen
                subprocess.run(
                    [sys.executable, "-m", "venv", str(venv_dir)], check=True
                )

                # Plattform-spezifische Pfade
                if sys.platform == "win32":
                    py_exe = venv_dir / "Scripts" / "python.exe"
                    pip_exe = venv_dir / "Scripts" / "pip.exe"
                else:
                    py_exe = venv_dir / "bin" / "python"
                    pip_exe = venv_dir / "bin" / "pip"

                # Pip aktualisieren & Requirements installieren
                subprocess.run(
                    [str(py_exe), "-m", "pip", "install", "--upgrade", "pip", "-q"],
                    check=False,
                )
                subprocess.run(
                    [
                        str(pip_exe),
                        "install",
                        "-r",
                        str(worker_dir / "requirements.txt"),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
    else:
        print("  ⚠️ WARNUNG: Quell-Ordner 'workers' nicht gefunden!")


def main() -> None:
    """Haupteinstiegspunkt für Phase 2."""
    print("🚀 Starte Phase 2: Runtime Assembly...")

    if not DIST_DIR.exists():
        print(
            "❌ FEHLER: 'dist' Ordner fehlt! Bitte zuerst 'python build.py' ausführen."
        )
        sys.exit(1)

    for target in TARGETS:
        if (DIST_DIR / target).exists():
            assemble_target(target)
        else:
            print(f"  ⚠️ Überspringe '{target}' (wurde nicht kompiliert).")

    print("\n🎉 Phase 2 (Assembly) erfolgreich abgeschlossen!")


if __name__ == "__main__":
    main()
